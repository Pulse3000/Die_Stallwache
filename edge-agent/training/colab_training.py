# KI-Wache – Training in Google Colab (Laufzeit -> Laufzeittyp -> T4-GPU).
# Zellen einzeln ausfuehren. Ablauf und Regeln: edge-agent/README.md,
# Abschnitt "Weg zum eigenen Modell".
#
# Hochladen: cvat-export.zip (CVAT-Format "Ultralytics YOLO Pose"),
# stall.yaml, datensatz.py, abnahme.py (training/) sowie main.py und
# freeze_watchdog.py (edge-agent/) – die Abnahme misst den Schwanzwinkel mit
# der Logik des Agenten selbst.

VERSION = 1  # best_v1.pt, best_v2.pt, … – nie ueberschreiben

# --- Zelle 1: Abhaengigkeiten -------------------------------------------
# !pip install -q ultralytics

# --- Zelle 2: Dateien hochladen, nach Stalltagen teilen -----------------
# from google.colab import files
# files.upload()
# !unzip -q cvat-export.zip -d cvat-export
# !python datensatz.py split cvat-export datensatz     # schreibt datensatz/split.json

# --- Zelle 3: Training --------------------------------------------------
from ultralytics import YOLO

# nano-Modell bewusst: der Stall-Rechner analysiert auf CPU mit 1 FPS.
modell = YOLO("yolov8n-pose.pt")
modell.train(
    data="stall.yaml",
    epochs=100,
    imgsz=640,
    patience=20,     # bricht ab, wenn sich 20 Epochen nichts verbessert
    hsv_v=0.5,       # Helligkeits-Augmentierung: Tag/Daemmerung/IR-Nacht
    hsv_s=0.4,       # Saettigung moderat: IR-Bilder sind fast monochrom
    fliplr=0.5,
    name=f"v{VERSION}",
)

# --- Zelle 4: Abnahme-Gates und Download --------------------------------
# import shutil
# shutil.copy(f"runs/pose/v{VERSION}/weights/best.pt", f"best_v{VERSION}.pt")
# !python abnahme.py best_v{VERSION}.pt datensatz --bericht abnahme_v{VERSION}.md
# Exit 0 = Gate 1, 2, 2b bestanden, 1 = verfehlt, 2 = zu wenig Val-Material
# (ohne Geburt: Austreibungs-Logik NICHT scharfschalten). Gate 3 (24 h Fehlalarm-
# Budget) und Gate 4 (--nur-fps auf dem Stall-Rechner) folgen von Hand.
# from google.colab import files
# for datei in (f"best_v{VERSION}.pt", f"abnahme_v{VERSION}.md", "datensatz/split.json"):
#     files.download(datei)
