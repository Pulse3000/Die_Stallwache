#!/usr/bin/env python3
"""ID-Stabilitaet am echten Clip messen und Tracker-Einstellungen vergleichen.

Skill bytetrack-tuning, Ziel: < 1 ID-Wechsel pro Kuh in 10 Minuten, je
Lichtverhaeltnis (Tag UND IR-Nacht). Das Modell rechnet den Clip nur EINMAL
durch (1 Bild je Sekunde wie im Agenten); die Erkennungen landen in einer
JSON-Datei. Danach laeuft jede tracker-*.yaml auf denselben Erkennungen —
auf dem langsamen Stall-Rechner spart das Stunden.

  # Clip aufnehmen (10 min, 1 FPS wie im Betrieb):
  ffmpeg -i rtsp://127.0.0.1:8554/stallwache -t 600 -r 1 nacht.mp4
  # Messen und vergleichen:
  python3 tracking_pruefung.py nacht.mp4 --modell best.pt \\
      --tracker ../tracker-kuh.yaml bytetrack.yaml
  # Weitere Einstellungen ohne neue Inferenz (Erkennungen aus der JSON):
  python3 tracking_pruefung.py nacht.mp4 --tracker variante.yaml

Ausgabe: Markdown-Tabelle fuer die Modellkarte. Braucht ultralytics und
opencv (Analyse-Image, Colab); die Kennzahlen selbst sind reines Python
(Tests: edge-agent/tests/test_tracking_pruefung.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ZIEL_WECHSEL_PRO_KUH_10MIN = 1.0
MIN_LEBENSDAUER_S = 10       # kuerzere IDs zaehlen nicht als Kuh (Flackern)
BAENDER = ((0.1, 0.25), (0.25, 0.4), (0.4, 0.5), (0.5, 1.01))


# --------------------------------------------------------------------------
# Reine Logik (ohne ultralytics/cv2 testbar)
# --------------------------------------------------------------------------

def sekundenbilder(fps: float, anzahl: int) -> list[int]:
    """Indizes der Videobilder, die 1 Bild je Sekunde ergeben (wie der Agent)."""
    if anzahl <= 0:
        return []
    if not fps or fps <= 1.0:
        return list(range(anzahl))
    schritt = fps
    out, naechstes = [], 0.0
    for i in range(anzahl):
        if i >= naechstes - 1e-9:
            out.append(i)
            naechstes += schritt
    return out


def kennzahlen(bilder: list[list[tuple[float, int | None]]]) -> dict:
    """Kennzahlen aus (Konfidenz, Track-ID oder None) je Erkennung und Bild.

    Kuehe im Bild = hoechste Zahl gleichzeitiger langer IDs (Schaetzung);
    ID-Wechsel = IDs mit >= MIN_LEBENSDAUER_S Bildern minus Kuehe.
    """
    leben: dict[int, int] = {}
    je_bild: list[set[int]] = []
    pro_band = {b: [0, 0] for b in BAENDER}  # [Erkennungen, davon ohne ID]
    for bild in bilder:
        ids_im_bild = set()
        for conf, tid in bild:
            for unten, oben in BAENDER:
                if unten <= conf < oben:
                    pro_band[(unten, oben)][0] += 1
                    if tid is None:
                        pro_band[(unten, oben)][1] += 1
            if tid is not None:
                ids_im_bild.add(tid)
        for tid in ids_im_bild:
            leben[tid] = leben.get(tid, 0) + 1
        je_bild.append(ids_im_bild)
    lange = sorted(t for t, n in leben.items() if n >= MIN_LEBENSDAUER_S)
    # Kurzes Flackern zaehlt nicht als weitere Kuh
    gleichzeitig = max((len(ids & set(lange)) for ids in je_bild), default=0)
    kuehe = max(gleichzeitig, 1) if leben else 0
    wechsel = max(0, len(lange) - kuehe)
    minuten = len(bilder) / 60
    je_kuh_10 = (wechsel / kuehe / (minuten / 10)) if kuehe and minuten else 0.0
    return {
        "dauer_min": round(minuten, 1),
        "ids": len(leben),
        "ids_lang": len(lange),
        "kuehe": kuehe,
        "wechsel": wechsel,
        "wechsel_je_kuh_10min": round(je_kuh_10, 2),
        "ziel_erfuellt": bool(kuehe) and je_kuh_10 < ZIEL_WECHSEL_PRO_KUH_10MIN,
        "ohne_id": {f"{u:.2f}–{min(o, 1.0):.2f}": (n, ohne) for (u, o), (n, ohne) in pro_band.items()},
    }


def ohne_id_anteil(e: dict) -> float:
    """Anteil der Erkennungen ab conf 0.25, die keine ID bekamen."""
    n = ohne = 0
    for band, (anz, o) in e["ohne_id"].items():
        if float(band.split("–")[0]) >= 0.25:
            n, ohne = n + anz, ohne + o
    return ohne / n if n else 0.0


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

    zeile("Dauer", lambda e: f"{e['dauer_min']} min")
    zeile("Kühe im Bild (geschätzt)", lambda e: str(e["kuehe"]))
    zeile(f"IDs (≥ {MIN_LEBENSDAUER_S} s)", lambda e: f"{e['ids_lang']} (alle: {e['ids']})")
    zeile("ID-Wechsel je Kuh / 10 min", lambda e: f"{e['wechsel_je_kuh_10min']}"
          + (" ✓" if e["ziel_erfuellt"] else " ✗"))
    for band in next(iter(ergebnisse.values()))["ohne_id"]:
        zeile(f"Erkennungen conf {band} ohne ID",
              lambda e, b=band: (f"{e['ohne_id'][b][1]} von {e['ohne_id'][b][0]}"
                                 if e["ohne_id"][b][0] else "–"))
    for n in namen:
        if ohne_id_anteil(ergebnisse[n]) > 0.05:
            z.append("")
            z.append(f"**Achtung {n}:** {ohne_id_anteil(ergebnisse[n]):.0%} der Erkennungen "
                     "ab conf 0.25 ohne ID – diese Kühe fehlen in der Auswertung, die "
                     "ID-Wechsel-Zahl allein trügt.")
    z.append("")
    z.append(f"Ziel: < {ZIEL_WECHSEL_PRO_KUH_10MIN:g} ID-Wechsel je Kuh in 10 min. "
             "Viele Erkennungen ohne ID in einem Band heißen: Diese Kühe werden "
             "nicht ausgewertet (Schwanzwinkel, Brunst) – Abwägung im Skill bytetrack-tuning.")
    return "\n".join(z)


# --------------------------------------------------------------------------
# Inferenz und Tracker (brauchen ultralytics/cv2)
# --------------------------------------------------------------------------

def erkennungen_aus_clip(clip: Path, modell_pfad: str, klasse: str) -> tuple[list, float]:
    """Je Sekundenbild die Kuh-Erkennungen [[cx, cy, w, h, conf], …] + Bilder/s."""
    import cv2
    from ultralytics import YOLO

    modell = YOLO(modell_pfad)
    namen = {v: k for k, v in modell.names.items()}
    if klasse not in namen:
        raise SystemExit(f"Klasse {klasse!r} nicht im Modell: {sorted(namen)}")
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    anzahl = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    wahl = set(sekundenbilder(fps, anzahl)) if anzahl else None
    bilder, rechenzeit, i = [], 0.0, -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        i += 1
        if wahl is not None and i not in wahl:
            continue
        t0 = time.perf_counter()
        # conf 0.1 wie model.track() im Agenten
        erg = modell.predict(frame, conf=0.1, classes=[namen[klasse]], verbose=False)[0]
        rechenzeit += time.perf_counter() - t0
        b = erg.boxes
        bilder.append([[*map(float, b.xywh[j].tolist()), float(b.conf[j])] for j in range(len(b))])
    cap.release()
    return bilder, (len(bilder) / rechenzeit if rechenzeit else 0.0)


def verfolge(bilder: list, tracker_pfad: str) -> list[list[tuple[float, int | None]]]:
    """Erkennungen durch den echten BYTETracker; je Erkennung (conf, ID|None)."""
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tracker_simulation import lade_tracker

    class Boxen:
        def __init__(self, zeilen):
            a = np.array(zeilen, dtype=np.float32).reshape(-1, 5)
            self.xywh, self.conf = a[:, :4], a[:, 4]
            self.cls = np.zeros(len(a), dtype=np.float32)

        def __len__(self):
            return len(self.conf)

    tracker = lade_tracker(tracker_pfad)
    out = []
    for zeilen in bilder:
        ids: dict[int, int] = {}
        if zeilen:  # wie ultralytics track.py: ohne Erkennung kein update()
            for t in tracker.update(Boxen(zeilen)):
                ids[int(t[-1])] = int(t[4])
        out.append([(z[4], ids.get(j)) for j, z in enumerate(zeilen)])
    return out


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("clip", type=Path)
    a.add_argument("--modell", help="best.pt/.onnx; ohne: Erkennungen aus <clip>.erkennungen.json")
    a.add_argument("--klasse", default="kuh")
    a.add_argument("--tracker", nargs="+", default=["../tracker-kuh.yaml", "bytetrack.yaml"])
    arg = a.parse_args()

    ablage = arg.clip.with_suffix(".erkennungen.json")
    fps_geraet = None
    if arg.modell:
        bilder, fps_geraet = erkennungen_aus_clip(arg.clip, arg.modell, arg.klasse)
        ablage.write_text(json.dumps({"modell": arg.modell, "klasse": arg.klasse,
                                      "fps_geraet": fps_geraet, "bilder": bilder}))
        print(f"Erkennungen gespeichert: {ablage}", file=sys.stderr)
    elif ablage.exists():
        daten = json.loads(ablage.read_text())
        bilder, fps_geraet = daten["bilder"], daten.get("fps_geraet")
    else:
        raise SystemExit(f"{ablage} fehlt – einmal mit --modell aufrufen.")

    ergebnisse = {Path(t).name: kennzahlen(verfolge(bilder, t)) for t in arg.tracker}
    print(f"## Tracking-Prüfung {arg.clip.name}\n")
    print(tabelle(ergebnisse, fps_geraet))
    return 0 if all(e["ziel_erfuellt"] for e in ergebnisse.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
