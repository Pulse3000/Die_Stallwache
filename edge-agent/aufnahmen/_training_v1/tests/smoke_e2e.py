# -*- coding: utf-8 -*-
"""
Ende-zu-Ende-Probelauf der Trainings-Pipeline (ohne Stalldaten, CPU, ~30–60 s):

  synthetische Bilder + CVAT-Export (Box + Skelett)  ->  cvat_zu_yolo_pose.py (Datensatz-ZIP)
  ->  Colab-Notebook ausgeführt im Probelauf-Modus (1 Epoche, 320 px)  ->  best_v1.pt/.onnx, Gates, Modellkarte
  ->  Versionsschutz (zweiter Lauf muss abbrechen)
  ->  ONNX-Backend der Gates gegen Ultralytics geprüft (COCO-Pose-Modell, Beispielbild aus dem Paket)
  ->  Gate-Modi `laufzeit` und `tag` (JSONL + Auswertung)

Aufruf:  python3 tests/smoke_e2e.py     (Exit-Code 0 = alles grün)
Belegt NICHT die Modellqualität — nur, dass die Mechanik vom CVAT-Export bis zur Modellkarte trägt.
"""
import glob
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

import cv2
import numpy as np

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
sys.path.insert(0, os.path.join(WURZEL, "werkzeuge"))
import cvat_zu_yolo_pose as konv  # noqa: E402
import abnahme_gates as gates  # noqa: E402

ERGEBNISSE = []


def pruefe(name, bedingung, info=""):
    ERGEBNISSE.append((name, bool(bedingung), info))
    print(("OK   " if bedingung else "FEHL ") + name + (f" — {info}" if info else ""), flush=True)


# ----------------------------------------------------------------------------- synthetische Daten
def zeichne_kuh(img, cx, cy, s, rng, ir):
    farbe = (60, 60, 60) if ir else rng.choice([(40, 70, 140), (30, 30, 30), (200, 200, 200)])
    for dx in (-80, -50, 50, 80):                                         # Beine
        cv2.rectangle(img, (int(cx + dx * s), int(cy + 20 * s)), (int(cx + (dx + 14) * s), int(cy + 110 * s)), farbe, -1)
    cv2.ellipse(img, (int(cx), int(cy)), (int(110 * s), int(55 * s)), 0, 0, 360, farbe, -1)    # Rumpf
    cv2.circle(img, (int(cx - 125 * s), int(cy - 30 * s)), int(28 * s), farbe, -1)              # Kopf
    se = (cx - 95 * s, cy - 45 * s)
    tb = (cx + 100 * s, cy - 35 * s)
    a = math.radians(rng.uniform(10, 40) if rng.random() < 0.3 else rng.uniform(70, 110))
    tt = (tb[0] + 90 * s * math.cos(a), tb[1] + 90 * s * math.sin(a))
    cv2.line(img, (int(tb[0]), int(tb[1])), (int(tt[0]), int(tt[1])), farbe, max(2, int(6 * s)))
    cv2.circle(img, (int(tt[0]), int(tt[1])), max(3, int(9 * s)), (20, 20, 20), -1)
    box = (cx - 155 * s, cy - 60 * s, max(cx + 115 * s, tt[0] + 10 * s), max(cy + 112 * s, tt[1] + 10 * s))
    return box, (se, tb, tt)


def erzeuge_daten(ordner, rng):
    os.makedirs(ordner, exist_ok=True)
    manifest, bilder_xml = [], []
    tage = {"20261012": "train", "20261013": "val", "20261014": "train"}
    w, h = 1280, 720
    for tag, split in tage.items():
        for i in range(20 if split == "train" else 12):
            ir = i % 3 == 0
            name = f"{tag}-{10 + i // 2:02d}{(i % 2) * 30:02d}00.jpg"   # 12–21:30 Uhr Ortszeit: Stalltag = Datum
            img = np.full((h, w, 3), (95, 105, 100) if not ir else (80, 80, 80), np.uint8)
            img = cv2.add(img, rng_np.integers(0, 25, img.shape, dtype=np.uint8))
            els = []
            n_kuehe = 0 if i % 5 == 4 else rng.randint(1, 3)          # jedes 5. Bild leer (Negativ)
            for k in range(n_kuehe):
                cx, cy = 250 + k * 380 + rng.uniform(-40, 40), 330 + rng.uniform(-60, 60)
                box, (se, tb, tt) = zeichne_kuh(img, cx, cy, rng.uniform(0.8, 1.2), rng, ir)
                tt_status = "outside" if rng.random() < 0.15 else ("occluded" if rng.random() < 0.1 else "")
                els.append(f'<box label="kuh" source="manual" occluded="0" xtl="{box[0]:.1f}" ytl="{box[1]:.1f}" '
                           f'xbr="{box[2]:.1f}" ybr="{box[3]:.1f}" z_order="0"></box>')
                pts = []
                for lab, p, st in (("spine_end", se, ""), ("tail_base", tb, ""), ("tail_tip", tt, tt_status)):
                    pts.append(f'<points label="{lab}" source="manual" outside="{int(st == "outside")}" '
                               f'occluded="{int(st == "occluded")}" points="{p[0]:.1f},{p[1]:.1f}"></points>')
                els.append('<skeleton label="kuh_pose" source="manual" z_order="0">' + "".join(pts) + "</skeleton>")
            if i in (3, 7) and split == "train" or (i == 2 and split == "val"):   # wenige "Fruchtblasen"
                cv2.ellipse(img, (1100, 600), (40, 50), 0, 0, 360, (180, 160, 200), -1)
                els.append('<box label="amniotic_sac" source="manual" occluded="0" xtl="1058" ytl="548" xbr="1142" '
                           'ybr="652" z_order="0"></box>')
            cv2.imwrite(os.path.join(ordner, name), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            bilder_xml.append((name, els))
            manifest.append({"datei": name, "split": split, "licht": "IR" if ir else "Tag", "lokalzeit": "",
                             "helligkeit": "", "schaerfe": "", "task": f"{split}_01", "defekt_anteil": 0.0,
                             "ansicht_grob": "A"})
    xml = ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>", "<version>1.1</version>"]
    for i, (name, els) in enumerate(bilder_xml):
        xml.append(f'<image id="{i}" name="{name}" width="{w}" height="{h}">' + "".join(els) + "</image>")
    xml.append("</annotations>")
    return manifest, "\n".join(xml)


# ----------------------------------------------------------------------------- Ablauf
def main():
    global rng_np
    t0 = time.time()
    rng, rng_np = random.Random(1), np.random.default_rng(1)
    tmp = tempfile.mkdtemp(prefix="stallwache_smoke_")
    bilder = os.path.join(tmp, "aufnahmen")
    manifest, xml_text = erzeuge_daten(bilder, rng)
    import csv
    mpfad = os.path.join(tmp, "manifest.csv")
    with open(mpfad, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(manifest[0]))
        wr.writeheader()
        wr.writerows(manifest)
    import zipfile
    export = os.path.join(tmp, "export_task.zip")
    with zipfile.ZipFile(export, "w") as zf:
        zf.writestr("annotations.xml", xml_text)

    # 1) Konverter
    ds = os.path.join(tmp, "datensatz_v1")
    b = konv.konvertiere([export], bilder, mpfad, ds, max_seite=640, zip_erstellen=True,
                         beilagen=[os.path.join(WURZEL, "werkzeuge", f) for f in ("abnahme_gates.py", "bildqualitaet.py")])
    pruefe("Konverter: Datensatz + ZIP", os.path.exists(b["zip"]) and b["fehler_anzahl"] == 0,
           f"train {b['splits']['train'].get('bilder')} / val {b['splits']['val'].get('bilder')} Bilder, "
           f"Puffer {b['uebersprungen'].get('puffer_zu_val', 0)}")
    from ultralytics.data.utils import check_det_dataset
    cfg = check_det_dataset(os.path.join(ds, "data.yaml"))
    pruefe("Ultralytics akzeptiert data.yaml", cfg["kpt_shape"] == [3, 3] and cfg["nc"] == 3 and os.path.isabs(str(cfg["path"])),
           f"path={cfg['path']}")

    # 2) Notebook im Probelauf-Modus
    drive = os.path.join(tmp, "drive")
    os.makedirs(drive)
    shutil.copyfile(b["zip"], os.path.join(drive, "datensatz_v1.zip"))
    env = dict(os.environ, STALLWACHE_SMOKE="1", STALLWACHE_DRIVE=drive, STALLWACHE_ARBEIT=os.path.join(tmp, "arbeit"))
    nb = os.path.join(tmp, "stallwache_training_v1.ipynb")          # Kopie: nichts landet im Quellbaum
    shutil.copyfile(os.path.join(WURZEL, "colab", "stallwache_training_v1.ipynb"), nb)
    aus_nb = os.path.join(tmp, "ausgefuehrt.ipynb")
    r = subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", nb,
                        "--output", aus_nb, "--ExecutePreprocessor.timeout=1500"], env=env, capture_output=True, text=True,
                       cwd=tmp)
    pruefe("Notebook läuft komplett durch", r.returncode == 0, (r.stderr or "")[-800:] if r.returncode else "")
    modelle = os.path.join(drive, "modelle")
    erwartet = ["best_v1.pt", "best_v1.onnx", "gates_v1.json", "gates_v1.md", "MODELLKARTE_v1.md"]
    vorhanden = sorted(os.listdir(modelle)) if os.path.isdir(modelle) else []
    pruefe("Drive-Ergebnisse vollständig", all(e in vorhanden for e in erwartet), str(vorhanden))
    if os.path.exists(os.path.join(modelle, "gates_v1.json")):
        g = json.load(open(os.path.join(modelle, "gates_v1.json")))
        pruefe("Gates berechnet (A/A2/B/B2/C/D vorhanden)", set(g["gates"]) == {"A", "A2", "B", "B2", "C", "D"},
               g["gesamt"])
        pruefe("Gates verbindlich am ONNX-Modell gemessen", g.get("verbindlich") and g["modell"].endswith(".onnx"), g["modell"])
        # Mechanik: Gate A muss die eine synthetische Fruchtblase im Val-Set als Grundwahrheit zählen
        # (das 1-Epochen-Modell findet sie erwartungsgemäß nicht -> Recall 0/1, NICHT BESTANDEN ist hier korrekt)
        pruefe("Gate A zählt die synthetische Fruchtblase als Grundwahrheit", "/1 Bilder)" in g["gates"]["A"]["messwert"],
               g["gates"]["A"]["messwert"])
    kandidaten = glob.glob(os.path.join(drive, "kandidaten", "v1_*", "best.pt"))
    pruefe("Kandidat direkt nach dem Training in Drive gesichert", len(kandidaten) == 1, str(kandidaten))
    pruefe("B7: Datensatz-ZIP nach dem Lauf aus Drive entfernt, Laufsicherung ohne Bilder",
           not os.path.exists(os.path.join(drive, "datensatz_v1.zip"))
           and not glob.glob(os.path.join(drive, "**", "*.jpg"), recursive=True),
           str(glob.glob(os.path.join(drive, "**", "*.jpg"), recursive=True)[:3]))
    if os.path.exists(os.path.join(modelle, "MODELLKARTE_v1.md")):
        karte = open(os.path.join(modelle, "MODELLKARTE_v1.md"), encoding="utf-8").read()
        pruefe("Modellkarte enthält Daten, Metriken, Gates", all(s in karte for s in ("## Daten", "## Val-Metriken", "## Abnahme-Gates")))

    # 3) Versionsschutz: zweiter Lauf mit gleicher VERSION muss abbrechen
    r2 = subprocess.run([sys.executable, "-m", "jupyter", "nbconvert", "--to", "notebook", "--execute", nb,
                         "--output", os.path.join(tmp, "zweiter.ipynb"), "--ExecutePreprocessor.timeout=600"], env=env,
                        capture_output=True, text=True, cwd=tmp)
    pruefe("Versionsschutz: kein Überschreiben von best_v1.pt", r2.returncode != 0 and "existiert schon" in (r2.stderr + r2.stdout))

    # 4) ONNX-Backend der Gates gegen Ultralytics (COCO-Pose, Beispielbild aus dem Paket)
    import ultralytics
    from ultralytics import YOLO
    alt_cwd = os.getcwd()
    os.chdir(tmp)                                                 # Download/Export nur im Temp-Ordner
    bus = os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg")
    pose_pt = os.path.join(tmp, "yolov8n-pose.pt")
    m = YOLO("yolov8n-pose.pt")
    onnx_coco = m.export(format="onnx", imgsz=640, simplify=True, dynamic=False)
    img = cv2.imread(bus)
    p_ul = gates.UltralyticsModell("yolov8n-pose.pt", 640, konf=0.5)(img)
    p_ox = gates.OnnxModell(onnx_coco, n_kpts=17, konf=0.5)(img)
    treffer = []
    for p in p_ul:
        beste = max(((gates.iou(p["xyxy"], q["xyxy"]), q) for q in p_ox), key=lambda t: t[0]) if p_ox else (0, None)
        if beste[1] is not None:
            kp_abst = np.mean([math.hypot(a[0] - b_[0], a[1] - b_[1]) for a, b_ in zip(p["kpts"], beste[1]["kpts"]) if a[2] > 0.5])
            treffer.append((beste[0], kp_abst))
    ok = len(p_ul) >= 3 and len(treffer) == len(p_ul) and all(i > 0.85 and (math.isnan(k) or k < 0.02) for i, k in treffer)
    pruefe("ONNX-Backend = Ultralytics (Boxen IoU > 0.85, Keypoints < 2 % Bildbreite)", ok,
           f"{len(p_ul)} vs {len(p_ox)} Personen; IoU/Abstand: {[(round(i, 3), round(float(k), 4)) for i, k in treffer]}")
    os.chdir(alt_cwd)

    # 5) Gate-Modi laufzeit + tag mit dem trainierten Probe-Modell
    onnx_v1 = os.path.join(modelle, "best_v1.onnx")
    if os.path.exists(onnx_v1):
        e = gates.pruefe_tag(onnx_v1, bilder, "20261013-*.jpg", None, max_bilder=5)
        pruefe("Modus laufzeit liefert FPS", e["fps_inferenz"] > 0 and e["fps_gesamt"] > 0,
               f"{e['fps_gesamt']} FPS Ende-zu-Ende, {e['fps_inferenz']} FPS Inferenz")
        jl = os.path.join(tmp, "tag.jsonl")
        e1 = gates.pruefe_tag(onnx_v1, bilder, "20261013-*.jpg", jl, max_bilder=6)
        e2 = gates.pruefe_tag(onnx_v1, bilder, "20261013-*.jpg", jl)      # Fortsetzung
        ausw = gates.auswerten_jsonl(jl)
        pruefe("Modus tag fortsetzbar + Auswertung", e2["vollstaendig"] and ausw["bilder"] == 12, json.dumps(ausw)[:200])

    shutil.rmtree(tmp, ignore_errors=True)
    fehl = [n for n, ok, _ in ERGEBNISSE if not ok]
    print(f"\n{len(ERGEBNISSE) - len(fehl)}/{len(ERGEBNISSE)} Prüfungen grün in {time.time() - t0:.0f} s")
    return 1 if fehl else 0


if __name__ == "__main__":
    sys.exit(main())
