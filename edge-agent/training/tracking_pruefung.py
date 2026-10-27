#!/usr/bin/env python3
"""ID-Stabilitaet am echten Clip messen und Tracker-Einstellungen vergleichen.

Skill bytetrack-tuning, Ziel: < 1 ID-Wechsel pro Kuh in 10 Minuten, je
Lichtverhaeltnis (Tag UND IR-Nacht). Das Modell rechnet den Clip nur EINMAL
durch (1 Bild je Sekunde wie im Agenten); die Erkennungen landen in einer
JSON-Datei. Danach laeuft jede tracker-*.yaml auf denselben Erkennungen —
auf dem langsamen Stall-Rechner spart das Stunden.

  # Clip aufnehmen (10 min, 1 FPS wie im Betrieb), Quelle = stream.url
  # aus config.yaml (die Adresse, die der Agent liest):
  ffmpeg -i "rtsp://…" -t 600 -r 1 nacht.mp4
  # Messen und vergleichen (--kuehe: so viele Kuehe stehen wirklich im Bild,
  # ohne die Angabe gibt es kein Urteil):
  python3 tracking_pruefung.py nacht.mp4 --modell best.pt --kuehe 2 \\
      --tracker ../tracker-kuh.yaml bytetrack.yaml
  # Weitere Einstellungen ohne neue Inferenz (Erkennungen aus der JSON):
  python3 tracking_pruefung.py nacht.mp4 --kuehe 2 --tracker variante.yaml

Fuer Szenen, in denen dieselben Kuehe den ganzen Clip ueber im Bild
bleiben (Abkalbebox, Liegebereich); --kuehe ist ihre Zahl. Kommen und
gehen Tiere (Futtertisch), zaehlt jede Besucherin als ID-Wechsel.

Ausgabe: Markdown-Tabelle fuer die Modellkarte. Je Einstellung ✗, wo die
Zaehlungen einen Fehler beweisen (ID-Wechsel, Kurz-IDs, Geist), sonst
„keine Beanstandung – Stellen ansehen“. Ein ✓ gibt es bewusst nicht: Ob
jede Kuh eine ID hat, laesst sich aus Zaehlungen nicht beweisen (fuenf
QA-Runden fanden zu jeder Regel ein Gegenbeispiel). Stattdessen nennt die
Tabelle die Orte, an denen sich Erkennungen ohne ID sammeln, mit Zeit und
Box zum Ansehen. Exit 0 = keine Beanstandung, 1 = mindestens ein ✗, 2 =
ohne --kuehe oder Eingabefehler. Braucht ultralytics und opencv
(Analyse-Image, Colab); die Kennzahlen selbst sind reines Python
(Tests: edge-agent/tests/test_tracking_pruefung.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ZIEL_WECHSEL_PRO_KUH_10MIN = 1.0   # gilt auch fuer Kurz-IDs
MIN_LEBENSDAUER_S = 10       # kuerzere IDs zaehlen nicht als Kuh (Flackern)
GEIST_BRUECKE = 2            # Geist darf so viele Bilder aussetzen (Flackern)
STELLE_BILDER = 60           # so viele Bilder ohne ID an einem Ort -> Stelle zum Ansehen
STELLE_DICHTE = 0.5          # … mindestens dieser Anteil der Bilder dort (ausser neben einer ID-Box)
STELLE_IOU = 0.3             # gleicher Ort: IoU zur mittleren Box des Orts
RASTER_PX = 256              # Rasterweite fuer die Ortssuche (nur Laufzeit)
ALLE_ERKANNT_BILDER = 60     # so viele Bilder mit allen angegebenen Kuehen erkannt
BAENDER = ((0.1, 0.25), (0.25, 0.4), (0.4, 0.5), (0.5, 1.01))
# Wie im Agenten (main.py OBJEKT_KLASSEN): Fruchtblase und Kaelberfuesse
# laufen durch denselben Tracker wie die Kuehe und lassen verlorene Spuren
# altern; gemessen werden nur die Tierklassen.
OBJEKT_KLASSEN = ("amniotic_sac", "calf_legs")


# --------------------------------------------------------------------------
# Reine Logik (ohne ultralytics/cv2 testbar)
# --------------------------------------------------------------------------

def sekundenwahl(fps: float):
    """Entscheider je Bildindex (aufsteigend abgefragt): 1 Bild je Sekunde.

    Braucht die Bildzahl nicht — manche Container melden sie als 0.
    """
    schritt = fps if fps and fps > 1.0 else 1.0
    naechstes = 0.0

    def nimm(i: int) -> bool:
        nonlocal naechstes
        if i >= naechstes - 1e-9:
            naechstes += schritt
            return True
        return False

    return nimm


def sekundenbilder(fps: float, anzahl: int) -> list[int]:
    """Indizes der Videobilder, die 1 Bild je Sekunde ergeben (wie der Agent)."""
    nimm = sekundenwahl(fps)
    return [i for i in range(max(anzahl, 0)) if nimm(i)]


def ist_tier(zeile: list, tier_ids: set[int]) -> bool:
    """Erkennung [cx, cy, w, h, conf, cls]; ohne cls (alte Ablage) = Tier."""
    return len(zeile) < 6 or int(zeile[5]) in tier_ids


def _strecken(flags: list[bool], bruecke: int) -> list[tuple[int, int]]:
    """(Start, Ende) der Bildfolgen mit Flag; Pausen bis `bruecke` Bilder ueberbrueckt."""
    out: list[tuple[int, int]] = []
    for i, f in enumerate(flags):
        if not f:
            continue
        if out and i - out[-1][1] - 1 <= bruecke:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def _iou(a: tuple, b: tuple) -> float:
    """IoU zweier Boxen (cx, cy, w, h)."""
    ax0, ay0, ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx0, by0, bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    schnitt = max(0.0, min(ax1, bx1) - max(ax0, bx0)) * max(0.0, min(ay1, by1) - max(ay0, by0))
    vereint = a[2] * a[3] + b[2] * b[3] - schnitt
    return schnitt / vereint if vereint > 0 else 0.0


def _box(d: tuple, j: int) -> tuple:
    """Box der Erkennung; ohne Box (nur Tests) steht der Listenplatz fuer den Ort."""
    return tuple(d[2]) if len(d) > 2 and d[2] is not None else (100.0 + 300.0 * j, 100.0, 200.0, 120.0)


def _zellen(box: tuple) -> set[tuple[int, int]]:
    """Rasterzellen, die eine Box (cx, cy, w, h) beruehrt."""
    x0, x1 = int((box[0] - box[2] / 2) // RASTER_PX), int((box[0] + box[2] / 2) // RASTER_PX)
    y0, y1 = int((box[1] - box[3] / 2) // RASTER_PX), int((box[1] + box[3] / 2) // RASTER_PX)
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}


def stellen_ohne_id(bilder: list[list[tuple]]) -> list[dict]:
    """Orte, an denen sich Erkennungen ohne ID sammeln (Kuh oder Fehlerkennung?).

    Alle Tier-Erkennungen werden gierig nach Ort gebuendelt (IoU zur
    mittleren Box >= STELLE_IOU). Eine Stelle zum Ansehen ist ein Ort mit
    mindestens STELLE_BILDER Bildern ohne ID, zusammenhaengend oder nicht,
    wenn eines gilt:
    - in mindestens STELLE_BILDER Bildern lag die Erkennung ohne ID NEBEN
      einer Box mit ID am selben Ort – ein zweites Objekt dort (etwa eine
      blinde Kuh unter einem Geist mit ID), oder
    - sie macht mindestens STELLE_DICHTE der Bilder mit einer Erkennung an
      diesem Ort aus. Eine Kuh mit stabiler ID, der der Tracker ab und zu
      kein Bild zuordnet, bleibt darunter.
    Ein Raster beschraenkt den Vergleich auf Orte in der Naehe.
    """
    orte: list[dict] = []
    raster: dict[tuple[int, int], set[int]] = {}
    for i, bild in enumerate(bilder):
        beruehrt: dict[int, list[bool]] = {}  # Ort -> [mit ID, ohne ID]
        for j, d in enumerate(bild):
            box = _box(d, j)
            ziel, beste = None, STELLE_IOU
            for k in sorted({k for z in _zellen(box) for k in raster.get(z, ())}):
                wert = _iou(orte[k]["mittel"], box)
                if wert >= beste:
                    ziel, beste = k, wert
            if ziel is None:
                ziel = len(orte)
                orte.append({"summe": [0.0] * 4, "n": 0, "mittel": box, "zellen": set(),
                             "bilder": set(), "ohne": set(), "neben": set(),
                             "ohne_summe": [0.0] * 4, "confs": []})
            o = orte[ziel]
            o["summe"] = [a + b for a, b in zip(o["summe"], box)]
            o["n"] += 1
            o["mittel"] = tuple(v / o["n"] for v in o["summe"])
            neu = _zellen(o["mittel"])
            if neu != o["zellen"]:
                for z in o["zellen"] - neu:
                    raster[z].discard(ziel)
                for z in neu - o["zellen"]:
                    raster.setdefault(z, set()).add(ziel)
                o["zellen"] = neu
            mit_ohne = beruehrt.setdefault(ziel, [False, False])
            if d[1] is None:
                mit_ohne[1] = True
                o["ohne_summe"] = [a + b for a, b in zip(o["ohne_summe"], box)]
                o["confs"].append(d[0])
            else:
                mit_ohne[0] = True
        for k, (mit, ohne) in beruehrt.items():
            orte[k]["bilder"].add(i)
            if ohne:
                orte[k]["ohne"].add(i)
                if mit:
                    orte[k]["neben"].add(i)
    stellen = []
    for o in orte:
        n_ohne = len(o["ohne"])
        if n_ohne < STELLE_BILDER:
            continue
        if len(o["neben"]) < STELLE_BILDER and n_ohne < STELLE_DICHTE * len(o["bilder"]):
            continue
        stellen.append({
            "bilder": n_ohne, "neben_id": len(o["neben"]),
            "start_s": min(o["ohne"]), "ende_s": max(o["ohne"]),
            "conf_min": min(o["confs"]), "conf_max": max(o["confs"]),
            "box": tuple(v / len(o["confs"]) for v in o["ohne_summe"]),
        })
    return sorted(stellen, key=lambda st: (-st["bilder"], st["start_s"]))


def kennzahlen(bilder: list[list[tuple]], kuehe_echt: int | None = None) -> dict:
    """Kennzahlen aus (Konfidenz, Track-ID oder None[, Box cx/cy/w/h]) je
    Tier-Erkennung und Bild.

    `kuehe_echt` = so viele Kuehe stehen den ganzen Clip ueber im Bild; ohne
    die Angabe gibt es kein Urteil (`urteil` „–“), die Kuhzahl ist dann die
    hoechste Zahl gleichzeitiger langer IDs (ein Geist zaehlt mit).

    ✗ nur, wo die Zaehlungen einen Fehler beweisen:
    - ID-Wechsel: IDs mit >= MIN_LEBENSDAUER_S Bildern minus Kuehe, je Kuh
      und 10 min, ab ZIEL_WECHSEL_PRO_KUH_10MIN.
    - Kurz-IDs: IDs darunter (ab conf 0.25), je Kuh und 10 min, ebenso.
      Schnelles Wechseln und kurze Geister landen hier.
    - Geist: mindestens MIN_LEBENSDAUER_S Bilder lang mehr lange IDs als
      Kuehe, Aussetzer bis GEIST_BRUECKE Bilder ueberbrueckt (ein kurzer
      Doppelrahmen beim Aufstehen zaehlt nicht).
    Sonst „ansehen“: Ob jede Kuh eine ID hat, zeigt nur das Bild. Dafuer
    die Stellen ohne ID (stellen_ohne_id) und ein Hinweis, wenn in weniger
    als ALLE_ERKANNT_BILDER Bildern alle angegebenen Kuehe zugleich erkannt
    sind.
    """
    if kuehe_echt is not None and kuehe_echt < 0:
        raise ValueError("kuehe_echt muss >= 0 sein")
    leben: dict[int, int] = {}
    je_bild: list[tuple[set[int], int]] = []  # (IDs, Zahl der Tier-Erkennungen)
    pro_band = {b: [0, 0] for b in BAENDER}  # [Erkennungen, davon ohne ID]
    for bild in bilder:
        ids_im_bild = set()
        for d in bild:
            conf, tid = d[0], d[1]
            for unten, oben in BAENDER:
                if unten <= conf < oben:
                    pro_band[(unten, oben)][0] += 1
                    if tid is None:
                        pro_band[(unten, oben)][1] += 1
            if tid is not None:
                ids_im_bild.add(tid)
        for tid in ids_im_bild:
            leben[tid] = leben.get(tid, 0) + 1
        je_bild.append((ids_im_bild, len(bild)))
    lange = {t for t, n in leben.items() if n >= MIN_LEBENSDAUER_S}
    lang_je_bild = [len(ids & lange) for ids, _ in je_bild]
    # Kurzes Flackern zaehlt nicht als weitere Kuh
    geschaetzt = max(max(lang_je_bild, default=0), 1) if leben else 0
    kuehe = geschaetzt if kuehe_echt is None else kuehe_echt
    wechsel = max(0, len(lange) - kuehe)
    zehner = len(bilder) / 600  # Einheiten zu 10 min
    je_kuh_10 = (wechsel / kuehe / zehner) if kuehe and zehner else 0.0
    kurz = {d[1] for bild in bilder for d in bild
            if d[1] is not None and d[0] >= 0.25 and leben[d[1]] < MIN_LEBENSDAUER_S}
    kurz_10 = (len(kurz) / max(kuehe, 1) / zehner) if zehner else 0.0
    geist_s = (max((b - a + 1 for a, b in _strecken([n > kuehe for n in lang_je_bild],
                                                    GEIST_BRUECKE)), default=0)
               if kuehe_echt is not None else 0)
    alle_erkannt = sum(1 for _, n in je_bild if n >= kuehe) if kuehe else 0

    e = {
        "dauer_min": round(len(bilder) / 60, 1),
        "ids": len(leben),
        "ids_lang": len(lange),
        "kuehe": kuehe,
        "kuehe_geschaetzt": geschaetzt,
        "kuehe_echt": kuehe_echt,
        "beurteilt": kuehe_echt is not None,
        "wechsel": wechsel,
        "wechsel_je_kuh_10min": round(je_kuh_10, 2),
        "kurz_ids": len(kurz),
        "kurz_je_kuh_10min": round(kurz_10, 2),
        "geist_s": geist_s,
        "alle_erkannt_bilder": alle_erkannt,
        "stellen": stellen_ohne_id(bilder),
        "ohne_id": {f"{u:.2f}–{min(o, 1.0):.2f}": (n, o_) for (u, o), (n, o_) in pro_band.items()},
    }
    # Bei 0 Kuehen ist das Ziel: keine lange ID (sonst ein Geist). Schnelles
    # Wechseln ohne jede lange ID faengt die Kurz-ID-Grenze.
    e["wechsel_ok"] = (not lange) if kuehe == 0 else je_kuh_10 < ZIEL_WECHSEL_PRO_KUH_10MIN
    e["kurz_ok"] = kurz_10 < ZIEL_WECHSEL_PRO_KUH_10MIN
    e["geister"] = geist_s >= MIN_LEBENSDAUER_S
    e["nie_alle_erkannt"] = bool(kuehe_echt) and alle_erkannt < ALLE_ERKANNT_BILDER
    if not e["beurteilt"]:
        e["urteil"] = "–"
    elif not (e["wechsel_ok"] and e["kurz_ok"]) or e["geister"]:
        e["urteil"] = "✗"
    else:
        e["urteil"] = "ansehen"
    return e


def _zeit(sekunden: int) -> str:
    h, rest = divmod(int(sekunden), 3600)
    return f"{h}:{rest // 60:02d}:{rest % 60:02d}" if h else f"{rest // 60:02d}:{rest % 60:02d}"


GESAMT_TEXT = {"✗": "✗", "ansehen": "keine Beanstandung – Stellen ansehen",
               "–": "– (--kuehe fehlt)"}


def tabelle(ergebnisse: dict[str, dict], fps_geraet: float | None) -> str:
    """Markdown fuer die Modellkarte."""
    z = []
    if fps_geraet is not None:
        z.append(f"Inferenz auf diesem Rechner: {fps_geraet:.2f} Bilder/s "
                 f"({'reicht' if fps_geraet >= 1 else 'UNTER 1 FPS – track_buffer zaehlt dann mehr als Sekunden'}).")
        z.append("")
    namen = list(ergebnisse)
    z.append("| Kennzahl | " + " | ".join(namen) + " |")
    z.append("|---|" + "---|" * len(namen))

    def zeile(titel, f):
        z.append(f"| {titel} | " + " | ".join(f(ergebnisse[n]) for n in namen) + " |")

    def kreuz(ok: bool) -> str:
        return "" if ok else " ✗"

    zeile("Dauer", lambda e: f"{e['dauer_min']} min")
    zeile("Kühe im Bild", lambda e: f"geschätzt {e['kuehe_geschaetzt']}"
          + (f", angegeben {e['kuehe_echt']}, alle zugleich erkannt in "
             f"{e['alle_erkannt_bilder']} Bildern" if e["beurteilt"] else ""))
    zeile(f"IDs (≥ {MIN_LEBENSDAUER_S} s)", lambda e: f"{e['ids_lang']} (alle: {e['ids']})")
    zeile("ID-Wechsel je Kuh / 10 min",
          lambda e: (f"{e['wechsel_je_kuh_10min']}" if e["kuehe"]
                     else f"{e['ids_lang']} lange ID(s) bei 0 Kühen") + kreuz(e["wechsel_ok"]))
    zeile(f"Kurz-IDs (< {MIN_LEBENSDAUER_S} s) je Kuh / 10 min",
          lambda e: f"{e['kurz_je_kuh_10min']}" + kreuz(e["kurz_ok"]))
    zeile("Geist (mehr lange IDs als Kühe, längste Strecke)",
          lambda e: (f"{e['geist_s']} s" + kreuz(not e["geister"])) if e["beurteilt"] else "–")
    zeile(f"Stellen ohne ID (≥ {STELLE_BILDER} Bilder)", lambda e: str(len(e["stellen"])))
    for band in next(iter(ergebnisse.values()))["ohne_id"]:
        zeile(f"Erkennungen conf {band} ohne ID",
              lambda e, b=band: (f"{e['ohne_id'][b][1]} von {e['ohne_id'][b][0]}"
                                 if e["ohne_id"][b][0] else "–"))
    zeile("**Gesamt**", lambda e: GESAMT_TEXT[e["urteil"]])
    for n in namen:
        e = ergebnisse[n]
        hinweise = []
        if not e["kurz_ok"]:
            hinweise.append(f"**Achtung {n}:** {e['kurz_ids']} IDs hielten keine "
                            f"{MIN_LEBENSDAUER_S} s – schneller ID-Wechsel oder kurze Geister, "
                            "das 30-Minuten-Fenster beginnt bei jedem Wechsel neu.")
        if e["geister"]:
            hinweise.append(f"**Achtung {n}:** {e['geist_s']} s mehr lange IDs als "
                            f"{e['kuehe']} Kühe – Dauer-Fehlerkennung mit eigener ID (Geist) "
                            "oder --kuehe zu klein.")
        if e["nie_alle_erkannt"]:
            hinweise.append(f"**Prüfen {n}:** angegeben {e['kuehe_echt']} Kühe, alle zugleich "
                            f"erkannt nur in {e['alle_erkannt_bilder']} Bildern – eine Kuh wird "
                            "kaum erkannt (Modell) oder --kuehe stimmt nicht.")
        for st in e["stellen"][:5]:
            neben = f" (davon {st['neben_id']} neben einer Box mit ID)" if st["neben_id"] else ""
            hinweise.append(f"**Prüfen {n}:** {st['bilder']} Bilder ohne ID zwischen "
                            f"{_zeit(st['start_s'])} und {_zeit(st['ende_s'])}{neben}, conf "
                            f"{st['conf_min']:.2f}–{st['conf_max']:.2f}, Box um "
                            f"({st['box'][0]:.0f}, {st['box'][1]:.0f}), "
                            f"{st['box'][2]:.0f}×{st['box'][3]:.0f} px. Kuh: blinde Kuh, gilt als "
                            "✗. Fehlerkennung: als Hard Negative labeln (Skill fehlalarm-triage).")
        if len(e["stellen"]) > 5:
            hinweise.append(f"**Prüfen {n}:** … und {len(e['stellen']) - 5} weitere Stellen.")
        for h in hinweise:
            z.append("")
            z.append(h)
    z.append("")
    z.append(f"✗ heißt bewiesen: ≥ {ZIEL_WECHSEL_PRO_KUH_10MIN:g} ID-Wechsel oder Kurz-ID je Kuh "
             f"in 10 min, oder ein Geist ab {MIN_LEBENSDAUER_S} Bildern. Ein ✓ gibt es bewusst "
             "nicht: Ob jede Kuh eine ID hat, zeigt nur das Bild – die genannten Stellen und eine "
             "Stichprobe im Clip ansehen. Zusagen und Grenzen im Skill bytetrack-tuning.")
    if not all(e["beurteilt"] for e in ergebnisse.values()):
        z.append("Ohne --kuehe kein Urteil: Die Kuhzahl ist dann geschätzt, und ein Geist "
                 "mit eigener ID zählt als Kuh.")
    return "\n".join(z)


def exit_code(ergebnisse: dict[str, dict]) -> int:
    """0 keine Beanstandung, 1 mindestens ein ✗, 2 ohne Urteil."""
    urteile = {e["urteil"] for e in ergebnisse.values()}
    if "–" in urteile:
        return 2
    return 1 if "✗" in urteile else 0


# --------------------------------------------------------------------------
# Inferenz und Tracker (brauchen ultralytics/cv2)
# --------------------------------------------------------------------------

def erkennungen_aus_clip(clip: Path, modell_pfad: str,
                         tier_klassen: list[str]) -> tuple[list, list[int], float]:
    """Je Sekundenbild die Erkennungen [[cx, cy, w, h, conf, cls], …],
    die Klassen-IDs der Tiere und die Bilder/s des Rechners."""
    import cv2
    from ultralytics import YOLO

    modell = YOLO(modell_pfad)
    namen = {v: k for k, v in modell.names.items()}
    fehlen = [k for k in tier_klassen if k not in namen]
    if fehlen:
        abbruch(f"Klasse(n) {fehlen} nicht im Modell: {sorted(namen)}")
    tier_ids = sorted(namen[k] for k in tier_klassen)
    # Wie InferenceEngine.klassen_filter: Tiere + Fruchtblase/Kaelberfuesse
    filter_ids = sorted(set(tier_ids) | {namen[k] for k in OBJEKT_KLASSEN if k in namen})
    cap = cv2.VideoCapture(str(clip))
    nimm = sekundenwahl(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    bilder, rechenzeit, i = [], 0.0, -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        i += 1
        if not nimm(i):
            continue
        t0 = time.perf_counter()
        # conf 0.1 wie model.track() im Agenten
        erg = modell.predict(frame, conf=0.1, classes=filter_ids, verbose=False)[0]
        rechenzeit += time.perf_counter() - t0
        b = erg.boxes
        bilder.append([[*map(float, b.xywh[j].tolist()), float(b.conf[j]), int(b.cls[j])]
                       for j in range(len(b))])
    cap.release()
    return bilder, tier_ids, (len(bilder) / rechenzeit if rechenzeit else 0.0)


def verfolge(bilder: list, tracker_pfad: str,
             tier_ids: set[int]) -> list[list[tuple[float, int | None]]]:
    """Alle Erkennungen durch den echten BYTETracker (wie im Agenten,
    ohne Trennung nach Klassen); je Tier-Erkennung (conf, ID|None, Box)."""
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tracker_simulation import lade_tracker

    class Boxen:
        def __init__(self, zeilen):
            a = np.array([[*z[:5], z[5] if len(z) > 5 else 0] for z in zeilen],
                         dtype=np.float32).reshape(-1, 6)
            self.xywh, self.conf, self.cls = a[:, :4], a[:, 4], a[:, 5]

        def __len__(self):
            return len(self.conf)

    tracker = lade_tracker(tracker_pfad)
    out = []
    for zeilen in bilder:
        ids: dict[int, int] = {}
        if zeilen:  # wie ultralytics track.py: ohne Erkennung kein update()
            for t in tracker.update(Boxen(zeilen)):
                ids[int(t[-1])] = int(t[4])
        out.append([(z[4], ids.get(j), tuple(z[:4]))
                    for j, z in enumerate(zeilen) if ist_tier(z, tier_ids)])
    return out


def abbruch(meldung: str) -> None:
    """Eingabefehler: Exit 2 (1 = ✗)."""
    print(meldung, file=sys.stderr)
    sys.exit(2)


def kuhzahl(text: str) -> int:
    n = int(text)
    if n < 0:
        raise argparse.ArgumentTypeError("muss >= 0 sein")
    return n


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("clip", type=Path)
    a.add_argument("--modell", help="best.pt/.onnx; ohne: Erkennungen aus <clip>.erkennungen.json")
    a.add_argument("--tier-klassen", nargs="+",
                   help="wie modell.tier_klassen in config.yaml (Default: kuh)")
    a.add_argument("--kuehe", type=kuhzahl,
                   help="so viele Kuehe bleiben den ganzen Clip im Bild (ohne: kein Urteil)")
    a.add_argument("--tracker", nargs="+", default=["../tracker-kuh.yaml", "bytetrack.yaml"])
    arg = a.parse_args()

    ablage = arg.clip.with_suffix(".erkennungen.json")
    fps_geraet = None
    if arg.modell:
        tier_klassen = arg.tier_klassen or ["kuh"]
        bilder, tier_ids, fps_geraet = erkennungen_aus_clip(arg.clip, arg.modell, tier_klassen)
        ablage.write_text(json.dumps({"modell": arg.modell, "tier_klassen": tier_klassen,
                                      "tier_ids": tier_ids, "fps_geraet": fps_geraet,
                                      "bilder": bilder}))
        print(f"Erkennungen gespeichert: {ablage}", file=sys.stderr)
    elif ablage.exists():
        daten = json.loads(ablage.read_text())
        bilder, fps_geraet = daten["bilder"], daten.get("fps_geraet")
        tier_ids = daten.get("tier_ids", [])
        gespeichert = daten.get("tier_klassen") or [daten.get("klasse", "kuh")]
        if arg.tier_klassen and sorted(arg.tier_klassen) != sorted(gespeichert):
            abbruch(f"{ablage} enthaelt Tierklassen {gespeichert}, verlangt "
                    f"{arg.tier_klassen} – mit --modell neu erzeugen.")
        print(f"Erkennungen aus {ablage} (Modell {daten.get('modell', '?')}, "
              f"Tierklassen {gespeichert})", file=sys.stderr)
    else:
        abbruch(f"{ablage} fehlt – einmal mit --modell aufrufen.")

    ergebnisse = {Path(t).name: kennzahlen(verfolge(bilder, t, set(tier_ids)), arg.kuehe)
                  for t in arg.tracker}
    print(f"## Tracking-Prüfung {arg.clip.name}\n")
    print(tabelle(ergebnisse, fps_geraet))
    return exit_code(ergebnisse)


if __name__ == "__main__":
    sys.exit(main())
