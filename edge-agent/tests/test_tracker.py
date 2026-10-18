#!/usr/bin/env python3
"""Logiktests InferenceEngine-Tracker-Wiring + YAML-Konsistenz der
Referenz-Schwellenwerte (bewacht vom Agenten ki-wache)."""

import re
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
    ("tracker_type: bytetrack", trk_text),
    ("track_high_thresh: 0.4", trk_text),
    ("track_low_thresh: 0.05", trk_text),
    ("new_track_thresh: 0.5", trk_text),
    ("match_thresh: 0.9", trk_text),
    ("fuse_score: True", trk_text),
    ("tracker: tracker-kuh.yaml", cfg_text),
]


def zeile_vorhanden(eintrag: str, text: str) -> bool:
    """Ganze YAML-Zeile statt Teilstring: 'track_buffer: 90' passt nicht
    auf 'track_buffer: 900', ein Kommentar dahinter ist erlaubt."""
    schluessel, wert = (s.strip() for s in eintrag.split(":", 1))
    muster = rf"(?m)^\s*{re.escape(schluessel)}:\s*{re.escape(wert)}\s*(#.*)?$"
    return re.search(muster, text) is not None


p.check("Zeilenpruefung erkennt 'track_buffer: 900' nicht als 90",
        not zeile_vorhanden("track_buffer: 90", "track_buffer: 900\n"))
for eintrag, text in referenzen:
    p.check(f"Referenzwert intakt: {eintrag}", zeile_vorhanden(eintrag, text))

# Verdrahtung: der Tracker wird mit persist=True und der eigenen Datei
# aufgerufen (sonst neue IDs in jedem Bild, das 30-min-Fenster liefe nie voll).
main_text = (wurzel / "main.py").read_text(encoding="utf-8")
aufruf = re.search(r"self\.modell\.track\((.*?)\)\[0\]", main_text, re.S)
p.check("track()-Aufruf gefunden", aufruf is not None)
p.check("track() mit persist=True und tracker=self.tracker",
        aufruf is not None and "persist=True" in aufruf.group(1)
        and "tracker=self.tracker" in aufruf.group(1))

sys.exit(p.bericht())
