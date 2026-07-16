# Spezifikation: Festliege-Wächter (Downer-Cow-Alarm)

Implementierungsreife Regeln für das P1-Alleinstellungs-Feature aus
[`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md) Abschnitt 4b — kein
Kamera-Produkt am Markt adressiert Festliegen explizit. Entwurf: Agent
`ki-wache` (16.07.2026), Entscheidung und Übernahme: Orchestrator.
**Status: spezifiziert, wartet nur noch auf das erste Modell** (Umsetzung
erst mit `best.pt`, siehe Skill `modell-training`).

## 0. Precision/Recall-Grundsatz

Festliegen hat ein Zeitbudget von Stunden, nicht Minuten: Ein um 60 min
späterer Alarm kostet fast nichts, ein nächtlicher Fehlalarm um 3 Uhr führt
erfahrungsgemäß zum Abschalten des Features — und damit zu Recall = 0.
Deshalb: **Precision-first im Normalbetrieb** (langes Fenster, konservative
Geometrie, Default aus), **Recall-first nur in zwei klar begrenzten
Hochrisiko-Pfaden**: (a) Milchfieber-Fenster nach erkannter Austreibung,
(b) Seitenlage als gelernte Objektklasse — Seitenlage einer adulten Kuh ist
per se ein Notfall (Aufblähgefahr, Minuten-Budget).

## 1. Liegend-Klassifikation (Box + Topline-Keypoints, keine Bein-Keypoints)

| Zustand | Kriterium (Geometrie) | Robustheit |
| --- | --- | --- |
| **steht** | Seitenverhältnis B/H ≤ 1.6 (Hysterese-Ausstieg) und Boxhöhe ≥ 85 % der Steh-Baseline | gut, per Hysterese flackerfrei |
| **liegt (Brustlage)** | B/H ≥ 1.9 (Einstieg) ODER Boxhöhe < 70 % der Steh-Baseline; Steh-Baseline = Median der Boxhöhe der letzten 60 „steht"-Frames pro Track | brauchbar, kamerawinkelabhängig (Risiko 1) |
| **Seitenlage-Verdacht** | B/H ≥ 2.6 UND y-Mittel der Rückenlinie unterhalb 45 % der Boxhöhe | **schwach — nicht alarmtauglich** |

Urteil pro **5-Minuten-Bucket**: liegend bei ≥ 70 % liegend-Frames,
Mindeststichprobe 20 Frames (Muster der bestehenden LogicEngine).

**Ehrliche Grenze:** Brustlage vs. Seitenlage ist aus Box + drei
Topline-Punkten nicht zuverlässig trennbar. **Entscheidung:** Geometrie nur
für die steht/liegt-Zeitregel; Seitenlage-Alarme ausschließlich über eine
**neue Objektklasse `kuh_seitenlage`** im nächsten Training (objektbasierter
Override wie `amniotic_sac`/`calf_legs`, Konfidenz ≥ 0.85). Bis dahin:
Geometrie-Verdachtsframes still nach `./aufnahmen/seitenlage-kandidaten`
sammeln — das baut den Labeling-Datensatz auf. Im nächsten CVAT-Durchgang
Klasse `kuh_seitenlage` ergänzen; Brustlage bleibt Klasse `kuh`.

## 2. Zeitregeln

| Fall | Regel | Begründung |
| --- | --- | --- |
| **Normalbetrieb** | ununterbrochen liegend ≥ **240 min** am selben Liegeplatz → Festliege-Verdacht | gesunde Liegeperioden: typ. 60–90 min, selten bis 3 h; 4 h hält < 1 Fehlalarm/Nacht |
| **Milchfieber-Fenster** | für **72 h** nach Ende einer Austreibungs-Episode (vorhandener Trigger `austreibung_zuletzt`) gilt verkürzt **120 min** | Hypokalzämie überwiegend 24–72 h post partum |
| **Seitenlage (nur Klasse)** | `kuh_seitenlage` ≥ 0.85 in ≥ 70 % der Frames eines **10-min-Fensters** (Mindeststichprobe 100) → dringender Alarm, fensterunabhängig | Minuten-Notfall; Anteilsfilter verhindert Einzelframe-Weckruf |

- **Aufsteh-Reset:** erst nach ≥ **60 s zusammenhängend** „steht" — ein
  Fehlklassifikations-Frame löscht weder die Uhr noch löst er Entwarnung aus.
- **ID-Wechsel-Robustheit:** Das Fenster hängt am **Liegeplatz**, nicht an
  der Track-ID: Verschwindet ein liegender Track und erscheint binnen 120 s
  ein neuer liegender Track mit IoU ≥ 0.5 zur letzten Box, erbt er die
  Episode (festliegende Kühe sind statisch — Orts-Kontinuität schlägt hier
  ID-Kontinuität). Episodenende nach 300 s ohne liegende Kuh am Platz oder
  nach bestätigtem Aufstehen.
- **Bauform:** eigenständige, offline testbare Klasse `FestliegeWaechter`
  mit injizierbarem `jetzt` (Muster `TotmannWaechter`).

## 3. Anti-Spam

- Genau **ein** Alarm pro Liegeplatz-Episode (analog Eskalations-Flag);
  genau **eine** Wiederholung nach weiteren 120 min, dann Schweigen bis
  Entwarnung.
- **Entwarnung** nur nach vorherigem Alarm, als **stille** Nachricht
  (`disable_notification`) — gute Nachrichten wecken nicht.
- **Wach-Modus verändert Festliege-Schwellen bewusst NICHT** (prä partum vs.
  post partum; der ereignisgetriggerte Milchfieber-Verschärfer ist präziser).
- Feedback-Buttons gelten auch hier; Fehlalarm-Frames sind Hard Negatives
  für die künftige `kuh_seitenlage`-Klasse.
- **Neuer Ereignistyp `festliege`** — Abhängigkeit: die Ingest-Whitelist
  (`lib/events.ts`, `app/api/events/route.ts`) muss parallel erweitert
  werden, sonst antwortet das Dashboard mit 400 (Telegram bliebe unberührt).
  Entwarnung als `typ: "info"` mit `kuhId`.

## 4. Alarmtexte

- **Verdacht:** „Kuh #17 liegt seit 4,1 Stunden ununterbrochen an derselben
  Stelle und ist nicht aufgestanden — bitte beim nächsten Stallgang prüfen,
  ob sie aufstehen kann."
- **Nach Kalbung (dringend):** „⚠️ FESTLIEGE-VERDACHT NACH KALBUNG: Kuh #17
  liegt seit 2,0 Stunden ohne Aufstehen, Kalbung war vor ca. 14 Stunden.
  Verdacht auf Milchfieber — bitte sofort kontrollieren, Kalzium
  bereithalten und Tierarzt erwägen."
- **Seitenlage (dringend, nur mit Klasse):** „⚠️ NOTFALL SEITENLAGE: Kuh #17
  liegt seit 12 Minuten flach auf der Seite — Aufblähgefahr! Bitte sofort in
  den Stall, Kuh in Brustlage aufrichten."
- **Wiederholung:** „Kuh #17 liegt weiterhin — jetzt seit 6,2 Stunden ohne
  Aufstehen. Falls noch nicht geschehen: bitte kontrollieren."
- **Entwarnung (still):** „Entwarnung: Kuh #17 steht wieder (lag zuvor
  4,6 Stunden). Keine Aktion mehr nötig."

Bewusst vermieden: Aussagen über Modell-Evidenz hinaus („bewegt sich
normal" — das System sieht nur Aufstehen, keinen Gang).

## 5. Konfig-Schema (für config.example.yaml, bei Umsetzung)

```yaml
festliege:
  aktiv: false                    # opt-in: erst nach Kamera-Verifikation
  liege_fenster_minuten: 240
  postpartum_fenster_minuten: 120
  postpartum_stunden: 72
  wiederholung_minuten: 120       # 0 = aus
  entwarnung: true
  liege_aspekt_min: 1.9
  steh_aspekt_max: 1.6
  hoehen_faktor: 0.70
  anteil_schwelle: 0.70
  min_stichprobe: 20
  aufsteh_bestaetigung_s: 60
  platz_iou_min: 0.5
  platz_luecke_s: 300
  seitenlage_klasse: false        # erst wenn best.pt kuh_seitenlage enthaelt
  seitenlage_konfidenz: 0.85
  seitenlage_fenster_minuten: 10
  seitenlage_anteil: 0.70
  seitenlage_kandidaten_ordner: ./aufnahmen/seitenlage-kandidaten
```

Dazu in `modell.klassen` (nach dem Training): `kuh_seitenlage: 3`.

## 6. Verifikationsplan (Abnahmekriterien vor dem Scharfschalten)

1. **Nacht-Nullprobe:** 3 IR-Nachtclips (je ≥ 8 h) ohne Festlieger →
   **0 Alarme**.
2. **Zustandsklassifikation:** 10 annotierte Clips → Bucket-Genauigkeit
   steht/liegt ≥ 90 %, Aufsteh-Reset ≤ 2 min.
3. **Verdeckungs-Stresstest:** provozierte ID-Wechsel → gemessene Liegedauer
   weicht < 10 % ab, Episode zerreißt nicht.
4. **Platz-Übernahme-Gegenprobe:** „A steht auf, B legt sich hin" →
   0 fälschliche Episoden-Vererbungen in 5 Szenen.
5. **Seitenlage-Positivfälle:** ≥ 10 Clips aus offenen Quellen →
   Konfidenz-Sweep dokumentieren (`docs/metriken.md`), Recall ≥ 90 % bei
   Präzision ≥ 80 %.
6. **Logik-Simulation ohne Kamera** (pytest, injiziertes `jetzt`): 1 Alarm
   nach 4 h, 1 Wiederholung, 1 Entwarnung, ID-Wechsel-Robustheit, kein Reset
   durch 30-s-Flackern, Post-Kalbungs-Pfad.

## Offene Risiken

1. **Kamerawinkel:** Bei steiler Montage bricht das Aspekt-Kriterium
   zusammen → Default `aktiv: false`, Pflicht-Verifikation pro Kamera.
2. **Fälschliche Episoden-Vererbung** bei schnellem Platztausch → Gegenprobe
   4 ist Abnahmekriterium; Restrisiko spricht zusätzlich fürs 240-min-Fenster.
3. **Unkalibrierte Seitenlage-Klasse** (zunächst Fremdmaterial) →
   konservative 0.85/10-min-Regel, Default aus, Kalibrierung über die
   Ein-Tipp-Feedback-Schleife.
