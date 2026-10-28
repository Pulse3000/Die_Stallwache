#!/usr/bin/env python3
"""Logiktests Zeitzone (docs/roadmap.md „Zeitzone"): Ortszeit fuer Menschen,
UTC fuer Dateinamen und Maschinen.

Zusagen:
  * Der Tagesbericht kommt zur eingestellten Ortszeit – im Sommer, im Winter
    und an beiden Umstellungstagen, genau einmal am Tag.
  * Trainingsbild-Namen bleiben im bisherigen Format und sind UTC, egal
    welche TZ der Prozess hat: keine Luecke und kein Doppel bei der
    Zeitumstellung, Split nach Stalltagen unveraendert.
  * Eine TZ, die nicht greift (Tippfehler, tzdata fehlt), meldet der Agent.

Die Zone wird je Fall per TZ + time.tzset() umgestellt. Die POSIX-Regel der
EU (CET-1CEST,M3.5.0,M10.5.0/3) braucht kein tzdata; Europe/Berlin wird
zusaetzlich geprueft, wenn die Zonendatei auf dem Testrechner liegt.
"""

import calendar
import importlib.util
import itertools
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

if not hasattr(time, "tzset"):
    print("Zeitzone: time.tzset fehlt (kein Unix) – uebersprungen")
    sys.exit(0)

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Zeitzone")

WURZEL = Path(__file__).resolve().parent.parent
EU_REGEL = "CET-1CEST,M3.5.0,M10.5.0/3"
ZONEN = [EU_REGEL]
if Path("/usr/share/zoneinfo/Europe/Berlin").is_file():
    ZONEN.append("Europe/Berlin")


def setze_tz(wert: str | None) -> None:
    if wert is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = wert
    time.tzset()


def utc(j, mo, d, h, mi=0, s=0) -> float:
    return float(calendar.timegm((j, mo, d, h, mi, s, 0, 0, 0)))


def lade_datensatz():
    spec = importlib.util.spec_from_file_location("datensatz", WURZEL / "training" / "datensatz.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules["datensatz"] = modul
    spec.loader.exec_module(modul)
    return modul


ds = lade_datensatz()
TMP = Path(tempfile.mkdtemp())


def neuer_notifier(uhrzeit="20:00"):
    return m.Notifier({
        "stream": {"kamera": "stallwache"},
        "telegram": {"token": "T", "chat_id": "C", "digest_uhrzeit": uhrzeit,
                     "feedback_buttons": False, "fehlalarm_ordner": str(TMP / "fa")},
        "dashboard": {"puffer_datei": str(TMP / "puffer.jsonl")},
    })


def berichte(nt, t) -> int:
    """Anzahl Tagesberichte, die ein digest_tick zum Zeitpunkt t ausloest."""
    gesendet.clear()
    nt.digest_tick(False, jetzt=t)
    nt.warte()
    return sum(1 for url, _ in gesendet if url.endswith("/sendMessage"))


# --- 1. Tagesbericht zur eingestellten Ortszeit ------------------------------

for zone in ZONEN:
    setze_tz(zone)
    z = f"[{zone.split(',')[0]}]"

    nt = neuer_notifier()
    # Sommerzeit (MESZ, UTC+2): Samstag vor der Umstellung
    p.check(f"1 {z} Sommer 19:59 MESZ: kein Bericht", berichte(nt, utc(2026, 10, 24, 17, 59)) == 0)
    p.check(f"1 {z} Sommer 20:00 MESZ: Bericht", berichte(nt, utc(2026, 10, 24, 18, 0)) == 1)
    p.check(f"1 {z} Sommer 23:59 MESZ: kein zweiter", berichte(nt, utc(2026, 10, 24, 21, 59)) == 0)
    # Umstellungstag 25.10.2026 (03:00 MESZ -> 02:00 MEZ)
    p.check(f"1 {z} Umstellung Herbst 00:30 MESZ: kein Bericht (neuer Tag, vor 20:00)",
            berichte(nt, utc(2026, 10, 24, 22, 30)) == 0)
    p.check(f"1 {z} Umstellung Herbst 19:59 MEZ: kein Bericht", berichte(nt, utc(2026, 10, 25, 18, 59)) == 0)
    p.check(f"1 {z} Umstellung Herbst 20:00 MEZ: Bericht", berichte(nt, utc(2026, 10, 25, 19, 0)) == 1)
    # Winter (MEZ, UTC+1): ohne TZ kam er hier erst um 21:00 (20:00 UTC)
    p.check(f"1 {z} Winter 19:59 MEZ: kein Bericht", berichte(nt, utc(2026, 10, 28, 18, 59)) == 0)
    p.check(f"1 {z} Winter 20:00 MEZ (19:00 UTC): Bericht", berichte(nt, utc(2026, 10, 28, 19, 0)) == 1)
    p.check(f"1 {z} Winter 21:00 MEZ: kein zweiter", berichte(nt, utc(2026, 10, 28, 20, 0)) == 0)
    p.check(f"1 {z} Tag des Berichts in Ortszeit gemerkt", nt._digest_tag == "2026-10-28")
    # Umstellungstag 28.03.2027 (02:00 MEZ -> 03:00 MESZ)
    p.check(f"1 {z} Umstellung Fruehjahr 19:59 MESZ: kein Bericht",
            berichte(nt, utc(2027, 3, 28, 17, 59)) == 0)
    p.check(f"1 {z} Umstellung Fruehjahr 20:00 MESZ: Bericht", berichte(nt, utc(2027, 3, 28, 18, 0)) == 1)

    # Uhrzeit in der doppelten Stunde: genau ein Bericht, nicht zwei
    nacht = neuer_notifier("02:30")
    p.check(f"1 {z} 02:30 am Herbst-Umstellungstag (MESZ): Bericht",
            berichte(nacht, utc(2026, 10, 25, 0, 30)) == 1)
    p.check(f"1 {z} 02:30 am Herbst-Umstellungstag (MEZ, zweites Mal): kein zweiter",
            berichte(nacht, utc(2026, 10, 25, 1, 30)) == 0)
    # Uhrzeit in der fehlenden Stunde: kommt zur ersten Minute danach, einmal
    p.check(f"1 {z} 02:30 am Fruehjahrs-Umstellungstag: 01:59 MEZ noch nicht",
            berichte(nacht, utc(2027, 3, 28, 0, 59)) == 0)
    p.check(f"1 {z} 02:30 am Fruehjahrs-Umstellungstag: 03:00 MESZ Bericht",
            berichte(nacht, utc(2027, 3, 28, 1, 0)) == 1)
    p.check(f"1 {z} 02:30 am Fruehjahrs-Umstellungstag: danach kein zweiter",
            berichte(nacht, utc(2027, 3, 28, 1, 30)) == 0)

# Gegenprobe: ohne Zonenangabe gilt UTC – genau der Befund (21:00 statt 20:00)
setze_tz("UTC")
nt = neuer_notifier()
p.check("1 Gegenprobe UTC: um 20:00 MEZ (19:00 UTC) noch kein Bericht",
        berichte(nt, utc(2026, 10, 28, 19, 0)) == 0)
p.check("1 Gegenprobe UTC: erst um 21:00 MEZ (20:00 UTC)", berichte(nt, utc(2026, 10, 28, 20, 0)) == 1)

# --- 2. Uhrzeit aus der Config -------------------------------------------------

p.check("2 \"20:00\" bleibt", m.lies_uhrzeit("20:00", "x") == "20:00")
p.check("2 \"8:00\" wird zweistellig (Textvergleich)", m.lies_uhrzeit("8:00", "x") == "08:00")
p.check("2 unquotiertes 20:00 (YAML: 1200 zur Basis 60) wird 20:00", m.lies_uhrzeit(1200, "x") == "20:00")
p.check("2 leer, None und 0 bleiben aus", all(m.lies_uhrzeit(w, "x") == "" for w in ("", "  ", None, 0)))
p.check("2 Ungueltiges schaltet ab statt nie/sofort zu senden",
        all(m.lies_uhrzeit(w, "x") == "" for w in ("25:00", "20:60", "abc", "20.00", "20:00:00", True)))
p.check("2 Notifier startet mit unquotiertem 20:00", neuer_notifier(1200).digest_uhrzeit == "20:00")

# --- 3. Trainingsbild-Namen: bisheriges Format, immer UTC ------------------------

FORMAT = re.compile(r"stallwache_\d{8}-\d{6}\.jpg")
fest = utc(2026, 10, 16, 3, 15)
namen_je_zone = {}
for zone in ["UTC", *ZONEN]:
    setze_tz(zone)
    namen_je_zone[zone] = m.trainingsbild_name("stallwache", fest)
    p.check(f"3 [{zone.split(',')[0]}] Format <kamera>_JJJJMMTT-HHMMSS.jpg",
            FORMAT.fullmatch(namen_je_zone[zone]) is not None)
p.check("3 Name ist UTC, unabhaengig von TZ",
        set(namen_je_zone.values()) == {"stallwache_20261016-031500.jpg"})

for zone in ZONEN:
    setze_tz(zone)
    z = f"[{zone.split(',')[0]}]"
    for titel, start, ende in (
        ("Herbst", utc(2026, 10, 24, 22, 0), utc(2026, 10, 25, 3, 0)),
        ("Fruehjahr", utc(2027, 3, 27, 23, 0), utc(2027, 3, 28, 4, 0)),
    ):
        zeiten = [start + i * 120 for i in range(int((ende - start) / 120) + 1)]
        namen = [m.trainingsbild_name("stallwache", t) for t in zeiten]
        p.check(f"3 {z} Umstellung {titel}: kein Doppel (nichts ueberschrieben)",
                len(set(namen)) == len(namen))
        p.check(f"3 {z} Umstellung {titel}: Namensordnung = Aufnahmeordnung", namen == sorted(namen))
        gelesen = [calendar.timegm(ds.zeit_aus_name(n).timetuple()) for n in namen]
        p.check(f"3 {z} Umstellung {titel}: keine Luecke (Abstand stets 120 s)",
                all(b - a == 120 for a, b in itertools.pairwise(gelesen)))
        p.check(f"3 {z} Umstellung {titel}: Split liest die Aufnahmezeit zurueck",
                [float(g) for g in gelesen] == zeiten)

    # Stalltag-Wechsel 12:00 UTC (13:00 MEZ/14:00 MESZ): die Nacht bleibt ganz
    for titel, abend, morgen in (
        ("Winter", utc(2026, 11, 3, 17, 0), utc(2026, 11, 4, 5, 0)),   # 18:00-06:00 MEZ
        ("Sommer", utc(2027, 6, 15, 16, 0), utc(2027, 6, 16, 4, 0)),   # 18:00-06:00 MESZ
    ):
        tage = {ds.stalltag(ds.zeit_aus_name(m.trainingsbild_name("stallwache", t)))
                for t in range(int(abend), int(morgen) + 1, 1800)}
        p.check(f"3 {z} Nacht 18-06 Uhr Ortszeit ({titel}) liegt in einem Stalltag", len(tage) == 1)

# --- 4. Bildbestand im Lebenszeichen rechnet in derselben Zeit wie die Namen ---

for zone in ZONEN:
    setze_tz(zone)
    z = f"[{zone.split(',')[0]}]"
    jetzt = utc(2026, 10, 25, 1, 30)  # in der doppelten Stunde
    ordner = Path(tempfile.mkdtemp()) / "aufnahmen"
    ordner.mkdir()
    for t in (jetzt - 86400 - 60, jetzt - 86400 + 60, jetzt - 3600, jetzt - 120):
        (ordner / m.trainingsbild_name("stallwache", t)).write_bytes(b"x")
    lz = m.Lebenszeichen({"stream": {"kamera": "stallwache"},
                          "dashboard": {"url": "http://x", "token": "T"},
                          "silent_mode": {"ordner": str(ordner)}})
    b = lz.bildbestand(jetzt)
    p.check(f"4 {z} 24-h-Grenze minutengenau (nicht um die UTC-Abweichung verschoben)",
            b is not None and b["trainingsbilder"] == 4 and b["trainingsbilder_24h"] == 3)
    p.check(f"4 {z} juengstes Bild als UTC-Zeit", b and b.get("trainingsbild_zuletzt") == "2026-10-25T01:28:00Z")

# --- 5. Maschinen-Zeitstempel in UTC ----------------------------------------------

setze_tz(ZONEN[-1])


class MqttStub:
    def __init__(self):
        self.nachrichten = []

    def publish(self, topic, nutzlast):
        self.nachrichten.append((topic, json.loads(nutzlast)))


nt = neuer_notifier()
nt._mqtt_client = MqttStub()
nt._mqtt(m.Alarm("kalbeverdacht", "Kuh #3", "T", None, None))
zeit = nt._mqtt_client.nachrichten[-1][1]["zeit"]
p.check("5 MQTT-Zeit ist UTC mit Z (eindeutig ueber die Zeitumstellung)",
        re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", zeit) is not None)
p.check("5 MQTT-Zeit stimmt mit der Uhr (± 5 s)",
        abs(calendar.timegm(time.strptime(zeit, "%Y-%m-%dT%H:%M:%SZ")) - time.time()) <= 5)
p.check("5 utc_iso endet auf Z", m.utc_iso().endswith("Z"))

# --- 6. Pruefung beim Start: TZ, die nicht greift, wird gemeldet ---------------

setze_tz(None)
p.check("6 ohne TZ (Zeitzone des Rechners): keine Warnung", m.zeitzone_warnung() is None)
setze_tz(EU_REGEL)
p.check("6 POSIX-Regel ohne tzdata: keine Warnung", m.zeitzone_warnung() is None)
setze_tz("UTC")
p.check("6 TZ=UTC: keine Warnung", m.zeitzone_warnung() is None)
setze_tz("Europe/Berln")
warnung = m.zeitzone_warnung(utc(2026, 10, 28, 12, 0))
p.check("6 Tippfehler Europe/Berln: Warnung mit Zonenname",
        warnung is not None and "TZ=Europe/Berln" in warnung and "tzdata" in warnung)
if "Europe/Berlin" in ZONEN:
    setze_tz("Europe/Berlin")
    p.check("6 Europe/Berlin mit Zonendatei: keine Warnung (Sommer und Winter)",
            m.zeitzone_warnung(utc(2026, 7, 1, 12)) is None
            and m.zeitzone_warnung(utc(2026, 12, 1, 12)) is None)

# --- 7. Betrieb: Compose, Image und systemd setzen die Zone ----------------------

compose = (WURZEL / "docker-compose.yml").read_text(encoding="utf-8")
p.check("7 Compose setzt TZ (Default Europe/Berlin)", "- TZ=${TZ:-Europe/Berlin}" in compose)
dockerfile = (WURZEL / "Dockerfile").read_text(encoding="utf-8")
p.check("7 Image hat die Zonendateien (tzdata)",
        "/usr/share/zoneinfo/Europe/Berlin" in dockerfile and "tzdata" in dockerfile)
setup = (WURZEL / "setup.sh").read_text(encoding="utf-8")
p.check("7 setup.sh schreibt TZ in die systemd-Unit", "Environment=TZ=Europe/Berlin" in setup)

setze_tz(None)
sys.exit(p.bericht())
