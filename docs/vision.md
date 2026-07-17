# Vision: Das Dritte Auge

> **Jeder Betrieb, egal wie klein, verdient eine Nachtwache, die niemals blinzelt —
> ohne 45.000 € auszugeben und ohne einen Sensor im Pansen.**

## Leitbild

Stallblick ist das **Dritte Auge** des Landwirts: Die ersten beiden schlafen
nachts, das dritte nicht. Es schaut (Live-Kameras), es versteht (KI-Erkennung
von Kalbung und Brunst) und es meldet sich genau dann — und nur dann — wenn
Handeln nötig ist.

## Die vier Ebenen

| Ebene | Modul | Versprechen |
| --- | --- | --- |
| **Sehen** | Stallblick (Zwei-Kamera-Übersicht) | In 3 Sekunden wissen, was im Stall los ist |
| **Verstehen** | Edge-Agent (YOLO-Pose, lokal) | Kalbung & Brunst erkennen, bevor es der Mensch könnte |
| **Handeln** | Alarme (Telegram + KI-Wache) | Geweckt werden, wenn es zählt — mit Beweisbildern |
| **Verbessern** | Ein-Tipp-Feedback + Nachtraining | Jeder Fehlalarm macht das System schlauer — der Landwirt trainiert sein eigenes Modell, keine Blackbox |

Die vierte Ebene ist der strukturelle Unterschied zu jedem Wettbewerber:
SaaS-Systeme trainieren zentral, DIY-Tools haben keinen Feedback-Kanal —
nur Stallblick besitzt die offene Kette Kamera → Modell → Training beim
Betrieb selbst. Dazu gehört auch die Ehrlichkeit der Wache über sich selbst:
Fällt ein Stream aus, meldet sich das dritte Auge („blind"), statt dass
Schweigen fälschlich „alles ruhig" bedeutet.

## Prinzipien (nicht verhandelbar)

1. **0 € pro Kuh und Jahr.** Vorhandene Kameras, ausgemusterte Rechner,
   kostenlose Trainings-Infrastruktur (Colab, CVAT, offene Datensätze).
2. **Edge-First.** Video verlässt den Hof nicht; nur Ereignisse gehen ins Netz.
   Datenhoheit ist Feature, nicht Fußnote.
3. **Ruhe vor Fülle.** Jeder Alarm muss eine Handlung auslösen können; alles
   andere ist Rauschen und fliegt raus. Lieber ein Tagesbericht als zehn Pings.
4. **Offen statt Abo.** Der ganze Stack ist im Repo nachvollziehbar. Wer einen
   alten Laptop und eine Kamera hat, kann morgen anfangen.
5. **Tierwohl ohne Eingriff.** Keine Boli, keine Ohrmarken-Pflicht, keine
   angeklemmten Sensoren — die Kamera sieht, das Tier bleibt unberührt.

## Nordstern-Metriken

- **Keine verpasste Kalbung**: Jede Austreibungsphase erzeugt einen Alarm,
  bevor ein Mensch sie bemerkt hätte.
- **< 30 Sekunden** von „Handy vibriert" bis „informierte Entscheidung"
  (Bildserie + Klartext-Nachricht machen den Stallgang oft unnötig).
- **< 1 Fehlalarm pro Nacht** im eingeschwungenen Zustand (Zeitfilter,
  Eskalationslogik, Negativ-Training).

## Zielbild 12 Monate

1. **Q3:** Silent-Mode-Datensammlung auf dem Hof, erstes eigenes Modell
   (CVAT + Colab), Analyse-Modus produktiv auf der Stallwache.
2. **Q4:** Brunst-Erkennung mit Zwei-Kamera-Plausibilisierung; Ereignis-Historie
   persistent; Tagesbericht als fester Rhythmus.
3. **Q1+:** Lahmheits-Frühwarnung aus der Rückenlinie (Daten fallen ohnehin an),
   Anbindung an Herdenmanagement optional — als Export, nie als Lock-in.

## Stand Juli 2026: gebaut oder baubar

Die Software-Seite des Zielbilds ist fertig oder entscheidungsreif — jede
Idee hat den Zustand „gebaut" oder „implementierungsreif spezifiziert",
nichts ist halb:

- **Gebaut:** Zwei-Kamera-App mit Login, KI-Wache-Dashboard, Edge-Agent
  (Silent Mode, Erkennungslogik, Eskalation, Tagesbericht, Wach-Modus,
  Stream-Totmann-Meldung, Ein-Tipp-Feedback), kuh-getuntes ByteTrack,
  Termux-Bridge mit Ein-Befehl-Installer, Edge-Setup-Skript,
  selbstaktivierende Ereignis-Persistenz (KV-Adapter).
- **Spezifiziert** (je mit Schwellen, Config, Alarmtexten, Abnahmekriterien):
  Festliege-Wächter, Zwei-Kamera-Brunst-Fusion, Kalbe-Akte,
  Lahmheits-Frühwarnung — alle Anforderungen an das 2. Modelltraining
  sind im Skill `modell-training` gebündelt.
- **Arbeitsmodell dahinter — die Spezifikations-Pipeline:** Marktbefund
  (`markt-analyst`) → Produktentscheidung (Orchestrator, dokumentiert in
  `wettbewerbsanalyse.md`) → Fachspezifikation (`ki-wache`) → Code erst,
  wenn die Voraussetzung real ist. Blockierte Ideen werden spezifiziert
  statt halb gebaut.

Der Weg zum scharfen System führt jetzt über drei Schritte des Betriebs:
Bridge ans Netz (Skill `stallwache-live-schalten`), KV-Store verknüpfen,
nach 1–2 Wochen Bildern das erste Training (Skill `modell-training`).

## Nicht-Ziele

Keine Cloud-Videoanalyse, kein Hardware-Verkauf, kein Abo-Modell, keine
Galerie mit 16 Kamerakacheln, keine Statistik-Dashboards ohne Handlungswert.
**Kein Ablamm-Monitoring (Schaf/Ziege):** Wolle verdeckt die Rückenlinie,
kupierte Schwänze nehmen das Leitsignal, Gruppen-Lammzeiten entwerten den
buchtbasierten Alarm — technisch wie ökonomisch kein Stallblick-Terrain.

## Zweitmarkt-Option: Abfohl-Überwachung (nach Modell v1)

Nachbarmarkt-Analyse Juli 2026 (Marktzahlen Stand ~01/2026, Live-Verifikation
im Nov-Check): Der Pferdemarkt hat exakt unsere Zielkunden-DNA — kleiner
Züchter, Boxenkamera vorhanden, nächtliches Selber-Gucken — und akzeptiert
500–1.500 € für **invasive** Sensorik (Foalert: an die Vulva genähter
Kontakt; Birth Alarm: Obergurt-Lagesensor), während ein offenes
Edge-Kamera-KI-Produkt fehlt. Unsere **Logik-Schicht ist tierartagnostisch**
(Zeitfilter, Eskalation, Totmann, Feedback — alles Konfiguration, nichts
weiß von Kühen), und der spezifizierte Festliege-Wächter (Seitenlage) ist
funktional bereits die Birth-Alarm-Logik. **Entscheidung:** dokumentierte
Option, frühestens nach stabilem Rinder-Betrieb (neues Modell + dichteres
Sampling nötig — Austreibung dauert beim Pferd Minuten, nicht Stunden, und
„Red Bag" ist ein Minuten-Notfall). Bis dahin gilt als Leitplanke: keine
Rind-Hardcodierung im Edge-Agenten neu einführen.

---

## Arbeitsorganisation (Agenten & Skills)

Das Projekt wird von spezialisierten Agenten und Skills getragen — jede
wiederkehrende Aufgabe hat einen benannten Zuständigen:

| Zuständigkeit | Werkzeug | Wann |
| --- | --- | --- |
| Markt beobachten | Agent `markt-analyst` + Skill `wettbewerbs-check` | quartalsweise / auf Zuruf |
| Qualität sichern | Agent `qa-waechter` + Skill `ki-wache-smoketest` | vor jedem Merge |
| Erkennungslogik hüten | Agent `ki-wache` | bei jeder Änderung an Schwellenwerten/Logik |
| Modell trainieren | Skill `modell-training` | sobald die Bridge läuft; danach bei Fehlalarm-Häufung |
| Fehlalarme in Trainingsdaten verwandeln | Skill `fehlalarm-triage` | im Analyse-Modus, wöchentlich |
| Kuh-Identität stabil halten (Tracking) | Skill `bytetrack-tuning` | nach dem Scharfschalten; bei ID-Flackern oder ausbleibenden Alarmen |
| Sicherheit härten | Skill `security-sweep` | vor Releases / nach neuen API-Routen |
| Ausliefern | Skill `stallblick-deploy` | nach jedem Feature |
| Futterwache-Cloud | Skill `tuya-futterwache` | sobald Tuya-Zugangsdaten vorliegen |
| Stallwache live schalten | Skill `stallwache-live-schalten` | sobald der Tunnel-Hostname gemeldet ist |

Regel: Der Hauptagent orchestriert und entscheidet; Subagenten recherchieren
und prüfen. Produktentscheidungen landen immer in
`docs/wettbewerbsanalyse.md` (Was/Warum) — Code folgt Entscheidung, nie umgekehrt.
Das vollständige Koordinationshandbuch (Rollen, Delegations-Entscheidung,
Muster): [`docs/agenten-orchestrierung.md`](./agenten-orchestrierung.md).
