#!/usr/bin/env python3
"""Logiktests Schwanzwinkel: nur sichtbare Keypoints zaehlen.

Die Zusage: Ein verdeckter Schwanz erzeugt keinen Phantomwinkel.
Ultralytics meldet Keypoints mit Konfidenz < 0.5 als (0, 0); ungeprueft
ergab das einen Winkel gegen die Bildecke (oft > 45°), der ins
30-Minuten-Fenster zaehlte und einen Kalbeverdacht ausloesen konnte, ohne
dass das Modell einen erhobenen Schwanz gesehen hat. Dazu der Dateiname der
Silent-Mode-Bilder (Kamera + Zeit, Grundlage fuer den Split nach Tagen).
"""

import sys
import time as echte_zeit
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, _ = lade_main()
p = Pruefer("Schwanzwinkel & Trainingsbild-Name")

w = m.schwanzwinkel_grad

# --- Reine Formel (unveraendert gegenueber der numpy-Fassung) -------------

p.check("anliegender Schwanz -> 0°", abs(w((0, 0), (100, 0), (150, 0))) < 1e-9)
p.check("rechtwinklig -> 90°", abs(w((0, 0), (100, 0), (100, 60)) - 90) < 1e-9)
p.check("Richtung egal (Betrag)", abs(w((0, 0), (100, 0), (100, -60)) - 90) < 1e-9)
p.check("45° exakt", abs(w((0, 0), (100, 0), (150, 50)) - 45) < 1e-9)
p.check("entarteter Ruecken -> None", w((5, 5), (5.5, 5), (50, 50)) is None)
p.check("entarteter Schwanz -> None", w((0, 0), (100, 0), (100.4, 0)) is None)
p.check("NaN -> None", w((0, 0), (float("nan"), 0), (1, 1)) is None)
p.check("unvollstaendiger Punkt -> None", w((0,), (100, 0), (150, 0)) is None)

# --- Sichtbarkeitspruefung der InferenceEngine ----------------------------

e = m.InferenceEngine({"modell": {
    "pfad": "",
    "keypoints": {"spine_end": 0, "tail_base": 1, "tail_tip": 2},
    "klassen": {"kuh": 0, "amniotic_sac": 1, "calf_legs": 2},
}})
p.check("Default keypoint_min_konfidenz 0.5", e.kp_min_konf == 0.5)

anliegend = [(200, 300), (400, 300), (450, 300)]
p.check("sichtbar, mit Konfidenz -> Winkel", abs(e._schwanzwinkel(anliegend, [0.9, 0.9, 0.8])) < 1e-9)
p.check("sichtbar, ohne Konfidenz -> Winkel", abs(e._schwanzwinkel(anliegend)) < 1e-9)

# Der Fehlerfall: tail_tip verdeckt -> Ultralytics liefert (0, 0)
verdeckt = [(200, 300), (400, 300), (0, 0)]
p.check(
    "Beleg: ungeprueft waere (0, 0) ein Phantomwinkel > 45°",
    w(*verdeckt) is not None and w(*verdeckt) > 45,
)
p.check("tail_tip (0, 0) ohne Konfidenz -> None", e._schwanzwinkel(verdeckt) is None)
p.check("tail_tip Konfidenz 0.3 -> None", e._schwanzwinkel(verdeckt, [0.9, 0.9, 0.3]) is None)
p.check(
    "Konfidenz knapp unter Schwelle -> None (auch ohne (0, 0))",
    e._schwanzwinkel(anliegend, [0.9, 0.49, 0.9]) is None,
)
p.check("spine_end (0, 0) -> None", e._schwanzwinkel([(0, 0), (400, 300), (450, 300)]) is None)
p.check("zu wenige Keypoints -> None", e._schwanzwinkel([(200, 300), (400, 300)]) is None)
p.check("Konfidenzliste zu kurz -> None", e._schwanzwinkel(anliegend, [0.9]) is None)
ohne_kp = m.InferenceEngine({"modell": {"pfad": "", "keypoints": {}, "klassen": {"kuh": 0}}})
p.check("Keypoint fehlt in der Konfiguration -> None statt Fehler", ohne_kp._schwanzwinkel(anliegend) is None)

streng = m.InferenceEngine({"modell": {
    "pfad": "",
    "keypoints": {"spine_end": 0, "tail_base": 1, "tail_tip": 2},
    "klassen": {"kuh": 0},
    "keypoint_min_konfidenz": 0.7,
}})
p.check("konfigurierte Schwelle 0.7 greift", streng._schwanzwinkel(anliegend, [0.9, 0.9, 0.6]) is None)

# --- Wirkung im 30-Minuten-Fenster: verdeckter Schwanz -> kein Verdacht ----

UHR = [50_000.0]
m.time = types.SimpleNamespace(
    **{k: getattr(echte_zeit, k) for k in dir(echte_zeit) if not k.startswith("_")}
)
m.time.time = lambda: UHR[0]

logik = m.LogicEngine({
    "logik": {
        "winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
        "override_konfidenz": 0.80, "brunst_min_dauer_s": 4,
    },
    "telegram": {"cooldown_minuten": 15},
})
alarme = []
for s in range(0, 40 * 60, 60):  # 40 min, ein Frame pro Minute, Schwanz verdeckt
    UHR[0] = 50_000.0 + s
    kuh = m.KuhBeobachtung(7, (150, 250, 480, 380), e._schwanzwinkel(verdeckt, [0.9, 0.9, 0.2]), None)
    alarme += [a for a in logik.bewerte([kuh], []) if a.typ == "kalbeverdacht"]
p.check("40 min verdeckter Schwanz -> kein Kalbeverdacht", alarme == [])

# --- Dateiname der Silent-Mode-Bilder --------------------------------------

zeit = echte_zeit.mktime((2026, 10, 16, 3, 15, 0, 0, 0, -1))
p.check(
    "Kamera + Zeit im Namen",
    m.trainingsbild_name("stallwache", zeit) == "stallwache_20261016-031500.jpg",
)
p.check(
    "Pfad-/Trennzeichen im Kameranamen entschaerft",
    m.trainingsbild_name("futter/wache_2", zeit) == "futter-wache-2_20261016-031500.jpg",
)
p.check("leerer Kameraname -> Platzhalter", m.trainingsbild_name("", zeit).startswith("kamera_"))

sys.exit(p.bericht())
