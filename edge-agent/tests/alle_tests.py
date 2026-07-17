#!/usr/bin/env python3
"""Fuehrt alle Edge-Agent-Logiktests aus (pures Python, keine Installation
noetig):  python3 edge-agent/tests/alle_tests.py"""

import subprocess
import sys
from pathlib import Path

hier = Path(__file__).resolve().parent
fehl = 0
for test in sorted(hier.glob("test_*.py")):
    print(f"\n=== {test.name} " + "=" * (40 - len(test.name)))
    # Jeder Test im eigenen Prozess: saubere sys.modules-Stubs pro Datei.
    if subprocess.run([sys.executable, str(test)]).returncode != 0:
        fehl += 1

print(f"\n{'ALLE TESTS GRUEN' if fehl == 0 else f'{fehl} TESTDATEI(EN) ROT'}")
sys.exit(1 if fehl else 0)
