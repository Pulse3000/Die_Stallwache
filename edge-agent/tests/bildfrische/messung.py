#!/usr/bin/env python3
"""Misst das Alter jedes analysierten Bilds am echten Stream (Teststrecke).

Quelle: sender.py (Sendezeit als Binaercode im Bild). Modi:

  agent   StreamHandler aus edge-agent/main.py, wie die Hauptschleife ihn nutzt
  puffer  das fruehere Lesemuster (VideoCapture.read() im Takt) zum Vergleich

Beispiele:
  python3 messung.py agent  --sekunden 240
  python3 messung.py puffer --sekunden 240
  python3 messung.py agent  --sekunden 120 --bremse 0.06   # zu langsamer Rechner

Ausgabe: je Abruf Laufzeit und Bildalter, am Ende eine Zusammenfassung.
"""

import argparse
import importlib.util
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uhr import bildalter_s, sendezeit_ms  # noqa: E402

MAIN_PY = Path(__file__).resolve().parents[2] / "main.py"

a = argparse.ArgumentParser()
a.add_argument("modus", choices=("agent", "puffer"))
a.add_argument("--url", default="rtsp://127.0.0.1:8554/stall")
a.add_argument("--sekunden", type=float, default=240)
a.add_argument("--takt", type=float, default=1.0, help="Abrufe pro Sekunde (ziel_fps)")
a.add_argument("--inferenz", type=float, default=0.4, help="simulierte Rechenzeit je Bild (s)")
a.add_argument("--bremse", type=float, default=0.0,
               help="zusaetzliche Sekunden je grab() (langsamer Rechner)")
arg = a.parse_args()

import cv2  # noqa: E402

t0 = time.time()
messung: list[tuple[float, float | None, int | None]] = []


def notiere(frame) -> None:
    alter = bildalter_s(frame)
    gesendet = sendezeit_ms(frame)
    messung.append((time.time() - t0, alter, gesendet))
    print(f"{time.time() - t0:7.1f}s  alter={'-' if alter is None else f'{alter:.2f}'}", flush=True)


if arg.modus == "puffer":
    cap = cv2.VideoCapture(arg.url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # wirkt beim FFmpeg-Backend nicht
    while time.time() - t0 < arg.sekunden:
        ok, frame = cap.read()
        if not ok:
            time.sleep(5)
            cap = cv2.VideoCapture(arg.url)
            continue
        notiere(frame)
        time.sleep(max(0.0, 1 / arg.takt))
else:
    spec = importlib.util.spec_from_file_location("stall_main", MAIN_PY)
    m = importlib.util.module_from_spec(spec)
    sys.modules["stall_main"] = m
    spec.loader.exec_module(m)
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if arg.bremse:
        echt = m.oeffne_capture

        class Gebremst:
            def __init__(self, cap):
                self._cap = cap

            def grab(self):
                time.sleep(arg.bremse)
                return self._cap.grab()

            def __getattr__(self, name):
                return getattr(self._cap, name)

        m.oeffne_capture = lambda url: Gebremst(echt(url))
    sh = m.StreamHandler({"stream": {"url": arg.url, "ziel_fps": arg.takt}})
    while time.time() - t0 < arg.sekunden:
        frame = sh.naechster_frame()
        if frame is None:
            print(f"{time.time() - t0:7.1f}s  kein Bild", flush=True)
            messung.append((time.time() - t0, None, None))
            continue
        notiere(frame)
        time.sleep(arg.inferenz)

werte = sorted(x[1] for x in messung if x[1] is not None)
gesendet = [x[2] for x in messung if x[2] is not None]
abstand = sorted((b - a_) / 1000 for a_, b in zip(gesendet, gesendet[1:]) if b > a_)
cpu = resource.getrusage(resource.RUSAGE_SELF)
cpu_s = cpu.ru_utime + cpu.ru_stime
print("\n=== Zusammenfassung", arg.modus, "===")
print(f"Abrufe: {len(messung)}, ohne Bild: {sum(1 for x in messung if x[1] is None)}")
if werte:
    print(f"Bildalter: Median {werte[len(werte) // 2]:.2f} s, "
          f"95 % {werte[int(len(werte) * 0.95) - 1]:.2f} s, max {werte[-1]:.2f} s")
if abstand:
    print(f"Abstand aufeinanderfolgender Bilder im Video: Median {abstand[len(abstand) // 2]:.3f} s")
print(f"CPU-Zeit des Prozesses: {cpu_s:.1f} s in {time.time() - t0:.0f} s "
      f"({cpu_s / (time.time() - t0) * 100:.0f} % eines Kerns, inkl. Messung) — {os.cpu_count()} Kerne")
