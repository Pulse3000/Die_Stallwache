#!/usr/bin/env python3
"""Logiktests des Datensatz-Archivs (Zweitkopie der Trainingsbilder).

Geprueft wird die Zusage, dass die Cloud-Kopie ein Zusatz bleibt und niemals
zum Risiko wird: Ohne Konfiguration passiert nichts, der Upload blockiert die
Analyseschleife nie, eine volle Warteschlange verwirft statt zu stauen, und
ein Netzfehler reisst den Worker nicht mit. HTTP ist komplett gestubbt — es
geht nie ein echter Request raus.
"""

import base64
import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Datensatz-Archiv")


def cfg(**dashboard):
    grund = {"url": "https://app.example/api/events", "token": "geheim"}
    grund.update(dashboard)
    return {"dashboard": grund, "stream": {"kamera": "stallwache"}}


# --- Aus-Zustand: ohne ausdrueckliche Freigabe passiert nichts -------------

a = m.DatensatzArchiv(cfg())
p.check("ohne archiv-Flag inaktiv", not a.aktiv)
vorher = len(gesendet)
a.sichere("silent", [b"bild"])
p.check("inaktiv -> kein Request", len(gesendet) == vorher)

p.check(
    "ohne Token inaktiv",
    not m.DatensatzArchiv(cfg(archiv=True, token="")).aktiv,
)
p.check(
    "ohne URL inaktiv",
    not m.DatensatzArchiv(cfg(archiv=True, url="", archiv_url="")).aktiv,
)
p.check(
    "leere Bildliste -> kein Request",
    (
        lambda arch, n: (arch.sichere("silent", []), len(gesendet) == n)[1]
    )(m.DatensatzArchiv(cfg(archiv=True)), len(gesendet)),
)

# --- URL-Ableitung ---------------------------------------------------------

p.check(
    "URL aus dashboard.url abgeleitet (/api/events -> /api/datensatz)",
    m.DatensatzArchiv(cfg(archiv=True)).url == "https://app.example/api/datensatz",
)
p.check(
    "archiv_url hat Vorrang",
    m.DatensatzArchiv(cfg(archiv=True, archiv_url="https://x.example/ablage")).url
    == "https://x.example/ablage",
)

# --- Aktiver Upload --------------------------------------------------------

archiv = m.DatensatzArchiv(cfg(archiv=True))
p.check("mit archiv: true aktiv", archiv.aktiv)

vorher = len(gesendet)
archiv.sichere("fehlalarm", [b"\xff\xd8\xffeins", b"\xff\xd8\xffzwei"])
archiv._queue.join()  # wartet, bis der Worker fertig ist

p.check("Upload ausgeloest", len(gesendet) == vorher + 1)
url, kw = gesendet[-1]
p.check("Ziel-URL korrekt", url == "https://app.example/api/datensatz")
p.check(
    "Ingest-Token im Header",
    kw.get("headers", {}).get("x-ingest-token") == "geheim",
)
rumpf = kw.get("json", {})
p.check("art durchgereicht", rumpf.get("art") == "fehlalarm")
p.check("kamera durchgereicht", rumpf.get("kamera") == "stallwache")
p.check("beide Bilder uebertragen", len(rumpf.get("bilder", [])) == 2)
p.check(
    "Bilder Base64-kodiert",
    rumpf["bilder"][0] == base64.b64encode(b"\xff\xd8\xffeins").decode("ascii"),
)
p.check("Timeout gesetzt (kein Haenger)", kw.get("timeout") == archiv.TIMEOUT_S)

# --- Warteschlange voll: verwerfen statt stauen ----------------------------
# Ohne Worker-Thread konstruiert, damit der Ueberlauf deterministisch ist.

voll = m.DatensatzArchiv.__new__(m.DatensatzArchiv)
voll.aktiv = True
voll._queue = queue.Queue(maxsize=1)
voll._verworfen = 0
voll.sichere("silent", [b"passt"])
voll.sichere("silent", [b"laeuft-ueber"])
p.check("volle Warteschlange verwirft", voll._verworfen == 1)
p.check("Warteschlange bleibt begrenzt", voll._queue.qsize() == 1)
p.check(
    "sichere() blockiert nie (kehrt trotz voller Schlange zurueck)",
    voll._queue.full(),
)

# --- Netzfehler darf den Worker nicht toeten -------------------------------


def kaputt(url, **kw):
    raise Exception("Netz weg")


echte_post = sys.modules["requests"].post
sys.modules["requests"].post = kaputt
archiv.sichere("silent", [b"\xff\xd8\xffdrei"])
archiv._queue.join()
sys.modules["requests"].post = echte_post

vorher = len(gesendet)
archiv.sichere("silent", [b"\xff\xd8\xffvier"])
archiv._queue.join()
p.check("Worker lebt nach Netzfehler weiter", len(gesendet) == vorher + 1)

sys.exit(p.bericht())
