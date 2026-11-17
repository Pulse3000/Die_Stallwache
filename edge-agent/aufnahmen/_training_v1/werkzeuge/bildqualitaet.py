#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bildqualität: erkennt Dekodier-Defekte (vertikale Schmierstreifen nach Paketverlust im Stream).

Hintergrund (gemessen 2026-11-01 an 2.586 Silent-Mode-Bildern): 11,7 % der Bilder (302, überwiegend nachts/IR)
zeigen ab einer Zeile senkrechte Farbstreifen — der Decoder hat nach Paketverlust Bildzeilen nach unten
"verschmiert". Solche Bilder sind fürs Labeln unbrauchbar (Kuh halb verschmiert).

Empfehlung für den Agenten (Recall der Austreibung geht vor):
  - Defektbild NICHT in die Schwanzwinkel-Statistik (30-min-Fenster) aufnehmen und Kalibrierung aussetzen,
  - die Austreibungs-Erkennung (amniotic_sac/calf_legs) aber trotzdem laufen lassen — nie unterdrücken,
  - Defektquote zählen; steigt sie dauerhaft (z. B. > 50 % über 10 min), Info-Ereignis "Bildqualität degradiert"
    (Stille Degradation: Restbetrieb läuft, Einschränkung wird gemeldet).

Merkmal: Bild auf 640x360 Graustufen, Raster aus 40x40-Zellen. Eine Zelle gilt als verschmiert, wenn die
mittlere vertikale Helligkeitsänderung deutlich kleiner ist als die horizontale
(v / (h + 0.5) < 0.35) bei vorhandener Struktur (h > 0.8). defekt_anteil = Anteil solcher Zellen.
Kalibrierung (Sichtprüfung von 36 Stichproben): intakte Bilder 0.000–0.033, defekte 0.050–0.750,
schmale Streifen am unteren Rand 0.017–0.033 (noch nutzbar). Schwelle 0.04.

Laufzeit: ~5 ms je Bild (ohne Dekodieren). Nur numpy + OpenCV.

CLI:  python3 bildqualitaet.py BILD [BILD ...]      -> druckt defekt_anteil je Bild
"""
import sys

import cv2
import numpy as np

SCHWELLE_DEFEKT = 0.04
ZELLE = 40


def defekt_anteil(bild):
    """bild: BGR- oder Graustufenbild beliebiger Größe. Rückgabe: Anteil verschmierter Zellen (0..1)."""
    if bild.ndim == 3:
        bild = cv2.cvtColor(bild, cv2.COLOR_BGR2GRAY)
    if bild.shape[1] != 640:
        bild = cv2.resize(bild, (640, int(round(bild.shape[0] * 640 / bild.shape[1]))), interpolation=cv2.INTER_AREA)
    g = bild.astype(np.float32)
    h_, w_ = g.shape
    vd = np.abs(np.diff(g, axis=0))[:, :-1]
    hd = np.abs(np.diff(g, axis=1))[:-1, :]
    ny, nx = (h_ - 1) // ZELLE, (w_ - 1) // ZELLE
    if ny == 0 or nx == 0:
        return 0.0
    v = vd[:ny * ZELLE, :nx * ZELLE].reshape(ny, ZELLE, nx, ZELLE).mean((1, 3))
    h = hd[:ny * ZELLE, :nx * ZELLE].reshape(ny, ZELLE, nx, ZELLE).mean((1, 3))
    return float(((v / (h + 0.5) < 0.35) & (h > 0.8)).mean())


def ist_defekt(bild, schwelle=SCHWELLE_DEFEKT):
    return defekt_anteil(bild) > schwelle


def lies_schnell(pfad):
    """Liest ein JPEG direkt in 1/4-Auflösung als Graustufen (2560x1440 -> 640x360), sehr schnell."""
    return cv2.imread(pfad, cv2.IMREAD_REDUCED_GRAYSCALE_4)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        img = lies_schnell(p)
        if img is None:
            print(f"{p}\tUNLESBAR")
            continue
        a = defekt_anteil(img)
        print(f"{p}\t{a:.3f}\t{'DEFEKT' if a > SCHWELLE_DEFEKT else 'ok'}")
