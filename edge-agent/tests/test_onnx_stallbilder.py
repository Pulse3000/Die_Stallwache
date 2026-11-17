#!/usr/bin/env python3
"""B19-Abnahme (3), vorlaeufig: echtes ONNX auf echten Stallbildern - der
Agent (InferenceEngine mit zwei Schwellen) liefert dieselben Objekte wie
abnahme_gates.OnnxModell. Mit dem Laufzeittest-Modell (Zufallsgewichte,
Scores < 0.005) wird mit sehr kleinen Schwellen verglichen; verbindlich wird
die Abnahme mit best_v1.onnx. Braucht numpy, OpenCV, onnxruntime, die Gates,
das ONNX und Stallbilder (Hof-Rechner); sonst 77 = uebersprungen.
Pfade ueberschreibbar mit STALLWACHE_GATES / STALLWACHE_ONNX."""

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import UEBERSPRUNGEN, Pruefer, braucht, lade_main  # noqa: E402

braucht("numpy", "cv2", "onnxruntime")
import cv2  # noqa: E402

AGENT = Path(__file__).resolve().parent.parent
TRAINING = AGENT / "aufnahmen" / "_training_v1"
GATES = Path(os.environ.get("STALLWACHE_GATES", TRAINING / "werkzeuge" / "abnahme_gates.py"))
ONNX = Path(os.environ.get("STALLWACHE_ONNX", TRAINING / "modelle" / "laufzeittest_yolov8n-pose_3kpt_640.onnx"))
fehlt = [str(x) for x in (GATES, ONNX) if not x.is_file()]
alle = sorted((AGENT / "aufnahmen").glob("*.jpg")) if (AGENT / "aufnahmen").is_dir() else []
if fehlt or not alle:
    print("UEBERSPRUNGEN: " + (", ".join(fehlt) + " fehlt" if fehlt else "keine Stallbilder in aufnahmen/"))
    sys.exit(UEBERSPRUNGEN)

m, _ = lade_main()
p = Pruefer("ONNX auf Stallbildern: Agent == Gates (B19)")
spec = importlib.util.spec_from_file_location("abnahme_gates_ref", GATES)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

KL = {"kuh": 0, "amniotic_sac": 1, "calf_legs": 2}
bilder = alle[:: max(1, len(alle) // 3)][:3]
p.check("mindestens 3 Stallbilder ausgewaehlt", len(bilder) == 3)


class FakeTracker:
    def update(self, boxen, konf, form):
        return list(range(1, len(boxen) + 1))


ref = g.OnnxModell(str(ONNX), threads=1, konf=0.002)
cfg = {"modell": {"pfad": str(ONNX), "threads": 1, "konfidenz_min": 0.002, "tracker_konfidenz_min": 0.001,
                  "keypoints": {"spine_end": 0, "tail_base": 1, "tail_tip": 2}, "klassen": dict(KL)}}
e = m.InferenceEngine(cfg, tracker=FakeTracker())
p.check("echtes ONNX geladen (1 Thread, Probe-Inferenz bestanden)", e.aktiv and e.threads == 1)
for b in bilder:
    img = cv2.imread(str(b))
    erwartet = ref(img)
    roh = [o for o in e.modell(img) if o["conf"] >= 0.002]
    kuehe, objekte = e.analysiere(img)
    aus_ref = sorted((o["cls"], round(o["conf"], 6)) for o in erwartet if o["cls"] in (1, 2))
    aus_agent = sorted((KL[o.klasse], round(o.konfidenz, 6)) for o in objekte)
    p.check(f"{b.name}: {len(erwartet)} Objekte identisch, Austreibungsobjekte vollstaendig",
            len(erwartet) > 20 and roh == erwartet and aus_ref == aus_agent
            and len(kuehe) == sum(o["cls"] == 0 for o in erwartet))

sys.exit(p.bericht())
