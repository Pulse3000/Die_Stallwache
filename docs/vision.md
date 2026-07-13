# Vision: Das Dritte Auge

> **Jeder Betrieb, egal wie klein, verdient eine Nachtwache, die niemals blinzelt —
> ohne 45.000 € auszugeben und ohne einen Sensor im Pansen.**

## Leitbild

Stallblick ist das **Dritte Auge** des Landwirts: Die ersten beiden schlafen
nachts, das dritte nicht. Es schaut (Live-Kameras), es versteht (KI-Erkennung
von Kalbung und Brunst) und es meldet sich genau dann — und nur dann — wenn
Handeln nötig ist.

## Die drei Ebenen

| Ebene | Modul | Versprechen |
| --- | --- | --- |
| **Sehen** | Stallblick (Zwei-Kamera-Übersicht) | In 3 Sekunden wissen, was im Stall los ist |
| **Verstehen** | Edge-Agent (YOLO-Pose, lokal) | Kalbung & Brunst erkennen, bevor es der Mensch könnte |
| **Handeln** | Alarme (Telegram + KI-Wache) | Geweckt werden, wenn es zählt — mit Beweisbildern |

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

## Nicht-Ziele

Keine Cloud-Videoanalyse, kein Hardware-Verkauf, kein Abo-Modell, keine
Galerie mit 16 Kamerakacheln, keine Statistik-Dashboards ohne Handlungswert.

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
| Sicherheit härten | Skill `security-sweep` | vor Releases / nach neuen API-Routen |
| Ausliefern | Skill `stallblick-deploy` | nach jedem Feature |
| Futterwache-Cloud | Skill `tuya-futterwache` | sobald Tuya-Zugangsdaten vorliegen |

Regel: Der Hauptagent orchestriert und entscheidet; Subagenten recherchieren
und prüfen. Produktentscheidungen landen immer in
`docs/wettbewerbsanalyse.md` (Was/Warum) — Code folgt Entscheidung, nie umgekehrt.
Das vollständige Koordinationshandbuch (Rollen, Delegations-Entscheidung,
Muster): [`docs/agenten-orchestrierung.md`](./agenten-orchestrierung.md).
