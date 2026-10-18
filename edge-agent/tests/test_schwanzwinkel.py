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
p.check("Sichtbarkeitsgrenze = Ultralytics-Definition 0.5", m.KEYPOINT_SICHTBAR_AB == 0.5)

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

p.check("Konfidenz genau 0.5 zaehlt als sichtbar", e._schwanzwinkel(anliegend, [0.5, 0.5, 0.5]) is not None)
p.check(
    "Keypoint am Bildrand (0, 300) zaehlt, nur exakt (0, 0) faellt raus",
    e._schwanzwinkel([(0, 300), (200, 300), (250, 300)]) is not None,
)

# --- Verdrahtung in analysiere(): kps.conf wird durchgereicht ---------------


class T:
    """Tensor-Ersatz mit .cpu().numpy()."""

    def __init__(self, wert):
        self.wert = wert

    def cpu(self):
        return self

    def numpy(self):
        return self.wert


class Boxen:
    def __init__(self, cls, conf, xyxy, ids):
        self.cls, self.conf, self.xyxy, self.id = cls, conf, xyxy, ids

    def __len__(self):
        return len(self.cls)


def ergebnis(kps):
    boxen = Boxen([0, 2], [0.9, 0.85], [(150, 250, 480, 380), (10, 10, 50, 50)], [7, 8])
    return types.SimpleNamespace(boxes=boxen, keypoints=kps)


e.modell = types.SimpleNamespace(track=lambda frame, **kw: [ergebnis(KPS[0])])
KPS = [types.SimpleNamespace(
    xy=[T(anliegend), T([(0, 0)] * 3)],
    conf=[T([0.9, 0.9, 0.2]), T([0.0, 0.0, 0.0])],
)]
kuehe, objekte = e.analysiere(None)
p.check("analysiere: niedrige tail_tip-Konfidenz -> kein Winkel", kuehe[0].winkel_grad is None)
p.check("analysiere: Kaelberfuesse unabhaengig von Keypoints erkannt",
        [o.klasse for o in objekte] == ["calf_legs"])
KPS[0] = types.SimpleNamespace(xy=[T(anliegend), T([(0, 0)] * 3)], conf=None)
kuehe, _ = e.analysiere(None)
p.check("analysiere: Modell ohne Sichtbarkeitsspalte -> Winkel aus Koordinaten",
        kuehe[0].winkel_grad is not None and abs(kuehe[0].winkel_grad) < 1e-9)
e.modell = None

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

# Recall bleibt: Die Haelfte der Frames verdeckt, von den sichtbaren 30 %
# erhoben -> Anteil 30 % > 20 % -> Kalbeverdacht muss weiterhin kommen.
erhoben = [(200, 300), (400, 300), (400, 200)]  # 90°
logik = m.LogicEngine({
    "logik": {
        "winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
        "override_konfidenz": 0.80, "brunst_min_dauer_s": 4,
    },
    "telegram": {"cooldown_minuten": 15},
})
alarme = []
for n, s in enumerate(range(0, 30 * 60, 30)):  # 30 min, alle 30 s
    UHR[0] = 60_000.0 + s
    if n % 2:
        punkte, konf = verdeckt, [0.9, 0.9, 0.1]
    else:
        punkte, konf = (erhoben if (n // 2) % 10 < 3 else anliegend), [0.9, 0.9, 0.9]
    kuh = m.KuhBeobachtung(9, (150, 250, 480, 380), e._schwanzwinkel(punkte, konf), None)
    alarme += [a for a in logik.bewerte([kuh], []) if a.typ == "kalbeverdacht"]
p.check("halb verdeckt, 30 % der sichtbaren erhoben -> Kalbeverdacht bleibt", len(alarme) >= 1)
p.check("Alarmtext nennt Anteil mit Leerzeichen, Bildzahl und Spanne",
        bool(alarme) and " % der auswertbaren Bilder über 45° angehoben (" in alarme[0].nachricht
        and "beobachtet in den letzten" in alarme[0].nachricht
        and "Wehenzeichen" in alarme[0].nachricht)

# Nach langer Verdeckung: der Text verraet, wie kurz die Evidenz ist
logik = m.LogicEngine({
    "logik": {
        "winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
        "override_konfidenz": 0.80, "brunst_min_dauer_s": 4,
    },
    "telegram": {"cooldown_minuten": 15},
})
kurz = []
for s in range(20):  # 20 s sichtbar erhoben nach 29 min Verdeckung
    UHR[0] = 65_000.0 + s
    kuh = m.KuhBeobachtung(11, (150, 250, 480, 380), e._schwanzwinkel(erhoben, [0.9] * 3), None)
    kurz += [a for a in logik.bewerte([kuh], []) if a.typ == "kalbeverdacht"]
p.check("kurze Evidenz steht im Text (erst seit 19 s, Grund, Pruefhinweis)",
        bool(kurz) and "beobachtet erst seit 19 s – neue Nummer, Neustart" in kurz[0].nachricht
        and "Koten oder Fliegenabwehr" in kurz[0].nachricht)
p.check("Bildzahl im kurzen Text stimmt (20 von 20)", bool(kurz) and "(20 von 20 Bildern" in kurz[0].nachricht)
p.check("Spanne wird abgerundet (89,6 s -> 89 s, nie mehr als belegt)",
        "erst seit 89 s" in logik._kalbe_text(99, m.deque([(1000.0, True)]), 1.0, 1089.6))

# Folgemeldungen bei anhaltenden Wehen: nach jeder Meldung beginnt das
# Fenster neu (p.clear()) – der Text darf trotzdem nicht zum Kurztext werden.
logik = m.LogicEngine({
    "logik": {
        "winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
        "override_konfidenz": 0.80, "brunst_min_dauer_s": 4,
    },
    "telegram": {"cooldown_minuten": 15},
})
serie = []
for s in range(20 * 60):  # 20 min, 1 FPS, jedes 2. Bild erhoben
    UHR[0] = 120_000.0 + s
    punkte = erhoben if s % 2 else anliegend
    kuh = m.KuhBeobachtung(7, (150, 250, 480, 380), e._schwanzwinkel(punkte, [0.9] * 3), None)
    serie += [(s, a.nachricht) for a in logik.bewerte([kuh], []) if a.typ == "kalbeverdacht"]
erste_t, erste = serie[0]
nach_15 = [n for s, n in serie if s - erste_t >= 900][0]
p.check("Serie: erste Meldung einer neuen Nummer nennt die kurze Beobachtung",
        "beobachtet erst seit" in erste)
p.check("Serie: Folgemeldung nach 15 min nennt die Dauer, kein Kurztext",
        "weiterhin über 45° angehoben: seit 15 min immer wieder auffällig" in nach_15
        and "Koten" not in nach_15 and "Wehenzeichen" in nach_15)
p.check("Serie: keine Folgemeldung mit Kurztext", all("erst seit" not in n for _, n in serie[1:]))
UHR[0] = 120_000.0 + 20 * 60 + 31 * 60  # 31 min Pause ohne Meldung dieser Nummer
logik.bewerte([], [])
p.check("Serie endet nach einem Fenster ohne Meldung", 7 not in logik.serien)

# Fenster verschwundener IDs werden freigegeben (Speicher im Dauerbetrieb)
logik = m.LogicEngine({
    "logik": {
        "winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
        "override_konfidenz": 0.80, "brunst_min_dauer_s": 4,
    },
    "telegram": {"cooldown_minuten": 15},
})
UHR[0] = 100_000.0
logik.bewerte([m.KuhBeobachtung(i, (0, 0, 10, 10), 10.0, None) for i in (1, 2, 3)], [])
p.check("drei IDs im Fenster", sorted(logik.puffer) == [1, 2, 3])
UHR[0] = 100_000.0 + 31 * 60
logik.bewerte([m.KuhBeobachtung(3, (0, 0, 10, 10), 10.0, None)], [])
p.check("nach > 30 min ohne Beobachtung: Fenster von ID 1 und 2 freigegeben", sorted(logik.puffer) == [3])
p.check("ID 3 behaelt nur den neuen Eintrag", len(logik.puffer[3]) == 1)

# Austreibungs-Override haengt nie an Keypoints
UHR[0] = 90_000.0
kuh = m.KuhBeobachtung(9, (150, 250, 480, 380), e._schwanzwinkel([(0, 0)] * 3, [0.1] * 3), None)
treffer = logik.bewerte([kuh], [m.ObjektErkennung("calf_legs", 0.85, (10, 10, 50, 50))])
p.check("alle Keypoints verdeckt + Kaelberfuesse 0.85 -> Austreibung",
        any(a.typ == "austreibung" for a in treffer))

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
