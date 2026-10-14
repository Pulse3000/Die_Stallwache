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

1. **Die Analyseschleife wartet nie auf das Netz.** Im Hauptthread bleibt
   nur CPU-Arbeit im Millisekundenbereich: Bilder kodieren, Ereignis bauen,
   in eine Warteschlange legen.
2. **Je Kanal ein Versand-Thread.** Telegram und Dashboard bekommen je einen
   eigenen Worker. Ein hängendes Telegram hält die App-Meldung (und damit
   den Push aufs Handy) nicht auf, und umgekehrt. Innerhalb eines Kanals
   bleibt die Reihenfolge erhalten.
3. **Dashboard als Outbox.** Jedes Ereignis kommt zuerst in die Outbox. Der
   Worker sichert sie auf die Platte, bevor er sendet, und entfernt nur, was
   der Server angenommen hat. Kein Alarm geht verloren, auch nicht bei einem
   Neustart mitten im Senden.
4. **Zustand der Logik bleibt im Hauptthread.** Feedback-Antworten von
   Telegram holt der Worker ab, *verarbeitet* werden sie im Hauptthread
   (sie greifen über `bei_fehlalarm` in die `LogicEngine`).

## 2. Regeln

| # | Regel |
| --- | --- |
| 1 | `melde()`, `wichtig()`, `status()` und `digest_tick()` kehren ohne Netzzugriff zurück. Telegram-Aufträge gehen in die Telegram-Warteschlange, Dashboard-Ereignisse in die Outbox |
| 2 | Telegram-Warteschlange begrenzt auf 50 Aufträge. Bei Überlauf fällt der **älteste** heraus (Log + Zähler). Bei so langem Ausfall ist der neueste Alarm der wichtigste, und die App-Meldung kommt über die Outbox trotzdem an |
| 3 | Outbox: Der Worker sendet alles Ausstehende als **einen** Stapel (wie bisher). Bei Erfolg entfernt er genau die gesendeten Einträge, über die Objekt-Identität und nicht über die Position. Was währenddessen dazukam, bleibt stehen |
| 4 | **Nachlieferung ohne neuen Alarm:** Steht etwas aus, versucht der Worker alle 60 s erneut zu senden. Das schließt den Roadmap-Punkt „Offline-Puffer nachliefern“ |
| 5 | Plattensicherung der Outbox **nur im Worker** (ein Schreiber), immer *vor* dem Senden. Der Hauptthread schreibt nie die ganze Pufferdatei (bei 200 Einträgen mit Bildern bis zu ~80 MB) |
| 6 | Feedback-Abruf: höchstens **ein** Abruf gleichzeitig. Der nächste wird erst angestoßen, wenn das Ergebnis des vorigen im Hauptthread verarbeitet ist (kein Doppel-Votum durch denselben Offset). Hängt ein Abruf länger als 120 s oder fällt er aus der Warteschlange, wird die Sperre freigegeben |
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

- `TELEGRAM_WARTESCHLANGE_MAX = 50`
- `NACHLIEFER_INTERVALL_S = 60`
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
11. Bestehende Suites (Offline-Puffer, Feedback, Episoden, Einbindung) bleiben grün; geänderte Tests warten nur explizit auf den Versand.

Am realen Agenten (Beweispflicht, offen):

12. Uplink im Stall trennen, Fruchtblasen-Testbild zeigen. Die Analyse läuft weiter, Log-Zeitstempel der Frames ohne Lücken > 2 s.
13. Uplink zurück → gepufferte Meldung erscheint binnen 60 s in der App, ohne neuen Alarm.

## 5. Risiken

1. **Prozessende mit vollen Warteschlangen** (SIGTERM, Stromausfall):
   - Ausstehende Telegram-Nachrichten gehen verloren. Bisher ging in
     diesem Fall nur die gerade laufende verloren.
   - Outbox-Einträge, die noch nicht gesichert waren, gehen verloren. Das
     Fenster dafür ist wenige Millisekunden lang; bisher waren es bis zu
     30 s, weil erst nach dem Fehlschlag gesichert wurde.
2. **Doppelte Ereignisse bei verlorener Antwort.** Kommt der Stapel beim
   Server an, die Antwort aber nicht zurück, sendet der Worker ihn erneut
   (at-least-once, wie bisher). Abhilfe wäre eine Client-ID je Ereignis; das
   ist eine Vertragsänderung und ein eigener Schritt.
3. **Mehr Threads** (Telegram, Dashboard, Lebenszeichen, Archiv): Alle sind
   Daemon-Threads, die je eine Warteschlange abarbeiten. Gemeinsamen
   Zustand gibt es nur bei Outbox und Feedback-Eingang, beide mit Lock bzw.
   `queue.Queue`.
