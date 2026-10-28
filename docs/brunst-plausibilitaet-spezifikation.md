# Spezifikation: Brunst-Plausibilität (ein Kalb ist kein Aufsprung)

Regeln für die Aufsprung-Heuristik des Edge-Agenten
(`edge-agent/main.py`, `LogicEngine._brunst` / `_aufsprung_lage`). Anlass:
Befund des Agenten `ki-wache` vom 27.10.2026 beim Review der KI-Ansicht.
Entwurf und Entscheidung: Orchestrator (28.10.2026), Prüfung: `ki-wache`
(28.10.2026, eingearbeitet). **Status: Stufe 1 umgesetzt** (Flächenverhältnis,
alle Aufsprung-Schwellen konfigurierbar und startsicher, Logiktests grün).
**Freigabe am Gerät offen** (erstes Modell, §7 G1–G3). **Stufe 2a**
(Dauerlage-Sperre) spezifiziert, ohne Daten baubar; **Stufe 2b** (Höchstdauer)
spezifiziert, blockiert (§8).

## 0. Befund

Bisherige Regel je Bild: Zwei Tier-Boxen sind eine Aufsprung-Lage, wenn
IoU ≥ 0,15 und die Oberkante der oberen Box um ≥ 20 % der Höhe der unteren
Box höher liegt. Hält die Lage ≥ 4 s, folgt `brunstverdacht` für die untere
Kuh, das Paar ist danach 1 h stumm. IoU 0,15 und 20 % standen fest im Code.

`ki-wache`: Das Modell kennt keine Klasse „Kalb“. Ein Kalb unter oder neben
der Mutter wird als `kuh` erkannt und erreicht IoU 0,21–0,37 (geometrisch
abgeschätzt, noch ohne Modell; die Messung liefert G1). Für eine
liegende Kuh dicht an einer stehenden gilt dasselbe. Beide Lagen sind
**statisch** (Minuten bis Stunden), die 4-s-Mindestdauer filtert sie also
nicht. Ein Kalb liegt nach der Geburt tagelang in der Abkalbebucht: ein
Brunst-Fehlalarm in jeder Nacht. Das verletzt „Ruhe vor Fülle“ (Ziel
< 1 Fehlalarm je Nacht, [`metriken.md`](./metriken.md)).

## 1. Entscheidung: Weg (a) jetzt, Weg (b) mit dem 2. Training

| Weg | Wirkung | Kosten | Entscheidung |
| --- | --- | --- | --- |
| **(a) Plausibilitätsprüfung ohne neues Modell:** Flächenverhältnis der beiden Boxen | wirkt ab dem ersten Modell, mit jedem Modell, für jede Tierart | eine Prüfung je Paar und Bild; Preis bei Färsen (Risiko 1) | **jetzt, Default an** |
| **(b) Klasse Kalb im Modell** | trennt Kalb und Kuh am Aussehen, unabhängig vom Kamerawinkel | Labeling und Training (Skill `modell-training`) | **nicht im 1. Training**; kommt mit `kalb_liegend`/`kalb_stehend` im 2. Training |

**Warum nicht (b) jetzt:**

1. **Blocker:** Es gibt kein Modell. Das 1. Training muss die Abnahme-Gates
   bestehen, vor allem Austreibung Recall 1,0 bei Konfidenz 0,80. Jede
   zusätzliche Klasse verlängert Labeling und Prüfung.
2. **Wenig Material:** Kälber sind nur in den Tagen nach einer Geburt im Bild.
   Eine Klasse mit wenigen Beispielen ist unzuverlässig.
3. **(b) löst nur das Kalb**, nicht die liegende Kuh.

**Label-Grenze, gilt für jedes Training mit Kalb-Boxen** (kein Grund für den
Aufschub, sondern eine Bedingung): Ultralytics vergibt je erkanntem Kasten nur
die beste Klasse (NMS-Standard `multi_label` aus, am Colab-Stand prüfen), und widersprüchliche Labels lehren das Modell, Kälberfüße im
Geburtsmoment als „kein `calf_legs`“ zu sehen. Ein Kalb ist deshalb erst ein
Kalb (bzw. im 1. Durchgang `kuh`), wenn es ganz geboren ist, vorher
`calf_legs` ([`kalbe-akte-spezifikation.md`](./kalbe-akte-spezifikation.md) §2).

**Wenn (b) kommt:** `kalb_liegend`/`kalb_stehend` gehören **nicht** in
`modell.tier_klassen`. Dann sieht der Agent im Kalb weder eine Aufsprung-
noch eine Kalbeverdachts- noch eine Festliege-Kuh. Achtung: Der
Tracker-Filter ist heute `tier_klassen` ∪ `amniotic_sac`/`calf_legs`
(`InferenceEngine.klassen_filter`); Kalb-Klassen außerhalb davon filtert
`classes=` ganz weg, und die Kalbe-Akte sähe nie ein Kalb. Sie braucht dafür
eine eigene Liste im Tracker-Filter. Stufe 1 bleibt als zweite Sicherung
(anderes Modell, andere Tierart, Fehlklassifikation).

**Geprüft und verworfen** (Widerspruch, belegt in
`edge-agent/tests/test_brunst_plausibilitaet.py` A7b):

- **Seitenverhältnis der unteren Box** (liegend = flach): Eine stehende,
  besprungene Kuh mit vorgestrecktem Hals erreicht in der Simulation B/H 2,11,
  eine liegende 2,30. Es gibt keine Lücke. Die Liegeschwelle 1,9 der
  Festliege-Spezifikation würde echte Aufsprünge in Seitenansicht verwerfen.
  Dort funktioniert sie nur mit Hysterese und Steh-Baseline je Tier über
  Minuten, die ein 4-s-Ereignis nicht hat.
- **Obergrenze des Höhenversatzes** (Kalb reicht nur bis zum Bauch):
  Oberkanten-Abstand / Höhe der oberen Box beim Aufsprung 0,14–0,59, beim Kalb
  0,31–0,75. Die Bereiche überlappen, und das Flächenverhältnis erledigt das
  Kalb bereits.

**Die liegende Kuh** trennt keine Einzelbild-Geometrie zuverlässig. Stufe 1
lässt in der Simulation 92 % dieser Lagen durch. Lösung ist die Zeitstruktur:
Eine Duldung dauert Sekunden, eine Nachbarschaft Minuten (Stufe 2, §8).

## 2. Grundsatz

- **Aufspringen tun zwei erwachsene Tiere.** Ein deutlich kleineres Tier in
  Überlappung ist ein Kalb (oder sehr weit weg): kein Aufsprung.
- **Verweildauer-Asymmetrie:** Eine Kalb-Mutter-Lage dauert Stunden, ein
  Aufsprung Sekunden. Bei 1 Bild/s reicht für einen Fehlalarm, dass das
  Rauschen die Schwelle 4 s lang am Stück überschreitet. Das kommt über
  Stunden oft vor. Der Abstand der Schwelle zu den Kalb-Werten zählt deshalb
  mehr als ein paar Prozent echter Aufsprung-Bilder.
- **Brunst ist kein Recall-100-Fall** (anders als die Austreibung). Eine
  Brunst bringt über das Besamungsfenster von 8–18 h meist mehrere
  Duldungen. Eine unterdrückte Duldung kostet auf Brunst-Ebene wenig, ein
  nächtlicher Fehlalarm kostet Vertrauen.
- **Austreibung unberührt:** Fruchtblase und Kälberfüße laufen nicht über
  `_brunst`. Die Prüfung betrifft nur Paare von Tier-Boxen.
- **Tierart-neutral:** ein Verhältnis zweier Boxen, keine Rindermaße. Gilt
  für Fohlen und Stute genauso.

## 3. Grenzen

- **Nur Box-Geometrie je Bild.** Ob ein Tier liegt, weiß die Prüfung nicht.
- **Perspektive:** Ein Kalb nah vor der Mutter (Richtung Kamera) wirkt
  größer. Simulation: Rest von 0,6 % der Kalb-Lagen, ausschließlich bei
  einer Kamera 3 m vom Geschehen und 2,2 m hoch. Ab 5 m Abstand: kein Rest.
- **Größenunterschied unter Erwachsenen:** Färse auf Kuh oder Kuh auf Jungrind
  wird teilweise unterdrückt (Zahlen §4, Risiko 1).
- **Liegende Kuh neben stehender:** durch Stufe 1 nicht gelöst (§1, §8).
- **„Oben“/„unten“ aus der Oberkante** (unverändert): Blickt die Kamera
  längs der Tiere, kann die falsche Kuh als duldend gemeldet werden.
- **Simulation ist nicht der Stall:** Lochkamera, Tiere als Punktwolken,
  keine Verdeckung, ideale Boxen. Sie begründet die Defaults, ersetzt aber
  nicht die Abnahme am Gerät (§7).

## 4. Schwellenwerte

| Prüfung (je Bild und Paar) | Formel | Default | Herkunft |
| --- | --- | --- | --- |
| Überlappung | IoU ≥ `brunst_min_iou` | 0,15 | unverändert, bisher fest im Code |
| Höhenversatz | Oberkante unten − Oberkante oben ≥ `brunst_min_hoehenversatz` × Höhe der unteren Box | 0,20 | unverändert, bisher fest im Code |
| **Flächenverhältnis (neu)** | kleinere Boxfläche / größere ≥ `brunst_min_flaechenverhaeltnis` | **0,45** | Befund ≤ 0,37 + Simulation |
| Mindestdauer | Lage ununterbrochen ≥ `brunst_min_dauer_s` | 4 s | unverändert; Wach-Modus halbiert nur diesen Wert |

Ein Kalb, das ganz in der Box der Mutter liegt, hat Flächenverhältnis = IoU,
im Befund also höchstens 0,37. Simulation (Test A7; 6 Kamerastandorte
3–10 m Abstand, 2,2–4 m Höhe, Blickwinkel in 15°-Schritten; gezählt werden
Bilder, die die alte Regel als Aufsprung-Lage sieht):

| Lage | alte Regel | mit 0,45 | bleibt |
| --- | ---: | ---: | ---: |
| Kalb liegt/steht unter, neben oder bis 2 m vor der Mutter | 1631 | 10 | 0,6 % |
| Kuh auf Kuh | 390 | 368 | 94,4 % |
| Färse (0,85) auf Kuh | 196 | 151 | 77,0 % |
| Kuh auf Färse (0,85) | 428 | 396 | 92,5 % |
| Jungrind (0,75) auf Kuh | 40 | 21 | 52,5 % |
| Kuh auf Jungrind (0,75) | 425 | 332 | 78,1 % |
| liegende Kuh neben stehender | 2028 | 1872 | 92,3 % |

Bei gleich großen Tieren entstehen alle Verluste bei Kameras ≤ 4 m vom
Geschehen (ab 5 m: Kuh auf Kuh 268 → 268). Bei Größenunterschied verliert die
Prüfung auch ab 5 m Bilder: Färse auf Kuh 138 → 110, Kuh auf Jungrind
288 → 241, Kuh auf Färse 288 → 275. Der Kalb-Rest entsteht nur bei 3 m
Abstand (ab 5 m: 1148 → 0). Kalb-Werte in der Simulation: Median 0,20,
99 % unter 0,42, Maximum 0,60.

Warum 0,45 und nicht 0,40 oder 0,50 (gleiche Simulation):

| Schwelle | Kalb bleibt | Kuh auf Kuh bleibt | Färse auf Kuh bleibt |
| ---: | ---: | ---: | ---: |
| 0,40 | 1,6 % | 98,2 % | 84,2 % |
| **0,45** | **0,6 %** | **94,4 %** | **77,0 %** |
| 0,50 | 0,5 % | 89,5 % | 67,9 % |

0,40 liegt nur 0,03 über dem ungünstigsten Befundwert 0,37. Mit 10 %
unabhängigem Flächenrauschen je Box (Standardabweichung, Monte-Carlo)
überschreitet ein solches Kalb 0,40 in 29 % der Bilder: etwa 7 Serien von
5 Bildern je Stunde, wegen der Paar-Sperre ein Alarm je Stunde. Bei 0,45 sind
es 8 % der Bilder und etwa 4 Serien in 10 Tagen (Verweildauer-Asymmetrie,
§2). Reales Detektor-Rauschen ist bei 1 Bild/s auf einer stehenden Szene
stark korreliert; entscheidend ist deshalb der systematische Abstand der
Kalb-Werte zur Schwelle, den die Geometrie-Simulation zeigt. 0,50 kostet bei
Kuh auf Kuh doppelt so viel wie 0,45 und bringt beim Kalb kaum noch Gewinn.

## 5. Konfiguration

```yaml
logik:
  brunst_min_dauer_s: 4
  brunst_min_iou: 0.15                 # > 0; 0 liesse Boxen ohne Ueberlappung zu
  brunst_min_hoehenversatz: 0.20
  brunst_min_flaechenverhaeltnis: 0.45 # 0 = Pruefung aus
modell:
  tier_klassen: [kuh]                  # kalb_liegend/kalb_stehend NICHT eintragen
```

- **Fehlt ein Schlüssel** (ältere `config.yaml`) oder ist er leer, gilt der
  Default aus dem Code. Bestehende Installationen bekommen den Kalb-Schutz
  ohne Config-Änderung. IoU und Versatz verhalten sich wie bisher.
- **Startsicher:** Dezimalkomma wird angenommen (`0,35` = `0.35`). Ein
  unlesbarer Wert oder einer außerhalb des Bereichs (IoU 0 < x ≤ 1, Versatz
  ≥ 0, Fläche 0–1) ergibt eine Warnung im Log, und der Default gilt. Die
  `LogicEngine` entsteht vor der Analyseschleife: Ein Tippfehler in einem
  Brunst-Wert darf den Agenten und damit die Austreibung nie am Start
  hindern.
- **`0` schaltet das Flächenverhältnis ab.** Das alte Verhalten ist so
  zurückholbar, z. B. für einen Vergleich am Gerät (G2).
- **Jungviehbucht ohne Kälber:** Fehlen dort Aufsprünge zwischen Färse und
  Kuh, die Schwelle senken (z. B. 0,35) oder abschalten. Nie in einer Bucht
  mit Kalb.
- **Nie anheben**, um Fehlalarme durch liegende Kühe zu drücken: Bei 0,60
  bleiben 76 % dieser Lagen, und 28 % der echten Kuh-auf-Kuh-Lagen gehen
  verloren. Das ist Stufe 2.
- Der Wach-Modus ändert das Flächenverhältnis bewusst nicht: Nach der Geburt
  liegt genau das Kalb in der Bucht, vor dem das schützt.

## 6. UI-Texte

- **Alarmtext unverändert:** „Aufsprungverhalten erkannt (Kuh #3 auf Kuh #4,
  Dauer 4 s) – Duldung deutet auf Brunst hin“.
- **Unterdrückte Lagen sind still:** keine Meldung, kein Eintrag im
  Tagesbericht, kein Log je Bild (1 Bild/s × Stunden). Ruhe vor Fülle.
- **Ungültiger Config-Wert** (Log, Warnung): „logik.brunst_min_iou=0 ist
  ungueltig – nutze 0.15“.
- Regel-Kurzform für README, System-Prompt und `ki-wache`: „zwei ähnlich
  große Kuh-Boxen überlappen (IoU ≥ 0,15, kleinere ≥ 45 % der Fläche der
  größeren – ein Kalb bei der Mutter ist kein Aufsprung), eine deutlich
  oberhalb, ≥ 4 s“.

## 7. Abnahmekriterien

**Offline** (`edge-agent/tests/test_brunst_plausibilitaet.py`, Teil von
`python3 edge-agent/tests/alle_tests.py`):

| Nr. | Prüfung |
| --- | --- |
| A1 | Kalb liegt unter der Mutter, IoU 0,21 / 0,29 / 0,37, 2 min bei 1 Bild/s → kein `brunstverdacht`. Gegenprobe mit `0` (aus): Brunstverdacht wie bisher, also der Befund |
| A2 | Echter Aufsprung, gleich große Boxen → nach 4 s genau ein Alarm für die untere Kuh, ihre Box, Text unverändert; ein Kalb daneben ändert daran nichts |
| A3 | Grenzwerte: Verhältnis 0,45 reicht, 0,449 nicht; symmetrisch; entartete Box → 0 statt Division durch null |
| A4 | Fehlende/leere Schlüssel → Defaults; `0` bleibt `0`; IoU 0,15 und Versatz 20 % wirken wie vorher; Config-Werte für IoU und Versatz wirken |
| A5 | Austreibung unberührt: Fruchtblase bzw. Kälberfüße bei Mutter und Kalb → Sofort-Meldung im ersten Bild, auch mit strengster Flächenprüfung (1,0) |
| A6 | Wach-Modus: nur die Mindestdauer halbiert (2 s), Kalb weiter still, echter Aufsprung nach 2 s |
| A7 | Simulation: Kalb ≥ 99 % unterdrückt, Kuh auf Kuh ≥ 90 % erhalten, Färse/Kuh ≥ 75 % erhalten, gleich große Tiere ab 5 m Abstand ohne Verlust und ohne Kalb-Rest; dokumentierte Lücken: liegende Kuh, ältere Kälber, Zwillinge |
| A7b | verworfene Prüfungen: Seitenverhältnis und Höhen-Obergrenze trennen nicht |

Dazu: Paar-Sperre 1 h und Neustart der 4-s-Uhr durch ein Bild unter der
Schwelle unverändert (A2), IoU-Schwelle an der Grenze über die Config (A4),
Startsicherheit bei Komma, Text, NaN und Werten außerhalb des Bereichs (A4),
ältere Kälber und Zwillinge als dokumentierte Lücken (A7).

**Am Gerät** (Beweispflicht, mit dem ersten Modell, Aufnahmen mit 1 Bild/s
wie in [`metriken.md`](./metriken.md)):

| Nr. | Prüfung | Bestanden, wenn |
| --- | --- | --- |
| G1 | Replay ≥ 1 h Kalb bei der Mutter, Tag und IR-Nacht | 0 × `brunstverdacht` |
| G2 | Replay echter Aufsprünge aus dem eigenen Stall, einmal mit Default, einmal mit `0` | gleiche Brunstmeldungen in beiden Läufen; jede Abweichung einzeln am Bild begründen |
| G3 | 7 Nächte Fehlalarm-Triage (Skill `fehlalarm-triage`) mit Kalb in der Bucht | 0 Brunst-Fehlalarme mit Kalb im Bild; Zeile in `metriken.md` |

Erst nach G1–G3 gilt die Prüfung als freigegeben.

## 8. Stufe 2 (spezifiziert, nicht gebaut): statische Nachbarn

### 8a. Dauerlage-Sperre (ohne Daten baubar, als Nächstes)

Heute meldet eine statische Lage einmal je Stunde (Paar-Sperre 1 h), also bis
zu 12 Fehlalarme in einer 12-h-Nacht, mit Nummernwechseln des Trackers mehr.
**Regel:** Ein Paar, das seit seiner letzten Brunstmeldung nie mindestens
5 min am Stück außer Lage war, meldet nicht erneut. Eine Duldung dauert
Sekunden; wer nach einer Stunde noch genauso daliegt, springt nicht auf.
Simulation `ki-wache` (Prototyp): statische Lage über 12 h → 1 Meldung statt
12, auch bei 10 % und 30 % Erkennungsaussetzern; zwei echte Aufsprünge im
Abstand von 30 min bzw. 2 h → weiterhin 1 bzw. 2 Meldungen (der erste fällt
in die bestehende 1-h-Sperre). **Grenzen:** Die erste Meldung bleibt; nach
einem Nummernwechsel meldet das neue Paar wieder einmal. Gebaut wird 8a als
eigene Änderung mit eigener Entscheidung und Tests (Spezifikations-Pipeline).

### 8b. Höchstdauer (blockiert)

**Grundsatz:** Eine Duldung dauert Sekunden. Statische Nachbarschaft dauert
Minuten: die liegende Kuh neben der stehenden, das Kalb, Kühe hintereinander
am Fressgitter. Eine Aufsprung-Lage zählt nur, wenn sie nach mindestens
`brunst_min_dauer_s` und höchstens `brunst_max_dauer_s` wieder **endet**.
Der Alarm kommt deshalb erst nach dem Aufsprung, was bei einem
Besamungsfenster von Stunden nichts kostet.

**Warum nicht jetzt gebaut:**

1. **Belegbild:** Beim Alarm sind die Tiere schon getrennt. Das Alarmbild
   muss aus dem Aufsprung stammen. Der Alarm braucht dafür den Bildabstand,
   die Hauptschleife das passende Bild aus `frame_puffer` (heute 8 Bilder).
   Sonst zeigt der Snapshot zwei Kühe nebeneinander und verletzt die
   Beweispflicht. Betroffen sind auch das Album (letzte 4 Bilder), der Kasten
   im Alarm und die Hard Negatives bei „Fehlalarm“: Ohne Bild aus dem
   Aufsprung landen Bilder ohne das Ereignis im Nachtraining. Der Puffer
   braucht Höchstdauer + 4 Bilder, also JPEG-kodiert (1080p roh ≈ 6 MB je
   Bild).
2. **Flackern:** Erkennungsaussetzer zerlegen eine statische Lage in kurze
   Stücke, die jedes wie ein Aufsprung aussehen. Nötig ist eine
   Vorgeschichte: Das Paar war vor dem Beginn nicht schon länger als X s nah.
   Ein Nummernwechsel des Trackers erzeugt ein neues Paar; die Vorgeschichte
   muss deshalb an der Lage im Bild hängen, nicht an der Nummer (wie die
   Liegeplatz-Vererbung im Festliege-Wächter).
3. **Werte nur aus Material:** `brunst_max_dauer_s`, Lückentoleranz und X
   kommen aus echten Aufsprung-Clips des eigenen Stalls (1 Bild/s), nicht aus
   Schätzung.
4. Die Gegenprobe in `test_ein_agent.py` (Mensch hinter Kuh, alter Filter)
   verlässt sich auf einen Alarm *während* der Lage und wäre anzupassen.

**Blocker:** erstes Modell + reale Aufsprung-Clips. Alternativ oder
zusätzlich bleibt die Zwei-Kamera-Fusion
([`brunst-fusion-spezifikation.md`](./brunst-fusion-spezifikation.md)).

## 9. Risiken

1. **Färsen und Jungrinder:** Bei großem Größenunterschied werden echte
   Aufsprünge unterdrückt (Simulation: Färse auf Kuh 23 %, Jungrind auf Kuh
   48 %, Kuh auf Jungrind 22 % der Bilder, auch ab 5 m Abstand). Mehrere
   Duldungen je Brunst mildern das nur, wenn die Verluste unabhängig sind; in
   derselben Bucht mit derselben Kamera scheitern sie systematisch. Den Preis
   zahlt vor allem „Färse auf Kuh“, also die Brunst der größeren Kuh; für die
   Brunst der Färse zählt „Kuh auf Färse“ (92,5 %). Schon die alte
   Versatz-Regel begrenzt Aufsprünge zwischen ungleich großen Tieren stärker
   als die Flächenprüfung (`ki-wache`, Ereignis-Ebene). Gegenmittel nur in
   Buchten ohne Kalb: Schwelle senken (§5).
2. **Kamera nah am Geschehen (≤ 4 m):** Dort entstehen alle Verluste bei
   gleich großen Tieren (Kuh auf Kuh: 3 m 50 von 64, 4 m 50 von 58 Bildern)
   und der Kalb-Rest. Die Prüfung G2 zeigt, ob das für die Stallwache gilt.
3. **Verdeckung:** Der Detektor schneidet verdeckte Teile ab. Die Box des
   Aufspringers oder der Besprungenen kann kleiner ausfallen und das
   Verhältnis senken. Die Simulation kennt keine Verdeckung, G2 schon.
4. **Mehr Prüfungen je Bild, mehr Neustarts:** Jedes Bild ohne Aufsprung-Lage
   setzt die 4-s-Uhr zurück (unverändert). Schwankt das Verhältnis um die
   Schwelle, startet ein echter Aufsprung neu. Bei gleich großen Tieren
   (Verhältnis 0,6–1,0) gering; G2 misst es.
5. **Liegende Kuh neben stehender** bleibt eine Fehlalarm-Quelle bis Stufe 2:
   Eine statische Lage meldet einmal je Stunde (Paar-Sperre 1 h), also bis
   zu 12 Fehlalarme je Nacht, mit Nummernwechseln des Trackers mehr. 8a
   senkt das auf einen. Die Fehlalarm-Triage zeigt, wie oft.
6. **Falsche „untere“ Kuh** bei Blick längs der Tiere (bestehend, unverändert).
7. **Wachsendes Kalb:** Die Prüfung schützt vor allem in den ersten
   Lebenswochen. Ist das Kalb 15 % größer (etwa 6–8 Wochen), bestehen in der
   Simulation 6 % der Kalb-Lagen die Schwelle (`ki-wache` mit Kopf und Hals
   vorgestreckt: 12 %), bei 30 % rund 20 %. In Mutterkuhhaltung und
   muttergebundener Kälberaufzucht hilft erst die Klasse Kalb (Weg b).
8. **Zwei Kälber** (Zwillinge, Kälbergruppe) sind gleich groß: Liegt eines
   und steht das andere daneben, greift die Flächenprüfung nicht (Simulation
   1120 → 1120). Wie die liegende Kuh: Stufe 2.
9. **Der Preis ist im Betrieb unsichtbar:** Verworfene echte Aufsprünge
   bleiben still, G2 misst nur Replays. Vorschlag für 8a: ein INFO-Log je
   verworfener Serie ab Mindestdauer (nicht je Bild).

## Offene Punkte

1. **Labeling-Regel für Kälber im 1. Durchgang** (Skill `modell-training`,
   Phase 2). Empfehlung `ki-wache`: Kälber als `kuh` labeln (Kasten und
   Keypoints nach denselben Regeln) und in CVAT das Attribut `kalb` setzen;
   das CVAT-Projekt behalten, denn der YOLO-Export verliert das Attribut. Ein
   halb geborenes Kalb ist `calf_legs`, `kuh` erst, wenn es ganz geboren ist.
   Unmarkiert lassen bestraft richtige Erkennungen genau am ähnlichsten Fall,
   der kompakt liegenden Kuh unter der Geburt. Mit dem Attribut kostet Weg (b)
   im 2. Training nur das Umstellen der Klasse. Folge bis dahin: Ein Kalb kann
   Kalbeverdacht auslösen (in der Triage getrennt zählen) und den
   Festliege-Wächter (dort als Grenze vermerkt). **Entscheidung Betreiber.**
2. Stufe 8a als eigene Änderung bauen; 8b nach dem ersten Modell mit
   Aufsprung-Clips.
3. Nebenbefund `ki-wache` (bestand vorher, betrifft Recall der Austreibung):
   `LogicEngine.bewerte` setzt den Episodenzustand der Austreibung, bevor die
   Meldung zurückgegeben wird. Wirft danach Kalbeverdacht oder `_brunst` im
   selben Bild eine Exception, ist die Sofort-Meldung verloren, und die erste
   zugestellte Meldung kommt erst mit der Erinnerung nach 15 min. Eigener
   Roadmap-Punkt (Schritte 2 und 3 je für sich kapseln).
