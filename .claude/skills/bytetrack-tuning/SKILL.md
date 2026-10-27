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
beliebig lange Pausen erhalten. Sieht der Tracker in der Zeit andere
Erkennungen, gilt 90 Bilder ≈ 90 s. Das sind weitere Kühe, aber auch
Fruchtblase, Kälberfüße und Fehlerkennungen: Der Agent gibt alle drei
Klassen in denselben Tracker.

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
| Kuh erscheint nachts neu, conf 0.3 bzw. 0.45 (konstant) | **0 % mit ID** | 100 % | 100 % |
| Kuh erscheint nachts neu, conf 0.35 ± 0.08 | 98 % | 100 % | 100 % |
| Kuh erscheint nachts neu, conf 0.45 ± 0.08 | 100 % | 100 % | 100 % |
| … conf 0.30 ± 0.08, 2 % der Bilder ohne Erkennung | **54 %** | 96 % | 97 % |
| Kuh tagsüber getrackt, nachts conf 0.3 | 100 %, 0 Wechsel | 100 % | 100 % |
| Einzelbild-Rauschen (5 % der Bilder) | 0 Geister-IDs | 0 | 0 |
| Dauer-Fehlerkennung conf 0.3 / 0.45 | keine ID | **Geister-ID** | **Geister-ID** |

(± = Standardabweichung der Konfidenz von Bild zu Bild, Mittel über 4
Läufe à 1 h.)

Die Zeilen mit konstanter Konfidenz sind der Grenzfall. Schwankt die
Konfidenz von Bild zu Bild, bekommt eine Kuh mit Mittel 0.45 auch mit
tracker-kuh nach wenigen Sekunden eine Nummer, mit 0.35 nach gut einer
Minute. Ein Heuballen mit gleicher Verteilung bekommt sie ebenso.
Entscheidend ist, ob einzelne Bilder 0.5 erreichen. Bei 0.30 ± 0.08 mit
Aussetzern wirken beide Wege zusammen: Die erste Nummer kommt erst nach
Minuten (ohne Aussetzer 78 %), und nach einem Aussetzer kehrt eine verlorene
Spur nur mit einer Erkennung ≥ `track_high_thresh` (0.4) zurück. Die vier
Läufe streuen stark (15–80 %); mit `track_high_thresh` 0.25 sind es im
Mittel 82 %.

Die Simulation ersetzt die Messung am Stall nicht, zeigt aber, was eine
Einstellung grundsätzlich tut.

## Verifikation (auf dem Stall-Rechner, mit Modell)

Ziel: **< 1 ID-Wechsel pro Kuh in 10 Minuten** Testmaterial, geprüft je
Lichtverhältnis (Tag UND IR-Nacht), **und** keine Kuh dauerhaft ohne ID.

1. 10-Minuten-Clips aufnehmen, 1 FPS wie im Betrieb, Tag und Nacht. Quelle
   ist `stream.url` aus `config.yaml`, also die Adresse, die der Agent liest:
   `ffmpeg -i "<stream.url>" -t 600 -r 1 nacht.mp4`.
   Bei der Cloud-Quelle ohne Bridge ist `stream.url` leer. Dann die
   kurzlebige HLS-Adresse nehmen, die der Agent über `quelle_api` holt
   (z. B. `/api/stallwache/stream`), und sie direkt vor der Aufnahme
   abrufen.
2. Messen (`edge-agent/training/tracking_pruefung.py`). Das Modell rechnet
   den Clip nur einmal, die Erkennungen landen in `nacht.erkennungen.json`:

   ```bash
   cd edge-agent/training
   python3 tracking_pruefung.py nacht.mp4 --modell best.pt --kuehe 2 \
       --tracker ../tracker-kuh.yaml bytetrack.yaml
   # weitere Variante ohne neue Inferenz:
   python3 tracking_pruefung.py nacht.mp4 --kuehe 2 --tracker variante.yaml
   ```

   Das Werkzeug ist für Szenen gemacht, in denen dieselben Kühe den ganzen
   Clip über im Bild bleiben (Abkalbebox, Liegebereich). `--kuehe` ist ihre
   Zahl und Pflicht für ein Urteil. Ohne die Angabe schätzt das Werkzeug
   sie, und ein Geist mit eigener ID zählt dann als Kuh. Kommen und gehen
   Tiere (Futtertisch), zählt jede Besucherin als ID-Wechsel. Eine Kuh, die
   länger als `track_buffer` (90 s) aus dem Bild geht, kommt mit neuer ID
   zurück. Das zählt zu Recht: Auch der Agent beginnt ihr Fenster dann neu.
   `--tier-klassen` entspricht `modell.tier_klassen` (Default `kuh`).
   Fruchtblase und Kälberfüße laufen wie im Agenten durch denselben Tracker,
   gemessen werden nur die Tiere.
3. Die Tabelle nennt je Einstellung:
   - geschätzte und angegebene Kühe, in wie vielen Bildern alle zugleich
     erkannt sind,
   - IDs, ID-Wechsel und Kurz-IDs (< 10 s) je Kuh und 10 min,
   - die längste Strecke mit mehr langen IDs als Kühen (Geist),
   - Stellen ohne ID, Erkennungen ohne ID je Konfidenzband und die
     Bildrate des Rechners.

   **Urteil: ✗ oder „keine Beanstandung – Stellen ansehen“, nie ✓.** Ob
   jede Kuh eine ID hat, lässt sich aus Zählungen nicht beweisen. Fünf
   QA-Runden haben zu jeder Zählregel ein Gegenbeispiel gefunden: Ein Geist
   mit ID verdeckt eine blinde Kuh, Rauschen täuscht eine fehlende Kuh vor,
   eine Verdeckung am Clip-Rand sieht aus wie ein Wechsel. Deshalb urteilt
   das Werkzeug nur, wo ein Fehler bewiesen ist, und zeigt sonst, wo man
   hinsehen soll (Entscheidung des Betreibers, 27.10.2026).
   - **✗**, sobald ein ID-Kriterium verfehlt ist:
     - ≥ 1 ID-Wechsel oder ≥ 1 Kurz-ID je Kuh und 10 min,
     - ein Geist: mindestens 10 Bilder mehr lange IDs als Kühe, Aussetzer
       bis 2 Bilder überbrückt. Ein Doppelrahmen beim Aufstehen (2–5
       Bilder) ist keiner.
   - **„keine Beanstandung – Stellen ansehen“** sonst, mit diesen
     Hinweisen:
     - **Stellen ohne ID:** Orte, an denen sich Erkennungen ohne ID sammeln.
       Erkennungen gehören zum selben Ort, wenn ihre Box die mittlere Box
       des Orts mit IoU ≥ 0.3 überlappt. Genannt wird ein Ort ab 60 Bildern
       ohne ID, zusammenhängend oder nicht, wenn die Erkennung ohne ID dort
       in mindestens 60 Bildern neben einer Box mit ID lag (etwa eine blinde
       Kuh unter einem Geist) oder mindestens die Hälfte der Bilder an
       diesem Ort ausmacht. Je Stelle stehen Bildzahl, Zeitraum, Konfidenz
       und mittlere Box da. Ist es eine Kuh, ist sie blind, das gilt als ✗.
       Ist es eine Fehlerkennung, als Hard Negative labeln (Skill
       `fehlalarm-triage`), nachtrainieren und neu messen.
     - **Nie alle erkannt:** In weniger als 60 Bildern sind alle
       angegebenen Kühe zugleich erkannt. Eine Kuh wird kaum erkannt, oder
       `--kuehe` stimmt nicht.

   Exit 0 = keine Beanstandung, 1 = mindestens ein ✗, 2 = ohne `--kuehe`
   oder Eingabefehler. **Kurze Clips sind streng:** Bei einer Kuh in 10 min
   reicht eine einzige Kurz-ID für ✗, etwa ein Mensch oder ein Kalb, das
   kurz als Kuh erkannt wird. Längere Clips mitteln.

   **Was das Werkzeug zusagt** (je Zusage Tests in
   `edge-agent/tests/test_tracking_pruefung.py`):
   - **Nie ✓**, und ohne `--kuehe` gar kein Urteil.
   - **✗ bei bewiesenem Fehler:** ≥ 1 Wechsel oder Kurz-ID je Kuh und
     10 min, oder ein Geist ab 10 Bildern. Jedes Kriterium allein reicht.
   - **Kein ✗ in gesunden Szenen:**
     - Verdeckung mit neuer ID (< 1 je Kuh und 10 min), auch am Clip-Rand,
     - Doppelrahmen beim Aufstehen,
     - Einzelbild-Rauschen,
     - Teilboxen in der Herde.
   - **Jede Kuh, die an einem Ort ≥ 60 Bilder ohne ID erkannt wird** (ab
     conf 0.1, auch dünn, mit Pausen oder unter einem Geist), steht als
     Stelle in der Liste. Eine Kuh mit stabiler ID, der der Tracker ab und
     zu kein Bild zuordnet, steht nicht darin.
   - **Hinweis „nie alle erkannt“** auch dann, wenn Einzelbild-Rauschen die
     Zahl der Erkennungen kurz anhebt.

   **Was es nicht sieht** (im Clip ansehen):
   - **Wandernde Kuh ohne ID:** eine Kuh, die an keinem Ort 60 Bilder
     verweilt.
   - **Unerkannte Kuh:** eine Kuh, die das Modell nie über conf 0.1 erkennt
     – nur der Hinweis „nie alle erkannt“ deutet darauf.
   - **ID-Tausch:** Tauschen zwei Kühe ihre IDs, sieht das Werkzeug es
     nicht, denn es zählt IDs, keine Tiere. Das Symptom „IDs flackern
     zwischen zwei nahen Kühen“ also im Clip ansehen.
   - **Gemeinsame Box:** Verschluckt eine Box zwei dicht stehende Kühe,
     fällt die zweite nicht auf.
   - **Eine Kuh mit vielen Wechseln unter vielen stabilen:** Der Mittelwert
     je Kuh kann unter 1 bleiben.
   - **Offene Szenen:** Kommen und gehen Tiere, zählt jede Besucherin als
     Wechsel.

   „Keine Beanstandung“ ersetzt weder den Blick auf die Stellen noch den
   24-h-Lauf wie Gate 3 vor einer Freigabe.
4. Nach jeder Änderung an `tracker-kuh.yaml` neu messen, immer nur EINEN
   Wert drehen. Die Tabelle gehört in die Modellkarte.

### Entscheidungsregel für IR-Nachtclips (vorab festgelegt)

- **Material:** mindestens eine volle Nacht mit liegender und stehender
  Kuh. `tracking_pruefung.py` gegen `tracker-kuh.yaml`, eine Variante mit
  `track_high_thresh` 0.25 und eine mit `track_high_thresh` und
  `new_track_thresh` 0.3 laufen lassen.
- **Handeln**, wenn eine Einstellung ✗ zeigt oder eine Stelle sich beim
  Ansehen als Kuh ohne ID herausstellt. Am wichtigsten: eine Kuh 30 min
  oder länger ohne ID, also ein ganzes Kalbeverdachts-Fenster.
- **Geister erkennen:** immer mit `--kuehe` messen. Sind mindestens
  10 Bilder lang mehr Kühe mit ID als angegeben, kommt ein Geist-Hinweis.
- **Reihenfolge:**
  1. Zuerst das Modell nachtrainieren (IR-Bilder, Hard Negatives).
  2. Dann `track_high_thresh` 0.4 → 0.25. Das hilft Kühen, die ihre Nummer
     nach einem Aussetzer verlieren. Eine neue Nummer braucht weiter ein
     Bild ≥ 0.5, die Bestätigung im Folgebild sinkt aber auf etwa 0.3 (mit
     `fuse_score` zählt IoU × Konfidenz > 0.3).
  3. Erst danach `new_track_thresh` 0.5 → 0.4 → 0.3, je Stufe auf Geister
     prüfen. Wirksam ist der größere Wert von `new_track_thresh` und
     `track_high_thresh`, darum diese Reihenfolge.
- **Freigabe** einer Änderung nur nach einem 24-h-Lauf wie Gate 3
  (`edge-agent/training/abnahme.py`), der eine volle IR-Nacht enthält und
  zusätzlich höchstens 1 Brunstverdacht zeigt.

## Fehlersuche

| Symptom | Ursache | Dreh |
| --- | --- | --- |
| Neue ID nach Verdeckung (Futtertisch, Kuh hinter Kuh) | `track_buffer` zu klein | Buffer erhöhen (90 → 120); Obergrenze: solange keine Fremdübernahmen auftreten |
| IDs flackern zwischen zwei nahen Kühen | Matching zu großzügig | `match_thresh` senken (0.9 → 0.85) |
| Geister-IDs bei Nacht/Rauschen | Neue Tracks zu billig | `new_track_thresh` erhöhen |
| Kuh nachts nie mit Nummer (Achtung-Hinweis, Band 0.25–0.50 ohne ID) | kein Bild ≥ `new_track_thresh` (0.5) mit Bestätigung ≥ `track_high_thresh` (0.4) im Folgebild | Modell mit IR-Bildern nachtrainieren (Skill `modell-training`); danach `new_track_thresh` 0.5 → 0.4, je Stufe auf Geister prüfen. Tiefer nur zusammen mit `track_high_thresh`, denn wirksam ist der größere der beiden Werte |
| Kuh hatte eine Nummer und verliert sie nachts nach kurzem Aussetzer | verlorene Spur kehrt nur mit Erkennung ≥ `track_high_thresh` zurück | `track_high_thresh` 0.4 → 0.25; der Geisterschutz bleibt bei `new_track_thresh` |
| „Kühe im Bild“ größer als die echte Kuhzahl, Alarme für eine Nummer, die es nicht gibt, stündlicher Brunstverdacht an einer liegenden Kuh | Dauer-Fehlerkennung mit Nummer | Bildstelle als Hard Negative labeln (Skill `fehlalarm-triage`), nachtrainieren; erst danach Schwelle anheben |
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
- **Geister gegen blinde Kuh (`new_track_thresh`).** Der Tracker
  unterscheidet eine schwach erkannte Kuh nicht von einer Dauer-Fehlerkennung
  (Heuballen, Trennwand, halbe Box an einer liegenden Kuh): Für ihn sind
  beides ruhende Kästen mit niedriger Konfidenz. Eine neue Nummer gibt es
  erst, wenn ein Bild 0.5 erreicht und das nächste mindestens 0.4. Einmal
  vergeben, hält `track_low_thresh` (0.05) die Nummer auch bei schwacher
  Konfidenz: Für einen Dauer-Geist reicht eine einzige Spitze über 0.5.
  Hohe Schwelle: Geister bekommen keine Nummer – eine Kuh, die nachts im
  Liegen nie 0.5 erreicht, aber auch nicht. Sie wird dann nicht auf Kalbe-
  und Brunstzeichen ausgewertet, und niemand merkt es. Niedrige Schwelle:
  Jede Kuh wird verfolgt, aber ein Dauer-Geist hinter oder auf einer
  liegenden Kuh löst jede Nacht stündlich einen Brunstverdacht aus, bei
  ungünstigen Keypoints zusätzlich alle 15 min einen Kalbeverdacht. Die
  Austreibung (Fruchtblase, Kälberfüße) hängt an keiner Nummer und ist von
  beidem nicht betroffen. Entschieden wird an echten IR-Nachtclips, nicht an
  der Simulation. Die Ursache liegt fast immer im Modell (zu wenig
  IR-Bilder, fehlende Hard Negatives) und wird dort behoben; erst danach an
  der Schwelle drehen.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Clips aufnehmen, Messung ausführen | Landwirt/Betreiber |
| Werte interpretieren, tracker-kuh.yaml anpassen | Orchestrator (dieser Skill) |
| Prüfen, dass Regel-Schwellen unangetastet bleiben | Agent `ki-wache` |
