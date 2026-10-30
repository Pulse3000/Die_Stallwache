"""Tests: Aufloesung der Kamera als Beleg und ehrlicher Modell-Umfang.

1. Der Agent loggt, welche Aufloesung WIRKLICH ankommt (einmal je Wechsel),
   warnt unter stream.min_breite (Substream statt Hauptstream/2K) und nennt
   sie im Tagesbericht.
2. Ein Modell der Brunst-Phase (nur Kuh-Boxen) bedient Austreibung und
   Kalbeverdacht nicht. Das steht in Start- und Tagesmeldung und geht als
   ``nicht_scharf`` im Lebenszeichen an die App, die dann nie „OK" sagt
   (docs/brunst-zuerst-entscheidung.md).

    python3 edge-agent/tests/test_aufloesung_umfang.py
"""

import logging
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main  # noqa: E402

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Aufloesung & Modell-Umfang")


class Sammler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.zeilen: list[tuple[int, str]] = []

    def emit(self, record):
        self.zeilen.append((record.levelno, record.getMessage()))


sammler = Sammler()
logging.getLogger().addHandler(sammler)
logging.getLogger().setLevel(logging.INFO)


def bild(h, w):
    return types.SimpleNamespace(shape=(h, w, 3))


# --- 1. Aufloesung ------------------------------------------------------------
sh = m.StreamHandler({"stream": {"url": "aufnahme.mp4"}})
p.check("1: Default min_breite 1280 (erkennt Unterstream, drängt nicht zu 2K)", sh.min_breite == 1280)
p.check("1: vor dem ersten Bild keine Aufloesung", sh.aufloesung is None)

sh._pruefe_aufloesung(bild(1440, 2560), "Livestream")
p.check("1: 2K -> gemerkt", sh.aufloesung == (2560, 1440))
p.check("1: 2K -> INFO mit Aufloesung",
        any(lv == logging.INFO and "2560x1440" in z for lv, z in sammler.zeilen))
p.check("1: 2K -> keine Warnung", not any(lv >= logging.WARNING for lv, _ in sammler.zeilen))

sammler.zeilen.clear()
for _ in range(50):
    sh._pruefe_aufloesung(bild(1440, 2560), "Livestream")
p.check("1: gleiche Aufloesung -> kein weiteres Log (1/s waere eine Flut)", sammler.zeilen == [])

sh._pruefe_aufloesung(bild(360, 640), "Livestream")
warnungen = [z for lv, z in sammler.zeilen if lv == logging.WARNING]
p.check("1: Substream 640x360 -> genau eine Warnung", len(warnungen) == 1)
p.check("1: Warnung nennt Hauptstream und 2K",
        warnungen and "stream1" in warnungen[0] and "Unterstream" in warnungen[0] and "640x360" in warnungen[0])

sh0 = m.StreamHandler({"stream": {"url": "aufnahme.mp4", "min_breite": 0}})
sammler.zeilen.clear()
sh0._pruefe_aufloesung(bild(360, 640), "Datei")
p.check("1: min_breite 0 -> keine Warnung, nur INFO",
        sammler.zeilen and all(lv == logging.INFO for lv, _ in sammler.zeilen))

sammler.zeilen.clear()
sh._pruefe_aufloesung(object(), "Datei")  # kein shape
p.check("1: Bild ohne shape -> wirft nicht, kein Log", sammler.zeilen == [])

# --- 2. Modell-Umfang ----------------------------------------------------------
KLASSEN = {"kuh": 0, "amniotic_sac": 1, "calf_legs": 2}
TIERE = {"kuh"}
ns = m.nicht_scharf

p.check("2: volles Pose-Modell -> alles scharf",
        ns({0: "kuh", 1: "amniotic_sac", 2: "calf_legs"}, "pose", KLASSEN, TIERE) == [])
p.check("2: Brunst-Modell (nur kuh, detect) -> Austreibung + Kalbeverdacht fehlen",
        ns({0: "kuh"}, "detect", KLASSEN, TIERE) == ["austreibung", "kalbeverdacht"])
p.check("2: Brunst-Modell (nur kuh, pose) -> nur Austreibung fehlt",
        ns({0: "kuh"}, "pose", KLASSEN, TIERE) == ["austreibung"])
p.check("2: nur Fruchtblase, keine Fuesse -> Austreibung nicht scharf",
        ns({0: "kuh", 1: "amniotic_sac"}, "pose", KLASSEN, TIERE) == ["austreibung"])
coco = {i: f"klasse{i}" for i in range(80)}
coco.update({0: "person", 1: "bicycle", 2: "car", 19: "cow"})
p.check("2: COCO-Modell mit Standard-Indizes -> Austreibung NICHT scharf (bicycle/car)",
        "austreibung" in ns(coco, "detect", {"kuh": 19, "amniotic_sac": 1, "calf_legs": 2}, TIERE))
p.check("2: COCO-Modell: Kuh auf 19 -> Brunst scharf",
        "brunst" not in ns(coco, "detect", {"kuh": 19, "amniotic_sac": 1, "calf_legs": 2}, TIERE))
p.check("2: Liste statt dict (names als Liste)",
        ns(["kuh", "amniotic_sac", "calf_legs"], "pose", KLASSEN, TIERE) == [])
p.check("2: Gross/Klein im Modellnamen egal",
        ns({0: "Kuh", 1: "Amniotic_Sac", 2: "CALF_LEGS"}, "pose", KLASSEN, TIERE) == [])
p.check("2: Modell ohne Tierklasse -> nichts ausser ggf. Austreibung",
        ns({1: "amniotic_sac", 2: "calf_legs"}, "pose", KLASSEN, TIERE) == ["brunst", "kalbeverdacht"])
# Im Zweifel weniger behaupten (Befund ki-wache S6 / qa-waechter H2): [] hiesse
# fuer die App „alles scharf".
p.check("2: names unbekannt (None) -> nichts scharf", ns(None, None, KLASSEN, TIERE) == list(m.ALARMWEGE))
p.check("2: task unbekannt -> Kalbeverdacht nicht scharf",
        ns({0: "kuh", 1: "amniotic_sac", 2: "calf_legs"}, None, KLASSEN, TIERE) == ["kalbeverdacht"])
p.check("2: freigegeben fehlt in der Konfig -> nichts freigegeben, mit Warnhinweis",
        m.freigabe_aus_konfig({}) == ([], True) and m.freigabe_aus_konfig({"freigegeben": None}) == ([], True))
p.check("2: freigegeben gesetzt -> unveraendert durchgereicht",
        m.freigabe_aus_konfig({"freigegeben": ["brunst"]}) == (["brunst"], False))

VOLL = {0: "kuh", 1: "amniotic_sac", 2: "calf_legs"}
p.check("2: freigegeben [brunst] -> Kalbe-Wege nicht scharf, auch wenn das Modell sie traegt",
        ns(VOLL, "pose", KLASSEN, TIERE, ["brunst"]) == ["austreibung", "kalbeverdacht"])
p.check("2: freigegeben alle -> alles scharf",
        ns(VOLL, "pose", KLASSEN, TIERE, ["brunst", "austreibung", "kalbeverdacht"]) == [])
p.check("2: Freigabe macht nichts scharf, was das Modell nicht kann",
        ns({0: "kuh"}, "detect", KLASSEN, TIERE, ["brunst", "austreibung"]) == ["austreibung", "kalbeverdacht"])
p.check("2: freigegeben [] -> nichts scharf", ns(VOLL, "pose", KLASSEN, TIERE, []) == list(m.ALARMWEGE))
p.check("2: freigegeben als Text (ohne Klammern) -> wie Liste mit einem Eintrag",
        ns(VOLL, "pose", KLASSEN, TIERE, "brunst") == ["austreibung", "kalbeverdacht"])
p.check("2: freigegeben unsinniger Typ -> nichts scharf (im Zweifel weniger behaupten)",
        ns(VOLL, "pose", KLASSEN, TIERE, {"brunst": True}) == list(m.ALARMWEGE))
p.check("2: Reihenfolge immer brunst, austreibung, kalbeverdacht",
        ns({1: "amniotic_sac", 2: "calf_legs"}, "detect", KLASSEN, TIERE, ["austreibung"]) == ["brunst", "kalbeverdacht"])

text = m.umfang_text(["austreibung", "kalbeverdacht"])
p.check("2: Text nennt scharf und NICHT scharf",
        text.startswith("Scharf: Brunst (Aufsprung)") and "NICHT scharf: Austreibung" in text
        and "Kalbeverdacht" in text)
p.check("2: alles scharf -> kein NICHT", "NICHT" not in m.umfang_text([]))
p.check("2: Austreibung nicht scharf -> Handlungsanweisung zu Geburten",
        text.endswith("Geburten erkennt die KI damit nicht – Kalbungen bitte wie bisher selbst kontrollieren."))
nur_kv = m.umfang_text(["kalbeverdacht"])
p.check("2: nur Kalbeverdacht nicht scharf -> Beobachtung vor dem Termin, Geburten werden gemeldet (ki-wache H4)",
        "Wehenzeichen vorher nicht" in nur_kv and "Geburten erkennt die KI damit nicht" not in nur_kv)
p.check("2: nur Brunst nicht scharf -> keine Kalbe-Anweisung",
        "Kalbungen" not in m.umfang_text(["brunst"]))

# --- 3. Lebenszeichen ------------------------------------------------------------
lz = m.Lebenszeichen({"dashboard": {"url": "https://app/api/events", "token": "t"},
                      "stream": {"kamera": "stallwache"}})
lz._sende = lambda nutzlast: gesendet.append(("lz", nutzlast))
lz.tick(True, True, jetzt=1000.0)
lz._thread.join(1)
p.check("3: ohne Angabe (alter Weg) kein nicht_scharf-Feld",
        "nicht_scharf" not in gesendet[-1][1]["lebenszeichen"])
lz.nicht_scharf = ["austreibung", "kalbeverdacht"]
lz.tick(True, True, jetzt=2000.0)
lz._thread.join(1)
p.check("3: Analyse -> nicht_scharf gemeldet",
        gesendet[-1][1]["lebenszeichen"].get("nicht_scharf") == ["austreibung", "kalbeverdacht"])
lz.tick(False, True, jetzt=3000.0)
lz._thread.join(1)
p.check("3: Silent -> kein nicht_scharf (dort sagt der Modus schon alles)",
        "nicht_scharf" not in gesendet[-1][1]["lebenszeichen"])
lz.nicht_scharf = []
lz.tick(True, True, jetzt=4000.0)
lz._thread.join(1)
p.check("3: alles scharf -> leere Liste (nicht fehlend)",
        gesendet[-1][1]["lebenszeichen"].get("nicht_scharf") == [])

# --- 4. Tagesbericht -------------------------------------------------------------
engine = types.SimpleNamespace(aktiv=True, nicht_scharf=["austreibung", "kalbeverdacht"])
zeilen = m.tagesbericht_zusatz(sh, engine)
p.check("4: Tagesbericht nennt Umfang", any("NICHT scharf" in z for z in zeilen))
p.check("4: Tagesbericht nennt Aufloesung mit Warnung",
        any(z.startswith("Bild: 640×360") and "Unterstream" in z for z in zeilen))
sh2 = m.StreamHandler({"stream": {"url": "aufnahme.mp4"}})
sh2._pruefe_aufloesung(bild(1440, 2560), "Livestream")
zeilen = m.tagesbericht_zusatz(sh2, types.SimpleNamespace(aktiv=False, nicht_scharf=[]))
p.check("4: Silent + 2K -> nur Bildzeile ohne Warnung", zeilen == ["Bild: 2560×1440"])

# --- 5. Tagesbericht: „nicht überwacht" statt 0 --------------------------------
tg = []
n5 = m.Notifier({"telegram": {"token": "T", "chat_id": "1", "digest_uhrzeit": "00:00"},
                 "stream": {"kamera": "stallwache"}})
n5._tg.auftrag = lambda fn, *a, **kw: tg.append(a)
n5.nicht_scharf = ["austreibung", "kalbeverdacht"]
n5._zaehler["brunstverdacht"] += 2
n5.digest_tick(True)
bericht = tg[-1][0] if tg else ""
p.check("5: Brunst-Phase -> Austreibung/Kalbeverdacht „nicht überwacht“, Brunst gezaehlt",
        "Kalbeverdacht: nicht überwacht · Austreibung: nicht überwacht · Brunstverdacht: 2" in bericht)
n7 = m.Notifier({"telegram": {"token": "T", "chat_id": "1", "digest_uhrzeit": "00:00"},
                 "stream": {"kamera": "stallwache"}})
n7._tg.auftrag = lambda fn, *a, **kw: tg.append(a)
n7.nicht_scharf = list(m.ALARMWEGE)          # z. B. freigegeben: [] vor der Abnahme
n7._zaehler["brunstverdacht"] += 3
n7.digest_tick(True)
p.check("5: zugestellte Alarme eines nicht abgenommenen Wegs werden nie verschwiegen (ki-wache S4)",
        "Brunstverdacht: 3 (nicht abgenommen – bitte am Bild prüfen)" in tg[-1][0]
        and "Austreibung: nicht überwacht" in tg[-1][0])
n6 = m.Notifier({"telegram": {"token": "T", "chat_id": "1", "digest_uhrzeit": "00:00"},
                 "stream": {"kamera": "stallwache"}})
n6._tg.auftrag = lambda fn, *a, **kw: tg.append(a)
n6.nicht_scharf = ["austreibung", "kalbeverdacht"]
n6.digest_tick(False)
p.check("5: Silent Mode -> Zahlen wie bisher (Modus steht in der Zeile darueber)",
        "Austreibung: 0" in tg[-1][0])

sys.exit(p.bericht())
