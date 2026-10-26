#!/usr/bin/env python3
"""Logiktests der Tracking-Pruefung (training/tracking_pruefung.py).

Die Zusagen: Aus einem Video wird 1 Bild je Sekunde genommen wie im
Agenten; ID-Wechsel werden gegen die Zahl gleichzeitig sichtbarer Kuehe
gezaehlt, Flackern unter 10 s zaehlt nicht als Kuh; Erkennungen ohne ID
werden je Konfidenzband ausgewiesen (nachts unter new_track_thresh
bekommt eine neu auftauchende Kuh keine ID). Ohne numpy/cv2/ultralytics.
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

sys.exit(p.bericht())
