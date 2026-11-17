#!/usr/bin/env python3
"""B19: KuhTracker mit dem echten Ultralytics-ByteTrack (tracker-kuh.yaml).

Prueft das Wiring gegen die echte Bibliothek: stabile IDs bei wechselnder
Reihenfolge der Detektionen, Zuordnung ueber den Detektionsindex, zweite
ByteTrack-Stufe (schwache Box haelt die ID), Wiederfinden nach 30 s
Verdeckung (track_buffer 90). Braucht ultralytics + lap (im Agent-Image
vorhanden: Ultralytics 8.3.40, lapx), sonst 77 = uebersprungen.
Im Container ausfuehren:
  docker run --rm -v "$PWD":/pruef -w /pruef kuhwatch-stallwache:latest \\
      python tests/test_bytetrack_echt.py      (aus edge-agent/)"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, braucht, lade_main  # noqa: E402

braucht("numpy", "yaml", "lap", "ultralytics")
import ultralytics  # noqa: E402

m, _ = lade_main()
p = Pruefer(f"ByteTrack echt (Ultralytics {ultralytics.__version__})")

AGENT = Path(__file__).resolve().parent.parent
FORM = (720, 1280)
trk = m.KuhTracker(str(AGENT / "tracker-kuh.yaml"))
p.check("tracker-kuh.yaml geladen", trk.pfad.endswith("tracker-kuh.yaml"))
p.check("track_buffer 90 -> 90 Bilder Gedaechtnis (frame_rate 30 wie model.track)",
        trk.gedaechtnis == 90)


def kuh_a(i):
    return (100 + 2 * i, 100, 300 + 2 * i, 250)


def kuh_b(i):
    return (600 - 2 * i, 300, 800 - 2 * i, 450)


ids_a, ids_b = [], []
for i in range(20):
    if i % 2:  # Reihenfolge der Detektionen wechselt
        ib, ia = trk.update([kuh_b(i), kuh_a(i)], [0.85, 0.9], FORM)
    else:
        ia, ib = trk.update([kuh_a(i), kuh_b(i)], [0.9, 0.85], FORM)
    ids_a.append(ia)
    ids_b.append(ib)
p.check("alle Detektionen ab Bild 2 haben eine ID", min(ids_a[1:] + ids_b[1:]) >= 0)
p.check("Kuh A behaelt ihre ID ueber 20 Bilder", len(set(ids_a[1:])) == 1)
p.check("Kuh B behaelt ihre ID ueber 20 Bilder", len(set(ids_b[1:])) == 1)
p.check("A und B verschieden (keine Verwechslung bei vertauschter Reihenfolge)",
        set(ids_a[1:]).isdisjoint(ids_b[1:]))
id_a = ids_a[-1]

(schwach,) = trk.update([kuh_a(20)], [0.3], FORM)
p.check("schwache Detektion 0.3 (zweite ByteTrack-Stufe) behaelt die ID", schwach == id_a)

for _ in range(30):  # Kuh A 30 s verdeckt, nur B sichtbar
    trk.update([kuh_b(20)], [0.9], FORM)
(zurueck,) = trk.update([(140, 100, 340, 250)], [0.9], FORM)
p.check("nach 30 s Verdeckung dieselbe ID (track_buffer 90)", zurueck == id_a)
p.check("leere Eingabe -> leere Liste, kein Tracker-Schritt", trk.update([], [], FORM) == [])

sys.exit(p.bericht())
