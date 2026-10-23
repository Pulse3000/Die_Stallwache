#!/usr/bin/env python3
"""Live-Testquelle: Bilder mit eingebrannter Sendezeit -> ffmpeg -> RTSP.

Jedes Bild traegt in der obersten Zeile 40 Bloecke (je 16 x 16 px) als
Binaercode der Sendezeit in Millisekunden (mod 2^40). messung.py liest sie
aus und kennt so das Alter jedes analysierten Bilds.

  python3 sender.py [rtsp://127.0.0.1:8554/stall] [fps]
"""

import subprocess
import sys
import time

import numpy as np

B, BITS = 16, 40
W, H = 1280, 720
URL = sys.argv[1] if len(sys.argv) > 1 else "rtsp://127.0.0.1:8554/stall"
FPS = int(sys.argv[2]) if len(sys.argv) > 2 else 25

ff = subprocess.Popen(
    ["ffmpeg", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "gray",
     "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
     "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
     "-g", str(FPS * 2), "-pix_fmt", "yuv420p", "-b:v", "2M",
     "-f", "rtsp", "-rtsp_transport", "tcp", URL],
    stdin=subprocess.PIPE,
)
rauschen = np.random.default_rng(0).integers(60, 120, size=(H, W), dtype=np.uint8)
t0 = time.time()
n = 0
while True:
    ms = int(time.time() * 1000) % (1 << BITS)
    bild = rauschen.copy()
    bild[: B + 8, :] = 128
    for i in range(BITS):
        x = 8 + i * (B + 8)
        bild[4 : 4 + B, x : x + B] = 255 if (ms >> i) & 1 else 0
    x = (n * 8) % W  # bewegter Balken -> echte P-Frames
    bild[200:400, x : x + 40] = 230
    ff.stdin.write(bild.tobytes())
    n += 1
    schlaf = t0 + n / FPS - time.time()
    if schlaf > 0:
        time.sleep(schlaf)
