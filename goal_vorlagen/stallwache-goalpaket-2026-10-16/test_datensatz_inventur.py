"""
Vertragstests — Datensatz-Inventur (Punkt 4 Tagesreport, training-pipeline §1–4).

Nicht löschen, nicht abschwächen. Ergänzen ausdrücklich erwünscht: ein Testfall
mit dem echten Dateinamensmuster aus ./aufnahmen (siehe GOAL_BRIEF_trainer.md).
"""

import os
import sys
from datetime import date, datetime

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))

from datensatz_inventur import (  # noqa: E402
    InventurKonfig,
    dhash,
    hamming,
    inventur,
    lichtphase,
    metriken_markdown,
    split_nach_tagen,
    stall_tag,
    zeit_aus_dateiname,
)

PIL = pytest.importorskip("PIL.Image")


def szene(seed, farbe=(1.0, 1.0, 1.0), hell=1.0, hoehe=180, breite=320):
    """Blockmuster als Stall-Ersatz: Struktur für dHash, steuerbare Farbe/Helligkeit."""
    rnd = np.random.default_rng(seed)
    bloecke = rnd.integers(40, 215, size=(9, 16)).astype(np.float64)
    grau = np.kron(bloecke, np.ones((hoehe // 9 + 1, breite // 16 + 1)))[:hoehe, :breite] * hell
    rgb = np.stack([grau * farbe[0], grau * farbe[1], grau * farbe[2]], axis=2)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def speichern(ordner, name, arr):
    pfad = os.path.join(ordner, name)
    PIL.fromarray(arr).save(pfad, quality=85)
    return pfad


class TestLichtphase:

    def test_graues_jpeg_ist_ir_nacht(self, tmp_path):
        pfad = speichern(tmp_path, "x.jpg", szene(1))
        arr = np.asarray(PIL.open(pfad).convert("RGB"))
        assert lichtphase(arr) == "ir_nacht"

    def test_einkanalbild_ist_ir_nacht(self):
        assert lichtphase(szene(1)[:, :, 0]) == "ir_nacht"

    def test_helles_farbbild_ist_tag(self):
        assert lichtphase(szene(2, farbe=(1.0, 0.75, 0.5))) == "tag"

    def test_dunkles_farbbild_ist_daemmerung(self):
        assert lichtphase(szene(3, farbe=(1.0, 0.7, 0.4), hell=0.3)) == "daemmerung"


class TestZeit:

    @pytest.mark.parametrize("name, kamera, zeit", [
        ("stallwache_20261014_031500.jpg", "stallwache", datetime(2026, 10, 14, 3, 15, 0)),
        ("futterwache_2026-10-14_03-15-00.jpg", "futterwache", datetime(2026, 10, 14, 3, 15, 0)),
        ("stallbox-20261014T031500.png", "stallbox", datetime(2026, 10, 14, 3, 15, 0)),
        ("stallwache_20261102-031500.jpg", "stallwache", datetime(2026, 11, 2, 3, 15, 0)),  # B21
        ("20261009-082828.jpg", "unbekannt", datetime(2026, 10, 9, 8, 28, 28)),  # Altbestand ohne Praefix
    ])
    def test_bekannte_muster(self, name, kamera, zeit):
        assert zeit_aus_dateiname(name) == (kamera, zeit)

    def test_unbekanntes_muster_ist_none(self):
        assert zeit_aus_dateiname("IMG_0042.jpg") is None

    def test_stalltag_in_ortszeit_wie_der_konverter(self):
        # 11:30 UTC = 13:30 Ortszeit (Sommerzeit) -> Stalltag 18.10., nicht 17.10. (B21)
        assert stall_tag(datetime(2026, 10, 18, 11, 30)) == date(2026, 10, 18)
        # 09:30 UTC = 11:30 Ortszeit -> gehoert noch zur Nacht davor
        assert stall_tag(datetime(2026, 10, 18, 9, 30)) == date(2026, 10, 17)
        # Winterzeit: 11:30 UTC = 12:30 Ortszeit -> 02.11.
        assert stall_tag(datetime(2026, 11, 2, 11, 30)) == date(2026, 11, 2)

    def test_nacht_gehoert_einem_stalltag(self):
        abend = stall_tag(datetime(2026, 10, 10, 23, 0))
        morgen = stall_tag(datetime(2026, 10, 11, 3, 0))
        mittag = stall_tag(datetime(2026, 10, 11, 13, 0))
        assert abend == morgen == date(2026, 10, 10)
        assert mittag == date(2026, 10, 11)


class TestDubletten:

    def test_rauschen_ist_dublette(self):
        a = szene(5, farbe=(1.0, 0.8, 0.6))
        rnd = np.random.default_rng(0)
        b = np.clip(a.astype(int) + rnd.integers(-3, 4, size=a.shape), 0, 255).astype(np.uint8)
        assert hamming(dhash(a), dhash(b)) <= InventurKonfig().dublette_hamming

    def test_andere_szene_ist_einzigartig(self):
        assert hamming(dhash(szene(5)), dhash(szene(6))) > InventurKonfig().dublette_hamming


@pytest.fixture
def aufnahmen(tmp_path):
    """2 Kameras, 4 Stall-Tage; IR nur in der Nacht 11./12.10.; eine Dublette, ein Fallback, eine kaputte Datei."""
    o = str(tmp_path)
    seed = 100
    for tag in (10, 11, 12, 13):
        for stunde, art in ((14, "tag"), (19, "daemmerung")):
            seed += 1
            farbe, hell = ((1.0, 0.75, 0.5), 1.0) if art == "tag" else ((1.0, 0.7, 0.4), 0.3)
            speichern(o, f"stallwache_202610{tag:02d}_{stunde:02d}0000.jpg", szene(seed, farbe, hell))
            seed += 1
            speichern(o, f"futterwache_202610{tag:02d}_{stunde:02d}0000.jpg", szene(seed, farbe, hell))
    for stunde, tag in ((23, 11), (2, 12), (4, 12)):
        seed += 1
        speichern(o, f"stallwache_202610{tag:02d}_{stunde:02d}0000.jpg", szene(seed))
    speichern(o, "stallwache_20261012_041000.jpg", szene(seed))              # Dublette des 04:00-Bildes
    speichern(o, "stallwache_kaputt.jpg", szene(999, (1.0, 0.75, 0.5)))      # Zeit aus Dateidatum
    with open(os.path.join(o, "stallwache_20261013_150000.jpg"), "wb") as f:
        f.write(b"keinbild")                                                   # unlesbar
    os.makedirs(os.path.join(o, "crops"))
    speichern(os.path.join(o, "crops"), "stallwache_20261012_050000.jpg", szene(1))  # Re-ID-Crops ignorieren
    return o


class TestInventur:

    def test_zaehlt_je_kamera(self, aufnahmen):
        inv = inventur(aufnahmen)
        sw, fw = inv.kameras["stallwache"], inv.kameras["futterwache"]
        assert fw.bilder == 8 and fw.einzigartig == 8
        assert sw.bilder == 8 + 3 + 1 + 1 + 1
        assert sw.unlesbar == 1 and sw.zeit_fallback == 1
        assert sw.einzigartig == sw.bilder - sw.unlesbar - 1      # genau eine Dublette
        assert sw.phasen["ir_nacht"] == 3

    def test_crops_werden_nicht_gezaehlt(self, aufnahmen):
        assert sum(k.bilder for k in inventur(aufnahmen).kameras.values()) == 8 + 14

    def test_liest_nur(self, aufnahmen):
        vorher = sorted(os.listdir(aufnahmen))
        inventur(aufnahmen)
        assert sorted(os.listdir(aufnahmen)) == vorher


class TestSplit:

    def test_ganze_tage_und_ir_nacht_im_val(self, aufnahmen):
        inv = inventur(aufnahmen)
        split = split_nach_tagen(inv)
        assert set(split.values()) == {"train", "val"}
        val = [t for t, s in split.items() if s == "val"]
        assert any(t in inv.tage_ir for t in val), "mindestens eine IR-Nacht exklusiv im Val-Set"
        assert len(set(split)) == len(split)

    def test_zu_wenige_tage_kein_val(self, tmp_path):
        speichern(str(tmp_path), "stallwache_20261014_140000.jpg", szene(1, (1.0, 0.75, 0.5)))
        split = split_nach_tagen(inventur(str(tmp_path)))
        assert list(split.values()) == ["train"]

    def test_deterministisch(self, aufnahmen):
        inv = inventur(aufnahmen)
        assert split_nach_tagen(inv) == split_nach_tagen(inv)


class TestMarkdown:

    def test_abschnitt_fuer_metriken(self, aufnahmen):
        inv = inventur(aufnahmen)
        md = metriken_markdown(inv, split_nach_tagen(inv), stand="16.10.2026 08:00")
        assert md.startswith("## Datensatz (Silent Mode) — Stand 16.10.2026 08:00")
        assert "| stallwache |" in md and "| futterwache |" in md
        assert "B9" in md and ("erfüllt" in md)
        assert "Austreibungs-Material" in md
