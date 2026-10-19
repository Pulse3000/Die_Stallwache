#!/usr/bin/env python3
"""Tests FreezeWatchdog: genau EIN Ereignis beim Eintritt in den Fehlerzustand,
genau eines bei Erholung, Streifen-Erkennung, kein Fehlalarm bei lebendigem
Bild, Fail-open bei Watchdog-Fehlern, Konfig-Fabrik.

Braucht echtes numpy (Teil von requirements.txt). Beides geht:
    python3 edge-agent/tests/test_freeze_watchdog.py
    pytest -q edge-agent/tests/test_freeze_watchdog.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from freeze_watchdog import (  # noqa: E402
    FRAMES_ANALYSE,
    FRAMES_SILENT,
    FreezeWatchdog,
    baue_watchdog,
)

H, B = 360, 640
RNG = np.random.default_rng(7)


def lebendig() -> np.ndarray:
    """Neues Bild mit natuerlichem Rauschen und Struktur (Kamera laeuft)."""
    basis = np.linspace(0, 255, B, dtype=np.float32)[None, :, None]
    return np.clip(
        basis + RNG.normal(0, 25, (H, B, 3)), 0, 255
    ).astype(np.uint8)


def streifenbild() -> np.ndarray:
    """Jede Spalte vertikal konstant – typische Dekoder-Korruption."""
    spalten = RNG.integers(0, 255, (1, B, 3)).astype(np.uint8)
    return np.repeat(spalten, H, axis=0)


def lauf(wd, frames, t0=1_000_000.0, schritt=60.0):
    """Schickt Frames durch den Watchdog; liefert (Ereignisliste mit Index)."""
    ereignisse = []
    for i, f in enumerate(frames):
        ev = wd.pruefe(f, jetzt=t0 + i * schritt)
        if ev:
            ereignisse.append((i, ev))
    return ereignisse


def test_lebendiges_bild_nie_alarm():
    wd = FreezeWatchdog("stallwache")
    assert lauf(wd, [lebendig() for _ in range(40)]) == []
    assert not wd.defekt


def test_eingefroren_genau_ein_ereignis_und_eine_erholung():
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=5)
    fest = lebendig()
    frames = [lebendig(), lebendig()] + [fest.copy() for _ in range(20)] + [lebendig(), lebendig()]
    ev = lauf(wd, frames)
    assert len(ev) == 2, ev
    (i_ein, e_ein), (i_aus, e_aus) = ev
    assert e_ein["typ"] == "info" and e_ein["kamera"] == "stallwache"
    assert e_ein["kuhId"] is None and e_ein["konfidenz"] is None
    assert "eingefroren" in e_ein["nachricht"]
    assert "wieder in Ordnung" in e_aus["nachricht"]
    # frames[2] ist der erste "feste"; 5 identische Folgebilder -> Alarm bei Index 2+5
    assert i_ein == 2 + 5
    assert i_aus == 22


def test_defekt_gilt_genau_waehrend_des_ausfalls():
    wd = FreezeWatchdog("futterwache", frames_bis_alarm=3)
    fest = lebendig()
    zustand = []
    for i, f in enumerate([lebendig()] + [fest.copy() for _ in range(8)] + [lebendig()]):
        wd.pruefe(f, jetzt=float(i))
        zustand.append(wd.defekt)
    assert zustand[:4] == [False] * 4          # 3 Wiederholungen noch kein Alarm
    assert zustand[4:9] == [True] * 5
    assert zustand[9] is False


def test_unter_schwelle_kein_alarm():
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=5)
    fest = lebendig()
    frames = [fest.copy() for _ in range(5)] + [lebendig()]   # nur 4 Wiederholungen
    assert lauf(wd, frames) == []


def test_streifen_genau_ein_ereignis():
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=4)
    frames = [lebendig()] + [streifenbild() for _ in range(15)] + [lebendig()]
    ev = lauf(wd, frames)
    assert len(ev) == 2, ev
    assert "Streifen" in ev[0][1]["nachricht"]
    assert "wieder in Ordnung" in ev[1][1]["nachricht"]


def test_einfarbige_wand_ist_kein_streifenfehler():
    """Gleichmaessige Flaeche (Dunkelheit): Spalten unterscheiden sich nicht."""
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=3)
    dunkel = lambda: np.full((H, B, 3), 12, np.uint8) + RNG.integers(0, 40, (H, B, 3), dtype=np.uint8)  # noqa: E731
    assert lauf(wd, [dunkel() for _ in range(10)]) == []


def mit_band(oben: bool, anteil: float, wert: int) -> np.ndarray:
    """Lebendiges Bild mit gleichmaessigem, bildbreitem Band (dunkle Decke
    ausserhalb der IR-Reichweite, ueberstrahlte Wand, Privatsphaere-Maske)."""
    bild = lebendig()
    h = int(H * anteil)
    zeilen = slice(0, h) if oben else slice(H - h, H)
    bild[zeilen] = np.clip(wert + RNG.normal(0, 0.3, (h, B, 3)), 0, 255).astype(np.uint8)
    return bild


def test_dunkles_band_mit_lebendigem_rest_ist_kein_streifenfehler():
    """IR-Nacht: Decke oben dunkel, Rest lebt -> kein Defekt (sonst fehlen
    nachts alle Trainingsbilder, Beschluss B9)."""
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=3)
    assert lauf(wd, [mit_band(True, 0.25, 6) for _ in range(10)]) == []
    assert not wd.defekt


def test_helles_band_unten_ist_kein_streifenfehler():
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=3)
    assert lauf(wd, [mit_band(False, 0.20, 250) for _ in range(10)]) == []


def test_streifen_nur_im_unteren_drittel_wird_erkannt():
    """Echte Dekoder-Korruption in einem Teilbereich bleibt ein Defekt."""
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=3)

    def teilstreifen():
        bild = lebendig()
        h = int(H * 0.30)
        bild[H - h:] = streifenbild()[H - h:]
        return bild

    ev = lauf(wd, [teilstreifen() for _ in range(6)])
    assert len(ev) == 1 and "Streifen" in ev[0][1]["nachricht"], ev


def test_streifen_neben_dunklem_band_wird_erkannt():
    """Ein gleichmaessiges Band darf echte Streifen daneben nicht verdecken."""
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=3)

    def beides():
        bild = mit_band(True, 0.25, 6)
        h = int(H * 0.30)
        bild[H - h:] = streifenbild()[H - h:]
        return bild

    ev = lauf(wd, [beides() for _ in range(6)])
    assert len(ev) == 1 and "Streifen" in ev[0][1]["nachricht"], ev


def test_meldetext_silent_mode_nennt_trainingsbilder():
    """Im Silent Mode gibt es keine Analyse – die Meldung sagt, was wirklich passiert."""
    wd = baue_watchdog({"watchdog": {"frames_bis_alarm": 2}}, "stallwache", analyse_aktiv=False)
    fest = lebendig()
    ev = lauf(wd, [fest.copy() for _ in range(4)])
    text = ev[0][1]["nachricht"]
    assert "keine Trainingsbilder" in text and "Analyse" not in text, text


def test_meldetext_analyse_modus_unveraendert():
    wd = baue_watchdog({"watchdog": {"frames_bis_alarm": 2}}, "stallwache", analyse_aktiv=True)
    fest = lebendig()
    ev = lauf(wd, [fest.copy() for _ in range(4)])
    assert "Analyse ausgesetzt" in ev[0][1]["nachricht"]


def test_aufloesungswechsel_ist_kein_einfrieren():
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=2)
    # Beide Formate bleiben nach dem internen Verkleinern verschieden
    # (90x160 vs. 80x160) - ein Formatwechsel ist ein neuer Stream, kein Einfrieren.
    a = np.full((360, 640, 3), 40, np.uint8)
    b = np.full((400, 800, 3), 40, np.uint8)
    assert lauf(wd, [a, b, a, b, a, b]) == []


def test_kein_bild_wird_ignoriert():
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=2)
    assert wd.pruefe(None) is None and not wd.defekt and wd.ausfaelle == 0


def test_fail_open_bei_watchdog_fehler():
    """Ein gestolperter Watchdog darf die Analyse nicht ausgesetzt lassen."""
    wd = FreezeWatchdog("stallwache", frames_bis_alarm=2)
    fest = lebendig()
    for i in range(5):
        wd.pruefe(fest.copy(), jetzt=float(i))
    assert wd.defekt
    assert wd.pruefe("kein bild", jetzt=9.0) is None      # loest intern Exception aus
    assert wd.ausfaelle == 1
    assert wd.defekt is False and wd.grund is None


def test_fabrik_standardwerte_je_modus():
    assert baue_watchdog({}, "stallwache", analyse_aktiv=False).frames_bis_alarm == FRAMES_SILENT == 5
    assert baue_watchdog({}, "stallwache", analyse_aktiv=True).frames_bis_alarm == FRAMES_ANALYSE == 300
    assert baue_watchdog({"watchdog": {"frames_bis_alarm": None}}, "k", False).frames_bis_alarm == 5


def test_fabrik_config_ueberschreibt_und_validiert():
    cfg = {"watchdog": {"frames_bis_alarm": 12}}
    assert baue_watchdog(cfg, "k", True).frames_bis_alarm == 12
    for kaputt in (0, -3, "viel", 2.5, True):
        wd = baue_watchdog({"watchdog": {"frames_bis_alarm": kaputt}}, "k", True)
        assert wd.frames_bis_alarm == 300, kaputt


def test_fabrik_abschaltbar_und_kameraname():
    assert baue_watchdog({"watchdog": {"aktiv": False}}, "stallwache", True) is None
    assert baue_watchdog({}, "futterwache", True).kamera == "futterwache"


if __name__ == "__main__":
    fehl = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"OK   {name}")
            except Exception as e:  # noqa: BLE001
                fehl += 1
                print(f"FEHL {name}: {type(e).__name__}: {e}")
    sys.exit(1 if fehl else 0)
