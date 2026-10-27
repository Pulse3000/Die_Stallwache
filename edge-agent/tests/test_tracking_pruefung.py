#!/usr/bin/env python3
"""Logiktests der Tracking-Pruefung (training/tracking_pruefung.py).

Die Zusagen (Skill bytetrack-tuning, „Was das Werkzeug zusagt“):
- Aus einem Video wird 1 Bild je Sekunde genommen wie im Agenten, auch wenn
  der Container die Bildzahl nicht kennt.
- Ohne --kuehe kein Urteil. Ein ✓ gibt es nie.
- ✗ nur bei bewiesenem Fehler: >= 1 ID-Wechsel oder Kurz-ID je Kuh und
  10 min, oder ein Geist ab 10 Bildern (Aussetzer bis 2 Bilder
  ueberbrueckt). Jedes Kriterium kippt das Urteil fuer sich allein.
- Kein ✗ in gesunden Szenen: Verdeckung mit neuer ID (< 1 je Kuh / 10 min),
  auch am Clip-Rand; Doppelrahmen beim Aufstehen; Rauschen; Teilboxen.
- Jeder Ort mit >= 60 Bildern ohne ID wird als Stelle genannt, wenn die
  Erkennung dort in >= 60 Bildern neben einer Box mit ID lag (Geist auf
  blinder Kuh) oder >= 50 % der Bilder dort ausmacht – auch duenn oder mit
  Pausen. Eine Kuh mit stabiler ID und gelegentlichem Aussetzer nicht.
- Hinweis, wenn in < 60 Bildern alle angegebenen Kuehe zugleich erkannt
  sind (auch bei Einzelbild-Rauschen).
- Exit-Codes von main(): 0 keine Beanstandung, 1 ✗, 2 ohne Urteil/Eingabe.
Ohne numpy/cv2/ultralytics.
"""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer  # noqa: E402

PFAD = Path(__file__).resolve().parent.parent / "training" / "tracking_pruefung.py"
spec = importlib.util.spec_from_file_location("tracking_pruefung", PFAD)
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)
p = Pruefer("Tracking-Pruefung")


def nur(k: dict, *verfehlt: str) -> bool:
    """Genau die genannten ✗-Kriterien verfehlt, alle anderen erfuellt."""
    ok = {"wechsel": k["wechsel_ok"], "kurz": k["kurz_ok"], "geist": not k["geister"]}
    return all(ok[n] == (n not in verfehlt) for n in ok)


def box(x: float, y: float = 100.0, w: float = 200.0, h: float = 120.0) -> tuple:
    return (x, y, w, h)


# --- 1. Ein Bild je Sekunde -------------------------------------------------
p.check("1: 25 fps, 75 Bilder -> 0, 25, 50", tp.sekundenbilder(25, 75) == [0, 25, 50])
p.check("1: 1 fps -> jedes Bild", tp.sekundenbilder(1, 5) == [0, 1, 2, 3, 4])
p.check("1: fps unbekannt (0) -> jedes Bild", tp.sekundenbilder(0, 3) == [0, 1, 2])
p.check("1: 29.97 fps, 10 s -> 10 Bilder",
        len(tp.sekundenbilder(29.97, int(29.97 * 10))) == 10)
p.check("1: leer", tp.sekundenbilder(25, 0) == [])

# --- 2. Stabile IDs: zwei Kuehe, 10 min ------------------------------------
stabil = [[(0.8, 1), (0.7, 2)] for _ in range(600)]
k = tp.kennzahlen(stabil)
p.check("2: 2 Kuehe geschaetzt", k["kuehe"] == 2 and k["kuehe_geschaetzt"] == 2)
p.check("2: ohne --kuehe kein Urteil", k["urteil"] == "–")
p.check("2: Dauer 10 min", k["dauer_min"] == 10.0)
k = tp.kennzahlen(stabil, kuehe_echt=2)
p.check("2: mit --kuehe 2: keine Beanstandung, kein ✓",
        nur(k) and k["urteil"] == "ansehen" and k["stellen"] == [])

# --- 3. Gesund: Verdeckung mit neuer ID, auch am Clip-Rand ------------------
wechsel = ([[(0.8, 1), (0.7, 2)] for _ in range(300)]
           + [[(0.8, 1)] for _ in range(120)]
           + [[(0.8, 1), (0.7, 3)] for _ in range(180)])
k = tp.kennzahlen(wechsel, kuehe_echt=2)
p.check("3: 1 Wechsel = 0.5 je Kuh / 10 min -> kein ✗",
        k["wechsel"] == 1 and k["wechsel_je_kuh_10min"] == 0.5 and k["urteil"] == "ansehen")
rand = ([[(0.8, 1)] for _ in range(30)] + [[(0.8, 1), (0.7, 2)] for _ in range(540)]
        + [[(0.8, 1)] for _ in range(30)])
k = tp.kennzahlen(rand, kuehe_echt=2)
p.check("3: D5 – B am Anfang und Ende verdeckt, eine ID -> kein ✗",
        nur(k) and k["urteil"] == "ansehen")
auf = ([[(0.9, 1), (0.8, 2)] for _ in range(300)] + [[(0.9, 1), (0.8, 2), (0.7, 3)] for _ in range(5)]
       + [[(0.9, 1), (0.7, 3)] for _ in range(295)])
k = tp.kennzahlen(auf, kuehe_echt=2)
p.check("3: Aufstehen mit 5 Bildern Doppelrahmen -> kein Geist, kein ✗",
        not k["geister"] and k["urteil"] == "ansehen")
rauschen = [[(0.8, 1)] + ([(0.3, None)] if t % 16 == 0 else []) for t in range(600)]
k = tp.kennzahlen(rauschen, kuehe_echt=1)
p.check("3: Einzelbild-Rauschen 6 % -> kein ✗, keine Stelle", nur(k) and k["stellen"] == [])
herde_teil = [[(0.8, c, box(300.0 * c)) for c in range(1, 21)]
              + [(0.15, None, box(300.0 * c, 300.0, 80.0, 60.0)) for c in range(1, 21) if (t + c) % 20 == 0]
              for t in range(600)]
k = tp.kennzahlen(herde_teil, kuehe_echt=20)
p.check("3: Herde, Kopf-Teilboxen je Kuh in 5 % -> kein ✗, keine Stelle",
        nur(k) and k["stellen"] == [])
fast = [[(0.8, 1), (0.7, None if t % 10 == 0 else 2)] for t in range(2400)]
k = tp.kennzahlen(fast, kuehe_echt=2)
p.check("3: B hat ihre ID 9 von 10 s -> keine Stelle", nur(k) and k["stellen"] == [])

# --- 4. Jedes ✗-Kriterium kippt das Urteil allein ---------------------------
viele = [[(0.8, 1), (0.7, 100 + t // 20)] for t in range(600)]  # alle 20 s neue ID
k = tp.kennzahlen(viele, kuehe_echt=2)
p.check("4: nur Wechsel (29) -> ✗", k["wechsel"] == 29 and nur(k, "wechsel") and k["urteil"] == "✗")
grenze_w = [[(0.8, 1)] for _ in range(300)] + [[(0.8, 2)] for _ in range(300)]
k = tp.kennzahlen(grenze_w, kuehe_echt=1)
p.check("4: Wechsel genau 1.0 je Kuh / 10 min -> ✗ (Grenze zaehlt mit)",
        k["wechsel_je_kuh_10min"] == 1.0 and not k["wechsel_ok"])
fragment = [[(0.8, 1), (0.7, 100 + t // 60 if t % 60 < 5 else 2)] for t in range(1200)]
k = tp.kennzahlen(fragment, kuehe_echt=2)
p.check("4: nur Kurz-IDs (B jede Minute 5 s Fragment-ID) -> ✗",
        nur(k, "kurz") and k["urteil"] == "✗")
p.check("4: Kurz-IDs je Kuh gerechnet (20 / 2 Kuehe / 2 x 10 min = 5)",
        k["kurz_je_kuh_10min"] == 5.0)
geist_lang = [[(0.9, 1), (0.8, 2), (0.45, 3)] for _ in range(600)]
k = tp.kennzahlen(geist_lang, kuehe_echt=2)
p.check("4: nur Geist (3 lange IDs bei 2 Kuehen, Wechsel 0.5) -> ✗",
        nur(k, "geist") and k["urteil"] == "✗")
schnell = [[(0.8, 1000 + t // 5)] for t in range(600)]  # alle 5 s neue ID
k = tp.kennzahlen(schnell, kuehe_echt=1)
p.check("4: alle 5 s neue ID -> 120 Kurz-IDs je Kuh / 10 min, ✗",
        k["kurz_je_kuh_10min"] == 120.0 and k["urteil"] == "✗")
herde = [[(0.8, c) for c in range(1, 21)] + [(0.7, 1000 + t // 5)] for t in range(600)]
k = tp.kennzahlen(herde, kuehe_echt=21)
p.check("4: 20 stabile + 1 wechselnde Kuh -> ✗", not k["kurz_ok"] and k["urteil"] == "✗")

# --- 5. Flackern unter 10 s zaehlt nicht als Kuh ---------------------------
flackern = [[(0.8, 1)] + ([(0.3, 50 + t)] if t % 60 == 0 else []) for t in range(600)]
k = tp.kennzahlen(flackern)
p.check("5: kurze Einzel-IDs zaehlen weder als Kuh noch als Wechsel",
        k["kuehe"] == 1 and k["ids_lang"] == 1 and k["wechsel"] == 0)
p.check("5: aber als Kurz-IDs (10 in 10 min)", k["kurz_ids"] == 10)

# --- 6. Stellen ohne ID: Felder ---------------------------------------------
nacht = [[(0.85, 1, (100, 100, 200, 120)), (0.45, None, (400, 300, 210, 110)),
          (0.3, None, (700, 300, 190, 100))] for _ in range(600)]
k = tp.kennzahlen(nacht)
p.check("6: Band 0.40–0.50: 600 von 600 ohne ID", k["ohne_id"]["0.40–0.50"] == (600, 600))
p.check("6: Band 0.25–0.40: 600 von 600 ohne ID", k["ohne_id"]["0.25–0.40"] == (600, 600))
p.check("6: Band 0.50–1.00: 0 ohne ID", k["ohne_id"]["0.50–1.00"] == (600, 0))
st = sorted(tp.kennzahlen(nacht, kuehe_echt=3)["stellen"], key=lambda x: x["box"][0])
p.check("6: zwei Stellen, je mit Zeit, conf und eigener Box",
        len(st) == 2 and (st[0]["start_s"], st[0]["ende_s"], st[0]["bilder"]) == (0, 599, 600)
        and st[0]["box"] == (400.0, 300.0, 210.0, 110.0) and st[0]["conf_min"] == 0.45
        and st[1]["box"] == (700.0, 300.0, 190.0, 100.0) and st[1]["conf_max"] == 0.3)
gemischt = ([[(0.8, 1, box(100)), (0.2, None, box(500))] for _ in range(60)]
            + [[(0.8, 1, box(100)), (0.4, None, box(520))] for _ in range(60)]
            + [[(0.8, 1, box(100)), (0.7, 9, box(500))] for _ in range(40)])
st = tp.kennzahlen(gemischt, kuehe_echt=2)["stellen"]
p.check("6: Box nur aus den Erkennungen ohne ID, conf min/max, Bildzahl ohne ID",
        len(st) == 1 and st[0]["box"] == (510.0, 100.0, 200.0, 120.0)
        and (st[0]["conf_min"], st[0]["conf_max"]) == (0.2, 0.4) and st[0]["bilder"] == 120)
mehr = ([[(0.8, 1, box(100))] + [(0.3, None, box(1000))] for _ in range(80)]
        + [[(0.8, 1, box(100))] + [(0.3, None, box(2000))] for _ in range(120)])
st = tp.kennzahlen(mehr, kuehe_echt=2)["stellen"]
p.check("6: Stellen nach Bildzahl sortiert", [x["bilder"] for x in st] == [120, 80])

# --- 7. Leerer Clip ---------------------------------------------------------
k = tp.kennzahlen([[] for _ in range(60)])
p.check("7: ohne Erkennung 0 Kuehe, kein Urteil", k["kuehe"] == 0 and k["urteil"] == "–")
k = tp.kennzahlen([[] for _ in range(60)], kuehe_echt=2)
p.check("7: leerer Clip, --kuehe 2 -> Hinweis 'nie alle erkannt', kein ✗",
        k["nie_alle_erkannt"] and k["urteil"] == "ansehen")

# --- 8. Tabelle fuer die Modellkarte ---------------------------------------
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(wechsel, 2),
                 "bytetrack.yaml": tp.kennzahlen(viele, 2)}, 0.8)
p.check("8: Tabelle nennt beide Tracker", "tracker-kuh.yaml" in md and "bytetrack.yaml" in md)
p.check("8: Warnung unter 1 FPS", "UNTER 1 FPS" in md)
p.check("8: Gesamt ohne ✓", "| **Gesamt** | keine Beanstandung – Stellen ansehen | ✗ |" in md
        and "✓" not in md.split("✗ heißt")[0])
p.check("8: Wechsel-Zeile: Kreuz nur bei Verfehlung", "| 0.5 | 14.5 ✗ |" in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(wechsel, 2)}, None)
p.check("8: ohne Befund kein Achtung/Pruefen", "**Achtung" not in md and "**Prüfen" not in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(nacht, 3)}, None)
p.check("8: Stelle mit Zeit und Box",
        "**Prüfen tracker-kuh.yaml:** 600 Bilder ohne ID zwischen 00:00 und 09:59, "
        "conf 0.45–0.45, Box um (400, 300), 210×110 px." in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(nacht)}, None)
p.check("8: ohne --kuehe: Gesamt '–'", "– (--kuehe fehlt)" in md)
md = tp.tabelle({"x": tp.kennzahlen(schnell, kuehe_echt=1)}, None)
p.check("8: Achtung-Hinweis Kurz-ID", "hielten keine 10 s" in md and "| **Gesamt** | ✗ |" in md)
k = tp.kennzahlen([[(0.45, 7)] for _ in range(600)], kuehe_echt=0)
p.check("8: --kuehe 0: Zeile ohne Widerspruch",
        "1 lange ID(s) bei 0 Kühen ✗" in tp.tabelle({"x": k}, None))
viel = [[(0.8, 1, box(100))] + [(0.3, None, box(1000 + 1000 * o, 300)) for o in range(7)]
        for _ in range(60)]
md = tp.tabelle({"x": tp.kennzahlen(viel, kuehe_echt=8)}, None)
p.check("8: mehr als 5 Stellen -> 5 genannt, Rest gezaehlt",
        md.count("**Prüfen x:** 60 Bilder") == 5 and "… und 2 weitere Stellen" in md)

# --- 9. Stellen: Grenzen der Regel ------------------------------------------
def stelle(n_ohne: int, n_mit: int = 0, gesamt: int = 2400) -> list:
    """Kuh A (ID 1); an Ort B n_ohne Bilder ohne ID, danach n_mit mit ID 2."""
    out = []
    for t in range(gesamt):
        bild = [(0.8, 1)]
        if t < n_ohne:
            bild.append((0.3, None))
        elif t < n_ohne + n_mit:
            bild.append((0.7, 2))
        out.append(bild)
    return out


p.check("9: 59 Bilder ohne ID -> keine Stelle",
        tp.kennzahlen(stelle(59), kuehe_echt=1)["stellen"] == [])
p.check("9: 60 Bilder -> Stelle", len(tp.kennzahlen(stelle(60), kuehe_echt=1)["stellen"]) == 1)
p.check("9: 60 ohne + 60 mit ID (Anteil genau 50 %) -> Stelle",
        len(tp.kennzahlen(stelle(60, 60), kuehe_echt=2)["stellen"]) == 1)
p.check("9: 60 ohne + 61 mit ID (Anteil < 50 %) -> keine Stelle",
        tp.kennzahlen(stelle(60, 61), kuehe_echt=2)["stellen"] == [])
duenn = [[(0.8, 1, box(100)), (0.6, 7, box(700))]
         + ([(0.15, None, box(400, 300))] if t % 7 in (0, 3, 5) else []) for t in range(600)]
p.check("9: Kuh ohne ID nur in 43 % der Bilder, Geist abseits -> Stelle",
        len(tp.kennzahlen(duenn, kuehe_echt=1)["stellen"]) == 1)
luecken = [[(0.8, 1)] + ([(0.3, None)] if t % 61 < 50 else []) for t in range(2400)]
p.check("9: Kuh 50 s da, 11 s weg, nie ID -> eine Stelle (Pausen egal)",
        len(tp.kennzahlen(luecken, kuehe_echt=2)["stellen"]) == 1)
# Blocker 1 (Runde 5): Geist mit ID UEBER der blinden Kuh (IoU 0.55)
geist_auf = [[(0.62, 1, (760.0, 440.0, 160.0, 100.0))]
             + ([(0.12, None, (800.0, 450.0, 220.0, 110.0))] if t % 9 < 4 else [])
             for t in range(600)]
st = tp.kennzahlen(geist_auf, kuehe_echt=1)["stellen"]
p.check("9: B1 – Geist mit ID auf blinder Kuh (44 %) -> Stelle 'neben einer Box mit ID'",
        len(st) == 1 and st[0]["neben_id"] == st[0]["bilder"] >= 60)
neben59 = [[(0.62, 1, box(500))] + ([(0.12, None, box(510))] if t < 59 else []) for t in range(600)]
p.check("9: 59 Bilder neben ID-Box -> keine Stelle",
        tp.kennzahlen(neben59, kuehe_echt=1)["stellen"] == [])
getrennt = [[(0.8, 1, box(100))] + [(0.3, None, box(400 + 600 * (t % 2), 300))] for t in range(80)]
p.check("9: zwei Orte ohne Ueberlappung, je 40 Bilder -> keine Stelle",
        tp.kennzahlen(getrennt, kuehe_echt=2)["stellen"] == [])
nah = [[(0.8, 1, box(100))] + [(0.3, None, box(400 + 20 * (t % 2), 300))] for t in range(80)]
p.check("9: derselbe Ort leicht versetzt, 80 Bilder -> eine Stelle",
        len(tp.kennzahlen(nah, kuehe_echt=2)["stellen"]) == 1)
weit_weg = [[(0.8, 1, box(100))] + [(0.3, None, box(5000.0 + 3000.0 * t, 5000.0))] for t in range(200)]
p.check("9: Rauschen an immer neuen Orten -> keine Stelle",
        tp.kennzahlen(weit_weg, kuehe_echt=2)["stellen"] == [])

# --- 9b. IoU und Ortsgrenze --------------------------------------------------
p.check("9b: IoU gleiche Box = 1", tp._iou(box(0), box(0)) == 1.0)
p.check("9b: IoU halb verschoben = 1/3", abs(tp._iou(box(0), box(100)) - 1 / 3) < 1e-9)
p.check("9b: IoU nur in y verschoben = 1/3",
        abs(tp._iou(box(0, 0), box(0, 60)) - 1 / 3) < 1e-9)
p.check("9b: IoU ohne Ueberlappung = 0", tp._iou(box(0), box(300)) == 0.0)
p.check("9b: IoU verschachtelt = Flaechenverhaeltnis",
        abs(tp._iou((0, 0, 200, 100), (0, 0, 100, 50)) - 0.25) < 1e-9)


def zwei_orte(abstand: float) -> list:
    """60 Bilder ohne ID bei x=0, dann 60 bei x=abstand (gleiche Groesse)."""
    return ([[(0.3, None, box(0.0))] for _ in range(60)]
            + [[(0.3, None, box(abstand))] for _ in range(60)])


# IoU(200 breit, Versatz d) = (200-d)/(200+d): 0.3 bei d = 107.7
p.check("9b: IoU knapp ueber 0.3 -> ein Ort (120 Bilder)",
        [x["bilder"] for x in tp.stellen_ohne_id(zwei_orte(107.0))] == [120])
p.check("9b: IoU knapp unter 0.3 -> zwei Orte (je 60)",
        [x["bilder"] for x in tp.stellen_ohne_id(zwei_orte(108.5))] == [60, 60])
# x=100 ueberlappt Ort 0 mit IoU 1/3 und Ort 140 mit IoU 2/3
naechster = ([[(0.3, None, box(0.0))] for _ in range(60)] + [[(0.3, None, box(140.0))] for _ in range(60)]
             + [[(0.3, None, box(100.0))] for _ in range(60)])
st = sorted(tp.stellen_ohne_id(naechster), key=lambda x: x["box"][0])
p.check("9b: Zuordnung zum naechsten Ort, nicht zum ersten",
        [x["bilder"] for x in st] == [60, 120])

# --- 10. Geist und Kurz-ID: Grenzen -----------------------------------------
def geist_bilder(an: int, aussetzer_alle: int = 0, gesamt: int = 600) -> list:
    out = []
    for t in range(gesamt):
        bild = [(0.9, 1), (0.8, 2)]
        if t < an and not (aussetzer_alle and t % aussetzer_alle == 0):
            bild.append((0.45, 3))
        out.append(bild)
    return out


p.check("10: Geist 10 Bilder -> Geist", tp.kennzahlen(geist_bilder(10), kuehe_echt=2)["geister"])
p.check("10: Geist 9 Bilder -> keiner", not tp.kennzahlen(geist_bilder(9), kuehe_echt=2)["geister"])
p.check("10: Geist flackert (jedes 10. Bild fehlt) -> Geist",
        tp.kennzahlen(geist_bilder(1200, 10, 1200), kuehe_echt=2)["geister"])
zwei_luecke = [[(0.9, 1), (0.8, 2)] + ([(0.45, 3)] if t in range(5) or t in range(7, 12) else [])
               for t in range(600)]
p.check("10: Aussetzer 2 Bilder ueberbrueckt (5+2+5 = 12)",
        tp.kennzahlen(zwei_luecke, kuehe_echt=2)["geist_s"] == 12)
drei_luecke = [[(0.9, 1), (0.8, 2)] + ([(0.45, 3)] if t in range(5) or t in range(8, 13) else [])
               for t in range(600)]
p.check("10: Aussetzer 3 Bilder trennt", tp.kennzahlen(drei_luecke, kuehe_echt=2)["geist_s"] == 5)
zehn = [[(0.8, 1)] + ([(0.6, 5)] if 100 <= t < 110 else []) for t in range(600)]
neun = [[(0.8, 1)] + ([(0.6, 5)] if 100 <= t < 109 else []) for t in range(600)]
p.check("10: ID mit genau 10 Bildern ist lang", tp.kennzahlen(zehn)["ids_lang"] == 2)
p.check("10: ID mit 9 Bildern ist kurz", tp.kennzahlen(neun)["kurz_ids"] == 1)
schwach_kurz = [[(0.8, 1)] + ([(0.2, 5)] if 100 <= t < 105 else []) for t in range(600)]
p.check("10: Kurz-ID nur mit conf < 0.25 zaehlt nicht", tp.kennzahlen(schwach_kurz)["kurz_ids"] == 0)
grenz_kurz = [[(0.8, 1)] + ([(0.25, 5)] if 100 <= t < 105 else []) for t in range(600)]
p.check("10: Kurz-ID mit conf genau 0.25 zaehlt", tp.kennzahlen(grenz_kurz)["kurz_ids"] == 1)

# --- 11. Kuhzahl ------------------------------------------------------------
geist = [[(0.8, 1), (0.3, 2)] for _ in range(600)]  # Heuballen mit eigener ID
k = tp.kennzahlen(geist)
p.check("11: ohne --kuehe zaehlt der Geist als Kuh, kein Urteil", k["kuehe"] == 2 and k["urteil"] == "–")
k = tp.kennzahlen(geist, kuehe_echt=1)
p.check("11: mit --kuehe 1 -> Geist, ✗", k["geister"] and k["urteil"] == "✗")
p.check("11: Tabelle nennt angegebene Zahl und Geist",
        "angegeben 1" in (md := tp.tabelle({"x": k}, None)) and "Geist" in md)
p.check("11: --kuehe zu hoch -> Hinweis 'nie alle erkannt'",
        tp.kennzahlen(stabil, kuehe_echt=3)["nie_alle_erkannt"])
# Blocker 2 (Runde 5): Kuh B nie erkannt, Einzelbild-Rauschen hebt die Zahl kurz an
nie_b = [[(0.8, 1, box(100))] + ([(0.3, None, box(3000.0 + 400.0 * t))] if t % 33 == 0 else [])
         for t in range(600)]
k = tp.kennzahlen(nie_b, kuehe_echt=2)
p.check("11: B2 – Kuh nie erkannt, 3 % Rauschen -> Hinweis bleibt",
        k["alle_erkannt_bilder"] == 19 and k["nie_alle_erkannt"])
p.check("11: 60 Bilder mit allen Kuehen -> kein Hinweis",
        not tp.kennzahlen([[(0.8, 1), (0.7, 2)] for _ in range(60)], kuehe_echt=2)["nie_alle_erkannt"])
p.check("11: 59 Bilder -> Hinweis",
        tp.kennzahlen([[(0.8, 1), (0.7, 2)] for _ in range(59)], kuehe_echt=2)["nie_alle_erkannt"])
k = tp.kennzahlen([[(0.45, 7)] for _ in range(600)], kuehe_echt=0)
p.check("11: leere Box, Heuballen mit ID, --kuehe 0 -> ✗",
        k["geister"] and not k["wechsel_ok"] and k["urteil"] == "✗")
k = tp.kennzahlen([[] for _ in range(600)], kuehe_echt=0)
p.check("11: leere Box ohne Erkennung, --kuehe 0 -> keine Beanstandung", k["urteil"] == "ansehen")
try:
    tp.kennzahlen(stabil, kuehe_echt=-1)
    p.check("11: --kuehe -1 abgewiesen", False)
except ValueError:
    p.check("11: --kuehe -1 abgewiesen", True)

# --- 12. Bildwahl ohne bekannte Bildzahl, Klassen wie im Agenten -----------
nimm = tp.sekundenwahl(25)
p.check("12: Strom ohne Bildzahl = sekundenbilder",
        [i for i in range(250) if nimm(i)] == tp.sekundenbilder(25, 250))
p.check("12: Kuh (cls 0) ist Tier", tp.ist_tier([1, 2, 3, 4, 0.8, 0], {0}))
p.check("12: Fruchtblase (cls 1) ist kein Tier", not tp.ist_tier([1, 2, 3, 4, 0.9, 1], {0}))
p.check("12: alte Ablage ohne Klasse -> Tier", tp.ist_tier([1, 2, 3, 4, 0.8], set()))

# --- 13. main(): Exit-Codes (verfolge ersetzt, ohne Tracker) ---------------
with tempfile.TemporaryDirectory() as tmp:
    clip = Path(tmp) / "clip.mp4"
    clip.with_suffix(".erkennungen.json").write_text(json.dumps(
        {"modell": "x.pt", "tier_klassen": ["kuh"], "tier_ids": [0], "bilder": [[]]}))

    def lauf(argv: list[str], szenario, ziel: Path | None = None) -> int:
        tp.verfolge = lambda bilder, pfad, ids: szenario
        alt = sys.argv
        sys.argv = ["tracking_pruefung.py", str(ziel or clip)] + argv
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return tp.main()
        except SystemExit as fehler:
            return fehler.code
        finally:
            sys.argv = alt

    p.check("13: keine Beanstandung -> 0", lauf(["--kuehe", "2", "--tracker", "a.yaml"], stabil) == 0)
    p.check("13: ✗ -> 1", lauf(["--kuehe", "2", "--tracker", "a.yaml"], viele) == 1)
    p.check("13: Stellen allein -> 0 (nur ansehen)",
            lauf(["--kuehe", "1", "--tracker", "a.yaml"], geist_auf) == 0)
    p.check("13: ✗ in einer von zwei Einstellungen -> 1",
            tp.exit_code({"a": tp.kennzahlen(stabil, 2), "b": tp.kennzahlen(viele, 2)}) == 1)
    p.check("13: ohne --kuehe -> 2", lauf(["--tracker", "a.yaml"], stabil) == 2)
    p.check("13: --kuehe -1 -> 2", lauf(["--kuehe", "-1"], stabil) == 2)
    p.check("13: --kuehe zwei -> 2", lauf(["--kuehe", "zwei"], stabil) == 2)
    p.check("13: falsche Tierklassen -> 2",
            lauf(["--kuehe", "2", "--tier-klassen", "pferd"], stabil) == 2)
    p.check("13: Ablage fehlt -> 2", lauf(["--kuehe", "2"], stabil, Path(tmp) / "fehlt.mp4") == 2)

# --- 14. Laufzeit: 12-h-Nacht, 20 Kuehe + 5 % Rauschen an neuen Orten -------
nacht12 = [[(0.8, c, box(300.0 * c)) for c in range(1, 21)]
           + ([(0.3, None, box(9000.0 + 250.0 * (t % 4000), 9000.0 + 250.0 * (t // 4000)))]
              if t % 20 == 0 else [])
           for t in range(43_200)]
t0 = time.perf_counter()
k = tp.kennzahlen(nacht12, kuehe_echt=20)
dauer = time.perf_counter() - t0
p.check(f"14: 12 h mit 20 Kuehen in {dauer:.1f} s (< 60 s)", dauer < 60 and k["stellen"] == [])

sys.exit(p.bericht())
