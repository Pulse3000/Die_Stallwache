#!/usr/bin/env python3
"""Logiktests InferenceEngine-Tracker-Wiring + YAML-Konsistenz der
Referenz-Schwellenwerte (bewacht vom Agenten ki-wache)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, _ = lade_main()
p = Pruefer("Tracker & Referenzwerte")

basis = {"keypoints": {}, "klassen": {"kuh": 0}}
e1 = m.InferenceEngine({"modell": dict(basis, pfad="", tracker="tracker-kuh.yaml")})
e2 = m.InferenceEngine({"modell": dict(basis, pfad="")})
e3 = m.InferenceEngine({"modell": dict(basis, pfad="", tracker="  ")})
p.check("eigener Tracker uebernommen", e1.tracker == "tracker-kuh.yaml")
p.check("fehlender Key -> Ultralytics-Default", e2.tracker == "bytetrack.yaml")
p.check("Leerstring -> Ultralytics-Default", e3.tracker == "bytetrack.yaml")
p.check("ohne Modellpfad inaktiv (Silent Mode)", not e1.aktiv)

# Referenz-Schwellenwerte in config.example.yaml / tracker-kuh.yaml (mit
# echtem PyYAML, falls installiert; sonst Text-Pruefung als Fallback).
wurzel = Path(__file__).resolve().parent.parent
cfg_text = (wurzel / "config.example.yaml").read_text(encoding="utf-8")
trk_text = (wurzel / "tracker-kuh.yaml").read_text(encoding="utf-8")
referenzen = [
    ("winkel_schwelle_grad: 45", cfg_text),
    ("fenster_minuten: 30", cfg_text),
    ("anteil_schwelle: 0.20", cfg_text),
    ("override_konfidenz: 0.80", cfg_text),
    ("brunst_min_dauer_s: 4", cfg_text),
    ("eskalation_minuten: 60", cfg_text),
    ("cooldown_minuten: 15", cfg_text),
    ("totmann_minuten: 5", cfg_text),
    ("track_buffer: 90", trk_text),
]
for eintrag, text in referenzen:
    p.check(f"Referenzwert intakt: {eintrag}", eintrag in text)

sys.exit(p.bericht())
