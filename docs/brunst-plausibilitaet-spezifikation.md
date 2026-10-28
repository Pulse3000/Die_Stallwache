# Spezifikation: Brunst-Plausibilität (ein Kalb ist kein Aufsprung)

Regeln für die Aufsprung-Heuristik des Edge-Agenten
(`edge-agent/main.py`, `LogicEngine._brunst` / `_aufsprung_lage`). Anlass:
Befund des Agenten `ki-wache` vom 27.10.2026 beim Review der KI-Ansicht.
Entwurf und Entscheidung: Orchestrator (28.10.2026), Prüfung: `ki-wache`.
**Status: Stufe 1 umgesetzt** (Flächenverhältnis, alle Aufsprung-Schwellen
konfigurierbar, Logiktests grün). **Freigabe am Gerät offen** (erstes Modell,
§7 G1–G3). **Stufe 2** (Höchstdauer gegen statische Nachbarn) spezifiziert,
blockiert (§8).

## 0. Befund

Bisherige Regel je Bild: Zwei Tier-Boxen sind eine Aufsprung-Lage, wenn
IoU ≥ 0,15 und die Oberkante der oberen Box um ≥ 20 % der Höhe der unteren
Box höher liegt. Hält die Lage ≥ 4 s, folgt `brunstverdacht` für die untere
Kuh, das Paar ist danach 1 h stumm. IoU 0,15 und 20 % standen fest im Code.

`ki-wache`: Das Modell kennt keine Klasse „Kalb“. Ein Kalb unter oder neben
der Mutter wird als `kuh` erkannt und erreicht IoU 0,21–0,37. Für eine
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
3. **Recall-Risiko Austreibung:** Im Geburtsmoment sind Füße und Kopf eines
   teilweise geborenen Kalbs sichtbar. Ohne klare Label-Grenze zwischen
   „Kalb“ und `calf_legs` kann eine Kalb-Klasse den `calf_legs`-Recall
   drücken, also Gate 1. Die Grenze wird im 2. Training mit den ohnehin
   geplanten Klassen gezogen: „Kalb“ erst, wenn es ganz geboren ist
   ([`kalbe-akte-spezifikation.md`](./kalbe-akte-spezifikation.md) §2).
4. **(b) löst nur das Kalb**, nicht die liegende Kuh.

**Wenn (b) kommt:** `kalb_liegend`/`kalb_stehend` gehören **nicht** in
`modell.tier_klassen`. Dann sieht der Agent im Kalb weder eine Aufsprung-
noch eine Kalbeverdachts- noch eine Festliege-Kuh. Stufe 1 bleibt als zweite
Sicherung (anderes Modell, andere Tierart, Fehlklassifikation).

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

Alle Verluste echter Aufsprünge und der Kalb-Rest entstehen bei Kameras
≤ 4 m vom Geschehen. Ab 5 m: Kuh auf Kuh 268 → 268, Kalb 1148 → 0.

Warum 0,45 und nicht 0,40 oder 0,50 (gleiche Simulation):

| Schwelle | Kalb bleibt | Kuh auf Kuh bleibt | Färse auf Kuh bleibt |
| ---: | ---: | ---: | ---: |
| 0,40 | 1,6 % | 98,2 % | 84,2 % |
| **0,45** | **0,6 %** | **94,4 %** | **77,0 %** |
| 0,50 | 0,5 % | 89,5 % | 67,9 % |

0,40 liegt nur 0,03 über dem Befund. Bei einem Flächenrauschen der Boxen von
10 % (Standardabweichung) überschreitet ein Kalb mit 0,37 die Schwelle 0,40 in rund jedem fünften Bild,
0,45 in etwa jedem 65. Bei unabhängigem Rauschen ergibt das rund 1,4 Serien
von 5 Bildern (= ein Alarm) je Stunde bei 0,40, bei 0,45 praktisch keine
(Verweildauer-Asymmetrie, §2). 0,50 kostet bei Kuh auf Kuh doppelt so viel
wie 0,45 und bringt beim Kalb kaum noch Gewinn.

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
- **`0` schaltet das Flächenverhältnis ab.** Das alte Verhalten ist so
  zurückholbar, z. B. für einen Vergleich am Gerät (G2).
- **Jungviehbucht ohne Kälber:** Fehlen dort Aufsprünge zwischen Färse und
  Kuh, die Schwelle senken (z. B. 0,35) oder abschalten. Nie in einer Bucht
  mit Kalb.
- Der Wach-Modus ändert das Flächenverhältnis bewusst nicht: Nach der Geburt
  liegt genau das Kalb in der Bucht, vor dem das schützt.

## 6. UI-Texte

- **Alarmtext unverändert:** „Aufsprungverhalten erkannt (Kuh #3 auf Kuh #4,
  Dauer 4 s) – Duldung deutet auf Brunst hin“.
- **Unterdrückte Lagen sind still:** keine Meldung, kein Eintrag im
  Tagesbericht, kein Log je Bild (1 Bild/s × Stunden). Ruhe vor Fülle.
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
| A7 | Simulation: Kalb ≥ 99 % unterdrückt, Kuh auf Kuh ≥ 90 % erhalten, Färse/Kuh ≥ 75 % erhalten, ab 5 m Abstand kein Verlust und kein Kalb-Rest; liegende Kuh bleibt offen |
| A7b | verworfene Prüfungen: Seitenverhältnis und Höhen-Obergrenze trennen nicht |

**Am Gerät** (Beweispflicht, mit dem ersten Modell, Aufnahmen mit 1 Bild/s
wie in [`metriken.md`](./metriken.md)):

| Nr. | Prüfung | Bestanden, wenn |
| --- | --- | --- |
| G1 | Replay ≥ 1 h Kalb bei der Mutter, Tag und IR-Nacht | 0 × `brunstverdacht` |
| G2 | Replay echter Aufsprünge aus dem eigenen Stall, einmal mit Default, einmal mit `0` | gleiche Brunstmeldungen in beiden Läufen; jede Abweichung einzeln am Bild begründen |
| G3 | 7 Nächte Fehlalarm-Triage (Skill `fehlalarm-triage`) mit Kalb in der Bucht | 0 Brunst-Fehlalarme mit Kalb im Bild; Zeile in `metriken.md` |

Erst nach G1–G3 gilt die Prüfung als freigegeben.

## 8. Stufe 2 (spezifiziert, nicht gebaut): Höchstdauer

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
   Beweispflicht.
2. **Flackern:** Erkennungsaussetzer zerlegen eine statische Lage in kurze
   Stücke, die jedes wie ein Aufsprung aussehen. Nötig ist eine
   Vorgeschichte: Das Paar war vor dem Beginn nicht schon länger als X s nah.
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
   48 %, Kuh auf Jungrind 22 % der Bilder). Gemildert dadurch, dass eine Brunst meist mehrere
   Duldungen bringt. Gegenmittel nur in Buchten ohne Kalb: Schwelle senken
   (§5).
2. **Kamera nah am Geschehen (≤ 4 m):** Dort entstehen alle Verluste (Kuh auf
   Kuh: 3 m 50 von 64, 4 m 50 von 58 Bildern) und der Kalb-Rest. Die Prüfung
   G2 zeigt, ob das für die Stallwache gilt.
3. **Verdeckung:** Der Detektor schneidet verdeckte Teile ab. Die Box des
   Aufspringers oder der Besprungenen kann kleiner ausfallen und das
   Verhältnis senken. Die Simulation kennt keine Verdeckung, G2 schon.
4. **Mehr Prüfungen je Bild, mehr Neustarts:** Jedes Bild ohne Aufsprung-Lage
   setzt die 4-s-Uhr zurück (unverändert). Schwankt das Verhältnis um die
   Schwelle, startet ein echter Aufsprung neu. Bei gleich großen Tieren
   (Verhältnis 0,6–1,0) gering; G2 misst es.
5. **Liegende Kuh neben stehender** bleibt eine Fehlalarm-Quelle bis Stufe 2.
   Die Fehlalarm-Triage zeigt, wie oft.
6. **Falsche „untere“ Kuh** bei Blick längs der Tiere (bestehend, unverändert).

## Offene Punkte

1. **Labeling-Regel für Kälber im 1. Durchgang** (Skill `modell-training`,
   Phase 2): Als `kuh` labeln (Ursache des Befunds) oder unmarkiert lassen
   (Hintergrund, aber Widerspruch zu ähnlichen Kuh-Boxen)? Entscheidung
   Betreiber, Einschätzung `ki-wache`.
2. Stufe 2 nach dem ersten Modell mit Aufsprung-Clips aufnehmen.
