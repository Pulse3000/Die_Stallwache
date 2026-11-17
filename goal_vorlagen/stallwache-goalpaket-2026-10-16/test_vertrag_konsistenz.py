"""
Konsistenz des Label-Vertrags über drei Orte: CVAT-Skelett, Datensatz-YAML, Edge-Konfig.
Eine vertauschte Keypoint-Reihenfolge rechnet Winkel aus falschen Punkten — still.
"""

import json
import os
import sys

import pytest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)

from erkennung import Konfig  # noqa: E402

yaml = pytest.importorskip("yaml")


def _lade():
    with open(os.path.join(WURZEL, "training", "stallwache-pose.yaml"), encoding="utf-8") as f:
        y = yaml.safe_load(f)
    with open(os.path.join(WURZEL, "training", "cvat-labels.json"), encoding="utf-8") as f:
        c = json.load(f)
    return y, c


def test_keypoint_reihenfolge_ueberall_gleich():
    y, c = _lade()
    skelett = next(l for l in c if l["type"] == "skeleton")
    assert [s["name"] for s in skelett["sublabels"]] == list(Konfig().keypoint_namen)
    assert y["kpt_shape"] == [len(Konfig().keypoint_namen), 3]


def test_mittellinie_ohne_spiegeltausch():
    y, _ = _lade()
    assert y["flip_idx"] == list(range(len(Konfig().keypoint_namen)))


def test_klassen_ueberall_gleich():
    y, c = _lade()
    k = Konfig()
    assert list(y["names"].values()) == [l["name"] for l in c]
    assert y["names"][0] == k.kuh_klasse
    assert set(y["names"].values()) == {k.kuh_klasse, *k.austreibung_klassen}
    assert "kalbt" not in y["names"].values()          # bewusst keine Verhaltensklasse
