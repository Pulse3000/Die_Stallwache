#!/usr/bin/env python3
"""
Sichtung von Stall-Aufnahmen in einem Zeitfenster — NUR LESEND.

Die Originale in ./aufnahmen werden weder verschoben noch verändert.
Ausgabe: beschriftete Kontaktbögen in einem NEUEN Ordner.

Beispiel (Mo 26.10.2026, 08:00-17:00):
    python stall_sichtung.py ./aufnahmen --von "2026-10-26 08:00" --bis "2026-10-26 17:00"

Optional mit Vorfilter (nur Bilder mit >= 2 Kühen dicht beieinander):
    python stall_sichtung.py ./aufnahmen --von ... --bis ... --modell best.pt

Zeitbasis ist die Änderungszeit der Datei (mtime), weil das Dateinamensmuster
nicht bekannt ist. Bei kopierten Dateien kann mtime vom Aufnahmezeitpunkt
abweichen — dann --zeit-aus-name nutzen (erwartet YYYYMMDD_HHMMSS im Namen).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ENDUNGEN = {".jpg", ".jpeg", ".png"}
NAME_ZEIT = re.compile(r"(\d{8})[_-]?(\d{6})")


def zeit_der_datei(p: Path, aus_name: bool) -> datetime:
    if aus_name:
        m = NAME_ZEIT.search(p.name)
        if m:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
    return datetime.fromtimestamp(p.stat().st_mtime)


def sammle(ordner: Path, von: datetime, bis: datetime, aus_name: bool):
    treffer = []
    for p in ordner.rglob("*"):
        if p.suffix.lower() not in ENDUNGEN or not p.is_file():
            continue
        t = zeit_der_datei(p, aus_name)
        if von <= t <= bis:
            treffer.append((t, p))
    return sorted(treffer)


def kuehe_dicht(ergebnis, abstand_faktor: float = 0.6) -> bool:
    """>= 2 Kuh-Boxen, die sich überlappen oder deren Mittelpunkte nah liegen."""
    boxen = [b for b, c in zip(ergebnis.boxes.xyxy.cpu().numpy(),
                               ergebnis.boxes.cls.cpu().numpy())
             if ergebnis.names[int(c)] == "kuh"]
    for i in range(len(boxen)):
        for j in range(i + 1, len(boxen)):
            a, b = boxen[i], boxen[j]
            ueberlapp = not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
            ca = ((a[0] + a[2]) / 2, (a[1] + a[3]) / 2)
            cb = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            breite = ((a[2] - a[0]) + (b[2] - b[0])) / 2
            if ueberlapp or np.hypot(ca[0] - cb[0], ca[1] - cb[1]) < abstand_faktor * breite:
                return True
    return False


def kachel(bild, text: str, breite: int, hoehe: int, markiert: bool):
    k = cv2.resize(bild, (breite, hoehe))
    cv2.rectangle(k, (0, 0), (breite, 22), (0, 0, 0), -1)
    cv2.putText(k, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (0, 200, 255) if markiert else (255, 255, 255), 1, cv2.LINE_AA)
    if markiert:
        cv2.rectangle(k, (0, 0), (breite - 1, hoehe - 1), (0, 200, 255), 3)
    return k


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ordner", type=Path)
    ap.add_argument("--von", required=True, help='z. B. "2026-10-26 08:00"')
    ap.add_argument("--bis", required=True, help='z. B. "2026-10-26 17:00"')
    ap.add_argument("--ausgabe", type=Path, default=None)
    ap.add_argument("--modell", type=Path, default=None, help="best.pt für den Nähe-Vorfilter")
    ap.add_argument("--zeit-aus-name", action="store_true")
    ap.add_argument("--spalten", type=int, default=4)
    ap.add_argument("--zeilen", type=int, default=3)
    a = ap.parse_args()

    fmt = "%Y-%m-%d %H:%M"
    von, bis = datetime.strptime(a.von, fmt), datetime.strptime(a.bis, fmt)
    treffer = sammle(a.ordner, von, bis, a.zeit_aus_name)
    if not treffer:
        print("Keine Bilder im Zeitfenster gefunden.", file=sys.stderr)
        return 1

    aus = a.ausgabe or Path(f"sichtung_{von:%Y-%m-%d_%H%M}-{bis:%H%M}")
    if aus.resolve() == a.ordner.resolve() or a.ordner.resolve() in aus.resolve().parents:
        print("Ausgabe darf nicht im Aufnahmen-Ordner liegen.", file=sys.stderr)
        return 2
    aus.mkdir(parents=True, exist_ok=True)

    modell = None
    if a.modell:
        from ultralytics import YOLO  # nur bei Bedarf
        modell = YOLO(str(a.modell))

    markiert_liste = []
    kacheln = []
    for t, p in treffer:
        bild = cv2.imread(str(p))
        if bild is None:
            print(f"Nicht lesbar, übersprungen: {p}", file=sys.stderr)
            continue
        nah = False
        if modell is not None:
            nah = kuehe_dicht(modell.predict(bild, verbose=False)[0])
            if nah:
                markiert_liste.append(p)
        kacheln.append(kachel(bild, f"{t:%H:%M:%S}  {p.name[:22]}", 480, 270, nah))

    pro_bogen = a.spalten * a.zeilen
    leer = np.zeros_like(kacheln[0])
    for n, start in enumerate(range(0, len(kacheln), pro_bogen), 1):
        block = kacheln[start:start + pro_bogen]
        block += [leer] * (pro_bogen - len(block))
        reihen = [np.hstack(block[r * a.spalten:(r + 1) * a.spalten]) for r in range(a.zeilen)]
        cv2.imwrite(str(aus / f"bogen_{n:03d}.jpg"), np.vstack(reihen),
                    [int(cv2.IMWRITE_JPEG_QUALITY), 85])

    if modell is not None:
        (aus / "nah_beieinander.txt").write_text("\n".join(map(str, markiert_liste)), encoding="utf-8")

    print(f"{len(kacheln)} Bilder im Fenster, {-(-len(kacheln) // pro_bogen)} Bögen in {aus}/")
    if modell is not None:
        print(f"{len(markiert_liste)} Bilder mit >= 2 Kühen dicht beieinander -> nah_beieinander.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
