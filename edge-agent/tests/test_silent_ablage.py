#!/usr/bin/env python3
"""Logiktests Datensammlung auf stallwache-lela (docs/lela-datensammlung-spezifikation.md).

Geprueft:
1. RTSP-Zugangsdaten stehen nie im Log (auch nicht beim Verbindungsaufbau).
2. Nur-Einzelbild-Quelle: stream.url leer + fallback_snapshot_url -> der
   Agent holt nur Einzelbilder (kein Dauer-Dekodieren auf der alten CPU).
3. Ein Snapshot-Ausfall schreibt eine Warnung je Stoerung, nicht alle 10 s.
4. AblageWaechter: Platzreserve und Schreibfehler werden genau einmal je
   Stoerung gemeldet, die Erholung genau einmal.
5. Hauptschleife: kein Bild bei voller Platte, Schreibfehler werden nicht als
   "gespeichert" gezaehlt, der Tagesbericht nennt die gesammelten Bilder.
cv2, numpy und HTTP sind gestubbt.
"""

import logging
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main  # noqa: E402

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Silent-Ablage")
GIB = 1024 ** 3


class Sammler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.zeilen: list[tuple[int, str]] = []

    def emit(self, record):
        self.zeilen.append((record.levelno, record.getMessage()))


sammler = Sammler()
logging.getLogger().addHandler(sammler)
logging.getLogger().setLevel(logging.DEBUG)

# --- 1. ohne_zugangsdaten ----------------------------------------------------
o = m.ohne_zugangsdaten
p.check("1: RTSP mit Login -> ohne",
        o("rtsp://admin:geheim@192.168.178.117:554/stream1") == "rtsp://192.168.178.117:554/stream1")
p.check("1: @ im Passwort (unkodiert) -> nichts vom Passwort bleibt",
        o("rtsp://admin:ge@heim@192.168.178.117:554/stream1") == "rtsp://192.168.178.117:554/stream1")
p.check("1: ohne Login unveraendert",
        o("rtsp://127.0.0.1:8554/stallwache") == "rtsp://127.0.0.1:8554/stallwache")
p.check("1: http mit Login", o("http://u:p@host:1984/x?src=a") == "http://host:1984/x?src=a")
p.check("1: leer bleibt leer", o("") == "")
p.check("1: kaputte URL wirft nicht", o("rtsp://[::1:554/x") == "rtsp://[::1:554/x")


# --- 2. _verbinde loggt keine Zugangsdaten -----------------------------------
class FakeCap:
    def __init__(self, url):
        self.url = url

    def set(self, *a):
        pass

    def isOpened(self):
        return True

    def read(self):
        return True, "frame"

    def release(self):
        pass


geoeffnet: list[str] = []
m.cv2 = types.SimpleNamespace(
    VideoCapture=lambda url: (geoeffnet.append(url), FakeCap(url))[1],
    CAP_PROP_BUFFERSIZE=38,
    imdecode=lambda buf, flag: "bild",
    IMREAD_COLOR=1,
)
m.np = types.SimpleNamespace(frombuffer=lambda b, dtype=None: b, uint8="u8")
sammler.zeilen.clear()
sh = m.StreamHandler({"stream": {"url": "rtsp://admin:geheim@192.168.178.117:554/stream1"}})
sh._verbinde()
p.check("2: OpenCV bekommt die URL mit Zugangsdaten", geoeffnet == ["rtsp://admin:geheim@192.168.178.117:554/stream1"])
p.check("2: Logzeile nennt den Host",
        any("192.168.178.117:554/stream1" in z for _, z in sammler.zeilen))
p.check("2: Passwort steht in keiner Logzeile", not any("geheim" in z for _, z in sammler.zeilen))

# --- 3. Nur-Einzelbild-Quelle -------------------------------------------------
abrufe: list[tuple[str, dict]] = []


class Antwort:
    def __init__(self, ok=True):
        self.ok = ok
        self.content = b"jpg"

    def raise_for_status(self):
        if not self.ok:
            raise m.requests.RequestException("503 Service Unavailable")


antworten: list[bool] = []


def get(url, **kw):
    abrufe.append((url, kw))
    return Antwort(antworten.pop(0) if antworten else True)


m.requests.get = get
geoeffnet.clear()
nur = m.StreamHandler({"stream": {
    "url": "",
    "fallback_snapshot_url": "http://127.0.0.1:1984/api/frame.jpeg?src=stallwache",
    "ziel_fps": 1000,
}})
p.check("3: leere stream.url mit Snapshot-URL startet", nur.nutze_fallback is True)
frame = nur.naechster_frame()
p.check("3: Bild kommt per Einzelbild", frame == "bild")
p.check("3: abgefragt wird die Snapshot-URL",
        abrufe and abrufe[-1][0] == "http://127.0.0.1:1984/api/frame.jpeg?src=stallwache")
p.check("3: kein RTSP-Strom geoeffnet", geoeffnet == [])

try:
    m.StreamHandler({"stream": {"url": ""}})
    p.check("3: ohne url, Snapshot und Cloud -> Abbruch", False)
except SystemExit as e:
    p.check("3: ohne url, Snapshot und Cloud -> Abbruch mit Hinweis auf fallback_snapshot_url",
            "fallback_snapshot_url" in str(e))

# --- 4. Snapshot-Ausfall: eine Warnung je Stoerung ---------------------------
sammler.zeilen.clear()
antworten[:] = [False] * 5 + [True] + [False]
for _ in range(7):
    nur.naechster_frame()
warnungen = [z for lvl, z in sammler.zeilen if lvl >= logging.WARNING and "Snapshot" in z]
p.check(f"4: 5 Ausfaelle + 1 Erholung + 1 Ausfall -> 2 Warnungen ({len(warnungen)})", len(warnungen) == 2)
p.check("4: Erholung wird geloggt", any("wieder stabil" in z for _, z in sammler.zeilen))
p.check("4: weiter im Einzelbild-Modus", nur.nutze_fallback is True)

# --- 5. AblageWaechter --------------------------------------------------------
frei = {"wert": 10 * GIB}
m.freier_platz = lambda pfad: frei["wert"]
a = m.AblageWaechter(Path("/agent/aufnahmen"))
p.check("5: genug Platz -> speichern, keine Meldung", a.darf_speichern() == (True, None))
p.check("5: Erfolg ohne Stoerung -> keine Meldung", a.ergebnis(True) is None)
frei["wert"] = int(1.5 * GIB)
darf, meldung = a.darf_speichern()
p.check("5: unter Reserve -> nicht speichern", darf is False)
p.check("5: Meldung nennt freien Platz und Bitte",
        meldung is not None and "1.5 GB frei" in meldung and "sichern" in meldung)
p.check("5: zweite Pruefung -> keine zweite Meldung", a.darf_speichern() == (False, None))
frei["wert"] = m.AblageWaechter.RESERVE_BYTES + 100 * 1024 ** 2
p.check("5: knapp ueber Reserve -> weiter pausiert (Hysterese)", a.darf_speichern() == (False, None))
frei["wert"] = 10 * GIB
p.check("5: Platz wieder da -> speichern", a.darf_speichern() == (True, None))
p.check("5: erstes Bild nach Pause -> Erholungsmeldung",
        a.ergebnis(True) == "Trainingsbilder werden wieder gespeichert.")
m_schreib = a.ergebnis(False)
p.check("5: Schreibfehler -> Meldung mit Ordner",
        m_schreib is not None and "/agent/aufnahmen" in m_schreib and "Rechte" in m_schreib)
p.check("5: zweiter Schreibfehler -> keine zweite Meldung", a.ergebnis(False) is None)
p.check("5: Erfolg nach Schreibfehler -> Erholung", a.ergebnis(True) == "Trainingsbilder werden wieder gespeichert.")
frei["wert"] = None
p.check("5: freier Platz unbekannt -> speichern (Schreibergebnis entscheidet)", a.darf_speichern() == (True, None))


# --- 6. Hauptschleife ---------------------------------------------------------
class FalscherNotifier:
    kamera = "stallwache"

    def __init__(self):
        self.meldungen: list[str] = []
        self.gezaehlt = 0
        self.feedback = types.SimpleNamespace(tick=lambda: None, archiv=None)

    def wichtig(self, nachricht):
        self.meldungen.append(nachricht)

    def status(self, nachricht):
        pass

    def digest_tick(self, analyse_aktiv):
        pass

    def zaehle_trainingsbild(self):
        self.gezaehlt += 1


def fahre(n_bilder, imwrite_ergebnisse, frei_bytes):
    notifier = FalscherNotifier()
    geschrieben: list[str] = []
    ergebnisse = list(imwrite_ergebnisse)

    class Strom:
        def __init__(self, cfg):
            self.rest = n_bilder

        def naechster_frame(self):
            if self.rest == 0:
                raise KeyboardInterrupt
            self.rest -= 1
            return object()

    class Engine:
        aktiv = False

        def __init__(self, cfg):
            pass

    class Leer:
        aktiv = False

        def __init__(self, cfg):
            pass

        def tick(self, *a):
            return None

        def fehlalarm_gemeldet(self, *a):
            pass

    def imwrite(pfad, frame):
        geschrieben.append(pfad)
        return ergebnisse.pop(0) if ergebnisse else True

    with tempfile.TemporaryDirectory() as tmp:
        cfg = {
            "stream": {"kamera": "stallwache"},
            "silent_mode": {"ordner": tmp, "intervall_sekunden": 0},
            "watchdog": {"aktiv": False},
        }
        alt = {k: getattr(m, k) for k in ("lade_konfig", "StreamHandler", "InferenceEngine",
                                          "LogicEngine", "Notifier", "TotmannWaechter",
                                          "DatensatzArchiv", "Lebenszeichen", "cv2", "freier_platz")}
        try:
            m.lade_konfig = lambda: cfg
            m.StreamHandler, m.InferenceEngine = Strom, Engine
            m.LogicEngine = m.TotmannWaechter = m.DatensatzArchiv = m.Lebenszeichen = Leer
            m.Notifier = lambda c: notifier
            m.cv2 = types.SimpleNamespace(imwrite=imwrite)
            m.freier_platz = lambda pfad: frei_bytes
            m.main()
        finally:
            for k, v in alt.items():
                setattr(m, k, v)
    return notifier, geschrieben


n, geschrieben = fahre(3, [True, True, True], 10 * GIB)
p.check("6: 3 Bilder geschrieben und gezaehlt", len(geschrieben) == 3 and n.gezaehlt == 3)
p.check("6: keine Stoerungsmeldung im Normalbetrieb", n.meldungen == [])

n, geschrieben = fahre(4, [True, False, False, True], 10 * GIB)
p.check("6: Schreibfehler zaehlt nicht als gespeichert", len(geschrieben) == 4 and n.gezaehlt == 2)
p.check(f"6: Schreibfehler einmal gemeldet, Erholung einmal ({n.meldungen})",
        len(n.meldungen) == 2 and "nicht gespeichert" in n.meldungen[0] and "wieder" in n.meldungen[1])

n, geschrieben = fahre(3, [], int(0.5 * GIB))
p.check("6: Platz unter Reserve -> kein Schreibversuch", geschrieben == [] and n.gezaehlt == 0)
p.check("6: Platzmeldung genau einmal", len(n.meldungen) == 1 and "0.5 GB frei" in n.meldungen[0])

# --- 7. Tagesbericht im Silent Mode ------------------------------------------
gesendet.clear()
with tempfile.TemporaryDirectory() as tmp:
    nt = m.Notifier({
        "stream": {"kamera": "stallwache"},
        "telegram": {"token": "T", "chat_id": "C", "digest_uhrzeit": "00:00",
                     "fehlalarm_ordner": tmp},
        "dashboard": {"puffer_datei": str(Path(tmp) / "puffer.jsonl")},
    })
    nt.silent_ordner = Path(tmp)
    m.freier_platz = lambda pfad: int(42.3 * GIB)
    for _ in range(3):
        nt.zaehle_trainingsbild()
    nt.digest_tick(analyse_aktiv=False)
    nt.warte()
    nt._digest_tag = None
    nt.digest_tick(analyse_aktiv=False)
    nt.warte()
    nt._digest_tag = None
    nt.digest_tick(analyse_aktiv=True)
    nt.warte()
berichte = [kw["data"]["text"] for u, kw in gesendet if u.endswith("/sendMessage")]
p.check("7: drei Berichte", len(berichte) == 3)
p.check("7: Silent-Bericht nennt Bilder und freien Platz",
        len(berichte) == 3 and "Trainingsbilder seit dem letzten Bericht: 3 · frei: 42.3 GB" in berichte[0])
p.check("7: Zaehler beginnt nach dem Bericht neu",
        len(berichte) == 3 and "Trainingsbilder seit dem letzten Bericht: 0" in berichte[1])
p.check("7: Analyse-Bericht ohne Trainingsbild-Zeile",
        len(berichte) == 3 and "Trainingsbilder" not in berichte[2])

sys.exit(p.bericht())
