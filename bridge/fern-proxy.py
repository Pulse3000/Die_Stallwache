#!/usr/bin/env python3
"""Absicherung vor go2rtc fuer den Fernzugriff auf die Stallwache (Tapo).

go2rtc darf NIE ungeschuetzt ins Internet: Seine API kann Konfiguration
aendern und Befehle auf dem Stall-Rechner ausfuehren. Dieser kleine Proxy
(nur Python-Standardbibliothek) ist das Einzige, was per `tailscale funnel`
oeffentlich wird. Er laesst ausschliesslich zu:

  * GET auf die HLS-Pfade der Stallwache (siehe ERLAUBT),
  * GET /api/ki-ansicht.jpg: das letzte Analysebild des Edge-Agenten mit
    Kaesten und Kuh-Nummern, direkt aus einer festen Datei (kein go2rtc,
    keine Pfadangabe des Aufrufers; docs/ki-ansicht-spezifikation.md),
  * mit dem geheimen Header  x-stallwache-token,
  * die Quelle wird erzwungen (stallwache_sd) – der Aufrufer waehlt sie nie.

Alles andere: 403 (Token falsch/fehlt) bzw. 404 (Pfad nicht erlaubt).

Start (siehe fern-einrichten.sh):
    FERN_TOKEN=<geheim, >= 24 Zeichen> python3 fern-proxy.py
Env: FERN_PORT (8089), GO2RTC_PORT (1984), FERN_QUELLE (stallwache_sd),
     KI_ANSICHT_DATEI (/dev/shm/stallwache-stallwache/ki-ansicht.jpg).
Lauscht nur auf 127.0.0.1.
"""
from __future__ import annotations

import hmac
import http.client
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlencode, urlsplit

# Pfad (relativ zu /api/) -> erlaubte Query-Parameter (Spiegel von lib/fern.ts)
ERLAUBT: dict[str, tuple[str, ...]] = {
    "stream.m3u8": (),
    "hls/playlist.m3u8": ("id",),
    "hls/segment.ts": ("id", "n"),
    "hls/init.mp4": ("id",),
    "hls/segment.m4s": ("id", "n"),
}
WERT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_GLEICHZEITIG = 12
UPSTREAM_TIMEOUT_S = 20
KI_ANSICHT_PFAD = "/api/ki-ansicht.jpg"
KI_ANSICHT_FRISCH_S = 10          # aelter -> 404, nie ein altes Bild als aktuell
KI_ANSICHT_MAX_BYTES = 2 * 1024 * 1024


def lies_ki_ansicht(datei: str, jetzt: float | None = None) -> tuple[bytes, float] | None:
    """Inhalt und Dateizeit der KI-Ansicht – oder None, wenn sie fehlt, zu
    alt oder zu gross ist. Der Agent ersetzt die Datei atomar (os.replace),
    ein Leser sieht also nie eine halbe."""
    try:
        with open(datei, "rb") as f:
            st = os.fstat(f.fileno())
            if st.st_size > KI_ANSICHT_MAX_BYTES:
                return None
            if (jetzt if jetzt is not None else time.time()) - st.st_mtime > KI_ANSICHT_FRISCH_S:
                return None
            return f.read(KI_ANSICHT_MAX_BYTES + 1), st.st_mtime
    except OSError:
        return None


def token_ok(erwartet: str, erhalten: str | None) -> bool:
    """Zeitkonstanter Tokenvergleich."""
    return bool(erhalten) and hmac.compare_digest(erwartet.encode(), erhalten.encode())


def ziel_fuer(roh_pfad: str, quelle: str = "stallwache_sd") -> str | None:
    """Wandelt den angefragten Pfad+Query in den Upstream-Pfad um – oder None,
    wenn er nicht erlaubt ist. Die Quelle setzt immer der Server."""
    teile = urlsplit(roh_pfad)
    if not teile.path.startswith("/api/"):
        return None
    pfad = teile.path[len("/api/"):]
    erlaubt = ERLAUBT.get(pfad)
    if erlaubt is None:
        return None
    angefragt = dict(parse_qsl(teile.query, keep_blank_values=True))
    ziel: list[tuple[str, str]] = []
    if pfad == "stream.m3u8":
        ziel.append(("src", quelle))
    for name in erlaubt:
        if name in angefragt:
            if not WERT.fullmatch(angefragt[name]):
                return None
            ziel.append((name, angefragt[name]))
    return f"/api/{pfad}" + (f"?{urlencode(ziel)}" if ziel else "")


class Handler(BaseHTTPRequestHandler):
    server_version = "stallwache-fern"
    sys_version = ""
    protocol_version = "HTTP/1.0"
    token = ""
    go2rtc_port = 1984
    quelle = "stallwache_sd"
    ki_ansicht_datei = "/dev/shm/stallwache-stallwache/ki-ansicht.jpg"
    schranke = threading.BoundedSemaphore(MAX_GLEICHZEITIG)

    def _antwort(self, status: int, text: str = "") -> None:
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ki_ansicht(self) -> None:
        erg = lies_ki_ansicht(self.ki_ansicht_datei)
        if erg is None:
            return self._antwort(404, "keine aktuelle KI-Ansicht")
        inhalt, zeit = erg
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Bild-Zeit", str(int(zeit)))
        self.end_headers()
        self.wfile.write(inhalt)

    def do_GET(self) -> None:  # noqa: N802 – Namensvorgabe von BaseHTTPRequestHandler
        if not token_ok(self.token, self.headers.get("x-stallwache-token")):
            return self._antwort(403, "verboten")
        if urlsplit(self.path).path == KI_ANSICHT_PFAD:
            return self._ki_ansicht()
        ziel = ziel_fuer(self.path, self.quelle)
        if ziel is None:
            return self._antwort(404, "nicht erlaubt")
        if not self.schranke.acquire(blocking=False):
            return self._antwort(503, "ausgelastet")
        try:
            verb = http.client.HTTPConnection("127.0.0.1", self.go2rtc_port, timeout=UPSTREAM_TIMEOUT_S)
            try:
                verb.request("GET", ziel)
                r = verb.getresponse()
                self.send_response(r.status)
                for kopf in ("Content-Type", "Content-Length"):
                    if r.getheader(kopf):
                        self.send_header(kopf, r.getheader(kopf))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while chunk := r.read(64 * 1024):
                    self.wfile.write(chunk)
            finally:
                verb.close()
        except (OSError, http.client.HTTPException):
            try:
                self._antwort(502, "go2rtc nicht erreichbar")
            except OSError:
                pass
        finally:
            self.schranke.release()

    # Alles ausser GET ist nicht vorgesehen.
    def _verboten(self) -> None:
        self._antwort(405, "nur GET")

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _verboten

    def log_message(self, fmt: str, *args) -> None:  # kein Token, keine Query im Log
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args if args else fmt))


def main() -> None:
    token = os.environ.get("FERN_TOKEN", "").strip()
    if len(token) < 24:
        raise SystemExit("FERN_TOKEN fehlt oder ist zu kurz (mind. 24 Zeichen).")
    Handler.token = token
    Handler.go2rtc_port = int(os.environ.get("GO2RTC_PORT", "1984"))
    Handler.quelle = os.environ.get("FERN_QUELLE", "stallwache_sd")
    Handler.ki_ansicht_datei = os.environ.get("KI_ANSICHT_DATEI", "").strip() or Handler.ki_ansicht_datei
    port = int(os.environ.get("FERN_PORT", "8089"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    print(f"fern-proxy lauscht auf 127.0.0.1:{port} -> go2rtc :{Handler.go2rtc_port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
