#!/usr/bin/env python3
"""Tests bridge/fern-proxy.py (Absicherung vor go2rtc fuer den Fernzugriff).

Prueft die Pfad-Freigabe, den Tokenvergleich und – mit einem gefaelschten
go2rtc auf Loopback – den ganzen Weg: ohne Token 403, go2rtc-API 404, nur das
Stallwache-HLS kommt durch und die Quelle wird erzwungen.

    python3 edge-agent/tests/test_fern_proxy.py
    pytest -q edge-agent/tests/test_fern_proxy.py
"""

import http.client
import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROXY_PY = Path(__file__).resolve().parent.parent.parent / "bridge" / "fern-proxy.py"
spec = importlib.util.spec_from_file_location("fern_proxy", PROXY_PY)
fp = importlib.util.module_from_spec(spec)
sys.modules["fern_proxy"] = fp
spec.loader.exec_module(fp)

TOKEN = "t" * 32


# --- reine Funktionen --------------------------------------------------------

def test_token_vergleich():
    assert fp.token_ok(TOKEN, TOKEN)
    assert not fp.token_ok(TOKEN, None)
    assert not fp.token_ok(TOKEN, "")
    assert not fp.token_ok(TOKEN, TOKEN + "x")
    assert not fp.token_ok(TOKEN, "x" * 32)


def test_einstieg_erzwingt_quelle():
    assert fp.ziel_fuer("/api/stream.m3u8?src=rollei") == "/api/stream.m3u8?src=stallwache_sd"
    assert fp.ziel_fuer("/api/stream.m3u8") == "/api/stream.m3u8?src=stallwache_sd"


def test_folgeabrufe_nur_erlaubte_parameter():
    assert fp.ziel_fuer("/api/hls/segment.ts?id=ab_1&n=7&src=rollei&x=1") == "/api/hls/segment.ts?id=ab_1&n=7"
    assert fp.ziel_fuer("/api/hls/playlist.m3u8?id=ab") == "/api/hls/playlist.m3u8?id=ab"


def test_api_und_fremde_pfade_gesperrt():
    for p in ("/api/streams", "/api/config", "/api/restart", "/api/frame.jpeg?src=stallwache",
              "/api/exec", "/api/webrtc", "/api/ws", "/config", "/", "/api/",
              "/api/hls/../config", "/api/../api/config", "/api/hls/segment.ts/../../config"):
        assert fp.ziel_fuer(p) is None, p


def test_parameter_mit_sonderzeichen_gesperrt():
    for wert in ("../x", "a%20b", "a;b", "x" * 65):
        assert fp.ziel_fuer(f"/api/hls/playlist.m3u8?id={wert}") is None, wert


# --- Ganzer Weg mit gefaelschtem go2rtc ---------------------------------------

class FalschesGo2rtc(BaseHTTPRequestHandler):
    gesehen: list[str] = []

    def do_GET(self):  # noqa: N802
        FalschesGo2rtc.gesehen.append(self.path)
        body = b"#EXTM3U\nhls/playlist.m3u8?id=abc\n"
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def starte(handler_klasse, port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler_klasse)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def anfrage(port, pfad, token=TOKEN, methode="GET"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    kopf = {"x-stallwache-token": token} if token is not None else {}
    c.request(methode, pfad, headers=kopf)
    r = c.getresponse()
    return r.status, r.read()


def test_ganzer_weg():
    go = starte(FalschesGo2rtc)
    fp.Handler.token = TOKEN
    fp.Handler.go2rtc_port = go.server_address[1]
    fp.Handler.quelle = "stallwache_sd"
    proxy = starte(fp.Handler)
    p = proxy.server_address[1]
    try:
        FalschesGo2rtc.gesehen.clear()
        assert anfrage(p, "/api/stream.m3u8", token=None)[0] == 403
        assert anfrage(p, "/api/stream.m3u8", token="falsch")[0] == 403
        assert anfrage(p, "/api/streams")[0] == 404          # go2rtc-API bleibt zu
        assert anfrage(p, "/api/config")[0] == 404
        assert anfrage(p, "/api/stream.m3u8", methode="POST")[0] == 405
        assert FalschesGo2rtc.gesehen == [], "unerlaubte Anfragen duerfen go2rtc nie erreichen"

        status, koerper = anfrage(p, "/api/stream.m3u8?src=rollei")
        assert status == 200 and b"#EXTM3U" in koerper
        assert FalschesGo2rtc.gesehen == ["/api/stream.m3u8?src=stallwache_sd"]
    finally:
        proxy.shutdown()
        go.shutdown()


def test_go2rtc_down_ergibt_502():
    fp.Handler.token = TOKEN
    fp.Handler.go2rtc_port = 1            # nichts lauscht dort
    proxy = starte(fp.Handler)
    try:
        assert anfrage(proxy.server_address[1], "/api/stream.m3u8")[0] == 502
    finally:
        proxy.shutdown()


if __name__ == "__main__":
    fehl = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as e:  # noqa: BLE001
                fehl += 1
                print(f"FEHL {name}: {type(e).__name__}: {e}")
    sys.exit(1 if fehl else 0)
