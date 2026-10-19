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
p.check("5: Meldung nennt freien Platz, Reserve, Bitte und Wiederaufnahme",
        meldung is not None and "nur noch 1,5 GB frei" in meldung and "2 GB Reserve" in meldung
        and "sichern" in meldung and "Ab 2,5 GB frei" in meldung)
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
p.check("5: Schreibfehler-Meldung nennt den Neustart als Abhilfe",
        m_schreib is not None and "neu starten" in m_schreib)
b2 = m.AblageWaechter(Path("/agent/aufnahmen"))
frei["wert"] = 2047 * 1024 ** 2
_, knapp = b2.darf_speichern()
p.check(f"5: 2047 MiB werden abgerundet, kein 2,0 GB unter 2 GB ({knapp})",
        knapp is not None and "nur noch 1,9 GB frei" in knapp)
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
p.check("6: Platzmeldung genau einmal", len(n.meldungen) == 1 and "0,5 GB frei" in n.meldungen[0])

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
    m.freier_platz = lambda pfad: int(42.35 * GIB)
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
    start = m.time.strftime("%H:%M", m.time.localtime(nt._start_ts))
berichte = [kw["data"]["text"] for u, kw in gesendet if u.endswith("/sendMessage")]
p.check("7: drei Berichte", len(berichte) == 3)
p.check("7: erster Bericht zaehlt ab dem Start (Neustart wirkt nicht wie Ausfall)",
        len(berichte) == 3 and f"Trainingsbilder seit dem Start um {start}: 3 · frei: 42,3 GB" in berichte[0])
p.check("7: Silent-Bericht sagt, dass nichts erkannt wird",
        len(berichte) == 3 and "keine Kalbe- und Brunsterkennung" in berichte[0]
        and "selbst kontrollieren" in berichte[0])
p.check("7: Silent-Bericht ohne irrefuehrende Null-Zaehler",
        len(berichte) == 3 and "Austreibung:" not in berichte[0] and "Kalbeverdacht:" not in berichte[0])
p.check("7: Zaehler beginnt nach dem Bericht neu",
        len(berichte) == 3 and "Trainingsbilder seit dem letzten Bericht: 0" in berichte[1])
p.check("7: Analyse-Bericht unveraendert mit Zaehlern, ohne Trainingsbild-Zeile",
        len(berichte) == 3 and "Kalbeverdacht: 0 · Austreibung: 0" in berichte[2]
        and "Trainingsbilder" not in berichte[2])


# --- 8. Warnung nach dem Wechsel RTSP -> Snapshot (Analyse-Installationen) --
class ToteCap(FakeCap):
    def isOpened(self):
        return False


m.cv2 = types.SimpleNamespace(VideoCapture=lambda url: ToteCap(url), CAP_PROP_BUFFERSIZE=38,
                              imdecode=lambda buf, flag: "bild", IMREAD_COLOR=1)
alt_wartezeit = m.StreamHandler.RECONNECT_WARTEZEIT_S
m.StreamHandler.RECONNECT_WARTEZEIT_S = 0
sammler.zeilen.clear()
rf = m.StreamHandler({"stream": {
    "url": "rtsp://127.0.0.1:8554/stallwache",
    "fallback_snapshot_url": "http://127.0.0.1:1984/api/frame.jpeg?src=stallwache",
    "ziel_fps": 1000,
}})
antworten[:] = [False, False, False]
for _ in range(rf.FEHLER_BIS_FALLBACK + 3):
    rf.naechster_frame()
m.StreamHandler.RECONNECT_WARTEZEIT_S = alt_wartezeit
snap_warn = [z for lvl, z in sammler.zeilen if lvl >= logging.WARNING and "Snapshot (Einzelbild)" in z]
p.check("8: Wechsel auf Snapshot erfolgt", rf.nutze_fallback is True)
p.check(f"8: erster Snapshot-Fehler nach dem Wechsel ist eine Warnung ({len(snap_warn)})", len(snap_warn) == 1)


# --- 9. Analyse mit zu wenigen Bildern: einmal Hinweis beim Start ------------
def fahre_analyse(intervall_s):
    notifier = FalscherNotifier()

    class Strom:
        frame_intervall = intervall_s

        def __init__(self, cfg):
            pass

        def naechster_frame(self):
            raise KeyboardInterrupt

    class Engine:
        aktiv = True

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

    alt = {k: getattr(m, k) for k in ("lade_konfig", "StreamHandler", "InferenceEngine", "LogicEngine",
                                      "Notifier", "TotmannWaechter", "DatensatzArchiv", "Lebenszeichen")}
    try:
        m.lade_konfig = lambda: {"stream": {"kamera": "stallwache"}, "watchdog": {"aktiv": False}}
        m.StreamHandler, m.InferenceEngine = Strom, Engine
        m.LogicEngine = m.TotmannWaechter = m.DatensatzArchiv = m.Lebenszeichen = Leer
        m.Notifier = lambda c: notifier
        m.main()
    finally:
        for k, v in alt.items():
            setattr(m, k, v)
    return notifier.meldungen


hinweis = fahre_analyse(10.0)
p.check(f"9: Analyse mit 1 Bild/10 s -> genau ein Hinweis ({hinweis})",
        len(hinweis) == 1 and "nur einem Bild alle 10 s" in hinweis[0] and "ziel_fps auf 1.0" in hinweis[0])
p.check("9: Analyse mit 1 Bild/s -> kein Hinweis", fahre_analyse(1.0) == [])

# --- 10. go2rtc erreicht die Kamera nicht: 200 ohne Inhalt ------------------
class Leer200:
    content = b""

    def raise_for_status(self):
        pass


m.requests.get = lambda url, **kw: Leer200()
decodier = {"modus": "ok"}


def imdecode(buf, flag):
    if decodier["modus"] == "wirft":
        raise RuntimeError("(-215:Assertion failed) !buf.empty()")
    return None if decodier["modus"] == "none" else "bild"


m.cv2 = types.SimpleNamespace(VideoCapture=lambda url: FakeCap(url), CAP_PROP_BUFFERSIZE=38,
                              imdecode=imdecode, IMREAD_COLOR=1)
leer = m.StreamHandler({"stream": {"url": "", "ziel_fps": 1000,
                                   "fallback_snapshot_url": "http://127.0.0.1:1984/api/frame.jpeg?src=stallwache"}})
sammler.zeilen.clear()
ergebnisse = []
try:
    for _ in range(3):
        ergebnisse.append(leer.naechster_frame())
    geworfen = False
except Exception:  # noqa: BLE001
    geworfen = True
p.check("10: 200 ohne Inhalt wirft nicht", not geworfen)
p.check("10: 200 ohne Inhalt -> kein Bild", ergebnisse == [None, None, None])
w10 = [z for lvl, z in sammler.zeilen if lvl >= logging.WARNING]
p.check(f"10: genau eine Warnung, nennt die leere Antwort ({w10})", len(w10) == 1 and "leer" in w10[0])
p.check("10: Ausfall wird gezaehlt (Totmann sieht ihn)", leer.fehler_in_folge == 3)


class Voll:
    content = b"jpg"

    def raise_for_status(self):
        pass


m.requests.get = lambda url, **kw: Voll()
for modus in ("wirft", "none"):
    decodier["modus"] = modus
    try:
        r10 = leer.naechster_frame()
        ok10 = r10 is None
    except Exception:  # noqa: BLE001
        ok10 = False
    p.check(f"10: nicht dekodierbares Bild ({modus}) -> None statt Ausnahme", ok10)
decodier["modus"] = "ok"


# --- 11. Fehler der Bildquelle schaltet Totmann und Lebenszeichen nicht ab ----
def fahre_kaputte_quelle(n):
    notifier = FalscherNotifier()
    ticks = {"totmann": [], "leben": []}

    class Strom:
        def __init__(self, cfg):
            self.n = n

        def naechster_frame(self):
            if self.n == 0:
                raise KeyboardInterrupt
            self.n -= 1
            raise RuntimeError("Dekoder kaputt")

    class Engine:
        aktiv = False

        def __init__(self, cfg):
            pass

    class Totmann:
        def __init__(self, cfg):
            pass

        def tick(self, ok):
            ticks["totmann"].append(ok)
            return "Kamerastream ausgefallen" if len(ticks["totmann"]) == n else None

    class Leben:
        def __init__(self, cfg):
            pass

        def tick(self, aktiv, bild):
            ticks["leben"].append(bild)

    class Leer:
        aktiv = False

        def __init__(self, cfg):
            pass

        def fehlalarm_gemeldet(self, *a):
            pass

    with tempfile.TemporaryDirectory() as tmp:
        alt = {k: getattr(m, k) for k in ("lade_konfig", "StreamHandler", "InferenceEngine", "LogicEngine",
                                          "Notifier", "TotmannWaechter", "DatensatzArchiv", "Lebenszeichen", "time")}
        try:
            m.lade_konfig = lambda: {"stream": {"kamera": "stallwache"}, "watchdog": {"aktiv": False},
                                     "silent_mode": {"ordner": tmp, "intervall_sekunden": 0}}
            m.StreamHandler, m.InferenceEngine, m.TotmannWaechter, m.Lebenszeichen = Strom, Engine, Totmann, Leben
            m.LogicEngine = m.DatensatzArchiv = Leer
            m.Notifier = lambda c: notifier
            m.time = types.SimpleNamespace(**{k: getattr(alt["time"], k) for k in dir(alt["time"]) if not k.startswith("_")})
            m.time.sleep = lambda s: None
            m.main()
        finally:
            for k, v in alt.items():
                setattr(m, k, v)
    return ticks, notifier.meldungen


ticks, meld11 = fahre_kaputte_quelle(4)
p.check(f"11: Totmann tickt bei jedem Quellenfehler mit 'kein Bild' ({ticks['totmann']})",
        ticks["totmann"] == [False] * 4)
p.check("11: Lebenszeichen tickt weiter mit 'kein Bild'", ticks["leben"] == [False] * 4)
p.check("11: Totmann-Meldung geht raus", meld11 == ["Kamerastream ausgefallen"])

# --- 12. Geheimnisse im Log: Bot-Token, Passwort mit '/' ----------------------
p.check("12: '/' im RTSP-Passwort wird entfernt",
        m.ohne_zugangsdaten("rtsp://admin:pa/ss@192.168.178.117:554/stream1") == "rtsp://192.168.178.117:554/stream1")
p.check("12: '#' und '?' im Passwort werden entfernt",
        m.ohne_zugangsdaten("http://u:a#b?c@host:1984/x") == "http://host:1984/x")
fmt = m.OhneGeheimnisse("%(levelname)s %(message)s", geheimnisse=["123456:ABC-geheimerToken", "ingest-geheim"])
try:
    raise ValueError("HTTPSConnectionPool(host='api.telegram.org'): url: /bot123456:ABC-geheimerToken/sendMessage")
except ValueError:
    rec = logging.LogRecord("x", logging.ERROR, __file__, 1,
                            "Senden an %s fehlgeschlagen (x-ingest-token ingest-geheim)",
                            ("rtsp://admin:pa/ss@192.168.178.117:554/stream1",), sys.exc_info())
zeile = fmt.format(rec)
p.check("12: Bot-Token weder in Meldung noch Traceback", "geheimerToken" not in zeile)
p.check("12: Ingest-Token nicht im Log", "ingest-geheim" not in zeile)
p.check("12: RTSP-Passwort (mit '/') nicht im Log", "pa/ss" not in zeile and "admin" not in zeile)
p.check("12: Host bleibt zur Diagnose sichtbar", "192.168.178.117" in zeile)
p.check("12: auch fremde Bot-Token (Muster) werden entfernt",
        "777:XYZ" not in m.OhneGeheimnisse("%(message)s").format(
            logging.LogRecord("x", logging.INFO, __file__, 1, "https://api.telegram.org/bot777:XYZabc_-/getMe", (), None)))

# --- 13. archiv nur mit echtem true (Bilder bleiben auf dem Hof) -------------
sammler.zeilen.clear()
for wert in ("false", "nein", "aus", "0", 1):
    arch = m.DatensatzArchiv({"stream": {"kamera": "stallwache"},
                              "dashboard": {"url": "https://x/api/events", "token": "t", "archiv": wert}})
    p.check(f"13: archiv: {wert!r} -> Archiv aus", arch.aktiv is False)
p.check("13: falscher archiv-Wert wird gewarnt",
        any(lvl >= logging.WARNING and "archiv" in z for lvl, z in sammler.zeilen))
p.check("13: archiv: false -> aus",
        m.DatensatzArchiv({"stream": {}, "dashboard": {"url": "https://x/api/events", "token": "t",
                                                      "archiv": False}}).aktiv is False)

sys.exit(p.bericht())
