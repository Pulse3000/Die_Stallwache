# Spezifikation: Austreibungs-Takt je Episode statt Kamera-Cooldown

Behebt den Roadmap-Befund „Austreibungs-Cooldown je Episode statt je
Kamera“ (Oktober 2026). Entwurf und Übernahme: Orchestrator (14.10.2026).
**Status: Regeln 1–5 umgesetzt (`edge-agent/main.py`), Regel 6 spezifiziert
und blockiert bis zum ersten Modell; Abnahme am realen Stream offen.**

## 0. Befund

Der `Notifier` bündelt jeden Alarm unter dem Schlüssel (Kuh-ID, Typ) für
`telegram.cooldown_minuten` (15). Austreibungen tragen keine Kuh-ID —
Fruchtblase und Kälberfüße sind Objekte, kein Teil eines Kuh-Tracks. Alle
Austreibungen einer Kamera teilen sich damit den Schlüssel
`(None, "austreibung")`. Eine Austreibungs-Erkennung binnen 15 min nach der
letzten Meldung geht erst nach Ablauf raus. Das widerspricht dem Grundsatz
„Austreibung nie unterdrücken oder verzögern“ (`edge-agent/SYSTEM_PROMPT.md`).

Wo das konkret schadet:

| Fall | Heute | Schaden |
| --- | --- | --- |
| **(a) zweite Kuh** kalbt in derselben Kamera, während die erste Austreibung noch läuft | erst nach Ablauf der 15 min gemeldet | bis 15 min Verzögerung; der Landwirt ist aber meist schon wegen Kuh 1 unterwegs |
| **(b) echter Befund kurz nach einem Fehlalarm**: 02:00 Fehlalarm, Landwirt prüft die Bildserie, tippt „❌ Fehlalarm“, schläft weiter; 02:10 beginnt die echte Austreibung | gemeldet frühestens 02:15 | bis 15 min Verzögerung, **und der Landwirt liegt im Bett** — der teuerste Fall |
| **(c) Stream war > 30 min weg** | Ob die Episode endet, hängt davon ab, ob das *erste* Bild nach dem Ausfall eine Erkennung zeigt (dann läuft sie weiter, ggf. sofort Eskalation) oder nicht (dann ist sie beendet, obwohl nichts beobachtet wurde) | uneinheitlich; Blindzeit zählt mal als Abwesenheit, mal nicht |

## 1. Widerspruch zur eigenen Aufgabenstellung

Die Aufgabe schlug „genau eine Meldung pro Episode“ vor. **Abgelehnt**, aus
zwei Gründen:

1. Der 15-min-Cooldown ist heute *nebenbei* die einzige laufende
   Wiederholung einer Austreibung: Solange Fruchtblase oder Füße sichtbar
   sind, kommt alle 15 min eine neue Meldung. Die Weckkette
   (`eskalationskette-spezifikation.md`) ist spezifiziert, aber nicht gebaut.
   Hat die erste Meldung nicht geweckt (iOS-Fokus, Handy in der Jacke), weckt
   heute die zweite. Eine einzige Meldung pro Episode würde genau diesen
   Weckweg abschalten.
2. Fall (b) würde **schlimmer**: Fehlalarm und echte Austreibung lägen in
   derselben 30-min-Episode, die echte bekäme gar keine eigene Meldung mehr,
   bis 60 min nach dem *Fehlalarm* die Eskalation käme.

Richtig ist: Der Takt der Austreibung gehört vollständig in die
`LogicEngine` (die die Episode kennt) und nicht in einen pauschalen
Cooldown des `Notifier` (der sie nicht kennt).

## 2. Regeln

| # | Regel | Wirkung |
| --- | --- | --- |
| 1 | **Episodenbeginn → Sofort-Meldung.** Erste Erkennung ≥ `override_konfidenz` ohne offene Episode | unverändert schnell, jetzt unabhängig vom Notifier-Cooldown |
| 2 | **Erinnerung im Takt.** Solange die Episode läuft und erkannt wird: alle `austreibung_erinnerung_minuten` eine Meldung „Austreibung läuft weiter seit N min“ | ersetzt den bisherigen Cooldown-Takt mit gleichem Default (15 min) und sagt jetzt, *seit wann* |
| 3 | **Eskalation** einmal pro Episode nach `eskalation_minuten` (60), im selben Bild ersetzt sie die Erinnerung | unverändert, umgeht den Notifier-Cooldown jetzt ausdrücklich statt über einen Hilfsschlüssel |
| 4 | **Episodenende** erst nach 30 min **beobachteter** Abwesenheit: Nur analysierte Bilder ohne Erkennung zählen (je Bild höchstens 10 s Lücke). Blindzeit — Stream weg, Kamera defekt, Uhrensprung — zählt nicht | macht Fall (c) einheitlich, in Recall-Richtung (siehe unten) |
| 5 | **„❌ Fehlalarm“ auf eine Meldung der laufenden Episode** → die nächste Erkennung nach mindestens **60 s** ohne Erkennung meldet **sofort** („erneut erkannt“), statt auf die nächste Erinnerung zu warten | behebt Fall (b) |
| 6 | **Zweite Kuh**: Erkennung räumlich bei einer anderen Kuh als die laufende Episode → eigene Episode, Sofort-Meldung | **blockiert** (Abschnitt 4) |

Weitere Festlegungen:

- Mehrere Objekte im selben Bild (Blase **und** Füße) erzeugen **eine**
  Meldung, mit dem Objekt höchster Konfidenz. Heute entstanden zwei, von denen
  der Cooldown die zweite schluckte.
- Der Notifier-Cooldown gilt ab jetzt **nur noch für Kalbe- und
  Brunstverdacht**. Austreibung und Eskalation tragen `sofort=True`.
- **Regel 5 unterdrückt nichts.** Ein „❌ Fehlalarm“ verschiebt weder die
  Erinnerung noch die Eskalation. Ein versehentlicher Tipp auf eine echte
  Austreibung darf nie stiller machen als heute. Die Eskalations-Uhr läuft
  deshalb ab der *ersten* Erkennung weiter: Nach einem Fehlalarm kommt der
  Kontroll-Alarm höchstens etwas früher, nie später.
- Ein Fehlalarm-Votum zu einer **beendeten** Episode ist wirkungslos (die
  neue Episode meldet ohnehin sofort).
- **Regel 4, Korrektur nach QA (14.10.2026):** Die erste Fassung beendete
  die Episode nach 30 min *Wanduhr* ohne Erkennung, auch über einen
  Stream-Ausfall hinweg. Der `qa-waechter` zeigte, was das kostet: Geburt
  läuft 0–50 min, Stream 45 min weg, Blase danach weiter sichtbar → neue
  Episode, Eskalation erst bei 155 statt 95 min. Ohne Bild ist nicht zu
  unterscheiden, ob dieselbe Geburt weiterlief. Recall vor Präzision:
  Blindzeit beendet keine Episode. Preis: Beginnt nach einem langen
  Ausfall tatsächlich eine *neue* Geburt, kann sofort die Eskalation statt
  der Beginn-Meldung kommen — ein Kontrollgang zu viel, kein verpasstes
  Kalb.
- Die 60-s-Lücke in Regel 5 verhindert die Schleife „Dauer-Fehlerkennung →
  Tipp → sofort neue Meldung → Tipp …“: Solange das Fehlobjekt ohne Pause im
  Bild bleibt, läuft nur der normale Erinnerungstakt.

## 3. Konfiguration

| Schlüssel | Default | Bedeutung |
| --- | --- | --- |
| `logik.austreibung_erinnerung_minuten` | leer = `telegram.cooldown_minuten` (15) | Takt der Erinnerung; mindestens 1 min. Der Default übernimmt den bisherigen Cooldown, damit sich für bestehende Konfigurationen nichts ändert |

Fest im Code (unverändert bzw. neu, ohne Schalter):

- Episodenende nach 30 min beobachteter Abwesenheit (`EPISODE_ENDE_S`,
  wie bisher 30 min, jetzt benannt), höchstens 10 s je Bildlücke
  (`MAX_BILDLUECKE_S`)
- Lücke für die Neumeldung nach Fehlalarm 60 s
  (`NEUMELDUNG_LUECKE_S`)

Erkennungsschwellen (45°/20 %/30 min/0.80/IoU 0.15/4 s),
`telegram.cooldown_minuten: 15` und `eskalation_minuten: 60` bleiben
unverändert.

## 4. Regel 6 (zweite Kuh) — warum blockiert

Die naheliegende Umsetzung ordnet jedes Fruchtblasen-/Füße-Objekt der
Kuh-Box zu, in der es liegt (Überdeckung ≥ 50 % der Objektfläche), und führt
die Episode je Kuh-Track. Zwei Gründe, das nicht ohne Modell zu bauen:

1. **Die Geometrie ist unbelegt.** Fruchtblase und Füße treten hinten aus
   der Kuh aus und liegen bei Draufsicht oft *außerhalb* der Kuh-Box. Ob
   „Überdeckung ≥ 50 %“ trägt oder ob ein Abstand zum Schwanzansatz-Keypoint
   besser ist, lässt sich erst an echten Erkennungen messen.
2. **ID-Wechsel kosten Fehlalarme.** Eine Kuh, die sich zum Pressen ablegt,
   bekommt bei ByteTrack gelegentlich eine neue ID. Je Kuh geführte Episoden
   melden dann „neue Austreibung“ für dieselbe Geburt. Gegenmittel (neue ID
   mit starker Box-Überlappung zur alten gilt als dieselbe Kuh) braucht
   ebenfalls echte Daten zur Kalibrierung.

Bis dahin gilt für Fall (a) der Erinnerungstakt (höchstens 15 min, wie
heute). Voraussetzung zum Entblocken: erstes Modell + mind. 3 aufgezeichnete
Kalbungen mit Fruchtblasen-Erkennung, an denen die Zuordnung gemessen wird.
Danach bekommt die Austreibung auch eine Kuh-ID im Ereignis
(„Fruchtblase bei Kuh #12“). Das Ereignis-Schema erlaubt das schon heute
(`kuhId` ist frei belegbar), die Statusabfrage wertet die Austreibung
unabhängig davon als Kamera-Ereignis.

## 5. Texte

| Anlass | Text |
| --- | --- |
| Episodenbeginn | „Fruchtblase erkannt (Konfidenz 87 %) – Austreibungsphase!“ (unverändert) |
| Erinnerung | „Austreibung läuft weiter seit 15 min – Kälberfüße weiterhin sichtbar (Konfidenz 91 %).“ |
| Neumeldung nach Fehlalarm | „Fruchtblase erneut erkannt (Konfidenz 88 %) – die vorige Meldung wurde als Fehlalarm markiert, bitte prüfen!“ |
| Eskalation | „⚠️ KEIN GEBURTSFORTSCHRITT: …“ (unverändert) |

## 6. Abnahmekriterien

Automatisiert (`edge-agent/tests/test_austreibung_episoden.py`):

1. Erste Erkennung → genau eine Meldung, `sofort=True`, Text unverändert.
2. Folgebilder derselben Episode innerhalb des Takts → keine Meldung.
3. Nach 15 min weiter erkannt → eine Erinnerung mit „seit 15 min“.
4. Blase und Füße im selben Bild → eine Meldung, höchste Konfidenz.
5. Eskalation genau einmal nach 60 min, im selben Bild keine Erinnerung.
6. 30 min **beobachtet** ohne Erkennung → Episode beendet; nächste Erkennung = neue Episode, sofortige Meldung, Eskalations-Uhr neu.
7. Blindzeit: Geburt 0–50 min, 45 min kein `bewerte`-Aufruf, Blase weiter sichtbar → dieselbe Episode, Eskalation sofort („seit 95 Minuten“). Erstes Bild nach 2 h ohne Erkennung beendet die Episode nicht; erst 30 min Beobachtung danach. Ein Uhrensprung zählt höchstens 10 s.
8. Fall (b): Fehlalarm-Votum zur laufenden Episode, 60 s ohne Erkennung, dann Erkennung → sofort „erneut erkannt“.
9. Fehlalarm-Votum, Objekt bleibt ohne Pause im Bild → keine Sofort-Meldung, Erinnerung im normalen Takt.
10. Fehlalarm-Votum verschiebt die Eskalation nicht.
11. Fehlalarm-Votum zu einer alten Episode oder zu einem anderen Typ → wirkungslos.
12. Notifier: Austreibung (`sofort=True`) innerhalb des Cooldowns wird gemeldet; Kalbe-/Brunstverdacht bleiben im Cooldown.
13. Feedback-Schleife reicht Typ und Episode des Alarms beim Votum „Fehlalarm“ an die Logik weiter; ein Fehler dort bricht die Feedback-Verarbeitung nicht ab.
14. `austreibung_erinnerung_minuten` leer oder 0 → Takt = `telegram.cooldown_minuten` (nie Dauerfeuer); gesetzt → eigener Wert, mindestens 1 min.
15. Kalbe- und Brunstlogik unverändert (Referenzwerte-Test grün).

Am realen Stream (Beweispflicht, offen):

16. Aufgezeichnete Kalbung abspielen: genau eine Meldung zu Beginn, danach
    Erinnerungen im 15-min-Takt, Eskalation nur bei > 60 min sichtbarer
    Blase/Füße.
17. Fehlalarm-Probe: Meldung mit „❌“ quittieren, Objekt verschwindet und
    taucht nach > 1 min wieder auf → sofortige Neumeldung.

## 7. Risiken

1. **Mehr Meldungen bei flackernder Fehlerkennung nach einem ❌-Tipp**: höchstens
   eine Sofort-Meldung pro Tipp (danach gilt wieder der Takt). Begrenzt durch
   den Menschen, nicht durch Bildraten.
2. **Fall (a) bleibt bis Regel 6 offen** (höchstens 15 min, wie heute).
3. **Neustart verliert die Episode** (Zustand nur im Speicher, wie bisher):
   Nach einem Neustart meldet eine laufende Austreibung sofort neu. Das ist
   die sichere Richtung — die Eskalations-Uhr beginnt dann aber neu.
4. **Uhr springt rückwärts** (Pi ohne RTC, NTP-Korrektur): Erinnerung und
   Eskalation setzen bis zum Aufholen aus. Unverändert gegenüber vorher
   (`time.time()`); Abhilfe `time.monotonic()` in der `LogicEngine` ist ein
   eigener Folgeschritt.
