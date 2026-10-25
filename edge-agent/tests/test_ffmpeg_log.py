#!/usr/bin/env python3
"""Logiktest: FFmpeg-Decodermeldungen fluten das Log nicht.

Manche Kameras haengen Zusatzdaten an jedes Bild an, und der h264-Decoder
meldet „SEI type … truncated" auf Fehlerstufe, im Stall mehrmals pro
Sekunde. main.py setzt deshalb OPENCV_FFMPEG_LOGLEVEL=8 (nur „fatal"),
bevor cv2 geladen wird. Ein Wert aus der Umgebung hat Vorrang.
Gegenprobe am echten OpenCV 4.10: 20 Decodermeldungen ohne die Einstellung,
0 mit ihr, gleich viele Bilder gelesen.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import MAIN_PY, Pruefer, lade_main  # noqa: E402

p = Pruefer("FFmpeg-Log")

# --- 1. Gesetzt, bevor cv2 importiert wird ---------------------------------
quelle = MAIN_PY.read_text(encoding="utf-8")
setzen = quelle.find('os.environ.setdefault("OPENCV_FFMPEG_LOGLEVEL", "8")')
import_cv2 = quelle.find("\nimport cv2")
p.check("1: Einstellung steht in main.py", setzen >= 0)
p.check("1: vor dem ersten 'import cv2'", 0 <= setzen < import_cv2)

# --- 2. Ohne Vorgabe: 8 ------------------------------------------------------
os.environ.pop("OPENCV_FFMPEG_LOGLEVEL", None)
lade_main()
p.check("2: ohne Vorgabe -> 8 (nur fatal)", os.environ.get("OPENCV_FFMPEG_LOGLEVEL") == "8")

# --- 3. Vorgabe aus der Umgebung bleibt (Fehlersuche) -----------------------
skript = (
    "import sys; sys.path.insert(0, %r); from hilfe import lade_main; "
    "lade_main(); import os; print(os.environ.get('OPENCV_FFMPEG_LOGLEVEL'))"
    % str(Path(__file__).resolve().parent)
)
umgebung = dict(os.environ, OPENCV_FFMPEG_LOGLEVEL="16")
aus = subprocess.run([sys.executable, "-c", skript], env=umgebung,
                     capture_output=True, text=True, timeout=60)
p.check("3: Vorgabe 16 bleibt 16", aus.stdout.strip().splitlines()[-1:] == ["16"])

sys.exit(p.bericht())
