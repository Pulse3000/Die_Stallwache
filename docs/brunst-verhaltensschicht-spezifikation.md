# Spezifikation: Brunst-Verhaltensschicht (Einzelkamera)

Implementierungsreife Regeln fuer den 24/7-Dauerlauf auf stallwache-lela.
Schliesst die Luecke des 09.10.2026 (brunstige Kuh rinderte, keine Meldung:
Anwesenheit ist kein Verhalten). Entwurf: LELA (10.10.2026), Entscheidung:
Landwirt. **Status: Entwurf v0.1 - zur Freigabe.**

Abgrenzung: Diese Spezifikation regelt die Brunst-Erkennung EINER Kamera.
Die Zwei-Kamera-Plausibilisierung bleibt unangetastet in
[`brunst-fusion-spezifikation.md`](./brunst-fusion-spezifikation.md) (P2,
erst mit zweiter Kamera).

## 1. Grundsatz

- **Brunst ist ein Verhaltensmuster ueber Zeit, kein Einzelbild-Ereignis.**
  Gemeldet wird "Kuh #ID zeigt brunsttypisches Verhalten seit X Min" -
  niemals "Tier im Bild".
- Datenbasis: Pose-Keypoints (spine_end, tail_base, tail_tip) und Tracking-ID
  je Tier, im 60-s-Zyklus des Dauerlaufs.
- **Ruhe vor Fuelle:** Brunst ist planbar (Besamungsfenster 8-18 h) -
  strikte zeitliche Evidenz, im Zweifel still. Kalbung ist ein Notfall -
  ihr Override (PRIO 1) uebersteuert alles, Recall 100 %.
- **Tierart-Neutralitaet:** Klassen, Keypoints und Schwellen sind
  Konfiguration (Option Abfohlen bleibt offen).
- **Beweispflicht:** Jeder Alarm enthaelt Snapshot mit Keypoint-Overlay,
  Tier-ID und Evidenzdauer. Kein Alarm ohne Modell-Befund.

## 2. Grenzen (Hardware/Echtbetrieb)

- CPU-only (AMD A6-3650, 1 Kern Container-Limit): Pose-Inferenz via ONNX
  Runtime. Ziel: Analyse < 25 s im 60-s-Zyklus. Ueberschreitung ->
  Rueckschritt: Pose nur jeden 2. Zyklus (120 s), Detektion bleibt 60 s.
- Tracking-ID-Spruenge im IR moeglich (liegende Tiere, Okklusion) -
  ID-Stabilitaet messen (siehe Risiken).
- Kein Cloud-Zwang: Auswertung lokal, Telegram ist der einzige externe Kanal.
- Watchdog: 5 Min ohne Messpunkt fuer ein zuvor stabiles Tier ->
  Stoerungsmeldung an Telegram (Kamera/Gateway-Verdacht), Analyse laeuft weiter.

## 3. Schwellenwerte

- **Schwanzwinkel** aus Keypoints: u = tail_base -> back_mid,
  v = tail_base -> tail_tip; theta = arccos(u.v / (|u||v|)).
- **Aktiver Messpunkt:** theta > 45 Grad (Konfiguration).
- **Brunst-Verdacht (Telegram, PRIO 2):** > 60 % der Messpunkte im
  gleitenden 30-Min-Fenster aktiv, mindestens 15 gueltige Messpunkte im
  Fenster (bei 60-s-Takt bis zu 30 Punkte).
- **Abklingen:** Aktiven-Anteil < 40 % fuer 10 Min -> Entlastungs-Nachricht.
- **Cooldown:** 15 Min pro Tier-ID nach Alarm (keine Push-Kaskaden).
- **Aufsprung-Einzelereignis (Phase 2, optional):** Reitposition zweier
  Tier-IDs > 4 s -> sofortiger Signal-Rohreport (Dauer fuer die
  Zwei-Kamera-Fusion, siehe dort).
- **Kalbungs-Override (PRIO 1, unveraendert):** Detektion amniotic_sac /
  calf_legs mit Konfidenz > 0.80 -> SOFORT-Alarm, uebersteuert Zeitfenster
  und Cooldown.

## 4. Konfiguration (Auszug config.yaml)

```yaml
brunst:
  aktiv: true
  winkel_schwelle_grad: 45
  zeitfenster_min: 30
  aktiv_anteil: 0.60
  abkling_anteil: 0.40
  min_messpunkte: 15
  cooldown_min: 15
  tier_klassen: [cow, horse]      # Whitelist-Entscheidung 10.10.2026
kalbung:
  override_klassen: [amniotic_sac, calf_legs]
  override_konfidenz: 0.80
```

## 5. UI-Texte (Telegram)

- *Verdacht:* "BRUNST-VERDACHT: Kuh #<ID> zeigt seit <X> Min. erhoehten
  Schwanzwinkel (>45 Grad in <Y> % der Messungen). Besamungsfenster pruefen."
- *Abklingen:* "Brunst-Fenster bei Kuh #<ID> abgeklungen (zuletzt aktiv
  <Uhrzeit>)."
- *Stoerung:* "Keine Pose-Daten fuer Kuh #<ID> seit <X> Min - Kamera oder
  Tracking pruefen."
- *Sofort-Alarm (Kalbung, unveraendert):* "SOFORT-ALARM: Fruchtblase bei
  Kuh #<ID> erkannt!"

## 6. Abnahmekriterien (Beweispflicht: am realen Geraet/Stream)

- **A1 Goldstandard Brunst:** Referenzdatensatz
  `brunst_referenz/20261009_abend` (180 Bilder, nutzerbestaetigte Brunst,
  siehe MANIFEST.md) -> Verdacht spaetestens 30 Min nach Beginn der
  Brunstzeichen im Replay.
- **A2 Negativ-Set:** Normalaufnahmen (liegende Kuhe, Kotabsatz,
  Fliegenwedeln) -> 0 Fehlalarme pro Nacht.
- **A3 Beweispflicht:** Jeder Alarm-Text-Exemplar enthaelt Snapshot mit
  Keypoints, Tier-ID, Evidenzdauer.
- **A4 Cooldown:** keine Doppel-Alarme < 15 Min (Replay + 24 h Live).
- **A5 Ressourcen:** Analysezyklus < 60 s inkl. Pose; CPU-Temperatur < 70
  Grad C im 24-h-Betrieb (Tempguard-Schwelle 85 bleibt).
- **A6 Kalbungs-Override:** injizierte Fruchtblasen-Konfidenz > 0.80 ->
  Telegram binnen 1 Zyklus, unabhaengig von Brunzstatus.

## 7. Risiken

1. **Keypoint-Guete im IR nachts unbekannt** -> A1-Test entscheidet.
   Fallback: Detektion + Unruhe-Mass (Positionswechsel-Rate) statt Winkel.
2. **Tracking-ID-Spruenge** verteilen Evidenz auf mehrere IDs ->
   ID-Stabilitaet in A1/A4 messen; Notloesung Stall-Modus (eine Kuh, ID via
   BBox-Abstand, keine Verschmelzung von IDs im Text).
3. **CPU-Budget:** Pose + Detektion je Zyklus ggf. zu teuer -> Pose alle
   120 s (Regel in Abschnitt 2), Detektion bleibt 60 s.
4. **IR-Fehlklasse horse:** Tier-Klassen cow+horse werden als Tierereignis
   gewertet - verhindert Blindheit durch IR-Fehldeutungen (Nachtbeweis
   10.10.: Kuh wurde als horse erkannt, nur cow haette sie verloren).

## Offene Punkte bis Umsetzung

1. Pose-Modell (best.pt / Pose-ONNX) auf stallwache-lela deployen und im
   Dauerlauf anbinden (Untersuchung: welches ONNX liegt wo).
2. Goldstandard-Set mit Landwirt verfeinern: tatsaechliches Brunst-Zeitfenster
   vom 09.10. nachtragen (Fenster ist derzeit 18:00-23:59 geschaetzt).
3. Entscheidung des Landwirts zu dieser Spezifikation (v0.1).
