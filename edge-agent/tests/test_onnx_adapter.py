#!/usr/bin/env python3
"""B19-Abnahme (1): Der ONNX-Adapter des Agenten - Dekodierung, Wiring und
Fehlerpfade, ohne Trainingsordner lauffaehig. Nur Kuh-Boxen in den Tracker
(ab tracker_konfidenz_min), Logik ab konfidenz_min, Fruchtblase/Kaelberfuesse
aus jedem Bild und ungetrackt, unsichtbare Keypoints -> kein Winkel,
Ladefehler (auch Probe-Inferenz) -> Silent Mode mit Meldung, Thread-Zahl aus
CPU-Affinitaet und cgroup-Quote. Der Vergleich mit abnahme_gates.py steht in
test_onnx_gates.py, der auf echten Stallbildern in test_onnx_stallbilder.py.
Braucht numpy + OpenCV (sonst 77 = uebersprungen)."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, braucht, lade_main  # noqa: E402

braucht("numpy", "cv2")
import cv2  # noqa: E402
import numpy as np  # noqa: E402

m, _ = lade_main()
p = Pruefer("ONNX-Adapter (B19)")


KP = {"spine_end": 0, "tail_base": 1, "tail_tip": 2}
KL = {"kuh": 0, "amniotic_sac": 1, "calf_legs": 2}


def cfg(**modell):
    return {"modell": {"pfad": "", "keypoints": dict(KP), "klassen": dict(KL),
                       "tracker": "tracker-kuh.yaml", **modell}}


def letterbox_param(w, h, s=640):
    r = min(s / h, s / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    return (s - nw) // 2, (s - nh) // 2, r


# --- 2) Handfaelle (immer): Mehrfach-Label, NMS je Klasse, Schwelle, Letterbox
W, H = 1280, 720                       # r = 0.5, oben = 140, links = 0
links, oben, r = letterbox_param(W, H)
aus = np.zeros((16, 6), np.float32)


def anker(j, cx, cy, bw, bh, s, kp=((0, 0, 0),) * 3):
    aus[0:4, j] = (cx, cy, bw, bh)
    aus[4:7, j] = s
    for i, (x, y, v) in enumerate(kp):
        aus[7 + 3 * i:10 + 3 * i, j] = (x, y, v)


anker(0, 320, 320, 200, 100, (0.90, 0.85, 0.0), ((300, 300, 0.9), (330, 330, 0.8), (360, 300, 0.3)))
anker(1, 322, 320, 200, 100, (0.80, 0.0, 0.0))     # Doppel der Kuh -> NMS
anker(2, 330, 330, 50, 50, (0.10, 0.0, 0.60))      # Kaelberfuesse in der Kuh-Box
anker(3, 500, 500, 60, 60, (0.20, 0.0, 0.0))       # unter 0.25
anker(4, 100, 200, 100, 80, (0.50, 0.30, 0.0))     # Kuh argmax + Fruchtblase 0.30
anker(5, 600, 200, 40, 40, (0.0, 0.0, 0.0))
res = m.dekodiere_pose(aus, 3, 0.25, 0.7, links, oben, r, W, H)
paare = sorted((o["cls"], round(o["conf"], 2)) for o in res)
p.check("Mehrfach-Label: Fruchtblase am Kuh-Anker bleibt erhalten",
        (1, 0.85) in paare and (0, 0.9) in paare)
p.check("Mehrfach-Label: Fruchtblase 0.30 neben Kuh-argmax 0.50", (1, 0.3) in paare and (0, 0.5) in paare)
p.check("NMS je Klasse: Kuh-Doppel unterdrueckt, Kaelberfuesse in der Kuh-Box bleiben",
        (0, 0.8) not in paare and (2, 0.6) in paare)
p.check("Kandidaten unter 0.25 verworfen", (0, 0.2) not in paare and len(res) == 5)
kuh = next(o for o in res if o["cls"] == 0 and round(o["conf"], 2) == 0.9)
soll = (440 / W, 260 / H, 840 / W, 460 / H)
p.check("Letterbox-Rueckrechnung der Box (normiert)",
        all(abs(a - b) < 1e-6 for a, b in zip(kuh["xyxy"], soll)))
p.check("Letterbox-Rueckrechnung der Keypoints",
        abs(kuh["kpts"][0][0] - 600 / W) < 1e-6 and abs(kuh["kpts"][0][1] - 320 / H) < 1e-6
        and abs(kuh["kpts"][2][2] - 0.3) < 1e-6)


# --- 3) Wiring im Agenten (Fake-Modell + Fake-Tracker) ----------------------
class FakeModell:
    def __init__(self, objekte):
        self.objekte = objekte

    def __call__(self, img):
        return self.objekte


class FakeTracker:
    def __init__(self, fehler=False):
        self.aufrufe, self.fehler = [], fehler

    def update(self, boxen, konf, form):
        self.aufrufe.append((list(boxen), list(konf), tuple(form)))
        if self.fehler:
            raise RuntimeError("Tracker kaputt")
        return [10 + i for i in range(len(boxen))]


OBJ = [
    {"cls": 0, "conf": 0.9, "xyxy": (0.1, 0.2, 0.3, 0.4),
     "kpts": [(0.15, 0.25, 0.9), (0.2, 0.25, 0.9), (0.2, 0.35, 0.9)]},
    {"cls": 1, "conf": 0.85, "xyxy": (0.5, 0.5, 0.6, 0.6), "kpts": [(0, 0, 0)] * 3},
    {"cls": 0, "conf": 0.6, "xyxy": (0.6, 0.1, 0.9, 0.5),
     "kpts": [(0.65, 0.2, 0.9), (0.8, 0.2, 0.9), (0.8, 0.4, 0.3)]},   # Schwanzspitze unsichtbar
    {"cls": 2, "conf": 0.4, "xyxy": (0.52, 0.52, 0.55, 0.58), "kpts": [(0, 0, 0)] * 3},
]
bild = np.zeros((H, W, 3), np.uint8)
trk = FakeTracker()
e = m.InferenceEngine(cfg(), tracker=trk, modell=FakeModell(OBJ))
p.check("injiziertes Modell -> aktiv", e.aktiv)
kuehe, objekte = e.analysiere(bild)
p.check("Tracker genau 1x, nur mit den 2 Kuh-Boxen", len(trk.aufrufe) == 1 and len(trk.aufrufe[0][0]) == 2)
p.check("Tracker bekommt Pixel-xyxy + conf + Bildform",
        np.allclose(trk.aufrufe[0][0][0], (128, 144, 384, 288)) and trk.aufrufe[0][1] == [0.9, 0.6]
        and trk.aufrufe[0][2] == (H, W))
p.check("Fruchtblase + Kaelberfuesse ungetrackt als Objekte (Pixel)",
        sorted(o.klasse for o in objekte) == ["amniotic_sac", "calf_legs"]
        and np.allclose(next(o.box for o in objekte if o.klasse == "amniotic_sac"), (640, 360, 768, 432)))
p.check("Track-IDs ueber den Detektionsindex", [k.track_id for k in kuehe] == [10, 11])
p.check("Schwanzwinkel aus Pixel-Keypoints (90 Grad)", abs(kuehe[0].winkel_grad - 90.0) < 1e-6)
p.check("unsichtbare Schwanzspitze (0.3 < 0.5) -> kein Winkel",
        kuehe[1].winkel_grad is None and np.isnan(kuehe[1].keypoints[2]).all())
p.check("alter Ultralytics-Pfad: Nullpunkt fuer unsichtbaren Punkt gab Scheinwinkel > 45 Grad",
        e._schwanzwinkel(np.array([[100.0, 200.0], [300.0, 200.0], [0.0, 0.0]])) > 45)

kuehe, objekte = e.analysiere(bild, defekt=True)
p.check("Defektbild: Tracker NICHT fortgeschrieben", len(trk.aufrufe) == 1)
p.check("Defektbild: Austreibungsobjekte trotzdem da", len(objekte) == 2)
p.check("Defektbild: Kuehe ohne ID (-1)", [k.track_id for k in kuehe] == [-1, -1])

e2 = m.InferenceEngine(cfg(), tracker=FakeTracker(fehler=True), modell=FakeModell(OBJ))
kuehe, objekte = e2.analysiere(bild)
p.check("Tracker-Ausnahme: Austreibung bleibt, Kuehe -1, kein Absturz",
        len(objekte) == 2 and [k.track_id for k in kuehe] == [-1, -1])

trk3 = FakeTracker()
e3 = m.InferenceEngine(cfg(), tracker=trk3, modell=FakeModell([OBJ[1]]))
kuehe, objekte = e3.analysiere(bild)
p.check("Bild ohne Kuh: Tracker nicht aufgerufen (wie Ultralytics 8.3 track)",
        trk3.aufrufe == [] and len(objekte) == 1 and kuehe == [])

e4 = m.InferenceEngine(cfg(), tracker=None, modell=FakeModell(OBJ))
kuehe, objekte = e4.analysiere(bild)
p.check("ohne Tracker: Austreibung aktiv, Kuehe -1", len(objekte) == 2 and all(k.track_id == -1 for k in kuehe))

e5 = m.InferenceEngine(cfg(keypoint_sichtbar_min=0.2), tracker=FakeTracker(), modell=FakeModell(OBJ))
p.check("keypoint_sichtbar_min aus der Konfig", e5.analysiere(bild)[0][1].winkel_grad is not None)

# --- 4) Ladefehler -> Silent Mode mit Meldung (kein Neustart-Schleifen-Absturz)
e = m.InferenceEngine(cfg(pfad="modelle/best.pt"))
p.check(".pt -> nicht aktiv, Fehlertext nennt .onnx", not e.aktiv and e.fehler and ".onnx" in e.fehler)
e = m.InferenceEngine(cfg(pfad="/gibt/es/nicht/best_v1.onnx"))
p.check("fehlende ONNX-Datei -> nicht aktiv, Fehler gemeldet", not e.aktiv and bool(e.fehler))
p.check("ohne Modellpfad: inaktiv ohne Fehler (Silent Mode)", m.InferenceEngine(cfg()).fehler is None)


class FormModell:
    def __init__(self, pfad, **kw):
        self.sess = type("S", (), {"get_outputs": lambda s: [type("O", (), {"shape": [1, 20, 8400]})()]})()

    def __call__(self, img):
        return []


echt = m.OnnxModell
m.OnnxModell = FormModell
try:
    with tempfile.NamedTemporaryFile(suffix=".onnx") as f:
        e = m.InferenceEngine(cfg(pfad=f.name, threads=1), tracker=FakeTracker())
    p.check("Ausgabeform passt nicht zum Label-Vertrag -> Silent Mode + Fehler",
            not e.aktiv and "Label-Vertrag" in (e.fehler or ""))
finally:
    m.OnnxModell = echt


class ProbeKaputt(FormModell):
    def __init__(self, pfad, **kw):
        self.sess = type("S", (), {"get_outputs": lambda s: [type("O", (), {"shape": [1, 16, 8400]})()]})()

    def __call__(self, img):
        raise RuntimeError("InvalidArgument: Got invalid dimensions for input")


m.OnnxModell = ProbeKaputt
try:
    with tempfile.NamedTemporaryFile(suffix=".onnx") as f:
        e = m.InferenceEngine(cfg(pfad=f.name, threads=1), tracker=FakeTracker())
    p.check("Probe-Inferenz scheitert (z. B. nicht-quadratischer Eingang) -> Silent Mode + Fehler",
            not e.aktiv and "laeuft aber nicht" in (e.fehler or "") and e.fehler_schritt)
finally:
    m.OnnxModell = echt


# --- 5) Threads: alle Kerne, die der Prozess bekommt ------------------------
def kerne(dateien):
    with tempfile.TemporaryDirectory() as d:
        for rel, inhalt in dateien.items():
            pf = Path(d, rel)
            pf.parent.mkdir(parents=True, exist_ok=True)
            pf.write_text(inhalt)
        return m.verfuegbare_kerne(d)


try:
    basis = len(os.sched_getaffinity(0))
except AttributeError:
    basis = os.cpu_count() or 1
p.check("cgroup v2 cpus: 1 -> 1 Thread", kerne({"cpu.max": "100000 100000\n"}) == 1)
p.check("cgroup v2 cpus: 1.5 -> 1 (abgerundet, Hitzeschutz)", kerne({"cpu.max": "150000 100000\n"}) == 1)
p.check("cgroup v2 ohne Quote -> alle Kerne", kerne({"cpu.max": "max 100000\n"}) == basis)
p.check("cgroup v1 Quote 2 -> min(2, Kerne)",
        kerne({"cpu/cpu.cfs_quota_us": "200000", "cpu/cpu.cfs_period_us": "100000"}) == min(2, basis))
p.check("cgroup v1 ohne Quote (-1) -> alle Kerne",
        kerne({"cpu/cpu.cfs_quota_us": "-1", "cpu/cpu.cfs_period_us": "100000"}) == basis)
p.check("keine cgroup-Dateien -> alle Kerne", kerne({}) == basis)
p.check("unlesbare Quote -> alle Kerne", kerne({"cpu.max": "kaputt"}) == basis)
with tempfile.TemporaryDirectory() as d:
    Path(d, "system.slice/stallblick.service").mkdir(parents=True)
    Path(d, "system.slice/stallblick.service/cpu.max").write_text("100000 100000\n")
    Path(d, "proc").write_text("0::/system.slice/stallblick.service\n")
    p.check("systemd CPUQuota=100% in der eigenen cgroup -> 1 Thread",
            m.verfuegbare_kerne(d, str(Path(d, "proc"))) == 1)

# --- 6) Zwei Schwellen: Tracker ab 0.10, Logik ab 0.25 -------------------------
rng = np.random.default_rng(1910)
gleich, faelle = 0, 300
for _ in range(faelle):
    n = 400
    roh = np.zeros((16, n), np.float32)
    roh[0], roh[1] = rng.uniform(0, 640, n), rng.uniform(0, 640, n)
    roh[2], roh[3] = rng.uniform(4, 320, n), rng.uniform(4, 320, n)
    roh[4:7] = rng.uniform(0, 1, (3, n)) ** 2
    roh[7:] = rng.uniform(0, 640, (9, n))
    roh[9::3] = rng.uniform(0, 1, (3, n))
    lb = letterbox_param(1280, 720)
    tief = m.dekodiere_pose(roh, 3, 0.10, 0.7, *lb, 1280, 720)
    hoch = m.dekodiere_pose(roh, 3, 0.25, 0.7, *lb, 1280, 720)
    gleich += [o for o in tief if o["conf"] >= 0.25] == hoch
p.check(f"Dekodierung ab 0.10 + Filter >= 0.25 == Dekodierung ab 0.25 ({faelle} Zufallsfaelle)",
        gleich == faelle)

OBJ2 = OBJ + [
    {"cls": 0, "conf": 0.15, "xyxy": (0.3, 0.6, 0.5, 0.9), "kpts": [(0.35, 0.7, 0.9)] * 3},  # schwache Kuh
    {"cls": 1, "conf": 0.20, "xyxy": (0.7, 0.7, 0.8, 0.8), "kpts": [(0, 0, 0)] * 3},          # schwache Blase
]
trk = FakeTracker()
e = m.InferenceEngine(cfg(), tracker=trk, modell=FakeModell(OBJ2))
kuehe, objekte = e.analysiere(bild)
p.check("Tracker bekommt auch die schwache Kuh (0.15 >= tracker_konfidenz_min 0.10)",
        len(trk.aufrufe[0][0]) == 3 and 0.15 in trk.aufrufe[0][1])
p.check("Logik sieht die schwache Kuh nicht (< konfidenz_min 0.25)",
        len(kuehe) == 2 and all(k.box != (384.0, 432.0, 640.0, 648.0) for k in kuehe))
p.check("Fruchtblase 0.20 geht nicht in die Logik (Gate-Schwelle 0.25)",
        sorted(o.konfidenz for o in objekte) == [0.4, 0.85])
p.check("Track-IDs bleiben den richtigen Kuehen zugeordnet", [k.track_id for k in kuehe] == [10, 11])
p.check("tracker_konfidenz_min ueber konfidenz_min wird gekappt",
        m.InferenceEngine(cfg(tracker_konfidenz_min=0.5), tracker=None, modell=FakeModell([])).tracker_konf == 0.25)

# --- 7) Laufzeit-Zustand: Tracker-Fehler, Messbarkeit, Modus ------------------
e2 = m.InferenceEngine(cfg(), tracker=FakeTracker(fehler=True), modell=FakeModell(OBJ))
e2.analysiere(bild)
p.check("Tracker-Laufzeitfehler wird festgehalten (fuer die Meldung)",
        e2.tracker_ok is False and "Tracker kaputt" in (e2.tracker_laufzeitfehler or ""))
e2.kuh_tracker = FakeTracker()
e2.analysiere(bild)
p.check("naechster gelungener Tracker-Schritt -> tracker_ok wieder True", e2.tracker_ok is True)
e2.analysiere(bild, defekt=True)
p.check("Defektbild: Tracker nicht aufgerufen -> tracker_ok None (kein Beleg, kein Waechter-Tick)",
        e2.tracker_ok is None)
e2.modell = FakeModell([OBJ[1]])
e2.analysiere(bild)
p.check("Bild ohne Kuh -> tracker_ok None", e2.tracker_ok is None)
w = m.baue_waechter({"stream": {"totmann_minuten": 5}}, jetzt=0.0)
w["blind"].gemeldet = True
p.check("Modus im Tagesbericht folgt laufenden Waechter-Episoden (blind)",
        e3_modus := m.InferenceEngine(cfg(), tracker=FakeTracker(), modell=FakeModell([])).modus_text(w))
p.check("... Text: 'blind – nur gestreifte Bilder'", e3_modus.startswith("blind – nur gestreifte Bilder"))
e3 = m.InferenceEngine(cfg(), tracker=FakeTracker(), modell=FakeModell(OBJ))
e3.analysiere(bild)
e3.analysiere(bild, defekt=True)
p.check("Tagesbericht: Schwanzwinkel messbar 1 von 2 (Defektbild zaehlt nicht)",
        e3.tagesbericht() == "Schwanzwinkel messbar: 50 % der Kuh-Beobachtungen (1 von 2)"
        and e3.tagesbericht() is None)
p.check("Modus: Analyse / eingeschraenkt / Datensammlung / AUS",
        e3.modus_text() == "Analyse"
        and m.InferenceEngine(cfg(), tracker=None, modell=FakeModell([])).modus_text()
        == "eingeschränkt – nur Fruchtblase/Kälberfüße"
        and m.InferenceEngine(cfg()).modus_text() == "Datensammlung – noch kein Modell, keine Alarme"
        and m.InferenceEngine(cfg(pfad="x.pt")).modus_text().startswith("KI-Wache AUS"))
pt = m.InferenceEngine(cfg(pfad="modelle/best.pt"))
text = m.TEXT_MODELL_AUS.format(kamera="stallwache", grund=pt.fehler_grund,
                                schritt=pt.fehler_schritt, technik=pt.fehler)
p.check("Ladefehler-Text: KEINE Alarme auch bei Fruchtblase, Handgriff genannt",
        "KEINE Alarme – auch nicht bei Fruchtblase oder Kälberfüßen" in text
        and "modell.pfad auf modelle/best_vN.onnx setzen" in text)

sys.exit(p.bericht())
