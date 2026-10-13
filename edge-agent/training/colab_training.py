# KI-Wache – Training in Google Colab (Laufzeit -> Laufzeittyp -> T4-GPU).
# Zellen einzeln ausfuehren. Voraussetzung: CVAT-Export als datensatz.zip
# (Format "Ultralytics YOLO Pose") und stall.yaml aus diesem Ordner.

# --- Zelle 1: Abhaengigkeiten -------------------------------------------
# !pip install -q ultralytics

# --- Zelle 2: Dateien hochladen -----------------------------------------
# from google.colab import files
# files.upload()            # datensatz.zip und stall.yaml auswaehlen
# !unzip -q datensatz.zip -d datensatz

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
    fliplr=0.5,
)

# --- Zelle 4: Ergebnis pruefen und herunterladen ------------------------
# metrics = modell.val()
# print(metrics.box.map50, metrics.pose.map50)
# from google.colab import files
# files.download("runs/pose/train/weights/best.pt")
