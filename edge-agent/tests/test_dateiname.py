#!/usr/bin/env python3
"""B21-Abnahme: Silent-Mode-Dateiname <kamera>_<YYYYmmdd-HHMMSS>.jpg in UTC
(auch wenn der Rechner auf Europe/Berlin steht), Kameraname bereinigt; die
Werkzeuge lesen Datum/Uhrzeit mit und ohne Praefix. Pures Python; die
Werkzeuge werden geprueft, wo sie liegen (Trainingsordner, Goal-Vorlage)."""

import calendar
import datetime as dt
import importlib.util
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main  # noqa: E402

os.environ["TZ"] = "Europe/Berlin"  # Ortszeit != UTC: der Name muss trotzdem UTC sein
if hasattr(time, "tzset"):
    time.tzset()

m, _ = lade_main()
p = Pruefer("Silent-Mode-Dateiname (B21)")

AGENT = Path(__file__).resolve().parent.parent
REPO = AGENT.parent
T = calendar.timegm((2026, 11, 2, 3, 15, 0))       # 03:15 UTC = 04:15 Ortszeit
MUSTER = re.compile(r"^[a-z][a-z0-9]*_\d{8}-\d{6}\.jpg$")

name = m.silent_dateiname("stallwache", T)
p.check("Format <kamera>_<YYYYmmdd-HHMMSS>.jpg", name == "stallwache_20261102-031500.jpg")
p.check("UTC trotz TZ=Europe/Berlin (Ortszeit waere 041500)", "031500" in name and "041500" not in name)
p.check("Namensmuster", MUSTER.match(name) is not None)
p.check("Kameraname bereinigt (Leer-/Sonderzeichen, gross)",
        m.silent_dateiname("Stall Wache/../1", T) == "stallwache1_20261102-031500.jpg")
p.check("leerer Kameraname -> 'kamera'", m.silent_dateiname("", T) == "kamera_20261102-031500.jpg")
p.check("Kameraname mit Ziffer vorn -> beginnt mit Buchstaben",
        MUSTER.match(m.silent_dateiname("2cam", T)) is not None)

ALT = "20261102-031500.jpg"   # Altbestand ohne Praefix


def lade(pfad: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, pfad)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # noetig fuer @dataclass-Introspektion
    spec.loader.exec_module(mod)
    return mod


werkzeuge = AGENT / "aufnahmen" / "_training_v1" / "werkzeuge"
for datei in ("cvat_zu_yolo_pose.py", "abnahme_gates.py"):
    pfad = werkzeuge / datei
    if not pfad.is_file():
        print(f"HINWEIS: {pfad} fehlt (nur am Hof-Rechner)")
        continue
    mod = lade(pfad, datei[:-3] + "_ref")
    a, b = mod.stalltag(name), mod.stalltag(ALT)
    p.check(f"{datei}: Stalltag mit und ohne Praefix gleich ({a})", a == b == "2026-11-01")

sichtung = lade(AGENT / "stall_sichtung.py", "stall_sichtung_ref")
p.check("stall_sichtung.py: Zeit aus Name mit und ohne Praefix gleich",
        sichtung.NAME_ZEIT.search(name).groups() == sichtung.NAME_ZEIT.search(ALT).groups())

inventur = REPO / "goal_vorlagen" / "stallwache-goalpaket-2026-10-16" / "datensatz_inventur.py"
if inventur.is_file():
    inv = lade(inventur, "datensatz_inventur_ref")
    soll = dt.datetime(2026, 11, 2, 3, 15, 0)
    p.check("datensatz_inventur.py: neues Format -> (stallwache, Zeit)",
            inv.zeit_aus_dateiname(name) == ("stallwache", soll))
    p.check("datensatz_inventur.py: Altbestand ohne Praefix -> (unbekannt, Zeit)",
            inv.zeit_aus_dateiname(ALT) == ("unbekannt", soll))
    p.check("datensatz_inventur.py: Fremdname bleibt None", inv.zeit_aus_dateiname("IMG_0042.jpg") is None)

sys.exit(p.bericht())
