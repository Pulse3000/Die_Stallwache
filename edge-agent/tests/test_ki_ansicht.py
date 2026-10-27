#!/usr/bin/env python3
"""Logiktest: KI-Ansicht als Live-Kaesten (docs/ki-ansicht-spezifikation.md,
Kriterium 1).

Die Zusagen: Der Agent schreibt die Kaesten der letzten Analyse als kleine
JSON-Datei, Koordinaten relativ zum Bild (0..1, auf das Bild begrenzt).
Kuehe nur mit Track-Nummer (-1 faellt weg), mit Schwanzwinkel wenn gueltig.
Fruchtblase/Kaelberfuesse ab 0.25; „alarm“ nach derselben Regel wie
LogicEngine.bewerte (>= override_konfidenz), Prozent abgerundet (0.7996 ->
79, nie 80 ohne Alarm). Geschrieben wird atomar (temporaere Datei, dann
os.replace), lesbar fuer andere Benutzer, mit der Aufnahmezeit des Bilds.
Ein Schreibfehler stoppt nichts und loggt hoechstens einmal je Stunde. Ohne
Pfad aus; im Silent Mode nie aufgerufen; Aufruf erst nach den Alarmen.
Ohne cv2/numpy.
"""

import json
import logging
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import MAIN_PY, Pruefer, lade_main  # noqa: E402

m, _ = lade_main()
p = Pruefer("KI-Ansicht")


class Bild:
    def __init__(self, h: int, w: int):
        self.shape = (h, w, 3)


Kuh = m.KuhBeobachtung
Objekt = m.ObjektErkennung
kuehe = [Kuh(12, (480.0, 270.0, 960.0, 810.0), 52.44, None),
         Kuh(7, (1000.0, 100.0, 2000.0, 500.0), None, None),   # ragt rechts heraus
         Kuh(-1, (1500.0, 100.0, 1800.0, 400.0), None, None)]
objekte = [Objekt("amniotic_sac", 0.913, (300.0, 400.0, 400.0, 500.0)),
           Objekt("calf_legs", 0.7996, (300.0, 400.0, 400.0, 500.0)),
           Objekt("calf_legs", 0.249, (0.0, 0.0, 10.0, 10.0))]

# --- 1. Aus ohne Pfad --------------------------------------------------------
os.environ.pop("KI_ANSICHT_DATEI", None)
p.check("1: ohne Pfad aus", not m.KiAnsicht({}, "stallwache").aktiv)
p.check("1: leerer Pfad aus", not m.KiAnsicht({"ki_ansicht": {"datei": ""}}, "x").aktiv)
os.environ["KI_ANSICHT_DATEI"] = "/tmp/ki.json"
p.check("1: Pfad aus der Umgebung", m.KiAnsicht({}, "x").datei == Path("/tmp/ki.json"))
p.check("1: config.yaml hat Vorrang",
        m.KiAnsicht({"ki_ansicht": {"datei": "/a/b.json"}}, "x").datei == Path("/a/b.json"))
os.environ.pop("KI_ANSICHT_DATEI", None)
p.check("1: kein Abschnitt in config.yaml -> ignoriert statt Absturz",
        m.KiAnsicht({"ki_ansicht": "/pfad.json"}, "x").datei is None)
p.check("1: aus -> schreibe tut nichts",
        m.KiAnsicht({}, "x").schreibe(Bild(1080, 1920), kuehe, objekte) is False)

# --- 2. Inhalt ------------------------------------------------------------------
ka = m.KiAnsicht({"ki_ansicht": {"datei": "/tmp/x.json"}}, "stallwache", 0.80)
d = ka.daten(1920, 1080, kuehe, objekte, 1761577200.1234)
p.check("2: Kopf", (d["v"], d["kamera"], d["zeit"], d["breite"], d["hoehe"], d["alarm_ab"])
        == (1, "stallwache", 1761577200.12, 1920, 1080, 0.80))
p.check("2: Kuh #12 relativ, mit Winkel",
        d["kuehe"][0] == {"id": 12, "box": [0.25, 0.25, 0.5, 0.75], "winkel": 52.4})
p.check("2: Kuh #7 ohne Winkel, Kasten auf das Bild begrenzt",
        d["kuehe"][1] == {"id": 7, "box": [0.5208, 0.0926, 1.0, 0.463], "winkel": None})
p.check("2: Kuh ohne Nummer (-1) faellt weg", [k["id"] for k in d["kuehe"]] == [12, 7])
p.check("2: Fruchtblase 0.913 -> 91, Alarm",
        d["objekte"][0] == {"klasse": "amniotic_sac", "box": [0.1562, 0.3704, 0.2083, 0.463],
                            "prozent": 91, "alarm": True})
p.check("2: Kaelberfuesse 0.7996 -> 79, kein Alarm (nie 80 ohne Alarm)",
        (d["objekte"][1]["prozent"], d["objekte"][1]["alarm"]) == (79, False))
p.check("2: unter 0.25 nicht angezeigt", len(d["objekte"]) == 2)
d = ka.daten(100, 100, [], [Objekt("amniotic_sac", 0.80, (0, 0, 1, 1)),
                            Objekt("amniotic_sac", 0.25, (0, 0, 1, 1))], 0)
p.check("2: genau 0.80 -> Alarm, genau 0.25 -> angezeigt",
        [(o["prozent"], o["alarm"]) for o in d["objekte"]] == [(80, True), (25, False)])
d = m.KiAnsicht({}, "x", 0.9).daten(100, 100, [], [Objekt("calf_legs", 0.85, (0, 0, 1, 1))], 0)
p.check("2: Schwelle aus der Logik (override_konfidenz 0.9)",
        d["alarm_ab"] == 0.9 and d["objekte"][0]["alarm"] is False)
quelle = MAIN_PY.read_text(encoding="utf-8")
p.check("2: main() reicht logik.override_konf an die KI-Ansicht",
        "KiAnsicht(cfg, notifier.kamera, logik.override_konf)" in quelle
        and "o.konfidenz >= self.override_konf" in quelle)

# --- 3. Atomar schreiben ---------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    ziel = Path(tmp) / "unter" / "ki-kaesten.json"
    ka = m.KiAnsicht({"ki_ansicht": {"datei": str(ziel)}}, "stallwache")
    ersetzt = []
    echtes_replace = m.os.replace

    def merke_replace(a, b):
        ersetzt.append((Path(a), Path(b), Path(a).exists()))
        echtes_replace(a, b)

    m.os.replace = merke_replace
    try:
        ok = ka.schreibe(Bild(1080, 1920), kuehe, objekte, zeit=1761577200.5)
    finally:
        m.os.replace = echtes_replace
    inhalt = json.loads(ziel.read_text(encoding="utf-8"))
    p.check("3: geschrieben, Ordner angelegt, gueltiges JSON",
            ok and inhalt["zeit"] == 1761577200.5 and len(inhalt["kuehe"]) == 2)
    p.check("3: Breite/Hoehe aus dem Bild", (inhalt["breite"], inhalt["hoehe"]) == (1920, 1080))
    p.check("3: klein (< 1 KB bei 2 Kuehen, 2 Objekten)", ziel.stat().st_size < 1024)
    p.check("3: ueber temporaere Datei im selben Ordner ersetzt",
            ersetzt == [(ziel.with_name("ki-kaesten.json.tmp"), ziel, True)])
    p.check("3: keine temporaere Datei bleibt liegen", not ziel.with_name("ki-kaesten.json.tmp").exists())
    p.check("3: lesbar fuer andere Benutzer (fern-proxy)", stat.S_IMODE(ziel.stat().st_mode) == 0o644)

# --- 4. Fehler stoppen nichts, hoechstens eine Warnung je Stunde ----------------
class Zaehler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.n = 0

    def emit(self, record):
        if "KI-Ansicht" in record.getMessage():
            self.n += 1


zaehler = Zaehler()
m.log.addHandler(zaehler)
with tempfile.NamedTemporaryFile() as datei:
    # Ordner ist eine Datei -> mkdir scheitert
    ka = m.KiAnsicht({"ki_ansicht": {"datei": datei.name + "/ki.json"}}, "x")
    uhr = [1000.0]
    echte_zeit = m.time.time
    m.time.time = lambda: uhr[0]
    try:
        ergebnisse = [ka.schreibe(Bild(480, 640), kuehe, []) for _ in range(5)]
        p.check("4: Schreibfehler -> False, keine Ausnahme", ergebnisse == [False] * 5)
        p.check("4: 5 Fehler -> 1 Warnung", zaehler.n == 1)
        uhr[0] += 3600
        ka.schreibe(Bild(480, 640), kuehe, [])
        p.check("4: nach einer Stunde wieder 1 Warnung", zaehler.n == 2)
    finally:
        m.time.time = echte_zeit
m.log.removeHandler(zaehler)

# --- 5. Nur im Analyse-Modus, nach den Alarmen, mit Aufnahmezeit ---------------
haupt = quelle[quelle.index("def main() -> None:"):]
silent = haupt.index("if not engine.aktiv:")
analyse = haupt.index("kuehe, objekte = engine.analysiere(frame)")
alarme = haupt.index("notifier.melde(alarm, frame")
schreiben = haupt.index("ki_ansicht.schreibe(")
p.check("5: Aufruf nach der Analyse und nach den Alarmen", silent < analyse < alarme < schreiben)
p.check("5: Silent-Mode-Zweig ruft die KI-Ansicht nicht auf", "ki_ansicht" not in haupt[silent:analyse])
p.check("5: Aufnahmezeit des Bilds wird mitgegeben",
        "ki_ansicht.schreibe(frame, kuehe, objekte, letztes_bild)" in haupt)

# --- 6. Compose: RAM-Ordner und Pfad -------------------------------------------
compose = (MAIN_PY.parent / "docker-compose.yml").read_text(encoding="utf-8")
p.check("6: Compose bindet /dev/shm/stallwache-<kamera> ein",
        "/dev/shm/stallwache-${KAMERA:-stallwache}:/ki-ansicht" in compose)
p.check("6: Compose setzt KI_ANSICHT_DATEI (abschaltbar mit leerem Wert)",
        "KI_ANSICHT_DATEI=${KI_ANSICHT_DATEI-/ki-ansicht/ki-kaesten.json}" in compose)

sys.exit(p.bericht())
