---
name: modell-training
description: Geführte Prozedur für die Modell-Erstinbetriebnahme der KI-Wache — Silent Mode (Datensammlung) → CVAT-Labeling → Colab-Training → best.pt → Analyse-Modus → Fehlalarm-Nachtraining. Nutzen, sobald der Agent eine Videoquelle hat (Cloud-Quelle ohne Bridge über die Tuya-Kameras ODER Bridge-RTSP) und Trainingsbilder gesammelt werden können, sowie bei jedem Nachtraining.
---

# KI-Wache: Modell-Erstinbetriebnahme & Nachtraining

Der nächste natürliche Meilenstein des Projekts (`docs/roadmap.md`): Ohne
eigenes Modell läuft der Edge-Agent im Silent Mode; erst `best.pt` schaltet
die Erkennung scharf. Alles hier ist mit 0 € umsetzbar (Colab-Free-GPU,
CVAT kostenlos, offene Datensätze).

## Reihenfolge: Brunst-Phase zuerst (Entscheidung 29.10.2026)

Der Betreiber hat entschieden: erst Brunst/Aufsprung, dann Kalbung
(`docs/brunst-zuerst-entscheidung.md`). Für **v1** gilt deshalb:
- Labeln nur `kuh` (Rechteck), Export „Ultralytics YOLO Detection“,
  Datensatz `training/stall-brunst.yaml`, Colab `PHASE = "brunst"`.
- Abnahme `abnahme.py … --phase brunst` (Gate K Kuh-Recall, Gate Ü beide
  Kühe bei Überlappung); dazu Goldstandard A1, 24 h ≤ 1 falscher
  Brunstverdacht, `--nur-fps` am Stall-Rechner.
- `config.yaml`: `klassen: {kuh: 0}`, `freigegeben: [brunst]`. Der Agent
  meldet „NICHT scharf: Austreibung, Kalbeverdacht“, die App sagt kein „OK“
  – das ist gewollt, nicht reparieren.
- Phasen 2–3b unten (Keypoints, Fruchtblase/Kälberfüße, Gates 1/2/2b) gelten
  ab v2 für die Kalbeüberwachung.

## Voraussetzungen prüfen

1. Der Agent hat eine Videoquelle — **einer** der beiden Wege genügt:
   - **Bridge im Stall-LAN:** RTSP-Restream vom Agenten aus erreichbar
     (go2rtc Port 8554 bzw. MediaMTX), ODER
   - **Cloud-Quelle ohne Bridge** (Kameras in der Tuya-Cloud: Futterwache,
     Abkalbebox): in `config.yaml` `stream.app_url` +
     `stream.quelle_api` (z. B. `/api/futterwache/stream`) +
     `stream.app_passwort` setzen, `stream.url` leer lassen — der Agent
     holt und erneuert die kurzlebige HLS-URL selbst.
2. Edge-Agent läuft im Silent Mode (`modell.pfad` leer in `config.yaml`) —
   sammelt alle 120 s ein Bild nach `./aufnahmen`.
3. Zielumfang: **1–2 Wochen** Bilder, zwingend alle Lichtverhältnisse
   (Tag, Dämmerung, IR-Nacht). Weniger Vielfalt = Nachtblindheit des Modells.

## Phase 1 — Datensatz zusammenstellen

- IR-Anteil prüfen: `python3 edge-agent/training/datensatz.py bilanz ./aufnahmen`
  (Beschluss B9: ≥ 1/3 IR-Nacht, sonst weiter sammeln).
- Nahezu identische Frames ausdünnen:
  `python3 edge-agent/training/datensatz.py ausduennen ./aufnahmen ./auswahl`;
  einige Leerbilder als Negativbeispiele behalten, Bilanz auf der Auswahl
  wiederholen.
- Vorwissen ergänzen: Open-Source-Datensätze **CVB** (Cattle Visual
  Behaviors) und **CattleEyeView** (Top-Down) beimischen – nur Beimischung,
  sie landen beim Split automatisch nur im Training.

## Phase 2 — Labeln mit CVAT (app.cvat.ai, kostenlos)

Pro Kuh: Bounding-Box + Keypoints `spine_end`, `tail_base`, `tail_tip`.
Zusätzliche Objektklassen als Boxen: `amniotic_sac` (Fruchtblase),
`calf_legs` (Kälberfüße). Export im Format **„Ultralytics YOLO Pose"**,
danach Split nach Stalltagen:
`python3 edge-agent/training/datensatz.py split ./cvat-export ./datensatz`.

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

Qualitätsregeln: Verdeckte Keypoints als **nicht sichtbar** markieren, nie
schätzen – besonders `tail_tip`. Der Agent wertet nur sichtbare Keypoints
(Konfidenz ≥ 0.5); geschätzte Labels lehren falsche
Geometrie und verfälschen die Winkel-Abnahme. `amniotic_sac`/`calf_legs`
nur labeln, wenn eindeutig – diese Klassen lösen Sofort-Alarme aus,
Falsch-Labels erzeugen Fehlalarme. Keine Klasse „kalbt": das Verhalten
entscheidet der Agent.

## Phase 3 — Training in Google Colab (Free-GPU)

Zellen in `edge-agent/training/colab_training.py` (Split, Training mit
`name=v<N>`, Abnahme, Download). Ergebnis heißt `best_v<N>.pt` – nie
überschreiben, je Version eine Modellkarte aus
`edge-agent/training/MODELLKARTE.vorlage.md`.

`yolov8n` (nano) bewusst beibehalten, solange der Stall-Rechner nur CPU hat —
1 FPS Analyse genügt fachlich, Kalbeanzeichen entwickeln sich über Minuten.

## Phase 3b — Abnahme-Gates (vor jedem Scharfschalten)

`python3 edge-agent/training/abnahme.py best_v<N>.pt datensatz --bericht abnahme_v<N>.md`

| Gate | Kriterium | Prüfung |
| --- | --- | --- |
| 1 | Austreibung Recall = 1.0 bei Konfidenz 0.80 | automatisch; ohne Geburt im Val-Set Exit 2 → Austreibungs-Logik **nicht** scharf |
| 2 | Schwanzwinkel Modell vs. Label < 10° (n ≥ 30) | automatisch, mit der Winkel-Logik des Agenten |
| 2b | erhobener Schwanz (> 45°): alle 3 Keypoints sichtbar in ≥ 90 % (n ≥ 10) | automatisch; sonst unterdrückt der Agent Kalbeverdacht still (Befund `ki-wache`) |
| 3 | 24 h ereignislos: 0 Austreibung, ≤ 1 Kalbeverdacht | von Hand: Aufnahme **mit 1 FPS** (`ffmpeg -i rtsp://… -r 1 nacht.mp4`), `stream.url` auf die Datei, Agent im Analyse-Modus. Der Agent liest ein Videobild je Sekunde Echtzeit – nur bei 1-FPS-Material entspricht das Fenster 30 min Stallzeit; 24 h Material laufen 24 h |
| 4 | ≥ 1 FPS auf der Zielhardware | `abnahme.py … --nur-fps` auf dem Stall-Rechner |

## Phase 4 — Scharfschalten

1. `best_v<N>.pt` auf den Stall-Rechner kopieren, Pfad in `config.yaml` unter
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
