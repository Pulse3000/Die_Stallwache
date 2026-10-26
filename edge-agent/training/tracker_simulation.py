#!/usr/bin/env python3
"""ByteTrack-Konfiguration an Kuh-Szenarien pruefen, ohne Modell und Kamera.

Fuettert den echten Ultralytics-Tracker (BYTETracker, gleiche Version wie im
Agent-Image) mit erfundenen Erkennungen bei 1 FPS: Verdeckung, zwei Kuehe
gehen aneinander vorbei, schwache Erkennung nachts, Rauschen. So laesst sich
eine tracker-*.yaml beurteilen, bevor es ein Modell gibt. Die Messung am
echten Stall ersetzt das nicht (tracking_pruefung.py, Skill bytetrack-tuning).

  python3 tracker_simulation.py ../tracker-kuh.yaml bytetrack.yaml

Braucht ultralytics (z. B. im Analyse-Image oder in Colab). bytetrack.yaml
ist der Ultralytics-Default der installierten Version.

Nachgebildet ist der Aufruf aus ultralytics/trackers/track.py: Bilder ohne
jede Erkennung erreichen den Tracker nicht, verlorene Tracks altern dort
also nicht. Darum steht in den Szenarien eine zweite, ruhende Kuh im Bild.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import numpy as np


@dataclass
class Box:
    kuh: str          # wahre Identitaet (nur fuer die Auswertung)
    cx: float
    cy: float
    w: float = 200.0
    h: float = 120.0
    conf: float = 0.85


class Erkennungen:
    """Minimaler Ersatz fuer ultralytics Boxes (conf, xywh, cls)."""

    def __init__(self, boxen: list[Box]):
        self.conf = np.array([b.conf for b in boxen], dtype=np.float32)
        self.xywh = np.array([[b.cx, b.cy, b.w, b.h] for b in boxen], dtype=np.float32)
        self.cls = np.zeros(len(boxen), dtype=np.float32)

    def __len__(self) -> int:
        return len(self.conf)


def lade_tracker(pfad: str):
    from ultralytics.trackers.byte_tracker import BYTETracker
    from ultralytics.utils import IterableSimpleNamespace, yaml_load
    from ultralytics.utils.checks import check_yaml

    cfg = IterableSimpleNamespace(**yaml_load(check_yaml(pfad)))
    return BYTETracker(args=cfg, frame_rate=30)  # wie track.py: Frames = Sekunden bei 1 FPS


def lauf(pfad: str, bilder: list[list[Box]]) -> dict[str, list[int | None]]:
    """IDs je wahrer Kuh und Bild (None = ohne ID in diesem Bild)."""
    tracker = lade_tracker(pfad)
    namen = sorted({b.kuh for bild in bilder for b in bild})
    ids: dict[str, list[int | None]] = {k: [] for k in namen}
    for bild in bilder:
        gesehen: dict[str, int] = {}
        if bild:  # track.py: ohne Erkennung kein update()
            tracks = tracker.update(Erkennungen(bild))
            for t in tracks:
                gesehen[bild[int(t[-1])].kuh] = int(t[4])
        for k in namen:
            ids[k].append(gesehen.get(k))
    return ids


def wechsel(folge: list[int | None]) -> int:
    """ID-Wechsel einer Kuh: wie oft die ID nach einer Luecke/Umschaltung anders ist."""
    bekannt = [i for i in folge if i is not None]
    return sum(1 for a, b in zip(bekannt, bekannt[1:]) if a != b)


# --------------------------------------------------------------------------
# Szenarien (1 Bild = 1 s)
# --------------------------------------------------------------------------

def verdeckung(sekunden: int) -> list[list[Box]]:
    """Kuh A steht 60 s, ist `sekunden` lang verdeckt, steht dann wieder da.
    Kuh B ruht die ganze Zeit sichtbar daneben."""
    bilder = []
    for t in range(60 + sekunden + 30):
        bild = [Box("B", 700, 300)]
        if not 60 <= t < 60 + sekunden:
            bild.append(Box("A", 300 + (5 if t >= 60 + sekunden else 0), 300))
        bilder.append(bild)
    return bilder


def vorbeigehen(geschwindigkeit: float) -> list[list[Box]]:
    """A geht nach rechts, C nach links, auf fast gleicher Hoehe (Stallgang)."""
    bilder = []
    for t in range(int(800 / geschwindigkeit) + 20):
        x = 150 + geschwindigkeit * t
        bilder.append([
            Box("A", min(x, 950), 300),
            Box("C", max(950 - geschwindigkeit * t, 150), 320),
        ])
    return bilder


def schwach(conf: float, neu: bool) -> list[list[Box]]:
    """Nachts (IR) nur `conf`. neu=True: A taucht nachts neu auf;
    neu=False: A war tagsueber mit 0.85 da und wird schwaecher."""
    bilder = []
    for t in range(300):
        bild = [Box("B", 700, 300)]
        if neu:
            bild.append(Box("A", 300, 300, conf=conf))
        else:
            bild.append(Box("A", 300, 300, conf=0.85 if t < 60 else conf))
        bilder.append(bild)
    return bilder


def rauschen(rate: float, conf: float, sekunden: int = 3600, saat: int = 7) -> list[list[Box]]:
    """Eine ruhende Kuh plus zufaellige Einzelbild-Fehlerkennungen."""
    rng = np.random.default_rng(saat)
    bilder = []
    for _ in range(sekunden):
        bild = [Box("B", 700, 300)]
        if rng.random() < rate:
            bild.append(Box("Geist", float(rng.uniform(100, 1100)),
                            float(rng.uniform(100, 600)), 120, 80, conf))
        bilder.append(bild)
    return bilder


def schwankend(mittel: float, sigma: float, aussetzer: float = 0.0,
               sekunden: int = 3600, saat: int = 0) -> list[list[Box]]:
    """Nachts taucht A neu auf, Konfidenz je Bild ~ N(mittel, sigma);
    `aussetzer` = Anteil Bilder, in denen A gar nicht erkannt wird."""
    rng = np.random.default_rng(saat)
    bilder = []
    for _ in range(sekunden):
        bild = [Box("B", 700, 300)]
        if rng.random() >= aussetzer:
            conf = float(np.clip(rng.normal(mittel, sigma), 0.11, 0.99))
            bild.append(Box("A", 300, 300, conf=conf))
        bilder.append(bild)
    return bilder


def dauer_fehlerkennung(conf: float, sekunden: int = 600) -> list[list[Box]]:
    """Ein ruhendes Objekt (z. B. Heuballen) wird in jedem Bild mit `conf`
    als Kuh erkannt, daneben eine echte Kuh."""
    return [[Box("B", 700, 300), Box("Geist", 300, 450, 160, 90, conf)]
            for _ in range(sekunden)]


def auswerten(pfade: list[str]) -> list[tuple[str, list[str]]]:
    zeilen: list[tuple[str, list[str]]] = []

    for s in (20, 45, 60, 85, 100, 150):
        werte = []
        for p in pfade:
            a = lauf(p, verdeckung(s))["A"]
            vorher, nachher = a[59], a[-1]
            werte.append("ID bleibt" if vorher is not None and vorher == nachher else "neue ID")
        zeilen.append((f"Verdeckung {s} s", werte))

    for v in (10.0, 30.0):
        werte = []
        for p in pfade:
            ids = lauf(p, vorbeigehen(v))
            n = wechsel(ids["A"]) + wechsel(ids["C"])
            werte.append("kein Wechsel" if n == 0 else f"{n} Wechsel")
        zeilen.append((f"Vorbeigehen {v:.0f} px/s", werte))

    for conf in (0.3, 0.45):
        for neu in (True, False):
            werte = []
            for p in pfade:
                a = lauf(p, schwach(conf, neu))["A"]
                nachts = a[60:]
                anteil = sum(1 for i in nachts if i is not None) / len(nachts)
                werte.append(f"{anteil:.0%} mit ID" + ("" if neu else f", {wechsel(a)} Wechsel"))
            zeilen.append((f"Nachts conf {conf} ({'neu' if neu else 'schon getrackt'})", werte))

    for mittel, sigma, aus in ((0.35, 0.08, 0.0), (0.45, 0.08, 0.0), (0.30, 0.08, 0.02)):
        werte = []
        for p in pfade:
            anteile = []
            for saat in range(4):
                a = lauf(p, schwankend(mittel, sigma, aus, saat=saat))["A"]
                anteile.append(sum(1 for i in a if i is not None) / len(a))
            werte.append(f"{sum(anteile) / len(anteile):.0%} mit ID")
        zeilen.append((f"Nachts neu, conf {mittel}±{sigma}"
                       + (f", {aus:.0%} Aussetzer" if aus else ""), werte))

    for conf in (0.3, 0.6):
        werte = []
        for p in pfade:
            ids = lauf(p, rauschen(0.05, conf))
            geister = len({i for i in ids.get("Geist", []) if i is not None})
            werte.append(f"{geister} Geister-IDs/h")
        zeilen.append((f"Rauschen 5 % der Bilder, conf {conf}", werte))

    for conf in (0.3, 0.45):
        werte = []
        for p in pfade:
            g = lauf(p, dauer_fehlerkennung(conf))["Geist"]
            werte.append("Geister-ID" if any(i is not None for i in g) else "keine ID")
        zeilen.append((f"Dauer-Fehlerkennung conf {conf} (Heuballen)", werte))
    return zeilen


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("tracker", nargs="+", help="tracker-*.yaml (Pfad) oder bytetrack.yaml")
    arg = a.parse_args()
    try:
        import ultralytics
    except ImportError:
        print("ultralytics fehlt (pip install ultralytics==8.3.40).", file=sys.stderr)
        return 2
    kopf = ["Szenario"] + arg.tracker
    print(f"Ultralytics {ultralytics.__version__}, 1 Bild = 1 s\n")
    print("| " + " | ".join(kopf) + " |")
    print("|" + "---|" * len(kopf))
    for name, werte in auswerten(arg.tracker):
        print("| " + " | ".join([name] + werte) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
