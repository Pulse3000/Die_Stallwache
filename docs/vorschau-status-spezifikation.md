# Spezifikation: Kachel-Status ohne Bridge (ungeprüfte Vorschau)

Stand: 15.10.2026 · Ergänzt [`fernzugriff-spezifikation.md`](./fernzugriff-spezifikation.md)
§2 (`NEXT_PUBLIC_BRIDGE_URL` bleibt leer) um die Frage, was eine Kachel
**ohne** Einzelbild über ihren Zustand sagen darf.
**Status: umgesetzt, Befunde des `qa-waechter` (F1–F5) eingearbeitet,
Abnahme am realen Gerät offen** (§6, Punkte 10–12).

## Anlass

In Produktion zeigt der Kopf „0 von 3 Kameras online“ mit rotem System-Punkt.
Nachmessung am 15.10.2026: Alle drei Tuya-Streams (Futterwache, Abkalbebox,
Weidewache) lieferten echte, aktuelle Bilder.

Ursache in `components/CameraStream.tsx`: Ohne Bridge gibt es kein
Einzelbild. Eine Kachel in der Vorschau-Rolle (Datensparen) meldete deshalb
ungeprüft `report(wasLiveRef.current ? "online" : "laedt")`.

- Eine nie live gewesene Vorschau blieb dauerhaft bei „Lädt“. Der Kopf zählte
  sie als „nicht online“ und färbte den Punkt rot.
- Eine einmal live gewesene Kachel meldete nach dem Rollenwechsel dauerhaft
  „Online“, auch wenn der Stream danach ausfiel.

Beides verletzt zwei Prinzipien: „Ruhe vor Fülle“ (kein falscher
Alarmzustand) und „Schweigen ist kein OK“ (kein ungeprüftes „Online“).

## 1. Grundsatz

1. **„Online“ nur mit aktuellem Bildbeweis.** Als Beweis gilt:
   - das `playing`-Ereignis des Video-Elements, solange der Player danach
     keinen fatalen Fehler meldet;
   - ein geladenes Einzelbild der Bridge (go2rtc `frame.jpeg`, Takt 5 s);
   - bei MediaMTX ein `HEAD` auf die HLS-Playlist im 5-s-Takt (bisherige
     Regel, unverändert: Playlist vorhanden heißt, die Quelle publiziert).

   Kein Beweis sind: ein früheres Livebild, die Rolle der Kachel, ein Flag und
   eine erfolgreich zugeteilte Stream-URL.
2. **Ohne Prüfung gibt es einen eigenen Zustand.** Eine Kachel ohne Beweis
   in die eine oder andere Richtung ist `ungeprueft` (Anzeige „Ungeprüft“).
   Er zählt im Kopf weder als online noch als offline, genau wie eine
   pausierte Kachel.
3. **Rot nur bei echtem Ausfall.** Der System-Punkt wird nur rot, wenn
   mindestens eine Kamera nachweislich offline ist und keine online.
   „Lädt“, „Ungeprüft“ und „Pausiert“ färben ihn nie rot.
4. **Der Kopf zählt, was die Kacheln zeigen.** Kopftext und Punkt entstehen
   aus denselben Anzeige-Zuständen wie die Statuszeilen der Kacheln
   (`lib/kamera-status.ts`, `kopfStatus`).
   - Folge: Eine pausierte Kachel zählt als „pausiert“, auch wenn sie vor der
     Pause online war. Bisher zählte sie weiter als online, ohne dass jemand
     nachsah.
   - „Offline“ bleibt auch während der Pause sichtbar (wie bisher).
5. **„Offline“ wird nicht ohne Beweis zurückgenommen.** Wechselt eine
   Offline-Kachel in die Vorschau oder kehrt sie aus der Pause zurück, bleibt
   sie offline, bis eine Prüfung etwas anderes zeigt. Das gilt auch über die
   Navigation hinweg (Dashboard → Alarme → Dashboard): Der Beleg gehört der
   Kamera, nicht der Kachel. Erst ein Neuladen der Seite beginnt frisch.
6. **Ein beendeter Live-Versuch startet nichts mehr.** Wechselt die Kachel in
   die Vorschau oder die Pause, während ein Live-Aufbau noch unterwegs ist
   (Tuya-Zuteilung, hls.js-Import, Reconnect), verwirft der alte Lauf sein
   Ergebnis. Er spielt kein Video und meldet nichts.

## 2. Grenzen

| Grenze | Folge |
| --- | --- |
| Ohne Bridge gibt es kein Einzelbild. Die Vorschau ohne Bridge zeigt nur den Platzhalter | Diese Kachel kann nie „Online“ sein, nur `ungeprueft` oder `offline`. Online wird sie erst als Livebild: Hauptbild mit „Live starten“, Vollbild oder Datensparen aus |
| Der Status-Ping (`camera.tuyaEndpoint`) beweist kein Bild. Bei Tuya teilt die Cloud nur eine HLS-URL zu. Ob die Kamera dann wirklich sendet, ist damit nicht belegt (am Gerät nicht geprüft). Bei der Stallwache mit Fernzugriff ist der Ping eine 6-s-Probe am Stall-Rechner | Ping erfolgreich: weiter `ungeprueft`. Ping zweimal in Folge gescheitert: `offline` (Beleg für eine Störung) |
| Ein Ping im 5-min-Takt ist nicht aktuell genug für „Online“ | Auch eine Probe mit Playlist (Fernzugriff) hebt die Kachel nicht auf „Online“ |
| Ohne Datensparen gibt es keine Vorschau-Kacheln. Alle sichtbaren Kacheln laufen live | Die Regel betrifft nur Datensparen an. Ohne Datensparen gilt allein §1.4 (pausierte Kacheln) |
| Mit Bridge (go2rtc-Einzelbild, MediaMTX-HEAD) gibt es schon eine Prüfung im 5-s-Takt | Dort ändert sich nur der Eintritt: kein übernommenes „Online“ mehr, siehe §3 |

## 3. Regeln und Schwellenwerte

### Eintritt in die Vorschau

Eintritt heißt: Rollenwechsel, Datensparen an, Vollbild geschlossen oder
Rückkehr aus der Pause.

| Quelle der Vorschau | Zustand beim Eintritt | danach |
| --- | --- | --- |
| ohne Bridge (Tuya, Fernzugriff) | `ungeprueft`; war die Kachel `offline`, bleibt sie `offline` | Status-Ping, siehe unten |
| Bridge go2rtc (Einzelbild) | `laedt`; `offline` bleibt `offline` | das erste Einzelbild (nach 600 ms) entscheidet: geladen → `online`, Fehler → `offline` |
| Bridge MediaMTX (HEAD) | unverändert | erster HEAD sofort: 2xx → `online`, sonst `offline` |

### Status-Ping ohne Bridge

Jede Antwort wird zuerst eingeordnet (`pingAntwort`):

| Antwort | Klasse | Begründung |
| --- | --- | --- |
| HTTP 2xx | `ok` | Quelle erreichbar, aber kein Bildbeweis |
| HTTP ≥ 500 (502 Tuya/Funnel gestört, 503 nicht konfiguriert) | `stoerung` | Server erreicht, Quelle gestört |
| kein Netz, Frist (20 s) abgelaufen, sonstiger Status (z. B. 401: Login abgelaufen) | `unklar` | sagt nichts über die Kamera. Ein Funkloch am Handy ist kein Kameraausfall |

| Ereignis | Zustand danach | nächster Ping |
| --- | --- | --- |
| `ok` | `ungeprueft`, Stand zurückgesetzt | 5 min |
| 1. `stoerung` | unverändert | 60 s (Bestätigung) |
| 2. `stoerung` in Folge (≤ 3 min nach der vorigen) | `offline` (belegt) | 2 min |
| jede weitere `stoerung` | `offline` | 2 min |
| `stoerung` mehr als 3 min nach der vorigen (z. B. nach langer Pause) | zählt als 1. Störung; ein belegtes `offline` bleibt stehen | 60 s |
| `unklar` | unverändert, zählt nicht | 2 min |
| Livebild (`playing`) als Hauptbild | `online`, Stand zurückgesetzt | 5 min nach dem Livebild, falls die Kachel bis dahin Vorschau ist |

| Konstante (`lib/kamera-status.ts`) | Wert | Zweck |
| --- | --- | --- |
| `PING_START_MS` | 3 s | frühester Ping nach dem Eintritt; das Hauptbild verbindet sich zuerst |
| `PING_OK_MS` | 5 min | Takt nach Erfolg oder Livebild |
| `PING_BESTAETIGUNG_MS` | 60 s | ein einzelner Fehlschlag färbt nichts rot |
| `PING_OFFLINE_MS` | 2 min | Takt, solange offline; danach erscheint „Live starten“ wieder |
| `PING_FEHLSCHLAEGE_OFFLINE` | 2 | Störungen in Folge bis `offline` |
| `PING_FOLGE_MAX_MS` | 3 min | so dicht müssen zwei Störungen aufeinander folgen (Offline-Takt plus Frist) |
| `PING_TIMEOUT_MS` | 20 s | Frist je Ping; eine hängende Anfrage hält den Takt nicht an |

- **Fälligkeit ist absolut und gehört der Kamera.** Der Ping-Stand
  (`PingStand`: Störungen in Folge, letzte Störung, nächste Fälligkeit,
  belegtes `offline`) liegt je Kamera auf Modulebene von
  `components/CameraStream.tsx`. Rollenwechsel, Pause, Rückkehr und
  Navigation setzen ihn nicht zurück. Je Kamera gibt es also höchstens einen
  Ping pro Intervall, egal wie oft gescrollt, getauscht oder der Tab
  gewechselt wird.
- **Kein Ping bei pausierter Kachel** (Tab verborgen, aus dem Bild), wie bei
  den Streams (`lib/pausiert.ts`).
- **Kosten:** Im Normalbetrieb höchstens 12 Pings pro Stunde je sichtbarer
  Vorschau-Kachel, bei Störung höchstens 31, bei unklarer Lage höchstens 30. Ein Tuya-Ping ist ein
  `allocate`-Aufruf (das Token ist zwischengespeichert). Bei der Stallwache
  ist er eine Probe am Stall-Rechner. Die Antwort (wenige hundert Byte) wird
  verworfen.

### Kopf

`kopfStatus(anzeigen)` bildet den Kopftext aus Teilen, verbunden mit „ · “.
Gezählt (mit Beweis oder Versuch) sind `online`, `offline` und `instabil`.

| Teil | Text |
| --- | --- |
| gezählte Kameras | „2 online“, wenn alle gezählten online sind, sonst „1 von 2 online“ |
| `laedt` | „1 lädt“ / „2 laden“ |
| `ungeprueft` | „2 ungeprüft“ |
| `pausiert` | „1 pausiert“ |

- Zahl und Wort sind mit einem geschützten Leerzeichen verbunden. Bricht der
  Kopf um, steht nie „· 1“ am Zeilenende und „pausiert“ allein darunter.
- Sonderfälle: Sind alle Kameras online, heißt es „4 Kameras online“. Steht
  nur der gezählte Teil da, heißt es „1 von 2 Kameras online“. Sind alle
  Kameras pausiert, heißt es „Livebilder pausiert“.
- **Die Begriffe sind die Kachel-Labels** (Online, Lädt, Ungeprüft, Pausiert).
  Der Kopf sagt also mit denselben Worten, was die Kacheln zeigen.
- **Gemessen statt geschätzt (Chromium, 15.10.2026):** Der Kopftext hat am
  360-px-Handy etwa 187 px, bei 390 px etwa 217 px.
  - „1 online · 2 Vorschau (ungeprüft) · 1 pausiert“ braucht 249 px und wurde
    abgeschnitten. Dabei fiel ausgerechnet der ehrliche Teil weg.
  - „1 online · 2 ungeprüft · 1 pausiert“ braucht 183 px und passt auf beide
    Breiten.
  - Längere Mischzustände (Störung plus Vorschau, z. B. „0 von 1 online ·
    2 ungeprüft · 1 pausiert“) brechen auf eine zweite Zeile um, statt
    abgeschnitten zu werden.
  - Die Anregung „Vorschau (ungeprüft)“ aus der Problembeschreibung lebt in
    der Kachel weiter: Statuszeile „Ungeprüft“ neben dem Hinweis „Vorschau“.

| Punkt (`ton`) | Bedingung |
| --- | --- |
| rot (`stoerung`) | mind. 1 `offline` und keine `online` |
| gelb (`hinweis`) | sonst, wenn mind. 1 `offline`, `instabil` oder `laedt` |
| grün (`ok`) | mind. 1 `online`, keine `offline`/`instabil`/`laedt` |
| grau (`neutral`) | nur `ungeprueft` und `pausiert` |

### Ereignisliste

„X ist online“ bzw. „X ist offline“ entsteht nur, wenn sich der belegte
Zustand einer Kamera zwischen `online` und `offline` ändert. Die
Zwischenzustände `ungeprueft`, `laedt`, `instabil` und `pausiert` erzeugen
keinen Eintrag und setzen nichts zurück. Ein Rollenwechsel wiederholt also
nicht „X ist online“.

## 4. Config

Keine neue Einstellung. Die Takte sind Betriebsparameter der App, nicht des
Hofs. Sie stehen als Konstanten in `lib/kamera-status.ts` und werden dort mit
getestet. Tierart und Kamera spielen keine Rolle.

## 5. UI-Texte

| Ort | Text |
| --- | --- |
| Statuszeile der Kachel, Statusblock | „Ungeprüft“ (grauer Punkt) neben dem Hinweis „Vorschau“ |
| Kopf, Datensparen, Hauptbild live | „1 online · 2 ungeprüft · 1 pausiert“ |
| Kopf, Datensparen, nichts live | „3 ungeprüft · 1 pausiert“ (grau) |
| Kopf, Aufbau | „3 laden · 1 pausiert“ (gelb, nicht rot) |
| Kopf, Störung in der Vorschau | „0 von 1 online · 2 ungeprüft · 1 pausiert“ (rot, zweizeilig) |
| „Live starten“ | bleibt sichtbar bei `ungeprueft`, verschwindet bei `offline` (wie bisher). Das Antippen des Bildes öffnet weiter das Vollbild mit Live-Versuch |

## 6. Abnahmekriterien

Automatisiert / im Repo:

1. `npm test` enthält `tests/kamera-status.test.ts`. Die Tabellen aus §3
   (Kopf, Punkt, Ping) sind dort Zeile für Zeile Testfälle.
2. `npm test`, `tsc --noEmit`, `npm run lint` und `npm run build` sind grün.
3. `tests/e2e/vorschau-status.mjs` im echten Chromium (390×844). Build mit
   leerer `NEXT_PUBLIC_BRIDGE_URL` und `NEXT_PUBLIC_STALLWACHE_FERN=1`.
   Stream-Endpunkte und HLS sind im Test nachgebildet (VP9-fMP4, echtes
   `playing`).
   1. Datensparen an, alle Quellen 2xx: Nach 5 s zeigt keine sichtbare
      Kachel „Lädt“ oder „Online“, alle zeigen „Ungeprüft“. Der Kopf enthält
      „ungeprüft“, nie „0 von“. Der Punkt ist nicht rot.
   2. „Live starten“: Das Hauptbild wird „Online“ (echtes `playing`). Der
      Kopf beginnt mit „1 online“, der Punkt ist grün.
   3. Rollenwechsel („Als Hauptbild“): Das bisherige Hauptbild zeigt
      „Ungeprüft“, nicht „Online“. Das neue Hauptbild wird „Online“.
   4. Datensparen an, eine Quelle antwortet 502: erst nach dem zweiten
      Fehlschlag „Offline“. Der Kopf zählt sie, der Punkt wird rot, weil
      keine Kamera online ist.
   5. Datensparen aus: Die sichtbaren Kacheln werden „Online“, keine zeigt
      „Ungeprüft“. Der Kopf enthält kein „ungeprüft“.
   6. Sparsamkeit: Je Vorschau-Kachel gibt es in den ersten 20 s höchstens
      einen Ping. Eine pausierte Kachel pingt nie.
   7. In keinem Durchlauf gibt es Seitenfehler (`pageerror`).
   8. Wettlauf (§1.6): Vollbild auf und nach 0,5 s wieder zu, die Zuteilung
      kommt erst nach 2 s. Die Vorschau-Kachel bleibt „Ungeprüft“, lädt kein
      Segment und das Video steht. Ebenso bei „Live starten“ mit verborgenem
      Tab nach 0,3 s.
   9. Navigation (§1.5): Abkalbebox belegt „Offline“, dann dreimal
      Dashboard → Alarme → Dashboard. Sie bleibt nach jeder Rückkehr
      „Offline“ und rot. Schon gepingte Kameras pingen dabei nicht erneut.

Am realen Gerät (Beweispflicht, Betreiber + Orchestrator):

10. Produktion, Datensparen an, die Tuya-Kameras senden: Der Kopf zeigt kein
    „0 von 3“ und der Punkt ist nicht rot.
11. Eine Tuya-Kamera wird stromlos, Datensparen an, Kachel in der Vorschau:
    - Wird sie nach spätestens ~3 min „Offline“?
    - Oder bleibt sie „Ungeprüft“, weil Tuya die URL trotzdem zuteilt?

    Das Ergebnis wird hier eingetragen (offen).
12. Am Handy mit ausgeschaltetem Bildschirm während eines Live-Aufbaus: Es
    läuft kein Stream weiter (Datenverbrauch in den Android-Einstellungen).

## 7. Risiken

1. **Tuya-Zuteilung bei stromloser Kamera ist unbekannt** (§6.11). Teilt Tuya
   die URL trotzdem zu, erkennt der Ping nur Cloud- und Konfigurationsfehler.
   Die Anzeige bleibt trotzdem ehrlich („Ungeprüft“, nie „Online“), sieht
   aber den Ausfall nicht. Abhilfe wäre ein Playlist-Abruf je Ping. Er weckt
   aber möglicherweise den Kamera-Upload und wird erst nach §6.11 entschieden.
2. **Ping zeigt „Offline“, „Live starten“ verschwindet.** Ist die Störung
   kurz, kommt der Knopf erst mit dem nächsten Ping (≤ 2 min) zurück. Das
   Vollbild bleibt als Live-Versuch erreichbar.
3. **Bestehend, nicht Teil dieser Änderung:**
   - Ein Livestream, der ohne fatalen Fehler einfriert, bleibt „Online“.
   - Mit Bridge hält eine hängende Einzelbild-Anfrage den letzten Zustand.
     Der Bridge-Weg wird ohnehin nicht mehr empfohlen
     (fernzugriff-spezifikation §2).
4. **Neue Bedeutung im Kopf.** Eine zuvor online gewesene, jetzt pausierte
   Kachel zählt nicht mehr als online. Statt „4 Kameras online“ steht dann
   „3 online · 1 pausiert“. Das ist gewollt (§1.4), ändert aber den
   gewohnten Text.
5. **Kopf zweizeilig in Mischzuständen.** Bei Störung plus Vorschau wächst
   der Kopf um eine Zeile und schiebt den Inhalt um etwa 16 px nach unten.
   Das wird in Kauf genommen: In genau diesem Zustand soll der ganze Text
   lesbar sein.
6. **Unklare Antworten färben nichts.** Im Funkloch oder bei abgelaufenem
   Login (401) bleibt eine Vorschau „Ungeprüft“, auch wenn die Kamera in
   dieser Zeit ausfällt. Das ist gewollt: Ohne Antwort des Servers gibt es
   keinen Beleg. Die Alarmkette (Edge-Agent, Telegram) hängt nicht daran.

### Befunde `qa-waechter` (15.10.2026), eingearbeitet

| Befund | Ursache | Abhilfe | Nachweis |
| --- | --- | --- | --- |
| F1 (hoch): Ein alter Live-Aufbau lief nach Rollenwechsel oder Pause unsichtbar weiter und meldete „Online“ (bestand schon vor dieser Änderung) | `disposedRef` galt für alle Effektläufe und wurde von jedem neuen Lauf zurückgesetzt | Ende-Flag je Effektlauf (`aus`) in allen asynchronen Fortsetzungen, `markLive` eingeschlossen | §6.3.8 |
| F2 (mittel): „Offline“ ging beim Tabwechsel verloren, und jede Rückkehr pingte neu | Ping-Stand lag in Refs der Kachel-Instanz | `PingStand` je Kamera auf Modulebene | §6.3.9 |
| F3 (niedrig): Eine alte Störung vor langer Pause zählte als erste von zweien | Zähler ohne Zeitbezug | Folge-Fenster `PING_FOLGE_MAX_MS`; Funkloch und 401 zählen nicht (`unklar`) | Unit-Tests |
| F4 (kosmetisch): Umbruch „· 1“ / „pausiert“ | normales Leerzeichen | geschütztes Leerzeichen zwischen Zahl und Wort | Unit-Test |
| F5 (Info): Ping ohne Frist | – | `PING_TIMEOUT_MS` 20 s | Code |
