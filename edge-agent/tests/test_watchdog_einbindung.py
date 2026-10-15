#!/usr/bin/env python3
"""Tests Einbindung des FreezeWatchdog in main.py: Meldung genau einmal ueber
Notifier.wichtig (Telegram + Dashboard), bei defekter Kamera keine
Trainingsbilder und keine Analyse, Fail-open bei Watchdog-/Sendefehlern.
Die Hauptschleife laeuft mit gefaelschter Kamera und gefaelschten Bausteinen.

Braucht echtes numpy. Beides geht:
    python3 edge-agent/tests/test_watchdog_einbindung.py
    pytest -q edge-agent/tests/test_watchdog_einbindung.py
"""

import sys
import tempfile
import types
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import lade_main  # noqa: E402

m, _ = lade_main()
H, B = 360, 640
RNG = np.random.default_rng(11)


def lebendig() -> np.ndarray:
    basis = np.linspace(0, 255, B, dtype=np.float32)[None, :, None]
    return np.clip(basis + RNG.normal(0, 25, (H, B, 3)), 0, 255).astype(np.uint8)


class FalscherNotifier:
    kamera = "stallwache"

    def __init__(self, wirft: bool = False):
        self.meldungen: list[str] = []
        self.status_meldungen: list[str] = []
        self.wirft = wirft
        self.feedback = types.SimpleNamespace(tick=lambda: None, archiv=None)

    def wichtig(self, nachricht: str) -> None:
        self.meldungen.append(nachricht)
        if self.wirft:
            raise RuntimeError("Telegram weg")

    def status(self, nachricht: str) -> None:
        self.status_meldungen.append(nachricht)

    def digest_tick(self, analyse_aktiv: bool) -> None:
        pass


def wd(n: int = 5):
    return m.FreezeWatchdog("stallwache", frames_bis_alarm=n)


# --- pruefe_kamerabild ------------------------------------------------------

def test_ohne_watchdog_nie_defekt():
    assert m.pruefe_kamerabild(None, lebendig(), FalscherNotifier()) is False


def test_meldung_einmal_je_episode_und_defekt_waehrend_ausfall():
    n, w = FalscherNotifier(), wd(5)
    fest = lebendig()
    ergebnis = [m.pruefe_kamerabild(w, f, n) for f in
                [lebendig()] + [fest.copy() for _ in range(10)] + [lebendig()]]
    assert ergebnis == [False] * 6 + [True] * 5 + [False]
    assert len(n.meldungen) == 2
    assert "eingefroren" in n.meldungen[0] and "wieder in Ordnung" in n.meldungen[1]


def test_sendefehler_blockiert_nicht_und_defekt_bleibt():
    n, w = FalscherNotifier(wirft=True), wd(2)
    fest = lebendig()
    ergebnis = [m.pruefe_kamerabild(w, fest.copy(), n) for _ in range(5)]
    assert ergebnis[-1] is True and len(n.meldungen) == 1


def test_defekter_watchdog_blockiert_nie():
    class Kaputt:
        defekt = True

        def pruefe(self, frame):
            raise RuntimeError("boom")

    assert m.pruefe_kamerabild(Kaputt(), lebendig(), FalscherNotifier()) is False


# --- Hauptschleife mit gefaelschten Bausteinen ----------------------------------

def fahre_hauptschleife(frames, analyse: bool, cfg_zusatz=None):
    """Startet main() mit gefaelschter Kamera; liefert (notifier, gespeichert,
    analysierte_frames)."""
    gespeichert: list[str] = []
    analysiert: list[int] = []
    notifier = FalscherNotifier()

    class Strom:
        def __init__(self, cfg):
            self._it = iter(frames)

        def naechster_frame(self):
            try:
                return next(self._it)
            except StopIteration:
                raise KeyboardInterrupt  # beendet main() sauber

    class Engine:
        aktiv = analyse

        def __init__(self, cfg):
            pass

        def analysiere(self, frame):
            analysiert.append(1)
            return [], []

    class Logik:
        def __init__(self, cfg):
            pass

        def bewerte(self, kuehe, objekte):
            return []

        def fehlalarm_gemeldet(self, typ, episode):
            pass

    class Archiv:
        aktiv = False

        def __init__(self, cfg):
            pass

    class Totmann:
        def __init__(self, cfg):
            pass

        def tick(self, ok):
            return None

    with tempfile.TemporaryDirectory() as tmp:
        cfg = {
            "stream": {"kamera": "stallwache"},
            "silent_mode": {"ordner": tmp, "intervall_sekunden": 0},
        }
        cfg.update(cfg_zusatz or {})
        alt = {k: getattr(m, k) for k in
               ("lade_konfig", "StreamHandler", "InferenceEngine", "LogicEngine",
                "Notifier", "TotmannWaechter", "DatensatzArchiv", "cv2")}
        try:
            m.lade_konfig = lambda: cfg
            m.StreamHandler, m.InferenceEngine, m.LogicEngine = Strom, Engine, Logik
            m.Notifier = lambda c: notifier
            m.TotmannWaechter, m.DatensatzArchiv = Totmann, Archiv
            m.cv2 = types.SimpleNamespace(
                imwrite=lambda pfad, frame: gespeichert.append(pfad),
                imencode=lambda *a, **k: (False, None),
                IMWRITE_JPEG_QUALITY=1,
            )
            m.main()
        finally:
            for k, v in alt.items():
                setattr(m, k, v)
    return notifier, gespeichert, analysiert


def folge():
    """3 lebendige, 8 identische, 1 lebendiges Bild."""
    fest = lebendig()
    return [lebendig() for _ in range(3)] + [fest.copy() for _ in range(8)] + [lebendig()]


def test_silent_mode_speichert_nichts_waehrend_defekt():
    notifier, gespeichert, _ = fahre_hauptschleife(folge(), analyse=False)
    # gespeichert: 3 lebendige + 5 feste (vor Alarm) + 1 lebendiges nach Erholung
    assert len(gespeichert) == 9, len(gespeichert)
    assert len(notifier.meldungen) == 2
    assert "eingefroren" in notifier.meldungen[0]


def test_analyse_modus_analysiert_nichts_waehrend_defekt():
    notifier, gespeichert, analysiert = fahre_hauptschleife(
        folge(), analyse=True, cfg_zusatz={"watchdog": {"frames_bis_alarm": 5}}
    )
    assert gespeichert == []                      # Analyse-Modus speichert nie
    assert len(analysiert) == 9, len(analysiert)  # 12 Frames - 3 im Defekt
    assert len(notifier.meldungen) == 2


def test_analyse_modus_standard_ist_300_frames():
    """Ohne Konfig gilt im Analyse-Modus 300: 100 gleiche Frames sind noch ok."""
    fest = lebendig()
    notifier, _, analysiert = fahre_hauptschleife(
        [fest.copy() for _ in range(100)], analyse=True
    )
    assert notifier.meldungen == [] and len(analysiert) == 100


def test_konfig_frames_bis_alarm_wirkt():
    cfg = {"watchdog": {"frames_bis_alarm": 3}}
    fest = lebendig()
    notifier, _, analysiert = fahre_hauptschleife(
        [fest.copy() for _ in range(10)], analyse=True, cfg_zusatz=cfg
    )
    assert len(notifier.meldungen) == 1
    assert len(analysiert) == 3            # Frames 1-3 laufen, ab Frame 4 defekt


def test_watchdog_abschaltbar():
    cfg = {"watchdog": {"aktiv": False, "frames_bis_alarm": 2}}
    fest = lebendig()
    notifier, _, analysiert = fahre_hauptschleife(
        [fest.copy() for _ in range(10)], analyse=True, cfg_zusatz=cfg
    )
    assert notifier.meldungen == [] and len(analysiert) == 10


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
