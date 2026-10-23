#!/usr/bin/env python3
"""Logiktests „Ein Edge-Agent“: Geraetewissen aus kuhwatch im Edge-Agenten.

docs/ein-edge-agent-spezifikation.md: alte CPU ohne AVX (U1), Tierklassen
statt „jede Box ist eine Kuh“ (U2), Silent Mode ohne torch. ultralytics,
torch und torchvision sind gestubbt; die NMS-Pruefung braucht numpy und
wird ohne numpy sichtbar uebersprungen.
"""

import random
import sys
import time as echte_zeit
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:  # echtes numpy vor dem Stub der Testhilfe, falls installiert
    import numpy  # noqa: F401
except ImportError:
    pass
from hilfe import Pruefer, lade_main  # noqa: E402

m, _ = lade_main()
p = Pruefer("Ein Edge-Agent")
ac = sys.modules["alte_cpu"]

# Flags einer AMD A6-3650 (Llano, 2011): sse4a, aber kein avx/sse4_1.
LLANO = ("processor\t: 0\nvendor_id\t: AuthenticAMD\nmodel name\t: AMD A6-3650 APU\n"
         "flags\t\t: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov pat "
         "pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb rdtscp lm "
         "3dnowext 3dnow constant_tsc rep_good nopl nonstop_tsc pni monitor cx16 popcnt "
         "lahf_lm cmp_legacy svm extapic cr8_legacy abm sse4a misalignsse 3dnowprefetch\n")
MODERN = LLANO.replace("3dnowprefetch", "3dnowprefetch ssse3 sse4_1 sse4_2 avx avx2")

# --- 1. Alte CPU erkennen (U1) -----------------------------------------------
p.check("1: A6-3650 hat kein AVX", ac.hat_avx(LLANO) is False)
p.check("1: moderne CPU hat AVX", ac.hat_avx(MODERN) is True)
p.check("1: ohne Flags-Zeile unbekannt", ac.hat_avx("processor : 0\n") is None)
p.check("1: auto + A6-3650 -> an", ac.alte_cpu_aktiv("auto", LLANO))
p.check("1: auto + AVX -> aus", not ac.alte_cpu_aktiv("auto", MODERN))
p.check("1: auto + unbekannt -> aus", not ac.alte_cpu_aktiv(None, "x"))
p.check("1: true erzwingt", ac.alte_cpu_aktiv(True, MODERN))
p.check("1: false verbietet", not ac.alte_cpu_aktiv("false", LLANO))
p.check("1: 'avx' als Teil eines anderen Flags zaehlt nicht",
        ac.hat_avx("flags : sse avx512_fake_x\n") is False)

# --- 2. NumPy-NMS gegen Referenz ---------------------------------------------
if not hasattr(sys.modules.get("numpy"), "asarray"):
    print("SKIP 2: NumPy-NMS (numpy fehlt; laeuft im Docker-Test und im venv)")
else:
    import numpy as np

    def referenz(boxen, werte, schwelle):
        def iou(a, b):
            s = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
            u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - s
            return s / u if u > 0 else 0.0
        offen = sorted(range(len(boxen)), key=lambda i: -werte[i])
        bleiben = []
        while offen:
            i = offen.pop(0)
            bleiben.append(i)
            offen = [j for j in offen if iou(boxen[i], boxen[j]) <= schwelle]
        return bleiben

    zufall = random.Random(7)
    gleich = 0
    for _ in range(200):
        n = zufall.randint(0, 25)
        boxen = []
        for _ in range(n):
            x, y = zufall.uniform(0, 600), zufall.uniform(0, 400)
            boxen.append([x, y, x + zufall.uniform(5, 200), y + zufall.uniform(5, 200)])
        werte = [zufall.random() for _ in range(n)]
        ist = ac.nms_indizes(np.asarray(boxen, dtype=np.float32).reshape(-1, 4),
                             np.asarray(werte, dtype=np.float32), 0.45)
        gleich += ist == referenz(boxen, werte, 0.45)
    p.check(f"2: NumPy-NMS = Referenz in {gleich}/200 Zufallsfaellen", gleich == 200)

# --- 3. Silent Mode laedt kein torch/ultralytics -----------------------------
BASIS = {
    "keypoints": {"spine_end": 0, "tail_base": 1, "tail_tip": 2},
    "klassen": {"kuh": 0, "amniotic_sac": 1, "calf_legs": 2},
}
e = m.InferenceEngine({"modell": dict(BASIS, pfad="")})
p.check("3: Silent Mode inaktiv", not e.aktiv)
p.check("3: kein torch/ultralytics geladen",
        not any(n in sys.modules for n in ("torch", "torchvision", "ultralytics")))


# --- Stubs fuer den Analyse-Modus -------------------------------------------
class T:
    def __init__(self, wert):
        self.wert = wert

    def cpu(self):
        return self

    def numpy(self):
        return self.wert


class Boxen:
    def __init__(self, dets, ids):
        self.cls = [d[5] for d in dets]
        self.conf = [d[4] for d in dets]
        self.xyxy = [d[:4] for d in dets]
        self.id = ids

    def __len__(self):
        return len(self.cls)


class FakeYOLO:
    letzte_kw: dict = {}

    def __init__(self, pfad):
        self.pfad = pfad
        self.callbacks = {"on_predict_postprocess_end": []}

    def add_callback(self, ereignis, fn):
        self.callbacks.setdefault(ereignis, []).append(fn)

    def track(self, dets, **kw):
        FakeYOLO.letzte_kw = kw
        erlaubt = kw.get("classes")
        dets = [d for d in dets if erlaubt is None or d[5] in erlaubt]
        kps = types.SimpleNamespace(xy=[T([(0, 0)] * 3)] * len(dets), conf=[T([0.1] * 3)] * len(dets))
        erg = types.SimpleNamespace(boxes=Boxen(dets, list(range(1, len(dets) + 1))), keypoints=kps)
        pred = types.SimpleNamespace(results=[erg])
        for fn in self.callbacks["on_predict_postprocess_end"]:
            fn(pred)
        return [erg]


torch = types.ModuleType("torch")
torch.backends = types.SimpleNamespace(mkldnn=types.SimpleNamespace(enabled=True))
torchvision = types.ModuleType("torchvision")
ORIGINAL_NMS = object()
torchvision.ops = types.SimpleNamespace(nms=ORIGINAL_NMS)
ul = types.ModuleType("ultralytics")
ul.YOLO = FakeYOLO
sys.modules.update(torch=torch, torchvision=torchvision, ultralytics=ul)

# --- 4. Alte CPU: Schalter vor dem Laden (U1) --------------------------------
m.InferenceEngine({"modell": dict(BASIS, pfad="best.onnx", alte_cpu=False)})
p.check("4: alte_cpu false -> oneDNN und NMS unberuehrt",
        torch.backends.mkldnn.enabled is True and torchvision.ops.nms is ORIGINAL_NMS)
m.InferenceEngine({"modell": dict(BASIS, pfad="best.onnx", alte_cpu=True)})
p.check("4: alte_cpu true -> oneDNN aus", torch.backends.mkldnn.enabled is False)
p.check("4: alte_cpu true -> NumPy-NMS eingesetzt", torchvision.ops.nms is ac.numpy_nms)

# --- 5. Standardmodell: nichts aendert sich (U2) -----------------------------
e = m.InferenceEngine({"modell": dict(BASIS, pfad="best.pt", alte_cpu=False)})
p.check(f"5: Standardmodell -> Filter alle drei Klassen ({e.klassen_filter})",
        e.klassen_filter == [0, 1, 2])
kuehe, objekte = e.analysiere([(50, 50, 400, 300, 0.9, 0), (420, 200, 470, 250, 0.88, 1)])
p.check("5: Kuh und Fruchtblase wie bisher", len(kuehe) == 1 and [o.klasse for o in objekte] == ["amniotic_sac"])
p.check("5: Filter geht an den Tracker", FakeYOLO.letzte_kw.get("classes") == [0, 1, 2])

# --- 6. Allgemeines Modell: Mensch ist keine Kuh (U2) ------------------------
COCO = {"keypoints": BASIS["keypoints"],
        "klassen": {"person": 0, "cow": 19, "amniotic_sac": 80}, "alte_cpu": False}
KUH = (100, 150, 400, 350, 0.9, 19)
MENSCH = (150, 40, 260, 330, 0.9, 0)       # steht hinter der Kuh, Box weit oben
BLASE = (380, 260, 420, 300, 0.91, 80)


def logik():
    return m.LogicEngine({
        "logik": {"winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
                  "override_konfidenz": 0.80, "brunst_min_dauer_s": 4, "eskalation_minuten": 60},
        "telegram": {"cooldown_minuten": 15},
    })


UHR = [80_000.0]
m.time = types.SimpleNamespace(**{k: getattr(echte_zeit, k) for k in dir(echte_zeit) if not k.startswith("_")})
m.time.time = lambda: UHR[0]


def brunst_alarme(engine):
    lg, typen = logik(), []
    for _ in range(8):
        kuehe, objekte = engine.analysiere([KUH, MENSCH])
        typen += [a.typ for a in lg.bewerte(kuehe, objekte)]
        UHR[0] += 1
    return typen


alt = m.InferenceEngine({"modell": dict(COCO, pfad="yolov8n.onnx", tier_klassen=["cow", "person"])})
p.check("6: Gegenprobe (Mensch als Tier gezaehlt): Brunstverdacht",
        "brunstverdacht" in brunst_alarme(alt))
neu = m.InferenceEngine({"modell": dict(COCO, pfad="yolov8n.onnx", tier_klassen=["cow"])})
p.check(f"6: Tracker-Filter ohne Mensch ({neu.klassen_filter})", neu.klassen_filter == [19, 80])
p.check("6: Mensch hinter Kuh -> kein Brunstverdacht", "brunstverdacht" not in brunst_alarme(neu))
kuehe, _ = neu.analysiere([KUH, MENSCH])
p.check("6: nur die Kuh ist ein Tier", [k.box for k in kuehe] == [KUH[:4]])
_, objekte = neu.analysiere([KUH, MENSCH, BLASE])
p.check("6: Fruchtblase meldet unabhaengig von tier_klassen",
        [o.klasse for o in objekte] == ["amniotic_sac"])

# Falsch konfigurierte tier_klassen fallen auf
leer = m.InferenceEngine({"modell": dict(BASIS, pfad="best.pt", tier_klassen=["rind"], alte_cpu=False)})
p.check("6: unbekannte tier_klassen -> keine Kuh, Filter nur Objekte",
        leer.klassen_filter == [1, 2])

sys.exit(p.bericht())
