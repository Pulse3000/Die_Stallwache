#!/usr/bin/env python3
"""Logiktests Versand-Entkopplung (docs/versand-entkopplung-spezifikation.md).

Die Zusage: Die Analyseschleife wartet nie auf das Netz. Telegram und
Dashboard laufen in eigenen Threads, das Dashboard als Outbox, die nichts
verliert und nichts doppelt schickt, und gepufferte Alarme gehen auch ohne
neuen Alarm raus. HTTP ist komplett gestubbt — es geht nie ein echter
Request raus; „haengen" wird mit threading.Event nachgestellt.
"""

import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, _ = lade_main(mit_requests_stub=True)
p = Pruefer("Versand-Entkopplung")

TMP = Path(tempfile.mkdtemp())
ANTWORT = type(
    "A",
    (),
    {
        "raise_for_status": staticmethod(lambda: None),
        "json": staticmethod(lambda: {"result": []}),
    },
)()


class Netz:
    """Steuerbarer requests-Ersatz: zeichnet auf, kann haengen oder scheitern."""

    def __init__(self):
        self.aufrufe: list[tuple[str, dict]] = []
        self.lock = threading.Lock()
        self.haengen_s = 0.0
        self.sperre: threading.Event | None = None
        self.ausfall = False
        self.get_ergebnis: list = []
        # Optional: Server-Nachbau, liefert den HTTP-Status je Anfrage.
        self.status = None
        # 400 kommt von einem Proxy (HTML) statt von der App (JSON {fehler}).
        self.fremde_400 = False

    def post(self, url, **kw):
        if self.sperre is not None:
            self.sperre.wait(5)
        if self.haengen_s:
            time.sleep(self.haengen_s)
        if self.ausfall:
            raise m.requests.RequestException("kein Netz")
        code = self.status(url, kw) if self.status else 200
        with self.lock:
            self.aufrufe.append((url, {**kw, "_status": code}))

        def pruefen():
            if code >= 400:
                raise m.requests.RequestException(f"HTTP {code}")

        fremd = self.fremde_400

        def koerper():
            if code == 400 and fremd:
                raise ValueError("kein JSON (Proxy-Fehlerseite)")
            if code == 400:
                return {"fehler": "Unbekannter typ"}
            return {"result": []}

        return type("R", (), {"status_code": code, "raise_for_status": staticmethod(pruefen),
                              "json": staticmethod(koerper)})()

    def get(self, url, **kw):
        if self.haengen_s:
            time.sleep(self.haengen_s)
        with self.lock:
            self.aufrufe.append((url, kw))
        ergebnis = self.get_ergebnis
        return type(
            "G",
            (),
            {
                "raise_for_status": staticmethod(lambda: None),
                "json": staticmethod(lambda: {"result": ergebnis}),
            },
        )()

    def an(self, teil):
        with self.lock:
            return [(u, kw) for u, kw in self.aufrufe if teil in u]


def neues_netz() -> Netz:
    n = Netz()
    m.requests.post = n.post
    m.requests.get = n.get
    return n


zaehler = [0]


def notifier(**db_extra):
    zaehler[0] += 1
    cfg = {
        "stream": {"kamera": "stallwache"},
        "telegram": {"token": "T", "chat_id": "C", "fehlalarm_ordner": str(TMP / "fb")},
        "dashboard": {
            "url": "https://beispiel.test/api/events",
            "token": "I",
            "puffer_datei": str(TMP / f"puffer-{zaehler[0]}.jsonl"),
            **db_extra,
        },
    }
    return m.Notifier(cfg)


def alarm(text="Fruchtblase erkannt", typ="austreibung"):
    return m.Alarm(typ, None, text, 0.9, None, sofort=True, episode=1)


def gestempelt(fn) -> float:
    start = time.monotonic()
    fn()
    return time.monotonic() - start


# --- 1. melde() blockiert nicht, obwohl Telegram UND Dashboard haengen -------
netz = neues_netz()
netz.haengen_s = 2.0
n1 = notifier()
dauer = gestempelt(lambda: n1.melde(alarm(), None))
p.check(f"1: melde() kehrt sofort zurueck ({dauer:.3f} s < 0.3 s)", dauer < 0.3)

# --- 2. Nach dem Warten ist alles mit unveraendertem Inhalt gesendet --------
p.check("2: Versand wird fertig", n1.warte(10))
tg = netz.an("sendMessage")
p.check("2: Telegram-Nachricht gesendet", len(tg) == 1)
p.check("2: Text enthaelt Alarm", "Fruchtblase erkannt" in tg[0][1]["data"]["text"])
p.check("2: Feedback-Buttons dabei", "reply_markup" in tg[0][1]["data"])
db = netz.an("/api/events")
p.check("2: Dashboard-Stapel gesendet", len(db) == 1)
ev = db[0][1]["json"]["ereignisse"]
p.check("2: genau das Ereignis, Schema unveraendert",
        len(ev) == 1 and set(ev[0]) == {"typ", "kuhId", "kamera", "nachricht", "konfidenz", "zeit"})
p.check("2: Ingest-Token im Header", db[0][1]["headers"] == {"x-ingest-token": "I"})

# --- 3. Dashboard down -> Puffer; wieder da -> Nachlieferung OHNE neuen Alarm
netz = neues_netz()
netz.ausfall = True
m.Notifier.NACHLIEFER_INTERVALL_S = 0.3
n3 = notifier()
n3.status("Kamerastream ausgefallen")
n3.warte()
p.check("3: bei Ausfall in der Pufferdatei", n3._puffer_datei.exists() and len(n3._puffer) == 1)
netz.ausfall = False
frist = time.monotonic() + 3
while time.monotonic() < frist and n3._puffer:
    time.sleep(0.05)
p.check("3: ohne neuen Alarm nachgeliefert", len(netz.an("/api/events")) == 1 and not n3._puffer)
time.sleep(0.2)
p.check("3: Pufferdatei danach entfernt", not n3._puffer_datei.exists())
m.Notifier.NACHLIEFER_INTERVALL_S = 60

# --- 4. Alarm trifft ein, waehrend ein Stapel unterwegs ist ----------------
netz = neues_netz()
netz.sperre = threading.Event()
n4 = notifier()
n4.status("A")
time.sleep(0.2)                     # Stapel [A] haengt jetzt im Versand
n4.status("B")
netz.sperre.set()
n4.warte()
gesendet = [e["nachricht"] for _, kw in netz.an("/api/events") for e in kw["json"]["ereignisse"]]
p.check(f"4: jedes Ereignis genau einmal ({gesendet})", sorted(gesendet) == ["A", "B"])
p.check("4: Outbox danach leer", not n4._puffer)

# --- 5. Obergrenze laeuft ueber, waehrend ein Stapel unterwegs ist ---------
netz = neues_netz()
netz.sperre = threading.Event()
n5 = notifier(puffer_max=2)
n5.status("A")
time.sleep(0.2)                     # [A] unterwegs
for t in ("B", "C", "D"):           # Obergrenze 2: B wird verdraengt
    n5.status(t)
netz.sperre.set()
n5.warte()
gesendet = [e["nachricht"] for _, kw in netz.an("/api/events") for e in kw["json"]["ereignisse"]]
p.check(f"5: nichts doppelt gesendet ({gesendet})", len(gesendet) == len(set(gesendet)))
p.check("5: A gesendet, C und D nachgeliefert", {"A", "C", "D"} <= set(gesendet))
p.check("5: Outbox danach leer", not n5._puffer)

# --- 6. Telegram-Warteschlange laeuft ueber -> aelteste fallen heraus -------
kanal = m.Versandkanal("test", 3)
frei = threading.Event()
erledigt: list[int] = []
kanal.auftrag(lambda: (frei.wait(5), erledigt.append(0)))
time.sleep(0.1)                     # Auftrag 0 laeuft und blockiert
for i in range(1, 7):
    kanal.auftrag(erledigt.append, i)
p.check("6: drei aelteste verworfen", kanal.verworfen == 3)
frei.set()
kanal.warte()
p.check(f"6: neueste in Reihenfolge erledigt ({erledigt})", erledigt == [0, 4, 5, 6])

# --- 7. Feedback-Abruf blockiert nicht, hoechstens einer gleichzeitig -------
netz = neues_netz()
netz.haengen_s = 1.0
kanal7 = m.Versandkanal("feedback-test", 10)
fb = m.FeedbackSchleife(
    {"telegram": {"token": "T", "chat_id": "C", "fehlalarm_ordner": str(TMP / "fb7")}},
    kanal=kanal7,
)
fid = fb.registriere(m.Alarm("kalbeverdacht", "Kuh #3", "x", None, None), [b"roh"])[
    "inline_keyboard"][0][1]["callback_data"].split(":")[1]
netz.get_ergebnis = [{"update_id": 5, "callback_query": {"id": "q", "data": f"fb:{fid}:fehlalarm"}}]
threads_rueckmeldung: list[str] = []
fb.bei_fehlalarm = lambda typ, ep: threads_rueckmeldung.append(threading.current_thread().name)
p.check("7: tick() stoesst Abruf an und kehrt sofort zurueck", gestempelt(lambda: fb.tick(11.0)) < 0.3)
time.sleep(0.1)                     # Abruf laeuft jetzt (haengt 1 s)
p.check("7: tick() waehrend des Abrufs sofort", gestempelt(lambda: fb.tick(22.0)) < 0.3)
p.check("7: kein zweiter Abruf, solange der erste laeuft", fb._abruf_seit == 11.0)
kanal7.warte()
p.check("7: hoechstens ein Abruf gleichzeitig", len(netz.an("getUpdates")) == 1)
fb.tick(22.5)
p.check("7: Ergebnis verarbeitet", fb.zaehler["fehlalarm"] == 1 and fb._offset == 6)
p.check("7: Rueckmeldung an die Logik im Hauptthread",
        threads_rueckmeldung == [threading.main_thread().name])
fb.verarbeite(netz.get_ergebnis)
p.check("7: dasselbe Update nie doppelt gezaehlt", fb.zaehler["fehlalarm"] == 1)
fb.tick(33.0)
kanal7.warte()
p.check("7: naechster Abruf mit neuem Offset",
        netz.an("getUpdates")[-1][1]["params"]["offset"] == 6)
fb.tick(33.5)                       # Ergebnis abholen, ggf. naechster Abruf
kanal7.warte()
fb.tick(33.6)                       # alles abgeholt, kein Abruf mehr unterwegs
p.check("7: Sperre frei, nichts unterwegs", fb._abruf_seit is None and kanal7.warte(0.1))
fb._abruf_seit = 30.0               # Abruf, der nie zurueckkommt
vorher = len(netz.an("getUpdates"))
fb.tick(100.0)
kanal7.warte()
p.check("7: haengende Sperre blockiert vor 120 s", len(netz.an("getUpdates")) == vorher)
fb.tick(151.0)
kanal7.warte()
p.check("7: nach 120 s freigegeben, neuer Abruf", len(netz.an("getUpdates")) == vorher + 1)

# --- 8. Feedback-Antworten laufen ueber den Kanal --------------------------
p.check("8: answerCallbackQuery ueber den Kanal gesendet", len(netz.an("answerCallbackQuery")) >= 1)
netz.haengen_s = 2.0
fid8 = fb.registriere(m.Alarm("brunstverdacht", "Kuh #9", "x", None, None), [b"r"])[
    "inline_keyboard"][0][0]["callback_data"].split(":")[1]
dauer = gestempelt(lambda: fb.verarbeite(
    [{"update_id": 50, "callback_query": {"id": "q8", "data": f"fb:{fid8}:treffer",
                                          "message": {"message_id": 3, "chat": {"id": "C"}}}}]))
p.check(f"8: verarbeite() blockiert nicht bei haengender Antwort ({dauer:.3f} s)", dauer < 0.3)
fb.verarbeite([{"update_id": 51, "callback_query": {"id": "q9", "data": f"fb:{fid8}:treffer",
                                                    "message": {"message_id": 3, "chat": {"id": "C"}}}}])
kanal7.warte(10)
p.check("8: Buttons nur beim ersten Votum entfernt", len(netz.an("editMessageReplyMarkup")) == 1)

# --- 9. digest_tick() und wichtig() blockieren nicht ------------------------
netz = neues_netz()
netz.haengen_s = 2.0
n9 = notifier()
n9.digest_uhrzeit = "00:00"
p.check("9: digest_tick() sofort", gestempelt(lambda: n9.digest_tick(True)) < 0.3)
p.check("9: wichtig() sofort", gestempelt(lambda: n9.wichtig("Kamera blind")) < 0.3)
n9.warte(10)
p.check("9: Tagesbericht und Meldung danach gesendet",
        len(netz.an("sendMessage")) == 2 and len(netz.an("/api/events")) >= 1)

# --- 10. Ein Auftrag, der wirft, stoppt den Worker nicht -------------------
kanal10 = m.Versandkanal("fehler-test", 5)
nach_fehler: list[str] = []
kanal10.auftrag(lambda: 1 / 0)
kanal10.auftrag(nach_fehler.append, "weiter")
kanal10.warte()
p.check("10: Worker laeuft nach Ausnahme weiter", nach_fehler == ["weiter"])

# --- 11. Teilstapel unter den Server-Grenzen (100 Eintraege, 4,5 MB) -------
def server_grenzen(url, kw):
    ev = kw["json"]["ereignisse"]
    if len(ev) > 100:
        return 400
    if len(m.json.dumps(kw["json"])) > 4_500_000:
        return 413
    return 201


netz = neues_netz()
netz.ausfall = True
n11 = notifier()
for i in range(130):
    n11.status(f"S{i}")
for i in range(6):                  # 6 Alarme mit je ~1,2 MB Bildern
    n11._dashboard(m.Alarm("kalbeverdacht", f"Kuh #{i}", f"K{i}", None, None),
                   [b"x" * 300_000, b"y" * 300_000, b"z" * 300_000])
n11.warte()
netz.ausfall = False
netz.status = server_grenzen
n11._outbox_signal.put(None)        # naechster Versuch (sonst nach Backoff)
n11.warte(20)
posts = netz.an("/api/events")
alle11 = [e["nachricht"] for _, kw in posts for e in kw["json"]["ereignisse"]]
p.check(f"11: alles nachgeliefert ({len(alle11)}/136), keins doppelt",
        len(alle11) == 136 and len(set(alle11)) == 136 and not n11._puffer)
p.check("11: jeder Teilstapel <= 50 Eintraege und < 4,5 MB",
        all(len(kw["json"]["ereignisse"]) <= 50 and len(m.json.dumps(kw["json"])) < 4_500_000 for _, kw in posts))
p.check("11: kein Stapel vom Server abgelehnt", all(kw["_status"] < 400 for _, kw in posts))

# --- 12. Austreibung zuerst, auch hinter einem Rueckstau --------------------
netz = neues_netz()
netz.ausfall = True
n12 = notifier()
for i in range(60):
    n12.status(f"S{i}")
n12._dashboard(alarm("Fruchtblase erkannt"), None)
n12.warte()
netz.ausfall = False
n12._outbox_signal.put(None)
n12.warte(10)
erster = netz.an("/api/events")[0][1]["json"]["ereignisse"]
p.check("12: erste Anfrage nach dem Ausfall enthaelt die Austreibung",
        erster[0]["typ"] == "austreibung")

# --- 13. Nach Fehlschlag tasten: nur ein Ereignis je Versuch ---------------
netz = neues_netz()
netz.status = lambda url, kw: 401
n13 = notifier()
for i in range(20):
    n13.status(f"S{i}")
n13.warte()
for _ in range(3):
    n13._outbox_signal.put(None)
    n13.warte()
groessen = [len(kw["json"]["ereignisse"]) for _, kw in netz.an("/api/events")]
p.check(f"13: nach erstem Fehlschlag nur noch Einzel-Versuche ({groessen[:6]}...)",
        all(g == 1 for g in groessen[1:]))
p.check("13: nichts verworfen bei 401", len(n13._puffer) == 20)

# --- 14. Backoff: 60 s, 120 s, ... hoechstens 900 s -------------------------
n14 = notifier()
werte = []
for f in range(0, 8):
    n14._db_fehler_in_folge = f
    werte.append(n14._wartezeit())
p.check(f"14: Backoff {werte}", werte == [60, 60, 120, 240, 480, 900, 900, 900])

# --- 15. Dauerhaft abgelehnter Eintrag blockiert nie die Schlange ----------
def server_giftig(url, kw):
    ev = kw["json"]["ereignisse"]
    if any(e["nachricht"] == "GIFT" for e in ev):
        return 400
    if any(e["nachricht"] == "GROSS" and e.get("bilder") for e in ev):
        return 413
    return 201


netz = neues_netz()
netz.ausfall = True
n15 = notifier()
n15.status("vorher")
n15.status("GIFT")
n15._dashboard(m.Alarm("kalbeverdacht", "Kuh #1", "GROSS", None, None), [b"b" * 1000])
n15.status("nachher")
n15.warte()
netz.ausfall = False
netz.status = server_giftig
n15._outbox_signal.put(None)
n15.warte(10)
angenommen = [e for _, kw in netz.an("/api/events") if kw["_status"] < 400 for e in kw["json"]["ereignisse"]]
namen = [e["nachricht"] for e in angenommen]
p.check(f"15: gesunde Eintraege geliefert ({namen})", {"vorher", "nachher"} <= set(namen))
p.check("15: zu grosser Eintrag ohne Bilder geliefert",
        any(e["nachricht"] == "GROSS" and "bilder" not in e for e in angenommen))
p.check("15: dauerhaft abgelehnter Eintrag verworfen, Outbox leer", "GIFT" not in namen and not n15._puffer)

# --- 16. Neuer Alarm wird gesichert, waehrend ein POST haengt --------------
netz = neues_netz()
netz.sperre = threading.Event()
n16 = notifier()
n16.status("A")
time.sleep(0.2)                     # [A] haengt im POST
n16._dashboard(alarm("Fruchtblase erkannt"), None)
frist = time.monotonic() + 2
gesichert = False
while time.monotonic() < frist and not gesichert:
    if n16._puffer_datei.exists():
        gesichert = "Fruchtblase erkannt" in n16._puffer_datei.read_text("utf-8")
    time.sleep(0.02)
p.check("16: Alarm binnen 2 s auf der Platte, obwohl der POST haengt", gesichert)
netz.sperre.set()
n16.warte(10)

# --- 17. puffer_max 0 schaltet die App-Meldung nicht still ab --------------
netz = neues_netz()
n17 = notifier(puffer_max=0)
n17.status("trotzdem senden")
n17.warte()
p.check("17: puffer_max 0 -> Ereignis wird trotzdem gesendet", len(netz.an("/api/events")) == 1)

# --- 18. Ueberlauf verdraengt nie einen dringenden Auftrag ------------------
k18 = m.Versandkanal("prio-test", 3)
frei18 = threading.Event()
lauf18: list[str] = []
k18.auftrag(lambda: (frei18.wait(5), lauf18.append("laufend")))
time.sleep(0.1)
k18.auftrag(lauf18.append, "AUSTREIBUNG", prio=True)
for i in range(6):
    k18.auftrag(lauf18.append, f"routine{i}")
frei18.set()
k18.warte()
p.check(f"18: dringender Auftrag ueberlebt den Ueberlauf ({lauf18})", "AUSTREIBUNG" in lauf18)

# --- 19. Feedback hat einen eigenen Kanal -----------------------------------
n19 = notifier()
p.check("19: Feedback konkurriert nicht mit Alarmen", n19.feedback._kanal is not n19._tg)

# --- 20. Fremde 400 (Proxy) verwirft nichts --------------------------------
netz = neues_netz()
netz.status = lambda url, kw: 400
netz.fremde_400 = True
n20 = notifier()
n20._dashboard(alarm("Fruchtblase erkannt"), None)
n20.warte()
p.check("20: Proxy-400 -> Austreibung bleibt in der Outbox", len(n20._puffer) == 1)
p.check("20: als Fehler gezaehlt (Backoff), nicht verworfen", n20._db_fehler_in_folge >= 1)

# --- 21. Neue Austreibung ueberholt den laufenden Rueckstau ----------------
netz = neues_netz()
netz.ausfall = True
n21 = notifier()
for i in range(120):
    n21.status(f"S{i}")
n21.warte()
netz.ausfall = False
n21._db_fehler_in_folge = 0         # kein Tasten: direkt in Teilstapeln
netz.sperre = threading.Event()
n21._outbox_signal.put(None)
time.sleep(0.2)                     # erster Teilstapel (50) haengt im POST
n21._dashboard(alarm("Fruchtblase erkannt"), None)
netz.sperre.set()
n21.warte(10)
posts21 = [kw["json"]["ereignisse"] for _, kw in netz.an("/api/events")]
p.check("21: zweite Anfrage beginnt mit der neuen Austreibung",
        len(posts21) >= 2 and posts21[1][0]["typ"] == "austreibung")
p.check("21: alles geliefert, nichts doppelt",
        sum(len(x) for x in posts21) == 121 and not n21._puffer)

# --- 22. Dringende ueberholen Routine; Routine verdraengt nie Dringendes ---
k22 = m.Versandkanal("prio-test-2", 2)
frei22 = threading.Event()
lauf22: list[str] = []
k22.auftrag(lambda: (frei22.wait(5), lauf22.append("laufend")))
time.sleep(0.1)
k22.auftrag(lauf22.append, "routine-alt")
k22.auftrag(lauf22.append, "AUSTREIBUNG-1", prio=True)   # voll: routine-alt weicht
k22.auftrag(lauf22.append, "AUSTREIBUNG-2", prio=True)   # voll, nur dringende: aelteste dringende weicht
k22.auftrag(lauf22.append, "routine-neu")                # nur dringende wartend -> neue Routine verworfen
frei22.set()
k22.warte()
p.check(f"22: Routine verdraengt nie einen dringenden Auftrag ({lauf22})",
        "routine-neu" not in lauf22 and "AUSTREIBUNG-2" in lauf22)
k22b = m.Versandkanal("prio-test-3", 10)
frei22b = threading.Event()
lauf22b: list[str] = []
k22b.auftrag(lambda: (frei22b.wait(5), lauf22b.append("laufend")))
time.sleep(0.1)
k22b.auftrag(lauf22b.append, "kalbeverdacht")
k22b.auftrag(lauf22b.append, "AUSTREIBUNG", prio=True)
frei22b.set()
k22b.warte()
p.check(f"22: dringender Auftrag ueberholt wartende Routine ({lauf22b})",
        lauf22b == ["laufend", "AUSTREIBUNG", "kalbeverdacht"])

# --- 23. Fehlalarm-Votum wartet nicht auf die Platte -----------------------
netz = neues_netz()
k23 = m.Versandkanal("feedback-platte", 10)
fb23 = m.FeedbackSchleife(
    {"telegram": {"token": "T", "chat_id": "C", "fehlalarm_ordner": str(TMP / "fb23")}},
    kanal=k23,
)
fid23 = fb23.registriere(m.Alarm("kalbeverdacht", "Kuh #1", "x", None, None), [b"a", b"b"])[
    "inline_keyboard"][0][1]["callback_data"].split(":")[1]
langsam = []
fb23._speichere = lambda fid, eintrag: (time.sleep(2), langsam.append(fid))
dauer = gestempelt(lambda: fb23.verarbeite(
    [{"update_id": 1, "callback_query": {"id": "q", "data": f"fb:{fid23}:fehlalarm"}}]))
p.check(f"23: Votum blockiert nicht bei langsamer Platte ({dauer:.3f} s)", dauer < 0.3)
k23.warte(10)
p.check("23: Bilder im Hintergrund gespeichert", langsam == [fid23])

sys.exit(p.bericht())
