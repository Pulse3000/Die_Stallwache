# Spezifikation: Kuh-Namen am Kasten (Stufe 1: vom Landwirt bestätigt)

Stand: 29.10.2026 · Entscheidung des Betreibers: „Kühe mit ID und Namen im
Kasten, auf dem Livebild der Web-App und im Auge des Edge-Agenten“.
**Status: Stufe 1 umgesetzt, automatische Abnahme (§6, 1–4) bestanden.
Sichtbar wird etwas erst mit einem eigenen Modell** (ohne Modell gibt es
keine Tracker-Nummern, siehe [`ki-ansicht-spezifikation.md`](./ki-ansicht-spezifikation.md)).
Kriterien 5–9 am Gerät offen. Stufe 2 ist beschrieben, nicht gebaut.

## 1. Grundsatz

1. **Ein falscher Name ist schlimmer als keiner.** Die Nummer am Kasten
   („Kuh #12“) vergibt der Tracker (ByteTrack). Sie ist keine Identität:
   Nach einem Neustart des Agenten oder wenn die Kuh länger aus dem Bild ist,
   bekommt dieselbe Kuh eine neue Nummer. Ein Name darf deshalb nur dort
   stehen, wo der Landwirt ihn **für genau diese laufende Spur** bestätigt
   hat.
2. **Stufe 1: Der Landwirt gibt den Namen, die KI hält ihn fest.** Er sieht
   auf dem Livebild „Kuh #12“ und schreibt dem Telegram-Bot `/kuh 12 Berta`.
   Ab dann steht am Kasten „Kuh #12 · Berta · 52°“, im Alarm „Kuh #12
   (Berta)“, im Alarmbild des Agenten „brunstverdacht Kuh #12 (Berta)“. Der
   Name gilt, solange der Tracker die Kuh unter dieser Nummer führt.
3. **Nur im Arbeitsspeicher, nie auf der Platte.** Nach einem Neustart
   vergibt ByteTrack die Nummern wieder ab 1. Eine gespeicherte Zuordnung
   hinge dann an einer anderen Kuh. Deshalb sind nach jedem Neustart alle
   Namen weg; der Tagesablauf ist: Namen neu geben, wenn man auf das Bild
   schaut.
4. **Nur was gerade im Bild ist, bekommt einen Namen.** `/kuh 99 Berta` für
   eine Nummer, die in den letzten 120 s nicht im Bild war, ändert nichts und
   sagt das. Tippfehler landen so nicht auf einer Kuh, die niemand sieht.
5. **Ein Name gehört höchstens einer Nummer.** Wird „Berta“ neu vergeben,
   wandert der Name („Berta war Kuh #7 – jetzt Kuh #12.“). Zwei Kästen mit
   demselben Namen gibt es nicht.
6. **Kein neuer öffentlicher Weg.** Befehle laufen über den Telegram-Bot, den
   der Agent ohnehin abfragt (getUpdates, keine eingehende Verbindung zum
   Stall). Angenommen werden nur Nachrichten aus der eingetragenen
   `telegram.chat_id`. Der Name kommt über die vorhandene KI-Ansicht-Datei zur
   Webapp und wird dort streng geprüft.
7. **Die Erkennung bleibt unberührt.** Namen ändern weder Schwellen noch
   Cooldowns noch die Kennung im Ereignis (`kuhId` bleibt „Kuh #12“). Sie
   sind reine Anzeige.

### Stufe 2 (beschrieben, nicht gebaut)

Automatische Wiedererkennung über das Fellmuster (Embedding je Kuh, z. B. aus
einem kleinen Re-ID-Netz). Jede bestätigte Zuordnung aus Stufe 1 ist dafür ein
gelabelter Bildausschnitt „das ist Berta“ – die Landwirte erzeugen die
Trainingsdaten nebenbei (Datenschwungrad). Voraussetzung: eigenes Modell
läuft, einige Wochen bestätigter Zuordnungen, eigene Spezifikation mit
Schwellen (Ähnlichkeit, Mindestabstand zum zweitbesten Kandidaten) und dem
Grundsatz „unsicher → nur Nummer“.

## 2. Grenzen

- **Kein Modell, keine Namen.** Im Silent Mode gibt es keine Tracker-Nummern;
  `/kuh` antwortet dann „Noch keine Kuh-Nummern …“.
- **Spur verloren, Name weg.** Ist eine Kuh länger aus dem Bild als der
  `track_buffer` des Trackers (`tracker-kuh.yaml`: 90 Bilder = 90 s bei
  1 FPS) oder wird sie so lange verdeckt, bekommt sie bei Rückkehr eine neue
  Nummer ohne Namen. Neu zuordnen.
- **ID-Wechsel bei Verdeckung** (zwei Kühe kreuzen sich) kann eine Nummer auf
  die andere Kuh übertragen; der Name wandert dann mit. Dieses Risiko trägt
  jede tracker-basierte Anzeige (Skill `bytetrack-tuning`). Der Landwirt sieht
  es am Bild und vergibt neu.
- **Neustart löscht alle Namen** (Grundsatz 3). Der Tracker wird im laufenden
  Agenten nicht zurückgesetzt (`persist=True`); Nummern steigen nur.
- **Nur mit Telegram-Feedback.** Befehle werden mit demselben Abruf gelesen
  wie die Treffer-/Fehlalarm-Knöpfe; mit `telegram.feedback_buttons: false`
  oder ohne Token/Chat gibt es keine Namen.
- **Gruppenchat:** Jeder in der eingetragenen Gruppe kann Namen vergeben. Das
  ist gewollt (Betriebsteam). Fremde Chats werden ignoriert.
- **Umlaute im Alarmbild:** Die Bildschrift des Agenten (OpenCV) kennt keine
  Umlaute; dort steht „Juergen“ statt „Jürgen“. Telegram-Text und Web-Kasten
  zeigen den Namen unverändert.
- **Nur die Stallwache-Kachel zeigt Kästen** (Grenzen der KI-Ansicht).

## 3. Schwellenwerte und Konstanten

| Name | Wert | Wo | Warum |
| --- | --- | --- | --- |
| im Bild für `/kuh` | 120 s | `KuhNamen.SICHTBAR_S` | Tippfehler treffen keine unsichtbare Kuh |
| Nummer vergessen | 24 h ungesehen | `KuhNamen.VERGESSEN_S` | Speicher begrenzen; Nummern kehren nach so langer Zeit nicht zurück |
| höchstens Einträge | 200 | `KuhNamen.MAX_EINTRAEGE` | Schutz gegen Dauerlauf mit vielen ID-Wechseln (älteste zuerst raus) |
| Name | 1–20 Zeichen: Buchstaben inkl. Umlaute/ß, Ziffern, Leerzeichen, Punkt, Bindestrich; beginnt mit Buchstabe oder Ziffer | Agent (`NAME_MUSTER`), Webapp (`leseKiBild`) | kein HTML, keine Steuerzeichen, passt auf den Kasten |

## 4. Konfiguration

Keine neuen Einträge. Voraussetzung im Edge-Agenten: `telegram.token`,
`telegram.chat_id`, `telegram.feedback_buttons: true` (Standard). Der Bot
erhält jetzt neben Knopf-Antworten auch Textnachrichten
(`allowed_updates: callback_query, message`); weiterhin ohne Webhook.

Befehle (im eingetragenen Chat):

| Befehl | Wirkung |
| --- | --- |
| `/kuh 12 Berta` | Kuh #12 heißt Berta (auch `/kuh #12 Berta`, `/kuh@MeinBot 12 Berta`) |
| `/kuh 12 -` oder `/kuh 12` | Name von Kuh #12 entfernen |
| `/kuehe` (oder `/kühe`) | Liste: Namen und Nummern ohne Namen im Bild |
| `/kuh` | kurze Hilfe |

## 5. UI-Texte

| Lage | Text |
| --- | --- |
| Kasten mit Name | „Kuh #12 · Berta · 52°“, ohne gültigen Winkel „Kuh #12 · Berta“ |
| Kasten ohne Name | unverändert „Kuh #12 · 52°“ |
| Alarm (Telegram, App) | „⚠️ BRUNSTVERDACHT – Kuh #12 (Berta)“ und im Text „Kuh #7 (Resi) auf Kuh #12 (Berta)“ |
| Alarmbild des Agenten | „brunstverdacht Kuh #12 (Berta)“ |
| gesetzt | „Kuh #12 heißt jetzt Berta. Gilt, solange die KI die Kuh unter dieser Nummer verfolgt (bis zum Neustart des Agenten).“ |
| umbenannt | „Kuh #12 hieß Resi – jetzt Berta.“ |
| verschoben | „Berta war Kuh #7 – jetzt Kuh #12.“ |
| nicht im Bild | „Kuh #99 ist gerade nicht im Bild – nichts geändert.“ |
| noch keine Nummern | „Noch keine Kuh-Nummern – die KI läuft im Silent Mode oder sieht gerade keine Kuh.“ |
| Name ungültig | „Name ungültig – erlaubt sind 1–20 Buchstaben, Ziffern, Leerzeichen, Punkt und Bindestrich. Beispiel: /kuh 12 Berta“ |
| entfernt | „Name von Kuh #12 (Berta) entfernt.“ / „Kuh #12 hatte keinen Namen.“ |
| Hilfe | „So geht's: /kuh 12 Berta gibt Kuh #12 den Namen Berta · /kuh 12 - entfernt ihn · /kuehe zeigt alle. Die Nummer steht am Kasten im Livebild.“ |

Die Statuszeile der KI-Kästen bleibt unverändert („… Nr. von der KI, nicht
Ohrmarke“): Sie muss am Handy einzeilig bleiben, und der Name ist ein
bestätigter Zusatz zur Nummer, keine Ohrmarke.

## 6. Abnahmekriterien

Automatisch (vor dem Merge):
1. `edge-agent/tests/test_kuh_namen.py`:
   - setzen, umbenennen, verschieben, entfernen; Liste;
   - Nummer nicht im Bild (> 120 s) → nichts geändert; ohne Sichtung → Silent-Text;
   - ungültige Namen (leer, zu lang, HTML, Steuerzeichen) abgelehnt, nichts geändert;
   - Vergessen nach 24 h und Obergrenze 200 (älteste zuerst);
   - Telegram: nur eingetragener Chat, `/kuh@Bot`, `/kuh #12`, Antwort per
     sendMessage, Nicht-Befehle still, `allowed_updates` enthält `message` in
     beiden Abrufwegen; Knopf-Antworten unverändert;
   - `ergaenze` mit zwei Nummern (Aufsprung-Text), nicht doppelt;
   - Alarm: Telegram-Text und Dashboard-`nachricht` mit Namen, `kuhId` und
     Cooldown-Schlüssel unverändert; Alarmbild-Beschriftung ohne Umlaute;
   - KI-Ansicht-JSON: `name` nur, wenn gesetzt;
   - `main()`: `namen.sehe` nach der Analyse und vor den Alarmen; nichts auf Platte.
2. `tests/ki-ansicht.test.ts`: `name` gültig übernommen; ungültig (HTML, zu
   lang, kein String) → nur der Name fällt weg, die Kuh bleibt; Beschriftung
   mit und ohne Winkel.
3. Bestehende Tests unverändert grün (`python3 edge-agent/tests/alle_tests.py`,
   `npm test`, `npm run typecheck`, `npm run lint`). Im echten Browser
   (`tests/e2e/ki-kaesten.mjs`): „Kuh #7 · Berta“ ohne Winkel und eine Kuh
   ohne Namen nebeneinander, Beschriftungen ganz im Bild.
4. Kein Feld der Ereignis-API ändert sich (`kuhId` wie bisher).

Am Gerät (erst mit Modell, Beweispflicht):
5. `/kuh 12 Berta` im Betriebs-Chat → Antwort binnen 15 s; der Kasten der
   Stallwache zeigt „Kuh #12 · Berta“ innerhalb von 2 s nach der Antwort.
6. Brunstverdacht mit benannter Kuh: Telegram, App und Alarmbild nennen den
   Namen; die Analytik zählt das Ereignis unter „Kuh #12“.
7. Nachricht aus einem fremden Chat an den Bot → keine Antwort, keine Änderung.
8. Agent neu starten → keine Namen mehr am Kasten.
9. Kuh verlässt das Bild > 90 s und kommt zurück → neue Nummer ohne Namen.

## 7. Risiken

1. **Name auf der falschen Kuh nach ID-Wechsel** (Grenzen): sichtbar am Bild,
   durch Neuvergabe behoben. Die Erkennung selbst hängt nicht am Namen.
2. **Fremde steuern Namen:** nur der eingetragene Chat wird angenommen; ein
   Name kann keinen Alarm auslösen oder unterdrücken.
3. **Mehr Telegram-Updates:** Mit `message` liefert Telegram auch normale
   Chatnachrichten; der Agent verwirft alles, was kein `/kuh`-Befehl aus dem
   eigenen Chat ist. Abruftakt (10 s) bleibt.
4. **Verwechslung Nummer ↔ Ohrmarke:** Die Statuszeile sagt weiter „Nr. von
   der KI, nicht Ohrmarke“; Stufe 1 ersetzt keine Tierkennzeichnung.

## 8. Umsetzung

| Teil | Datei | Prüfung |
| --- | --- | --- |
| Namen halten, prüfen, ergänzen | `edge-agent/main.py` (`KuhNamen`) | `edge-agent/tests/test_kuh_namen.py` |
| Telegram-Befehle | `edge-agent/main.py` (`FeedbackSchleife._befehl`) | ebenda |
| Alarmtext, Alarmbild | `edge-agent/main.py` (`Notifier._mit_namen`, `_annotiere`) | ebenda |
| Name im JSON der KI-Kästen | `edge-agent/main.py` (`KiAnsicht.daten`) | ebenda |
| Prüfen und Beschriften | `lib/ki-ansicht.ts` | `tests/ki-ansicht.test.ts` |
