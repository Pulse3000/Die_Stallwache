# Spezifikation: Lahmheits-Frühwarnung aus der Rückenlinie

Implementierungsreife Regeln für Roadmap P3 (Wettbewerbsbezug CattleEye:
„Cobb-Winkel < 170° als Frühindikator", [`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md)
Abschnitt 2 Punkt 3). Entwurf: Agent `ki-wache` (16.07.2026), Entscheidung
und Übernahme: Orchestrator. **Status: spezifiziert — hart abhängig vom
neuen Keypoint `spine_mid` im 2. Training; bis dahin gar nicht (auch nicht
teilweise) umsetzbar.**

## 0. Melde-Grundsatz: Hinweis, nie Alarm

Lahmheit hat ein Zeitbudget von **Tagen bis Wochen** — ein um 24 h späterer
Hinweis kostet fast nichts, ein nächtlicher Lahmheits-Ping wäre ein
Systemfehler. Strengste Auslegung von „Ruhe vor Fülle":

- **Kein Eintrag in die Alarmkette:** kein Telegram-Weckruf, kein neuer
  Dashboard-Ereignistyp (nur `typ: "info"`, wie bei der Kalbe-Akte).
- **Ausgabe ausschließlich:** eine Zeile im Tagesbericht + ein stiller
  Wochenhinweis (`disable_notification`).
- **Spezifität vor Sensitivität:** Zielwert < 1 falsch-auffällige Kuh-Zeile
  pro Woche — eine verpasste beginnende Lahmheit ist am Folgetag erneut
  messbar; eine Woche unglaubwürdiger Zeilen führt zum Abschalten.
- **Ehrliche Wortwahl:** gemeldet wird „Rücken im Stehen anhaltend
  aufgekrümmt" — niemals „Kuh lahmt", kein Locomotion-Score, keine
  Diagnose. Klassische Systeme (CattleEye, COW-AI) bewerten den Rücken
  **im Gang** über einem Laufgang; unsere Buchtkameras sehen stehende
  Kühe. Statisches Aufkrümmen ist ein anerkannter, aber schwächerer
  Frühindikator — genau das und nicht mehr behaupten wir.

## 1. Messgröße: Rückenwinkel an `spine_mid` (erst ab 2. Training)

**Ehrliche Grenze zuerst:** Mit den heutigen drei Keypoints ist
Rückenkrümmung **nicht messbar** — `tail_tip` liegt auf dem Schwanz, auf dem
Rücken liegen nur zwei Punkte, und zwei Punkte definieren eine Gerade.
Voraussetzung ist der neue Keypoint **`spine_mid`** (Widerrist/Rückenmitte).
Kein Behelf über Boxgeometrie (misst Umriss, nicht Topline).

**Winkeldefinition** (Cobb-analog, exakt das `_schwanzwinkel`-Muster):

```
v1 = spine_mid − spine_end        # vorderes Rückensegment
v2 = tail_base − spine_mid        # hinteres Rückensegment
abweichung = abs(degrees(atan2(v1×v2, v1·v2)))   # 0° = gerade
rueckenwinkel = 180° − abweichung                # 180° = gerader Rücken
```

**Gültigkeitsfilter pro Messung:**

| Filter | Wert | Begründung |
| --- | --- | --- |
| Zustand „steht" | B/H ≤ 1.6 + Boxhöhe ≥ 85 % Steh-Baseline (identische Geometrie wie Festliege-Spez.) | liegend ist die Topline gestaucht, der Winkel bedeutungslos |
| Keypoints finit | alle drei `isfinite` | Muster `_schwanzwinkel` |
| Segmentlänge | ‖v1‖, ‖v2‖ ≥ **30 px** | darunter dominiert Keypoint-Rauschen (±2 px ≈ ±4°) |
| Track gültig | `track_id ≥ 0` | Muster LogicEngine |
| **Kalbe-Ausschluss** | aktiver Kalbeverdacht, Austreibungs-Episode + 24 h, `wach_modus` → keine Bewertung | Wehen krümmen den Rücken physiologisch — Kalbe-Signal, kein Lahmheits-Signal |

Kurzzeitiges Aufkrümmen (Koten, Strecken, < 1–2 min) wird nicht einzeln
gefiltert — das erledigt der Tages-Median statistisch.

## 2. Aggregation: Tages-Median pro Kuh-ID

| Regel | Wert | Begründung |
| --- | --- | --- |
| Tageswert | **Median** aller gültigen Winkel pro Kuh-ID und Kalendertag | immun gegen Kurz-Episoden (müssten > 50 % der Steh-Zeit ausmachen) |
| Mindeststichprobe | **≥ 600** Messungen/Tag (≈ 10 min seitliche Steh-Zeit bei 1 FPS) | darunter kein Urteil („zu wenig Daten" statt falscher Zahl) |
| **Auffällig** | Tages-Median < **170°** | CattleEye-Referenz; gesunde Kuh in 2D-Seitenansicht > 175°, 10° liegt klar außerhalb des Rauschens |
| **Entwarnt** | Tages-Median ≥ **174°** | 4° Hysterese gegen Tages-Flackern |
| Bestätigung | Digest-Zeile erst ab **2 auffälligen Tagen derselben Kuh-ID in derselben Agent-Laufzeit**; Tag 1 nur stilles Belegbild | halbiert Einzeltag-Artefakte, kostet beim Tage-Budget nichts |

**Ehrliche ID-Antwort:** Kuh-IDs sind sitzungsstabil, keine Tieridentität.
Heute möglich: Tageswerte pro ID + Mehrtages-Bestätigung nur bei
durchlaufender ID (reißt sie, beginnt die Zählung neu — mit Vermerk);
identitätsfreier buchtweiter Wochenzähler in lokaler JSON-Datei
(`verlauf_datei`, überlebt Neustarts). **Nicht möglich und nicht
behauptet:** echte 7-Tage-Trends pro Tier — bräuchte Tier-Wiedererkennung,
die bewusst auf der Nicht-Roadmap steht.

Bauform: eigenständige, offline testbare Klasse `LahmheitsBeobachter` mit
injizierbarem `jetzt` (Muster `TotmannWaechter`).

## 3. Meldeweg (fertige Texte)

**Tagesbericht-Zeile** (nur bei Befund oder Datenmangel, sonst Schweigen):
- *Auffällig:* „Rückenlinie: Kuh #12 stand heute überwiegend mit
  aufgekrümmtem Rücken (Median 166°, 1.240 Messungen, 2. Tag in Folge) —
  beim nächsten Melken auf Gang und Klauen achten."
- *Entwarnung (nur nach Auffällig-Zeile):* „Rückenlinie: Kuh #12 heute
  wieder unauffällig (Median 176°)."
- *Datenmangel:* „Rückenlinie: heute zu wenige seitliche Steh-Ansichten für
  eine Bewertung (beste Kuh: 214 von 600 nötigen Messungen)."
- *ID-Bruch-Vermerk:* „Hinweis: Kuh-Nummer kann sich seit gestern geändert
  haben — Tier über das Belegbild identifizieren."

**Stiller Wochenhinweis** (einmal wöchentlich, entfällt bei null Befunden):
„🦶 Rückenlinien-Wochenblick (Bucht stallwache): an 3 von 7 Tagen mindestens
eine Kuh mit anhaltend aufgekrümmtem Rücken (Mo, Di, Do). Belegbilder:
aufnahmen/lahmheit-kandidaten/. Kein Notfall — Empfehlung:
Klauenpflege-Termin prüfen."

**Belegbilder:** pro auffälligem Kuh-Tag genau 1 unannotiertes Bild (Frame
am nächsten zum Tages-Median) → `kandidaten_ordner`; für
Tierarzt-Besprechung und als Trainingsmaterial. Dashboard/MQTT über den
bestehenden `info`-Pfad — keine Ingest-Änderung.

## 4. Konfig-Schema (für config.example.yaml, bei Umsetzung)

```yaml
lahmheit:
  aktiv: false                    # opt-in: erst nach Verifikation UND spine_mid im Modell
  winkel_auffaellig_grad: 170     # Tages-Median darunter -> auffaellig (CattleEye-Referenz)
  winkel_entwarnung_grad: 174     # Hysterese
  min_messungen_tag: 600          # ~10 min Steh-Zeit bei 1 FPS
  min_segment_px: 30              # Rauschgrenze
  bestaetigung_tage: 2
  steh_aspekt_max: 1.6            # identisch zur Festliege-Spezifikation
  kalbe_sperre_stunden: 24
  wochenhinweis: true
  wochenhinweis_tag: "So"
  verlauf_datei: ./aufnahmen/lahmheit-verlauf.json
  kandidaten_ordner: ./aufnahmen/lahmheit-kandidaten
```

Dazu in `modell.keypoints` (2. Training, **anhängen statt umsortieren** —
Indizes 0–2 bleiben stabil): `spine_mid: 3`.

## 5. Verifikationsplan (Abnahme vor dem Scharfschalten)

1. **Winkel-Unit-Tests:** kollinear → exakt 180°; konstruierte 10°/20°-
   Krümmung → ± 0,5°; Segment < 30 px → `None`; liegend → keine Messung.
2. **Logik-Simulation** (injiziertes `jetzt`): 599 Messungen → kein Urteil;
   Median-Robustheit (10 % Koten-Frames kippen den Tag nicht); 1 Tag → nur
   Belegbild, 2 Tage → Zeile; Hysterese; ID-Wechsel → Neustart + Vermerk;
   Kalbe-Sperre.
3. **Kamera-Kalibrierprobe (Pflicht pro Kamera):** 7 Tage Winkelverteilung
   der gesunden Herde loggen — Abnahme: Median > **175°**, P25–P75 < **6°**.
   Fällt die Kamera durch (steiler Winkel, Frontalsicht) → `aktiv: false`
   für diese Kamera; die Schwelle wird NICHT verbogen.
4. **Nullprobe:** 14 auswertbare Tage gesunde Herde → **0** bestätigte
   Auffällig-Zeilen.
5. **Positiv-Validierung** (die „eigene Validierung" der Roadmap): ≥ **3**
   durch Klauenpfleger/Tierarzt bestätigte Fälle → an ≥ 2 der 3 Tage vor
   der Feststellung auffällig; Ergebnis in `docs/metriken.md`. Erst danach
   darf das Feature im README erwähnt werden.
6. **Praxis-Probelauf:** 4 Wochen; Abbruch bei > 1 unplausibler Zeile/Woche.

## 6. Abhängigkeiten

1. **2. Training: Keypoint `spine_mid`** (hart) — reiht sich neben
   `kuh_seitenlage` (Festliege) und `kalb_liegend`/`kalb_stehend`
   (Kalbe-Akte) in **einen** gemeinsamen 2. Trainingsdurchgang ein;
   Bestand muss nachgelabelt werden.
2. Leichte lokale JSON-Persistenz für den buchtweiten Wochenzähler.
3. Steh-Klassifikation gemeinsam mit dem Festliege-Wächter (eine
   Geometrie-Funktion, keine Doppel-Implementierung).
4. Keine Dashboard-/Ingest-Änderung.

## Offene Risiken

1. **2D-Projektion:** Der gemessene Winkel ist eine Bildebenen-Projektion,
   kein anatomischer Cobb-Winkel — ein schräg gesehener gesunder Rücken
   kann gekrümmt wirken. Gegenmaßnahme: Pflicht-Kalibrierprobe pro Kamera,
   Default aus, Freigabe pro Kamera einzeln.
2. **Physiologisches Aufkrümmen (v. a. Wehen):** ohne Kalbe-Sperre würde
   die Zeile ausgerechnet vor Kalbungen falsch anschlagen — Sperre +
   Tages-Median sind Pflichtbestandteile.
3. **Fehlende Tieridentität:** ID-Wechsel verwässern Mediane oder zerreißen
   die 2-Tage-Bestätigung — konservative Formulierung auf Tages-Ebene,
   ID-Bruch-Vermerk, Belegbild zur manuellen Identifikation, buchtweiter
   Wochenblick als identitätsfreier Ausweg.
