#!/usr/bin/env python3
"""Logiktest: KI-Ansicht (docs/ki-ansicht-spezifikation.md, Kriterium 1).

Die Zusagen: Jede Kuh bekommt einen gruenen Kasten mit „Kuh #ID“ (und dem
Schwanzwinkel, wenn gueltig), Fruchtblase/Kaelberfuesse einen roten mit
Konfidenz; das Bild wird erst auf 960 px verkleinert, dann gezeichnet.
Geschrieben wird atomar (temporaere Datei, dann os.replace), lesbar fuer
andere Benutzer. Ein Schreibfehler stoppt nichts und loggt hoechstens
einmal je Stunde. Ohne Pfad ist die KI-Ansicht aus; im Silent Mode wird sie
nie aufgerufen. Ohne cv2/numpy (nachgebildet).
"""

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

    def copy(self):
        return Bild(*self.shape[:2])


class Jpg:
    def tobytes(self) -> bytes:
        return b"\xff\xd8JPEG\xff\xd9"


class FalschesCv2:
    FONT_HERSHEY_SIMPLEX = 0
    INTER_AREA = 3
    IMWRITE_JPEG_QUALITY = 1

    def __init__(self, kodieren_ok: bool = True):
        self.aufrufe: list[tuple] = []
        self.kodieren_ok = kodieren_ok

    def resize(self, bild, groesse, interpolation=None):
        self.aufrufe.append(("resize", groesse))
        return Bild(groesse[1], groesse[0])

    def rectangle(self, bild, p1, p2, farbe, dicke):
        self.aufrufe.append(("rect", p1, p2, farbe))

    def putText(self, bild, text, ort, schrift, groesse, farbe, dicke):  # noqa: N802
        self.aufrufe.append(("text", text, ort, farbe))

    def imencode(self, endung, bild, parameter):
        self.aufrufe.append(("encode", endung, tuple(parameter)))
        return self.kodieren_ok, Jpg()


Kuh = m.KuhBeobachtung
Objekt = m.ObjektErkennung
kuehe = [Kuh(12, (100.0, 200.0, 500.0, 600.0), 52.4, None),
         Kuh(7, (1000.0, 100.0, 1400.0, 500.0), None, None)]
objekte = [Objekt("amniotic_sac", 0.913, (300.0, 400.0, 400.0, 500.0))]

# --- 1. Aus ohne Pfad --------------------------------------------------------
os.environ.pop("KI_ANSICHT_DATEI", None)
p.check("1: ohne Pfad aus", not m.KiAnsicht({}, "stallwache").aktiv)
p.check("1: leerer Pfad aus", not m.KiAnsicht({"ki_ansicht": {"datei": ""}}, "x").aktiv)
os.environ["KI_ANSICHT_DATEI"] = "/tmp/ki.jpg"
p.check("1: Pfad aus der Umgebung", m.KiAnsicht({}, "x").datei == Path("/tmp/ki.jpg"))
p.check("1: config.yaml hat Vorrang",
        m.KiAnsicht({"ki_ansicht": {"datei": "/a/b.jpg"}}, "x").datei == Path("/a/b.jpg"))
os.environ.pop("KI_ANSICHT_DATEI", None)
p.check("1: aus -> schreibe tut nichts", m.KiAnsicht({}, "x").schreibe(Bild(1080, 1920), kuehe, objekte) is False)

# --- 2. Zeichnen ---------------------------------------------------------------
cv = FalschesCv2()
m.cv2 = cv
ka = m.KiAnsicht({"ki_ansicht": {"datei": "/tmp/x.jpg"}}, "stallwache")
erg = ka.zeichne(Bild(1080, 1920), kuehe, objekte, zeit=0)
p.check("2: erst auf 960 px verkleinert", cv.aufrufe[0] == ("resize", (960, 540)) and erg.shape[1] == 960)
texte = [a for a in cv.aufrufe if a[0] == "text"]
kaesten = [a for a in cv.aufrufe if a[0] == "rect"]
p.check("2: Kuh #12 mit Winkel, gruen", ("text", "Kuh #12 52 Grad", (53, 94), m.KiAnsicht.KUH) in texte)
p.check("2: Kuh #7 ohne Winkel", any(t[1] == "Kuh #7" for t in texte))
p.check("2: Kasten auf 960 px umgerechnet", ("rect", (50, 100), (250, 300), m.KiAnsicht.KUH) in kaesten)
p.check("2: Fruchtblase rot mit Konfidenz",
        any(t[1] == "Fruchtblase 0.91" and t[3] == m.KiAnsicht.OBJEKT for t in texte))
p.check("2: Stempel mit Kamera und Uhrzeit",
        any(t[1].startswith("stallwache ") and len(t[1].split()[1]) == 8 for t in texte))
p.check("2: Beschriftung nur ASCII (Hershey-Schrift)", all(t[1].isascii() for t in texte))
cv.aufrufe.clear()
ka.zeichne(Bild(480, 640), kuehe[:1], [], zeit=0)
p.check("2: kleines Bild wird nicht vergroessert", not any(a[0] == "resize" for a in cv.aufrufe))
p.check("2: Kasten unveraendert bei Faktor 1", ("rect", (100, 200), (500, 600), m.KiAnsicht.KUH) in cv.aufrufe)
p.check("2: Text nie ueber den Bildrand", ("text", "Kuh #12 52 Grad", (103, 194), m.KiAnsicht.KUH) in cv.aufrufe)
cv.aufrufe.clear()
ka.zeichne(Bild(480, 640), [Kuh(3, (10.0, 5.0, 50.0, 50.0), None, None)], [], zeit=0)
p.check("2: Kasten am oberen Rand -> Text bei y >= 18",
        any(a[0] == "text" and a[1] == "Kuh #3" and a[2][1] == 18 for a in cv.aufrufe))

# --- 3. Atomar schreiben ---------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    ziel = Path(tmp) / "unter" / "ki-ansicht.jpg"
    ka = m.KiAnsicht({"ki_ansicht": {"datei": str(ziel)}}, "stallwache")
    ersetzt = []
    echtes_replace = m.os.replace

    def merke_replace(a, b):
        ersetzt.append((Path(a), Path(b), Path(a).exists()))
        echtes_replace(a, b)

    m.os.replace = merke_replace
    try:
        ok = ka.schreibe(Bild(1080, 1920), kuehe, objekte)
    finally:
        m.os.replace = echtes_replace
    p.check("3: geschrieben, Ordner angelegt", ok and ziel.read_bytes() == Jpg().tobytes())
    p.check("3: ueber temporaere Datei im selben Ordner ersetzt",
            ersetzt == [(ziel.with_name("ki-ansicht.jpg.tmp"), ziel, True)])
    p.check("3: keine temporaere Datei bleibt liegen", not ziel.with_name("ki-ansicht.jpg.tmp").exists())
    p.check("3: lesbar fuer andere Benutzer (fern-proxy)", stat.S_IMODE(ziel.stat().st_mode) == 0o644)
    p.check("3: JPEG-Qualitaet 70", ("encode", ".jpg", (1, 70)) in cv.aufrufe)

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
    ka = m.KiAnsicht({"ki_ansicht": {"datei": datei.name + "/ki.jpg"}}, "x")
    uhr = [1000.0]
    echte_zeit = m.time.time
    m.time.time = lambda: uhr[0]
    try:
        ergebnisse = []
        for _ in range(5):
            ergebnisse.append(ka.schreibe(Bild(480, 640), kuehe, []))
        p.check("4: Schreibfehler -> False, keine Ausnahme", ergebnisse == [False] * 5)
        p.check("4: 5 Fehler -> 1 Warnung", zaehler.n == 1)
        uhr[0] += 3600
        ka.schreibe(Bild(480, 640), kuehe, [])
        p.check("4: nach einer Stunde wieder 1 Warnung", zaehler.n == 2)
    finally:
        m.time.time = echte_zeit
m.cv2 = FalschesCv2(kodieren_ok=False)
with tempfile.TemporaryDirectory() as tmp:
    ka = m.KiAnsicht({"ki_ansicht": {"datei": str(Path(tmp) / "k.jpg")}}, "x")
    p.check("4: Kodierfehler -> False, keine Datei",
            ka.schreibe(Bild(480, 640), kuehe, []) is False and not (Path(tmp) / "k.jpg").exists())
m.log.removeHandler(zaehler)

# --- 5. Nur im Analyse-Modus, nach den Alarmen -------------------------------
quelle = MAIN_PY.read_text(encoding="utf-8")
haupt = quelle[quelle.index("def main() -> None:"):]
silent = haupt.index("if not engine.aktiv:")
analyse = haupt.index("kuehe, objekte = engine.analysiere(frame)")
alarme = haupt.index("notifier.melde(alarm, frame")
schreiben = haupt.index("ki_ansicht.schreibe(")
p.check("5: Aufruf nach der Analyse und nach den Alarmen", silent < analyse < alarme < schreiben)
silent_block = haupt[silent:analyse]
p.check("5: Silent-Mode-Zweig ruft die KI-Ansicht nicht auf", "ki_ansicht" not in silent_block)

# --- 6. Compose: RAM-Ordner und Pfad -------------------------------------------
compose = (MAIN_PY.parent / "docker-compose.yml").read_text(encoding="utf-8")
p.check("6: Compose bindet /dev/shm/stallwache-<kamera> ein",
        "/dev/shm/stallwache-${KAMERA:-stallwache}:/ki-ansicht" in compose)
p.check("6: Compose setzt KI_ANSICHT_DATEI", "KI_ANSICHT_DATEI=/ki-ansicht/ki-ansicht.jpg" in compose)

sys.exit(p.bericht())
