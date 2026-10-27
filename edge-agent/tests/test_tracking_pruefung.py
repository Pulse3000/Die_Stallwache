#!/usr/bin/env python3
"""Logiktests der Tracking-Pruefung (training/tracking_pruefung.py).

Die Zusagen: Aus einem Video wird 1 Bild je Sekunde genommen wie im
Agenten, auch wenn der Container die Bildzahl nicht kennt. Ein Urteil gibt
es nur mit der echten Kuhzahl:
- ✗, sobald ein ID-Kriterium verfehlt ist: zu viele Wechsel, Kurz-IDs (auch
  in grossen Herden) oder ein Geist von mindestens 10 s. Ein Doppelrahmen
  von 2 Bildern beim Aufstehen ist kein Geist.
- „?“, wenn sich eine Erkennung ohne ID dauerhaft haelt oder nie alle
  Kuehe erkannt werden. Kuh oder Fehlerkennung zeigt dann nur das Bild; ein
  Geist mit ID kann eine blinde Kuh verdecken. Die Stelle wird mit Zeit und
  Box genannt.
- In eindeutiger Szene ✗ bei zu vielen sichtbaren Kuh-Sekunden ohne lange ID
  oder einer Luecke ab 30 min bzw. 80 % des Clips; Bilder mit allen Kuehen
  samt ID beenden die Luecke.
- Jedes Kriterium kippt das Urteil fuer sich allein.
- Exit-Codes von main(): 0/1/2/3.
Ohne numpy/cv2/ultralytics.
"""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer  # noqa: E402

PFAD = Path(__file__).resolve().parent.parent / "training" / "tracking_pruefung.py"
spec = importlib.util.spec_from_file_location("tracking_pruefung", PFAD)
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)
p = Pruefer("Tracking-Pruefung")


def nur(k: dict, *verfehlt: str) -> bool:
    """Genau die genannten Kriterien verfehlt, alle anderen erfuellt."""
    ok = {"wechsel": k["wechsel_ok"], "kurz": k["kurz_ok"], "geist": not k["geister"],
          "ohne_id": k["ohne_id_ok"], "luecke": k["luecke_ok"], "eindeutig": not k["mehrdeutig"]}
    return all(ok[n] == (n not in verfehlt) for n in ok)


# --- 1. Ein Bild je Sekunde -------------------------------------------------
p.check("1: 25 fps, 75 Bilder -> 0, 25, 50", tp.sekundenbilder(25, 75) == [0, 25, 50])
p.check("1: 1 fps -> jedes Bild", tp.sekundenbilder(1, 5) == [0, 1, 2, 3, 4])
p.check("1: fps unbekannt (0) -> jedes Bild", tp.sekundenbilder(0, 3) == [0, 1, 2])
p.check("1: 29.97 fps, 10 s -> 10 Bilder",
        len(tp.sekundenbilder(29.97, int(29.97 * 10))) == 10)
p.check("1: leer", tp.sekundenbilder(25, 0) == [])

# --- 2. Stabile IDs: zwei Kuehe, 10 min, keine Wechsel ----------------------
stabil = [[(0.8, 1), (0.7, 2)] for _ in range(600)]
k = tp.kennzahlen(stabil)
p.check("2: 2 Kuehe geschaetzt", k["kuehe"] == 2 and k["kuehe_geschaetzt"] == 2)
p.check("2: ohne --kuehe kein Urteil", k["urteil"] == "–" and not k["ziel_erfuellt"])
p.check("2: Dauer 10 min", k["dauer_min"] == 10.0)
k = tp.kennzahlen(stabil, kuehe_echt=2)
p.check("2: mit --kuehe 2: alles erfuellt, ✓", nur(k) and k["urteil"] == "✓" and k["ziel_erfuellt"])

# --- 3. Kuh 2 bekommt nach Verdeckung eine neue ID --------------------------
wechsel = ([[(0.8, 1), (0.7, 2)] for _ in range(300)]
           + [[(0.8, 1)] for _ in range(120)]
           + [[(0.8, 1), (0.7, 3)] for _ in range(180)])
k = tp.kennzahlen(wechsel, kuehe_echt=2)
p.check("3: 3 lange IDs bei 2 Kuehen -> 1 Wechsel = 0.5 je Kuh / 10 min",
        k["wechsel"] == 1 and k["wechsel_je_kuh_10min"] == 0.5)
p.check("3: ganz verdeckte Kuh zaehlt nicht als 'ohne ID' -> ✓",
        k["kuh_anteil_ohne_id"] == 0.0 and k["laengste_luecke_s"] == 0 and k["urteil"] == "✓")

# --- 4. Jedes Kriterium kippt das Urteil allein -----------------------------
viele = [[(0.8, 1), (0.7, 100 + t // 20)] for t in range(600)]  # alle 20 s neue ID
k = tp.kennzahlen(viele, kuehe_echt=2)
p.check("4: nur Wechsel (29) -> ✗", k["wechsel"] == 29 and nur(k, "wechsel") and k["urteil"] == "✗")
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
loch = [[(0.8, 1), (0.7, None if t % 15 < 3 else 2)] for t in range(600)]
k = tp.kennzahlen(loch, kuehe_echt=2)
p.check("4: nur Anteil ohne ID (B 3 von 15 Bildern ohne ID = 10 %) -> ✗",
        nur(k, "ohne_id") and k["urteil"] == "✗")
# Kuh 21 nie mit ID, wandert (60 Orte, keiner sammelt 60 Bilder), 40 min
wandert = [[(0.8, c) for c in range(1, 21)]
           + [(0.5, None, (9000.0 + 300.0 * (t % 60), 900.0, 200.0, 120.0))] for t in range(2400)]
k = tp.kennzahlen(wandert, kuehe_echt=21)
p.check("4: nur Luecke (Kuh 21 wandert ohne ID, Anteil 4.8 %) -> ✗",
        nur(k, "luecke") and k["urteil"] == "✗")
mitte = ([[(0.8, 1), (0.7, 2)] for _ in range(100)] + [[(0.8, 1), (0.7, 3)] for _ in range(300)]
         + [[(0.8, 1), (0.7, 4)] for _ in range(1400)])
k = tp.kennzahlen(mitte, kuehe_echt=2)
p.check("4: nur Zwischen-ID (B: ID 3 lebt 5 min, Mittel 0.67 je Kuh) -> ✗",
        k["wechsel_je_kuh_10min"] < 1 and k["zwischen_ids"] == [(3, 100, 399)]
        and nur(k, "wechsel") and k["urteil"] == "✗")
lang_mitte = ([[(0.8, 1), (0.7, 2)] for _ in range(100)] + [[(0.8, 1), (0.7, 3)] for _ in range(600)]
              + [[(0.8, 1), (0.7, 4)] for _ in range(1700)])
p.check("4: Zwischen-ID mit genau 10 min zaehlt nicht",
        tp.kennzahlen(lang_mitte, kuehe_echt=2)["zwischen_ids"] == [])

# --- 5. Flackern unter 10 s zaehlt nicht als Kuh ---------------------------
flackern = [[(0.8, 1)] + ([(0.3, 50 + t)] if t % 60 == 0 else []) for t in range(600)]
k = tp.kennzahlen(flackern)
p.check("5: kurze Einzel-IDs zaehlen weder als Kuh noch als Wechsel",
        k["kuehe"] == 1 and k["ids_lang"] == 1 and k["wechsel"] == 0)
p.check("5: aber als Kurz-IDs (10 in 10 min)", k["kurz_ids"] == 10)

# --- 6. Nachts: Erkennungen ohne ID je Band, Szene mehrdeutig --------------
nacht = [[(0.85, 1, (100, 100, 200, 120)), (0.45, None, (400, 300, 210, 110)),
          (0.3, None, (700, 300, 190, 100))] for _ in range(600)]
k = tp.kennzahlen(nacht)
p.check("6: Band 0.40–0.50: 600 von 600 ohne ID", k["ohne_id"]["0.40–0.50"] == (600, 600))
p.check("6: Band 0.25–0.40: 600 von 600 ohne ID", k["ohne_id"]["0.25–0.40"] == (600, 600))
p.check("6: Band 0.50–1.00: 0 ohne ID", k["ohne_id"]["0.50–1.00"] == (600, 0))
k = tp.kennzahlen(nacht, kuehe_echt=3)
p.check("6: --kuehe 3: 2 von 3 sichtbaren ohne ID, aber Kuh oder Fehlerkennung? -> ?",
        abs(k["kuh_anteil_ohne_id"] - 2 / 3) < 1e-9 and not k["ohne_id_ok"]
        and k["mehrdeutig"] and k["urteil"] == "?")
st = sorted(k["dauer_ohne_id"], key=lambda x: x["box"][0])
p.check("6: zwei Stellen, je mit Zeit, conf und eigener Box",
        len(st) == 2 and (st[0]["start_s"], st[0]["ende_s"], st[0]["bilder"]) == (0, 599, 600)
        and st[0]["box"] == (400.0, 300.0, 210.0, 110.0) and st[0]["conf_min"] == 0.45
        and st[1]["box"] == (700.0, 300.0, 190.0, 100.0) and st[1]["conf_max"] == 0.3)

# --- 7. Leerer Clip ---------------------------------------------------------
k = tp.kennzahlen([[] for _ in range(60)])
p.check("7: ohne Erkennung 0 Kuehe, kein Urteil", k["kuehe"] == 0 and not k["ziel_erfuellt"])
k = tp.kennzahlen([[] for _ in range(60)], kuehe_echt=2)
p.check("7: leerer Clip, --kuehe 2 -> ? (nie erkannt)", k["nie_alle_erkannt"] and k["urteil"] == "?")

# --- 8. Tabelle fuer die Modellkarte ---------------------------------------
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(wechsel, 2),
                 "bytetrack.yaml": tp.kennzahlen(viele, 2)}, 0.8)
p.check("8: Tabelle nennt beide Tracker", "tracker-kuh.yaml" in md and "bytetrack.yaml" in md)
p.check("8: Warnung unter 1 FPS", "UNTER 1 FPS" in md)
p.check("8: Ziel-Haken", "0.5 ✓" in md and "| **Gesamt** | ✓ | ✗ |" in md)
p.check("8: Zwischen-IDs werden mit Zeit genannt", "**Achtung bytetrack.yaml:** ID 101 lebte nur" in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(wechsel, 2)}, None)
p.check("8: ohne Befund kein Achtung/Pruefen", "**Achtung" not in md and "**Prüfen" not in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(nacht, 3)}, None)
p.check("8: Nacht: Achtung mit Vorbehalt, Pruefen mit Zeit und Box, Gesamt ?",
        "67% der sichtbaren Kuh-Sekunden ohne lange ID (falls die Erkennungen ohne ID Kühe sind)" in md
        and "**Prüfen tracker-kuh.yaml:** 600 Bilder ohne ID zwischen 00:00 und 09:59, "
            "conf 0.45–0.45, Box um (400, 300)" in md
        and "| **Gesamt** | ? Bilder ansehen |" in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(nacht)}, None)
p.check("8: ohne --kuehe: Gesamt '–'", "– (--kuehe fehlt)" in md)

# --- 9. Schneller ID-Wechsel faellt durch, auch in grossen Herden ----------
schnell = [[(0.8, 1000 + t // 5)] for t in range(600)]  # alle 5 s neue ID
k = tp.kennzahlen(schnell, kuehe_echt=1)
p.check("9: alle 5 s neue ID -> 120 Kurz-IDs je Kuh / 10 min", k["kurz_je_kuh_10min"] == 120.0)
p.check("9: ✗ ueber die Kurz-IDs", nur(k, "kurz", "ohne_id", "luecke") and k["urteil"] == "✗")
md = tp.tabelle({"tracker-kuh.yaml": k}, None)
p.check("9: Achtung-Hinweis Kurz-ID", "hielten keine 10 s" in md and "| **Gesamt** | ✗ |" in md)
herde = [[(0.8, c) for c in range(1, 21)] + [(0.7, 1000 + t // 5)] for t in range(600)]
k = tp.kennzahlen(herde, kuehe_echt=21)
p.check("9: 20 stabile + 1 wechselnde Kuh -> ✗", not k["kurz_ok"] and k["urteil"] == "✗")

# --- 10. Luecke: Kuh sichtbar, ohne lange ID --------------------------------
luecke = ([[(0.8, 1)] for _ in range(300)]
          + [[(0.8, 1), (0.45, None)] for _ in range(31 * 60)]
          + [[(0.8, 1)] for _ in range(300)])
k = tp.kennzahlen(luecke, kuehe_echt=2)
p.check("10: 31 min am Stueck ohne ID", k["laengste_luecke_s"] == 31 * 60 and not k["luecke_ok"])
p.check("10: Dauer-Erkennung -> ?, Hinweis mit Vorbehalt",
        k["urteil"] == "?" and "länger als ein Kalbeverdachts-Fenster" in tp.tabelle({"x": k}, None))
# Schwankend: Kuh B nur 0.12–0.33, jedes 10. Bild gar nicht erkannt
schwach = [[(0.8, 1)] + ([(0.12 + (t % 7) * 0.035, None)] if t % 10 else []) for t in range(2400)]
k = tp.kennzahlen(schwach, kuehe_echt=2)
p.check("10: kurze Aussetzer und conf unter 0.25 unterbrechen die Luecke nicht",
        k["laengste_luecke_s"] >= 39 * 60 and not k["luecke_ok"] and k["urteil"] == "?")
weg = ([[(0.8, 1), (0.4, None)] for _ in range(20 * 60)] + [[(0.8, 1)] for _ in range(60)]
       + [[(0.8, 1), (0.4, None)] for _ in range(20 * 60)])
k = tp.kennzahlen(weg, kuehe_echt=2)
p.check("10: 60 s ganz verdeckt trennt die Luecke", k["laengste_luecke_s"] == 20 * 60 and k["luecke_ok"])


def mit_pause(s: int, pause: list) -> list:
    return ([[(0.8, 1), (0.4, None)] for _ in range(100)] + [pause for _ in range(s)]
            + [[(0.8, 1), (0.4, None)] for _ in range(100)])


p.check("10: Pause (B nicht erkannt) 10 s wird ueberbrueckt",
        tp.kennzahlen(mit_pause(10, [(0.8, 1)]), kuehe_echt=2)["laengste_luecke_s"] == 210)
p.check("10: Pause 11 s trennt",
        tp.kennzahlen(mit_pause(11, [(0.8, 1)]), kuehe_echt=2)["laengste_luecke_s"] == 100)
voll = [[(0.8, 1), (0.7, 2)] for _ in range(20)]  # ID 2 lebt >= 10 s
p.check("10: 1 Bild mit allen Kuehen samt langer ID trennt",
        tp.kennzahlen(voll + mit_pause(1, [(0.8, 1), (0.7, 2)]), kuehe_echt=2)["laengste_luecke_s"] == 100)
fast = [[(0.8, 1), (0.7, None if t % 10 == 0 else 2)] for t in range(2400)]
k = tp.kennzahlen(fast, kuehe_echt=2)
p.check("10: B hat ihre ID 9 von 10 s -> keine lange Luecke, eindeutig, ✓",
        k["laengste_luecke_s"] == 1 and not k["mehrdeutig"] and k["urteil"] == "✓")
grenz = [[(0.8, 1), (0.4, None)] for _ in range(1798)] + [[(0.8, 1)] for _ in range(600)]
k = tp.kennzahlen(grenz, kuehe_echt=2)
md = tp.tabelle({"x": k}, None)
p.check("10: 1798 s -> '29.9 min ✓', kein Luecken-Hinweis",
        "29.9 min ✓" in md and "Kalbeverdachts-Fenster" not in md.split("Ziel je")[0])
genau = [[(0.8, 1), (0.4, None)] for _ in range(1800)] + [[(0.8, 1)] for _ in range(600)]
p.check("10: genau 30 min -> verfehlt (Grenze zaehlt mit)",
        not tp.kennzahlen(genau, kuehe_echt=2)["luecke_ok"])
herde_blind = [[(0.8, c) for c in range(1, 21)] + [(0.33, None)] for _ in range(600)]
k = tp.kennzahlen(herde_blind, kuehe_echt=21)
p.check("10: 10-min-Clip, 1 von 21 Kuehen nie mit ID -> Luecke verfehlt (Anteil 4.8 % nicht)",
        k["ohne_id_ok"] and not k["luecke_ok"] and k["urteil"] == "?")
p.check("10: Hinweis nennt kurzen Clip", "kaum verfolgt" in tp.tabelle({"x": k}, None))
rauschen = [[(0.8, 1)] + ([(0.3, None)] if t % 16 == 0 else []) for t in range(600)]
k = tp.kennzahlen(rauschen, kuehe_echt=1)
p.check("10: Einzelbild-Rauschen 6 % -> eindeutig, ✓", nur(k) and k["urteil"] == "✓")

# --- 11. Geister und die Kuhzahl -------------------------------------------
geist = [[(0.8, 1), (0.3, 2)] for _ in range(600)]  # Heuballen mit eigener ID
k = tp.kennzahlen(geist)
p.check("11: ohne --kuehe zaehlt der Geist als Kuh, kein Urteil",
        k["kuehe"] == 2 and k["urteil"] == "–")
k = tp.kennzahlen(geist, kuehe_echt=1)
p.check("11: mit --kuehe 1 -> Geist, ✗", k["geister"] and k["urteil"] == "✗")
md = tp.tabelle({"bytetrack.yaml": k}, None)
p.check("11: Tabelle nennt angegebene Zahl und Geist", "angegeben 1" in md and "Geist" in md)
# Blinde Kuh hinter einem Geist (Gegenbeispiel F4): A getrackt, Heuballen mit
# ID, Kuh B nie mit ID. Zaehlungen gleichen dem gesunden Fall -> nie ✓.
f4 = [[(0.85, 1), (0.45, 7), (0.30, None)] for _ in range(600)]
k = tp.kennzahlen(f4, kuehe_echt=2)
p.check("11: Geist verdeckt blinde Kuh -> ?, nicht ✓", k["urteil"] == "?")
h0 = [[(0.85, 1), (0.8, 2), (0.30, None)] for _ in range(600)]
p.check("11: gesund mit Dauer-Fehlerkennung ohne ID -> ebenfalls ? (nur das Bild entscheidet)",
        tp.kennzahlen(h0, kuehe_echt=2)["urteil"] == "?")
# Gegenbeispiel L1: Kuh B ausser Sicht, schwacher Heuballen -> nicht faelschlich ✗
l1 = ([[(0.85, 1), (0.8, 2)] for _ in range(300)]
      + [[(0.85, 1), (0.12, None)] for _ in range(35 * 60)]
      + [[(0.85, 1), (0.8, 2)] for _ in range(300)])
p.check("11: Kuh ausser Sicht + schwacher Heuballen -> ?, nicht ✗",
        tp.kennzahlen(l1, kuehe_echt=2)["urteil"] == "?")
# Aufstehen: 2 Bilder Doppelrahmen, danach neue ID (Gegenbeispiel K)
auf = ([[(0.9, 1), (0.8, 2)] for _ in range(300)] + [[(0.9, 1), (0.8, 2), (0.7, 3)] for _ in range(2)]
       + [[(0.9, 1), (0.7, 3)] for _ in range(298)])
k = tp.kennzahlen(auf, kuehe_echt=2)
p.check("11: Doppelrahmen 2 Bilder ist kein Geist -> ✓", not k["geister"] and k["urteil"] == "✓")
k = tp.kennzahlen(stabil, kuehe_echt=3)
p.check("11: --kuehe zu hoch (nie 3 erkannt) -> ?", k["nie_alle_erkannt"] and k["urteil"] == "?")
k = tp.kennzahlen([[(0.45, 7)] for _ in range(600)], kuehe_echt=0)
p.check("11: leere Box, Heuballen mit ID, --kuehe 0 -> ✗",
        k["geister"] and not k["wechsel_ok"] and k["urteil"] == "✗")
p.check("11: --kuehe 0: Zeile ohne Widerspruch",
        "1 lange ID(s) bei 0 Kühen ✗" in tp.tabelle({"x": k}, None))
k = tp.kennzahlen([[] for _ in range(600)], kuehe_echt=0)
p.check("11: leere Box ohne Erkennung, --kuehe 0 -> ✓", k["urteil"] == "✓")
k = tp.kennzahlen([[(0.3, None)] for _ in range(600)], kuehe_echt=0)
p.check("11: leere Box, Fehlerkennung ohne ID, --kuehe 0 -> ✓ (keine Kuh verdeckbar)",
        k["urteil"] == "✓")
try:
    tp.kennzahlen(stabil, kuehe_echt=-1)
    p.check("11: --kuehe -1 abgewiesen", False)
except ValueError:
    p.check("11: --kuehe -1 abgewiesen", True)

# --- 11b. Stellen ohne ID: Grenzen der „?“-Regel ---------------------------
def stelle(n_ohne: int, n_mit: int = 0, gesamt: int = 2400) -> list:
    """Kuh A (ID 1) dauerhaft; an Ort B n_ohne Bilder ohne ID, n_mit mit
    langer ID 2 (verstreut ueber den Clip)."""
    out = []
    for t in range(gesamt):
        bild = [(0.8, 1)]
        if t < n_ohne:
            bild.append((0.3, None))
        elif t < n_ohne + n_mit:
            bild.append((0.7, 2))
        out.append(bild)
    return out


p.check("11b: 59 Bilder ohne ID an einer Stelle -> keine Stelle",
        tp.kennzahlen(stelle(59), kuehe_echt=1)["dauer_ohne_id"] == [])
p.check("11b: 60 Bilder -> Stelle, ?", tp.kennzahlen(stelle(60), kuehe_echt=1)["urteil"] == "?")
p.check("11b: 60 ohne + 60 mit ID (Anteil genau 50 %) -> Stelle",
        len(tp.kennzahlen(stelle(60, 60), kuehe_echt=2)["dauer_ohne_id"]) == 1)
p.check("11b: 60 ohne + 61 mit ID -> keine Stelle",
        tp.kennzahlen(stelle(60, 61), kuehe_echt=2)["dauer_ohne_id"] == [])
duenn = [[(0.8, 1, (100, 100, 200, 120)), (0.6, 7, (700, 100, 200, 120))]
         + ([(0.15, None, (400, 300, 200, 120))] if t % 7 in (0, 3, 5) else []) for t in range(600)]
k = tp.kennzahlen(duenn, kuehe_echt=1)
p.check("11b: B1 – Geist mit ID + blinde Kuh nur in 43 % der Bilder -> ?, nicht ✓",
        k["urteil"] in ("?", "✗") and len(k["dauer_ohne_id"]) == 1)
luecken = [[(0.8, 1)] + ([(0.3, None)] if t % 61 < 50 else []) for t in range(2400)]
p.check("11b: Kuh 50 s da, 11 s weg, nie ID -> eine Stelle (Pausen egal)",
        len(tp.kennzahlen(luecken, kuehe_echt=2)["dauer_ohne_id"]) == 1)
getrennt = [[(0.8, 1, (100, 100, 200, 120))]
            + [(0.3, None, (400 + 600 * (t % 2), 300, 200, 120))] for t in range(80)]
p.check("11b: zwei Orte ohne Ueberlappung, je 40 Bilder -> keine Stelle",
        tp.kennzahlen(getrennt, kuehe_echt=2)["dauer_ohne_id"] == [])
nah = [[(0.8, 1, (100, 100, 200, 120))]
       + [(0.3, None, (400 + 20 * (t % 2), 300, 200, 120))] for t in range(80)]
p.check("11b: derselbe Ort leicht versetzt (IoU > 0.3), 80 Bilder -> eine Stelle",
        len(tp.kennzahlen(nah, kuehe_echt=2)["dauer_ohne_id"]) == 1)
herde_teil = [[(0.8, c, (300.0 * c, 100.0, 200.0, 120.0)) for c in range(1, 21)]
              + [(0.15, None, (300.0 * c, 300.0, 80.0, 60.0)) for c in range(1, 21) if (t + c) % 20 == 0]
              for t in range(600)]
k = tp.kennzahlen(herde_teil, kuehe_echt=20)
p.check("11b: Herde, Kopf-Teilboxen je Kuh in 5 % der Bilder -> keine Stelle, ✓",
        k["dauer_ohne_id"] == [] and k["urteil"] == "✓")
viel = [[(0.8, 1, (100, 100, 200, 120))]
        + [(0.3, None, (1000 + 1000 * o, 300, 200, 120)) for o in range(7)] for _ in range(60)]
md = tp.tabelle({"x": tp.kennzahlen(viel, kuehe_echt=8)}, None)
p.check("11b: mehr als 5 Stellen -> 5 genannt, Rest gezaehlt",
        md.count("**Prüfen x:** 60 Bilder") == 5 and "… und 2 weitere Stellen" in md)

# --- 11c. Grenzen der ID-Kriterien -----------------------------------------
def geist_bilder(an: int, aussetzer_alle: int = 0, gesamt: int = 600) -> list:
    out = []
    for t in range(gesamt):
        bild = [(0.9, 1), (0.8, 2)]
        if t < an and not (aussetzer_alle and t % aussetzer_alle == 0):
            bild.append((0.45, 3))
        out.append(bild)
    return out


p.check("11c: Geist 10 Bilder -> Geist", tp.kennzahlen(geist_bilder(10), kuehe_echt=2)["geister"])
p.check("11c: Geist 9 Bilder -> keiner", not tp.kennzahlen(geist_bilder(9), kuehe_echt=2)["geister"])
p.check("11c: M2 – Geist flackert (jedes 10. Bild fehlt) -> Geist",
        tp.kennzahlen(geist_bilder(1200, 10, 1200), kuehe_echt=2)["geister"])
zwei_luecke = [[(0.9, 1), (0.8, 2)] + ([(0.45, 3)] if t in range(5) or t in range(7, 12) else [])
               for t in range(600)]
p.check("11c: Aussetzer 2 Bilder ueberbrueckt (5+2+5 = 12 >= 10)",
        tp.kennzahlen(zwei_luecke, kuehe_echt=2)["geist_s"] == 12)
drei_luecke = [[(0.9, 1), (0.8, 2)] + ([(0.45, 3)] if t in range(5) or t in range(8, 13) else [])
               for t in range(600)]
p.check("11c: Aussetzer 3 Bilder trennt", tp.kennzahlen(drei_luecke, kuehe_echt=2)["geist_s"] == 5)
zehn = [[(0.8, 1)] + ([(0.6, 5)] if 100 <= t < 110 else []) for t in range(600)]
neun = [[(0.8, 1)] + ([(0.6, 5)] if 100 <= t < 109 else []) for t in range(600)]
p.check("11c: ID mit genau 10 Bildern ist lang", tp.kennzahlen(zehn)["ids_lang"] == 2)
p.check("11c: ID mit 9 Bildern ist kurz", tp.kennzahlen(neun)["kurz_ids"] == 1)
schwach_kurz = [[(0.8, 1)] + ([(0.2, 5)] if 100 <= t < 105 else []) for t in range(600)]
p.check("11c: Kurz-ID nur mit conf < 0.25 zaehlt nicht", tp.kennzahlen(schwach_kurz)["kurz_ids"] == 0)
grenz_kurz = [[(0.8, 1)] + ([(0.25, 5)] if 100 <= t < 105 else []) for t in range(600)]
p.check("11c: Kurz-ID mit conf genau 0.25 zaehlt", tp.kennzahlen(grenz_kurz)["kurz_ids"] == 1)

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

    def lauf(argv: list[str], szenario) -> int:
        tp.verfolge = lambda bilder, pfad, ids: szenario
        alt = sys.argv
        sys.argv = ["tracking_pruefung.py", str(clip)] + argv
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return tp.main()
        except SystemExit as fehler:
            return fehler.code
        finally:
            sys.argv = alt

    p.check("13: ✓ -> 0", lauf(["--kuehe", "2", "--tracker", "a.yaml"], stabil) == 0)
    p.check("13: ✗ -> 1", lauf(["--kuehe", "2", "--tracker", "a.yaml"], viele) == 1)
    p.check("13: ? -> 3", lauf(["--kuehe", "2", "--tracker", "a.yaml"], f4) == 3)
    p.check("13: ✗ hat Vorrang vor ?",
            tp.exit_code({"a": tp.kennzahlen(viele, 2), "b": tp.kennzahlen(f4, 2)}) == 1)
    p.check("13: ohne --kuehe -> 2", lauf(["--tracker", "a.yaml"], stabil) == 2)
    p.check("13: --kuehe -1 -> 2", lauf(["--kuehe", "-1"], stabil) == 2)
    p.check("13: --kuehe zwei -> 2", lauf(["--kuehe", "zwei"], stabil) == 2)
    p.check("13: falsche Tierklassen -> 2",
            lauf(["--kuehe", "2", "--tier-klassen", "pferd"], stabil) == 2)
    (Path(tmp) / "fehlt.mp4")
    clip_alt, clip = clip, Path(tmp) / "fehlt.mp4"
    p.check("13: Ablage fehlt -> 2", lauf(["--kuehe", "2"], stabil) == 2)
    clip = clip_alt

sys.exit(p.bericht())
