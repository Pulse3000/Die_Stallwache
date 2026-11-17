import numpy as np
from freeze_watchdog import FreezeWatchdog

rng = np.random.default_rng(0)
def szene(): return rng.integers(0, 255, (360, 640, 3), dtype=np.uint8)
def streifen(f):
    f = f.copy(); f[240:] = f[240:241]; return f

def test_eingefroren_einmal_dann_ruhe_dann_erholung():
    wd = FreezeWatchdog("stallwache"); bild = szene(); evs = []
    for i in range(20): evs.append(wd.pruefe(bild, jetzt=1000 + i*120))
    evs = [e for e in evs if e]
    assert len(evs) == 1 and "eingefroren" in evs[0]["nachricht"] and evs[0]["typ"] == "info"
    e = wd.pruefe(szene(), jetzt=5000)
    assert e and "wieder in Ordnung" in e["nachricht"] and not wd.defekt

def test_streifen_erkannt():
    wd = FreezeWatchdog("stallwache")
    evs = [wd.pruefe(streifen(szene())) for _ in range(6)]
    assert sum(1 for e in evs if e) == 1 and "Streifen" in wd.grund

def test_normal_kein_alarm():
    wd = FreezeWatchdog("stallwache")
    assert all(wd.pruefe(szene()) is None for _ in range(30))

def test_kaputter_frame_blockiert_nicht():
    assert FreezeWatchdog("x").pruefe(None) is None
