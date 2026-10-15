#!/usr/bin/env python3
"""Logiktests FeedbackSchleife: Markup, Hard-Negative-Ablage, Doppel-Vote,
Robustheit, RAM-Grenze, Deaktivierung, eindeutige IDs ueber Neustarts,
Doppel-Tipp-Zaehlung (Versand-Spezifikation §7) — Telegram-HTTP komplett
gestubbt."""

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("FeedbackSchleife")

tmp = Path(tempfile.mkdtemp())
cfg = {"telegram": {"token": "T", "chat_id": "C", "fehlalarm_ordner": str(tmp)}}
fb = m.FeedbackSchleife(cfg)

alarm = m.Alarm("kalbeverdacht", "Kuh #3", "Test", None, None)
mk = fb.registriere(alarm, [b"roh1", b"roh2"])
p.check("Markup mit 2 Buttons", mk and len(mk["inline_keyboard"][0]) == 2)
teile = mk["inline_keyboard"][0][1]["callback_data"].split(":")
fid0 = teile[1]
p.check(
    "callback_data-Format fb:<fid>:fehlalarm",
    len(teile) == 3 and teile[0] == "fb" and teile[2] == "fehlalarm" and fid0.isalnum(),
)
p.check(
    "info ohne Buttons",
    fb.registriere(m.Alarm("info", None, "x", None, None), [b"a"]) is None,
)

# Fehlalarm-Vote
fb.verarbeite([
    {
        "update_id": 41,
        "callback_query": {
            "id": "cq1",
            "data": f"fb:{fid0}:fehlalarm",
            "message": {"message_id": 7, "chat": {"id": "C"}},
        },
    }
])
dateien = list(tmp.rglob("*.jpg"))
p.check("2 Hard Negatives gespeichert", len(dateien) == 2)
p.check("Dateiname traegt Typ", all(f"kalbeverdacht-{fid0}-" in d.name for d in dateien))
p.check("Zaehler fehlalarm=1", fb.zaehler == {"treffer": 0, "fehlalarm": 1})
p.check("Offset fortgeschrieben", fb._offset == 42)
urls = [u for u, _ in gesendet]
p.check("answerCallbackQuery gesendet", any("answerCallbackQuery" in u for u in urls))
p.check("Buttons entfernt", any("editMessageReplyMarkup" in u for u in urls))

# Doppel-Vote
gesendet.clear()
fb.verarbeite([
    {
        "update_id": 42,
        "callback_query": {
            "id": "cq2",
            "data": f"fb:{fid0}:fehlalarm",
            "message": {"message_id": 7, "chat": {"id": "C"}},
        },
    }
])
p.check("Doppel-Vote schreibt nichts Neues", len(list(tmp.rglob("*.jpg"))) == 2)
antworten = [kw["data"]["text"] for u, kw in gesendet if "answerCallbackQuery" in u]
p.check("Doppel-Vote: 'notiert'-Antwort", antworten and "notiert" in antworten[0])

# Treffer-Vote
mk2 = fb.registriere(m.Alarm("brunstverdacht", "Kuh #5", "T", None, None), [b"x"])
fid = mk2["inline_keyboard"][0][0]["callback_data"].split(":")[1]
fb.verarbeite([
    {
        "update_id": 50,
        "callback_query": {
            "id": "cq3",
            "data": f"fb:{fid}:treffer",
            "message": {"message_id": 9, "chat": {"id": "C"}},
        },
    }
])
p.check("Treffer gezaehlt", fb.zaehler["treffer"] == 1)
p.check("Treffer speichert keine Bilder", len(list(tmp.rglob("*.jpg"))) == 2)

# Robustheit
fb.verarbeite([{"update_id": 60, "callback_query": {"id": "cq4", "data": "unsinn"}}])
fb.verarbeite([{"update_id": 61}])
p.check("robust gegen Unsinn", fb._offset == 62)

# RAM-Grenze
fb2 = m.FeedbackSchleife(cfg)
for _ in range(fb2.MAX_OFFEN + 5):
    fb2.registriere(m.Alarm("austreibung", None, "T", 0.9, None), [b"b"])
p.check("RAM begrenzt auf MAX_OFFEN", len(fb2._offen) == fb2.MAX_OFFEN)

# Deaktiviert
fb3 = m.FeedbackSchleife(
    {"telegram": {"token": "T", "chat_id": "C", "feedback_buttons": False}}
)
p.check("deaktiviert -> kein Markup", fb3.registriere(alarm, [b"x"]) is None)


# Feedback-IDs tragen einen Start-Token je Prozess (feedback-id-
# spezifikation.md); die Tests lesen sie deshalb aus dem Markup.
def cb(markup, urteil="fehlalarm"):
    return markup["inline_keyboard"][0][1 if urteil == "fehlalarm" else 0]["callback_data"]


def fid_von(markup):
    return cb(markup).split(":")[1]


# --- Doppel-Tipp zaehlt einmal (versand-entkopplung-spezifikation.md §7) ---

def tipp(update_id: int, fid: str, urteil: str, message_id: int = 70) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cq{update_id}",
            "data": f"fb:{fid}:{urteil}",
            "message": {"message_id": message_id, "chat": {"id": "C"}},
        },
    }


def neue_schleife() -> tuple:
    ordner = Path(tempfile.mkdtemp())
    s = m.FeedbackSchleife(
        {"telegram": {"token": "T", "chat_id": "C", "fehlalarm_ordner": str(ordner)}}
    )
    rueckrufe: list = []
    s.bei_fehlalarm = lambda typ, episode: rueckrufe.append((typ, episode))
    return s, ordner, rueckrufe


def antworttexte() -> list[str]:
    return [kw["data"]["text"] for u, kw in gesendet if "answerCallbackQuery" in u]


def buttons_entfernt() -> int:
    return sum("editMessageReplyMarkup" in u for u, _ in gesendet)


# 28: Doppel-Tipp ❌ in zwei Abrufen
fb4, ordner4, rueck4 = neue_schleife()
f28 = fid_von(fb4.registriere(m.Alarm("kalbeverdacht", "Kuh #3", "T", None, None), [b"r1", b"r2"]))
gesendet.clear()
fb4.verarbeite([tipp(100, f28, "fehlalarm")])
fb4.verarbeite([tipp(101, f28, "fehlalarm")])
p.check("28: Doppel-Tipp zaehlt einmal", fb4.zaehler == {"treffer": 0, "fehlalarm": 1})
p.check(
    "28: Antworttexte unveraendert",
    antworttexte() == [
        "Danke – 2 Bild(er) fürs Nachtraining gespeichert.",
        "Danke – notiert (Bilder lagen nicht mehr vor).",
    ],
)
p.check("28: keine weiteren Bilder", len(list(ordner4.rglob("*.jpg"))) == 2)
p.check("28: Buttons nur einmal entfernt", buttons_entfernt() == 1)
p.check("28: bei_fehlalarm nur einmal", rueck4 == [("kalbeverdacht", None)])

# 28: Doppel-Tipp im selben Abruf
f28b = fid_von(fb4.registriere(m.Alarm("brunstverdacht", "Kuh #4", "T", None, None), [b"r"]))
fb4.verarbeite([tipp(102, f28b, "fehlalarm"), tipp(103, f28b, "fehlalarm")])
p.check("28: Doppel-Tipp im selben Abruf zaehlt einmal", fb4.zaehler["fehlalarm"] == 2)

# 29: Wechsel ✅ -> ❌ zaehlt nur das erste Urteil
f29 = fid_von(fb4.registriere(m.Alarm("brunstverdacht", "Kuh #5", "T", None, None), [b"r"]))
fb4.verarbeite([tipp(104, f29, "treffer"), tipp(105, f29, "fehlalarm")])
p.check(
    "29: Wechsel zaehlt nur das erste Urteil",
    fb4.zaehler == {"treffer": 1, "fehlalarm": 2},
)

# 30: Votum zu einem durch MAX_OFFEN verdraengten Eintrag zaehlt (einmal)
fb5, _, rueck5 = neue_schleife()
f30 = [
    fid_von(fb5.registriere(m.Alarm("kalbeverdacht", None, "T", None, None), [b"b"]))
    for _ in range(fb5.MAX_OFFEN + 1)
][0]
p.check("30: erster Eintrag ist verdraengt", f30 not in fb5._offen)
gesendet.clear()
fb5.verarbeite([tipp(200, f30, "fehlalarm")])
p.check("30: Votum zu verdraengtem Eintrag zaehlt", fb5.zaehler["fehlalarm"] == 1)
p.check(
    "30: Antwort wie bisher",
    antworttexte() == ["Danke – notiert (Bilder lagen nicht mehr vor)."],
)
p.check("30: kein Rueckruf ohne Eintrag", rueck5 == [])
fb5.verarbeite([tipp(201, f30, "fehlalarm")])
p.check("30: zweiter Tipp darauf zaehlt nicht", fb5.zaehler["fehlalarm"] == 1)

# 32: Votum auf eine Alt-ID, die erst danach neu vergeben wird — das erste
# Votum des neuen Alarms zaehlt. Seit dem Start-Token (feedback-id-
# spezifikation.md) nur noch bei einer Token-Kollision denkbar; die Alt-ID
# wird deshalb mit dem eigenen Token nachgebildet (ID ohne die Nummer 0).
fb7, _, rueck7 = neue_schleife()
token7 = fid_von(fb7.registriere(m.Alarm("kalbeverdacht", None, "T", None, None), [b"w"]))[:-1]
alt32 = f"{token7}2"
fb7.verarbeite([tipp(300, alt32, "treffer")])
fb7.registriere(m.Alarm("kalbeverdacht", None, "T", None, None), [b"a"])
fb7.registriere(m.Alarm("kalbeverdacht", None, "T", None, None), [b"b"])
fb7.verarbeite([tipp(301, alt32, "fehlalarm")])
p.check(
    "32: neu vergebene ID ist wieder abstimmbar",
    fb7.zaehler == {"treffer": 1, "fehlalarm": 1} and len(rueck7) == 1,
)

# 33: Tagesbericht nach Doppel-Tipp
nt = m.Notifier({
    "stream": {"kamera": "stallwache"},
    "telegram": {
        "token": "T",
        "chat_id": "C",
        "digest_uhrzeit": "00:00",
        "fehlalarm_ordner": str(Path(tempfile.mkdtemp())),
    },
    "dashboard": {"puffer_datei": str(Path(tempfile.mkdtemp()) / "puffer.jsonl")},
})
f33 = fid_von(nt.feedback.registriere(m.Alarm("kalbeverdacht", "Kuh #3", "T", None, None), [b"r"]))
gesendet.clear()
nt.feedback.verarbeite([tipp(400, f33, "fehlalarm")])
nt.feedback.verarbeite([tipp(401, f33, "fehlalarm")])
nt.digest_tick(analyse_aktiv=True)
nt.warte()
nt.feedback.verarbeite([tipp(402, f33, "fehlalarm")])  # Tipp nach dem Bericht
nt._digest_tag = None  # naechster Tag
nt.digest_tick(analyse_aktiv=True)
nt.warte()
berichte = [kw["data"]["text"] for u, kw in gesendet if u.endswith("/sendMessage")]
p.check(
    "33: Tagesbericht zaehlt Doppel-Tipp einmal",
    len(berichte) == 2 and "Feedback: ✅ 0 Treffer · ❌ 1 Fehlalarm" in berichte[0],
)
p.check(
    "33: Tipp nach dem Bericht erzeugt keine Feedback-Zeile",
    len(berichte) == 2 and "Feedback:" not in berichte[1],
)

# 31: Menge bleibt begrenzt (kein RAM-Wachstum im 24/7-Betrieb)
fb6, _, _ = neue_schleife()
anzahl = fb6.MAX_ABGESTIMMT + 25
for i in range(anzahl):
    fb6.verarbeite([tipp(1000 + i, str(i), "treffer")])
p.check("31: jedes erste Votum gezaehlt", fb6.zaehler["treffer"] == anzahl)
p.check("31: Menge begrenzt auf MAX_ABGESTIMMT", len(fb6._abgestimmt) == fb6.MAX_ABGESTIMMT)
p.check(
    "31: genau die aeltesten 25 heraus, Rest in Einfuegereihenfolge",
    list(fb6._abgestimmt) == [str(i) for i in range(25, anzahl)],
)
fb6.verarbeite([tipp(5000, str(anzahl - 1), "treffer")])
p.check("31: juengste ID weiter gesperrt", fb6.zaehler["treffer"] == anzahl)


# Neustart (docs/feedback-id-spezifikation.md): Prozess A hinterlaesst Hard
# Negatives und eine unbewertete Nachricht, Prozess B nutzt denselben Ordner.
# Am alten Stand (fid = Prozesszaehler ab 0) traf der alte Button den neuen
# Alarm mit derselben Nummer, und B ueberschrieb die Bilder von A.
tmp_n = Path(tempfile.mkdtemp())
cfg_n = {"telegram": {"token": "T", "chat_id": "C", "fehlalarm_ordner": str(tmp_n)}}


def tippe(schleife, update_id, data):
    schleife.verarbeite([{"update_id": update_id, "callback_query": {
        "id": f"n{update_id}", "data": data,
        "message": {"message_id": update_id, "chat": {"id": "C"}}}}])


def bilder_im_ordner():
    return {d.name: d.read_bytes() for d in tmp_n.rglob("*.jpg")}


a = m.FeedbackSchleife(cfg_n)
mk_a0 = a.registriere(m.Alarm("kalbeverdacht", "Kuh #1", "A0", None, None), [b"A0-0", b"A0-1"])
mk_a1 = a.registriere(m.Alarm("kalbeverdacht", "Kuh #2", "A1", None, None), [b"A1-0"])
tippe(a, 1, cb(mk_a0))  # A0 als Fehlalarm; A1 bleibt unbewertet (alte Buttons)
vorher = bilder_im_ordner()

b = m.FeedbackSchleife(cfg_n)  # Neustart, gleicher Ordner
rueck = []
b.bei_fehlalarm = lambda typ, episode: rueck.append((typ, episode))
mk_b0 = b.registriere(m.Alarm("kalbeverdacht", "Kuh #4", "B0", None, None), [b"B0-0", b"B0-1"])
mk_b1 = b.registriere(
    m.Alarm("austreibung", None, "B1", 0.9, None, sofort=True, episode=3), [b"B1-0"]
)
p.check(
    "Neustart: neue Buttons tragen andere IDs als die alten",
    {cb(mk_b0), cb(mk_b1), cb(mk_b0, "treffer")}.isdisjoint(
        {cb(mk_a0), cb(mk_a1), cb(mk_a0, "treffer"), cb(mk_a1, "treffer")}
    ),
)

gesendet.clear()
tippe(b, 2, cb(mk_a1))  # alter Button einer Nachricht ohne Votum
p.check("Neustart: alter Button schreibt keine Bilder", bilder_im_ordner() == vorher)
p.check("Neustart: alter Button ruft bei_fehlalarm nicht", rueck == [])
p.check(
    "Neustart: alter Button -> 'Bilder lagen nicht mehr vor'",
    antworttexte() and "nicht mehr vor" in antworttexte()[0],
)

tippe(b, 3, cb(mk_b0))  # Fehlalarm-Votum auf die neue Nachricht
nachher = bilder_im_ordner()
p.check(
    "Neustart: Hard Negatives von A unveraendert",
    all(nachher.get(name) == inhalt for name, inhalt in vorher.items()),
)
p.check("Neustart: Hard Negatives von B kommen hinzu", len(nachher) == len(vorher) + 2)
tippe(b, 4, cb(mk_b1))
p.check(
    "Neustart: neue Alarme bleiben abstimmbar (bei_fehlalarm mit eigenem Typ/Episode)",
    rueck == [("kalbeverdacht", None), ("austreibung", 3)],
)

# Exklusives Anlegen: eine vorhandene Datei wird nie ueberschrieben, und es
# gibt keine Erfolgsmeldung.
c = m.FeedbackSchleife(cfg_n)
mk_c = c.registriere(m.Alarm("kalbeverdacht", "Kuh #6", "C", None, None), [b"NEU"])
belegt = tmp_n / time.strftime("%Y-%m-%d") / f"kalbeverdacht-{cb(mk_c).split(':')[1]}-0.jpg"
belegt.parent.mkdir(parents=True, exist_ok=True)
belegt.write_bytes(b"ALT")
gesendet.clear()
tippe(c, 5, cb(mk_c))
p.check("Vorhandene Datei bleibt unveraendert", belegt.read_bytes() == b"ALT")
p.check("Vorhandene Datei: keine Erfolgsmeldung", antworttexte() and "NICHT" in antworttexte()[0])

# Telegram erlaubt hoechstens 64 Bytes callback_data — auch nach sehr vielen
# Alarmen (laufende Nummer 10**15).
lang = m.FeedbackSchleife(cfg_n)
lang._naechste_id = 10**15
knoepfe = lang.registriere(alarm, [b"x"])["inline_keyboard"][0] + mk["inline_keyboard"][0]
p.check(
    "callback_data <= 64 Bytes",
    all(len(k["callback_data"].encode("utf-8")) <= 64 for k in knoepfe),
)

sys.exit(p.bericht())
