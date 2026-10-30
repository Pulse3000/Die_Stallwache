# Entscheidung: Brunst zuerst, Kalbeüberwachung danach

Stand: 30.10.2026 · Entscheidung des Betreibers (29.10.2026): „Zuerst fangen
wir mit der Brunsterkennung an und dem Aufsprungverhalten der Kühe, die
Kalb-Überwachung und Kalb-Erkennung kommt erst danach.“
**Status: im Repo umgesetzt (Trainingsweg, Abnahme, ehrliche Statusmeldung),
fachlich geprüft (`ki-wache`, 30.10.2026). Am Gerät nichts scharf: Vor dem
Scharfschalten sind die Punkte in Abschnitt 9 offen.**

## 1. Grundsatz

1. **Das erste eigene Modell (v1) kennt nur Kühe.** Eine Klasse `kuh`, nur
   Boxen (YOLOv8n-Detection), getrackt mit ByteTrack. Daraus erkennt der
   Agent das **Aufsprungverhalten** mit der bestehenden, unveränderten Regel
   (`aufsprung_oben` in `edge-agent/main.py`, genutzt von
   `LogicEngine._brunst`). Die Regel greift, wenn zwei getrackte Kuh-Boxen
   sich überlappen (IoU ≥ 0,15) und die obere mindestens 20 % der Boxhöhe
   höher ansetzt, und zwar mindestens `logik.brunst_min_dauer_s` (4 s) lang.
2. **Was v1 nicht kann, wird nicht behauptet.** Austreibung (Fruchtblase,
   Kälberfüße) und Kalbeverdacht (Schwanzwinkel) brauchen Klassen bzw.
   Keypoints, die v1 nicht hat. Der Agent erkennt das selbst
   (`nicht_scharf()`) und meldet es an drei Stellen:
   - **Startmeldung:** „Scharf: Brunst (Aufsprung) · NICHT scharf: Austreibung
     (Fruchtblase/Kälberfüße), Kalbeverdacht (Schwanzwinkel). Kalbungen
     erkennt die KI damit nicht – bitte wie bisher selbst kontrollieren.“
   - **Tagesbericht:** „Austreibung: nicht überwacht“ statt „0“; eine 0 läse
     sich wie „keine Geburt“.
   - **Lebenszeichen** als `nicht_scharf`. Die Statusabfrage sagt für diese
     Kamera dann **nie „OK“**, sondern `UNBEKANNT` mit Grund und dem Stand
     der Brunst-Erkennung. Offene Brunstverdachte bleiben `WARNUNG`.
3. **Freigabe ist ausdrücklich.** `modell.freigegeben` in `config.yaml`
   überträgt das Abnahmeergebnis.
   - Fehlt der Eintrag, gilt nichts als scharf, und der Agent warnt beim Start.
   - Weiß der Agent nicht, was das Modell kann, gilt ebenfalls nichts als
     scharf.
   - Der Eintrag meldet nur und unterdrückt keine Erkennung: Recall vor allem.
4. **Ein Modell ehrlich durch Konstruktion.** Der Datensatz der Brunst-Phase
   (`edge-agent/training/stall-brunst.yaml`) enthält nur `kuh`. Ein Modell,
   das die Namen `amniotic_sac`/`calf_legs` trägt, ohne sie gelernt zu haben,
   sähe sonst wie eine scharfe Kalbeüberwachung aus.

## 2. Fachlicher Widerspruch (Widerspruchspflicht)

**Kalbung ist der Notfall, Brunst ist planbar.** Das Besamungsfenster ist
8–18 h breit; eine verpasste Austreibung kann Kalb und Kuh kosten. Mit
„Brunst zuerst“ überwacht die KI in dieser Phase **keine Geburt**. Die
Entscheidung trägt nur unter zwei Bedingungen:
1. Die bisherige menschliche Kalbeüberwachung läuft unverändert weiter.
2. Die App zeigt das unmissverständlich (Grundsatz 2).

**Aufsprünge sind kurz, die Regel verlangt fünf Bilder am Stück.**
- Ein Aufsprung dauert typischerweise wenige Sekunden. Der Literaturwert aus
  Drucksensor-Studien liegt bei etwa 3 s; Betreiber oder Tierarzt sollten ihn
  bestätigen.
- Bei 1 Bild/s müssen beide Kühe in fünf Bildern hintereinander erkannt
  sein, stabile Nummern tragen und übereinander liegen.
- Ein fehlendes Bild oder ein Nummernwechsel startet die Zeit neu. Eine neue
  Spur gibt Ultralytics erst im zweiten Bild aus. Kurze Aufsprünge fallen
  deshalb heraus.
- Wie viele Brunsten tatsächlich erkannt werden, misst erst der
  Feldvergleich (Abschnitt 9, B1).

**Ohne Laufbereich kein Aufsprung.** In Anbindehaltung gibt es keinen,
in kleinen Gruppen deutlich weniger. Viele Aufsprünge fallen in die Nacht,
dann entscheidet die IR-Bildqualität.

**Die Stallwache ist die Kamera am Abkalbebereich.** Hochtragende und
frisch abgekalbte Kühe zeigen praktisch keine Brunst. Gleichzeitig liegen
dort die typischen Fehlalarme. `ki-wache` hat sie an ausgedachten Boxen
nachgerechnet, nicht gemessen; alle erfüllen die Regel und können
minutenlang anhalten:

| Fall | IoU |
| --- | --- |
| Kalb am Euter (das Kalb wird als brünstige Kuh gemeldet) | ≈ 0,17 |
| Kuh hinter Kuh in Tiefenstaffelung | ≈ 0,31 |
| Doppelbox derselben Kuh | ≈ 0,44 |

**Stichprobe der Stallwache-Bilder vom 27.10.2026.** Drei Bilder aus der
Google-Drive-Ablage (05:41, 10:02 und 22:59 Uhr) zeigen:
- **Kühe nur am Rand.** Die Kamera blickt auf Futtertisch, Fressgitter und
  Strohlager. Kühe sind nur am unteren Rand am Gitter zu sehen. Der
  Laufbereich, in dem Aufsprünge passieren, ist nicht im Bild. Um 22:59 Uhr
  ist keine Kuh zu sehen.
- **Etwas hängt vor dem Objektiv.** Ein weißer Kasten mit Kabel hängt vor
  der Linse, nachts grell vom IR-Licht angestrahlt, dazu ein Faden oder
  Spinnennetz.
- **Bildfehler.** Blockartige Fehler im Bild deuten auf verlorene
  Datenpakete hin.
- **Uhrzeit weicht ab.** Die eingeblendete Uhrzeit liegt 53–57 min hinter
  dem Dateinamen.
- **Auflösung stimmt:** 2560×1440, also 2K.

**Folge:** Vor dem Labeln die Kamera auf den Laufbereich der
besamungsfähigen Gruppe richten. Ist das an der Stallwache nicht möglich,
läuft die Brunst-Phase auf einer anderen Kamera.

**Im Analyse-Modus endet die Datensammlung.** Trainingsbilder speichert der
Agent nur im Silent Mode. Jede Geburt während der Brunst-Phase fehlt damit
dem Kalbe-Modell der Phase 2. Läuft das Brunst-Modell an der Stallwache, muss
der Betreiber entscheiden: entweder parallel weitersammeln (eigene
Entscheidung, Code nötig), oder die Brunst-Phase nur an einer Kamera ohne
Abkalbebereich betreiben.

**Im Training fehlen Aufsprung-Bilder.** Bei einem Bild alle 120 s landen pro
Brunst im Mittel 0,1–0,25 Aufsprung-Bilder im Datensatz. Die aufgerichtete
Kuh ist für das Modell unbekannt. Gate Ü (Abschnitt 4) braucht deshalb
Bilder aus echten Aufsprung-Videos; eng stehende Kühe genügen nicht.

**Nummern tauschen beim Aufsprung am ehesten.** Das ist der Moment mit der
größten Bewegung und Überdeckung. Ein Tausch nennt die falsche Kuh als
brünstig; die Folgen sind falsche Besamung, verpasste Brunst und drei Wochen
Verlust. Maßgeblich ist das Alarmbild: Der rote Kasten sitzt immer auf der
geometrisch unteren, also duldenden Kuh. Name und Nummer im Text können
falsch sein (Abschnitt 9, B6).

**Alternative für später:** eine eigene Klasse `aufsprung` mit einer Box um
das Paar. Sie ist robuster gegen NMS und Nummerntausch, braucht aber gelabelte
Aufsprünge.

## 3. Grenzen

- Brunst nur über Aufsprung. Duldung ohne Aufsprung, Unruhe und
  Schwanzwedeln gehören nicht zu v1. Die Brunst-Verhaltensschicht v0.1 mit
  Schwanzwinkel braucht Keypoints und kommt in Phase 2.
- Kuh-Nummern sind Tracker-Nummern, keine Ohrmarken. Namen vergibt der
  Landwirt per Telegram (`/kuh 12 Berta`, `docs/kuh-namen-spezifikation.md`).
- Saugkälber erfüllen die Regel am Euter (Abschnitt 2). Labelregel (Vorschlag
  `ki-wache`, Betreiber entscheidet): Saugkälber nicht als `kuh` labeln,
  Färsen schon, weil ihre Brunst zählt.

## 4. Schwellenwerte

| Wert | Größe | Herkunft |
| --- | --- | --- |
| Aufsprung IoU | ≥ 0,15 | `aufsprung_oben`, unverändert |
| Höhenversatz | ≥ 20 % der Boxhöhe | ebenda |
| Mindestdauer | `logik.brunst_min_dauer_s` = 4 s | Referenzwert |
| Paar stumm nach Meldung | 1 h | ebenda |
| Gate K Kuh-Recall | ≥ 90 % bei Konfidenz ≥ 0,5, n ≥ 100 | `ki-wache`; 0,5 = `new_track_thresh` (Test koppelt beide) |
| Gate K-Nacht | wie K, nur IR-Nachtbilder, n ≥ 30 | `ki-wache`, von Hand |
| Gate Ü Aufsprung-Lage | beide Kühe erkannt **und** erkannte Lage wie beim Aufsprung, ≥ 90 %, n ≥ 20 Paare; Paare ab IoU 0,5 getrennt ausgewiesen | `ki-wache`; nutzt `aufsprung_oben` |
| Gate D Doppelboxen | ≤ 2 % der Kühe mit zweiter Box (IoU ≥ 0,3) | `ki-wache` |
| Gate E Ende zu Ende | ≥ 4 von 5 echten Aufsprung-Szenen (Video mit 1 Bild/s) ergeben einen Alarm mit der richtigen unteren Kuh | `ki-wache`, von Hand |

Begründung der Stichproben: 27 von 30 belegen nur eine Rate ≥ 0,76
(einseitige 95-%-Untergrenze). Bei 5 Paaren bestünde eine wahre Rate von 60 %
das Gate in 34 % der Fälle, bei 20 Paaren in 5 %. Die NMS-Grenze von
Ultralytics (0,7) bleibt; höher hieße mehr Doppelboxen. Die Werte bestätigt
der Betreiber; bis dahin gelten sie.

## 5. Konfiguration (Stall-Rechner, Brunst-Phase)

```yaml
modell:
  pfad: best_v1.pt
  tier_klassen: [kuh]
  freigegeben: [brunst]   # erst wenn K, Ü, D und E bestanden; vorher []
```

`modell.klassen` **nicht** kürzen. Das Modell meldet selbst, welche Klassen
es kennt, und `nicht_scharf` wertet das aus. Gekürzte Klassen wären eine
Falle für Phase 2: Der Tracker würde Fruchtblase und Kälberfüße schon vor
der Logik wegfiltern.

## 6. Ablauf für den Betreiber: Silent Mode beenden, Training beginnen

Der Silent Mode endet nur auf eine Art: Ein abgenommenes Modell steht in
`modell.pfad`. Bis dahin sammelt der Agent weiter, und das ist gut so.

0. **Kamera prüfen:**
   - Laufbereich der besamungsfähigen Gruppe im Bild?
   - Nichts vor dem Objektiv?
   - Uhr richtig?

   Siehe Abschnitt 2, Stichprobe.
1. **Bestand prüfen** (Stall-Rechner):
   `python3 edge-agent/training/datensatz.py bilanz ./aufnahmen`. Gefordert
   ist mindestens ⅓ IR-Nacht (Beschluss B9).
2. **Ausdünnen:**
   `python3 edge-agent/training/datensatz.py ausduennen ./aufnahmen ./auswahl`.
3. **Labeln in CVAT** (app.cvat.ai, kostenlos):
   - Label `kuh` als Rechteck, jede Kuh einzeln.
   - Zusätzlich Bilder aus echten Aufsprung-Videos (Gate Ü), für den Fall E
     als Video mit 1 Bild/s aufheben.
   - Export „Ultralytics YOLO Detection“.
4. **Teilen nach Stalltagen:**
   `python3 edge-agent/training/datensatz.py split ./cvat-export ./datensatz`.
5. **Colab** (`edge-agent/training/colab_training.py`, `PHASE = "brunst"`):
   trainiert YOLOv8n (COCO-vortrainiert) auf `stall-brunst.yaml`.
6. **Abnahme:**
   - `python3 abnahme.py best_v1.pt datensatz --phase brunst` prüft K, Ü
     und D automatisch.
   - Von Hand: K-Nacht, E, 24-h-Test 3b und die Laufzeit (`--nur-fps` am
     Stall-Rechner).
7. **Scharfschalten:**
   - Konfiguration aus Abschnitt 5, dann
     `ANALYSE=1 docker compose up -d --build`.
   - Startmeldung prüfen.
   - Vorher Abschnitt 9 erledigen.

## 7. Abnahmekriterien (dieser Entscheidung)

Automatisch (vor dem Merge):
1. `edge-agent/tests/test_aufloesung_umfang.py`:
   - Brunst-Modell: Austreibung und Kalbeverdacht nicht scharf.
   - COCO-Modell (Index 1/2 = bicycle/car): Austreibung nicht scharf.
   - Unbekanntes Modell (`names`/`task` = None) und fehlendes `freigegeben`:
     nichts bzw. Kalbeverdacht nicht scharf.
   - Tagesbericht: „nicht überwacht“.
   - Lebenszeichen meldet `nicht_scharf`.
2. `tests/stall-status.test.ts` 24–24g:
   - Mit `nicht_scharf` nie „OK“.
   - Brunst-Stand im Text nur mit KV.
   - Unbekannte oder kaputte Werte, auch aus der KV, ergeben „Umfang
     unklar“, nie „OK“ und kein Absturz.
3. `edge-agent/tests/test_training.py`:
   - Gates K, Ü (Regel des Agenten, keine Kopie) und D, mit Exit-Codes und
     Bericht.
   - Die Kopplung an `new_track_thresh`.

Am Gerät (Beweispflicht, erst mit v1):
4. Startmeldung und Tagesbericht nennen den Umfang wie oben.
5. Statusabfrage für die Kamera:
   `UNBEKANNT – Austreibung …, Kalbeverdacht … nicht scharf – das Modell ist
   dafür nicht abgenommen; Kalbungen bitte wie bisher selbst kontrollieren.
   Brunst (Aufsprung): keine offenen Meldungen …`, nie `OK`.
6. Gate E: echte Aufsprünge im 1-Bild/s-Replay erkannt.
7. 24 h Live: ≤ 1 falscher Brunstverdacht.

## 8. Risiken

1. **Falsches Sicherheitsgefühl bei der Kalbung.** Gegenmittel ist
   Grundsatz 2. Restrisiko: Die Startmeldung geht bisher nur ans Dashboard
   und nicht per Telegram (B4 in Abschnitt 9).
2. **Aufsprung-Regel passt nicht zur Kameraposition.** Bei Draufsicht heißt
   „höher im Bild“ „weiter hinten“. Gegenmittel: Kamera richten, Gate E.
3. **NMS schluckt die zweite Kuh.** Das Risiko ist bei Seitenansicht
   kleiner als vermutet (IoU beim Aufsprung etwa 0,3–0,45), bei Ansicht von
   hinten größer. Gegenmittel: Gate Ü mit getrennt ausgewiesenen engen
   Paaren.
4. **Doppelbox, Kalb am Euter, Tiefenstaffelung** lösen die Regel aus.
   Gegenmittel: Gate D, Labelregel Saugkälber, Kamera nicht auf den
   Abkalbebereich.
5. **Nachtraining nach Fehlalarmen beschädigt das Kuh-Modell.** Brunst-
   Fehlalarme zeigen echte Kühe. Als „Background“ gelabelt (Skill
   `fehlalarm-triage`) lernt das Modell, dass überlappende Kühe kein Objekt
   sind. Deshalb in der Brunst-Phase trennen:
   - **Modellfehler** (Geisterbox, Doppelbox, Kalb als Kuh): jede Kuh korrekt
     umranden.
   - **Regelfehler** (Boxen stimmen, es war aber kein Aufsprung): nicht ins
     Training.

## 9. Vor dem Scharfschalten offen

| Nr. | Punkt | Wer |
| --- | --- | --- |
| B1 | Erfolgsmaß Brunst: Gate E und ein Feldvergleich über 4 Wochen (erkannte gegen notierte Brunsten). Vorschlag `ki-wache`: ≥ 50 % bei ≤ 1 Fehlalarm/Tag, also mindestens so gut wie Sichtbeobachtung. Der alte Goldstandard A1 (Bilder im 2-min-Takt) prüft keine 4-s-Regel | Betreiber legt das Ziel fest |
| B2 | Kamera auf die besamungsfähige Gruppe im Laufbereich, nicht auf den Abkalbebereich | Betreiber |
| B3 | Datensammlung für Phase 2 während der Brunst-Phase (parallel sammeln oder andere Kamera) | Betreiber entscheidet |
| B4 | Startmeldung „Kalbung nicht überwacht“ einmal per Telegram, nur bei geändertem Umfang oder höchstens 1× in 24 h | Code, nach Entscheidung |
| B5 | Fehlalarm-Triage in der Brunst-Phase: Modell- und Regelfehler trennen (Risiko 5) | Skill `fehlalarm-triage` anpassen |
| B6 | Aufsprung-Alarmbild mit beiden Kästen (rot: duldet, gelb: springt auf) und Hinweis „bitte im Bild prüfen“. Namen weglassen, wenn die Spur seit der Bestätigung verloren war, gesprungen ist oder stark überlappt hat | Code, eigene Spezifikation |
| – | Brunst-Alarme nachts (22–6 Uhr) still zustellen; Austreibung, Eskalation und Totmann bleiben laut | Betreiber entscheidet |
| – | Wach-Modus warnt, wenn die Austreibung nicht scharf ist (er senkt sonst nur die Brunst-Mindestdauer) | Code, klein |
