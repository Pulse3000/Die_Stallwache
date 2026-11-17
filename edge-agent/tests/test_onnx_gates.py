#!/usr/bin/env python3
"""B19-Abnahme (1), Gegenprobe: Vorverarbeitung und Dekodierung des Agenten
sind woertlich die der Abnahme-Gates (abnahme_gates.py) und liefern fuer
feste Rohausgaben dieselben Objekte - auch mit den zwei Schwellen des
Agenten (Dekodierung ab 0.10, Logik ab 0.25). Braucht numpy + OpenCV und den
Trainingsordner (Hof-Rechner); fehlt er: 77 = uebersprungen.
Pfad ueberschreibbar mit STALLWACHE_GATES."""

import ast
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import UEBERSPRUNGEN, Pruefer, braucht, lade_main  # noqa: E402

braucht("numpy", "cv2")
import numpy as np  # noqa: E402

AGENT = Path(__file__).resolve().parent.parent
GATES = Path(os.environ.get("STALLWACHE_GATES",
                            AGENT / "aufnahmen" / "_training_v1" / "werkzeuge" / "abnahme_gates.py"))
if not GATES.is_file():
    print(f"UEBERSPRUNGEN: {GATES} fehlt (Trainingsordner nur am Hof-Rechner)")
    sys.exit(UEBERSPRUNGEN)

m, _ = lade_main()
p = Pruefer("ONNX-Adapter gegen abnahme_gates.py (B19)")
spec = importlib.util.spec_from_file_location("abnahme_gates_ref", GATES)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


def knoten(pfad, name):
    for k in ast.parse(Path(pfad).read_text(encoding="utf-8")).body:
        if isinstance(k, (ast.FunctionDef, ast.ClassDef)) and k.name == name:
            return ast.dump(k)
    return None


p.check("dekodiere_pose: Funktionskoerper identisch mit abnahme_gates.py",
        knoten(m.__file__, "dekodiere_pose") == knoten(GATES, "dekodiere_pose") is not None)
p.check("OnnxModell: Klasse identisch mit abnahme_gates.py (Letterbox, RGB, /255)",
        knoten(m.__file__, "OnnxModell") == knoten(GATES, "OnnxModell") is not None)
p.check("Austreibungsklassen gleich (1, 2)", tuple(m.AUSTREIBUNG) == tuple(g.AUSTREIBUNG))


def zufall(rng, n=600):
    aus = np.zeros((16, n), np.float32)
    aus[0], aus[1] = rng.uniform(0, 640, n), rng.uniform(0, 640, n)
    aus[2], aus[3] = rng.uniform(4, 320, n), rng.uniform(4, 320, n)
    aus[4:7] = rng.uniform(0, 1, (3, n)) ** 3
    aus[7:] = rng.uniform(0, 640, (9, n))
    aus[9::3] = rng.uniform(0, 1, (3, n))
    return aus


def letterbox_param(w, h, s=640):
    r = min(s / h, s / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    return (s - nw) // 2, (s - nh) // 2, r


rng = np.random.default_rng(19)
gleich = zwei = 0
for i in range(40):
    aus = zufall(rng)
    w, h = [(2560, 1440), (1280, 720), (640, 640), (1920, 1080), (720, 1280)][i % 5]
    lb = letterbox_param(w, h)
    ref = g.dekodiere_pose(aus, 3, 0.25, 0.7, *lb, w, h)
    gleich += m.dekodiere_pose(aus, 3, 0.25, 0.7, *lb, w, h) == ref
    zwei += [o for o in m.dekodiere_pose(aus, 3, 0.10, 0.7, *lb, w, h) if o["conf"] >= 0.25] == ref
p.check("40 Zufalls-Rohausgaben: Agent == Gates (exakt, gleiche Schwelle)", gleich == 40)
p.check("40 Zufalls-Rohausgaben: Agent ab 0.10 + Filter 0.25 == Gates ab 0.25", zwei == 40)

sys.exit(p.bericht())
