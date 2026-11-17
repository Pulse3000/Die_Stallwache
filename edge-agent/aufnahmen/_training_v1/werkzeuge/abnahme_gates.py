#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Abnahme-Gates für ein Stallwache-YOLO-Pose-Modell (training-pipeline, Abschnitt 5).

Ein Modell wird nur `best_vN.pt` und scharfgeschaltet, wenn alle Gates bestanden sind.
VERBINDLICH ist das Ergebnis am ONNX-Modell (so läuft es auf dem Hof-Rechner) — Gates am .pt dienen nur
zur Information (andere Letterbox, Konfidenzen weichen messbar ab).

  A   Austreibung-Recall: in JEDEM Val-Bild mit Fruchtblase/Kälberfüßen muss das Modell mindestens
      eine Austreibungs-Detektion mit Konfidenz > 0.80 liefern (Recall = 1.0, bildweise).
      Ohne echte Geburt im Val-Set: OFFEN -> Austreibungs-Logik bleibt im Silent Mode.
  A2  Austreibungs-Fehlalarme: in Val-Bildern ohne Fruchtblase/Füße darf keine Austreibungs-Detektion
      > 0.80 vorkommen (Austreibung hat bewusst keinen Zeitfilter/Cooldown: jede solche Detektion wäre
      ein Sofort-Alarm).
  B   Schwanzwinkel: mittlere |Winkel(Modell) − Winkel(Hand)| < 10° über ≥ 30 Kühe mit allen 3
      gelabelten Punkten (Zuordnung Modell↔Hand über Box-IoU ≥ 0.5). Wie im Agenten (B19) zählt eine
      Vorhersage nur, wenn alle 3 Punkte eine Sichtbarkeit ≥ 0.5 haben — sonst rechnet der Agent keinen Winkel.
  B2  Messbarkeit: Anteil der zugeordneten Kühe mit messbarem Modell-Winkel bei erhobenem Schwanz
      (Hand-Winkel > 45°) höchstens 10 Prozentpunkte unter dem bei anliegendem Schwanz (je n ≥ 30).
      Fällt gerade der erhobene Schwanz öfter unter die Sichtbarkeit, fehlt dem 30-min-Fenster still die
      Evidenz, nach der es sucht (Einwand ki-wache, 05.11.2026).
  C   Fehlalarm-Budget 24 h (0 Austreibungs-, ≤ 1 Kalbeverdacht-Fehlalarm): Austreibungs-Teil exakt im
      Modus `tag` über einen kompletten, unausgedünnten Stalltag (auch Defektbilder werden ausgewertet und
      getrennt ausgewiesen). Der Kalbeverdacht-Teil braucht den Agenten (ByteTrack + 30-min-Fenster +
      Cooldown) — dafür schreibt `tag` die Vorhersagen als JSONL für den Replay. Bis dahin: OFFEN.
  D   Laufzeit ≥ 1 FPS auf der Zielhardware, gemessen Ende-zu-Ende je Bild (Lesen + Qualitätsprüfung +
      Inferenz; ohne Tracking/Logik) im Modus `tag` oder `laufzeit` auf dem Hof-Rechner.

Austreibungsklassen werden im ONNX-Backend unabhängig ausgewertet (Mehrfach-Label je Anker): eine
Fruchtblase direkt an der Kuh geht nicht verloren, nur weil "kuh" am selben Anker höher bewertet ist.

Aufrufe
  python3 abnahme_gates.py val      --modell best_v1.onnx --daten datensatz_v1/data.yaml [--json g.json --md g.md]
  python3 abnahme_gates.py tag      --modell best_v1.onnx --bilder-ordner ../.. --stalltag 2026-10-18 --jsonl tag.jsonl --zeitlimit 160
  python3 abnahme_gates.py laufzeit --modell best_v1.onnx --bilder-ordner ../.. --stalltag 2026-10-18 --anzahl 30

Schwanzwinkel-Definition (ki-wache-kern): Winkel zwischen spine_end→tail_base und tail_base→tail_tip,
per atan2, in Pixeln (nicht in normierten Koordinaten — das Bild ist 16:9). Muss identisch zur Funktion im
Agenten sein; mit --winkel modul:funktion lässt sich die Agenten-Funktion direkt verwenden.
"""
import argparse
import datetime as dt
import fnmatch
import hashlib
import glob
import importlib
import json
import math
import os
import platform
import re
import sys
import time

KLASSEN = ["kuh", "amniotic_sac", "calf_legs"]
AUSTREIBUNG = (1, 2)
KONF_AUSTREIBUNG = 0.80
WINKEL_MAX_ABWEICHUNG = 10.0
WINKEL_MIN_N = 30
SICHTBAR_MIN = 0.5            # wie modell.keypoint_sichtbar_min im Agenten (B19)
WINKEL_SCHWELLE = 45.0        # logik.winkel_schwelle_grad
MESSBAR_MAX_LUECKE = 0.10     # Gate B2: höchstens 10 Prozentpunkte weniger messbar bei erhobenem Schwanz
MESSBAR_MIN_N = WINKEL_MIN_N  # je Gruppe n >= 30: eine Kuh darf das Gate nicht kippen
IOU_KUH = 0.5
FPS_MIN = 1.0
SCHWELLE_DEFEKT = 0.04


# ----------------------------------------------------------------------------- Geometrie / Zeit
def schwanzwinkel(spine_end, tail_base, tail_tip):
    """Winkel in Grad (0..180) zwischen spine_end→tail_base und tail_base→tail_tip."""
    v1 = (tail_base[0] - spine_end[0], tail_base[1] - spine_end[1])
    v2 = (tail_tip[0] - tail_base[0], tail_tip[1] - tail_base[1])
    if (v1[0] == 0 and v1[1] == 0) or (v2[0] == 0 and v2[1] == 0):
        return float("nan")
    kreuz = v1[0] * v2[1] - v1[1] * v2[0]
    punkt = v1[0] * v2[0] + v1[1] * v2[1]
    return abs(math.degrees(math.atan2(kreuz, punkt)))


def lade_winkelfunktion(spez):
    if not spez:
        return schwanzwinkel
    modul, funktion = spez.split(":")
    return getattr(importlib.import_module(modul), funktion)


def iou(a, b):
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


_ZEIT_RE = re.compile(r"(\d{8})-(\d{6})")


def stalltag(name):
    """Wie cvat_zu_yolo_pose.stalltag: UTC-Dateiname -> Ortszeit (Europe/Berlin) minus 12 h -> Datum."""
    m = _ZEIT_RE.search(os.path.basename(name))
    if not m:
        return None
    from zoneinfo import ZoneInfo
    t = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
    return (t.astimezone(ZoneInfo("Europe/Berlin")) - dt.timedelta(hours=12)).date().isoformat()


# ----------------------------------------------------------------------------- Ground Truth
def lies_yaml_einfach(pfad):
    """Minimaler YAML-Leser für die vom Konverter geschriebene data.yaml (ohne PyYAML-Abhängigkeit)."""
    daten, namen, in_namen = {}, {}, False
    with open(pfad, encoding="utf-8") as fh:
        for zeile in fh:
            z = zeile.split("#", 1)[0].rstrip()
            if not z.strip():
                continue
            if in_namen and z.startswith("  "):
                k, v = z.strip().split(":", 1)
                namen[int(k)] = v.strip()
                continue
            in_namen = False
            k, v = z.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "names":
                in_namen = True
            elif v.startswith("["):
                daten[k] = json.loads(v)
            else:
                daten[k] = v
    daten["names"] = namen
    return daten


def bildgroesse(pfad):
    try:
        from PIL import Image
        with Image.open(pfad) as im:
            return im.size
    except ImportError:
        import cv2
        h, w = cv2.imread(pfad).shape[:2]
        return w, h


def lade_gt(daten_yaml, split="val"):
    """{stamm: {"bild": pfad, "w": W, "h": H, "objekte": [{"cls", "xyxy" (norm), "kpts" [(x,y,v)] (norm)}]}}"""
    basis = os.path.dirname(os.path.abspath(daten_yaml))
    cfg = lies_yaml_einfach(daten_yaml)
    bild_ordner = os.path.join(basis, cfg[split])
    label_ordner = bild_ordner.replace(os.sep + "images", os.sep + "labels")
    gt = {}
    for bild in sorted(glob.glob(os.path.join(bild_ordner, "*.jpg"))):
        stamm = os.path.splitext(os.path.basename(bild))[0]
        w, h = bildgroesse(bild)
        objekte = []
        lp = os.path.join(label_ordner, stamm + ".txt")
        if os.path.exists(lp):
            with open(lp) as fh:
                for zeile in fh:
                    t = zeile.split()
                    if not t:
                        continue
                    c, cx, cy, bw, bh = int(t[0]), *map(float, t[1:5])
                    kp = [tuple(map(float, t[i:i + 3])) for i in range(5, len(t), 3)]
                    objekte.append({"cls": c, "xyxy": (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2), "kpts": kp})
        gt[stamm] = {"bild": bild, "w": w, "h": h, "objekte": objekte}
    return gt


# ----------------------------------------------------------------------------- Vorhersage-Backends
def cpu_ohne_sse41():
    try:
        with open("/proc/cpuinfo") as fh:
            return "sse4_1" not in fh.read()
    except OSError:
        return False


def dekodiere_pose(aus, n_kpts, konf, iou_nms, links, oben, r, w, h, mehrfach_klassen=AUSTREIBUNG):
    """Rohausgabe (4 + nc + 3*n_kpts, N) eines YOLOv8-Pose-ONNX -> Liste von Objekten (normierte Koordinaten).
    Scores und Keypoint-Sichtbarkeit sind im Export bereits sigmoid-aktiviert. Klassen in `mehrfach_klassen`
    werden zusätzlich unabhängig vom argmax ausgewertet (Recall der Austreibung vor allem anderen)."""
    import cv2
    import numpy as np
    nc = aus.shape[0] - 4 - 3 * n_kpts
    if nc < 1:
        raise ValueError(f"Modellausgabe {aus.shape} passt nicht zu {n_kpts} Keypoints")
    scores = aus[4:4 + nc]
    argmax = scores.argmax(0)
    kand_anker, kand_cls, kand_conf = [], [], []
    for j in np.where(scores[argmax, np.arange(scores.shape[1])] >= konf)[0]:
        kand_anker.append(int(j)); kand_cls.append(int(argmax[j])); kand_conf.append(float(scores[argmax[j], j]))
    for c in mehrfach_klassen:
        if c < nc:
            for j in np.where((scores[c] >= konf) & (argmax != c))[0]:
                kand_anker.append(int(j)); kand_cls.append(int(c)); kand_conf.append(float(scores[c, j]))
    if not kand_anker:
        return []
    a = np.array(kand_anker)
    cx, cy, bw, bh = aus[0, a], aus[1, a], aus[2, a], aus[3, a]
    x1 = np.clip((cx - bw / 2 - links) / r, 0, w)
    y1 = np.clip((cy - bh / 2 - oben) / r, 0, h)
    x2 = np.clip((cx + bw / 2 - links) / r, 0, w)
    y2 = np.clip((cy + bh / 2 - oben) / r, 0, h)
    boxen = [[float(p), float(q), float(s - p), float(t - q)] for p, q, s, t in zip(x1, y1, x2, y2)]
    keep = cv2.dnn.NMSBoxesBatched(boxen, kand_conf, kand_cls, konf, iou_nms)
    kp_roh = aus[4 + nc:, :]
    ergebnis = []
    for k in np.array(keep).reshape(-1):
        k = int(k)
        j = kand_anker[k]
        kp = [(float((kp_roh[3 * i, j] - links) / r / w), float((kp_roh[3 * i + 1, j] - oben) / r / h),
               float(kp_roh[3 * i + 2, j])) for i in range(n_kpts)]
        ergebnis.append({"cls": kand_cls[k], "conf": kand_conf[k],
                         "xyxy": (float(x1[k] / w), float(y1[k] / h), float(x2[k] / w), float(y2[k] / h)), "kpts": kp})
    return ergebnis


class OnnxModell:
    """YOLOv8-Pose als ONNX (statisch, quadratisch), ONNX Runtime CPU. Vorverarbeitung = Agent auf dem Hof:
    quadratische Letterbox (Rand 114), RGB, /255."""

    def __init__(self, pfad, n_kpts=3, threads=0, konf=0.25, iou_nms=0.7):
        import onnxruntime as ort
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(pfad, so, providers=["CPUExecutionProvider"])
        inp = self.sess.get_inputs()[0]
        self.eingang, self.groesse = inp.name, int(inp.shape[2])
        self.n_kpts, self.konf, self.iou_nms = n_kpts, konf, iou_nms

    def __call__(self, img):
        import cv2
        import numpy as np
        h, w = img.shape[:2]
        s = self.groesse
        r = min(s / h, s / w)
        nh, nw = int(round(h * r)), int(round(w * r))
        oben, links = (s - nh) // 2, (s - nw) // 2
        lw = np.full((s, s, 3), 114, np.uint8)
        lw[oben:oben + nh, links:links + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = np.ascontiguousarray(lw[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0)
        aus = self.sess.run(None, {self.eingang: x})[0][0]
        return dekodiere_pose(aus, self.n_kpts, self.konf, self.iou_nms, links, oben, r, w, h)


class UltralyticsModell:
    def __init__(self, pfad, bildgroesse=640, konf=0.25):
        import torch
        if cpu_ohne_sse41():
            torch.backends.mkldnn.enabled = False
        from ultralytics import YOLO
        self.m, self.bildgroesse, self.konf = YOLO(pfad), bildgroesse, konf

    def __call__(self, img):
        r = self.m.predict(img, imgsz=self.bildgroesse, conf=self.konf, verbose=False)[0]
        ergebnis = []
        if r.boxes is None:
            return ergebnis
        boxen = r.boxes.xyxyn.cpu().numpy()
        kp = r.keypoints.data.cpu().numpy() if r.keypoints is not None else None
        h, w = r.orig_shape
        for i in range(len(boxen)):
            kpts = []
            if kp is not None:
                for x, y, c in kp[i]:
                    kpts.append((float(x) / w, float(y) / h, float(c)))
            ergebnis.append({"cls": int(r.boxes.cls[i]), "conf": float(r.boxes.conf[i]),
                             "xyxy": tuple(float(v) for v in boxen[i]), "kpts": kpts})
        return ergebnis


def rechner_info():
    modell = platform.processor() or platform.machine()
    try:
        with open("/proc/cpuinfo") as fh:
            for zeile in fh:
                if zeile.startswith("model name"):
                    modell = zeile.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    return f"{modell}, {os.cpu_count()} logische Kerne sichtbar"


def lade_modell(pfad, bildgroesse=640, threads=0):
    if str(pfad).lower().endswith(".onnx"):
        return OnnxModell(pfad, threads=threads)
    return UltralyticsModell(pfad, bildgroesse)


def sage_vorher(modell, gt):
    import cv2
    vorhersagen = {}
    for stamm, g in gt.items():
        vorhersagen[stamm] = modell(cv2.imread(g["bild"]))
    return vorhersagen


# ----------------------------------------------------------------------------- Gates
def gate_austreibung(gt, vorhersagen, schwelle=KONF_AUSTREIBUNG):
    mit, treffer, fehl_bilder, fehlalarme = 0, 0, [], []
    for stamm, g in gt.items():
        hat_gt = any(o["cls"] in AUSTREIBUNG for o in g["objekte"])
        alarm = any(p["cls"] in AUSTREIBUNG and p["conf"] > schwelle for p in vorhersagen.get(stamm, []))
        if hat_gt:
            mit += 1
            if alarm:
                treffer += 1
            else:
                fehl_bilder.append(stamm)
        elif alarm:
            fehlalarme.append(stamm)
    if mit == 0:
        a = {"status": "OFFEN", "messwert": "keine Fruchtblase/Füße im Val-Set",
             "hinweis": "Austreibungs-Logik bleibt im Silent Mode, bis eine echte Geburt im Val-Set ist."}
    else:
        rec = treffer / mit
        a = {"status": "BESTANDEN" if treffer == mit else "NICHT BESTANDEN",
             "messwert": f"Recall {rec:.3f} ({treffer}/{mit} Bilder)", "verpasst": fehl_bilder[:50]}
    a2 = {"status": "BESTANDEN" if not fehlalarme else "NICHT BESTANDEN",
          "messwert": f"{len(fehlalarme)} Bilder mit Austreibungs-Detektion > {schwelle} ohne Fruchtblase/Füße",
          "beispiele": fehlalarme[:50]}
    return a, a2


def gate_schwanzwinkel(gt, vorhersagen, winkel=schwanzwinkel, min_n=WINKEL_MIN_N, grenze=WINKEL_MAX_ABWEICHUNG,
                       sichtbar_min=SICHTBAR_MIN):
    abweichungen, nicht_gefunden, beispiele = [], 0, []
    messbar = {"flach": [0, 0], "hoch": [0, 0]}   # [messbar, zugeordnet] nach Hand-Winkel <= / > 45°
    for stamm, g in gt.items():
        w, h = g["w"], g["h"]
        kandidaten = [o for o in g["objekte"] if o["cls"] == 0 and len(o["kpts"]) == 3 and all(v > 0 for _, _, v in o["kpts"])]
        preds = [p for p in vorhersagen.get(stamm, []) if p["cls"] == 0 and len(p["kpts"]) == 3]
        paare = sorted(((iou(o["xyxy"], p["xyxy"]), oi, pi) for oi, o in enumerate(kandidaten) for pi, p in enumerate(preds)),
                       reverse=True)
        o_frei, p_frei = set(range(len(kandidaten))), set(range(len(preds)))
        for wert, oi, pi in paare:
            if wert < IOU_KUH:
                break
            if oi in o_frei and pi in p_frei:
                o_frei.discard(oi)
                p_frei.discard(pi)
                gpx = [(x * w, y * h) for x, y, _ in kandidaten[oi]["kpts"]]
                a_gt = winkel(*gpx)
                if math.isnan(a_gt):
                    continue
                gruppe = messbar["hoch" if a_gt > WINKEL_SCHWELLE else "flach"]
                gruppe[1] += 1
                if any(v < sichtbar_min for _, _, v in preds[pi]["kpts"]):
                    continue            # wie im Agenten: unsichtbarer Punkt -> kein Winkel
                ppx = [(x * w, y * h) for x, y, _ in preds[pi]["kpts"]]
                a_p = winkel(*ppx)
                if math.isnan(a_p):
                    continue
                gruppe[0] += 1
                d = abs(a_gt - a_p)
                abweichungen.append(d)
                if len(beispiele) < 30:
                    beispiele.append({"bild": stamm, "hand": round(a_gt, 1), "modell": round(a_p, 1), "abweichung": round(d, 1)})
        nicht_gefunden += len(o_frei)
    n = len(abweichungen)
    if n < min_n:
        return {"status": "OFFEN", "messwert": f"nur {n} auswertbare Kühe (mind. {min_n})",
                "nicht_gefunden": nicht_gefunden, "beispiele": beispiele, "messbar": messbar}
    mittel = sum(abweichungen) / n
    return {"status": "BESTANDEN" if mittel < grenze else "NICHT BESTANDEN",
            "messwert": f"mittlere Abweichung {mittel:.1f}° (n={n}, max {max(abweichungen):.1f}°)",
            "nicht_gefunden": nicht_gefunden, "beispiele": beispiele, "messbar": messbar}


def gate_messbarkeit(messbar, min_n=MESSBAR_MIN_N, max_luecke=MESSBAR_MAX_LUECKE):
    """Gate B2: Messbarkeit bei erhobenem Schwanz darf nicht deutlich unter der bei anliegendem liegen."""
    (mf, nf), (mh, nh) = messbar["flach"], messbar["hoch"]
    text = f"messbar: Schwanz anliegend {mf}/{nf}, erhoben (> {WINKEL_SCHWELLE:.0f}°) {mh}/{nh}"
    if nf < min_n or nh < min_n:
        return {"status": "OFFEN", "messwert": f"{text} — je mind. {min_n} zugeordnete Kühe nötig"}
    luecke = mf / nf - mh / nh
    return {"status": "BESTANDEN" if luecke <= max_luecke else "NICHT BESTANDEN",
            "messwert": f"{text}, Lücke {luecke * 100:.0f} Prozentpunkte"}


def pruefe_val(modell_pfad, daten_yaml, bildgroesse=640, winkel=None, vorhersagen=None):
    gt = lade_gt(daten_yaml, "val")
    if vorhersagen is None:
        modell = lade_modell(modell_pfad, bildgroesse)
        t0 = time.time()
        vorhersagen = sage_vorher(modell, gt)
        dauer = time.time() - t0
    else:
        dauer = None
    a, a2 = gate_austreibung(gt, vorhersagen)
    b = gate_schwanzwinkel(gt, vorhersagen, lade_winkelfunktion(winkel) if isinstance(winkel, str) else (winkel or schwanzwinkel))
    gates = {
        "A": dict(name="Austreibung-Recall (> 0.80, bildweise)", kriterium="= 1.0", **a),
        "A2": dict(name="Austreibungs-Fehlalarme im Val-Set", kriterium="0", **a2),
        "B": dict(name="Schwanzwinkel Modell vs. Hand", kriterium=f"< {WINKEL_MAX_ABWEICHUNG:.0f}° (n ≥ {WINKEL_MIN_N}, "
                  f"nur Punkte mit Sichtbarkeit ≥ {SICHTBAR_MIN} wie im Agenten)", **b),
        "B2": dict(name="Schwanzwinkel messbar bei erhobenem Schwanz",
                   kriterium=f"höchstens {MESSBAR_MAX_LUECKE * 100:.0f} Prozentpunkte unter anliegendem Schwanz "
                             f"(je n ≥ {MESSBAR_MIN_N})", **gate_messbarkeit(b["messbar"])),
        "C": dict(name="Fehlalarm-Budget 24 h", kriterium="0 Austreibung, ≤ 1 Kalbeverdacht", status="OFFEN",
                  messwert="Modus `tag` auf dem Hof-Rechner + Agenten-Replay"),
        "D": dict(name="Laufzeit Zielhardware", kriterium=f"≥ {FPS_MIN:.0f} FPS", status="OFFEN",
                  messwert="Modus `tag`/`laufzeit` auf dem Hof-Rechner (ONNX Runtime)"),
    }
    verbindlich = str(modell_pfad).lower().endswith(".onnx")
    return {"modus": "val", "modell": os.path.basename(str(modell_pfad)), "modell_sha256": sha256(modell_pfad),
            "verbindlich": verbindlich,
            "dekodierung": ("ONNX Runtime, quadratische Letterbox, Austreibungsklassen mit Mehrfach-Label (dekodiere_pose)"
                            if verbindlich else "Ultralytics predict (argmax je Anker)"),
            "daten": daten_yaml, "bilder": len(gt), "vorhersage_dauer_s": round(dauer, 1) if dauer else None,
            "gates": gates, "gesamt": gesamturteil(gates), "erstellt": time.strftime("%Y-%m-%d %H:%M:%S")}


def sha256(pfad):
    try:
        h = hashlib.sha256()
        with open(pfad, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return None


def gesamturteil(gates):
    if any(g["status"] == "NICHT BESTANDEN" for g in gates.values()):
        return "NICHT FREIGEGEBEN"
    if any(g["status"] == "OFFEN" for g in gates.values()):
        return "VORLÄUFIG — offene Gates vor dem Scharfschalten schließen"
    return "FREIGEGEBEN"


def tagesdateien(bilder_ordner, muster="*.jpg", tag=None):
    dateien = sorted(f for f in os.listdir(bilder_ordner) if fnmatch.fnmatch(f, muster))
    if tag:
        dateien = [f for f in dateien if stalltag(f) == tag]
    return dateien


def pruefe_tag(modell_pfad, bilder_ordner, muster="*.jpg", jsonl=None, threads=0, max_bilder=0, zeitlimit=0, tag=None,
               modell=None):
    """Läuft über alle Bilder eines Stalltags (unausgedünnt): wertet JEDES Bild aus (auch Defektbilder, getrennt
    ausgewiesen), zählt Austreibungs-Alarme, misst FPS, schreibt JSONL (fortsetzbar)."""
    import cv2
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from bildqualitaet import defekt_anteil
    modell = modell or lade_modell(modell_pfad, threads=threads)
    dateien = tagesdateien(bilder_ordner, muster, tag)
    if max_bilder:
        dateien = dateien[:max_bilder]
    fertig = set()
    if jsonl and os.path.exists(jsonl):
        with open(jsonl) as fh:
            for z in fh:
                try:
                    fertig.add(json.loads(z)["datei"])
                except (ValueError, KeyError):
                    pass
    alarme = {"sauber": [], "defekt": []}
    n_defekt, n_unlesbar, n_inf, inferenz_s, gesamt_s = 0, 0, 0, 0.0, 0.0
    t_start = time.time()
    fh = open(jsonl, "a") if jsonl else None
    try:
        for f in dateien:
            if f in fertig:
                continue
            if zeitlimit and time.time() - t_start > zeitlimit:
                break
            t_bild = time.time()
            img = cv2.imread(os.path.join(bilder_ordner, f))
            if img is None:
                n_unlesbar += 1
                eintrag = {"datei": f, "fehler": "unlesbar", "objekte": None}
            else:
                d = defekt_anteil(img)
                t0 = time.time()
                p = modell(img)
                inferenz_s += time.time() - t0
                n_inf += 1
                defekt = d > SCHWELLE_DEFEKT
                n_defekt += defekt
                if any(o["cls"] in AUSTREIBUNG and o["conf"] > KONF_AUSTREIBUNG for o in p):
                    alarme["defekt" if defekt else "sauber"].append(f)
                eintrag = {"datei": f, "defekt": round(d, 3), "objekte": [
                    {"cls": o["cls"], "conf": round(o["conf"], 4), "xyxy": [round(v, 5) for v in o["xyxy"]],
                     "kpts": [[round(x, 5), round(y, 5), round(c, 3)] for x, y, c in o["kpts"]]} for o in p]}
                gesamt_s += time.time() - t_bild
            if fh:
                fh.write(json.dumps(eintrag) + "\n")
                fh.flush()
    finally:
        if fh:
            fh.close()
    fps_inf = n_inf / inferenz_s if inferenz_s else 0.0
    fps_ges = n_inf / gesamt_s if gesamt_s else 0.0
    bearbeitet = len(fertig) + n_inf + n_unlesbar
    return {"modus": "tag", "modell": os.path.basename(str(modell_pfad)), "muster": muster, "stalltag": tag,
            "bilder_gesamt": len(dateien), "bilder_diese_sitzung": n_inf, "defekt_ausgewertet": n_defekt,
            "unlesbar": n_unlesbar, "vollstaendig": bearbeitet >= len(dateien),
            "austreibungs_alarme_diese_sitzung": {k: v[:100] for k, v in alarme.items()},
            "fps_inferenz": round(fps_inf, 2), "fps_gesamt": round(fps_ges, 2), "rechner": rechner_info(),
            "gate_D": "BESTANDEN" if fps_ges >= FPS_MIN else ("NICHT BESTANDEN" if n_inf else "OFFEN"),
            "hinweis": "Gate C über den ganzen Tag: auswerten_jsonl() bzw. Ausgabe nach dem letzten Aufruf."}


def auswerten_jsonl(jsonl):
    """Fasst eine (ggf. in mehreren Sitzungen geschriebene) Tages-JSONL zusammen: Gate C (Austreibungs-Teil)."""
    n, n_defekt, n_unlesbar, n_kaputt, alarme = 0, 0, 0, 0, {"sauber": [], "defekt": []}
    with open(jsonl) as fh:
        for z in fh:
            if not z.strip():
                continue
            try:
                e = json.loads(z)
            except ValueError:
                n_kaputt += 1          # z. B. abgeschnittene letzte Zeile nach Absturz
                continue
            n += 1
            if e.get("objekte") is None:
                n_unlesbar += 1
                continue
            defekt = float(e.get("defekt") or 0) > SCHWELLE_DEFEKT
            n_defekt += defekt
            if any(o["cls"] in AUSTREIBUNG and o["conf"] > KONF_AUSTREIBUNG for o in e["objekte"]):
                alarme["defekt" if defekt else "sauber"].append(e["datei"])
    gesamt = len(alarme["sauber"]) + len(alarme["defekt"])
    return {"bilder": n, "davon_defekt": n_defekt, "unlesbar": n_unlesbar, "kaputte_zeilen": n_kaputt,
            "austreibungs_fehlalarme": gesamt, "davon_in_defektbildern": len(alarme["defekt"]),
            "beispiele": (alarme["sauber"] + alarme["defekt"])[:50],
            "gate_C_austreibung": "BESTANDEN" if gesamt == 0 else "NICHT BESTANDEN",
            "gate_C_kalbeverdacht": "OFFEN — JSONL in den Agenten-Replay geben (ByteTrack + 30-min-Fenster + Cooldown)"}


# ----------------------------------------------------------------------------- Berichte
def bericht_md(e):
    z = [f"# Abnahme-Gates — {e.get('modell', '')}", "", f"Erstellt: {e.get('erstellt', '')}  ",
         f"Val-Bilder: {e.get('bilder', '')}  ",
         "Verbindlich: " + ("ja (ONNX, wie auf dem Hof)" if e.get("verbindlich") else "nein — nur Information (.pt)") + "  ",
         f"Modell SHA-256: {e.get('modell_sha256') or '—'}  ",
         f"Dekodierung: {e.get('dekodierung', '—')} — der Agent muss identisch dekodieren, sonst gilt das Ergebnis nicht.", "",
         "| Gate | Prüfung | Kriterium | Messwert | Status |", "|---|---|---|---|---|"]
    for k, g in e["gates"].items():
        z.append(f"| {k} | {g['name']} | {g['kriterium']} | {g['messwert']} | **{g['status']}** |")
    z += ["", f"**Gesamt: {e['gesamt']}**", ""]
    b = e["gates"].get("B", {})
    if b.get("beispiele"):
        z += ["Schwanzwinkel-Stichproben (Hand / Modell / Abweichung):", ""]
        z += [f"- {x['bild']}: {x['hand']}° / {x['modell']}° / {x['abweichung']}°" for x in b["beispiele"][:10]]
    if e["gates"].get("A", {}).get("hinweis"):
        z += ["", f"Hinweis Gate A: {e['gates']['A']['hinweis']}"]
    return "\n".join(z) + "\n"


def modellkarte(version, gates_ergebnis, konvertierung, kennzahlen, training):
    """Erzeugt MODELLKARTE_<version>.md (Pflicht je Version, training-pipeline Abschnitt 6)."""
    sp = konvertierung.get("splits", {})
    tr, va = sp.get("train", {}), sp.get("val", {})
    tage = training.get("tage", {})
    schwaechen = []
    if tr.get("inst_amniotic_sac", 0) == 0 and tr.get("inst_calf_legs", 0) == 0:
        schwaechen.append("Keine echte Geburt im Training: amniotic_sac/calf_legs nicht gelernt — Austreibungs-Alarm "
                          "darf mit diesem Modell NICHT scharfgeschaltet werden.")
    if gates_ergebnis["gates"]["B"]["status"] != "BESTANDEN":
        schwaechen.append(f"Schwanzwinkel-Gate: {gates_ergebnis['gates']['B']['messwert']}")
    schwaechen.append("best.pt und Early-Stopping wurden auf demselben Val-Set gewählt, auf dem die Gates laufen "
                      "(leicht optimistisch). Unabhängiger Beleg: Gate C über einen kompletten Stalltag und der Betrieb.")
    z = [f"# Modellkarte {version}", "",
         f"- Trainingsdatum: {training.get('datum', '')}",
         f"- Basis: {training.get('basis', '')}, Bildgröße {training.get('bildgroesse', '')}, Epochen {training.get('epochen', '')}",
         f"- Software: Ultralytics {training.get('ultralytics', '')}, PyTorch {training.get('torch', '')}, GPU {training.get('gpu', '')}",
         f"- Datenzeitraum (Stalltage, 12–12 Uhr Ortszeit): train {tage.get('train', '?')}, val {tage.get('val', '?')}",
         f"- Klassen: {', '.join(KLASSEN)} — Keypoints: spine_end, tail_base, tail_tip",
         f"- Gates gemessen am: {gates_ergebnis.get('modell', '')} "
         f"({'verbindlich, ONNX wie auf dem Hof' if gates_ergebnis.get('verbindlich') else 'nur Information'}), "
         f"SHA-256 {gates_ergebnis.get('modell_sha256') or '—'} (best_{version}.onnx ist eine bitgleiche Kopie)",
         f"- Dekodierung: {gates_ergebnis.get('dekodierung', '—')}", "",
         "## Daten", "", "| | train | val |", "|---|---:|---:|"]
    for k in ("bilder", "bilder_Tag", "bilder_IR", "bilder_leer", "inst_kuh", "kuh_mit_skelett", "kuh_ohne_skelett",
              "inst_amniotic_sac", "inst_calf_legs"):
        z.append(f"| {k} | {tr.get(k, 0)} | {va.get(k, 0)} |")
    z += ["", "## Val-Metriken", ""] + [f"- {k}: {v:.3f}" if isinstance(v, float) else f"- {k}: {v}" for k, v in kennzahlen.items()]
    z += ["", "## Abnahme-Gates", "", bericht_md(gates_ergebnis).split("\n", 2)[2]]
    z += ["## Bekannte Schwächen", ""] + [f"- {s}" for s in schwaechen]
    z += ["- (von Hand ergänzen: auffällige Fehlalarme, Lichtsituationen, Ansichten)", "",
          "## Scharfschalten", "", "Erst wenn alle Gates BESTANDEN sind: `modell.pfad` setzen, Info-Ereignis "
          f"\"Modell {version} aktiv\" ans Dashboard, Eintrag im Tagesbericht.", ""]
    return "\n".join(z)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="modus", required=True)
    v = sub.add_parser("val", help="Gates A, A2, B auf dem Val-Set")
    v.add_argument("--modell", required=True)
    v.add_argument("--daten", required=True)
    v.add_argument("--bildgroesse", type=int, default=640)
    v.add_argument("--winkel", help="modul:funktion der Agenten-Winkelfunktion (optional)")
    v.add_argument("--vorhersagen", help="JSON mit fertigen Vorhersagen statt Modell (für Tests)")
    v.add_argument("--json")
    v.add_argument("--md")
    t = sub.add_parser("tag", help="kompletter Stalltag: Austreibungs-Fehlalarme (C), FPS (D), JSONL für Replay")
    t.add_argument("--modell", required=True)
    t.add_argument("--bilder-ordner", required=True)
    t.add_argument("--stalltag", required=True, help="Val-Stalltag, z. B. 2026-10-18 (12–12 Uhr Ortszeit)")
    t.add_argument("--bericht", help="konvertierung_bericht.json des Datensatzes: prüft, dass der Stalltag ein Val-Tag ist")
    t.add_argument("--muster", default="*.jpg")
    t.add_argument("--jsonl", required=True)
    t.add_argument("--threads", type=int, default=0)
    t.add_argument("--zeitlimit", type=float, default=0, help="Sekunden je Sitzung (fortsetzbar über --jsonl)")
    l_ = sub.add_parser("laufzeit", help="nur FPS messen (Gate D)")
    l_.add_argument("--modell", required=True)
    l_.add_argument("--bilder-ordner", required=True)
    l_.add_argument("--stalltag")
    l_.add_argument("--muster", default="*.jpg")
    l_.add_argument("--anzahl", type=int, default=30)
    l_.add_argument("--threads", type=int, default=0)
    a = ap.parse_args(argv)

    if a.modus == "val":
        vh = None
        if a.vorhersagen:
            with open(a.vorhersagen) as fh:
                vh = json.load(fh)
        e = pruefe_val(a.modell, a.daten, a.bildgroesse, a.winkel, vh)
        md = bericht_md(e)
        print(md)
        if a.json:
            with open(a.json, "w") as fh:
                json.dump(e, fh, ensure_ascii=False, indent=2)
        if a.md:
            with open(a.md, "w") as fh:
                fh.write(md)
        return 1 if e["gesamt"] == "NICHT FREIGEGEBEN" else 0
    if a.modus == "tag":
        if a.bericht:
            with open(a.bericht, encoding="utf-8") as fh:
                val_tage = json.load(fh).get("stalltage", {}).get("val", [])
            if a.stalltag not in val_tage:
                print(f"FEHLER: {a.stalltag} ist kein Val-Stalltag dieses Datensatzes ({val_tage}) — "
                      "Gate C muss auf ungesehenen Tagen laufen.", file=sys.stderr)
                return 2
        else:
            print("WARNUNG: --bericht fehlt — nicht geprüft, ob der Stalltag ein Val-Tag ist.", file=sys.stderr)
        e = pruefe_tag(a.modell, a.bilder_ordner, a.muster, a.jsonl, a.threads, zeitlimit=a.zeitlimit, tag=a.stalltag)
        print(json.dumps(e, ensure_ascii=False, indent=2))
        if e["vollstaendig"]:
            print(json.dumps(auswerten_jsonl(a.jsonl), ensure_ascii=False, indent=2))
        return 0
    e = pruefe_tag(a.modell, a.bilder_ordner, a.muster, None, a.threads, max_bilder=a.anzahl, tag=a.stalltag)
    print(f"FPS Ende-zu-Ende: {e['fps_gesamt']} (nur Inferenz {e['fps_inferenz']}) auf {e['rechner']} — Gate D: {e['gate_D']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
