#!/usr/bin/env python3
"""B20-Abnahme an echten Stallbildern: defekt_anteil im Agenten ist woertlich
die kalibrierte Funktion aus bildqualitaet.py und klassifiziert Stallbilder im
Agentenpfad (Vollbild BGR, INTER_AREA) genauso wie im Kalibrierpfad (JPEG in
1/4-Aufloesung, Graustufen) und wie die Aussortier-Liste. Braucht numpy,
OpenCV, bildqualitaet.py, die _cvat_v1-Listen und die Bilder (Hof-Rechner);
fehlt etwas: 77 = uebersprungen. Pfad ueberschreibbar mit STALLWACHE_BILDQUALITAET."""

import ast
import csv
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import UEBERSPRUNGEN, Pruefer, braucht, lade_main  # noqa: E402

braucht("numpy", "cv2")
import cv2  # noqa: E402

AGENT = Path(__file__).resolve().parent.parent
AUFNAHMEN = AGENT / "aufnahmen"
BQ = Path(os.environ.get("STALLWACHE_BILDQUALITAET", AUFNAHMEN / "_training_v1" / "werkzeuge" / "bildqualitaet.py"))
LISTE_DEF = AUFNAHMEN / "_cvat_v1" / "ausgeschlossen_defekt.csv"
LISTE_OK = AUFNAHMEN / "_cvat_v1" / "manifest.csv"
fehlt = [str(x) for x in (BQ, LISTE_DEF, LISTE_OK) if not x.is_file()]
if fehlt:
    print("UEBERSPRUNGEN: " + ", ".join(fehlt) + " fehlt (nur am Hof-Rechner)")
    sys.exit(UEBERSPRUNGEN)

m, _ = lade_main()
p = Pruefer("Bildqualitaet an Stallbildern (B20)")
spec = importlib.util.spec_from_file_location("bildqualitaet_ref", BQ)
ref = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ref)


def knoten(pfad, name):
    for k in ast.parse(Path(pfad).read_text(encoding="utf-8")).body:
        if isinstance(k, ast.FunctionDef) and k.name == name:
            return ast.dump(k)
    return None


p.check("defekt_anteil: Funktionskoerper identisch mit bildqualitaet.py",
        knoten(m.__file__, "defekt_anteil") == knoten(BQ, "defekt_anteil") is not None)
p.check("Zellgroesse gleich (40)", m.ZELLE == ref.ZELLE)
p.check("Konfig-Default = kalibrierte Schwelle", m.BildQualitaet({}).schwelle == ref.SCHWELLE_DEFEKT == 0.04)

with LISTE_DEF.open(encoding="utf-8") as f:
    defekte = [r["datei"] for r in csv.DictReader(f)][::25][:12]
with LISTE_OK.open(encoding="utf-8") as f:
    intakte = [r["datei"] for r in csv.DictReader(f) if float(r["defekt_anteil"]) == 0.0][::150][:12]
q = m.BildQualitaet({})
gleich, n, falsch = 0, 0, []
for name, soll in [(x, True) for x in defekte] + [(x, False) for x in intakte]:
    voll = cv2.imread(str(AUFNAHMEN / name))
    klein = cv2.imread(str(AUFNAHMEN / name), cv2.IMREAD_REDUCED_GRAYSCALE_4)
    if voll is None or klein is None:
        continue
    n += 1
    agent, kalib = q.pruefe(voll)[0], m.defekt_anteil(klein) > q.schwelle
    gleich += agent == kalib == soll
    if not agent == kalib == soll:
        falsch.append(f"{name}: Agent {agent}, Kalibrierpfad {kalib}, Liste {soll}")
for zeile in falsch:
    print("ABWEICHUNG", zeile)
p.check(f"{n} echte Stallbilder (mind. 20): Agentenpfad == Kalibrierpfad == Liste", n >= 20 and gleich == n)

sys.exit(p.bericht())
