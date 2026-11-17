#!/usr/bin/env python3
"""Fuehrt alle Edge-Agent-Logiktests aus (pures Python, keine Installation
noetig):

    python3 edge-agent/tests/alle_tests.py           # volle Ausgabe
    python3 edge-agent/tests/alle_tests.py --kurz    # eine Zeile je Testdatei

--kurz zeigt je Datei nur das Ergebnis und die Zahl der Checks; die volle
Ausgabe einer Datei erscheint nur, wenn sie rot ist. Das ist die Form fuer
`npm run test:agent` und die CI: Die volle Ausgabe sind ueber tausend Zeilen
Log, in denen ein einzelnes FEHL leicht untergeht.
"""

import subprocess
import sys
from pathlib import Path

hier = Path(__file__).resolve().parent
kurz = "--kurz" in sys.argv[1:]
fehl = 0
checks_gesamt = 0
dateien = sorted(hier.glob("test_*.py"))

for test in dateien:
    # Jeder Test im eigenen Prozess: saubere sys.modules-Stubs pro Datei.
    if not kurz:
        print(f"\n=== {test.name} " + "=" * (40 - len(test.name)))
        if subprocess.run([sys.executable, str(test)]).returncode != 0:
            fehl += 1
        continue

    lauf = subprocess.run(
        [sys.executable, str(test)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    zeilen = lauf.stdout.splitlines()
    checks = sum(1 for z in zeilen if z.startswith("OK "))
    checks_gesamt += checks
    if lauf.returncode == 0:
        print(f"OK   {test.name} ({checks} Checks)")
    else:
        fehl += 1
        print(f"ROT  {test.name} — volle Ausgabe:")
        print(lauf.stdout)

if kurz:
    print(f"\n{len(dateien)} Testdateien, {checks_gesamt} Checks.")
print(f"{'ALLE TESTS GRUEN' if fehl == 0 else f'{fehl} TESTDATEI(EN) ROT'}")
sys.exit(1 if fehl else 0)
