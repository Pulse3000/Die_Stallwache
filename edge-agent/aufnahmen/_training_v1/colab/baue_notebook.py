# -*- coding: utf-8 -*-
"""Erzeugt colab/stallwache_training_v1.ipynb (einmal ausführen; das Notebook ist das Ergebnis)."""
import os

import nbformat as nbf

nb = nbf.v4.new_notebook()
nb.metadata = {"accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
               "kernelspec": {"display_name": "Python 3", "name": "python3"}, "language_info": {"name": "python"}}
Z = []

Z.append(nbf.v4.new_markdown_cell("""# Stallwache – YOLOv8-Pose-Training v1

**Vorher (auf dem Hof-Rechner):** CVAT-Export → `cvat_zu_yolo_pose.py ... --zip` → `datensatz_v1.zip`
in Google Drive nach `MyDrive/stallwache/` hochladen.

**Hier:** Laufzeit → Laufzeittyp ändern → **T4 GPU**, dann *Laufzeit → Alle ausführen*.

Ergebnis in `MyDrive/stallwache/modelle/`: `best_v1.pt`, `best_v1.onnx` (für den Hof-Rechner),
`gates_v1.md`, `MODELLKARTE_v1.md`, Trainingslauf. Modelle werden **nie überschrieben** – für einen
neuen Lauf `VERSION` erhöhen. Direkt nach dem Training liegt eine Sicherung in `stallwache/kandidaten/`.

Die Abnahme-Gates sind **am ONNX-Modell verbindlich** (so läuft es auf dem Hof).

Hinweis B7/B22: Die gelabelten Trainingsbilder liegen nur **vorübergehend** in Drive/Colab. Nach einem
erfolgreichen Lauf löscht das Notebook `datensatz_v1.zip` aus Drive (danach den Drive-Papierkorb leeren),
die Laufsicherung enthält keine Bilder. Videos und der Live-Betrieb bleiben lokal."""))

Z.append(nbf.v4.new_code_cell("""# 1) Konfiguration
import os, sys, json, glob, shutil, zipfile, subprocess, time, datetime

VERSION = "v1"                       # -> best_v1.pt; nie überschreiben, für neue Läufe erhöhen
DATENSATZ_ZIP = "datensatz_v1.zip"   # in DRIVE_ORDNER
DRIVE_ORDNER = "/content/drive/MyDrive/stallwache"
BASIS_MODELL = "yolov8n-pose.pt"     # Zielrechner ohne AVX2/SSE4.1 -> nur n (gemessen 1,87 FPS mit ONNX Runtime)
EPOCHEN, BILDGROESSE, BATCH, GEDULD = 100, 640, 16, 30
ULTRALYTICS_VERSION = "8.4.197"      # mit dieser Version getestet
DATENSATZ_NACH_LAUF_LOESCHEN = True  # B7/B22: keine Frames dauerhaft in Drive
# Farb-Augmentierung moderat: IR-Nachtbilder sind fast monochrom
AUGMENTIERUNG = dict(hsv_h=0.005, hsv_s=0.3, hsv_v=0.3, fliplr=0.5, mosaic=1.0, close_mosaic=10, degrees=0.0)

IN_COLAB = "google.colab" in sys.modules
SMOKE = os.environ.get("STALLWACHE_SMOKE") == "1"     # lokaler Probelauf: CPU, 1 Epoche
if SMOKE:
    DRIVE_ORDNER = os.environ["STALLWACHE_DRIVE"]
    EPOCHEN, BILDGROESSE, BATCH, GEDULD = 1, 320, 4, 1
ARBEIT = "/content" if IN_COLAB else os.environ.get("STALLWACHE_ARBEIT", os.path.abspath("arbeit"))
os.makedirs(ARBEIT, exist_ok=True)
os.chdir(ARBEIT)                     # alle Nebenprodukte (Gewichte-Download, runs/) landen im Arbeitsordner
print("Colab:", IN_COLAB, "| Probelauf:", SMOKE, "| Arbeitsordner:", ARBEIT)"""))

Z.append(nbf.v4.new_code_cell("""# 2) Umgebung: Ultralytics installieren, Drive verbinden, GPU prüfen
if IN_COLAB:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", f"ultralytics=={ULTRALYTICS_VERSION}",
                    "onnx", "onnxslim", "onnxruntime"], check=True)
    from google.colab import drive
    drive.mount("/content/drive")
import torch, ultralytics
GPU = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "keine (CPU)"
GERAET = 0 if torch.cuda.is_available() else "cpu"
print("Ultralytics", ultralytics.__version__, "| PyTorch", torch.__version__, "| GPU:", GPU)
if IN_COLAB and not torch.cuda.is_available():
    raise SystemExit("Keine GPU aktiv: Laufzeit -> Laufzeittyp ändern -> T4 GPU, dann neu starten.")
if ultralytics.__version__ != ULTRALYTICS_VERSION:
    print(f"WARNUNG: getestet mit {ULTRALYTICS_VERSION}, installiert ist {ultralytics.__version__}")"""))

Z.append(nbf.v4.new_code_cell("""# 3) Versionsschutz, Datensatz entpacken, Beilagen prüfen (alles VOR dem Training)
MODELLE = os.path.join(DRIVE_ORDNER, "modelle")
os.makedirs(MODELLE, exist_ok=True)
ZIELE = {n: os.path.join(MODELLE, n) for n in (f"best_{VERSION}.pt", f"best_{VERSION}.onnx", f"gates_{VERSION}.json",
                                                 f"gates_{VERSION}.md", f"MODELLKARTE_{VERSION}.md", f"lauf_{VERSION}")}
belegt = [n for n, p in ZIELE.items() if os.path.exists(p)]
if belegt:
    raise SystemExit(f"{belegt} existiert schon in {MODELLE}. VERSION erhöhen – Modelle werden nie überschrieben.")

zpfad = os.path.join(DRIVE_ORDNER, DATENSATZ_ZIP)
if not os.path.exists(zpfad):
    raise SystemExit(f"Datensatz fehlt: {zpfad}")
with zipfile.ZipFile(zpfad) as zf:
    zf.extractall(ARBEIT)
kandidaten = glob.glob(os.path.join(ARBEIT, "*", "data.yaml"))
stamm = os.path.splitext(DATENSATZ_ZIP)[0]
kandidaten = [k for k in kandidaten if os.path.basename(os.path.dirname(k)) == stamm] or kandidaten
assert len(kandidaten) == 1, f"data.yaml nicht eindeutig: {kandidaten}"
DATA_YAML = kandidaten[0]
DS = os.path.dirname(DATA_YAML)
for beilage in ("abnahme_gates.py", "bildqualitaet.py"):
    if not os.path.exists(os.path.join(DS, "werkzeuge", beilage)):
        raise SystemExit(f"Beilage {beilage} fehlt im Datensatz-ZIP — Konverter ohne --beilage-Änderung neu laufen lassen.")
sys.path.insert(0, os.path.join(DS, "werkzeuge"))
import abnahme_gates as gates
print(open(os.path.join(DS, "konvertierung_bericht.md"), encoding="utf-8").read()[:4000])"""))

Z.append(nbf.v4.new_code_cell("""# 4) Datensatz prüfen (Bild/Label-Paare, Split nach Stalltagen, Keypoint-Format)
KONVERTIERUNG = json.load(open(os.path.join(DS, "konvertierung_bericht.json"), encoding="utf-8"))
for s in ("train", "val"):
    bilder = sorted(glob.glob(os.path.join(DS, "images", s, "*.jpg")))
    labels = sorted(glob.glob(os.path.join(DS, "labels", s, "*.txt")))
    assert len(bilder) == len(labels) > 0, f"{s}: {len(bilder)} Bilder, {len(labels)} Labels"
    for lp in labels:
        for zeile in open(lp):
            assert len(zeile.split()) == 5 + 3 * 3, f"falsches Zeilenformat in {lp}"
    print(f"{s}: {len(bilder)} Bilder")
TAGE = KONVERTIERUNG["stalltage"]
assert not set(TAGE["train"]) & set(TAGE["val"]), "Datenleck: gleicher Stalltag in train und val"
for s in TAGE:
    print(f"Stalltage {s}: {TAGE[s][0]} … {TAGE[s][-1]} ({len(TAGE[s])})")"""))

Z.append(nbf.v4.new_code_cell("""# 5) Training + sofortige Sicherung des Kandidaten in Drive
from ultralytics import YOLO
modell = YOLO(BASIS_MODELL)
modell.train(data=DATA_YAML, epochs=EPOCHEN, imgsz=BILDGROESSE, batch=BATCH, patience=GEDULD, seed=0,
             deterministic=True, project=os.path.join(ARBEIT, "laeufe"), name=VERSION, exist_ok=True,
             device=GERAET, workers=0 if SMOKE else 2, plots=True, **AUGMENTIERUNG)
LAUF = str(modell.trainer.save_dir)
BEST = os.path.join(LAUF, "weights", "best.pt")
KANDIDAT = os.path.join(DRIVE_ORDNER, "kandidaten", f"{VERSION}_{time.strftime('%Y%m%d-%H%M%S')}")
os.makedirs(KANDIDAT)
for d in ("weights/best.pt", "weights/last.pt", "results.csv", "args.yaml"):
    if os.path.exists(os.path.join(LAUF, d)):
        shutil.copyfile(os.path.join(LAUF, d), os.path.join(KANDIDAT, os.path.basename(d)))
print("Lauf:", LAUF, "| Sicherung:", KANDIDAT)"""))

Z.append(nbf.v4.new_code_cell("""# 6) Validierung (Val-Set = komplette Stalltage, nie im Training gesehen)
m = YOLO(BEST)
met = m.val(data=DATA_YAML, imgsz=BILDGROESSE, split="val", plots=False, verbose=False, device=GERAET,
            project=os.path.join(ARBEIT, "laeufe"), name=f"{VERSION}_val", exist_ok=True)
KENNZAHLEN = {"box_mAP50": float(met.box.map50), "box_mAP50-95": float(met.box.map),
              "pose_mAP50": float(met.pose.map50), "pose_mAP50-95": float(met.pose.map)}
for i, name in m.names.items():
    if i < len(met.box.maps):
        KENNZAHLEN[f"box_mAP50-95_{name}"] = float(met.box.maps[i])
print(json.dumps(KENNZAHLEN, indent=2))"""))

Z.append(nbf.v4.new_code_cell("""# 7) ONNX-Export und Abnahme-Gates A, A2, B — verbindlich am ONNX-Modell (C und D laufen auf dem Hof-Rechner)
ONNX = YOLO(BEST).export(format="onnx", imgsz=BILDGROESSE, simplify=True, dynamic=False)
GATES = gates.pruefe_val(ONNX, DATA_YAML, bildgroesse=BILDGROESSE)
print(gates.bericht_md(GATES))"""))

Z.append(nbf.v4.new_code_cell("""# 8) Sicherung in Drive — exklusiv anlegen, nie überschreiben
def neu_kopieren(quelle, ziel):
    with open(quelle, "rb") as q, open(ziel, "xb") as z:     # "x": bricht ab, falls inzwischen vorhanden
        shutil.copyfileobj(q, z)

def neu_schreiben(ziel, text):
    with open(ziel, "x", encoding="utf-8") as fh:
        fh.write(text)

neu_kopieren(BEST, ZIELE[f"best_{VERSION}.pt"])
neu_kopieren(ONNX, ZIELE[f"best_{VERSION}.onnx"])
neu_schreiben(ZIELE[f"gates_{VERSION}.json"], json.dumps(GATES, ensure_ascii=False, indent=2))
neu_schreiben(ZIELE[f"gates_{VERSION}.md"], gates.bericht_md(GATES))
shutil.copytree(LAUF, ZIELE[f"lauf_{VERSION}"],               # bricht ab, wenn der Ordner existiert
                ignore=shutil.ignore_patterns("*.jpg"))         # Mosaike enthalten Stallbilder (B7)
print("Gesichert in", MODELLE, ":", sorted(os.listdir(MODELLE)))"""))

Z.append(nbf.v4.new_code_cell("""# 9) Modellkarte
TRAINING = {"datum": datetime.date.today().isoformat(), "basis": BASIS_MODELL, "bildgroesse": BILDGROESSE,
            "epochen": EPOCHEN, "ultralytics": ultralytics.__version__, "torch": torch.__version__, "gpu": GPU,
            "tage": {s: f"{TAGE[s][0]}–{TAGE[s][-1]} ({len(TAGE[s])} Stalltage)" for s in TAGE}}
karte = gates.modellkarte(VERSION, GATES, KONVERTIERUNG, KENNZAHLEN, TRAINING)
neu_schreiben(ZIELE[f"MODELLKARTE_{VERSION}.md"], karte)
print(karte)"""))

Z.append(nbf.v4.new_code_cell("""# 10) Aufräumen (B7/B22): Datensatz nach erfolgreichem Lauf aus Drive entfernen
if DATENSATZ_NACH_LAUF_LOESCHEN and os.path.exists(zpfad):
    os.remove(zpfad)
    print(f"{DATENSATZ_ZIP} aus Drive entfernt. Bitte den Drive-Papierkorb leeren (sonst bleibt die Datei 30 Tage).")
bilder_in_drive = [p for p in glob.glob(os.path.join(DRIVE_ORDNER, "**", "*.jpg"), recursive=True)]
print("Bilder in Drive/stallwache:", len(bilder_in_drive))
if IN_COLAB:
    drive.flush_and_unmount()          # sicherstellen, dass Löschung und Modellkopien in Drive ankommen
    print("Drive synchronisiert und getrennt. Fertig.")"""))

Z.append(nbf.v4.new_markdown_cell("""## Nächste Schritte (auf dem Hof-Rechner)

1. `best_v1.onnx` aus Drive nach `_training_v1/modelle/` kopieren.
2. Gate C + D: einen kompletten, ereignislosen Val-Stalltag durchspielen (fortsetzbar, je Aufruf ≤ 160 s):
   `python3 abnahme_gates.py tag --modell ../modelle/best_v1.onnx --bilder-ordner ../.. --stalltag 2026-10-18 --bericht ../datensatz_v1/konvertierung_bericht.json --jsonl ../modelle/tag_2026-10-18.jsonl --zeitlimit 160`
   (wiederholen, bis "vollstaendig": true). Die JSONL zusätzlich in den Agenten-Replay geben (Kalbeverdacht-Fehlalarme).
3. Der Agent muss das ONNX-Modell genauso dekodieren wie die Gates (`dekodiere_pose` in `abnahme_gates.py`:
   quadratische Letterbox, Austreibungsklassen mit Mehrfach-Label) – sonst gilt Gate A nicht für den Betrieb.
   Prüfsumme in `gates_v1.md` mit `sha256sum best_v1.onnx` vergleichen.
4. Erst wenn alle Gates **BESTANDEN** sind: `modell.pfad` setzen, Info-Ereignis „Modell v1 aktiv“, Eintrag im Tagesbericht.
   Ohne echte Geburt im Val-Set bleibt die Austreibungs-Logik im Silent Mode (Gate A OFFEN)."""))

nb.cells = Z
ziel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stallwache_training_v1.ipynb")
nbf.validate(nb)
with open(ziel, "w", encoding="utf-8") as fh:
    nbf.write(nb, fh)
print("geschrieben:", ziel)
