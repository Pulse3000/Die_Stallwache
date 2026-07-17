#!/usr/bin/env python3
"""Logiktests TotmannWaechter: genau eine Meldung pro Ausfall-Episode,
genau eine Entwarnung, frische Zaehlung pro Episode, Deaktivierung."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, _ = lade_main()
p = Pruefer("TotmannWaechter")

cfg = {"stream": {"totmann_minuten": 5}}
w = m.TotmannWaechter(cfg, jetzt=0.0)


def enthaelt(ergebnis, soll):
    if soll is None:
        return ergebnis is None
    return ergebnis is not None and soll in ergebnis


# Normalbetrieb
p.check("t=10 Frame ok -> still", enthaelt(w.tick(True, 10), None))
p.check("t=100 Frame ok -> still", enthaelt(w.tick(True, 100), None))

# Ausfall (zaehlt ab letztem gutem Frame t=100)
p.check("t=150 unter Schwelle", enthaelt(w.tick(False, 150), None))
p.check("t=399: 299 s < 300 s", enthaelt(w.tick(False, 399), None))
p.check("t=400: 300 s -> MELDUNG", enthaelt(w.tick(False, 400), "blind"))
p.check("t=500 weiter still (einmal pro Episode)", enthaelt(w.tick(False, 500), None))
p.check("t=800 weiter still", enthaelt(w.tick(False, 800), None))

# Rueckkehr
p.check("t=900 Rueckkehr -> ENTWARNUNG", enthaelt(w.tick(True, 900), "wieder"))
p.check("t=901 ok -> still", enthaelt(w.tick(True, 901), None))

# Zweite Episode zaehlt frisch (letzter guter Frame t=901)
p.check("t=1000 unter Schwelle", enthaelt(w.tick(False, 1000), None))
p.check("t=1200: 299 s", enthaelt(w.tick(False, 1200), None))
p.check("t=1201: 300 s -> MELDUNG", enthaelt(w.tick(False, 1201), "blind"))

# Kurzer Ausfall unter Schwelle: weder Meldung noch Entwarnung
w2 = m.TotmannWaechter(cfg, jetzt=0.0)
w2.tick(True, 10)
p.check("kurzer Ausfall still", enthaelt(w2.tick(False, 130), None))
p.check("Rueckkehr ohne Entwarnung", enthaelt(w2.tick(True, 140), None))

# Deaktiviert
w3 = m.TotmannWaechter({"stream": {"totmann_minuten": 0}}, jetzt=0.0)
p.check("deaktiviert: nie Meldung", enthaelt(w3.tick(False, 3600), None))

sys.exit(p.bericht())
