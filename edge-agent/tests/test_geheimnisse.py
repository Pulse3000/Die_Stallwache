#!/usr/bin/env python3
"""Logiktests: Der Telegram-Bot-Token steht in keiner Logzeile.

requests nennt in Fehlermeldungen die URL, bei Telegram samt Token
(/bot<TOKEN>/getUpdates) – solange Telegram nicht erreichbar ist, alle 10 s.
Im Container bleibt das Log ueber `docker logs` lesbar (Befund qa-waechter
zu PR #89). Der GeheimFilter schwaerzt den Token in jeder Zeile und in
Tracebacks. HTTP ist gestubbt; es geht kein Request raus.
"""

import io
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main  # noqa: E402

m, _ = lade_main(mit_requests_stub=True)
p = Pruefer("Geheimnisse im Log")

TOKEN = "123456789:AAH-geheimes-token-XYZ"
puffer = io.StringIO()
handler = logging.StreamHandler(puffer)
handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.DEBUG)


class Netzfehler(m.requests.RequestException):
    pass


def get_mit_fehler(url, **kw):
    # Wie requests: Die Meldung nennt die URL samt Token.
    raise Netzfehler(f"HTTPSConnectionPool(host='api.telegram.org', port=443): "
                     f"Max retries exceeded with url: /bot{TOKEN}/getUpdates?offset=0")


m.requests.get = get_mit_fehler
fb = m.FeedbackSchleife({"telegram": {"token": TOKEN, "chat_id": "42"}})

# --- 1. Feedback-Abruf scheitert: Warnung ohne Token ------------------------
fb._abrufen(0)
text = puffer.getvalue()
p.check("1: Warnung wird geloggt", "Feedback-Abruf fehlgeschlagen" in text)
p.check("1: Token steht nicht in der Zeile", TOKEN not in text)
p.check("1: an seiner Stelle ***", "/bot***/getUpdates" in text)

# --- 2. Traceback (log.exception) ohne Token -------------------------------
puffer.truncate(0)
puffer.seek(0)
try:
    raise RuntimeError(f"https://api.telegram.org/bot{TOKEN}/sendMediaGroup")
except RuntimeError:
    m.log.exception("Telegram-Versand: unerwarteter Fehler")
text = puffer.getvalue()
p.check("2: Traceback wird geloggt", "Traceback" in text and "RuntimeError" in text)
p.check("2: Token steht nicht im Traceback", TOKEN not in text)

# --- 3. Platzhalter-Argumente werden korrekt eingesetzt --------------------
puffer.truncate(0)
puffer.seek(0)
m.log.info("Lebenszeichen zugestellt (nach %d Fehlversuchen) an %s", 3, "Dashboard")
p.check("3: normale Zeile unveraendert",
        "Lebenszeichen zugestellt (nach 3 Fehlversuchen) an Dashboard" in puffer.getvalue())

# --- 4. Fehlerhafter Aufruf wirft nie an der Aufrufstelle (H1) -------------
# Ohne Filter meldet logging nur "--- Logging error ---" auf stderr; der
# Filter darf daraus keine Ausnahme im Agenten machen.
import contextlib  # noqa: E402

geworfen = []
with contextlib.redirect_stderr(io.StringIO()):
    for aufruf in (lambda: m.log.warning("x %s %s", 1), lambda: m.log.warning("n=%d", None)):
        try:
            aufruf()
        except Exception as e:  # noqa: BLE001
            geworfen.append(repr(e))
p.check(f"4: fehlerhafte Platzhalter werfen nicht ({geworfen or 'ok'})", not geworfen)

# --- 5. Kurze/leere Werte werden nicht geschwaerzt -------------------------
vorher = set(m.GEHEIM.geheim)
m.GEHEIM.merke("")
m.GEHEIM.merke("42")
p.check("5: leere und kurze Werte nicht gemerkt", m.GEHEIM.geheim == vorher)

sys.exit(p.bericht())
