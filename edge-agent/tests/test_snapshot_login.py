#!/usr/bin/env python3
"""Logiktests Snapshot-Fallback mit go2rtc-Login.

Die go2rtc-Schnittstelle bekommt einen Login (docs/fernzugriff-spezifikation.md
§1.2). Zugangsdaten stehen dann in stream.fallback_snapshot_url
(http://user:pass@host:1984/…). Geprueft: Sie gehen als Basic-Auth an requests,
nie in Logs; ohne Zugangsdaten bleibt alles wie vorher. HTTP ist gestubbt.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, _ = lade_main(mit_requests_stub=True)
p = Pruefer("Snapshot-Login")

# --- 1. trenne_zugangsdaten ----------------------------------------------
url, auth = m.trenne_zugangsdaten("http://stall:geheim@192.168.178.50:1984/api/frame.jpeg?src=stallwache")
p.check("1: URL ohne Zugangsdaten", url == "http://192.168.178.50:1984/api/frame.jpeg?src=stallwache")
p.check("1: Zugangsdaten getrennt", auth == ("stall", "geheim"))

url, auth = m.trenne_zugangsdaten("http://192.168.178.50:1984/api/frame.jpeg?src=stallwache")
p.check("2: ohne Login unveraendert", url.endswith(":1984/api/frame.jpeg?src=stallwache") and auth is None)

url, auth = m.trenne_zugangsdaten("http://st%40ll:pa%3Ass@host:1984/x")
p.check("3: kodierte Sonderzeichen", url == "http://host:1984/x" and auth == ("st@ll", "pa:ss"))

url, auth = m.trenne_zugangsdaten("http://u:p@[fd7a::1]:1984/x")
p.check("4: IPv6-Host bleibt gueltig", url == "http://[fd7a::1]:1984/x" and auth == ("u", "p"))

p.check("5: leere URL", m.trenne_zugangsdaten("") == ("", None))

# --- 6. StreamHandler: Basic-Auth an requests, nie ins Log ------------------
aufrufe = []


class Fehler(m.requests.RequestException):
    pass


def get_fehler(u, **kw):
    aufrufe.append((u, kw))
    raise Fehler(f"401 Client Error: Unauthorized for url: {u}")


m.requests.get = get_fehler
sh = m.StreamHandler({"stream": {
    "url": "rtsp://192.168.178.50:8554/stallwache",
    "fallback_snapshot_url": "http://stall:geheim@192.168.178.50:1984/api/frame.jpeg?src=stallwache",
}})


class Sammler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.zeilen = []

    def emit(self, record):
        self.zeilen.append(record.getMessage())


sammler = Sammler()
logging.getLogger().addHandler(sammler)
logging.getLogger().setLevel(logging.DEBUG)
ergebnis = sh._frame_snapshot()
p.check("6: Fehlschlag liefert None (Analyse laeuft weiter)", ergebnis is None)
p.check("6: requests bekommt URL ohne Zugangsdaten",
        aufrufe and aufrufe[0][0] == "http://192.168.178.50:1984/api/frame.jpeg?src=stallwache")
p.check("6: requests bekommt Basic-Auth", aufrufe and aufrufe[0][1].get("auth") == ("stall", "geheim"))
p.check(f"6: Passwort steht in keiner Logzeile ({len(sammler.zeilen)} Zeilen)",
        sammler.zeilen and not any("geheim" in z for z in sammler.zeilen))
p.check("6: Fallback bleibt aktivierbar", bool(sh.fallback_url))

# --- 7. ohne Login: auth=None (Verhalten wie vorher) ------------------------
aufrufe.clear()
sh2 = m.StreamHandler({"stream": {
    "url": "rtsp://192.168.178.50:8554/stallwache",
    "fallback_snapshot_url": "http://192.168.178.50:1984/api/frame.jpeg?src=stallwache",
}})
sh2._frame_snapshot()
p.check("7: ohne Login kein auth", aufrufe and aufrufe[0][1].get("auth") is None)

sys.exit(p.bericht())
