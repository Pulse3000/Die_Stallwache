#!/usr/bin/env python3
"""Logiktests der Training-Pipeline (training/datensatz.py, training/abnahme.py).

Die Zusagen: Der Split trennt nach Stalltagen (keine Nachbarframes in train
UND val, jede Nacht bleibt ganz), eine Geburt landet im Val-Set, offene
Datensaetze nie. Die IR-Bilanz prueft Beschluss B9 (≥ 1/3 IR-Nacht). Die
Abnahme zaehlt Austreibung nur ab Konfidenz 0.80 und misst den Winkel mit
der Logik des Agenten. Alles ohne numpy/cv2/ultralytics.
"""

import datetime as dt
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

TRAINING = Path(__file__).resolve().parent.parent / "training"


def lade(name):
    spec = importlib.util.spec_from_file_location(name, TRAINING / f"{name}.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules[name] = modul
    spec.loader.exec_module(modul)
    return modul


m, _ = lade_main()  # vor abnahme laden: abnahme nutzt sys.modules["stall_main"]
ds = lade("datensatz")
ab = lade("abnahme")
p = Pruefer("Training-Pipeline")

# --- Dateinamen und Stalltag ------------------------------------------------

p.check(
    "Zeit aus neuem Namen",
    ds.zeit_aus_name("stallwache_20261016-031500.jpg") == dt.datetime(2026, 10, 16, 3, 15),
)
p.check("Zeit aus altem Namen", ds.zeit_aus_name("20261016-031500.jpg") == dt.datetime(2026, 10, 16, 3, 15))
p.check("ohne Zeit -> None", ds.zeit_aus_name("cvb_frame_0042.jpg") is None)
p.check("ungueltiges Datum -> None", ds.zeit_aus_name("x_20261399-250000.jpg") is None)
p.check("Kamera aus Namen", ds.kamera_aus_name("futterwache_20261016-031500.jpg") == "futterwache")
p.check("alter Name -> Kamera unbekannt", ds.kamera_aus_name("20261016-031500.jpg") == "unbekannt")
p.check("03:00 gehoert zum Stalltag davor", ds.stalltag(dt.datetime(2026, 10, 16, 3, 0)) == "20261015")
p.check("13:00 gehoert zum selben Stalltag", ds.stalltag(dt.datetime(2026, 10, 16, 13, 0)) == "20261016")
p.check(
    "Nacht 22:00 und 05:00 im selben Stalltag",
    ds.stalltag(dt.datetime(2026, 10, 15, 22)) == ds.stalltag(dt.datetime(2026, 10, 16, 5)),
)

# --- Lichtphasen und B9 -----------------------------------------------------

p.check("graustufig -> IR", ds.lichtphase(120, 1.5) == "ir")
p.check("dunkles Farbbild -> Daemmerung", ds.lichtphase(40, 20) == "daemmerung")
p.check("helles Farbbild -> Tag", ds.lichtphase(140, 25) == "tag")
b = ds.bilanz([("stallwache", "ir")] * 3 + [("stallwache", "tag")] * 5 + [("futterwache", "daemmerung")])
p.check("Bilanz zaehlt je Kamera", b["je_kamera"]["stallwache"] == {"tag": 5, "daemmerung": 0, "ir": 3})
p.check("3/9 IR erfuellt B9 (>= 1/3)", b["b9_erfuellt"] and abs(b["ir_anteil"] - 1 / 3) < 1e-9)
p.check("2/9 IR verfehlt B9", not ds.bilanz([("k", "ir")] * 2 + [("k", "tag")] * 7)["b9_erfuellt"])
p.check("leere Bilanz verfehlt B9", not ds.bilanz([])["b9_erfuellt"])

# --- Ausduennen ---------------------------------------------------------------

folge = [("a1", "stall", 0), ("a2", "stall", 2), ("a3", "stall", 9), ("b1", "futter", 1), ("a4", "stall", 10)]
behalten = ds.waehle_aus(folge, lambda x, y: abs(x - y), 6)
p.check("erstes Bild je Kamera bleibt", "a1" in behalten and "b1" in behalten)
p.check("fast identisches Bild faellt weg", "a2" not in behalten and "a4" not in behalten)
p.check("deutliche Aenderung bleibt", "a3" in behalten)
p.check("Kameras getrennt verglichen", behalten == ["a1", "a3", "b1"])

# befehl_ausduennen selbst, mit gestubbtem cv2 (Bildwert = Dateiinhalt)
import argparse
import tempfile


class Bild:
    def __init__(self, wert):
        self.wert = wert

    def astype(self, _):
        return self

    def __sub__(self, anderes):
        return Bild(self.wert - anderes.wert)

    def __abs__(self):
        return Bild(abs(self.wert))

    def mean(self):
        return self.wert


cv2 = sys.modules["cv2"]
cv2.IMREAD_GRAYSCALE, cv2.INTER_AREA = 0, 3
cv2.imread = lambda pfad, *_: Bild(float(Path(pfad).read_text()))
cv2.resize = lambda bild, *_a, **_k: bild

with tempfile.TemporaryDirectory() as tmp:
    quelle, ziel = Path(tmp) / "aufnahmen", Path(tmp) / "auswahl"
    for rel, wert in (("fehlalarme/2026-10-16/kalbeverdacht-0-0.jpg", "30"),
                      ("fehlalarme/2026-10-17/kalbeverdacht-0-0.jpg", "32"),
                      ("fehlalarme/2026-10-17/kalbeverdacht-0-1.jpg", "33"),
                      ("stallwache_20261014-230000.jpg", "110")):
        (quelle / rel).parent.mkdir(parents=True, exist_ok=True)
        (quelle / rel).write_text(wert)
    code = ds.befehl_ausduennen(argparse.Namespace(quelle=str(quelle), ziel=str(ziel), schwelle=6.0))
    kopiert = sorted(x.relative_to(ziel).as_posix() for x in ziel.rglob("*.jpg"))
    p.check("ausduennen: gleichnamige Bilder zweier Tage bleiben beide erhalten",
            code == 0 and "fehlalarme/2026-10-16/kalbeverdacht-0-0.jpg" in kopiert
            and "fehlalarme/2026-10-17/kalbeverdacht-0-0.jpg" in kopiert)
    def inhalt(rel):
        datei = ziel / rel
        return datei.read_text() if datei.exists() else None

    p.check("ausduennen: Inhalt bleibt dem Ursprung zugeordnet",
            inhalt("fehlalarme/2026-10-16/kalbeverdacht-0-0.jpg") == "30"
            and inhalt("fehlalarme/2026-10-17/kalbeverdacht-0-0.jpg") == "32")
    p.check("ausduennen: Vergleich je Ordner (fast gleiches Bild im selben Ordner faellt weg)",
            "fehlalarme/2026-10-17/kalbeverdacht-0-1.jpg" not in kopiert and len(kopiert) == 3)
    p.check("ausduennen: nicht leeres Ziel -> Exit 1",
            ds.befehl_ausduennen(argparse.Namespace(quelle=str(quelle), ziel=str(ziel), schwelle=6.0)) == 1)

q = Path("aufnahmen")
p.check("Vergleichsgruppe: Kamera aus dem Namen",
        ds.vergleichsgruppe(q, q / "stallwache_20261014-031500.jpg") == "stallwache")
p.check("Vergleichsgruppe: ohne Kamera der Unterordner",
        ds.vergleichsgruppe(q, q / "fehlalarme" / "2026-10-16" / "kalbeverdacht-0-0.jpg")
        == "ordner:fehlalarme/2026-10-16")
a = ds.zielpfad(q, q / "fehlalarme" / "2026-10-16" / "kalbeverdacht-0-0.jpg", Path("auswahl"))
b = ds.zielpfad(q, q / "fehlalarme" / "2026-10-17" / "kalbeverdacht-0-0.jpg", Path("auswahl"))
p.check("gleichnamige Bilder aus zwei Tagen -> zwei verschiedene Ziele", a != b
        and a == Path("auswahl/fehlalarme/2026-10-16/kalbeverdacht-0-0.jpg"))

# --- Split nach Stalltagen ----------------------------------------------------

def tage(n_tage, je_tag=10, geburt_an=None):
    bilder = []
    for t in range(n_tage):
        tag = f"202610{t + 1:02d}"
        for i in range(je_tag):
            bilder.append((f"{tag}-{i}.jpg", tag, tag == geburt_an and i == 0))
    return bilder


train, val, prot = ds.teile_nach_tagen(tage(10) + [("cvb_1.jpg", None, False)], 0.15)
tag_von = lambda n: n.split("-")[0]
p.check("kein Stalltag in train und val", not {tag_von(n) for n in train if "-" in n} & {tag_von(n) for n in val})
p.check("Val-Anteil >= 15 %", prot["bilder_val"] >= 15 and prot["val_anteil_datiert"] >= 0.15)
p.check("Val = juengste Tage", prot["val_tage"] == ["20261009", "20261010"])
p.check("undatiertes Bild (offener Datensatz) -> train", "cvb_1.jpg" in train and "cvb_1.jpg" not in val)
p.check("alle Bilder verteilt", len(train) + len(val) == 101)

_, _, prot = ds.teile_nach_tagen(tage(10, geburt_an="20261003") + tage(0), 0.15)
p.check("Geburtstag liegt in val", "20261003" in prot["val_tage"])
p.check("einziger Geburtstag in val -> Warnung", any("liegen in val" in w for w in prot["warnungen"]))

# Geburt ueber die 12-Uhr-Grenze: Fruchtblase am Stalltag 16, Fuesse am 17.
ueber_mittag = [(f"{tg}-{i}.jpg", tg, ({1} if tg == "20261006" and i == 0 else
                 {2} if tg == "20261007" and i == 0 else set()))
                for tg in (f"202610{d:02d}" for d in range(1, 11)) for i in range(10)]
_, val_ueber, prot = ds.teile_nach_tagen(ueber_mittag, 0.15)
p.check("Geburt ueber 12 Uhr: beide Klassen-Tage in val",
        {"20261006", "20261007"} <= set(prot["val_tage"]))
p.check("Protokoll fuehrt Geburtstage je Klasse",
        prot["geburtstage_je_klasse"] == {"amniotic_sac": ["20261006"], "calf_legs": ["20261007"]})
p.check("je Klasse ohne Train-Tag eine Warnung",
        sum("liegen in val" in w for w in prot["warnungen"]) == 2)
zwei_tage = [(f"{tg}-{i}.jpg", tg, ({1} if tg == "20261006" and i == 0 else
              {2} if tg == "20261007" and i == 0 else set()))
             for tg in ("20261006", "20261007") for i in range(40)]
try:
    _, _, prot = ds.teile_nach_tagen(zwei_tage, 0.15)
    p.check("Geburt ueber 12 Uhr mit nur zwei Stalltagen: Split bleibt moeglich",
            len(prot["train_tage"]) == 1 and len(prot["val_tage"]) == 1)
    p.check("... mit Warnung, dass eine Klasse keinen Val-Tag bekommt",
            any("kein eigener Val-Tag" in w for w in prot["warnungen"]))
except ValueError as fehler:
    p.check(f"Geburt ueber 12 Uhr mit nur zwei Stalltagen: Split bleibt moeglich ({fehler})", False)
p.check("Label-Klassen gelesen",
        ds.austreibungsklassen("0 .5 .5 .1 .1\n2 .4 .4 .1 .1\n1 .3 .3 .1 .1\n") == {1, 2}
        and ds.austreibungsklassen("0 .5 .5 .1 .1\n") == set())

_, _, prot = ds.teile_nach_tagen(
    [(n, t, a or t in ("20261002", "20261008")) for n, t, a in tage(10)], 0.15
)
p.check("bei zwei Geburtstagen: juengster in val, keine Warnung",
        "20261008" in prot["val_tage"] and "20261002" in prot["train_tage"] and not prot["warnungen"])

_, _, prot = ds.teile_nach_tagen(tage(10), 0.15, ["20261004", "20269999"])
p.check("erzwungener Val-Tag", "20261004" in prot["val_tage"])
p.check("unbekannter Val-Tag -> Warnung", any("20269999" in w for w in prot["warnungen"]))

def meldung(*args):
    try:
        ds.teile_nach_tagen(*args)
    except ValueError as fehler:
        return str(fehler)
    return ""


grosser_kleiner = [(f"a-{i}.jpg", "20261010", False) for i in range(100)] + \
                  [(f"b-{i}.jpg", "20261011", False) for i in range(5)]
p.check("Val-Anteil unerreichbar ohne --val-tag -> Rat: mehr Tage / Anteil senken",
        "mehr Stalltage" in meldung(grosser_kleiner, 0.15)
        and "--val-tag" not in meldung(grosser_kleiner, 0.15))
p.check("alle Tage per --val-tag erzwungen -> Rat nennt --val-tag",
        "--val-tag" in meldung(tage(2), 0.15, ["20261001", "20261002"]))

for fall, args in (
    ("ein Stalltag -> Fehler", (tage(1), 0.15)),
    ("alle Tage erzwungen -> Fehler", (tage(2), 0.15, ["20261001", "20261002"])),
    ("Val-Anteil 0 -> Fehler", (tage(5), 0.0)),
):
    try:
        ds.teile_nach_tagen(*args)
        p.check(fall, False)
    except ValueError:
        p.check(fall, True)

# --- Abnahme: Labels, Zuordnung, Gates ----------------------------------------

objekte = ab.lese_label("0 0.5 0.5 0.2 0.4 0.4 0.4 2 0.5 0.4 2 0.55 0.4 2\n1 0.1 0.1 0.1 0.1 0 0 0 0 0 0 0 0 0\n", 1000, 500)
p.check("Label: Box in Pixeln", objekte[0]["box"] == (400.0, 150.0, 600.0, 350.0))
p.check("Label: Keypoints in Pixeln mit Sichtbarkeit", objekte[0]["kp"][1] == (500.0, 200.0, 2.0))
p.check("Label: zweite Klasse gelesen", objekte[1]["klasse"] == 1)
p.check("IoU identisch = 1", ab.iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0)
p.check("IoU disjunkt = 0", ab.iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0)


def objekt(k, box, konf=1.0, kp=()):
    return {"klasse": k, "box": box, "konf": konf, "kp": list(kp)}


blase = (100, 100, 200, 200)
gt = [objekt(1, blase), objekt(2, (300, 300, 380, 380))]
r = ab.austreibungs_recall([(gt, [objekt(1, blase, 0.85), objekt(2, (300, 300, 380, 380), 0.79)])])
p.check("Fruchtblase ab 0.80 zaehlt", r[1] == {"gt": 1, "treffer": 1})
p.check("Kaelberfuesse mit 0.79 zaehlen nicht", r[2] == {"gt": 1, "treffer": 0})
p.check("doppelte Vorhersage zaehlt einmal",
        ab.austreibungs_recall([([objekt(1, blase)], [objekt(1, blase, 0.9), objekt(1, blase, 0.95)])])[1]["treffer"] == 1)

gt_w, pred_w = ab.winkel_des_agenten()
kuh_box = (100, 200, 500, 400)
label_kuh = objekt(0, kuh_box, kp=[(200, 300, 2), (400, 300, 2), (450, 330, 2)])
paare = ab.winkel_paare(
    [([label_kuh], [objekt(0, kuh_box, 0.9, [(200, 300, 0.9), (400, 300, 0.9), (450, 320, 0.9)])])],
    gt_w, pred_w,
)
p.check("Winkelpaar gebildet", len(paare) == 1 and paare[0][0] > paare[0][1] > 0)
p.check(
    "verdeckter Modell-Keypoint -> kein Paar",
    ab.winkel_paare([([label_kuh], [objekt(0, kuh_box, 0.9, [(200, 300, 0.9), (400, 300, 0.9), (0, 0, 0.1)])])],
                    gt_w, pred_w) == [],
)
p.check(
    "Label mit unsichtbarem Keypoint -> kein Paar",
    ab.winkel_paare([([objekt(0, kuh_box, kp=[(200, 300, 2), (400, 300, 2), (0, 0, 0)])],
                      [objekt(0, kuh_box, 0.9, [(200, 300, 0.9), (400, 300, 0.9), (450, 320, 0.9)])])],
                    gt_w, pred_w) == [],
)

# Gate 2b: erhobener Schwanz muss sichtbar bleiben
erhoben_label = objekt(0, kuh_box, kp=[(200, 300, 2), (400, 300, 2), (400, 200, 2)])  # 90°
sicht = ab.sichtbarkeit_erhoben([
    ([erhoben_label], [objekt(0, kuh_box, 0.9, [(200, 300, 0.9), (400, 300, 0.9), (405, 205, 0.9)])]),
    ([erhoben_label], [objekt(0, kuh_box, 0.9, [(200, 300, 0.9), (400, 300, 0.9), (0, 0, 0.2)])]),
    ([erhoben_label], []),
    ([label_kuh], [objekt(0, kuh_box, 0.9, [(200, 300, 0.9), (400, 300, 0.9), (0, 0, 0.2)])]),
], gt_w, pred_w)
p.check("2b: erhoben gesehen / verdeckt / Kuh verpasst; haengender Schwanz zaehlt nicht", sicht == (3, 1))

voll = {1: {"gt": 2, "treffer": 2}, 2: {"gt": 1, "treffer": 1}}
gute = [(30.0, 35.0)] * 30
gut_sicht = (10, 9)
e = ab.bewerte(voll, gute, gut_sicht)
p.check("alle Gates bestanden -> Exit 0",
        e["gate1"] == e["gate2"] == e["gate2b"] == "bestanden" and e["code"] == 0)
p.check("eine verpasste Fruchtblase -> verfehlt, Exit 1",
        ab.bewerte({1: {"gt": 2, "treffer": 1}, 2: {"gt": 0, "treffer": 0}}, gute, gut_sicht)["code"] == 1)
nur_fuesse = ab.bewerte({1: {"gt": 0, "treffer": 0}, 2: {"gt": 4, "treffer": 4}}, gute, gut_sicht)
p.check("Fruchtblase ohne Val-Beispiele -> nicht pruefbar statt bestanden, Exit 2",
        nur_fuesse["gate1"] == "nicht prüfbar" and nur_fuesse["code"] == 2
        and nur_fuesse["gate1_fehlend"] == ["amniotic_sac"])
text_fuesse = ab.bericht(nur_fuesse, "best_v1.pt", "datensatz")
p.check("Bericht nennt die fehlende Klasse und sperrt die Austreibung",
        "Keine Val-Beispiele für amniotic_sac" in text_fuesse and "NICHT scharfschalten" in text_fuesse)
p.check("2b: 8 von 10 erhobenen gesehen -> verfehlt, Exit 1",
        ab.bewerte(voll, gute, (10, 8))["gate2b"] == "verfehlt" and ab.bewerte(voll, gute, (10, 8))["code"] == 1)
p.check("2b: unter 10 Stichproben -> nicht pruefbar, Exit 2",
        ab.bewerte(voll, gute, (9, 9))["gate2b"] == "nicht prüfbar" and ab.bewerte(voll, gute, (9, 9))["code"] == 2)
e = ab.bewerte({1: {"gt": 0, "treffer": 0}, 2: {"gt": 0, "treffer": 0}}, gute, gut_sicht)
p.check("keine Geburt im Val-Set -> nicht pruefbar, Exit 2", e["gate1"] == "nicht prüfbar" and e["code"] == 2)
p.check("29 Stichproben -> Gate 2 verfehlt", ab.bewerte(voll, gute[:29])["gate2"] == "verfehlt")
p.check("Abweichung 10° -> Gate 2 verfehlt", ab.bewerte(voll, [(30.0, 40.0)] * 30)["gate2"] == "verfehlt")
p.check("keine Paare -> Gate 2 verfehlt", ab.bewerte(voll, [])["gate2"] == "verfehlt")
text = ab.bericht(ab.bewerte({1: {"gt": 0, "treffer": 0}, 2: {"gt": 0, "treffer": 0}}, gute), "runs/best_v1.pt", "datensatz")
p.check("Bericht nennt Modell und offene Hand-Gates", "best_v1.pt" in text and text.count("| offen |") == 2)
p.check("Bericht enthaelt Gate 2b und Hinweis bei zu wenig Material",
        "| 2b Sichtbarkeit |" in text and "erhobene Schwänze" in text)
p.check("Bericht warnt ohne Geburt im Val-Set", "NICHT scharfschalten" in text)

# --- Brunst-Phase (Modell nur mit Klasse kuh) ---------------------------------
m_quelle = (TRAINING.parent / "main.py").read_text(encoding="utf-8")

def kuh(box, konf=None):
    o = {"klasse": ab.KUH, "box": box, "kp": []}
    if konf is not None:
        o["konf"] = konf
    return o


oben, unten = (100, 100, 300, 260), (120, 160, 320, 320)   # IoU ~0,57: Aufsprung
p.check("Brunst: Testpaar ueberlappt wie ein Aufsprung", ab.iou(oben, unten) >= ab.AUFSPRUNG_IOU)
frei = (600, 100, 800, 260)
bilder_b = [
    # beide erkannt
    ([kuh(oben), kuh(unten), kuh(frei)], [kuh(oben, 0.9), kuh(unten, 0.8), kuh(frei, 0.9)]),
    # NMS hat die untere Kuh geschluckt
    ([kuh(oben), kuh(unten)], [kuh(oben, 0.9)]),
    # untere Kuh nur unsicher (unter 0,5 -> keine Spur im Tracker)
    ([kuh(oben), kuh(unten)], [kuh(oben, 0.9), kuh(unten, 0.45)]),
]
p.check("Brunst: Kuh-Recall zaehlt nur ab Konfidenz 0,5", ab.kuh_recall(bilder_b) == (7, 5))
p.check("Brunst: Ueberlappung zaehlt Paare, beide noetig", ab.ueberlapp_recall(bilder_b) == (3, 1))
p.check("Brunst: weit entfernte Kuh ist kein Paar",
        ab.ueberlapp_recall([([kuh(oben), kuh(frei)], [kuh(oben, 0.9), kuh(frei, 0.9)])]) == (0, 0))

e = ab.bewerte_brunst((100, 95), (10, 9))
p.check("Brunst: 95 % und 90 % -> bestanden, Exit 0",
        (e["gate_k"], e["gate_u"], e["code"]) == ("bestanden", "bestanden", 0))
e = ab.bewerte_brunst((100, 95), (10, 7))
p.check("Brunst: Ueberlappung 70 % -> verfehlt, Exit 1", (e["gate_u"], e["code"]) == ("verfehlt", 1))
e = ab.bewerte_brunst((100, 89), (10, 10))
p.check("Brunst: Kuh-Recall 89 % -> verfehlt", (e["gate_k"], e["code"]) == ("verfehlt", 1))
e = ab.bewerte_brunst((100, 95), (4, 4))
p.check("Brunst: < 5 ueberlappende Paare -> nicht pruefbar, Exit 2",
        (e["gate_u"], e["code"]) == ("nicht prüfbar", 2))
e = ab.bewerte_brunst((29, 29), (10, 10))
p.check("Brunst: < 30 Kuehe -> nicht pruefbar", (e["gate_k"], e["code"]) == ("nicht prüfbar", 2))
text_b = ab.bericht_brunst(ab.bewerte_brunst((100, 95), (4, 4)), "best_v1.pt", "datensatz")
p.check("Brunst-Bericht: Austreibung/Kalbeverdacht ausdruecklich NICHT scharf",
        "NICHT scharf" in text_b and "Austreibung" in text_b)
p.check("Brunst-Bericht: Hinweis auf fehlende Ueberlappungs-Bilder", "überlappende Kühe" in text_b)
p.check("Brunst-Schwelle = Agent: AUFSPRUNG_IOU wie LogicEngine._brunst (0.15)",
        ab.AUFSPRUNG_IOU == 0.15 and "self._iou(a.box, b.box) < 0.15" in m_quelle)

sys.exit(p.bericht())
