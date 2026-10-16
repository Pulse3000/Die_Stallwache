#!/usr/bin/env python3
"""Abnahme-Gates vor dem Scharfschalten eines Modells (best_vN.pt).

  python3 abnahme.py best_v1.pt datensatz [--bericht abnahme_v1.md]
  python3 abnahme.py best_v1.pt datensatz --nur-fps     # auf der Zielhardware

Automatisch geprueft auf datensatz/images/val + labels/val:
  Gate 1  Austreibung: Recall = 1.0 fuer amniotic_sac/calf_legs bei
          Konfidenz >= 0.80 (IoU >= 0.5). Ohne Geburt im Val-Set nicht
          pruefbar -> Austreibungs-Logik nicht scharfschalten.
  Gate 2  Keypoint-Guete: Schwanzwinkel Modell vs. Hand-Label (alle drei
          Keypoints sichtbar gelabelt), mittlere Abweichung < 10° bei
          mindestens 30 Stichproben.
  Gate 2b Sichtbarkeit: Bei gelabelt erhobenem Schwanz (> 45°) liefert das
          Modell in >= 90 % der Faelle alle drei Keypoints sichtbar
          (n >= 10). Sonst wuerde der Agent diese Frames verwerfen und
          Kalbeverdacht still unterdruecken - Gate 2 allein merkt das nicht.
Nur von Hand pruefbar (im Bericht als offene Punkte):
  Gate 3  Fehlalarm-Budget: 24 h ereignisloses Material durch den ganzen
          Agenten -> 0 Austreibungs-, <= 1 Kalbeverdacht-Fehlalarm.
  Gate 4  Laufzeit >= 1 FPS auf der Zielhardware (--nur-fps dort ausfuehren).

Winkel und Sichtbarkeitspruefung kommen aus dem Agenten selbst
(main.schwanzwinkel_grad, InferenceEngine._schwanzwinkel) - nie eine Kopie,
sonst misst die Abnahme etwas anderes, als im Stall laeuft.

Exit-Code: 0 Gate 1, 2 und 2b bestanden, 1 ein Gate verfehlt,
2 keines verfehlt, aber Gate 1 oder 2b nicht pruefbar (zu wenig Val-Material).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
BILDENDUNGEN = {".jpg", ".jpeg", ".png"}
# Klassen und Keypoint-Reihenfolge aus stall.yaml
KUH = 0
AUSTREIBUNG = {1: "amniotic_sac", 2: "calf_legs"}
KEYPOINTS = {"spine_end": 0, "tail_base": 1, "tail_tip": 2}
# Referenzwerte (Skill training-pipeline, Abschnitt 5)
OVERRIDE_KONFIDENZ = 0.80
IOU_MIN = 0.5
STICHPROBEN_MIN = 30
MAX_ABWEICHUNG_GRAD = 10.0
ERHOBEN_AB_GRAD = 45.0          # Referenzwert logik.winkel_schwelle_grad
SICHTBARKEIT_MIN = 0.90
SICHTBARKEIT_STICHPROBEN_MIN = 10


# --------------------------------------------------------------------------
# Reine Logik
# --------------------------------------------------------------------------

def lese_label(text: str, breite: int, hoehe: int) -> list[dict]:
    """YOLO-Pose-Label (normiert) -> Objekte in Pixeln.

    Zeile: klasse cx cy w h [x y v]... ; v = 2 heisst sichtbar gelabelt.
    """
    objekte = []
    for zeile in text.splitlines():
        werte = zeile.split()
        if len(werte) < 5:
            continue
        k = int(float(werte[0]))
        cx, cy, w, h = (float(v) for v in werte[1:5])
        box = ((cx - w / 2) * breite, (cy - h / 2) * hoehe,
               (cx + w / 2) * breite, (cy + h / 2) * hoehe)
        rest = [float(v) for v in werte[5:]]
        kp = [(rest[i] * breite, rest[i + 1] * hoehe, rest[i + 2])
              for i in range(0, len(rest) - len(rest) % 3, 3)]
        objekte.append({"klasse": k, "box": box, "kp": kp})
    return objekte


def iou(a: tuple, b: tuple) -> float:
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    schnitt = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if not schnitt:
        return 0.0
    fl_a = (a[2] - a[0]) * (a[3] - a[1])
    fl_b = (b[2] - b[0]) * (b[3] - b[1])
    return schnitt / (fl_a + fl_b - schnitt)


def ordne_zu(gt: list[dict], pred: list[dict], klasse: int, iou_min: float = IOU_MIN):
    """Gierige Zuordnung je Klasse: sicherste Vorhersage zuerst. -> [(gi, pi)]"""
    g_idx = [i for i, o in enumerate(gt) if o["klasse"] == klasse]
    p_idx = sorted((i for i, o in enumerate(pred) if o["klasse"] == klasse),
                   key=lambda i: -pred[i]["konf"])
    frei = set(g_idx)
    paare = []
    for pi in p_idx:
        beste, bester_wert = None, iou_min
        for gi in frei:
            wert = iou(gt[gi]["box"], pred[pi]["box"])
            if wert >= bester_wert:
                beste, bester_wert = gi, wert
        if beste is not None:
            frei.discard(beste)
            paare.append((beste, pi))
    return paare


def austreibungs_recall(bilder, konf: float = OVERRIDE_KONFIDENZ, iou_min: float = IOU_MIN) -> dict:
    """bilder: [(gt, pred)] -> {klasse: {"gt": n, "treffer": k}}"""
    ergebnis = {k: {"gt": 0, "treffer": 0} for k in AUSTREIBUNG}
    for gt, pred in bilder:
        sicher = [o for o in pred if o["konf"] >= konf]
        for k in AUSTREIBUNG:
            ergebnis[k]["gt"] += sum(1 for o in gt if o["klasse"] == k)
            ergebnis[k]["treffer"] += len(ordne_zu(gt, sicher, k, iou_min))
    return ergebnis


def winkel_paare(bilder, gt_winkel, pred_winkel, iou_min: float = IOU_MIN):
    """[(winkel_label, winkel_modell)] fuer zugeordnete Kuehe.

    Nur Labels mit allen drei Keypoints sichtbar (v = 2); die Vorhersage
    laeuft durch dieselbe Sichtbarkeitspruefung wie im Stall.
    """
    paare = []
    for gt, pred in bilder:
        for gi, pi in ordne_zu(gt, pred, KUH, iou_min):
            kp_gt = gt[gi]["kp"]
            if len(kp_gt) < 3 or any(v != 2 for _, _, v in kp_gt[:3]):
                continue
            soll = gt_winkel(*[(x, y) for x, y, _ in kp_gt[:3]])
            kp_p = pred[pi]["kp"]
            ist = pred_winkel([(x, y) for x, y, _ in kp_p], [c for _, _, c in kp_p])
            if soll is not None and ist is not None:
                paare.append((soll, ist))
    return paare


def _sichtbar_gelabelt(objekt: dict) -> bool:
    kp = objekt["kp"]
    return len(kp) >= 3 and all(v == 2 for _, _, v in kp[:3])


def sichtbarkeit_erhoben(bilder, gt_winkel, pred_winkel, iou_min: float = IOU_MIN) -> tuple[int, int]:
    """(n, gesehen): gelabelt erhobene Schwaenze (> 45°) und wie oft das
    Modell dafuer einen auswertbaren Winkel liefert. Nicht erkannte Kuh
    zaehlt als nicht gesehen."""
    n = gesehen = 0
    for gt, pred in bilder:
        zuordnung = dict(ordne_zu(gt, pred, KUH, iou_min))
        for gi, o in enumerate(gt):
            if o["klasse"] != KUH or not _sichtbar_gelabelt(o):
                continue
            soll = gt_winkel(*[(x, y) for x, y, _ in o["kp"][:3]])
            if soll is None or soll <= ERHOBEN_AB_GRAD:
                continue
            n += 1
            pi = zuordnung.get(gi)
            if pi is not None:
                kp_p = pred[pi]["kp"]
                if pred_winkel([(x, y) for x, y, _ in kp_p], [c for _, _, c in kp_p]) is not None:
                    gesehen += 1
    return n, gesehen


def bewerte(recall: dict, paare: list, sicht: tuple[int, int] = (0, 0),
            stichproben_min: int = STICHPROBEN_MIN,
            max_abweichung: float = MAX_ABWEICHUNG_GRAD) -> dict:
    vorhanden = {k: v for k, v in recall.items() if v["gt"]}
    if not vorhanden:
        gate1 = "nicht prüfbar"
    elif all(v["treffer"] == v["gt"] for v in vorhanden.values()):
        gate1 = "bestanden"
    else:
        gate1 = "verfehlt"
    abweichung = (sum(abs(a - b) for a, b in paare) / len(paare)) if paare else None
    if len(paare) < stichproben_min:
        gate2 = "verfehlt"
    else:
        gate2 = "bestanden" if abweichung < max_abweichung else "verfehlt"
    n_sicht, gesehen = sicht
    if n_sicht < SICHTBARKEIT_STICHPROBEN_MIN:
        gate2b = "nicht prüfbar"
    else:
        gate2b = "bestanden" if gesehen / n_sicht >= SICHTBARKEIT_MIN else "verfehlt"
    stati = (gate1, gate2, gate2b)
    if "verfehlt" in stati:
        code = 1
    elif "nicht prüfbar" in stati:
        code = 2
    else:
        code = 0
    return {"gate1": gate1, "recall": recall, "gate2": gate2,
            "stichproben": len(paare), "abweichung": abweichung,
            "gate2b": gate2b, "sicht": sicht, "code": code}


def bericht(e: dict, modell: str, datensatz: str) -> str:
    z = [f"## Abnahme {Path(modell).name}", "",
         f"Val-Set: `{datensatz}/images/val`", "",
         "| Gate | Kriterium | Ergebnis | Status |", "| --- | --- | --- | --- |"]
    teile = []
    for k, name in AUSTREIBUNG.items():
        v = e["recall"][k]
        teile.append(f"{name} {v['treffer']}/{v['gt']}" if v["gt"] else f"{name} keine Val-Beispiele")
    z.append(f"| 1 Austreibung | Recall = 1.0 bei Konfidenz ≥ {OVERRIDE_KONFIDENZ:.2f} | "
             f"{', '.join(teile)} | {e['gate1']} |")
    abw = f"{e['abweichung']:.1f}°" if e["abweichung"] is not None else "–"
    z.append(f"| 2 Keypoints | mittl. Winkelabweichung < {MAX_ABWEICHUNG_GRAD:.0f}° "
             f"(n ≥ {STICHPROBEN_MIN}) | {abw} bei n = {e['stichproben']} | {e['gate2']} |")
    n_sicht, gesehen = e["sicht"]
    z.append(f"| 2b Sichtbarkeit | erhobener Schwanz (> {ERHOBEN_AB_GRAD:.0f}°): alle 3 Keypoints "
             f"sichtbar in ≥ {SICHTBARKEIT_MIN:.0%} (n ≥ {SICHTBARKEIT_STICHPROBEN_MIN}) | "
             f"{gesehen}/{n_sicht} | {e['gate2b']} |")
    z.append("| 3 Fehlalarm-Budget | 24 h ereignislos: 0 Austreibung, ≤ 1 Kalbeverdacht | "
             "von Hand | offen |")
    z.append("| 4 Laufzeit | ≥ 1 FPS auf der Zielhardware | `--nur-fps` dort | offen |")
    if e["gate1"] == "nicht prüfbar":
        z += ["", "Keine Geburt im Val-Set: Austreibungs-Logik NICHT scharfschalten, "
              "Silent Mode für diese Klassen verlängern."]
    if e["gate2b"] == "nicht prüfbar":
        z += ["", "Zu wenige gelabelte erhobene Schwänze im Val-Set: Sichtbarkeit beim "
              "Kalbeverdacht unbelegt – mehr solche Bilder labeln."]
    elif e["gate2b"] == "verfehlt":
        z += ["", "Erhobene Schwänze werden zu oft nicht vollständig erkannt: Der Agent "
              "würde Kalbeverdacht still unterdrücken. Nicht scharfschalten."]
    return "\n".join(z) + "\n"


# --------------------------------------------------------------------------
# Modell und Agent laden (nur fuer den echten Lauf)
# --------------------------------------------------------------------------

def lade_agent():
    """main.py des Edge-Agenten (neben training/ oder im selben Ordner)."""
    if "stall_main" in sys.modules:
        return sys.modules["stall_main"]
    for pfad in (HIER.parent / "main.py", HIER / "main.py"):
        if pfad.exists():
            spec = importlib.util.spec_from_file_location("stall_main", pfad)
            m = importlib.util.module_from_spec(spec)
            sys.modules["stall_main"] = m
            spec.loader.exec_module(m)
            return m
    raise SystemExit("main.py des Edge-Agenten nicht gefunden (neben abnahme.py "
                     "oder eine Ebene darueber ablegen).")


def winkel_des_agenten():
    """(gt_winkel, pred_winkel) mit genau der Logik des Agenten."""
    m = lade_agent()
    engine = m.InferenceEngine({"modell": {
        "pfad": "", "keypoints": KEYPOINTS,
        "klassen": {"kuh": KUH, **{n: k for k, n in AUSTREIBUNG.items()}},
    }})
    return m.schwanzwinkel_grad, engine._schwanzwinkel


def _val_bilder(datensatz: Path) -> list[Path]:
    return sorted(p for p in (datensatz / "images" / "val").glob("*")
                  if p.suffix.lower() in BILDENDUNGEN)


def _vorhersage(ergebnis) -> list[dict]:
    pred = []
    boxen = ergebnis.boxes
    if boxen is None:
        return pred
    kps = ergebnis.keypoints
    kxy = kps.xy.cpu().numpy() if kps is not None else None
    kkonf = kps.conf.cpu().numpy() if kps is not None and kps.conf is not None else None
    for i in range(len(boxen)):
        kp = []
        if kxy is not None:
            kp = [(float(x), float(y), float(kkonf[i][j]) if kkonf is not None else 1.0)
                  for j, (x, y) in enumerate(kxy[i])]
        pred.append({"klasse": int(boxen.cls[i]), "konf": float(boxen.conf[i]),
                     "box": tuple(float(v) for v in boxen.xyxy[i]), "kp": kp})
    return pred


def sammle(modell, datensatz: Path) -> list:
    import cv2

    bilder = []
    for bild in _val_bilder(datensatz):
        img = cv2.imread(str(bild))
        if img is None:
            continue
        h, w = img.shape[:2]
        label = datensatz / "labels" / "val" / (bild.stem + ".txt")
        gt = lese_label(label.read_text(encoding="utf-8") if label.exists() else "", w, h)
        bilder.append((gt, _vorhersage(modell.predict(img, conf=0.25, verbose=False)[0])))
    return bilder


def miss_fps(modell, datensatz: Path, anzahl: int = 20) -> float:
    import cv2

    pfade = _val_bilder(datensatz)[: anzahl + 2]
    if len(pfade) < 3:
        raise SystemExit("Zu wenige Val-Bilder für die Zeitmessung.")
    bilder = [cv2.imread(str(p)) for p in pfade]
    for img in bilder[:2]:  # Aufwaermen
        modell.predict(img, verbose=False)
    start = time.perf_counter()
    for img in bilder[2:]:
        modell.predict(img, verbose=False)
    return (len(bilder) - 2) / (time.perf_counter() - start)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Abnahme-Gates vor dem Scharfschalten")
    parser.add_argument("modell", help="z. B. best_v1.pt")
    parser.add_argument("datensatz", help="Ordner mit images/val und labels/val")
    parser.add_argument("--bericht", help="Markdown-Bericht zusaetzlich in diese Datei")
    parser.add_argument("--nur-fps", action="store_true",
                        help="nur Laufzeit messen (auf der Zielhardware ausfuehren)")
    args = parser.parse_args(argv)

    from ultralytics import YOLO

    modell = YOLO(args.modell)
    datensatz = Path(args.datensatz)
    if args.nur_fps:
        fps = miss_fps(modell, datensatz)
        print(f"Gate 4 Laufzeit: {fps:.2f} FPS – {'bestanden' if fps >= 1 else 'verfehlt'} "
              "(zählt nur auf der Zielhardware)")
        return 0 if fps >= 1 else 1

    gt_winkel, pred_winkel = winkel_des_agenten()
    bilder = sammle(modell, datensatz)
    ergebnis = bewerte(
        austreibungs_recall(bilder),
        winkel_paare(bilder, gt_winkel, pred_winkel),
        sichtbarkeit_erhoben(bilder, gt_winkel, pred_winkel),
    )
    text = bericht(ergebnis, args.modell, args.datensatz)
    print(text)
    if args.bericht:
        Path(args.bericht).write_text(text, encoding="utf-8")
    return ergebnis["code"]


if __name__ == "__main__":
    sys.exit(main())
