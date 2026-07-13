---
name: bytetrack-tuning
description: ByteTrack-Tracking der KI-Wache einstellen und verifizieren — stabile Kuh-IDs sind das Fundament jeder zeitbasierten Erkennungsregel (30-Minuten-Fenster, Brunst-Dauer, Cooldown). Nutzen nach dem Scharfschalten des Modells, bei ID-Flackern/ID-Wechseln in den Alarmen oder wenn Kalbeverdachts-Alarme trotz sichtbarer Wehen ausbleiben.
---

# ByteTrack: Kuh-Identität stabil halten

ByteTrack (in Ultralytics integriert) vergibt die Track-IDs („Kuh #42"), auf
denen JEDE zeitbasierte Regel aufbaut: das 30-Minuten-Schwanzwinkel-Fenster,
die ≥-4-s-Brunst-Dauer und der 15-min-Cooldown laufen **pro Kuh-ID**. Ein
ID-Wechsel wirkt darum wie eine neue Kuh — das Kalbeverdachts-Fenster beginnt
bei null, und ein realer Alarm verspätet sich oder bleibt aus.

**Deshalb gilt: ID-Stabilität vor allem anderen.** Fehlende Alarme trotz
sichtbarer Symptome sind bis zum Beweis des Gegenteils ein Tracking-Problem,
kein Schwellenwert-Problem (Schwellen bewacht der Agent `ki-wache`).

## Wo konfiguriert

- `edge-agent/config.yaml` → `modell.tracker: tracker-kuh.yaml`
  (leer = Ultralytics-Default `bytetrack.yaml`)
- Mitgelieferte Kuh-Konfiguration: `edge-agent/tracker-kuh.yaml` —
  jeder Wert dort ist kommentiert (Warum + Default)
- Verdrahtung: `InferenceEngine` (`edge-agent/main.py`), Aufruf
  `modell.track(..., persist=True, tracker=self.tracker)`

## Die Stellschrauben (Wirkung bei 1 FPS)

| Parameter | Kuh-Wert | Default | Wirkung |
| --- | --- | --- | --- |
| `track_buffer` | **90** | 30 | **Wichtigster Wert.** Frames = Sekunden bei 1 FPS: wie lange eine verdeckte Kuh ihre ID behält. Zu klein → neue ID nach jeder Verdeckung; zu groß → tote Tracks fangen fremde Kühe ein |
| `match_thresh` | 0.9 | 0.8 | IoU-Matching-Toleranz. Kühe sind langsam → Boxen überlappen stark → großzügig matchen stabilisiert |
| `track_high_thresh` | 0.4 | 0.5 | Sichere Boxen. Abgesenkt, weil Konfidenzen bei IR-Nacht sinken |
| `track_low_thresh` | 0.05 | 0.1 | ByteTracks Kernidee: auch schwache Boxen zuordnen statt verwerfen |
| `new_track_thresh` | 0.5 | 0.6 | Schwelle für neue IDs (gegen Geister-IDs durch Rauschen) |

## Verifikation (auf dem Stall-Rechner, mit Modell)

Ziel: **< 1 ID-Wechsel pro Kuh in 10 Minuten** Testmaterial, geprüft je
Lichtverhältnis (Tag UND IR-Nacht).

1. 10-Minuten-Clip aufnehmen (z. B. `ffmpeg -i rtsp://BRIDGE:8554/stallwache
   -t 600 -r 1 test-tag.mp4` — 1 FPS wie im Betrieb).
2. Tracking laufen lassen und IDs zählen:

   ```python
   from collections import Counter
   from ultralytics import YOLO
   m = YOLO("best.pt")
   ids = Counter()
   for erg in m.track("test-tag.mp4", tracker="tracker-kuh.yaml",
                      persist=True, stream=True, verbose=False):
       if erg.boxes is not None and erg.boxes.id is not None:
           ids.update(int(i) for i in erg.boxes.id)
   print(f"{len(ids)} verschiedene IDs:", dict(ids))
   ```

3. Bewerten: Anzahl verschiedener IDs ≈ Anzahl Kühe im Clip → gut.
   Deutlich mehr IDs als Kühe → ID-Wechsel, siehe Fehlersuche.
4. Nach jeder Änderung an `tracker-kuh.yaml` neu messen — immer nur EINEN
   Wert drehen.

## Fehlersuche

| Symptom | Ursache | Dreh |
| --- | --- | --- |
| Neue ID nach Verdeckung (Futtertisch, Kuh hinter Kuh) | `track_buffer` zu klein | Buffer erhöhen (90 → 120); Obergrenze: solange keine Fremdübernahmen auftreten |
| IDs flackern zwischen zwei nahen Kühen | Matching zu großzügig | `match_thresh` senken (0.9 → 0.85) |
| Geister-IDs bei Nacht/Rauschen | Neue Tracks zu billig | `new_track_thresh` erhöhen |
| Kuh nachts gar nicht getrackt | Konfidenz unter Schwelle | erst Modell nachtrainieren (IR-Bilder!), dann erst `track_high_thresh` senken — Skill `modell-training` |
| ID-Wechsel genau beim Aufsprung (Brunst) | zwei Boxen verschmelzen | erwartbar; die Brunst-Heuristik arbeitet mit IoU der Boxen, nicht mit IDs der Paarung — nichts drehen |

## Grenzen (ehrlich bleiben)

- IDs sind **sitzungsstabil, keine Tieridentität**: Nach einem Agent-Neustart
  ist „Kuh #42" eine andere Kuh. Deshalb bleibt Stallblick in der Alarmierung
  buchtbasiert (Entscheidung in `docs/wettbewerbsanalyse.md`, Abschnitt 3).
- Zeitbasierte Zustände (Fenster, Cooldowns) überleben den Neustart nicht —
  ein Neustart mitten in der Wehenphase verzögert den Kalbeverdachts-Alarm
  um bis zu ein halbes Fenster. Austreibung ist davon NICHT betroffen
  (Objekt-Override ohne ID-Bezug, Recall 100 % bleibt).

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Clips aufnehmen, Messung ausführen | Landwirt/Betreiber |
| Werte interpretieren, tracker-kuh.yaml anpassen | Orchestrator (dieser Skill) |
| Prüfen, dass Regel-Schwellen unangetastet bleiben | Agent `ki-wache` |
