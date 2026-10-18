#!/usr/bin/env python3
"""Logiktests: Fruchtblase/Kaelberfuesse kommen am Tracker vorbei an.

Die Zusage: Jede einzelne Austreibungs-Erkennung erreicht die Logik –
auch die erste und auch flackernde. Ultralytics kuerzt nach dem Tracking
die Ergebnisse auf bestaetigte Tracks, sobald eine Kuh getrackt wird; ein
neues Objekt ist im ersten Bild unbestaetigt und fiel bisher weg
(ultralytics/trackers/track.py, on_predict_postprocess_end). Der Agent
liest die beiden Klassen deshalb in einem eigenen Callback VOR dem
Tracker. Der Ultralytics-Ablauf ist hier nachgebaut: registrierte
Callbacks laufen in Reihenfolge, danach kuerzt der "Tracker" auf Kuehe.
"""

import sys
import time as echte_zeit
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main


class T:
    """Tensor-Ersatz mit .cpu().numpy()."""

    def __init__(self, wert):
        self.wert = wert

    def cpu(self):
        return self

    def numpy(self):
        return self.wert


class Boxen:
    def __init__(self, dets, ids=None):
        self.cls = [d[5] for d in dets]
        self.conf = [d[4] for d in dets]
        self.xyxy = [d[:4] for d in dets]
        self.id = ids

    def __len__(self):
        return len(self.cls)


def ergebnis(dets, ids=None):
    sichtbar = [(200, 300), (400, 300), (450, 300)]
    kps = types.SimpleNamespace(xy=[T(sichtbar)] * len(dets), conf=[T([0.9] * 3)] * len(dets))
    return types.SimpleNamespace(boxes=Boxen(dets, ids), keypoints=kps)


class FakeYOLO:
    """Ultralytics-Ablauf: Callbacks in Reihenfolge, dann kuerzt der Tracker."""

    kuerzen = True

    def __init__(self, pfad):
        self.pfad = pfad
        self.callbacks = {"on_predict_postprocess_end": []}

    def add_callback(self, ereignis, fn):
        self.callbacks.setdefault(ereignis, []).append(fn)

    def track(self, dets, **kw):
        predictor = types.SimpleNamespace(results=[ergebnis(dets)])
        for fn in self.callbacks["on_predict_postprocess_end"]:
            fn(predictor)
        if not self.kuerzen:
            return [ergebnis(dets, ids=list(range(1, len(dets) + 1)))]
        # Nur die bestaetigte Kuh bleibt; neue/flackernde Objekte fallen weg.
        kuehe = [d for d in dets if d[5] == 0]
        return [ergebnis(kuehe, ids=[7] * len(kuehe))]


m, _ = lade_main()
ul = types.ModuleType("ultralytics")
ul.YOLO = FakeYOLO
sys.modules["ultralytics"] = ul
p = Pruefer("Austreibung vor dem Tracker")

UHR = [70_000.0]
m.time = types.SimpleNamespace(
    **{k: getattr(echte_zeit, k) for k in dir(echte_zeit) if not k.startswith("_")}
)
m.time.time = lambda: UHR[0]

CFG = {"modell": {
    "pfad": "best_v1.pt",
    "keypoints": {"spine_end": 0, "tail_base": 1, "tail_tip": 2},
    "klassen": {"kuh": 0, "amniotic_sac": 1, "calf_legs": 2},
}}


def logik():
    return m.LogicEngine({
        "logik": {
            "winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
            "override_konfidenz": 0.80, "brunst_min_dauer_s": 4, "eskalation_minuten": 60,
        },
        "telegram": {"cooldown_minuten": 15},
    })


KUH = (50, 50, 400, 300, 0.92, 0)
FUESSE = (420, 200, 460, 240, 0.92, 2)
BLASE = (420, 200, 470, 250, 0.88, 1)

e = m.InferenceEngine(CFG)
p.check("Callback beim Laden registriert (vor dem ersten track)",
        e._merke_objekte in e.modell.callbacks["on_predict_postprocess_end"])

kuehe, objekte = e.analysiere([KUH, FUESSE])
p.check("Kuh kommt aus dem Tracker-Ergebnis", [k.track_id for k in kuehe] == [7])
p.check("Kaelberfuesse kommen trotz Kuerzung an",
        [(o.klasse, round(o.konfidenz, 2)) for o in objekte] == [("calf_legs", 0.92)])

# Erstes Bild einer Austreibung -> sofort Alarm (vorher: erst ab Bild 2)
l = logik()
UHR[0] = 70_000.0
alarme = l.bewerte(*e.analysiere([KUH, BLASE]))
p.check("erste Fruchtblase -> sofort Austreibungs-Alarm",
        [a.typ for a in alarme] == ["austreibung"] and alarme[0].sofort)

# Flackern: nur jedes 2. Bild erkannt -> jede Erkennung kommt an
l = logik()
angekommen = 0
for f in range(10):
    UHR[0] = 80_000.0 + f
    dets = [KUH, FUESSE] if f % 2 else [KUH]
    _, objekte = e.analysiere(dets)
    angekommen += len(objekte)
    l.bewerte([], objekte)
p.check("flackernde Fuesse: alle 5 Erkennungen kommen an", angekommen == 5)
p.check("Episode laeuft nach dem Flackern", l.austreibung_start is not None)

# Einzelbild ohne Kuh im Bild (Tracker kuerzt dann nicht) bleibt gleich
_, objekte = e.analysiere([BLASE])
p.check("ohne getrackte Kuh: Fruchtblase kommt an", [o.klasse for o in objekte] == ["amniotic_sac"])

# Kein Objekt im Bild -> keine Altlast aus dem Vorbild
_, objekte = e.analysiere([KUH])
p.check("Bild ohne Objekt -> keine Objekte (kein Uebertrag aus dem Vorbild)", objekte == [])

# Rueckfall: Callback scheitert -> Tracker-Ergebnis wie bisher, kein Absturz
kaputt = m.InferenceEngine(CFG)
kaputt.modell.kuerzen = False
kaputt.modell.callbacks["on_predict_postprocess_end"] = [
    lambda pr: kaputt._merke_objekte(types.SimpleNamespace(results=[]))
]
kuehe, objekte = kaputt.analysiere([KUH, FUESSE])
p.check("Callback-Fehler -> Rueckfall auf Tracker-Ergebnis",
        [o.klasse for o in objekte] == ["calf_legs"] and len(kuehe) == 1)

# Ohne registrierten Callback (aeltere Ultralytics-Mechanik) -> Rueckfall
ohne = m.InferenceEngine(CFG)
ohne.modell.kuerzen = False
ohne.modell.callbacks["on_predict_postprocess_end"] = []
_, objekte = ohne.analysiere([KUH, BLASE])
p.check("Callback lief nicht -> Objekte aus dem Tracker-Ergebnis",
        [o.klasse for o in objekte] == ["amniotic_sac"])

# Objekte landen nie im Kuh-Fenster (Trennung objekt- vs. regelbasiert)
kuehe, _ = e.analysiere([KUH, FUESSE, BLASE])
p.check("Objekte erscheinen nicht als Kuh", all(k.track_id == 7 for k in kuehe) and len(kuehe) == 1)

sys.exit(p.bericht())
