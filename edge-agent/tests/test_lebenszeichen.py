#!/usr/bin/env python3
"""Logiktests Lebenszeichen an die App (Grundlage der Statusabfrage).

Geprueft wird die Zusage aus docs/statusabfrage-spezifikation.md
(Abnahmekriterien 15 und 24): Das Lebenszeichen nennt Kamera, Modus und
Bildzustand, haelt sein Intervall ein, meldet Zustandswechsel frueher, und
ein toter oder haengender Uplink blockiert die Hauptschleife nie. Dazu die
Zahl der Trainingsbilder im Silent-Mode-Ordner, gezaehlt im Sende-Thread. HTTP ist
komplett gestubbt — es geht nie ein echter Request raus.
"""

import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Lebenszeichen")

URL = "https://beispiel.test/api/events"


def lz(**db):
    cfg = {
        "stream": {"kamera": "futterwache"},
        "dashboard": {"url": URL, "token": "T", **db},
    }
    return m.Lebenszeichen(cfg)


def warte(l):
    if l._thread is not None:
        l._thread.join(2)


def netz_an():
    antwort = type("A", (), {"raise_for_status": staticmethod(lambda: None)})()
    m.requests.post = lambda url, **kw: (gesendet.append((url, kw)), antwort)[1]


netz_an()

# --- 1. Ohne Dashboard-Ziel oder mit 0 Minuten: nichts ---------------------
gesendet.clear()
ohne = m.Lebenszeichen({"stream": {}, "dashboard": {"url": "", "token": "T"}})
ohne_token = m.Lebenszeichen({"stream": {}, "dashboard": {"url": URL, "token": ""}})
aus = lz(lebenszeichen_minuten=0)
p.check("ohne URL: inaktiv, sendet nichts", not ohne.aktiv and ohne.tick(True, True, 0) is False)
p.check("ohne Token: inaktiv", not ohne_token.aktiv and ohne_token.tick(True, True, 0) is False)
p.check("lebenszeichen_minuten 0: aus", not aus.aktiv and aus.tick(True, True, 0) is False)
p.check("ohne dashboard-Abschnitt: inaktiv", not m.Lebenszeichen({"stream": {}}).aktiv)
p.check("nichts gesendet", gesendet == [])

# --- 2. Erstes Lebenszeichen sofort, mit Vertragsfeldern -------------------
gesendet.clear()
l = lz()
p.check("Default-Intervall 5 min", l.intervall_s == 300)
p.check("erster Tick sendet", l.tick(True, True, 1000.0) is True)
warte(l)
url, kw = gesendet[0]
p.check("an die Ingest-URL", url == URL)
p.check("mit Ingest-Token", kw["headers"] == {"x-ingest-token": "T"})
p.check("kurzer Timeout (<= 10 s)", kw["timeout"] <= 10)
p.check(
    "leerer Stapel + Kamera/Modus/Bild",
    kw["json"]
    == {
        "ereignisse": [],
        "lebenszeichen": {"kamera": "futterwache", "modus": "analyse", "bild": True},
    },
)

# --- 3. Intervall wird eingehalten ----------------------------------------
gesendet.clear()
p.check("nach 60 s gleicher Zustand: nichts", l.tick(True, True, 1060.0) is False)
p.check("nach 299 s: nichts", l.tick(True, True, 1299.0) is False)
p.check("nach 300 s: senden", l.tick(True, True, 1300.0) is True)
warte(l)
p.check("genau ein Versand", len(gesendet) == 1)

# --- 4. Zustandswechsel frueher, aber nicht oefter als alle 30 s ----------
gesendet.clear()
p.check("Bild weg nach 10 s: noch nicht", l.tick(True, False, 1310.0) is False)
p.check("Bild weg nach 30 s: senden", l.tick(True, False, 1330.0) is True)
warte(l)
p.check("meldet bild=false", gesendet[-1][1]["json"]["lebenszeichen"]["bild"] is False)
gesendet.clear()
p.check("unveraendert danach: nichts", l.tick(True, False, 1400.0) is False)
s = lz()
s.tick(False, True, 0.0)
warte(s)
p.check("Silent Mode heisst modus=silent", gesendet[-1][1]["json"]["lebenszeichen"]["modus"] == "silent")

# --- 5. Netzfehler wirft nicht, Stoerung wird nur einmal gezaehlt geloggt --
def wirft(url, **kw):
    raise m.requests.RequestException("kein Netz")


m.requests.post = wirft
f = lz()
ok = True
try:
    f.tick(True, True, 0.0)
    warte(f)
    f.tick(True, True, 300.0)
    warte(f)
except Exception:  # noqa: BLE001
    ok = False
p.check("Netzfehler wirft nicht", ok)
p.check("Fehler werden gezaehlt", f.fehler_in_folge == 2)
netz_an()
f.tick(True, True, 600.0)
warte(f)
p.check("nach Erholung zurueckgesetzt", f.fehler_in_folge == 0)


# --- 6. Haengender Uplink blockiert die Schleife nicht --------------------
frei = threading.Event()


def haengt(url, **kw):
    frei.wait(5)
    raise m.requests.RequestException("Timeout")


m.requests.post = haengt
h = lz()
start = time.monotonic()
h.tick(True, True, 0.0)
dauer = time.monotonic() - start
p.check("Tick kehrt sofort zurueck (< 0.5 s)", dauer < 0.5)
p.check("haengender Versand: kein zweiter Thread", h.tick(True, True, 400.0) is False)
frei.set()
warte(h)
netz_an()
p.check("nach Ende des Versands wieder moeglich", h.tick(True, True, 800.0) is True)
warte(h)

# --- 7. Fehler beim Thread-Start stoert die Schleife nicht -----------------
kaputt = lz()
original = m.threading.Thread


class KaputterThread:
    def __init__(self, *a, **kw):
        raise RuntimeError("keine Threads mehr")


m.threading.Thread = KaputterThread
try:
    p.check("Thread-Startfehler -> False statt Ausnahme", kaputt.tick(True, True, 0.0) is False)
finally:
    m.threading.Thread = original

# --- 8. Trainingsbilder im Silent-Mode-Ordner (Kriterium 24) --------------
netz_an()
with tempfile.TemporaryDirectory() as tmp:
    ordner = Path(tmp) / "aufnahmen"
    ordner.mkdir()
    for name in ("stallwache_20261025-080000.jpg", "stallwache_20261025-080200.JPG",
                 "stallwache_20261025-080400.jpg", "notiz.txt", "labels.json"):
        (ordner / name).write_bytes(b"x")
    (ordner / "unterordner.jpg").mkdir()  # Ordner mit .jpg-Namen zaehlt nicht
    (ordner / "tiefer").mkdir()
    (ordner / "tiefer" / "nicht_rekursiv.jpg").write_bytes(b"x")

    def mit_ordner(pfad):
        return m.Lebenszeichen({
            "stream": {"kamera": "stallwache"},
            "dashboard": {"url": URL, "token": "T"},
            "silent_mode": {"ordner": str(pfad)},
        })

    gesendet.clear()
    t = mit_ordner(ordner)
    p.check("Ordner aus silent_mode.ordner", t.ordner == ordner)
    p.check("zaehlt nur *.jpg-Dateien, nicht rekursiv", t.zaehle_trainingsbilder() == 3)
    p.check("Versand startet", t.tick(False, True, 0.0) is True)
    warte(t)
    p.check(
        "Lebenszeichen traegt trainingsbilder",
        gesendet[-1][1]["json"]["lebenszeichen"]
        == {"kamera": "stallwache", "modus": "silent", "bild": True, "trainingsbilder": 3},
    )

    # Zaehlen im Sende-Thread, nicht beim Tick: ein neues Bild zwischen zwei
    # Lebenszeichen steht im naechsten Versand.
    (ordner / "stallwache_20261025-080600.jpg").write_bytes(b"x")
    gesendet.clear()
    p.check("naechstes Lebenszeichen", t.tick(False, True, 400.0) is True)
    warte(t)
    p.check("neue Zahl", gesendet[-1][1]["json"]["lebenszeichen"]["trainingsbilder"] == 4)

    gesendet.clear()
    fehlt = mit_ordner(Path(tmp) / "gibt-es-nicht")
    p.check("fehlender Ordner -> None", fehlt.zaehle_trainingsbilder() is None)
    fehlt.tick(False, True, 0.0)
    warte(fehlt)
    p.check("fehlender Ordner -> Feld fehlt, Versand trotzdem",
            len(gesendet) == 1 and "trainingsbilder" not in gesendet[-1][1]["json"]["lebenszeichen"])

    original_scandir = m.os.scandir

    def scandir_kaputt(_):
        raise PermissionError("kein Zugriff")

    m.os.scandir = scandir_kaputt
    try:
        gesendet.clear()
        k = mit_ordner(ordner)
        p.check("Lesefehler -> None statt Ausnahme", k.zaehle_trainingsbilder() is None)
        k.tick(False, True, 0.0)
        warte(k)
        p.check("Lesefehler blockiert den Versand nicht", len(gesendet) == 1)
    finally:
        m.os.scandir = original_scandir

sys.exit(p.bericht())
