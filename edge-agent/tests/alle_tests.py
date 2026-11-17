#!/usr/bin/env python3
"""Fuehrt alle Edge-Agent-Logiktests aus (pures Python, keine Installation
noetig):  python3 edge-agent/tests/alle_tests.py"""

import subprocess
import sys
from pathlib import Path

hier = Path(__file__).resolve().parent
fehl = 0
uebersprungen = []
for test in sorted(hier.glob("test_*.py")):
    print(f"\n=== {test.name} " + "=" * (40 - len(test.name)))
    # Jeder Test im eigenen Prozess: saubere sys.modules-Stubs pro Datei.
    rc = subprocess.run([sys.executable, str(test)]).returncode
    if rc == 77:  # hilfe.UEBERSPRUNGEN: Abhaengigkeit oder Daten fehlen (z. B. ultralytics, Trainingsordner)
        uebersprungen.append(test.name)
    elif rc != 0:
        fehl += 1

if uebersprungen:
    print(f"\nUEBERSPRUNGEN (Abhaengigkeit oder Daten fehlen): {', '.join(uebersprungen)}")
print(f"\n{'ALLE TESTS GRUEN' if fehl == 0 else f'{fehl} TESTDATEI(EN) ROT'}")
sys.exit(1 if fehl else 0)
