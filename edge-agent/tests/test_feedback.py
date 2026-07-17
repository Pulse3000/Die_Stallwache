#!/usr/bin/env python3
"""Logiktests FeedbackSchleife: Markup, Hard-Negative-Ablage, Doppel-Vote,
Robustheit, RAM-Grenze, Deaktivierung — Telegram-HTTP komplett gestubbt."""

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

sys.exit(p.bericht())
