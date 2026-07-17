#!/usr/bin/env python3
"""Logiktests CloudQuelle: Login, URL-Extraktion aus der Proxy-URL,
Session-Erneuerung nach 401, Kapselung von Fehlern."""

import sys
import types
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, _ = lade_main(mit_requests_stub=True)
p = Pruefer("CloudQuelle")

TUYA = "https://cdn.tuyaeu.com:8080/live/abc.m3u8?sign=xyz&t=1"
PROXY = "/api/futterwache/proxy?url=" + urllib.parse.quote(TUYA, safe="")


class StubAntwort:
    def __init__(self, status=200, url=""):
        self.status_code = status
        self._url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise sys.modules["requests"].RequestException(f"HTTP {self.status_code}")

    def json(self):
        return {"url": self._url}


class StubSession:
    """Konfigurierbare Session: zeichnet Aufrufe auf, liefert Skript ab."""

    logins: list = []
    gets: list = []
    skript: list = []  # Liste von StubAntwort fuer aufeinanderfolgende GETs

    def post(self, url, **kw):
        StubSession.logins.append((url, kw.get("json")))
        return StubAntwort(200)

    def get(self, url, **kw):
        StubSession.gets.append(url)
        return StubSession.skript.pop(0) if StubSession.skript else StubAntwort(500)


sys.modules["requests"].Session = StubSession

cfg = {
    "stream": {
        "app_url": "https://die-stallwache.vercel.app/",
        "quelle_api": "/api/futterwache/stream",
        "app_passwort": "geheim",
    }
}

# 1) Normalfall: Login + Proxy-URL -> Original-CDN-URL
q = m.CloudQuelle(cfg)
StubSession.skript = [StubAntwort(200, PROXY)]
url = q.hole_url()
p.check("CDN-URL extrahiert", url == TUYA)
p.check("Login mit Passwort", StubSession.logins[-1][1] == {"passwort": "geheim"})
p.check("Basis ohne Doppel-Slash", StubSession.gets[-1].endswith(".app/api/futterwache/stream"))

# 2) Session laeuft ab: 401 -> genau ein Re-Login, dann Erfolg
StubSession.logins.clear()
StubSession.skript = [StubAntwort(401), StubAntwort(200, PROXY)]
p.check("nach 401 frische URL", q.hole_url() == TUYA)
p.check("genau ein Re-Login", len(StubSession.logins) == 1)

# 3) API liefert bereits absolute URL -> unveraendert uebernehmen
StubSession.skript = [StubAntwort(200, TUYA)]
p.check("absolute URL unveraendert", q.hole_url() == TUYA)

# 4) Unerwartete relative URL ohne url-Parameter -> None (kein Absturz)
StubSession.skript = [StubAntwort(200, "/irgendwas/anderes")]
p.check("unerwartete URL -> None", q.hole_url() is None)

# 5) Serverfehler -> None, Session zurueckgesetzt
StubSession.skript = [StubAntwort(500)]
p.check("Serverfehler gekapselt -> None", q.hole_url() is None)
p.check("Session nach Fehler zurueckgesetzt", q._session is None)

# 6) Ohne Konfiguration inaktiv
q2 = m.CloudQuelle({"stream": {}})
p.check("unkonfiguriert -> inaktiv/None", not q2.aktiv and q2.hole_url() is None)

sys.exit(p.bericht())
