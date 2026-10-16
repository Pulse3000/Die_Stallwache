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
p.check("einziger Geburtstag in val -> Warnung", any("Geburtstag" in w for w in prot["warnungen"]))

_, _, prot = ds.teile_nach_tagen(
    [(n, t, a or t in ("20261002", "20261008")) for n, t, a in tage(10)], 0.15
)
p.check("bei zwei Geburtstagen: juengster in val, keine Warnung",
        "20261008" in prot["val_tage"] and "20261002" in prot["train_tage"] and not prot["warnungen"])

_, _, prot = ds.teile_nach_tagen(tage(10), 0.15, ["20261004", "20269999"])
p.check("erzwungener Val-Tag", "20261004" in prot["val_tage"])
p.check("unbekannter Val-Tag -> Warnung", any("20269999" in w for w in prot["warnungen"]))

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

sys.exit(p.bericht())
