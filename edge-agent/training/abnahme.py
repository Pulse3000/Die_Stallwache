#!/usr/bin/env python3
"""Abnahme-Gates vor dem Scharfschalten eines Modells (best_vN.pt).

  python3 abnahme.py best_v1.pt datensatz [--bericht abnahme_v1.md]
  python3 abnahme.py best_v1.pt datensatz --nur-fps     # auf der Zielhardware

Automatisch geprueft auf datensatz/images/val + labels/val:
  Gate 1  Austreibung: Recall = 1.0 fuer amniotic_sac UND calf_legs bei
          Konfidenz >= 0.80 (IoU >= 0.5). Fehlen einer Klasse Val-Beispiele,
          ist das Gate nicht pruefbar -> Austreibungs-Logik nicht
          scharfschalten. Gemessen wird wie im Agenten: Erkennungen vor dem
          Tracker (InferenceEngine._merke_objekte).
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

Brunst-Phase (--phase brunst, Modell nur mit Klasse kuh,
docs/brunst-zuerst-entscheidung.md):
  Gate K  Kuh-Recall >= 90 % bei Konfidenz >= 0.5 (n >= 100).
  Gate Ü  Bei Kuh-Paaren in Aufsprung-Lage (Regel des Agenten,
          main.aufsprung_oben) erkennt das Modell BEIDE und die erkannten
          Boxen liegen ebenso, in >= 90 % (n >= 20) - sonst schluckt die NMS
          eine Box. Paare ab IoU 0,5 getrennt ausgewiesen.
  Gate D  Hoechstens 2 % der Kuehe mit Doppelbox (loest sonst Aufsprung aus).
  Von Hand: K nur Nachtbilder, E Ende zu Ende (Aufsprung-Videos mit 1 Bild/s).
  Exit-Code wie oben (0 / 1 verfehlt / 2 nicht pruefbar).
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
    # Recall 1.0 fuer JEDE Austreibungsklasse: Eine Klasse ohne
    # Val-Beispiele ist ungeprueft, nicht bestanden.
    fehlend = [AUSTREIBUNG[k] for k, v in recall.items() if not v["gt"]]
    if any(v["treffer"] < v["gt"] for v in recall.values() if v["gt"]):
        gate1 = "verfehlt"
    elif fehlend:
        gate1 = "nicht prüfbar"
    else:
        gate1 = "bestanden"
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
    return {"gate1": gate1, "gate1_fehlend": fehlend, "recall": recall, "gate2": gate2,
            "stichproben": len(paare), "abweichung": abweichung,
            "gate2b": gate2b, "sicht": sicht, "code": code}


# --------------------------------------------------------------------------
# Brunst-Phase (docs/brunst-zuerst-entscheidung.md): Modell nur mit Klasse
# kuh. Werte nach der Fachpruefung durch ki-wache (29.10.2026); der
# Betreiber bestaetigt sie. Austreibung und Kalbeverdacht sind NICHT Teil
# dieser Abnahme und bleiben nicht scharf (der Agent meldet das selbst).
# --------------------------------------------------------------------------

KUH_KONFIDENZ = 0.5          # = new_track_thresh (tracker-kuh.yaml): darunter keine neue Spur
KUH_RECALL_MIN = 0.90
KUH_STICHPROBEN_MIN = 100    # 27/30 hiesse nur >= 0,76 (einseitige 95-%-Untergrenze)
UEBERLAPP_RECALL_MIN = 0.90
UEBERLAPP_STICHPROBEN_MIN = 20  # bei n = 5 bestuende eine wahre Rate von 60 % in 34 % der Faelle
NMS_KRITISCH_IOU = 0.5       # ab hier droht die NMS (Grenze 0,7) eine Box zu verschlucken
DOPPEL_IOU = 0.3             # zweite Box auf derselben Kuh
DOPPEL_MAX = 0.02            # hoechstens 2 % der Kuehe mit Doppelbox


def kuh_recall(bilder, konf: float = KUH_KONFIDENZ, iou_min: float = IOU_MIN) -> tuple[int, int]:
    """(n, treffer): gelabelte Kuehe und davon vom Modell erkannte."""
    n = treffer = 0
    for gt, pred in bilder:
        sicher = [o for o in pred if o["konf"] >= konf]
        n += sum(1 for o in gt if o["klasse"] == KUH)
        treffer += len(ordne_zu(gt, sicher, KUH, iou_min))
    return n, treffer


def ueberlapp_recall(bilder, konf: float = KUH_KONFIDENZ, iou_min: float = IOU_MIN) -> dict:
    """Gelabelte Kuh-Paare, die wie ein Aufsprung liegen (exakt die Regel des
    Agenten: main.aufsprung_oben), und wie oft das Modell BEIDE erkennt UND
    die erkannten Boxen die Regel ebenfalls erfuellen.

    Genau hier droht die Non-Maximum-Suppression eine der zwei Boxen zu
    verschlucken - dann gibt es kein Paar und nie einen Brunstverdacht,
    obwohl die Kuh-Erkennung insgesamt gut aussieht. Nebeneinander stehende
    Kuehe zaehlen nicht (Befund ki-wache). Getrennt ausgewiesen: Paare ab
    IoU 0,5, wo die NMS am ehesten zuschlaegt.
    -> {"n", "treffer", "n_eng", "treffer_eng"}
    """
    aufsprung_oben = lade_agent().aufsprung_oben
    e = {"n": 0, "treffer": 0, "n_eng": 0, "treffer_eng": 0}
    for gt, pred in bilder:
        sicher = [o for o in pred if o["konf"] >= konf]
        zuordnung = dict(ordne_zu(gt, sicher, KUH, iou_min))
        kuehe = [i for i, o in enumerate(gt) if o["klasse"] == KUH]
        for pos, a in enumerate(kuehe):
            for b in kuehe[pos + 1:]:
                if aufsprung_oben(gt[a]["box"], gt[b]["box"]) is None:
                    continue
                eng = iou(gt[a]["box"], gt[b]["box"]) >= NMS_KRITISCH_IOU
                e["n"] += 1
                e["n_eng"] += eng
                if a in zuordnung and b in zuordnung and aufsprung_oben(
                        sicher[zuordnung[a]]["box"], sicher[zuordnung[b]]["box"]) is not None:
                    e["treffer"] += 1
                    e["treffer_eng"] += eng
    return e


def doppelboxen(bilder, konf: float = KUH_KONFIDENZ, iou_min: float = IOU_MIN) -> tuple[int, int]:
    """(n, doppelt): gelabelte Kuehe und wie viele davon eine zweite sichere
    Box tragen (nicht zugeordnete Vorhersage mit IoU >= 0,3 zu einer schon
    erkannten Kuh). Eine Doppelbox derselben Kuh erfuellt die Aufsprung-Regel
    und waere ein Brunst-Fehlalarm ohne zweite Kuh."""
    n = doppelt = 0
    for gt, pred in bilder:
        sicher = [o for o in pred if o["konf"] >= konf and o["klasse"] == KUH]
        zuordnung = ordne_zu(gt, sicher, KUH, iou_min)
        erkannt = {gi for gi, _ in zuordnung}
        genutzt = {pi for _, pi in zuordnung}
        n += sum(1 for o in gt if o["klasse"] == KUH)
        betroffen = set()
        for pi, o in enumerate(sicher):
            if pi in genutzt:
                continue
            for gi in erkannt:
                if iou(gt[gi]["box"], o["box"]) >= DOPPEL_IOU:
                    betroffen.add(gi)
        doppelt += len(betroffen)
    return n, doppelt


def bewerte_brunst(kuh: tuple[int, int], ueberlapp: dict, doppel: tuple[int, int] = (0, 0)) -> dict:
    n_k, t_k = kuh
    if n_k < KUH_STICHPROBEN_MIN:
        gate_k = "nicht prüfbar"
    else:
        gate_k = "bestanden" if t_k / n_k >= KUH_RECALL_MIN else "verfehlt"
    n_u, t_u = ueberlapp["n"], ueberlapp["treffer"]
    if n_u < UEBERLAPP_STICHPROBEN_MIN:
        gate_u = "nicht prüfbar"
    else:
        gate_u = "bestanden" if t_u / n_u >= UEBERLAPP_RECALL_MIN else "verfehlt"
    n_d, d = doppel
    if n_d < KUH_STICHPROBEN_MIN:
        gate_d = "nicht prüfbar"
    else:
        gate_d = "bestanden" if d / n_d <= DOPPEL_MAX else "verfehlt"
    stati = (gate_k, gate_u, gate_d)
    code = 1 if "verfehlt" in stati else 2 if "nicht prüfbar" in stati else 0
    return {"gate_k": gate_k, "kuh": kuh, "gate_u": gate_u, "ueberlapp": ueberlapp,
            "gate_d": gate_d, "doppel": doppel, "code": code}


def bericht_brunst(e: dict, modell: str, datensatz: str) -> str:
    n_k, t_k = e["kuh"]
    u = e["ueberlapp"]
    n_d, d = e["doppel"]
    z = [f"## Abnahme {Path(modell).name} – Brunst-Phase", "",
         f"Val-Set: `{datensatz}/images/val`", "",
         "| Gate | Kriterium | Ergebnis | Status |", "| --- | --- | --- | --- |",
         f"| K Kuh-Erkennung | Recall ≥ {KUH_RECALL_MIN:.0%} bei Konfidenz ≥ {KUH_KONFIDENZ} "
         f"(n ≥ {KUH_STICHPROBEN_MIN}) | {t_k}/{n_k} | {e['gate_k']} |",
         "| K-Nacht | wie K, nur IR-Nachtbilder (n ≥ 30) | von Hand (Val-Set nach Licht teilen) | offen |",
         f"| Ü Aufsprung-Lage | beide Kühe erkannt und Lage wie beim Aufsprung in ≥ "
         f"{UEBERLAPP_RECALL_MIN:.0%} (n ≥ {UEBERLAPP_STICHPROBEN_MIN} Paare) | {u['treffer']}/{u['n']} "
         f"(davon IoU ≥ {NMS_KRITISCH_IOU}: {u['treffer_eng']}/{u['n_eng']}) | {e['gate_u']} |",
         f"| D Doppelboxen | ≤ {DOPPEL_MAX:.0%} der Kühe mit zweiter Box | {d}/{n_d} | {e['gate_d']} |",
         "| E Ende zu Ende | ≥ 4 von 5 echten Aufsprung-Szenen als Video mit 1 Bild/s "
         "(`ffmpeg -i clip.mp4 -r 1 clip_1fps.mp4`) ergeben einen Alarm mit der richtigen unteren Kuh "
         "| von Hand | offen |",
         "| 3b Fehlalarm-Budget | 24 h: ≤ 1 falscher Brunstverdacht | von Hand | offen |",
         "| 4 Laufzeit | ≥ 1 FPS auf der Zielhardware | `--nur-fps` dort | offen |",
         "", "Austreibung und Kalbeverdacht sind nicht Teil dieser Abnahme: NICHT scharf. "
         "Der Agent meldet das selbst, die App sagt für diese Kamera kein „OK“.",
         "", "Erst wenn K, Ü, D und E bestanden sind: `modell.freigegeben: [brunst]`. "
         "Bis dahin darf das Modell laufen, aber mit `freigegeben: []`."]
    if e["gate_u"] == "nicht prüfbar":
        z += ["", "Zu wenige gelabelte Aufsprung-Lagen im Val-Set: Ob beim Aufsprung beide Kühe "
              "erkannt werden, ist unbelegt – Bilder aus echten Aufsprung-Videos labeln "
              "(eng stehende Kühe genügen nicht)."]
    elif e["gate_u"] == "verfehlt":
        z += ["", "Bei Aufsprung-Lagen fehlt oft eine Box: Aufsprung würde übersehen. "
              "Mehr solche Szenen labeln; nicht freigeben."]
    if e["gate_d"] == "verfehlt":
        z += ["", "Zu viele Doppelboxen: Eine Kuh mit zwei Boxen löst die Aufsprung-Regel aus. "
              "Nicht freigeben."]
    return "\n".join(z) + "\n"


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
        fehlend = e.get("gate1_fehlend") or list(AUSTREIBUNG.values())
        grund = ("Keine Geburt im Val-Set" if len(fehlend) == len(AUSTREIBUNG)
                 else f"Keine Val-Beispiele für {', '.join(fehlend)}")
        z += ["", f"{grund}: Austreibungs-Logik NICHT scharfschalten, "
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
    parser.add_argument("--phase", choices=("voll", "brunst"), default="voll",
                        help="brunst = Modell nur mit Klasse kuh (Gates K und Ü)")
    args = parser.parse_args(argv)

    from ultralytics import YOLO

    modell = YOLO(args.modell)
    datensatz = Path(args.datensatz)
    if args.nur_fps:
        fps = miss_fps(modell, datensatz)
        print(f"Gate 4 Laufzeit: {fps:.2f} FPS – {'bestanden' if fps >= 1 else 'verfehlt'} "
              "(zählt nur auf der Zielhardware)")
        return 0 if fps >= 1 else 1

    if args.phase == "brunst":
        bilder = sammle(modell, datensatz)
        ergebnis = bewerte_brunst(kuh_recall(bilder), ueberlapp_recall(bilder), doppelboxen(bilder))
        text = bericht_brunst(ergebnis, args.modell, args.datensatz)
        print(text)
        if args.bericht:
            Path(args.bericht).write_text(text, encoding="utf-8")
        return ergebnis["code"]

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
