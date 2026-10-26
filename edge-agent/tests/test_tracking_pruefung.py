#!/usr/bin/env python3
"""Logiktests der Tracking-Pruefung (training/tracking_pruefung.py).

Die Zusagen: Aus einem Video wird 1 Bild je Sekunde genommen wie im
Agenten, auch wenn der Container die Bildzahl nicht kennt; ID-Wechsel werden
gegen die Zahl der Kuehe gezaehlt, Flackern unter 10 s zaehlt nicht als Kuh.
Ein Gesamturteil gibt es nur mit der echten Kuhzahl. Es faellt bei vielen
Wechseln, bei Kurz-IDs (neue ID alle paar Sekunden, auch in grossen
Herden), bei sichtbaren Kuehen ohne lange ID (Anteil und Luecke ab 30 min,
auch wenn die Kuh zwischendurch schwach oder gar nicht erkannt wird), bei
Geistern und bei 0 angegebenen Kuehen mit Geist-ID. Fehlerkennungen ohne ID
neben getrackten Kuehen sind nur ein Hinweis. Ohne numpy/cv2/ultralytics.
"""

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer  # noqa: E402

PFAD = Path(__file__).resolve().parent.parent / "training" / "tracking_pruefung.py"
spec = importlib.util.spec_from_file_location("tracking_pruefung", PFAD)
tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tp)
p = Pruefer("Tracking-Pruefung")

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
p.check("2: ohne --kuehe kein Gesamturteil", not k["beurteilt"] and not k["ziel_erfuellt"])
p.check("2: Dauer 10 min", k["dauer_min"] == 10.0)
k = tp.kennzahlen(stabil, kuehe_echt=2)
p.check("2: 0 Wechsel, mit --kuehe 2 Ziel erfuellt", k["wechsel"] == 0 and k["ziel_erfuellt"])

# --- 3. Kuh 2 bekommt nach Verdeckung eine neue ID --------------------------
wechsel = ([[(0.8, 1), (0.7, 2)] for _ in range(300)]
           + [[(0.8, 1)] for _ in range(120)]
           + [[(0.8, 1), (0.7, 3)] for _ in range(180)])
k = tp.kennzahlen(wechsel, kuehe_echt=2)
p.check("3: 3 lange IDs bei 2 Kuehen -> 1 Wechsel", k["ids_lang"] == 3 and k["wechsel"] == 1)
p.check("3: 1 Wechsel / 2 Kuehe / 10 min = 0.5 -> Ziel erfuellt",
        k["wechsel_je_kuh_10min"] == 0.5 and k["ziel_erfuellt"])
p.check("3: ganz verdeckte Kuh zaehlt nicht als 'ohne ID'",
        k["kuh_anteil_ohne_id"] == 0.0 and k["laengste_luecke_s"] == 0)

# --- 4. Viele Wechsel verfehlen das Ziel ------------------------------------
viele = []
for t in range(600):
    viele.append([(0.8, 1), (0.7, 100 + t // 20)])  # Kuh 2: alle 20 s neue ID
k = tp.kennzahlen(viele, kuehe_echt=2)
p.check("4: 30 IDs fuer Kuh 2 -> 29 Wechsel", k["wechsel"] == 29)
p.check("4: Ziel verfehlt", not k["wechsel_ok"] and not k["ziel_erfuellt"])

# --- 5. Flackern unter 10 s zaehlt nicht als Kuh ---------------------------
flackern = [[(0.8, 1)] + ([(0.3, 50 + t)] if t % 60 == 0 else []) for t in range(600)]
k = tp.kennzahlen(flackern)
p.check("5: kurze Einzel-IDs zaehlen weder als Kuh noch als Wechsel",
        k["kuehe"] == 1 and k["ids_lang"] == 1 and k["wechsel"] == 0)
p.check("5: aber als Kurz-IDs (10 in 10 min)", k["kurz_ids"] == 10)

# --- 6. Nachts: Erkennungen ohne ID je Band --------------------------------
nacht = [[(0.85, 1), (0.45, None), (0.3, None)] for _ in range(600)]
k = tp.kennzahlen(nacht)
p.check("6: Band 0.40–0.50: 600 von 600 ohne ID", k["ohne_id"]["0.40–0.50"] == (600, 600))
p.check("6: Band 0.25–0.40: 600 von 600 ohne ID", k["ohne_id"]["0.25–0.40"] == (600, 600))
p.check("6: Band 0.50–1.00: 0 ohne ID", k["ohne_id"]["0.50–1.00"] == (600, 0))
k = tp.kennzahlen(nacht, kuehe_echt=3)
p.check("6: mit --kuehe 3: 2 von 3 sichtbaren Kuehen ohne ID -> verfehlt",
        abs(k["kuh_anteil_ohne_id"] - 2 / 3) < 1e-9 and not k["ziel_erfuellt"])

# --- 7. Leerer Clip ---------------------------------------------------------
k = tp.kennzahlen([[] for _ in range(60)])
p.check("7: ohne Erkennung 0 Kuehe, Ziel nicht erfuellt", k["kuehe"] == 0 and not k["ziel_erfuellt"])

# --- 8. Tabelle fuer die Modellkarte ---------------------------------------
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(wechsel, 2),
                 "bytetrack.yaml": tp.kennzahlen(viele, 2)}, 0.8)
p.check("8: Tabelle nennt beide Tracker", "tracker-kuh.yaml" in md and "bytetrack.yaml" in md)
p.check("8: Warnung unter 1 FPS", "UNTER 1 FPS" in md)
p.check("8: Ziel-Haken", "0.5 ✓" in md and "| **Gesamt** | ✓ | ✗ |" in md)
p.check("8: ohne Nacht-Luecke kein Achtung-Hinweis", "Achtung" not in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(nacht, 3)}, None)
p.check("8: Nacht-Kuehe ohne ID -> Achtung-Hinweis",
        "**Achtung tracker-kuh.yaml:** 67% der sichtbaren Kuh-Sekunden" in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(nacht)}, None)
p.check("8: ohne --kuehe: Hinweis, Gesamt '–'",
        "**Hinweis tracker-kuh.yaml:** 67%" in md and "– (--kuehe fehlt)" in md)
p.check("8: Anteil ab 0.25: 1200 ohne ID von 1800", abs(tp.ohne_id_anteil(tp.kennzahlen(nacht)) - 2 / 3) < 1e-9)

# --- 9. Schneller ID-Wechsel faellt durch, auch in grossen Herden ----------
schnell = [[(0.8, 1000 + t // 5)] for t in range(600)]  # alle 5 s neue ID
k = tp.kennzahlen(schnell, kuehe_echt=1)
p.check("9: alle 5 s neue ID -> 120 Kurz-IDs je Kuh / 10 min", k["kurz_je_kuh_10min"] == 120.0)
p.check("9: keine lange ID -> Wechsel, Anteil ohne ID und Gesamt verfehlt",
        not k["wechsel_ok"] and not k["ohne_id_ok"] and not k["ziel_erfuellt"])
md = tp.tabelle({"tracker-kuh.yaml": k}, None)
p.check("9: Achtung-Hinweis Kurz-ID", "hielten keine 10 s" in md and "| **Gesamt** | ✗ |" in md)
herde = [[(0.8, c) for c in range(1, 21)] + [(0.7, 1000 + t // 5)] for t in range(600)]
k = tp.kennzahlen(herde, kuehe_echt=21)
p.check("9: 20 stabile + 1 wechselnde Kuh -> Kurz-ID-Kriterium verfehlt",
        not k["kurz_ok"] and not k["ziel_erfuellt"])

# --- 10. Laengste Luecke: Kuh sichtbar, ohne lange ID -----------------------
luecke = ([[(0.8, 1)] for _ in range(300)]
          + [[(0.8, 1), (0.45, None)] for _ in range(31 * 60)]
          + [[(0.8, 1)] for _ in range(300)])
k = tp.kennzahlen(luecke, kuehe_echt=2)
p.check("10: 31 min am Stueck ohne ID", k["laengste_luecke_s"] == 31 * 60)
p.check("10: Gesamturteil verfehlt", not k["luecke_ok"] and not k["ziel_erfuellt"])
p.check("10: Hinweis Kalbeverdachts-Fenster",
        "länger als ein Kalbeverdachts-Fenster" in tp.tabelle({"x": k}, None))
# Schwankend: Kuh B nur 0.12–0.33, jedes 10. Bild gar nicht erkannt
schwach = [[(0.8, 1)] + ([(0.12 + (t % 7) * 0.035, None)] if t % 10 else []) for t in range(2400)]
k = tp.kennzahlen(schwach, kuehe_echt=2)
p.check("10: kurze Aussetzer und conf unter 0.25 unterbrechen die Luecke nicht",
        k["laengste_luecke_s"] >= 39 * 60 and not k["luecke_ok"])
weg = ([[(0.8, 1), (0.4, None)] for _ in range(20 * 60)] + [[(0.8, 1)] for _ in range(60)]
       + [[(0.8, 1), (0.4, None)] for _ in range(20 * 60)])
k = tp.kennzahlen(weg, kuehe_echt=2)
p.check("10: 60 s ganz verdeckt trennt die Luecke", k["laengste_luecke_s"] == 20 * 60 and k["luecke_ok"])
def mit_pause(s: int) -> list:
    return ([[(0.8, 1), (0.4, None)] for _ in range(100)] + [[(0.8, 1)] for _ in range(s)]
            + [[(0.8, 1), (0.4, None)] for _ in range(100)])
p.check("10: Pause 10 s wird ueberbrueckt",
        tp.kennzahlen(mit_pause(10), kuehe_echt=2)["laengste_luecke_s"] == 210)
p.check("10: Pause 11 s trennt", tp.kennzahlen(mit_pause(11), kuehe_echt=2)["laengste_luecke_s"] == 100)
grenz = [[(0.8, 1), (0.4, None)] for _ in range(1798)] + [[(0.8, 1)] for _ in range(600)]
k = tp.kennzahlen(grenz, kuehe_echt=2)
md = tp.tabelle({"x": k}, None)
p.check("10: 1798 s -> '29.9 min', kein Luecken-Hinweis",
        "29.9 min ✓" in md and "Kalbeverdachts-Fenster" not in md.split("Ziel je")[0])
k = tp.kennzahlen([[(0.8, 1), (0.3, None)] for _ in range(600)], kuehe_echt=1)
p.check("10: Fehlerkennung neben getrackter Kuh -> keine Luecke, kein Anteil",
        k["laengste_luecke_s"] == 0 and k["kuh_anteil_ohne_id"] == 0.0)
herde_blind = [[(0.8, c) for c in range(1, 21)] + [(0.33, None)] for _ in range(600)]
k = tp.kennzahlen(herde_blind, kuehe_echt=21)
p.check("10: 10-min-Clip, 1 von 21 Kuehen nie mit ID -> verfehlt (Anteil allein 4.8 %)",
        k["ohne_id_ok"] and not k["luecke_ok"] and not k["ziel_erfuellt"])
p.check("10: Hinweis nennt kurzen Clip", "kaum verfolgt" in tp.tabelle({"x": k}, None))
rauschen = [[(0.8, 1)] + ([(0.3, None)] if t % 16 == 0 else []) for t in range(600)]
k = tp.kennzahlen(rauschen, kuehe_echt=1)
md = tp.tabelle({"x": k}, None)
p.check("10: Einzelbild-Rauschen 6 % -> Ziel erfuellt, nur Hinweis",
        k["ziel_erfuellt"] and "**Hinweis x:**" in md and "Achtung" not in md)

# --- 11. Echte Kuhzahl entlarvt Geister ------------------------------------
geist = [[(0.8, 1), (0.3, 2)] for _ in range(600)]  # Heuballen mit eigener ID
k = tp.kennzahlen(geist)
p.check("11: ohne --kuehe zaehlt der Geist als Kuh, kein Urteil",
        k["kuehe"] == 2 and not k["beurteilt"])
k = tp.kennzahlen(geist, kuehe_echt=1)
p.check("11: mit --kuehe 1 -> Geist erkannt, Gesamturteil verfehlt",
        k["geister"] and not k["ziel_erfuellt"])
md = tp.tabelle({"bytetrack.yaml": k}, None)
p.check("11: Tabelle nennt angegebene Zahl und Geist", "angegeben 1" in md and "Geist" in md)
k = tp.kennzahlen(stabil, kuehe_echt=2)
p.check("11: echte Zahl stimmt -> Ziel erfuellt", k["ziel_erfuellt"] and not k["geister"])
k = tp.kennzahlen([[(0.45, 7)] for _ in range(600)], kuehe_echt=0)
p.check("11: leere Box, Heuballen mit ID, --kuehe 0 -> verfehlt",
        k["geister"] and not k["wechsel_ok"] and not k["ziel_erfuellt"])
k = tp.kennzahlen([[] for _ in range(600)], kuehe_echt=0)
p.check("11: leere Box ohne Erkennung, --kuehe 0 -> erfuellt", k["ziel_erfuellt"])
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

sys.exit(p.bericht())
