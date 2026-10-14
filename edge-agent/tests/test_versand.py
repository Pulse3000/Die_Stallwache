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

    def post(self, url, **kw):
        if self.sperre is not None:
            self.sperre.wait(5)
        if self.haengen_s:
            time.sleep(self.haengen_s)
        if self.ausfall:
            raise m.requests.RequestException("kein Netz")
        with self.lock:
            self.aufrufe.append((url, kw))
        return ANTWORT

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
p.check("7: tick() kehrt sofort zurueck", gestempelt(lambda: fb.tick(0.0)) < 0.3)
p.check("7: zweiter tick waehrend des Abrufs ebenfalls sofort", gestempelt(lambda: fb.tick(11.0)) < 0.3)
kanal7.warte()
p.check("7: hoechstens ein Abruf gleichzeitig", len(netz.an("getUpdates")) == 1)
fb.tick(12.0)
p.check("7: Ergebnis im Hauptthread verarbeitet", fb.zaehler["fehlalarm"] == 1 and fb._offset == 6)
fb.verarbeite(netz.get_ergebnis)
p.check("7: dasselbe Update nie doppelt gezaehlt", fb.zaehler["fehlalarm"] == 1)
fb.tick(23.0)
kanal7.warte()
p.check("7: naechster Abruf mit neuem Offset",
        netz.an("getUpdates")[-1][1]["params"]["offset"] == 6)
fb.tick(24.0)                       # Ergebnis abholen, Sperre frei
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

sys.exit(p.bericht())
