#!/usr/bin/env python3
"""Logiktests Offline-Puffer der Dashboard-Meldung.

Geprueft wird die Zusage, auf der die ganze App aufbaut: Faellt im Stall das
Netz aus, geht kein Alarm verloren. Er landet auf der Platte, ueberlebt einen
Neustart des Agenten und wird beim naechsten Kontakt mit dem urspruenglichen
Zeitstempel nachgeliefert. HTTP ist komplett gestubbt — es geht nie ein
echter Request raus.
"""

import base64
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Offline-Puffer")

tmp = Path(tempfile.mkdtemp())
puffer = tmp / "alarm-puffer.jsonl"


def notifier(**db_extra):
    """Notifier ohne Telegram/MQTT — nur der Dashboard-Weg zaehlt hier."""
    cfg = {
        "stream": {"kamera": "stallwache"},
        "telegram": {},
        "dashboard": {
            "url": "https://beispiel.test/api/events",
            "token": "T",
            "puffer_datei": str(puffer),
            **db_extra,
        },
    }
    return m.Notifier(cfg)


def netz_aus():
    def wirft(url, **kw):
        raise m.requests.RequestException("kein Netz")

    m.requests.post = wirft


def netz_an():
    antwort = type("A", (), {"raise_for_status": staticmethod(lambda: None)})()
    m.requests.post = lambda url, **kw: (gesendet.append((url, kw)), antwort)[1]


alarm1 = m.Alarm("austreibung", "Kuh #42", "Fruchtblase erkannt", 0.87, None)
alarm2 = m.Alarm("brunstverdacht", "Kuh #17", "Aufsprung erkannt", 0.71, None)

# --- 1. Netzausfall: Alarm landet im Puffer, nichts geht raus --------------
netz_aus()
n = notifier()
n._dashboard(alarm1, [b"jpeg-a", b"jpeg-b"])
p.check("bei Netzausfall gepuffert", len(n._puffer) == 1)
p.check("Pufferdatei geschrieben", puffer.exists())

gespeichert = json.loads(puffer.read_text("utf-8").splitlines()[0])
p.check("Typ erhalten", gespeichert["typ"] == "austreibung")
p.check("Kuh-ID erhalten", gespeichert["kuhId"] == "Kuh #42")
p.check("Zeitstempel des Ereignisses gesetzt", gespeichert["zeit"].endswith("Z"))
p.check("Bilder base64-kodiert mitgepuffert", len(gespeichert["bilder"]) == 2)

# --- 2. Neustart des Agenten: Puffer wird wieder eingelesen ---------------
n2 = notifier()
p.check("Puffer ueberlebt Neustart", len(n2._puffer) == 1)

# --- 3. Netz zurueck: alter + neuer Alarm gehen als ein Stapel raus -------
netz_an()
gesendet.clear()
n2._dashboard(alarm2, None)
p.check("genau eine Anfrage", len(gesendet) == 1)

koerper = gesendet[0][1]["json"]
p.check("als Stapel gesendet", "ereignisse" in koerper)
p.check("beide Ereignisse im Stapel", len(koerper["ereignisse"]) == 2)
p.check("Reihenfolge: gepuffertes zuerst", koerper["ereignisse"][0]["typ"] == "austreibung")
p.check(
    "Ingest-Token im Header",
    gesendet[0][1]["headers"]["x-ingest-token"] == "T",
)
p.check("Puffer nach Erfolg leer", len(n2._puffer) == 0)
p.check("Pufferdatei nach Erfolg entfernt", not puffer.exists())

# --- 4. Bildgrenze: hoechstens `bilder` Stueck, aelteste fallen weg -------
gesendet.clear()
n3 = notifier(bilder=2)
n3._dashboard(alarm1, [b"alt", b"mitte", b"neu"])
bilder = gesendet[0][1]["json"]["ereignisse"][0]["bilder"]
p.check("auf konfigurierte Anzahl begrenzt", len(bilder) == 2)
p.check(
    "juengste Bilder behalten (Alarmbild zuletzt)",
    [base64.b64decode(b) for b in bilder] == [b"mitte", b"neu"],
)

gesendet.clear()
n4 = notifier(bilder=0)
n4._dashboard(alarm1, [b"x"])
p.check(
    "bilder=0 sendet reinen Text",
    "bilder" not in gesendet[0][1]["json"]["ereignisse"][0],
)

# --- 5. Auswahl der Bilder: annotiertes Alarmbild zuletzt -----------------
n5 = notifier(bilder=3)
auswahl = n5._dashboard_bilder([b"v1", b"v2"], b"alarm")
p.check("Alarmbild ist das letzte", auswahl[-1] == b"alarm")
p.check("Verlauf davor", auswahl[0] == b"v1")
p.check(
    "ohne Alarmbild nur der Verlauf",
    n5._dashboard_bilder([b"v1"], None) == [b"v1"],
)

# --- 6. Pufferobergrenze: aelteste Eintraege fallen raus ------------------
netz_aus()
n6 = notifier(puffer_max=3)
for i in range(5):
    n6._dashboard(m.Alarm("info", None, f"Meldung {i}", None, None), None)
p.check("Puffer respektiert Obergrenze", len(n6._puffer) == 3)
p.check("aelteste verdraengt", n6._puffer[0]["nachricht"] == "Meldung 2")

# --- 7. Ohne Dashboard-Konfiguration passiert gar nichts ------------------
gesendet.clear()
netz_an()
n7 = m.Notifier({"stream": {"kamera": "stallwache"}, "telegram": {}, "dashboard": {}})
n7._dashboard(alarm1, [b"x"])
p.check("ohne url/token kein Request", len(gesendet) == 0)

sys.exit(p.bericht())
