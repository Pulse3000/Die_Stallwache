#!/usr/bin/env python3
"""Logiktests Bildfrische: Bildgreifer und StreamHandler.

docs/bildfrische-spezifikation.md: Analysiert wird das juengste Bild, nie
eines aus dem Puffer; der Verbindungsaufbau blockiert die Analyse nie;
Dateien bleiben sequenziell; Snapshot-Fallback mit Rueckkehr. OpenCV ist
durch einen Schein-Stream ersetzt (Bildnummer = Sendezeit * fps); die
Messung am echten RTSP-Stream steht in tests/bildfrische/.
"""

import logging
import sys
import threading
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

FPS = 50


class Quelle:
    """Gemeinsamer Zustand des Schein-Streams (von den Tests geschaltet)."""

    def __init__(self):
        self.t0 = time.time()
        self.erreichbar = True
        self.haengt = False        # grab() blockiert ohne Daten
        self.wirf = False          # grab() wirft eine Ausnahme
        self.pos_faktor = 1.0      # Stream-Uhr / Wanduhr (0 = keine Zeitstempel)
        self.oeffnungen: list[float] = []

    def bildnummer(self) -> int:
        return int((time.time() - self.t0) * FPS)


Q = Quelle()


class ScheinCapture:
    def __init__(self, url, *args):
        self.url = url
        self.datei = "://" not in url
        self.offen = self.datei or Q.erreichbar
        self.aktuell = -1
        self.t_offen = time.time()
        if not self.datei:
            Q.oeffnungen.append(time.time())

    def isOpened(self):
        return self.offen

    def grab(self):
        if Q.wirf:
            raise RuntimeError("Dekoder kaputt")
        if not Q.erreichbar:
            time.sleep(0.01)
            return False
        while Q.haengt:
            time.sleep(0.01)
        # Blockiert bis zum naechsten Bild der Kamera (Livekante).
        naechstes = Q.bildnummer() + 1
        time.sleep(max(0.0, Q.t0 + naechstes / FPS - time.time()))
        self.aktuell = naechstes
        return True

    def retrieve(self):
        return True, ("bild", self.aktuell)

    def read(self):  # nur Datei: Bild fuer Bild
        self.aktuell += 1
        return True, ("datei", self.aktuell)

    def get(self, prop):
        return (time.time() - self.t_offen) * 1000 * Q.pos_faktor

    def release(self):
        self.offen = False


cv2 = types.ModuleType("cv2")
cv2.VideoCapture = ScheinCapture
cv2.CAP_ANY = 0
cv2.CAP_PROP_POS_MSEC = 0
cv2.CAP_PROP_OPEN_TIMEOUT_MSEC = 53
cv2.CAP_PROP_READ_TIMEOUT_MSEC = 54
sys.modules["cv2"] = cv2

from hilfe import Pruefer, lade_main  # noqa: E402

m, _ = lade_main(mit_requests_stub=True)
p = Pruefer("Bildfrische")


class Sammler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.zeilen: list[str] = []

    def emit(self, record):
        self.zeilen.append(record.getMessage())


sammler = Sammler()
logging.getLogger().addHandler(sammler)
logging.getLogger().setLevel(logging.INFO)

# Kurze Konstanten, damit die Tests in Sekunden laufen.
G = m.Bildgreifer
G.FRISCH_S = 0.5
G.UEBERGABE_S = 0.3
G.BACKOFF_S = (0.05, 0.1, 0.2, 0.4)
G.RUECKSTAND_WARNUNG_S = 0.2
G.RUECKSTAND_NEU_S = 0.6


def warte_bis(bedingung, timeout=3.0) -> bool:
    ende = time.time() + timeout
    while time.time() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return bedingung()


def neuer_greifer():
    return m.Bildgreifer(lambda: m.oeffne_capture("rtsp://kamera/stall"))


# --- 1. Live oder Datei (R1) -------------------------------------------------
for url, live in [
    ("rtsp://192.168.178.50:8554/stallwache", True),
    ("RTSP://host/x", True),
    ("https://cdn.tuyaeu.com/live/abc.m3u8?sign=x", True),
    ("http://host:1984/api/stream.mjpeg", True),
    ("srt://host:8890", True),
    ("aufnahme_24h.mp4", False),
    ("/home/stall/aufnahme.mp4", False),
    ("C:\\aufnahmen\\nacht.mp4", False),
    ("", False),
]:
    p.check(f"1: {url or '(leer)'} -> {'live' if live else 'Datei'}", m.ist_livequelle(url) is live)

# --- 2. Juengstes Bild statt Puffer (R2, Kriterien 1-2) ----------------------
g = neuer_greifer()
p.check("2: Greifer wird frisch", warte_bis(lambda: g.frisch))
abstaende = []
alter = []
vorher = None
for _ in range(5):
    bild = g.hole()
    if bild is not None:
        alter.append(Q.bildnummer() - bild[1])
        if vorher is not None:
            abstaende.append(bild[1] - vorher)
        vorher = bild[1]
    time.sleep(0.3)
p.check(f"2: jeder Abruf liefert ein Bild ({len(alter)}/5)", len(alter) == 5)
p.check(f"2: Bild ist das juengste (Rueckstand in Bildern: {alter})",
        alter and max(alter) <= 2)
p.check(f"2: Abstand im Video ~ Abruftakt 0,3 s = 15 Bilder (ist {abstaende})",
        abstaende and min(abstaende) >= 12)
g.stopp()

# --- 3. Ausfall, Backoff, Rueckkehr (R3, R5, Kriterium 4) ---------------------
g = neuer_greifer()
warte_bis(lambda: g.frisch)
Q.oeffnungen.clear()
Q.erreichbar = False
t_aus = time.time()
p.check("3: nach Ausfall kein Bild mehr (Frischegrenze)",
        warte_bis(lambda: g.hole() is None, timeout=2.0))
p.check("3: kein Bild spaeter als Frischegrenze + Uebergabe",
        time.time() - t_aus <= G.FRISCH_S + G.UEBERGABE_S + 0.3)
warte_bis(lambda: g.fehlversuche >= 1)
t = time.time()
g.hole()
p.check(f"3: ohne Verbindung kehrt der Abruf ohne Wartezeit zurueck ({time.time() - t:.3f} s)",
        time.time() - t < 0.05)
warte_bis(lambda: len(Q.oeffnungen) >= 4, timeout=3.0)
d = [b - a for a, b in zip(Q.oeffnungen, Q.oeffnungen[1:])]
p.check(f"3: Backoff waechst ({[round(x, 2) for x in d]})",
        len(d) >= 3 and d[0] < d[1] < d[2])
p.check("3: Fehlversuche gezaehlt", g.fehlversuche >= 3)
Q.erreichbar = True
p.check("3: nach Rueckkehr wieder frisches Bild", warte_bis(lambda: g.hole() is not None, timeout=3.0))
p.check("3: Backoff nach erstem Bild zurueckgesetzt", g.fehlversuche == 0)
p.check("3: Log meldet Verbindung", any("Bildgreifer laeuft" in z for z in sammler.zeilen))
g.stopp()

# --- 4. Haengender grab(): Abruf kehrt begrenzt zurueck (R3, Kriterium 5) ----
g = neuer_greifer()
warte_bis(lambda: g.frisch)
Q.haengt = True
time.sleep(0.05)
t = time.time()
bild = g.hole()
dauer = time.time() - t
p.check(f"4: Abruf bei haengendem Stream kehrt zurueck ({dauer:.2f} s)",
        dauer <= G.UEBERGABE_S + 0.2)
Q.haengt = False
g.stopp()

# --- 5. Ausnahme im Greifer: Thread laeuft weiter (R8) -----------------------
g = neuer_greifer()
warte_bis(lambda: g.frisch)
Q.oeffnungen.clear()
Q.wirf = True
p.check("5: nach Ausnahme wird neu verbunden", warte_bis(lambda: len(Q.oeffnungen) >= 2))
p.check("5: Traceback hoechstens einmal", sum("Bildgreifer gestoert" in z for z in sammler.zeilen) == 1)
Q.wirf = False
p.check("5: Greifer erholt sich", warte_bis(lambda: g.hole() is not None))
p.check("5: Thread lebt", g._thread.is_alive())
g.stopp()

# --- 6. Rueckstand gegen die Stream-Uhr (R9) ---------------------------------
# Rechner zu langsam: Stream-Zeit laeuft halb so schnell wie die Wanduhr.
Q.pos_faktor = 0.5
g = neuer_greifer()
warte_bis(lambda: g.frisch)
Q.oeffnungen.clear()
p.check("6: zu grosser Rueckstand -> neu verbinden",
        warte_bis(lambda: len(Q.oeffnungen) >= 1, timeout=3.0))
p.check("6: Warnung mit Rat zum Substream",
        any("hinter dem Stream" in z and "Substream" in z for z in sammler.zeilen))
g.stopp()
# Quelle ohne Zeitstempel (pos immer 0) und normale Quelle: nie neu verbinden.
for faktor, name in ((0.0, "ohne Zeitstempel"), (1.0, "im Takt")):
    Q.pos_faktor = faktor
    g = neuer_greifer()
    warte_bis(lambda: g.frisch)
    Q.oeffnungen.clear()
    time.sleep(1.2)
    p.check(f"6: Quelle {name}: keine Neuverbindung", len(Q.oeffnungen) == 0)
    g.stopp()
Q.pos_faktor = 1.0

# --- 7. StreamHandler: Konstruktor ohne Thread, Abruf blockiert nie ----------
sperre = threading.Event()


def langsames_oeffnen():
    sperre.wait(3)  # Host antwortet nicht
    return None


sh = m.StreamHandler({"stream": {"url": "rtsp://user:geheim@192.168.178.50:8554/stallwache",
                                 "ziel_fps": 100}})
p.check("7: Konstruktor startet keinen Thread", sh.greifer is None and sh.live)
sh._oeffne_live = langsames_oeffnen
t = time.time()
ergebnisse = [sh.naechster_frame() for _ in range(3)]
dauer = time.time() - t
p.check(f"7: Abrufe bei haengendem Verbindungsaufbau kehren sofort zurueck ({dauer:.2f} s)",
        dauer < 0.5 and ergebnisse == [None, None, None])
sperre.set()
sh.greifer.stopp()

# Zugangsdaten nie im Log
sammler.zeilen.clear()
sh2 = m.StreamHandler({"stream": {"url": "rtsp://user:geheim@192.168.178.50:8554/stallwache"}})
sh2._oeffne_live()
p.check("7: Passwort steht in keiner Logzeile",
        sammler.zeilen and not any("geheim" in z for z in sammler.zeilen))

# --- 8. Snapshot-Fallback und Rueckkehr (R6, Kriterium 6) --------------------
Q.erreichbar = False
sh = m.StreamHandler({"stream": {"url": "rtsp://192.168.178.50:8554/stallwache",
                                 "fallback_snapshot_url": "http://192.168.178.50:1984/api/frame.jpeg",
                                 "ziel_fps": 100}})
snapshots = []
sh._frame_snapshot = lambda: (snapshots.append(1), ("snapshot", 0))[1]
sammler.zeilen.clear()
erste = [sh.naechster_frame() for _ in range(4)]
p.check("8: vor dem 5. Fehlversuch kein Snapshot", erste == [None] * 4 and not snapshots)
fuenfter = sh.naechster_frame()
p.check("8: ab dem 5. Fehlversuch Snapshot", fuenfter == ("snapshot", 0) and sh.nutze_fallback)
Q.erreichbar = True
live = None
for _ in range(300):
    f = sh.naechster_frame()
    if f is not None and f[0] == "bild":
        live = f
        break
p.check("8: Livestream gewinnt wieder, sobald frisch", live is not None and not sh.nutze_fallback)
p.check("8: Rueckkehr steht im Log",
        any("zurueck vom Snapshot-Polling" in z for z in sammler.zeilen))
p.check("8: Wechsel genau einmal geloggt",
        sum("wechsle auf Snapshot-Polling" in z for z in sammler.zeilen) == 1)
sh.greifer.stopp()

# --- 9. Datei: Bild fuer Bild, kein Greifer (Grundsatz 5, Kriterium 3) -------
sh = m.StreamHandler({"stream": {"url": "aufnahme_24h.mp4", "ziel_fps": 1000}})
bilder = [sh.naechster_frame() for _ in range(5)]
p.check(f"9: Datei sequenziell ({[b[1] for b in bilder]})",
        [b[1] for b in bilder] == [0, 1, 2, 3, 4])
p.check("9: Datei ohne Greifer", sh.greifer is None and not sh.live)

sys.exit(p.bericht())
