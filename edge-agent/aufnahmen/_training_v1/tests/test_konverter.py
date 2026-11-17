# -*- coding: utf-8 -*-
"""Tests für werkzeuge/cvat_zu_yolo_pose.py — synthetische CVAT-Exporte, keine Stalldaten nötig."""
import csv
import os
import sys
import zipfile

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "werkzeuge"))
import cvat_zu_yolo_pose as k  # noqa: E402

W, H = 2560, 1440


# ----------------------------------------------------------------------------- Hilfen
def skelett(pts, gruppe=None, label="kuh_pose"):
    """pts: dict name -> (x, y) oder (x, y, 'outside'|'occluded')."""
    g = f' group_id="{gruppe}"' if gruppe else ""
    teile = [f'<skeleton label="{label}" source="manual" z_order="0"{g}>']
    for name in ("spine_end", "tail_base", "tail_tip"):
        p = pts[name]
        outside = "1" if len(p) > 2 and p[2] == "outside" else "0"
        occluded = "1" if len(p) > 2 and p[2] == "occluded" else "0"
        teile.append(f'<points label="{name}" source="manual" outside="{outside}" occluded="{occluded}" '
                     f'points="{p[0]:.2f},{p[1]:.2f}"></points>')
    teile.append("</skeleton>")
    return "".join(teile)


def box(x1, y1, x2, y2, label="kuh", gruppe=None, rotation=None, source="manual", outside=None):
    g = f' group_id="{gruppe}"' if gruppe else ""
    r = f' rotation="{rotation}"' if rotation is not None else ""
    o = f' outside="{outside}"' if outside is not None else ""
    return (f'<box label="{label}" source="{source}" occluded="0" xtl="{x1}" ytl="{y1}" xbr="{x2}" ybr="{y2}" '
            f'z_order="0"{g}{r}{o}></box>')


def cvat_xml(bilder, task_ids=None, quelle=None):
    """bilder: list of (name, [element-strings]); task_ids: optional Liste je Bild (Projekt-Export);
    quelle: Inhalt von <meta><source> (z. B. "stall_labeler v1")."""
    teile = ['<?xml version="1.0" encoding="utf-8"?>', "<annotations>", "<version>1.1</version>"]
    if quelle:
        teile.append(f"<meta><task><name>t</name></task><source>{quelle}</source></meta>")
    for i, (name, els) in enumerate(bilder):
        t = f' subset="default" task_id="{task_ids[i]}"' if task_ids else ""
        teile.append(f'<image id="{i}" name="{name}"{t} width="{W}" height="{H}">')
        teile += els
        teile.append("</image>")
    teile.append("</annotations>")
    return "\n".join(teile)


@pytest.fixture
def umgebung(tmp_path):
    bilder = tmp_path / "aufnahmen"
    bilder.mkdir()
    zeilen = []

    def bild(name, split="train", defekt=0.0, licht="Tag"):
        img = np.full((H, W, 3), 90, np.uint8)
        cv2.imwrite(str(bilder / name), img)
        zeilen.append({"datei": name, "split": split, "licht": licht, "lokalzeit": "", "helligkeit": "",
                       "schaerfe": "", "task": f"{split}_01", "defekt_anteil": defekt, "ansicht_grob": "A"})

    def schreibe_manifest():
        p = tmp_path / "manifest.csv"
        with open(p, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
            w.writeheader()
            w.writerows(zeilen)
        return str(p)

    def xml(name, inhalt):
        p = tmp_path / name
        p.write_text(inhalt, encoding="utf-8")
        return str(p)

    return {"tmp": tmp_path, "bilder": str(bilder), "bild": bild, "manifest": schreibe_manifest, "xml": xml}


def labels(ausgabe, split, name):
    return (ausgabe / "labels" / split / (name[:-4] + ".txt")).read_text().split("\n")


def zahlen(zeile):
    return [float(v) for v in zeile.split()]


# ----------------------------------------------------------------------------- Tests
def test_box_plus_skelett_wird_ein_yolo_objekt(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(1000, 400, 1800, 1000),
                                 skelett({"spine_end": (1100, 500), "tail_base": (1700, 520), "tail_tip": (1750, 900)})]),
        ("20261013-100000.jpg", [box(10, 10, 500, 400), skelett({"spine_end": (50, 50), "tail_base": (400, 60), "tail_tip": (450, 300)})]),
    ]))
    aus = u["tmp"] / "ds"
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=640)
    z = zahlen(labels(aus, "train", "20261012-100000.jpg")[0])
    assert z[0] == 0
    assert z[1:5] == pytest.approx([1400 / W, 700 / H, 800 / W, 600 / H], abs=1e-6)
    assert z[5:] == pytest.approx([1100 / W, 500 / H, 2, 1700 / W, 520 / H, 2, 1750 / W, 900 / H, 2], abs=1e-6)
    assert len(z) == 5 + 9
    assert b["splits"]["train"]["kuh_mit_skelett"] == 1
    # Bild wurde verkleinert (längste Seite 640), Seitenverhältnis bleibt
    img = cv2.imread(str(aus / "images" / "train" / "20261012-100000.jpg"))
    assert img.shape[:2] == (360, 640)
    yaml_text = (aus / "data.yaml").read_text()
    assert "kpt_shape: [3, 3]" in yaml_text and "flip_idx: [0, 1, 2]" in yaml_text
    assert "0: kuh" in yaml_text and "1: amniotic_sac" in yaml_text and "2: calf_legs" in yaml_text
    assert "\npath:" not in yaml_text


def test_sichtbarkeit_outside_und_occluded(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(1000, 400, 1800, 1000),
                                 skelett({"spine_end": (1100, 500), "tail_base": (1700, 520, "occluded"),
                                          "tail_tip": (1750, 900, "outside")})]),
        ("20261013-100000.jpg", []),
    ]))
    aus = u["tmp"] / "ds"
    k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=0)
    z = zahlen(labels(aus, "train", "20261012-100000.jpg")[0])
    assert z[7] == 2 and z[10] == 1           # spine_end sichtbar, tail_base verdeckt
    assert z[11:14] == [0.0, 0.0, 0.0]         # tail_tip outside -> 0 0 0
    # leeres Bild -> leere Label-Datei (Negativbeispiel)
    assert (aus / "labels" / "val" / "20261013-100000.txt").read_text() == ""


def test_gruppe_schlaegt_geometrie(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    # Skelett liegt geometrisch in Box A, ist aber per Gruppe mit Box B verbunden
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(0, 0, 1000, 1000, gruppe="7"), box(1200, 0, 2400, 1000, gruppe="3"),
                                 skelett({"spine_end": (100, 100), "tail_base": (500, 120), "tail_tip": (600, 600)}, gruppe="3")]),
        ("20261013-100000.jpg", []),
    ]))
    aus = u["tmp"] / "ds"
    k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=0)
    zs = [zahlen(z) for z in labels(aus, "train", "20261012-100000.jpg") if z]
    box_b = [z for z in zs if z[1] > 0.5][0]
    box_a = [z for z in zs if z[1] < 0.5][0]
    assert box_b[7] == 2 and box_a[5:] == [0.0] * 9


def test_ueberlappende_kuehe_werden_richtig_gepaart(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    # zwei überlappende Boxen; jedes Skelett liegt tief in "seiner" Box
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [
            box(100, 100, 1100, 900), box(800, 300, 1900, 1100),
            skelett({"spine_end": (300, 300), "tail_base": (700, 350), "tail_tip": (750, 700)}),
            skelett({"spine_end": (1300, 500), "tail_base": (1700, 550), "tail_tip": (1750, 950)})]),
        ("20261013-100000.jpg", []),
    ]))
    aus = u["tmp"] / "ds"
    k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=0)
    zs = [zahlen(z) for z in labels(aus, "train", "20261012-100000.jpg") if z]
    links = [z for z in zs if z[1] < 0.3][0]
    rechts = [z for z in zs if z[1] > 0.4][0]
    assert links[5] == pytest.approx(300 / W, abs=1e-6)
    assert rechts[5] == pytest.approx(1300 / W, abs=1e-6)


def test_mehrdeutige_paarung_ist_fehler():
    boxen = [{"xyxy": (0, 0, 1000, 1000), "gruppe": None}, {"xyxy": (0, 0, 1000, 1000), "gruppe": None}]
    sk = [{"pts": [(500, 500, 2), (600, 600, 2), (700, 700, 2)], "gruppe": None}]
    zuordnung, mehrdeutig, ohne, knapp = k.paare_box_skelett(boxen, sk)
    assert mehrdeutig == [0] and ohne == [] and knapp == []


def test_skelett_ohne_box_bricht_ab(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(0, 0, 300, 300),
                                 skelett({"spine_end": (1500, 500), "tail_base": (1700, 520), "tail_tip": (1750, 900)})]),
        ("20261013-100000.jpg", []),
    ]))
    with pytest.raises(k.KonverterFehler, match="ohne passende Kuh-Box"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)
    # mit --erzwingen läuft es durch, Fehler stehen im Bericht
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds2"), max_seite=0, erzwingen=True)
    assert b["fehler_anzahl"] == 1 and b["parameter"]["erzwungen"]


def test_nur_vorannotation_ohne_skelette_bricht_ab(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(0, 0, 300, 300)]),
        ("20261013-100000.jpg", [box(0, 0, 300, 300)]),
    ]))
    with pytest.raises(k.KonverterFehler, match="kein Skelett"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)


def test_gedrehte_box_wird_achsenparallel():
    import xml.etree.ElementTree as ET
    el = ET.fromstring(box(0, 0, 200, 100, rotation=90))
    x1, y1, x2, y2 = k.box_achsenparallel(el)
    assert (x1, y1, x2, y2) == pytest.approx((50, -50, 150, 150), abs=1e-6)


def test_punkt_ausserhalb_bild_wird_unsichtbar_und_box_geclippt(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(2000, 1000, 2700, 1500),
                                 skelett({"spine_end": (2100, 1100), "tail_base": (2500, 1200), "tail_tip": (2550, 1460)})]),
        ("20261013-100000.jpg", []),
    ]))
    aus = u["tmp"] / "ds"
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=0)
    z = zahlen(labels(aus, "train", "20261012-100000.jpg")[0])
    assert all(0 <= v <= 1 for v in z[1:5])
    assert z[1] + z[3] / 2 == pytest.approx(1.0, abs=1e-6)     # Box an rechter Kante geclippt
    assert z[11:14] == [0.0, 0.0, 0.0]                          # tail_tip außerhalb -> v=0
    assert b["warnungen"]["punkt_ausserhalb_bild"]["anzahl"] == 1


def test_austreibungsklassen_ohne_keypoints(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(100, 100, 300, 300, label="amniotic_sac"), box(400, 400, 500, 600, label="calf_legs"),
                                 box(0, 0, 1000, 1000), skelett({"spine_end": (100, 100), "tail_base": (500, 120), "tail_tip": (600, 600)})]),
        ("20261013-100000.jpg", []),
    ]))
    aus = u["tmp"] / "ds"
    k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=0)
    zs = [zahlen(z) for z in labels(aus, "train", "20261012-100000.jpg") if z]
    klassen = sorted(int(z[0]) for z in zs)
    assert klassen == [0, 1, 2]
    for z in zs:
        if z[0] in (1, 2):
            assert z[5:] == [0.0] * 9


def test_split_nur_aus_manifest_mit_puffer_und_defekt(umgebung):
    u = umgebung
    u["bild"]("20261012-090000.jpg", "train")
    u["bild"]("20261012-233000.jpg", "train")          # 30 min vor Val-Tag -> Puffer
    u["bild"]("20261013-000500.jpg", "val")
    u["bild"]("20261013-120000.jpg", "val", defekt=0.2)  # defekt -> nie übernommen
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-090000.jpg", []), ("20261012-233000.jpg", []), ("20261013-000500.jpg", []),
        ("20261013-120000.jpg", []), ("20261020-100000.jpg", []),   # nicht im Manifest
    ]))
    aus = u["tmp"] / "ds"
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=0, puffer_min=60)
    assert sorted(os.listdir(aus / "labels" / "train")) == ["20261012-090000.txt"]
    assert sorted(os.listdir(aus / "labels" / "val")) == ["20261013-000500.txt"]
    assert b["uebersprungen"] == {"puffer_zu_val": 1, "defekt": 1, "nicht_im_manifest": 1}


def test_unbekannter_keypoint_bricht_ab(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    falsch = cvat_xml([("20261012-100000.jpg", [box(0, 0, 900, 900),
                                                skelett({"spine_end": (10, 10), "tail_base": (20, 20), "tail_tip": (30, 30)})]),
                       ("20261013-100000.jpg", [])]).replace('label="tail_tip"', 'label="schwanz"')
    x = u["xml"]("a.xml", falsch)
    with pytest.raises(k.KonverterFehler, match="unbekannter Keypoint"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)


def test_doppelter_export_und_nicht_leerer_zielordner(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    inhalt = cvat_xml([("20261012-100000.jpg", []), ("20261013-100000.jpg", [])])
    a, b = u["xml"]("a.xml", inhalt), u["xml"]("b.xml", inhalt)
    with pytest.raises(k.KonverterFehler, match="doppelt"):
        k.konvertiere([a, b], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)
    voll = u["tmp"] / "voll"
    voll.mkdir()
    (voll / "alt.txt").write_text("x")
    with pytest.raises(k.KonverterFehler, match="nicht leer"):
        k.konvertiere([a], u["bilder"], u["manifest"](), str(voll), max_seite=0)


def test_export_zip_und_datensatz_zip(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    xml_text = cvat_xml([("20261012-100000.jpg", [box(0, 0, 900, 900),
                                                  skelett({"spine_end": (10, 10), "tail_base": (300, 20), "tail_tip": (330, 300)})]),
                         ("20261013-100000.jpg", [])])
    exp = u["tmp"] / "task_export.zip"
    with zipfile.ZipFile(exp, "w") as zf:
        zf.writestr("annotations.xml", xml_text)
    aus = u["tmp"] / "datensatz_test"
    beilage = u["tmp"] / "abnahme_gates.py"
    beilage.write_text("# test")
    b = k.konvertiere([str(exp)], u["bilder"], u["manifest"](), str(aus), max_seite=0, zip_erstellen=True,
                      beilagen=[str(beilage)])
    assert b["stalltage"] == {"train": ["2026-10-12"], "val": ["2026-10-13"]}
    with zipfile.ZipFile(b["zip"]) as zf:
        namen = zf.namelist()
    assert "datensatz_test/data.yaml" in namen
    assert "datensatz_test/labels/train/20261012-100000.txt" in namen
    assert "datensatz_test/werkzeuge/abnahme_gates.py" in namen
    assert "datensatz_test/konvertierung_bericht.md" in namen


def test_verkleinern_mit_halber_dekodierung(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([("20261012-100000.jpg", []), ("20261013-100000.jpg", [])]))
    aus = u["tmp"] / "ds"
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=1280)
    assert cv2.imread(str(aus / "images" / "train" / "20261012-100000.jpg")).shape[:2] == (720, 1280)
    assert "- keine" in k.bericht_md(b)          # Abschnitt "Übersprungen" ohne Einträge


def test_cli_exitcode(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([("20261012-100000.jpg", [box(0, 0, 300, 300)]), ("20261013-100000.jpg", [])]))
    m = u["manifest"]()
    assert k.main(["--xml", x, "--bilder", u["bilder"], "--manifest", m, "--ausgabe", str(u["tmp"] / "ds")]) == 2


# ----------------------------------------------------------------------------- QA-Befunde (H1, H2, M2, N3, N5)
def test_verschachtelte_boxen_verlangen_gruppierung():
    # QA-Fall H1: vordere Kuh A (groß) umschließt die Box der hinteren Kuh B
    a = {"xyxy": (0, 0, 2000, 1400), "gruppe": None}
    b = {"xyxy": (800, 300, 1300, 700), "gruppe": None}
    sk_b = {"pts": [(830, 330, 2), (1250, 350, 2), (1280, 680, 2)], "gruppe": None}
    sk_a = {"pts": [(100, 200, 2), (1800, 250, 2), (1900, 1200, 2)], "gruppe": None}
    # ungruppiert: Skelett B liegt streng in A und B -> nicht entscheidbar -> Fehler (kein stilles Raten)
    _, mehrdeutig, ohne, _ = k.paare_box_skelett([a, b], [sk_b])
    assert mehrdeutig == [0] and ohne == []
    _, mehrdeutig, ohne, _ = k.paare_box_skelett([a, b], [sk_a, sk_b])
    assert mehrdeutig == [1] and ohne == []
    # gruppiert (README-Regel): eindeutig und richtig
    a_g, b_g = dict(a, gruppe="1"), dict(b, gruppe="2")
    zuordnung, mehrdeutig, ohne, _ = k.paare_box_skelett([a_g, b_g], [dict(sk_a, gruppe="1"), dict(sk_b, gruppe="2")])
    assert zuordnung == {0: 0, 1: 1} and mehrdeutig == [] and ohne == []
    # nur B gruppiert: A ist dann die einzige freie Box für Skelett A
    zuordnung, mehrdeutig, ohne, _ = k.paare_box_skelett([a, b_g], [sk_a, dict(sk_b, gruppe="2")])
    assert zuordnung == {1: 1, 0: 0} and mehrdeutig == []


def test_kompaktes_skelett_bleibt_in_eigener_weiter_box():
    # QA-Gegenfall: Kuh von hinten, nur tail_base + tail_tip sichtbar; eigene Box R weit, fremde Box F eng
    r = {"xyxy": (800, 200, 1300, 1100), "gruppe": None}
    f = {"xyxy": (900, 250, 1500, 700), "gruppe": None}
    # Punkte streng in R, in F nur über den Toleranzrand -> R muss gewinnen
    sk = {"pts": [(0, 0, 0), (850, 600, 2), (880, 1000, 2)], "gruppe": None}
    zuordnung, mehrdeutig, ohne, _ = k.paare_box_skelett([r, f], [sk])
    assert zuordnung == {0: 0} and mehrdeutig == [] and ohne == []
    # Punkte streng in R UND F -> geometrisch nicht entscheidbar -> Fehler statt falscher Zuordnung
    sk2 = {"pts": [(0, 0, 0), (1000, 400, 2), (1050, 650, 2)], "gruppe": None}
    _, mehrdeutig, _, _ = k.paare_box_skelett([r, f], [sk2])
    assert mehrdeutig == [0]


def test_schwanzspitze_knapp_ausserhalb_eigener_box_ist_mehrdeutig():
    # QA Runde 3: tail_tip der hinteren Kuh 20 px außerhalb ihrer Box (im 10-%-Rand), vordere Kuh ohne Skelett
    a = {"xyxy": (0, 0, 2000, 1400), "gruppe": None}
    b = {"xyxy": (800, 300, 1300, 700), "gruppe": None}
    sk_b = {"pts": [(830, 330, 2), (1250, 350, 2), (1280, 720, 2)], "gruppe": None}
    _, mehrdeutig, ohne, _ = k.paare_box_skelett([a, b], [sk_b])
    assert mehrdeutig == [0] and ohne == []
    # mit Gruppe eindeutig
    zuordnung, mehrdeutig, _, _ = k.paare_box_skelett([a, dict(b, gruppe="5")], [dict(sk_b, gruppe="5")])
    assert zuordnung == {0: 1} and mehrdeutig == []


def test_mehrdeutig_bricht_konvertierung_ab(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(0, 0, 2000, 1400), box(800, 300, 1300, 700),
                                 skelett({"spine_end": (830, 330), "tail_base": (1250, 350), "tail_tip": (1280, 680)})]),
        ("20261013-100000.jpg", []),
    ]))
    with pytest.raises(k.KonverterFehler, match="gruppieren"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)


def test_ungarisch_optimal_statt_gierig():
    # Gierig würde Zeile 0 die billigste Spalte 0 geben (Summe 1+10); optimal ist 2+2
    assert k.ungarisch([[1, 2], [2, 10]]) == [1, 0]


@pytest.mark.parametrize("name, erwartet", [
    ("20261013-210000.jpg", "2026-10-13"),            # 23:00 Ortszeit -> Stalltag 13.
    ("20261014-030000.jpg", "2026-10-13"),            # 05:00 Ortszeit am 14. gehört noch zur Nacht des 13.
    ("20261014-103000.jpg", "2026-10-14"),            # 12:30 Ortszeit -> neuer Stalltag
    ("20261025-013000.jpg", "2026-10-24"),            # Zeitumstellung: 02:30 MEZ am 25. -> Nacht des 24.
    ("20261026-110500.jpg", "2026-10-26"),            # MEZ: 12:05 Ortszeit
    ("stallwache_20261013-210000.jpg", "2026-10-13"), # Kamera-Präfix
    ("ohne_datum.jpg", None),
])
def test_stalltag(name, erwartet):
    assert k.stalltag(name) == erwartet


def test_leck_nach_stalltag_wird_erkannt(umgebung):
    u = umgebung
    u["bild"]("20261013-210000.jpg", "train")          # Stalltag 13 (Nacht)
    u["bild"]("20261013-100000.jpg", "val")            # Stalltag 13 (Mittag) — 11 h entfernt, Puffer greift nicht
    u["bild"]("20261015-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([(n, []) for n in ("20261013-210000.jpg", "20261013-100000.jpg", "20261015-100000.jpg")]))
    with pytest.raises(k.KonverterFehler, match="Stalltage in train und val"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)


def test_projekt_export_prueft_jede_aufgabe(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("projekt.xml", cvat_xml([
        ("20261012-100000.jpg", [box(0, 0, 900, 900), skelett({"spine_end": (10, 10), "tail_base": (300, 20), "tail_tip": (330, 300)})]),
        ("20261013-100000.jpg", [box(0, 0, 900, 900, source="auto")]),   # Aufgabe 2 nur vorannotiert
    ], task_ids=[1, 2]))
    with pytest.raises(k.KonverterFehler, match="task2"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)


def test_unbestaetigte_vorschlaege_werden_gezaehlt(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(0, 0, 900, 900), skelett({"spine_end": (10, 10), "tail_base": (300, 20), "tail_tip": (330, 300)}),
                                 box(1500, 100, 2400, 900, source="auto")]),
        ("20261013-100000.jpg", []),
    ]))
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)
    assert b["splits"]["train"]["unbestaetigter_vorschlag"] == 1
    assert b["warnungen"]["vorschlag_ohne_skelett"]["anzahl"] == 1


def test_fehlendes_quellbild_bricht_vor_dem_schreiben_ab(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    m = u["manifest"]()
    os.remove(os.path.join(u["bilder"], "20261013-100000.jpg"))
    x = u["xml"]("a.xml", cvat_xml([("20261012-100000.jpg", []), ("20261013-100000.jpg", [])]))
    aus = u["tmp"] / "ds"
    with pytest.raises(k.KonverterFehler, match="Quellbilder fehlen"):
        k.konvertiere([x], u["bilder"], m, str(aus), max_seite=0)
    assert not aus.exists()


def test_vorhandenes_zip_wird_nicht_ueberschrieben(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([("20261012-100000.jpg", []), ("20261013-100000.jpg", [])]))
    (u["tmp"] / "ds.zip").write_text("alt")
    with pytest.raises(k.KonverterFehler, match="existiert schon"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0, zip_erstellen=True)


def test_standard_beilagen_und_track_outside(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("a.xml", cvat_xml([
        ("20261012-100000.jpg", [box(0, 0, 900, 900, outside="1")]),   # Track-Objekt nicht im Bild
        ("20261013-100000.jpg", []),
    ]))
    aus = u["tmp"] / "ds"
    k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=0)
    assert (aus / "labels" / "train" / "20261012-100000.txt").read_text() == ""
    assert sorted(os.listdir(aus / "werkzeuge")) == ["abnahme_gates.py", "bildqualitaet.py"]


# ----------------------------------------------------------------------------- Geprüft-Markierung (Stall-Labeler, B18)
def test_nur_gepruefte_bilder_wenn_aufgabe_markiert(umgebung):
    u = umgebung
    for n, sp in (("20261012-100000.jpg", "train"), ("20261012-120000.jpg", "train"), ("20261013-100000.jpg", "val")):
        u["bild"](n, sp)
    kuh = [box(0, 0, 900, 900, gruppe="1"),
           skelett({"spine_end": (10, 10), "tail_base": (300, 20), "tail_tip": (330, 300)}, gruppe="1")]
    tag = '<tag label="geprueft" source="manual"></tag>'
    x = u["xml"]("labeler.xml", cvat_xml([
        ("20261012-100000.jpg", [tag] + kuh),
        ("20261012-120000.jpg", [box(1000, 100, 1400, 500, source="auto")]),   # ungeprüft: Vorschlag bleibt draußen
        ("20261013-100000.jpg", [tag]),                                        # geprüft und leer: Negativbeispiel
    ]))
    aus = u["tmp"] / "ds"
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(aus), max_seite=0)
    assert b["uebersprungen"] == {"ungeprueft": 1}
    assert sorted(os.listdir(aus / "labels" / "train")) == ["20261012-100000.txt"]
    assert (aus / "labels" / "val" / "20261013-100000.txt").read_text() == ""
    assert b["aufgaben_mit_geprueft_markierung"] == ["labeler.xml"]


def test_ohne_markierung_zaehlen_alle_bilder_wie_bisher(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("cvat.xml", cvat_xml([("20261012-100000.jpg", []), ("20261013-100000.jpg", [])]))
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)
    assert b["uebersprungen"] == {} and b["splits"]["train"]["bilder"] == 1


def test_nur_vorannotation_in_geprueften_bildern_bricht_ab(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    tag = '<tag label="geprueft" source="manual"></tag>'
    x = u["xml"]("a.xml", cvat_xml([("20261012-100000.jpg", [tag, box(0, 0, 900, 900)]), ("20261013-100000.jpg", [tag])]))
    with pytest.raises(k.KonverterFehler, match="kein Skelett"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)


def test_labeler_export_ohne_gepruefte_bilder_ist_fehler(umgebung):
    # QA Runde 5: mit Pfeiltasten durchgeblättert, nie Enter -> darf nicht als "alles geprüft" durchgehen
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    x = u["xml"]("train_01_labels.xml", cvat_xml([("20261012-100000.jpg", [box(0, 0, 900, 900, source="auto")]),
                                                  ("20261013-100000.jpg", [])], quelle="stall_labeler v1"))
    with pytest.raises(k.KonverterFehler, match="ohne ein einziges geprüftes Bild"):
        k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)


def test_labeler_export_nimmt_nur_gepruefte_bilder(umgebung):
    u = umgebung
    for n, sp in (("20261012-100000.jpg", "train"), ("20261012-120000.jpg", "train"), ("20261013-100000.jpg", "val")):
        u["bild"](n, sp)
    tag = '<tag label="geprueft" source="manual"></tag>'
    x = u["xml"]("l.xml", cvat_xml([("20261012-100000.jpg", [tag]), ("20261012-120000.jpg", []), ("20261013-100000.jpg", [tag])],
                                   quelle="stall_labeler v1"))
    b = k.konvertiere([x], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)
    assert b["uebersprungen"] == {"ungeprueft": 1} and b["splits"]["train"]["bilder"] == 1


def test_doppelter_export_nennt_abhilfe(umgebung):
    u = umgebung
    u["bild"]("20261012-100000.jpg", "train")
    u["bild"]("20261013-100000.jpg", "val")
    inhalt = cvat_xml([("20261012-100000.jpg", []), ("20261013-100000.jpg", [])])
    a, b = u["xml"]("alt.xml", inhalt), u["xml"]("neu.xml", inhalt)
    with pytest.raises(k.KonverterFehler, match="neuesten Export"):
        k.konvertiere([a, b], u["bilder"], u["manifest"](), str(u["tmp"] / "ds"), max_seite=0)
