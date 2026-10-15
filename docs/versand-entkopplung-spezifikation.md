# Spezifikation: Versand-Entkopplung (die Analyse wartet nie auf das Netz)

Härtung nach der Reifegrad-Regel („Härtung vor Features“). Der Vertrag der
KI-Wache verlangt: *Telegram-/Dashboard-/MQTT-Ausfälle dürfen die Analyse
NIE blockieren (Versand asynchron/fire-and-forget mit kurzem Timeout).*
Der Code hält das bisher nicht ein. Entwurf und Übernahme: Orchestrator
(14.10.2026). **Status: umgesetzt, Abnahme am realen Agenten offen.**

## 0. Befund

Alle Netzaufrufe des `Notifier` laufen im Hauptthread, also in der
1-FPS-Analyseschleife:

| Aufruf | Timeout | Wann |
| --- | --- | --- |
| Telegram-Album (`sendMediaGroup`) + Feedback-Nachricht | 30 s + 20 s | jeder Alarm |
| Dashboard (`POST /api/events`) | 30 s | jeder Alarm, jede Systemmeldung |
| Feedback-Abruf (`getUpdates`) | 10 s | **alle 10 s**, auch ohne Alarm |
| Tagesbericht, Feedback-Antworten | 20 s / 10 s | selten |

Typischer Ausfall im Stall ist ein WLAN, das Pakete verschluckt, statt die
Verbindung abzulehnen. Dann laufen die Timeouts voll aus:

- **Pro Alarm bis zu 80 s Blindflug.** Eine Fruchtblase, die in dieser Zeit
  erscheint, wird erst danach ausgewertet.
- **Feedback-Abruf:** Analyse fällt etwa die Hälfte der Zeit aus (10 s
  hängen alle 10 s), dauerhaft, solange Telegram nicht erreichbar ist.

Dazu der offene Roadmap-Punkt „Lebenszeichen liefert den Offline-Puffer
mit“: Gepufferte Alarme gehen heute erst mit dem *nächsten* Alarm raus, in
einer ruhigen Nacht also gar nicht.

## 1. Grundsatz

1. **Die Analyseschleife wartet nie auf das Netz und nie auf die Platte.**
   Im Hauptthread bleibt nur CPU-Arbeit im Millisekundenbereich: Bilder
   kodieren, Ereignis bauen, in eine Warteschlange legen. Auch die
   Hard-Negative-Bilder eines „❌ Fehlalarm“-Votums schreibt der
   Feedback-Kanal; vorher hielt ein Votum die Analyse auf einer langsamen
   SD-Karte mehrere Sekunden an. Die Antwort an den Landwirt kommt erst
   nach dem Schreiben und nennt das tatsächliche Ergebnis. Schlägt das
   Schreiben fehl (volle oder defekte Karte), sagt die Antwort das, statt
   „gespeichert“ zu behaupten.
2. **Je Kanal ein Versand-Thread.** Telegram-Alarme, Telegram-Feedback
   und das Dashboard bekommen je einen eigenen Worker. Ein hängendes
   Telegram hält die App-Meldung (und damit den Push aufs Handy) nicht auf,
   und umgekehrt. Button-Antworten konkurrieren nie mit Alarmen. Innerhalb
   eines Kanals bleibt die Reihenfolge erhalten.
3. **Dashboard als Outbox.** Jedes Ereignis kommt zuerst in die Outbox. Ein
   eigener Sicherungs-Thread schreibt sie bei jeder Änderung auf die Platte,
   unabhängig vom Netz. Der Dashboard-Thread entfernt nur, was der Server
   angenommen hat. Kein Alarm geht verloren, auch nicht bei einem Neustart
   mitten im Senden.
4. **Zustand der Logik bleibt im Hauptthread.** Feedback-Antworten von
   Telegram holt der Worker ab, *verarbeitet* werden sie im Hauptthread
   (sie greifen über `bei_fehlalarm` in die `LogicEngine`).

## 2. Regeln

| # | Regel |
| --- | --- |
| 1 | `melde()`, `wichtig()`, `status()` und `digest_tick()` kehren ohne Netzzugriff zurück. Telegram-Aufträge gehen in die Telegram-Warteschlange, Dashboard-Ereignisse in die Outbox |
| 2 | Telegram-Warteschlange begrenzt auf 50 Aufträge. Austreibung, Eskalation und Systemwarnungen (`prio=True`) **überholen** wartende Routine-Aufträge; untereinander bleibt die Reihenfolge. Bei Überlauf fällt der älteste Routine-Auftrag heraus. Warten nur dringende, wird ein **neuer Routine-Auftrag** verworfen. Ein dringender Auftrag weicht nie für Routine, nur für einen neueren dringenden. Feedback-Abruf, -Antworten und Hard-Negative-Speicherung laufen über einen eigenen Kanal |
| 3 | Outbox in **Teilstapeln** (höchstens 50 Einträge und 3 MB, die Server-Grenzen sind 100 und 4,5 MB). Vor **jedem** Teilstapel wird die Outbox neu gelesen und **Austreibung/Eskalation vorgezogen**: Ein frischer Alarm wartet höchstens auf den gerade laufenden Teilstapel. Nach einem Fehlschlag wird erst mit **einem** Ereignis getastet. **413** (zu groß): Die Einträge gehen einzeln raus, ein einzelner notfalls ohne Bilder; verworfen wird bei 413 nie. **400 der App selbst** (JSON `{fehler}`/`{ergebnisse}`): Die Einträge gehen einzeln raus. Ein einzeln abgelehnter Eintrag geht ohne Bilder raus oder wird verworfen und protokolliert. **Fremde 400** (Proxy, Captive-Portal ohne App-JSON) gelten als Fehler, verworfen wird nichts. Kein Eintrag blockiert je die Schlange. Entfernt wird nur Angenommenes, über die Objekt-Identität und nicht über die Position |
| 4 | **Nachlieferung ohne neuen Alarm:** Steht etwas aus, versucht der Worker nach 60 s erneut. Nach weiteren Fehlschlägen verdoppelt sich der Abstand bis 15 min. Ein neues Ereignis löst immer sofort einen Versuch aus. Das schließt den Roadmap-Punkt „Offline-Puffer nachliefern“ |
| 5 | Plattensicherung der Outbox in einem **eigenen Sicherungs-Thread** (ein Schreiber), bei jeder Änderung, nie durch das Netz aufgehalten. Der Hauptthread schreibt nie die Pufferdatei (bei 200 Einträgen mit Bildern bis zu ~80 MB) |
| 5a | `dashboard.puffer_max` < 1 wird auf 1 angehoben, mit Warnung. Sonst würde jedes Ereignis schon beim Einreihen verworfen. Jede Verdrängung durch die Obergrenze wird protokolliert |
| 6 | Feedback-Abruf: höchstens **ein** Abruf gleichzeitig. Der nächste wird erst angestoßen, wenn das Ergebnis des vorigen im Hauptthread verarbeitet ist (kein Doppel-Votum durch denselben Offset). Hängt ein Abruf länger als 120 s oder fällt er aus der Warteschlange, wird die Sperre freigegeben |
| 6a | Je Feedback-ID zählt nur das **erste** Votum im Tagesbericht. Ein Doppel-Tipp kommt als neues Update an und wird von Regel 6 nicht erfasst; Regel und Grenzen in §7 |
| 7 | Ein Fehler in einem Auftrag beendet den Worker nie |
| 8 | Ohne zugeordneten Kanal (Tests, Einzelbetrieb) arbeitet die `FeedbackSchleife` wie bisher synchron |

Unverändert bleiben:

- Erkennungslogik, Schwellen und Cooldown.
- Alarm-Texte und Ereignis-Schema.
- Ein Versuch je Telegram-Nachricht, ohne Wiederholung. Neu ist nur, dass dieser Versuch die Analyse nicht mehr blockiert.
- MQTT: `publish` ist bei paho ohnehin nicht blockierend.
- `Lebenszeichen` (eigener Thread, siehe Statusabfrage-Spezifikation).

## 3. Konfiguration

Keine neuen Schalter. Fest im Code:

- `TELEGRAM_WARTESCHLANGE_MAX = 50` (Feedback-Kanal ebenfalls 50)
- `NACHLIEFER_INTERVALL_S = 60`, `NACHLIEFER_MAX_S = 900`
- `MAX_STAPEL = 50`, `MAX_STAPEL_BYTES = 3_000_000`
- `ABRUF_SPERRE_MAX_S = 120`

## 4. Abnahmekriterien

Automatisiert (`edge-agent/tests/test_versand.py`):

1. `melde()` kehrt in < 0,3 s zurück, obwohl Telegram **und** Dashboard je 2 s hängen.
2. Nach dem Warten sind Album, Feedback-Nachricht und Dashboard-Stapel gesendet, mit unverändertem Inhalt.
3. Dashboard down → Ereignis in der Pufferdatei; Dashboard wieder da → **ohne neuen Alarm** nachgeliefert (Nachlieferungs-Takt).
4. Alarm trifft ein, während ein Stapel unterwegs ist → jedes Ereignis genau einmal gesendet, keins verloren.
5. Pufferobergrenze läuft über, während ein Stapel unterwegs ist → kein bereits gesendetes Ereignis wird erneut geschickt, kein ungesendetes entfernt.
6. Telegram-Warteschlange läuft über → älteste fallen raus, Zähler steigt, neue Alarme gehen weiter raus.
7. `feedback.tick()` kehrt in < 0,3 s zurück, obwohl `getUpdates` 2 s hängt. Das Ergebnis wird beim nächsten `tick()` im Hauptthread verarbeitet. Es läuft höchstens ein Abruf gleichzeitig; eine hängende Sperre wird nach 120 s freigegeben.
8. Feedback-Antworten (`answerCallbackQuery`, Buttons entfernen) laufen über den Kanal.
9. `digest_tick()` und `wichtig()` blockieren nicht.
10. Ein Auftrag, der wirft, stoppt den Worker nicht.
11. Rückstau von 136 Ereignissen, davon 6 mit je ~1,2 MB Bildern, gegen einen Server-Nachbau mit den echten Grenzen (100 Einträge, 4,5 MB): Alles kommt an, keins doppelt, kein Stapel abgelehnt.
12. Hinter 60 gepufferten Routinemeldungen enthält die erste Anfrage nach dem Ausfall die Austreibung.
13. Bei 401 wird nach dem ersten Fehlschlag nur noch ein Ereignis je Versuch geschickt; nichts wird verworfen.
14. Backoff 60, 60, 120, 240, 480, 900, 900 s.
15. Ein dauerhaft abgelehnter Eintrag wird verworfen, ein zu großer geht ohne Bilder raus, die gesunden kommen an.
16. Hängt ein POST, ist ein neuer Alarm trotzdem binnen 2 s auf der Platte.
17. `puffer_max: 0` schaltet die App-Meldung nicht still ab.
18. Ein Überlauf verdrängt nie einen dringenden Auftrag.
19. Feedback und Alarme laufen über getrennte Kanäle.
20. Bestehende Suites (Offline-Puffer, Feedback, Episoden, Einbindung) bleiben grün; geänderte Tests warten nur explizit auf den Versand bzw. erlauben das Tasten nach einem Fehlschlag.
21. Fremde 400 (Proxy-Fehlerseite ohne App-JSON) verwerfen nichts, die Austreibung bleibt in der Outbox.
22. Eine Austreibung, die während eines laufenden Rückstau-Teilstapels eintrifft, führt die nächste Anfrage an.
23. Ein dringender Auftrag überholt wartende Routine. Warten nur dringende, wird eine neue Routine verworfen, kein dringender.
24. Ein „❌ Fehlalarm“-Votum kehrt sofort zurück, auch wenn das Speichern der Bilder 2 s dauert. Die Antwort nennt die tatsächlich gespeicherte Anzahl. Bei defekter Platte gibt es keine Erfolgsmeldung, die Buttons verschwinden trotzdem, und der Kanal arbeitet weiter.
25. Mutationsprobe: 14 gezielte Fehler werden von je mindestens einem Test erkannt. Geprüft: ohne Sperre, Antworten synchron, keine Sicherung, ohne Teilstapel, ohne Vorrang, Priorität ignoriert, ohne Tasten, Ablehnung endlos, kein Neulesen je Teilstapel, Routine verdrängt Dringendes, kein Überholen, jede 400 verwerfen, Platte synchron, Erfolgsmeldung unabhängig vom Speichern.

Am realen Agenten (Beweispflicht, offen):

26. Uplink im Stall trennen, Fruchtblasen-Testbild zeigen. Die Analyse läuft weiter, Log-Zeitstempel der Frames ohne Lücken > 2 s.
27. Uplink zurück → gepufferte Meldung erscheint binnen 60 s in der App, ohne neuen Alarm (nach längerem Ausfall spätestens nach dem aktuellen Backoff, höchstens 15 min, oder sofort mit dem nächsten Ereignis).

## 5. Risiken

1. **Prozessende mit vollen Warteschlangen** (SIGTERM, Stromausfall):
   - Ausstehende Telegram-Nachrichten gehen verloren. Bisher ging in
     diesem Fall nur die gerade laufende verloren.
   - Outbox-Einträge, die der Sicherungs-Thread noch nicht geschrieben hat,
     gehen verloren. Das Fenster ist so lang wie ein Schreibvorgang
     (Millisekunden bis wenige Sekunden bei vollem Puffer auf einer
     SD-Karte), nie so lang wie ein hängender POST. Bisher waren es bis zu
     30 s, weil erst nach dem Fehlschlag gesichert wurde. *Korrektur nach
     der Prüfung:* Die erste Fassung sicherte im Dashboard-Thread vor dem
     Senden. Ein neuer Alarm wartete dann auf das Ende eines hängenden POST,
     also 30 s oder länger.
2. **Doppelte Ereignisse bei verlorener Antwort.** Kommt der Stapel beim
   Server an, die Antwort aber nicht zurück, sendet der Worker ihn erneut
   (at-least-once, wie bisher). Abhilfe wäre eine Client-ID je Ereignis; das
   ist eine Vertragsänderung und ein eigener Schritt.
3. **Mehr Threads** (Telegram, Telegram-Feedback, Dashboard, Sicherung,
   Lebenszeichen, Archiv): Alle sind Daemon-Threads, die je eine
   Warteschlange abarbeiten. Gemeinsamen Zustand gibt es nur bei Outbox und
   Feedback-Eingang, beide mit Lock bzw. `queue.Queue`.
4. **Schnittstelle zur Eskalationskette** (`eskalationskette-spezifikation.md`
   §3.1/§9): Die Spezifikation erwartet, dass `_dashboard()` synchron die
   Server-ID des Ereignisses zurückgibt. Mit der Outbox geht das nicht mehr.
   Die Kette braucht dafür eine Client-ID je Ereignis oder eine
   Bestätigung aus dem Dashboard-Thread. Beim Umsetzen der Kette klären;
   das ist eine Vertragsänderung am Ingest.
5. **Verworfene Einträge:** Verworfen wird nur ein Eintrag, den die **App
   selbst** auch ohne Bilder mit 400 ablehnt (ihre JSON-Antwort, z. B. bei
   unbekanntem Typ). Ohne Verwerfen würde er jede spätere Meldung
   blockieren; den Befund dazu gab es schon vor dem Umbau. Fremde 400 und
   jede 413 verwerfen nichts.
6. **Timeouts in den Workern bleiben lang** (POST 30 s, Telegram 30 + 20 s,
   `getUpdates` 10 s). Das ist der Rest des Vertragsworts „kurzer Timeout“.
   Die Analyse betrifft das nicht mehr. Hängt ein Kanal, arbeitet er seine
   Aufträge aber nacheinander ab; eine Austreibung überholt dabei die
   wartende Routine (Regel 2). Gegenüber dem alten Stand ist das nicht
   schlechter: Dort blockierte jede Sendung sogar die Erkennung.
7. **Bereits vorher so:** Antwortet ein Captive-Portal mit 200 und HTML,
   gilt das als zugestellt. Bei vollem Puffer (200) wird der älteste
   Eintrag verdrängt, auch eine Austreibung; das wird jetzt protokolliert.

## 6. Ergebnis der adversarialen Prüfung (14.10.2026)

Vier unabhängige Prüfer (Nebenläufigkeit, Alarmverlust, Blockieren,
Regression) haben den ersten Stand geprüft. Jeder Befund wurde von einem
eigenen Skeptiker gegengeprüft. Bestätigt und behoben:

| Befund | Schwere | Behebung |
| --- | --- | --- |
| Ein Rückstau über den Server-Grenzen (100 Einträge, 4,5 MB, mit Bildern schon 5–12 Alarme) blockierte App und Push **dauerhaft**, auch über Neustarts. Das bestand schon vor dem Umbau, der 60-s-Takt verschärfte es | hoch | Regel 3 (Teilstapel, Vorrang, Ablehnung auflösen) |
| Ein vom Server abgelehnter Stapel wurde jede Minute komplett neu hochgeladen | mittel | Regeln 3 und 4 (Tasten, Backoff) |
| Neuer Alarm lag während eines hängenden POST nur im RAM | niedrig | Regel 5 (Sicherungs-Thread) |
| Feedback-Antworten konnten Alarme aus der Warteschlange verdrängen | niedrig | Regel 2 (eigener Kanal, Vorrang) |
| `puffer_max: 0` schaltete App-Meldungen still ab | niedrig | Regel 5a |

Dazu kamen nachgeschärfte Tests (Abruf-Sperre, Hauptthread, nicht blockierende
Antworten) und die Mutationsprobe (Kriterium 25).

**Abnahme `qa-waechter`, 1. Lauf: KEINE FREIGABE** wegen drei kleiner, nicht
dokumentierter Fälle. Alle drei sind behoben (Kriterien 21–23):

1. Eine neue Austreibung wartete bis zum Ende des laufenden
   Rückstau-Durchlaufs.
2. Warteten nur dringende Aufträge, konnte ein neuer Routine-Auftrag einen
   dringenden verdrängen.
3. Eine Proxy-400 verwarf eine Austreibung.

Dazu kommt ein Rest aus dem alten Stand: Das Hard-Negative-Schreiben beim
Votum lief im Hauptthread (Kriterium 24). Gemessen hat er auch: Die
Hauptschleife lief mit 300 Frames ohne Iteration über 0,5 s, obwohl jede
Anfrage 3 s hing (#72: Lücken bis 6 s). Im Stresstest kamen 1492 von 1492
Ereignissen an, keins verloren, keins doppelt. Verworfen wurde der
Befund „GIL-Blockade beim Serialisieren“: Gemessen wurden 0,3 s bei 80 MB,
eine Fehlfunktion folgt daraus nicht. Mit den Teilstapeln sind es jetzt
höchstens 3 MB je Serialisierung.

**Abnahme `qa-waechter`, 2. Lauf (Delta 70390da..ebf1a7b): FREIGABE.**
Die drei Befunde und der Plattenrest sind behoben und nachgemessen:

- Eine Austreibung hinter 200 gepufferten Meldungen kommt nach 6,3 s an
  (vorher nie). Sie wartet höchstens noch auf den gerade laufenden
  Teilstapel. Ruht der Rückstau im Backoff, sind es 0,2 s.
- Die Hauptschleife lief mit hängendem Netz (3 s) und langsamer Platte
  (2 s je Schreibvorgang) samt Votum 400 Frames lang ohne Iteration über
  0,5 s.
- `_nachliefern` kehrt in allen Server-Antwortmustern zurück und ist
  durch die Zahl der Einträge begrenzt.

Der Prüfer nannte einen kosmetischen Rest: Die Antwort „N Bild(er)
gespeichert“ ging seit dem asynchronen Speichern auch dann raus, wenn das
Schreiben scheiterte. Vor #74 gab es in diesem Fall keine Erfolgsmeldung.
Weil der Landwirt keine unbewiesene Meldung bekommen soll, ist das
behoben: Speichern und Antworten sind ein Auftrag (Grundsatz 1,
Kriterium 24). Am alten Stand schlägt der neue Test fehl.

## 7. Nachtrag: Doppel-Tipp zählt einmal (15.10.2026)

**Befund.** `FeedbackSchleife.verarbeite()` erhöhte `zaehler[urteil]`,
bevor geprüft wurde, ob zu dieser Feedback-ID schon abgestimmt wurde. Ein
zweiter Tipp auf ✅/❌ ist möglich, solange die Buttons noch stehen: im
kurzen Fenster, bevor `_entferne_buttons` sie entfernt hat, oder dauerhaft,
wenn das Entfernen am Netz scheitert oder der Alarm schon aus `_offen`
verdrängt war (dann entfernt das Votum die Buttons gar nicht, siehe
`if eintrag is not None` in `verarbeite()`). Telegram liefert ihn als eigenes
Update mit neuer `update_id`, Regel 6 (Offset) greift deshalb nicht. Er
zählte doppelt. Der Zähler geht in den Tagesbericht und damit in die
Treffer-/Fehlalarm-Quote, die Grundlage fürs Nachtraining ist.

### 7.1 Grundsatz

Je Feedback-ID zählt nur das erste Votum. Das gilt auch für einen Wechsel
(erst ✅, dann ❌ oder umgekehrt): Das erste Urteil bleibt.

`_offen` taugt nicht als Gedächtnis dafür. Ein Eintrag fehlt dort auch,
wenn ihn die RAM-Grenze (`MAX_OFFEN = 20`) verdrängt hat. Ein Votum zu
einem verdrängten Alarm ist echt und zählt. Die `FeedbackSchleife` führt
deshalb eine eigene, von `_offen` getrennte Menge `_abgestimmt` der
Feedback-IDs, für die schon ein Votum gezählt wurde.

### 7.2 Grenzen

| # | Regel |
| --- | --- |
| 1 | `_abgestimmt` hält höchstens `MAX_ABGESTIMMT = 200` IDs. Bei Überlauf fällt die älteste heraus. Kein RAM-Wachstum im 24/7-Betrieb (wenige zehn KB) |
| 2 | Eine ID kommt mit dem ersten gezählten Votum hinein, unabhängig davon, ob der Eintrag noch in `_offen` lag |
| 3 | Der Tagesbericht setzt nur die Zähler zurück, nicht `_abgestimmt`. Ein Doppel-Tipp nach dem Bericht auf einen Alarm von vorher zählt ebenfalls nicht |
| 4 | Unverändert: alle Antworttexte an den Landwirt (auch beim Doppel-Tipp), Hard-Negative-Speicherung, `bei_fehlalarm`-Rückruf und Entfernen der Buttons nur beim ersten Votum, Schwellen. Keine neuen Schalter |
| 5 | `_abgestimmt` wird nur im Hauptthread gelesen und geschrieben (wie `zaehler` und `_offen`, Grundsatz 4) |
| 6 | `registriere()` nimmt die neu vergebene ID aus `_abgestimmt`. Innerhalb eines Laufs ist das wirkungslos (IDs sind eindeutig). Nach einem Neustart verhindert es, dass ein Votum auf eine Alt-Nachricht (ID ≥ aktueller Zähler) später das echte erste Votum des neuen Alarms mit derselben ID verschluckt |

Bewusst nicht abgedeckt:

- Ist eine ID aus `_abgestimmt` verdrängt (mehr als 200 spätere erste
  Voten), zählt ein erneuter Tipp darauf wieder. Bei 15 min Cooldown je
  Kuh und Typ sind das Wochen. Für Alarme mit `_offen`-Eintrag sind die
  Buttons bis dahin entfernt, sofern Telegram einmal erreichbar war. Bei
  verdrängten Alarmen und Alt-Nachrichten entfernt das Votum die Buttons
  nie (vorbestehend); dort schützt allein `_abgestimmt`.
- Wechsel ✅ → ❌: Der zweite Tipp zählt nicht, die Antwort lautet aber
  weiter „Danke – notiert (Bilder lagen nicht mehr vor).“ (Grenze 4).
  Vorher stimmte „notiert“, jetzt nicht mehr. Ob der Text angepasst wird,
  entscheidet der Betreiber.
- Nach einem Neustart beginnen `_abgestimmt`, `_offen` und die Zähler leer,
  wie bisher.

### 7.3 Abnahmekriterien

Automatisiert (`edge-agent/tests/test_feedback.py`):

28. Doppel-Tipp ❌ auf dieselbe ID, in zwei Abrufen und im selben Abruf:
    Der Zähler steigt um eins. Antworttext wie bisher, keine weiteren
    Bilder, Buttons nur einmal entfernt, `bei_fehlalarm` nur einmal.
29. Wechsel ✅ → ❌ auf dieselbe ID zählt nur den Treffer.
30. Votum zu einem durch `MAX_OFFEN` verdrängten Eintrag zählt; ein zweiter
    Tipp darauf nicht.
31. Nach `MAX_ABGESTIMMT + 25` Voten enthält `_abgestimmt` genau
    `MAX_ABGESTIMMT` IDs: die ältesten 25 sind heraus, die übrigen in
    Einfügereihenfolge drin; die jüngste bleibt gesperrt.
32. Votum auf eine ID, die erst danach neu vergeben wird (Alt-Nachricht
    nach Neustart): Das erste Votum des neuen Alarms zählt trotzdem.
33. Tagesbericht nach Doppel-Tipp: „✅ 0 Treffer · ❌ 1 Fehlalarm“. Ein
    Doppel-Tipp nach dem Bericht erzeugt keine neue Feedback-Zeile.
34. Gegenprobe: Am Stand vor dieser Änderung schlagen die Kriterien 28,
    29, 33 und der zweite Teil von 30 fehl.

Am realen Agenten (Beweispflicht, offen):

35. Zweimal schnell auf ❌ unter einem echten Alarm tippen. Der
    Tagesbericht zeigt „❌ 1 Fehlalarm“, der Hard-Negative-Ordner enthält
    die Bildserie einmal.

**Ergebnis (15.10.2026):** Gegenprobe am Stand `ecde966`: 6 Checks rot
(28 zweimal, 29, 30 zweiter Tipp, 33 zweimal), 31 bricht mangels
`MAX_ABGESTIMMT` ab. Mutationsprobe am neuen Stand, jede Mutation von
mindestens einem Check erkannt: ohne Freigabe in `registriere()` (32),
ohne Obergrenze (31), Doppel-Erkennung über `_offen` statt eigener Menge
(30, 31, 32), jüngste statt älteste ID verdrängt (31). Alle Edge-Suites
grün.

**Abnahme `qa-waechter` (Delta `ecde966..49d9657`): FREIGABE.** Gegenprobe
und Mutationsprobe nachgestellt. Differenzieller Vergleich Basis gegen neu
mit Zufallsfolgen (synchron und mit Versandkanal, Neustarts, Votes im
selben Abruf, Unsinns-Daten): HTTP-Aufrufe samt Texten, geschriebene
Dateien, `bei_fehlalarm`-Rückrufe, `_offen` und `_offset` identisch; nur der
Zähler weicht ab, exakt nach §7. `_abgestimmt` nur im Hauptthread berührt,
nie über 200 IDs (16–31 KB). Befunde, alle niedrig oder kosmetisch:

1. Buttons verdrängter Alarme werden nie entfernt (vorbestehend): Befund
   und „Bewusst nicht abgedeckt“ präzisiert.
2. Grenze 6 heilt nur den ersten Tipp auf eine Alt-Nachricht: Risiko 1
   präzisiert.
3. Antworttext beim Wechsel ✅ → ❌: als Betreiber-Entscheidung unter
   „Bewusst nicht abgedeckt“ aufgenommen.
4. Test 31 legte die Verdrängungsreihenfolge nur schwach fest (eine
   Mutante „lexikografisch kleinste ID raus“ bestand): Test geschärft,
   prüft jetzt die exakte Menge in Reihenfolge.
5. Gefälschte `callback_data`: Risiko 2.

### 7.4 Risiken

1. **Kollision der Feedback-IDs nach Neustart (vorbestehend, nicht Teil
   dieser Änderung).** `_naechste_id` beginnt nach jedem Start bei 0. Ein
   Tipp auf die noch stehenden Buttons eines Alarms von *vor* dem Neustart
   trifft die gleichnamige ID eines neuen Alarms: Dessen Bilder würden als
   Hard Negatives abgelegt, und `bei_fehlalarm` griffe in die falsche
   Episode. `_abgestimmt` behebt das nicht. Trifft die Alt-Nachricht eine
   ID, die im neuen Lauf schon vergeben ist, gelten beide Voten als eines
   (Zähler um eins zu niedrig statt, wie bisher, beide gezählt). Grenze 6
   heilt nur den ersten Tipp auf eine Alt-Nachricht, solange ihre ID im
   neuen Lauf noch nicht vergeben ist. Die Buttons der Alt-Nachricht
   bleiben dabei stehen (kein `_offen`-Eintrag); ein weiterer Tipp nach der
   Neuvergabe trifft den neuen Alarm wie oben. Abhilfe für die Kollision
   selbst wäre eine Start-Kennung in `callback_data` (Grenze 64 Byte); das
   ist ein eigener Schritt.
2. **Gefälschte `callback_data`** (nur aus dem Chat, mit manipuliertem
   Client): erhöhen den Zähler wie bisher. Neu ist, dass sie echte IDs aus
   `_abgestimmt` verdrängen können. Die Menge bleibt dabei auf 200 IDs
   begrenzt, Telegram begrenzt `callback_data` auf 64 Byte. Unkritisch.
