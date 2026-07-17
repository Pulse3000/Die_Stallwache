---
name: modell-training
description: Geführte Prozedur für die Modell-Erstinbetriebnahme der KI-Wache — Silent Mode (Datensammlung) → CVAT-Labeling → Colab-Training → best.pt → Analyse-Modus → Fehlalarm-Nachtraining. Nutzen, sobald die Stallwache-Bridge läuft und Trainingsbilder gesammelt werden können, sowie bei jedem Nachtraining.
---

# KI-Wache: Modell-Erstinbetriebnahme & Nachtraining

Der nächste natürliche Meilenstein des Projekts (`docs/roadmap.md`): Ohne
eigenes Modell läuft der Edge-Agent im Silent Mode; erst `best.pt` schaltet
die Erkennung scharf. Alles hier ist mit 0 € umsetzbar (Colab-Free-GPU,
CVAT kostenlos, offene Datensätze).

## Voraussetzungen prüfen

1. Bridge liefert den Stream: `NEXT_PUBLIC_BRIDGE_URL` gesetzt, RTSP-Restream
   erreichbar (go2rtc Port 8554 bzw. MediaMTX).
2. Edge-Agent läuft im Silent Mode (`modell.pfad` leer in `config.yaml`) —
   sammelt alle 120 s ein Bild nach `./aufnahmen`.
3. Zielumfang: **1–2 Wochen** Bilder, zwingend alle Lichtverhältnisse
   (Tag, Dämmerung, IR-Nacht). Weniger Vielfalt = Nachtblindheit des Modells.

## Phase 1 — Datensatz zusammenstellen

- Eigene `aufnahmen/` sichten; unbrauchbare Frames (leerer Stall, Unschärfe)
  aussortieren, aber einige Leerbilder als Negativbeispiele behalten.
- Vorwissen ergänzen: Open-Source-Datensätze **CVB** (Cattle Visual
  Behaviors) und **CattleEyeView** (Top-Down) herunterladen und beimischen.

## Phase 2 — Labeln mit CVAT (app.cvat.ai, kostenlos)

Pro Kuh: Bounding-Box + Keypoints `Spine_End`, `Tail_Base`, `Tail_Tip`.
Zusätzliche Objektklassen als Boxen: `amniotic_sac` (Fruchtblase),
`calf_legs` (Kälberfüße). Export im **YOLO-Format**.

Ab dem 2. Trainingsdurchgang zusätzlich labeln:
- `kuh_seitenlage` (flach auf der Seite, Beine ausgestreckt) — Grundlage für
  den Festliege-Wächter (`docs/festliege-spezifikation.md`); Material in
  `aufnahmen/seitenlage-kandidaten/`. Brustlage bleibt Klasse `kuh`.
- `kalb_liegend` und `kalb_stehend` — Grundlage für die Voll-Kalbe-Akte
  („Kalb steht seit 04:32", `docs/kalbe-akte-spezifikation.md`); Material in
  `aufnahmen/kalbungen/`.
- Keypoint `spine_mid` (Widerrist/Rückenmitte, Index 3 **anhängen**, Indizes
  0–2 nicht umsortieren) — Grundlage für die Lahmheits-Frühwarnung
  (`docs/lahmheit-spezifikation.md`); Bestand nachlabeln.

Qualitätsregeln: Keypoints auch bei teilverdeckten Kühen setzen (schätzen,
nicht weglassen); `amniotic_sac`/`calf_legs` nur labeln, wenn eindeutig —
diese Klassen lösen Sofort-Alarme aus, Falsch-Labels erzeugen Fehlalarme.

## Phase 3 — Training in Google Colab (Free-GPU)

```python
!pip install ultralytics
from ultralytics import YOLO
modell = YOLO("yolov8n-pose.pt")          # vortrainiert, klein & CPU-tauglich
modell.train(data="stall.yaml", epochs=100, imgsz=640)
# Ergebnis: runs/pose/train/weights/best.pt herunterladen
```

`yolov8n` (nano) bewusst beibehalten, solange der Stall-Rechner nur CPU hat —
1 FPS Analyse genügt fachlich, Kalbeanzeichen entwickeln sich über Minuten.

## Phase 4 — Scharfschalten

1. `best.pt` auf den Stall-Rechner kopieren, Pfad in `config.yaml` unter
   `modell.pfad` eintragen → Agent wechselt automatisch in den Analyse-Modus.
2. Erste 48 h beobachten: Tagesbericht + Telegram-Alben sichten. Zielwert
   < 1 Fehlalarm/Nacht (siehe `docs/metriken.md`).
3. **Jetzt Metriken füllen:** Precision/Recall-Zahlen aus der Praxis in
   `docs/metriken.md` eintragen — vorher stehen dort nur Methodik-Platzhalter.
4. Danach entsperren sich die modellabhängigen Roadmap-Punkte
   (Zwei-Kamera-Brunst-Fusion, Lahmheits-Frühwarnung) — Status in
   `docs/roadmap.md` aktualisieren.

## Phase 5 — Fehlalarm-Nachtraining (wiederkehrend)

Falsch erkannte Bilder (aus den Telegram-Alben) zurück in CVAT als
Negativ-Beispiele („Background") labeln, Datensatz erweitern, erneut
trainieren, `best.pt` austauschen. Kein Schwellenwert-Drehen als Ersatz für
Nachtraining — die Referenzwerte (45°/30 min/20 %, 0.80, IoU 0.15/4 s) sind
fachlich begründet und bleiben stehen (Wächter: Agent `ki-wache`).

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Silent Mode, Bilder sichern, CVAT, Colab | Landwirt/Betreiber (Anleitung: `edge-agent/README.md`) |
| Logik-/Schwellenwert-Treue nach Modellwechsel prüfen | Agent `ki-wache` |
| Build/Smoke vor zugehörigen Repo-Änderungen | Agent `qa-waechter` |
| Metriken & Roadmap fortschreiben | Orchestrator |
