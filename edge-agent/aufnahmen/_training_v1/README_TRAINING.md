# Trainings-Pipeline v1 – Stand 2026-11-01

Zyklus: **Sammeln → Sichten → Labeln → Trainieren → Abnehmen → Scharfschalten → Beobachten**

| Schritt | Status |
|---|---|
| Sammeln (Silent Mode) | ✅ 31.755 Bilder, 09.10.–01.11. |
| Sichten | ✅ 2.284 Bilder (ausgedünnt, 302 Defektbilder entfernt), Split nach Stalltagen (train 1.941 / val 343) |
| Vorannotation | ✅ 4.151 Kuh-Box-Vorschläge auf 1.179 Bildern (`_cvat_v1/vorannotation/`) |
| Labeln (Stall-Labeler, B18) | ⏳ **du** – `labeler/stall_labeler.html` im Browser öffnen, Anleitung `_cvat_v1/README_CVAT.md` |
| Konvertieren | ✅ Werkzeug fertig, getestet (auch auf dem Hof-Rechner), wartet auf den Export |
| Trainieren (Colab) | ✅ Notebook fertig und im Probelauf ausgeführt, wartet auf Datensatz |
| Abnahme-Gates | ✅ Skript fertig; A/A2/B/B2 in Colab (verbindlich am ONNX-Modell), C/D auf dem Hof-Rechner |

## Ordner `_training_v1/`

```
labeler/stall_labeler.html       Labeling-Werkzeug (eine Datei, Browser, ohne Netz; Export CVAT-1.1-XML)
ENTSCHEIDUNGEN_B18-B22.md        Beschlüsse vom 01.11. (Labeln lokal, ONNX Runtime, Bildqualität, Konventionen, Colab nur vorübergehend)
UEBERGABE_AGENT_B19-B21.md       Spezifikation + Goal-Vertrag für die Agent-Änderungen (Claude Code im Repo)
cvat_labels_stallwache_v2.json   Label-Definition, falls doch CVAT (Box kuh + Skelett kuh_pose)
werkzeuge/
  cvat_zu_yolo_pose.py           CVAT-Export -> YOLO-Pose-Datensatz (+ ZIP für Colab, Gates als Beilage)
  abnahme_gates.py               Gates A, A2, B, B2 (val), C/D (tag, laufzeit); ONNX- und Ultralytics-Backend
  vorannotation.py               Kuh-Box-Vorschläge mit COCO-Detektor (lokal, ONNX Runtime)
  bildqualitaet.py               erkennt Dekodier-Streifen (auch für den Agenten gedacht)
colab/stallwache_training_v1.ipynb   Training, Validierung, ONNX-Export, Gates, Modellkarte
tests/                           73 Tests (inkl. Browser-Tests des Labelers) + Ende-zu-Ende-Probelauf (14 Prüfungen)
modelle/laufzeittest_*           Zufallsgewichte, NUR für die Laufzeitmessung (kein echtes Modell)
```

## Ablauf nach dem Labeln

1. Im Stall-Labeler je Paket **Export** → XML nach `_training_v1/exporte/` (nur geprüfte Bilder zählen).
   Falls doch CVAT: Export „CVAT for images 1.1“ ohne Bilder, nur fertige Aufgaben.
2. Konvertieren (Hof-Rechner, einige Minuten):
   ```bash
   cd ~/Die_Stallwache/edge-agent/aufnahmen/_training_v1/werkzeuge
   python3 cvat_zu_yolo_pose.py --xml ../exporte/*.xml --bilder ../.. \
       --manifest ../../_cvat_v1/manifest.csv --ausgabe ../datensatz_v1 --zip
   ```
   Prüft vor dem Schreiben und bricht bei Fehlern ab (Skelett ohne Box, Aufgabe nur vorannotiert,
   gleicher Stalltag in train und val, fehlende Bilder). Bericht: `datensatz_v1/konvertierung_bericht.md`.
   Bilder werden auf 1280 px verkleinert (Labels sind normiert); Gate-Skripte liegen im ZIP bei.
3. `datensatz_v1.zip` nach Google Drive `MyDrive/stallwache/` hochladen. Das Notebook löscht es nach einem
   erfolgreichen Lauf wieder (B22) – danach den Drive-Papierkorb leeren.
4. `colab/stallwache_training_v1.ipynb` in Colab öffnen → T4-GPU → *Alle ausführen*
   (yolov8n-pose, 640 px, 100 Epochen, moderate Farb-Augmentierung wegen IR). Direkt nach dem Training
   wird der Kandidat nach `stallwache/kandidaten/` gesichert.
5. Ergebnis in Drive `stallwache/modelle/`: `best_v1.pt`, `best_v1.onnx`, `gates_v1.md`, `MODELLKARTE_v1.md`.
   Die Gates A/A2/B/B2 laufen am **ONNX-Modell** (so läuft es auf dem Hof) und sind dort verbindlich.
   Gate B rechnet wie der Agent nur mit Punkten ab Sichtbarkeit 0.5; Gate B2 prüft, dass erhobene Schwänze
   nicht seltener messbar sind als anliegende (höchstens 10 Prozentpunkte Lücke, je n ≥ 30).
6. Gate C + D auf dem Hof-Rechner mit `best_v1.onnx` (je Aufruf ≤ 160 s, fortsetzbar):
   ```bash
   python3 abnahme_gates.py tag --modell ../modelle/best_v1.onnx --bilder-ordner ../.. \
       --stalltag 2026-10-18 --bericht ../datensatz_v1/konvertierung_bericht.json \
       --jsonl ../modelle/tag_2026-10-18.jsonl --zeitlimit 160
   ```
   Nur Val-Stalltage (13., 18., 25., 31.10.) – `--bericht` prüft das. Wiederholen bis `"vollstaendig": true`.
   Ausgewertet wird jedes Bild des Stalltags, auch Defektbilder
   (getrennt ausgewiesen). Die JSONL zusätzlich durch den Agenten-Replay schicken
   (Kalbeverdacht-Fehlalarme brauchen ByteTrack + 30-min-Fenster + Cooldown).
7. Scharfschalten erst, wenn alle Gates **BESTANDEN** sind. Ohne echte Geburt im Val-Set bleibt
   Gate A OFFEN → Austreibungs-Logik bleibt im Silent Mode.

## Heute gemessen (Belege)

**Hof-Rechner (AMD A6-3650, kein SSE4.1/SSE4.2/AVX):**
- PyTorch 2.14 (CPU-Wheel) bricht bei jeder Faltung ab: `RuntimeError: could not create a primitive`
  (oneDNN braucht mind. SSE4.1). Mit `torch.backends.mkldnn.enabled = False` läuft es, aber langsam.
- yolov8n-pose (3 Klassen, 3 Keypoints, 640 px) in der Cowork-VM auf diesem Rechner (2 von 4 Kernen):
  ONNX Runtime **1,87 FPS (Gate D bestanden)**, PyTorch ohne oneDNN **0,86 FPS (nicht bestanden)**,
  OpenCV-DNN ~1,1 FPS (COCO-Pose). → Der Agent sollte das Modell als **ONNX mit ONNX Runtime** laden
  (deckt sich mit der Export-Entscheidung „ONNX Runtime als Basis“) und **genau so dekodieren wie die
  Gates**: `OnnxModell`/`dekodiere_pose` in `abnahme_gates.py` (quadratische Letterbox 640, Rand 114,
  Austreibungsklassen mit Mehrfach-Label je Anker). Ultralytics `predict`/`track` wertet nur den
  argmax je Anker aus und fände im Probelauf weniger Austreibungs-Detektionen – dann wäre Gate A zu optimistisch. OpenVINO setzt laut
  Hersteller SSE4.2 voraus und kommt auf diesem Rechner nicht in Frage (nicht getestet).
- Gemessen mit Zufallsgewichten (Rechenaufwand identisch), reine Inferenz. Mit dem echten Modell
  Ende-zu-Ende nachmessen (`abnahme_gates.py laufzeit`, misst Lesen + Qualitätsprüfung + Inferenz).

**Daten:**
- 11,7 % der ausgewählten Bilder (302/2.586), fast nur nachts, haben Dekodier-Streifen (Paketverlust
  im Stream). `bildqualitaet.py` erkennt sie (Schwelle 0.04, an 36 Stichproben geprüft).
  **Empfehlung Agent:** Defektbilder nicht in die Schwanzwinkel-Statistik nehmen, die
  Austreibungs-Erkennung aber trotzdem laufen lassen (nie unterdrücken); Defektquote zählen und bei
  dauerhaft hoher Quote „Bildqualität degradiert“ melden.
- Die Kamera-Ansicht wechselt: bis 19.10. und ab 29.10. vor allem Abkalbe-/Laufbereich, 20.–28.10. vor
  allem Futtertisch, dazu einzelne andere Ansichten. Die Silent-Mode-Dateinamen tragen **keinen
  Kameranamen** (Skill-Vorgabe: `stallwache_…`, `futterwache_…`) – im Agenten nachziehen; die Werkzeuge
  lesen Datum/Uhrzeit auch mit Präfix.
- Dateinamen sind UTC, der Bildstempel zeigt Ortszeit (+2 h bis 25.10., danach +1 h). Split deshalb nach
  **Stalltag** (12:00–12:00 Uhr Ortszeit), damit jede Nacht komplett in einem Split liegt.
- Echte Geburt: keine im Datensatz → `amniotic_sac`/`calf_legs` können noch nicht gelernt werden.
- Prüfbilder der Sichtkontrollen: `probe_vorannotation.jpg` (Vorschläge), `probe_defekt*.jpg` (Defekt-Schwelle),
  `probe_ansichten.jpg` (Kamera-Ansichten).

## Qualitätssicherung

- 73 Tests (Konverter, Gates, Stall-Labeler im echten Browser bis in den Konverter) und ein Ende-zu-Ende-Probelauf mit 14 Prüfungen: synthetische Bilder →
  Konverter → Colab-Notebook im Probelauf-Modus (1 Epoche, CPU) → ONNX-Gates → Modellkarte;
  dazu Versionsschutz, ONNX-Backend gegen Ultralytics (Boxen-IoU 0,96–0,98) und die Gate-Modi.
  Belegt die Mechanik, nicht die Modellqualität.
- Auf dem Hof-Rechner ausgeführt: Vorannotation (alle 2.284 Bilder), Konverter mit den echten
  Vorannotationen (bricht korrekt ab: „Kuh-Boxen, aber kein Skelett“), Laufzeitmessung.
- Unabhängige Prüfung (qa-waechter, fünf Runden), alle Befunde eingearbeitet. Pipeline: Split nach Stalltag, Gates verbindlich am ONNX-Modell (mit SHA-256), Austreibungsklassen
  unabhängig dekodiert, Prüfung je Aufgabe, Versionsschutz exklusiv, Sicherung direkt nach dem Training,
  Defektbilder in Gate C mitgezählt, Vorab-Prüfung von Bildern und Beilagen, Gate C nur auf Val-Stalltagen.
  Paarung Box↔Skelett: liegt ein ungruppiertes Skelett in mehreren Kuh-Boxen, bricht der Konverter mit
  „gruppieren“ ab, statt still zu raten.
  Offen: CVAT-Import der Vorannotation live testen; Val-Set dient auch der Modellauswahl (in der
  Modellkarte ausgewiesen).

```bash
cd _training_v1
python3 -m pytest -q tests/           # braucht numpy, opencv, pytest (Labeler-Test zusätzlich playwright, sonst übersprungen)
python3 tests/smoke_e2e.py            # braucht zusätzlich ultralytics, torch, onnxruntime, nbconvert
```

## Entscheidungen

Am 01.11. getroffen (im Auftrag, `ENTSCHEIDUNGEN_B18-B22.md`): B18 Labeln lokal mit dem Stall-Labeler,
B19 ONNX Runtime im Agenten, B20 Bildqualitäts-Gate, B21 Datensatz-Konventionen, B22 Colab nur vorübergehend
(das Notebook löscht den Datensatz nach dem Lauf aus Drive). Vor der Umsetzung von B19–B21 in
`ENTSCHEIDUNGEN.md` übernehmen und bestätigen, dann Claude-Code-Sitzung im Repo (`UEBERGABE_AGENT_B19-B21.md`).

Weiter offen beim Landwirt: die Vorlagen B15–B17 im Repo und Geburtsaufnahmen um die nächsten Kalbetermine
(ohne sie bleibt Gate A offen).
