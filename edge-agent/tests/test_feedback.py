#!/usr/bin/env python3
"""Logiktests FeedbackSchleife: Markup, Hard-Negative-Ablage, Doppel-Vote,
Robustheit, RAM-Grenze, Deaktivierung, Doppel-Tipp-Zaehlung (Versand-
Spezifikation §7) — Telegram-HTTP komplett gestubbt."""

import sys
import tempfile
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
p.check(
    "callback_data-Format",
    mk["inline_keyboard"][0][1]["callback_data"] == "fb:0:fehlalarm",
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
            "data": "fb:0:fehlalarm",
            "message": {"message_id": 7, "chat": {"id": "C"}},
        },
    }
])
dateien = list(tmp.rglob("*.jpg"))
p.check("2 Hard Negatives gespeichert", len(dateien) == 2)
p.check("Dateiname traegt Typ", all("kalbeverdacht-0-" in d.name for d in dateien))
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
            "data": "fb:0:fehlalarm",
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
fb4.registriere(m.Alarm("kalbeverdacht", "Kuh #3", "T", None, None), [b"r1", b"r2"])
gesendet.clear()
fb4.verarbeite([tipp(100, "0", "fehlalarm")])
fb4.verarbeite([tipp(101, "0", "fehlalarm")])
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
fb4.registriere(m.Alarm("brunstverdacht", "Kuh #4", "T", None, None), [b"r"])
fb4.verarbeite([tipp(102, "1", "fehlalarm"), tipp(103, "1", "fehlalarm")])
p.check("28: Doppel-Tipp im selben Abruf zaehlt einmal", fb4.zaehler["fehlalarm"] == 2)

# 29: Wechsel ✅ -> ❌ zaehlt nur das erste Urteil
fb4.registriere(m.Alarm("brunstverdacht", "Kuh #5", "T", None, None), [b"r"])
fb4.verarbeite([tipp(104, "2", "treffer"), tipp(105, "2", "fehlalarm")])
p.check(
    "29: Wechsel zaehlt nur das erste Urteil",
    fb4.zaehler == {"treffer": 1, "fehlalarm": 2},
)

# 30: Votum zu einem durch MAX_OFFEN verdraengten Eintrag zaehlt (einmal)
fb5, _, rueck5 = neue_schleife()
for _ in range(fb5.MAX_OFFEN + 1):
    fb5.registriere(m.Alarm("kalbeverdacht", None, "T", None, None), [b"b"])
p.check("30: Eintrag 0 ist verdraengt", "0" not in fb5._offen)
gesendet.clear()
fb5.verarbeite([tipp(200, "0", "fehlalarm")])
p.check("30: Votum zu verdraengtem Eintrag zaehlt", fb5.zaehler["fehlalarm"] == 1)
p.check(
    "30: Antwort wie bisher",
    antworttexte() == ["Danke – notiert (Bilder lagen nicht mehr vor)."],
)
p.check("30: kein Rueckruf ohne Eintrag", rueck5 == [])
fb5.verarbeite([tipp(201, "0", "fehlalarm")])
p.check("30: zweiter Tipp darauf zaehlt nicht", fb5.zaehler["fehlalarm"] == 1)

# 32: Votum auf eine Alt-ID (z. B. Nachricht von vor dem Neustart), die erst
# danach neu vergeben wird — das erste Votum des neuen Alarms zaehlt.
fb7, _, rueck7 = neue_schleife()
fb7.verarbeite([tipp(300, "1", "treffer")])
fb7.registriere(m.Alarm("kalbeverdacht", None, "T", None, None), [b"a"])
fb7.registriere(m.Alarm("kalbeverdacht", None, "T", None, None), [b"b"])
fb7.verarbeite([tipp(301, "1", "fehlalarm")])
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
nt.feedback.registriere(m.Alarm("kalbeverdacht", "Kuh #3", "T", None, None), [b"r"])
gesendet.clear()
nt.feedback.verarbeite([tipp(400, "0", "fehlalarm")])
nt.feedback.verarbeite([tipp(401, "0", "fehlalarm")])
nt.digest_tick(analyse_aktiv=True)
nt.warte()
nt.feedback.verarbeite([tipp(402, "0", "fehlalarm")])  # Tipp nach dem Bericht
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

sys.exit(p.bericht())
