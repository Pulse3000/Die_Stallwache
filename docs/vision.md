# Vision: Das Dritte Auge

> **Jeder Betrieb, egal wie klein, verdient eine Nachtwache, die niemals blinzelt —
> ohne 45.000 € auszugeben und ohne einen Sensor im Pansen.**

## Leitbild

Stallblick ist das **Dritte Auge** des Landwirts: Die ersten beiden schlafen
nachts, das dritte nicht. Es schaut (Live-Kameras), es versteht (KI-Erkennung
von Kalbung und Brunst) und es meldet sich genau dann — und nur dann — wenn
Handeln nötig ist.

## Die fünf Ebenen

| Ebene | Modul | Versprechen |
| --- | --- | --- |
| **Sehen** | Stallblick (Vier-Kamera-Übersicht) | In 3 Sekunden wissen, was im Stall los ist |
| **Verstehen** | Edge-Agent (YOLO-Pose, lokal) | Kalbung & Brunst erkennen, bevor es der Mensch könnte |
| **Handeln** | Alarme (Telegram + Push + KI-Wache) | Geweckt werden, wenn es zählt — mit Beweisbildern, und so lange, bis jemand bestätigt |
| **Durchhalten** | PWA-Cache, Aktions-Warteschlange, Agent-Puffer | Der Alarm kommt an, **auch wenn das Netz zusammenbricht** |
| **Verbessern** | Ein-Tipp-Feedback + Nachtraining | Jeder Fehlalarm macht das System schlauer — der Landwirt trainiert sein eigenes Modell, keine Blackbox |

Die letzte Ebene ist der strukturelle Unterschied zu jedem Wettbewerber:
SaaS-Systeme trainieren zentral, DIY-Tools haben keinen Feedback-Kanal —
nur Stallblick besitzt die offene Kette Kamera → Modell → Training beim
Betrieb selbst.

**Warum „Durchhalten" eine eigene Ebene ist.** Die ersten drei Ebenen
unterstellen stillschweigend, dass die Kette hält. Sie hält aber am
schlechtesten genau dann, wenn sie gebraucht wird: nachts, im Stall, wo der
Empfang des Betriebs am schwächsten ist. Ein System, das nur bei gutem Netz
warnt, warnt nicht — es warnt *manchmal*, und das ist schlimmer, weil man
sich darauf verlässt. Deshalb puffert der Agent auf der Platte und liefert
mit dem **ursprünglichen** Zeitstempel nach (die Kalbung war um 03:12, nicht
um 07:40), deshalb bleibt die App im Funkloch lesbar und bedienbar, und
deshalb meldet sich das dritte Auge bei Stream-Ausfall selbst als „blind",
statt dass Schweigen fälschlich „alles ruhig" bedeutet.

## Prinzipien (nicht verhandelbar)

1. **0 € pro Kuh und Jahr.** Vorhandene Kameras, ausgemusterte Rechner,
   kostenlose Trainings-Infrastruktur (Colab, CVAT, offene Datensätze).
   Ehrlich dazugesagt: Der lokale Weckkanal (Prinzip 8) ist die **einzige**
   Stufe, für die ein Betrieb Hardware kaufen muss, die er nicht hat — rund
   **24–66 € einmalig**, gegen 100–660 € in der Nachbarkategorie. Die Aussage
   lautet deshalb „Software 0 €, Weckhardware ab 24 €, laufend 0 €/Kuh/Jahr"
   und nicht „0 €, du hast schon alles". Die Zahl selbst zu nennen ist
   stärker, als sie den Betrieb beim Aufbau entdecken zu lassen.
2. **Edge-First.** Video verlässt den Hof nicht; nur Ereignisse gehen ins Netz.
   Datenhoheit ist Feature, nicht Fußnote.
3. **Ruhe vor Fülle.** Jeder Alarm muss eine Handlung auslösen können; alles
   andere ist Rauschen und fliegt raus. Lieber ein Tagesbericht als zehn Pings.
4. **Offen statt Abo.** Der ganze Stack ist im Repo nachvollziehbar. Wer einen
   alten Laptop und eine Kamera hat, kann morgen anfangen.
5. **Tierwohl ohne Eingriff.** Keine Boli, keine Ohrmarken-Pflicht, keine
   angeklemmten Sensoren — die Kamera sieht, das Tier bleibt unberührt.
6. **Stille Ausfälle sind der eigentliche Gegner.** Ein System, das nicht
   funktioniert, aber so aussieht, ist gefährlicher als eines, das sichtbar
   ausfällt — es ersetzt echte Wachsamkeit durch falsches Vertrauen. Jeder
   Baustein muss deshalb entweder laut ausfallen oder seinen Zustand zeigen:
   „offline, letzter Stand von 21:40", „Push nicht eingerichtet", „das dritte
   Auge ist blind". Und jede Inbetriebnahme endet mit einem **Beweis am
   echten Gerät**, nicht mit einer gesetzten Variablen — dafür gibt es den
   Probealarm und die Scharfschalt-Skills.
7. **Der Alarm gehört dem Landwirt.** Er entscheidet, was ihn nachts weckt:
   Dringlichkeit nur für die Austreibung, Alarmarten pro Gerät abwählbar,
   jeder Alarm quittierbar. Nachgelieferte Ereignisse aus einem Funkloch
   wandern still ins Protokoll statt vierzigmal zu klingeln — Alarmmüdigkeit
   kostet mehr als eine spät gelesene Meldung.
8. **Gesendet ist nicht angekommen — die Kette endet am wachen Menschen.**
   Die ganze Branche hört beim Absenden auf: Erkennung, Push, fertig. Aber
   Schweigen ist zweideutig — „gesehen und für harmlos befunden" und
   „durchgeschlafen" sehen von außen identisch aus. Nur die **Quittierung**
   löst diese Zweideutigkeit auf. Deshalb wird ein unbestätigter dringender
   Alarm nicht leiser, sondern hartnäckiger: Wiederholung, zweiter Mensch,
   und zuletzt ein Weckton, der ohne Internet auskommt. Das ist die einzige
   Stelle, an der das System die Ruhe des Landwirts bewusst übergeht — und
   sie ist mit Prinzip 7 vereinbar, weil sie **niemanden zusätzlich
   alarmiert, der reagiert hat**. Die zusätzliche Lautstärke bezahlt nur, wer
   nicht antwortet.

   Zwei Konsequenzen, die nicht verhandelbar sind: Der Weckkanal liegt
   **lokal** (MQTT im Hof-LAN, nicht in der Cloud, die mit derselben Leitung
   ausfällt), und das Weckgerät hängt **im Wohnhaus, nicht im Stall** — Stress
   im Stadium II hemmt die Oxytocin-Ausschüttung, ein Ton über der kalbenden
   Kuh gefährdet genau das Kalb, das der Alarm retten soll (Prinzip 5).

## Nordstern-Metriken

- **Keine verpasste Kalbung**: Jede Austreibungsphase erzeugt einen Alarm,
  bevor ein Mensch sie bemerkt hätte.
- **< 30 Sekunden** von „Handy vibriert" bis „informierte Entscheidung"
  (Bildserie + Klartext-Nachricht machen den Stallgang oft unnötig).
- **< 1 Fehlalarm pro Nacht** im eingeschwungenen Zustand (Zeitfilter,
  Eskalationslogik, Negativ-Training).
- **Die Kette ist jederzeit beweisbar**: Ein Probealarm erreicht den
  gesperrten Bildschirm — auf Zuruf, nicht erst im Ernstfall. Was sich nicht
  vorführen lässt, gilt als nicht scharf.

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
  Tuya-Cloud-Anbindung aller Kameras (ohne Gerät im Stall), Edge-Setup-Skript,
- **Gebaut:** installierbare PWA mit vier Bereichen (Dashboard, Alarme,
  Steuerung, Einstellungen) über vier Kameras, Push-Alarme via FCM mit
  Bild-Replay und Quittierung, Offline-Betrieb auf beiden Seiten
  (App-Cache + Aktions-Warteschlange, Agent-Plattenpuffer mit Nachlieferung),
  Tuya-Gerätesteuerung, Freitext-/Sprachanfragen, KI-Wache-Dashboard,
  Edge-Agent (Silent Mode, Erkennungslogik, Eskalation, Tagesbericht,
  Wach-Modus, Stream-Totmann-Meldung, Ein-Tipp-Feedback), kuh-getuntes
  ByteTrack, Termux-Bridge mit Ein-Befehl-Installer, Edge-Setup-Skript,
  selbstaktivierende Ereignis-Persistenz (KV-Adapter).
- **Spezifiziert** (je mit Schwellen, Config, Alarmtexten, Abnahmekriterien):
  Festliege-Wächter, Zwei-Kamera-Brunst-Fusion, Kalbe-Akte,
  Lahmheits-Frühwarnung — alle Anforderungen an das 2. Modelltraining
  sind im Skill `modell-training` gebündelt — sowie die
  **quittierungs-getriebene Nacht-Eskalation** samt lokalem Weckkanal
  (Prinzip 8); sie hängt als einzige nicht am Modell, sondern nur an der
  Ereignis-Persistenz. Der Weg von einer Spezifikation zu gemergtem Code ist
  selbst eine Prozedur: Skill `spezifikation-umsetzen`.
- **Arbeitsmodell dahinter — die Spezifikations-Pipeline:** Marktbefund
  (`markt-analyst`) → Produktentscheidung (Orchestrator, dokumentiert in
  `wettbewerbsanalyse.md`) → Fachspezifikation (`ki-wache`) → Code erst,
  wenn die Voraussetzung real ist. Blockierte Ideen werden spezifiziert
  statt halb gebaut.

Der Weg zum scharfen System führt jetzt über drei Schritte des Betriebs:
Kameras in der Tuya-Cloud verknüpfen und die `TUYA_*`-Variablen setzen (Skill
`tuya-futterwache`), KV-Store verknüpfen, nach 1–2 Wochen Bildern das erste
Training (Skill `modell-training`).
Der Weg zum scharfen System führt über vier Schritte des Betriebs — alle
vier sind reine Konfiguration, kein Code mehr: Bridge ans Netz (Skill
`stallwache-live-schalten`), KV-Store verknüpfen (Skill
`persistenz-live-schalten`), Firebase eintragen und Probealarm bestehen
(Skill `push-live-schalten`), nach 1–2 Wochen Bildern das erste Training
(Skill `modell-training`). Solange Schritt 3 fehlt, ist die Nachtwache
gebaut, aber stumm — sie zeigt Alarme nur dem, der von selbst nachsieht.

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
| Modell trainieren | Skill `modell-training` | sobald die Kameras live sind; danach bei Fehlalarm-Häufung |
| Fehlalarme in Trainingsdaten verwandeln | Skill `fehlalarm-triage` | im Analyse-Modus, wöchentlich |
| Kuh-Identität stabil halten (Tracking) | Skill `bytetrack-tuning` | nach dem Scharfschalten; bei ID-Flackern oder ausbleibenden Alarmen |
| Sicherheit härten | Skill `security-sweep` | vor Releases / nach neuen API-Routen |
| Ausliefern | Skill `stallblick-deploy` | nach jedem Feature |
| Futterwache-Cloud | Skill `tuya-futterwache` | sobald Tuya-Zugangsdaten vorliegen |
| Stallwache live schalten | Skill `stallwache-live-schalten` | sobald der Tunnel-Hostname gemeldet ist |
| Persistenz live schalten | Skill `persistenz-live-schalten` | sobald der KV-Store verknüpft ist |
| Bereitschaft feststellen | Skill `betriebs-bereitschaft` | nach jedem Deploy, vor jeder Übergabe |
| Push live schalten | Skill `push-live-schalten` | sobald Firebase eingerichtet ist; Nachtprobe einmalig |
| GCP anbinden (Pub/Sub, Vertex) | Skill `gcp-anbindung` | sobald das Dienstkonto steht |
| PWA abnehmen | Skill `pwa-abnahme` | nach Änderungen am Service Worker, Offline-Puffer, Manifest oder den vier Bereichen |
| Kamera aufnehmen | Skill `neue-kamera` | wenn der Betrieb um eine Kamera wächst |
| Tuya-Störung eingrenzen | Skill `tuya-diagnose` | bei „sign invalid", „clientId is invalid", schwarzem Livebild |

Regel: Der Hauptagent orchestriert und entscheidet; Subagenten recherchieren
und prüfen. Produktentscheidungen landen immer in
`docs/wettbewerbsanalyse.md` (Was/Warum) — Code folgt Entscheidung, nie umgekehrt.
Das vollständige Koordinationshandbuch (Rollen, Delegations-Entscheidung,
Muster): [`docs/agenten-orchestrierung.md`](./agenten-orchestrierung.md).
