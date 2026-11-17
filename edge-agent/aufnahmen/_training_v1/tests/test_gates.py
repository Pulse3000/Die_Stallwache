# -*- coding: utf-8 -*-
"""Tests für werkzeuge/abnahme_gates.py (reine Logik, ohne Modell)."""
import json
import math
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "werkzeuge"))
import abnahme_gates as g  # noqa: E402


# ----------------------------------------------------------------------------- Schwanzwinkel
@pytest.mark.parametrize("se, tb, tt, erwartet", [
    ((0, 0), (10, 0), (20, 0), 0.0),        # Schwanz verlängert die Rückenlinie
    ((0, 0), (10, 0), (10, 10), 90.0),      # rechter Winkel
    ((0, 0), (10, 0), (10, -10), 90.0),     # Vorzeichen egal (Betrag)
    ((0, 0), (10, 0), (0, 0), 180.0),       # Schwanz zurückgeklappt
    ((0, 0), (10, 0), (20, 10), 45.0),      # Schwellenwert-Fall
])
def test_schwanzwinkel(se, tb, tt, erwartet):
    assert g.schwanzwinkel(se, tb, tt) == pytest.approx(erwartet, abs=1e-9)


def test_schwanzwinkel_entartet_ist_nan():
    assert math.isnan(g.schwanzwinkel((5, 5), (5, 5), (9, 9)))


def test_winkel_in_pixeln_nicht_normiert():
    # 45° in Pixeln auf einem 16:9-Bild sind in normierten Koordinaten NICHT 45° — Gate rechnet in Pixeln
    w, h = 1600, 900
    se, tb, tt = (0, 0), (100, 0), (200, 100)
    assert g.schwanzwinkel(se, tb, tt) == pytest.approx(45.0)
    norm = [(x / w, y / h) for x, y in (se, tb, tt)]
    assert abs(g.schwanzwinkel(*norm) - 45.0) > 5


# ----------------------------------------------------------------------------- Gate A / A2
def _gt(objekte_je_bild, w=1280, h=720):
    return {k: {"bild": "", "w": w, "h": h, "objekte": v} for k, v in objekte_je_bild.items()}


def _sack(conf=0.9, cls=1):
    return {"cls": cls, "conf": conf, "xyxy": (0.4, 0.4, 0.5, 0.5), "kpts": [(0, 0, 0)] * 3}


def test_gate_a_offen_ohne_geburt():
    gt = _gt({"a": [], "b": [{"cls": 0, "xyxy": (0, 0, 1, 1), "kpts": []}]})
    a, a2 = g.gate_austreibung(gt, {"a": [], "b": []})
    assert a["status"] == "OFFEN" and a2["status"] == "BESTANDEN"


def test_gate_a_recall_muss_eins_sein():
    gt = _gt({"g1": [{"cls": 1, "xyxy": (0.4, 0.4, 0.5, 0.5), "kpts": []}],
              "g2": [{"cls": 2, "xyxy": (0.4, 0.4, 0.5, 0.5), "kpts": []}]})
    a, _ = g.gate_austreibung(gt, {"g1": [_sack(0.95)], "g2": [_sack(0.85, cls=2)]})
    assert a["status"] == "BESTANDEN"
    a, _ = g.gate_austreibung(gt, {"g1": [_sack(0.95)], "g2": [_sack(0.80, cls=2)]})   # 0.80 ist NICHT > 0.80
    assert a["status"] == "NICHT BESTANDEN" and a["verpasst"] == ["g2"]


def test_gate_a2_zaehlt_fehlalarme():
    gt = _gt({"leer": [], "kuh": [{"cls": 0, "xyxy": (0, 0, 1, 1), "kpts": []}]})
    _, a2 = g.gate_austreibung(gt, {"leer": [_sack(0.81)], "kuh": [_sack(0.5)]})
    assert a2["status"] == "NICHT BESTANDEN" and a2["beispiele"] == ["leer"]


# ----------------------------------------------------------------------------- Gate B
def _kuh(kpts_px, w=1280, h=720, box=(0.1, 0.1, 0.9, 0.9), conf=0.9):
    return {"cls": 0, "conf": conf, "xyxy": box, "kpts": [(x / w, y / h, 2) for x, y in kpts_px]}


def test_gate_b_bestanden_und_offen():
    gt, vh = {}, {}
    for i in range(30):
        name = f"b{i}"
        gt[name] = {"bild": "", "w": 1280, "h": 720, "objekte": [_kuh([(100, 100), (300, 100), (400, 200)])]}
        vh[name] = [_kuh([(100, 100), (300, 100), (400, 205)])]        # leicht abweichend
    b = g.gate_schwanzwinkel(gt, vh)
    assert b["status"] == "BESTANDEN" and "n=30" in b["messwert"]
    b = g.gate_schwanzwinkel({k: gt[k] for k in list(gt)[:29]}, vh)
    assert b["status"] == "OFFEN"


def test_gate_b_nicht_bestanden_bei_grosser_abweichung():
    gt, vh = {}, {}
    for i in range(30):
        gt[f"b{i}"] = {"bild": "", "w": 1280, "h": 720, "objekte": [_kuh([(100, 100), (300, 100), (500, 100)])]}   # 0°
        vh[f"b{i}"] = [_kuh([(100, 100), (300, 100), (300, 300)])]                                                # 90°
    b = g.gate_schwanzwinkel(gt, vh)
    assert b["status"] == "NICHT BESTANDEN"


def test_gate_b_ignoriert_unvollstaendige_und_schlecht_passende():
    gt = {"x": {"bild": "", "w": 1280, "h": 720, "objekte": [
        {"cls": 0, "xyxy": (0.1, 0.1, 0.5, 0.5), "kpts": [(0.1, 0.1, 2), (0.2, 0.1, 2), (0, 0, 0)]},   # tail_tip fehlt
        _kuh([(100, 100), (300, 100), (400, 200)], box=(0.0, 0.0, 0.2, 0.2))]}}
    vh = {"x": [_kuh([(100, 100), (300, 100), (400, 200)], box=(0.6, 0.6, 0.9, 0.9))]}   # IoU 0 -> keine Zuordnung
    b = g.gate_schwanzwinkel(gt, vh, min_n=1)
    assert b["status"] == "OFFEN" and b["nicht_gefunden"] == 1


def test_gate_b_rechnet_wie_der_agent_nur_sichtbare_punkte():
    gt, vh = {}, {}
    for i in range(30):
        gt[f"b{i}"] = {"bild": "", "w": 1280, "h": 720, "objekte": [_kuh([(100, 100), (300, 100), (400, 200)])]}
        p = _kuh([(100, 100), (300, 100), (300, 300)])                       # 90° statt 45°: grob falsch ...
        p["kpts"][2] = (p["kpts"][2][0], p["kpts"][2][1], 0.3)               # ... aber Spitze unsichtbar
        vh[f"b{i}"] = [p] if i % 2 else [_kuh([(100, 100), (300, 100), (400, 205)])]
    b = g.gate_schwanzwinkel(gt, vh, min_n=10)
    assert b["status"] == "BESTANDEN" and "n=15" in b["messwert"]          # unsichtbare zählen nicht
    assert b["messbar"] == {"flach": [15, 30], "hoch": [0, 0]}


def _paare(n, winkel_hoch, sichtbar):
    """n Kühe mit Hand-Winkel 0° (flach) bzw. 90° (hoch); die ersten `sichtbar` Vorhersagen sind messbar."""
    gt, vh = {}, {}
    for i in range(n):
        spitze = (300, 300) if winkel_hoch else (500, 100)
        gt[f"m{i}"] = {"bild": "", "w": 1280, "h": 720, "objekte": [_kuh([(100, 100), (300, 100), spitze])]}
        p = _kuh([(100, 100), (300, 100), spitze])
        if i >= sichtbar:
            p["kpts"][2] = (p["kpts"][2][0], p["kpts"][2][1], 0.2)
        vh[f"m{i}"] = [p]
    return gt, vh


def test_gate_b2_messbarkeit_bei_erhobenem_schwanz():
    def b2(flach_sichtbar, hoch_n, hoch_sichtbar):
        gt, vh = _paare(30, False, flach_sichtbar)
        gt2, vh2 = _paare(hoch_n, True, hoch_sichtbar)
        gt.update({k + "h": v for k, v in gt2.items()})
        vh.update({k + "h": v for k, v in vh2.items()})
        return g.gate_messbarkeit(g.gate_schwanzwinkel(gt, vh, min_n=1)["messbar"])
    assert g.MESSBAR_MIN_N == g.WINKEL_MIN_N == 30                # eine Kuh darf das Gate nicht kippen
    assert b2(30, 30, 15)["status"] == "NICHT BESTANDEN"         # 100 % vs. 50 %: Kalbe-Signal fiele heraus
    assert b2(30, 30, 28)["status"] == "BESTANDEN"               # Lücke 7 Prozentpunkte
    assert b2(30, 29, 29)["status"] == "OFFEN"                   # zu wenige erhobene Schwänze im Val-Set


# ----------------------------------------------------------------------------- Dateien / Berichte
@pytest.fixture
def mini_datensatz(tmp_path):
    ds = tmp_path / "ds"
    for s in ("train", "val"):
        (ds / "images" / s).mkdir(parents=True)
        (ds / "labels" / s).mkdir(parents=True)
    cv2.imwrite(str(ds / "images" / "val" / "a.jpg"), np.zeros((720, 1280, 3), np.uint8))
    (ds / "labels" / "val" / "a.txt").write_text("0 0.5 0.5 0.4 0.4 0.4 0.4 2 0.5 0.4 2 0.55 0.5 1\n1 0.2 0.2 0.1 0.1 0 0 0 0 0 0 0 0 0\n")
    cv2.imwrite(str(ds / "images" / "val" / "b.jpg"), np.zeros((720, 1280, 3), np.uint8))
    (ds / "data.yaml").write_text("# Kommentar\ntrain: images/train\nval: images/val\nkpt_shape: [3, 3]\nflip_idx: [0, 1, 2]\n"
                                  "names:\n  0: kuh\n  1: amniotic_sac\n  2: calf_legs\n")
    return ds


def test_yaml_und_gt_lesen(mini_datensatz):
    cfg = g.lies_yaml_einfach(str(mini_datensatz / "data.yaml"))
    assert cfg["kpt_shape"] == [3, 3] and cfg["names"] == {0: "kuh", 1: "amniotic_sac", 2: "calf_legs"}
    gt = g.lade_gt(str(mini_datensatz / "data.yaml"))
    assert set(gt) == {"a", "b"} and gt["a"]["w"] == 1280 and len(gt["a"]["objekte"]) == 2 and gt["b"]["objekte"] == []
    assert gt["a"]["objekte"][0]["xyxy"] == pytest.approx((0.3, 0.3, 0.7, 0.7))


def test_pruefe_val_mit_vorhersagen_und_cli(mini_datensatz, tmp_path):
    vh = {"a": [{"cls": 1, "conf": 0.95, "xyxy": [0.15, 0.15, 0.25, 0.25], "kpts": [[0, 0, 0]] * 3}], "b": []}
    e = g.pruefe_val("modell.pt", str(mini_datensatz / "data.yaml"), vorhersagen=vh)
    assert e["gates"]["A"]["status"] == "BESTANDEN"
    assert e["gates"]["A2"]["status"] == "BESTANDEN"
    assert e["gates"]["B"]["status"] == "OFFEN"
    assert e["gates"]["B2"]["status"] == "OFFEN"
    assert e["gesamt"].startswith("VORLÄUFIG")
    md = g.bericht_md(e)
    assert "| A |" in md and "VORLÄUFIG" in md
    p = tmp_path / "vh.json"
    p.write_text(json.dumps(vh))
    assert g.main(["val", "--modell", "m.pt", "--daten", str(mini_datensatz / "data.yaml"), "--vorhersagen", str(p),
                   "--json", str(tmp_path / "g.json"), "--md", str(tmp_path / "g.md")]) == 0
    assert json.loads((tmp_path / "g.json").read_text())["gates"]["D"]["status"] == "OFFEN"
    # Fehlalarm im leeren Bild -> NICHT FREIGEGEBEN -> Exit-Code 1
    vh["b"] = [{"cls": 2, "conf": 0.99, "xyxy": [0.1, 0.1, 0.2, 0.2], "kpts": [[0, 0, 0]] * 3}]
    p.write_text(json.dumps(vh))
    assert g.main(["val", "--modell", "m.pt", "--daten", str(mini_datensatz / "data.yaml"), "--vorhersagen", str(p)]) == 1


def test_modellkarte_warnt_ohne_geburt(mini_datensatz):
    vh = {"a": [], "b": []}
    e = g.pruefe_val("m.pt", str(mini_datensatz / "data.yaml"), vorhersagen=vh)
    konv = {"splits": {"train": {"bilder": 10, "inst_kuh": 5}, "val": {"bilder": 2}}}
    karte = g.modellkarte("v1", e, konv, {"pose_map50": 0.5}, {"datum": "2026-11-01", "basis": "yolov8n-pose.pt"})
    assert "# Modellkarte v1" in karte and "NICHT scharfgeschaltet" in karte and "pose_map50: 0.500" in karte


def test_auswerten_jsonl(tmp_path):
    p = tmp_path / "tag.jsonl"
    zeilen = [{"datei": "1.jpg", "defekt": 0.0, "objekte": []},
              {"datei": "2.jpg", "fehler": "unlesbar", "objekte": None},
              {"datei": "3.jpg", "defekt": 0.0, "objekte": [{"cls": 1, "conf": 0.9, "xyxy": [0, 0, 1, 1], "kpts": []}]},
              {"datei": "4.jpg", "defekt": 0.3, "objekte": [{"cls": 2, "conf": 0.95, "xyxy": [0, 0, 1, 1], "kpts": []}]}]
    p.write_text("\n".join(json.dumps(z) for z in zeilen) + "\n")
    e = g.auswerten_jsonl(str(p))
    assert e["bilder"] == 4 and e["unlesbar"] == 1 and e["davon_defekt"] == 1
    assert e["austreibungs_fehlalarme"] == 2 and e["davon_in_defektbildern"] == 1
    assert e["gate_C_austreibung"] == "NICHT BESTANDEN"


# ----------------------------------------------------------------------------- QA-Befunde (H3, M1, N2, N6)
def _roh(anker, nc=3, n_kpts=3, n=8):
    """Synthetische YOLOv8-Pose-Rohausgabe (4 + nc + 3k, n); anker: {j: (cx, cy, w, h, [scores], [(x,y,v)...])}."""
    aus = np.zeros((4 + nc + 3 * n_kpts, n), np.float32)
    for j, (cx, cy, bw, bh, sc, kp) in anker.items():
        aus[:4, j] = (cx, cy, bw, bh)
        aus[4:4 + nc, j] = sc
        for i, (x, y, v) in enumerate(kp):
            aus[4 + nc + 3 * i:4 + nc + 3 * i + 3, j] = (x, y, v)
    return aus


def test_dekodierung_verliert_fruchtblase_am_kuh_anker_nicht():
    kp = [(300, 300, 0.9), (400, 300, 0.9), (420, 360, 0.8)]
    aus = _roh({0: (320, 320, 200, 120, [0.90, 0.85, 0.0], kp), 1: (100, 100, 20, 20, [0.1, 0.1, 0.1], kp)})
    erg = g.dekodiere_pose(aus, 3, 0.25, 0.7, links=0, oben=0, r=1.0, w=640, h=640)
    klassen = sorted(o["cls"] for o in erg)
    assert klassen == [0, 1]
    sack = [o for o in erg if o["cls"] == 1][0]
    assert sack["conf"] == pytest.approx(0.85) and sack["xyxy"] == pytest.approx((0.34375, 0.40625, 0.65625, 0.59375))


def test_dekodierung_letterbox_rueckrechnung():
    # 1280x720-Bild in 640er-Letterbox: r = 0.5, oben = 140
    kp = [(320, 320, 0.9), (330, 320, 0.9), (340, 330, 0.9)]
    aus = _roh({0: (320, 320, 100, 50, [0.9, 0.0, 0.0], kp)})
    erg = g.dekodiere_pose(aus, 3, 0.25, 0.7, links=0, oben=140, r=0.5, w=1280, h=720)
    o = erg[0]
    assert o["xyxy"] == pytest.approx(((270 / 0.5) / 1280, ((295 - 140) / 0.5) / 720, (370 / 0.5) / 1280, ((345 - 140) / 0.5) / 720))
    assert o["kpts"][0][:2] == pytest.approx((640 / 1280, 360 / 720))


@pytest.mark.parametrize("name", ["20261013-210000.jpg", "20261014-030000.jpg", "20261025-013000.jpg", "kamera_20261026-110500.jpg"])
def test_stalltag_gleich_wie_konverter(name):
    import cvat_zu_yolo_pose as konv
    assert g.stalltag(name) == konv.stalltag(name)


def test_tag_modus_wertet_defektbilder_aus_und_zaehlt_unlesbare(tmp_path):
    ordner = tmp_path / "bilder"
    ordner.mkdir()
    rng = np.random.default_rng(0)
    sauber = rng.integers(0, 255, (360, 640, 3), dtype=np.uint8)
    defekt = sauber.copy()
    defekt[180:] = defekt[180]                      # untere Hälfte "verschmiert" (Zeile wiederholt)
    cv2.imwrite(str(ordner / "20261018-120000.jpg"), sauber)
    cv2.imwrite(str(ordner / "20261018-120100.jpg"), defekt)
    (ordner / "20261018-120200.jpg").write_bytes(b"")   # unlesbar (0 Byte)
    cv2.imwrite(str(ordner / "20261020-120000.jpg"), sauber)   # anderer Stalltag

    def fake_modell(img):
        return [{"cls": 1, "conf": 0.9, "xyxy": (0.1, 0.1, 0.2, 0.2), "kpts": [(0, 0, 0)] * 3}]
    jl = tmp_path / "t.jsonl"
    e = g.pruefe_tag("fake.onnx", str(ordner), "*.jpg", str(jl), tag="2026-10-18", modell=fake_modell)
    assert e["bilder_gesamt"] == 3 and e["vollstaendig"] and e["unlesbar"] == 1 and e["defekt_ausgewertet"] == 1
    assert e["austreibungs_alarme_diese_sitzung"] == {"sauber": ["20261018-120000.jpg"], "defekt": ["20261018-120100.jpg"]}
    ausw = g.auswerten_jsonl(str(jl))
    assert ausw["austreibungs_fehlalarme"] == 2 and ausw["davon_in_defektbildern"] == 1 and ausw["unlesbar"] == 1
    # zweiter Aufruf: alles schon erledigt -> vollständig, nichts doppelt
    e2 = g.pruefe_tag("fake.onnx", str(ordner), "*.jpg", str(jl), tag="2026-10-18", modell=fake_modell)
    assert e2["vollstaendig"] and e2["bilder_diese_sitzung"] == 0
    assert sum(1 for _ in open(jl)) == 3


def test_gates_an_onnx_sind_verbindlich(mini_datensatz):
    e = g.pruefe_val("best_v1.onnx", str(mini_datensatz / "data.yaml"), vorhersagen={"a": [], "b": []})
    assert e["verbindlich"] and "ja (ONNX" in g.bericht_md(e)
    e = g.pruefe_val("best.pt", str(mini_datensatz / "data.yaml"), vorhersagen={"a": [], "b": []})
    assert not e["verbindlich"] and "nur Information" in g.bericht_md(e)


# ----------------------------------------------------------------------------- QA-Nachprüfung
def test_auswerten_jsonl_uebersteht_abgeschnittene_zeile(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"datei": "1.jpg", "defekt": 0.0, "objekte": []}) + "\n" + '{"datei": "2.jpg", "def')
    e = g.auswerten_jsonl(str(p))
    assert e["bilder"] == 1 and e["kaputte_zeilen"] == 1


def test_tag_cli_prueft_val_stalltag(tmp_path):
    bericht = tmp_path / "konvertierung_bericht.json"
    bericht.write_text(json.dumps({"stalltage": {"train": ["2026-10-19"], "val": ["2026-10-18"]}}))
    rc = g.main(["tag", "--modell", "x.onnx", "--bilder-ordner", str(tmp_path), "--stalltag", "2026-10-19",
                 "--bericht", str(bericht), "--jsonl", str(tmp_path / "t.jsonl")])
    assert rc == 2
    with pytest.raises(SystemExit):
        g.main(["tag", "--modell", "x.onnx", "--bilder-ordner", str(tmp_path), "--jsonl", str(tmp_path / "t.jsonl")])


def test_bericht_enthaelt_sha256_und_dekodierung(mini_datensatz, tmp_path):
    modell = tmp_path / "best_v1.onnx"
    modell.write_bytes(b"abc")
    e = g.pruefe_val(str(modell), str(mini_datensatz / "data.yaml"), vorhersagen={"a": [], "b": []})
    assert e["modell_sha256"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    md = g.bericht_md(e)
    assert "SHA-256: ba7816bf" in md and "Mehrfach-Label" in md
    karte = g.modellkarte("v1", e, {"splits": {}}, {}, {})
    assert "ba7816bf" in karte and "Dekodierung" in karte
