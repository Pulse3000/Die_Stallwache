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
| `track_high_thresh` | 0.4 | 0.5 (bis 8.3.2x) · 0.25 (ab 8.3.30) | Sichere Boxen. Gegenüber dem alten Default abgesenkt (IR-Nacht), gegenüber dem neuen **angehoben** – an IR-Nacht-Clips prüfen |
| `track_low_thresh` | 0.05 | 0.1 | ByteTracks Kernidee: auch schwache Boxen zuordnen statt verwerfen. Wirksam höchstens 0.1, weil `model.track()` ohne `conf` alles darunter vorher verwirft |
| `new_track_thresh` | 0.5 | 0.6 (bis 8.3.2x) · 0.25 (ab 8.3.30) | Schwelle für neue IDs (gegen Geister-IDs durch Rauschen). Eine Kuh, die nur darunter erkannt wird, bekommt nie eine ID und fehlt in der Analyse |

Die Defaults hängen an der Ultralytics-Version (`requirements.txt` erlaubt
`>=8.2,<9`). **Im Agent-Image ist 8.3.40 fest eingestellt** (`Dockerfile`),
dort gelten die Defaults 0.25 / 0.1 / 0.25 / 30 / 0.8.

**Zählweise von `track_buffer`:** Ultralytics ruft den Tracker nur für Bilder
mit mindestens einer Erkennung auf (`ultralytics/trackers/track.py`). In
Bildern ganz ohne Erkennung altern verlorene Tracks nicht. Steht in der
Abkalbebox nur eine Kuh und verschwindet sie ganz, bleibt ihre ID also über
beliebig lange Pausen erhalten. Mit weiteren Kühen im Bild gilt: 90 Bilder ≈
90 s.

## Vor dem Modell: Simulation mit dem echten Tracker

`edge-agent/training/tracker_simulation.py` füttert den Ultralytics-
`BYTETracker` mit erfundenen Erkennungen bei 1 FPS und vergleicht beliebige
`tracker-*.yaml`. Szenarien: Verdeckung, zwei Kühe gehen aneinander vorbei,
schwache Erkennung nachts, Einzelbild-Rauschen, dauerhafte Fehlerkennung
(z. B. ein Heuballen):

```bash
cd edge-agent/training
python3 tracker_simulation.py ../tracker-kuh.yaml bytetrack.yaml
```

Ergebnis mit Ultralytics 8.3.40 (25.10.2026, `kuh_03` = tracker-kuh mit
`track_high_thresh`/`new_track_thresh` 0.3):

| Szenario | tracker-kuh | kuh_03 | Default |
|---|---|---|---|
| Verdeckung 45–85 s | ID bleibt | ID bleibt | neue ID |
| Verdeckung ≥ 100 s | neue ID | neue ID | neue ID |
| Vorbeigehen 10 / 30 px/s | kein Wechsel | kein Wechsel | kein Wechsel |
| Kuh erscheint nachts neu, conf 0.3 bzw. 0.45 | **0 % mit ID** | 100 % | 100 % |
| Kuh tagsüber getrackt, nachts conf 0.3 | 100 %, 0 Wechsel | 100 % | 100 % |
| Einzelbild-Rauschen (5 % der Bilder) | 0 Geister-IDs | 0 | 0 |
| Dauer-Fehlerkennung conf 0.3 / 0.45 | keine ID | **Geister-ID** | **Geister-ID** |

Die Simulation ersetzt die Messung am Stall nicht, zeigt aber, was eine
Einstellung grundsätzlich tut.

## Verifikation (auf dem Stall-Rechner, mit Modell)

Ziel: **< 1 ID-Wechsel pro Kuh in 10 Minuten** Testmaterial, geprüft je
Lichtverhältnis (Tag UND IR-Nacht), **und** keine Kuh dauerhaft ohne ID.

1. 10-Minuten-Clips aufnehmen, 1 FPS wie im Betrieb, Tag und Nacht:
   `ffmpeg -i rtsp://127.0.0.1:8554/stallwache -t 600 -r 1 nacht.mp4`
2. Messen (`edge-agent/training/tracking_pruefung.py`). Das Modell rechnet
   den Clip nur einmal, die Erkennungen landen in `nacht.erkennungen.json`:

   ```bash
   cd edge-agent/training
   python3 tracking_pruefung.py nacht.mp4 --modell best.pt \
       --tracker ../tracker-kuh.yaml bytetrack.yaml
   # weitere Variante ohne neue Inferenz:
   python3 tracking_pruefung.py nacht.mp4 --tracker variante.yaml
   ```

3. Die Tabelle nennt je Einstellung: geschätzte Kühe, IDs, ID-Wechsel je Kuh
   und 10 min (✓/✗), Erkennungen ohne ID je Konfidenzband, die Bildrate des
   Rechners. Ein **Achtung**-Hinweis kommt, wenn mehr als 5 % der
   Erkennungen ab conf 0.25 keine ID bekamen. Diese Kühe fehlen in der
   Auswertung, dann trügt auch ein „0 Wechsel ✓“.
4. Nach jeder Änderung an `tracker-kuh.yaml` neu messen, immer nur EINEN
   Wert drehen. Die Tabelle gehört in die Modellkarte.

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
  (Objekt-Override ohne ID-Bezug, Recall 100 % bleibt): Der Agent liest
  Fruchtblase/Kälberfüße **vor** dem Tracker
  (`InferenceEngine._merke_objekte`). Ultralytics kürzt die Ergebnisse
  nach dem Tracking auf bestätigte Tracks – ohne diesen Abgriff ginge das
  erste Bild jeder Erkennung verloren und flackernde Erkennungen nie durch.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Clips aufnehmen, Messung ausführen | Landwirt/Betreiber |
| Werte interpretieren, tracker-kuh.yaml anpassen | Orchestrator (dieser Skill) |
| Prüfen, dass Regel-Schwellen unangetastet bleiben | Agent `ki-wache` |
