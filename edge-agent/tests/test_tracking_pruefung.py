#!/usr/bin/env python3
"""Logiktests der Tracking-Pruefung (training/tracking_pruefung.py).

Die Zusagen: Aus einem Video wird 1 Bild je Sekunde genommen wie im
Agenten, auch wenn der Container die Bildzahl nicht kennt; ID-Wechsel werden
gegen die Zahl gleichzeitig sichtbarer Kuehe gezaehlt, Flackern unter 10 s
zaehlt nicht als Kuh; Erkennungen ohne ID werden je Konfidenzband
ausgewiesen (nachts unter new_track_thresh bekommt eine neu auftauchende Kuh
keine ID). Das Gesamturteil faellt auch bei schnellem ID-Wechsel (neue ID
alle paar Sekunden), bei einer Luecke ohne ID ab 30 min und bei Geistern
(mehr Kuehe mit ID als angegeben). Ohne numpy/cv2/ultralytics.
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
p.check("2: 2 Kuehe erkannt", k["kuehe"] == 2)
p.check("2: 0 Wechsel, Ziel erfuellt", k["wechsel"] == 0 and k["ziel_erfuellt"])
p.check("2: Dauer 10 min", k["dauer_min"] == 10.0)

# --- 3. Kuh 2 bekommt nach Verdeckung eine neue ID --------------------------
wechsel = ([[(0.8, 1), (0.7, 2)] for _ in range(300)]
           + [[(0.8, 1)] for _ in range(120)]
           + [[(0.8, 1), (0.7, 3)] for _ in range(180)])
k = tp.kennzahlen(wechsel)
p.check("3: 3 lange IDs bei 2 Kuehen -> 1 Wechsel", k["ids_lang"] == 3 and k["wechsel"] == 1)
p.check("3: 1 Wechsel / 2 Kuehe / 10 min = 0.5 -> Ziel erfuellt",
        k["wechsel_je_kuh_10min"] == 0.5 and k["ziel_erfuellt"])

# --- 4. Viele Wechsel verfehlen das Ziel ------------------------------------
viele = []
for t in range(600):
    viele.append([(0.8, 1), (0.7, 100 + t // 20)])  # Kuh 2: alle 20 s neue ID
k = tp.kennzahlen(viele)
p.check("4: 30 IDs fuer Kuh 2 -> 29 Wechsel", k["wechsel"] == 29)
p.check("4: Ziel verfehlt", not k["ziel_erfuellt"])

# --- 5. Flackern unter 10 s zaehlt nicht als Kuh ---------------------------
flackern = [[(0.8, 1)] + ([(0.3, 50 + t)] if t % 60 == 0 else []) for t in range(600)]
k = tp.kennzahlen(flackern)
p.check("5: kurze Einzel-IDs zaehlen weder als Kuh noch als Wechsel",
        k["kuehe"] == 1 and k["ids_lang"] == 1 and k["wechsel"] == 0)

# --- 6. Nachts: Erkennungen ohne ID je Band --------------------------------
nacht = [[(0.85, 1), (0.45, None), (0.3, None)] for _ in range(600)]
k = tp.kennzahlen(nacht)
p.check("6: Band 0.40–0.50: 600 von 600 ohne ID", k["ohne_id"]["0.40–0.50"] == (600, 600))
p.check("6: Band 0.25–0.40: 600 von 600 ohne ID", k["ohne_id"]["0.25–0.40"] == (600, 600))
p.check("6: Band 0.50–1.00: 0 ohne ID", k["ohne_id"]["0.50–1.00"] == (600, 0))

# --- 7. Leerer Clip ---------------------------------------------------------
k = tp.kennzahlen([[] for _ in range(60)])
p.check("7: ohne Erkennung 0 Kuehe, Ziel nicht erfuellt", k["kuehe"] == 0 and not k["ziel_erfuellt"])

# --- 8. Tabelle fuer die Modellkarte ---------------------------------------
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(wechsel),
                 "bytetrack.yaml": tp.kennzahlen(viele)}, 0.8)
p.check("8: Tabelle nennt beide Tracker", "tracker-kuh.yaml" in md and "bytetrack.yaml" in md)
p.check("8: Warnung unter 1 FPS", "UNTER 1 FPS" in md)
p.check("8: Ziel-Haken", "0.5 ✓" in md and "✗" in md)
p.check("8: ohne Nacht-Luecke kein Achtung-Hinweis", "Achtung" not in md)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(nacht)}, None)
p.check("8: Nacht-Kuehe ohne ID -> Achtung-Hinweis", "**Achtung tracker-kuh.yaml:** 67%" in md)
p.check("8: Anteil ab 0.25: 1200 ohne ID von 1800", abs(tp.ohne_id_anteil(tp.kennzahlen(nacht)) - 2 / 3) < 1e-9)

# --- 9. Schneller ID-Wechsel faellt durch (vorher faelschlich ✓) -----------
schnell = [[(0.8, 1000 + t // 5)] for t in range(600)]  # alle 5 s neue ID
k = tp.kennzahlen(schnell)
p.check("9: alle 5 s neue ID -> 100 % Kurz-ID", k["kurz_anteil"] == 1.0)
p.check("9: keine lange ID -> Wechsel-Kriterium verfehlt", not k["wechsel_ok"])
p.check("9: Gesamturteil verfehlt", not k["ziel_erfuellt"])
neben = [[(0.8, 1), (0.7, 1000 + t // 5)] for t in range(600)]
k = tp.kennzahlen(neben)
p.check("9: neben stabiler Kuh -> Gesamturteil verfehlt",
        not k["ziel_erfuellt"] and k["kurz_anteil"] == 0.5)
md = tp.tabelle({"tracker-kuh.yaml": tp.kennzahlen(schnell)}, None)
p.check("9: Achtung-Hinweis Kurz-ID", "keine 10 s hält" in md and "| **Gesamt** | ✗ |" in md)

# --- 10. Laengste Luecke ohne ID -------------------------------------------
luecke = ([[(0.8, 1)] for _ in range(300)]
          + [[(0.8, 1), (0.45, None)] for _ in range(31 * 60)]
          + [[(0.8, 1)] for _ in range(300)])
k = tp.kennzahlen(luecke)
p.check("10: 31 min am Stueck ohne ID", k["laengste_luecke_min"] == 31.0)
p.check("10: Gesamturteil verfehlt", not k["ziel_erfuellt"])
p.check("10: Hinweis Kalbeverdachts-Fenster",
        "länger als ein Kalbeverdachts-Fenster" in tp.tabelle({"x": k}, None))
k = tp.kennzahlen([[(0.8, 1), (0.2, None)] for _ in range(600)])
p.check("10: unter conf 0.25 keine Luecke", k["laengste_luecke_min"] == 0.0)

# --- 11. Echte Kuhzahl entlarvt Geister ------------------------------------
geist = [[(0.8, 1), (0.3, 2)] for _ in range(600)]  # Heuballen mit eigener ID
k = tp.kennzahlen(geist)
p.check("11: ohne --kuehe zaehlt der Geist als Kuh (bekannte Grenze)",
        k["kuehe"] == 2 and k["ziel_erfuellt"])
k = tp.kennzahlen(geist, kuehe_echt=1)
p.check("11: mit --kuehe 1 -> Geist erkannt, Gesamturteil verfehlt",
        k["geister"] and not k["ziel_erfuellt"])
md = tp.tabelle({"bytetrack.yaml": k}, None)
p.check("11: Tabelle nennt echte Zahl und Geist", "(echt: 1)" in md and "Geist" in md)
k = tp.kennzahlen(stabil, kuehe_echt=2)
p.check("11: echte Zahl stimmt -> Ziel erfuellt", k["ziel_erfuellt"] and not k["geister"])

# --- 12. Bildwahl ohne bekannte Bildzahl, Klassen wie im Agenten -----------
nimm = tp.sekundenwahl(25)
p.check("12: Strom ohne Bildzahl = sekundenbilder",
        [i for i in range(250) if nimm(i)] == tp.sekundenbilder(25, 250))
p.check("12: Kuh (cls 0) ist Tier", tp.ist_tier([1, 2, 3, 4, 0.8, 0], {0}))
p.check("12: Fruchtblase (cls 1) ist kein Tier", not tp.ist_tier([1, 2, 3, 4, 0.9, 1], {0}))
p.check("12: alte Ablage ohne Klasse -> Tier", tp.ist_tier([1, 2, 3, 4, 0.8], set()))

sys.exit(p.bericht())
