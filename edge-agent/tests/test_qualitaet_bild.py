#!/usr/bin/env python3
"""B20-Abnahme am Bild (synthetisch): defekt_anteil erkennt senkrechte
Schmierstreifen und laesst intakte Textur durch. Quelltext-Waechter und echte
Stallbilder: test_qualitaet_stallbilder.py. Braucht numpy + OpenCV (sonst 77)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, braucht, lade_main  # noqa: E402

braucht("numpy", "cv2")
import cv2  # noqa: E402
import numpy as np  # noqa: E402

m, _ = lade_main()
p = Pruefer("Bildqualitaet am Bild (B20)")

p.check("Konfig-Default = kalibrierte Schwelle 0.04", m.BildQualitaet({}).schwelle == 0.04)

# Synthetisch: Textur intakt vs. ab Zeile 600 nach unten verschmiert
rng = np.random.default_rng(20)
intakt = cv2.GaussianBlur(rng.integers(0, 255, (1440, 2560, 3), dtype=np.uint8), (5, 5), 0)
schmier = intakt.copy()
schmier[600:] = schmier[600]
q = m.BildQualitaet({})
p.check("intakte Textur -> kein Defektbild", q.pruefe(intakt)[0] is False)
d, anteil = q.pruefe(schmier)
p.check(f"senkrechte Schmierstreifen ab Zeile 600 -> Defektbild ({anteil:.2f})", d is True)
p.check("Graustufenbild geht auch", isinstance(m.defekt_anteil(cv2.cvtColor(intakt, cv2.COLOR_BGR2GRAY)), float))

sys.exit(p.bericht())
