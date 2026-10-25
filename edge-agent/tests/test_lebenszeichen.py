#!/usr/bin/env python3
"""Logiktests Lebenszeichen an die App (Grundlage der Statusabfrage).

Geprueft wird die Zusage aus docs/statusabfrage-spezifikation.md
(Abnahmekriterien 15, 24 und 24a): Das Lebenszeichen nennt Kamera, Modus
und Bildzustand, haelt sein Intervall ein, meldet Zustandswechsel frueher,
und ein toter oder haengender Uplink blockiert die Hauptschleife nie. Im
Silent Mode dazu der Bildbestand der Kamera, gezaehlt im Sende-Thread; im
Analyse-Modus wird nie gezaehlt. HTTP ist
komplett gestubbt — es geht nie ein echter Request raus.
"""

import datetime as dt
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

# --- 8. Bildbestand im Silent Mode (Kriterien 24, 24a) --------------------
netz_an()
JETZT = time.time()
with tempfile.TemporaryDirectory() as tmp:
    ordner = Path(tmp) / "aufnahmen"
    ordner.mkdir()
    eigene = [JETZT - 3 * 86400, JETZT - 2 * 3600, JETZT - 600]  # 1 alt, 2 juenger als 24 h
    for t in eigene:
        (ordner / m.trainingsbild_name("stallwache", t)).write_bytes(b"x")
    (ordner / m.trainingsbild_name("futterwache", JETZT)).write_bytes(b"x")  # andere Kamera
    for fremd in ("screenshot.jpg", "stallwache_export.jpg", "notiz.txt"):
        (ordner / fremd).write_bytes(b"x")
    (ordner / m.trainingsbild_name("stallwache", JETZT - 60)).mkdir()  # Ordner, keine Datei
    (ordner / "tiefer").mkdir()
    (ordner / "tiefer" / m.trainingsbild_name("stallwache", JETZT)).write_bytes(b"x")

    def mit_ordner(pfad, kamera="stallwache"):
        return m.Lebenszeichen({
            "stream": {"kamera": kamera},
            "dashboard": {"url": URL, "token": "T"},
            "silent_mode": {"ordner": str(pfad)},
        })

    t = mit_ordner(ordner)
    b = t.bildbestand(JETZT)
    p.check("Ordner aus silent_mode.ordner", t.ordner == ordner)
    p.check("zaehlt nur eigene Bilder (Praefix, Zeitstempel, Datei, nicht rekursiv)",
            b is not None and b["trainingsbilder"] == 3)
    p.check("davon juenger als 24 h", b["trainingsbilder_24h"] == 2)
    erwartet = dt.datetime.fromtimestamp(int(JETZT - 600), dt.timezone.utc).isoformat().replace("+00:00", "Z")
    p.check("juengstes Bild als UTC-Zeit aus dem Dateinamen", b.get("trainingsbild_zuletzt") == erwartet)
    p.check("andere Kamera zaehlt ihre eigenen", mit_ordner(ordner, "futterwache").bildbestand(JETZT)["trainingsbilder"] == 1)

    gesendet.clear()
    p.check("Versand startet (Silent)", t.tick(False, True, 0.0) is True)
    warte(t)
    lzs = gesendet[-1][1]["json"]["lebenszeichen"]
    p.check("Lebenszeichen traegt den Bildbestand",
            lzs["modus"] == "silent" and lzs["trainingsbilder"] == 3
            and lzs["trainingsbilder_24h"] == 2 and lzs["trainingsbild_zuletzt"] == erwartet)

    # Gezaehlt wird beim Versand, nicht beim Tick
    (ordner / m.trainingsbild_name("stallwache", JETZT - 5)).write_bytes(b"x")
    gesendet.clear()
    p.check("naechstes Lebenszeichen", t.tick(False, True, 400.0) is True)
    warte(t)
    p.check("neue Zahl", gesendet[-1][1]["json"]["lebenszeichen"]["trainingsbilder"] == 4)

    # Analyse-Modus: nie zaehlen (ein haengender Ordner darf kein altes
    # „Bild da" verspaeten) -> scandir wird gar nicht aufgerufen
    aufrufe = []
    original_scandir = m.os.scandir
    m.os.scandir = lambda pfad: (aufrufe.append(pfad), original_scandir(pfad))[1]
    try:
        gesendet.clear()
        a = mit_ordner(ordner)
        a.tick(True, True, 0.0)
        warte(a)
        p.check("Analyse-Modus: scandir nie aufgerufen", aufrufe == [])
        p.check("Analyse-Modus: kein Bildbestand im Lebenszeichen",
                gesendet[-1][1]["json"]["lebenszeichen"]
                == {"kamera": "stallwache", "modus": "analyse", "bild": True})
    finally:
        m.os.scandir = original_scandir

    gesendet.clear()
    fehlt = mit_ordner(Path(tmp) / "gibt-es-nicht")
    p.check("fehlender Ordner -> None", fehlt.bildbestand() is None)
    fehlt.tick(False, True, 0.0)
    warte(fehlt)
    lzf = gesendet[-1][1]["json"]["lebenszeichen"] if gesendet else {}
    p.check("fehlender Ordner (Silent) -> trainingsbilder ausdruecklich null, Versand trotzdem",
            len(gesendet) == 1 and "trainingsbilder" in lzf and lzf["trainingsbilder"] is None)

    def scandir_kaputt(_):
        raise PermissionError("kein Zugriff")

    m.os.scandir = scandir_kaputt
    try:
        gesendet.clear()
        k = mit_ordner(ordner)
        p.check("Lesefehler -> None statt Ausnahme", k.bildbestand() is None)
        k.tick(False, True, 0.0)
        warte(k)
        p.check("Lesefehler blockiert den Versand nicht, meldet null",
                len(gesendet) == 1 and gesendet[-1][1]["json"]["lebenszeichen"]["trainingsbilder"] is None)
    finally:
        m.os.scandir = original_scandir

    gesendet.clear()
    ohne_cfg = lz()  # kein silent_mode-Abschnitt
    ohne_cfg.tick(False, True, 0.0)
    warte(ohne_cfg)
    p.check("ohne silent_mode-Konfiguration: kein Feld",
            "trainingsbilder" not in gesendet[-1][1]["json"]["lebenszeichen"])

sys.exit(p.bericht())
