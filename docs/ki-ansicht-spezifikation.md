# Spezifikation: KI-Kästen auf dem Livebild der Stallwache (Kühe mit Kasten und ID)

Stand: 27.10.2026 · Entscheidung des Betreibers: „auf der Webseite bei zum
Beispiel dem Stallwache-Stream die Kühe in der Box mit der zugehörigen ID
anzeigen“. Zuerst als **KI-Ansicht mit 1 Bild/s** umgesetzt (PR #96: das
analysierte Bild als JPEG statt des Videos). Am selben Tag hat der Betreiber
umentschieden: **„KI-Ansicht doch umstellen auf Live-Kästen“**. Die Kästen
liegen jetzt über dem laufenden Livevideo; das JPEG entfällt.
**Status: umgesetzt, automatische Abnahme (§6, 1–6) bestanden. Sichtbar wird
etwas erst mit einem eigenen Modell** (der Agent läuft im Silent Mode);
Kriterien 7–11 am Gerät offen.

## 1. Grundsatz

1. **Livebild bleibt Livebild, die KI legt nur Kästen darüber.** Die Kachel
   der Stallwache bekommt einen Schalter „KI-Kästen“. Ist er an, liegen über
   dem laufenden Video Kästen und Beschriftungen aus der Analyse des
   Edge-Agenten. Das Video, „LIVE“ und alle Knöpfe bleiben, wie sie sind.
   Ein Tippen ins Bild öffnet weiter das Vollbild; die Kästen nehmen keine
   Klicks an.
2. **Die Kästen passen zum gezeigten Moment, nicht zur Gegenwart.** Das
   Video (HLS über den Fernzugriff) läuft einige Sekunden hinter der
   Wirklichkeit, die Analyse fast nicht. Deshalb puffert die Kachel die
   Erkennungen der letzten 30 s und zeigt die, deren Zeit um den Versatz des
   Videos hinter der neuesten liegt:
   - Versatz = Abstand der Wiedergabe zum Ende der HLS-Playlist
     (`video.seekable`) + Zuschlag 1,5 s für den Weg Kamera → go2rtc →
     Playlist (Schätzwert, Kriterium 8 misst ihn).
   - Zwischen zwei Abrufen rückt das Ziel mit der Handy-Uhr weiter.
   - Gerechnet wird nur mit Zeiten des Stall-Rechners untereinander. Eine
     falsch gehende Uhr am Handy oder am Stall stört nicht.
   - Liegt die passende Erkennung mehr als 3 s vor dem gezeigten Moment
     (Lücke im Puffer), zeigt die Kachel **keine** Kästen statt falscher.
   Die erste Fassung hatte ein Overlay wegen dieses Versatzes verworfen
   (Tuya-Stream bis 15 s). Mit dem Fernzugriff ist das Video der Stallwache
   HLS von go2rtc, und der Versatz lässt sich am Player ablesen.
3. **Was eingezeichnet wird** (Befunde `ki-wache` zur ersten Fassung
   eingearbeitet):
   - jede getrackte Kuh: grüner Kasten, „Kuh #12 · 52°“ (Tracker-Nummer wie
     in den Alarmen, Schwanzwinkel nur bei gültigen Keypoints). Kühe ohne
     Tracker-Nummer (-1) fallen weg, es gibt kein „Kuh #-1“.
   - Fruchtblase und Kälberfüße **ab Alarmschwelle** (`override_konfidenz`,
     ≥ 0,80 wie `LogicEngine.bewerte`): roter, dicker Kasten,
     „Fruchtblase 91 % ALARM“. Diese Kästen liegen immer obenauf; keine
     andere Beschriftung verdeckt sie.
   - **unter der Schwelle** ab 0,25: gelber, gestrichelter Kasten,
     „Kälberfüße? 79 % (Alarm ab 80 %)“. Rot und „ALARM“ gibt es nur mit
     Alarm. Prozent werden abgerundet, damit nie „80 %“ ohne Alarm dasteht.
   - unter 0,25: nichts (Rauschen).

   Beschriftungen stehen über dem Kasten, im Bereich von LIVE/Status/Schalter
   an seiner Unterkante, und brechen am Bildrand um, statt abgeschnitten zu
   werden.
4. **Der Weg ist der vorhandene Fernzugriff, nichts Neues ist öffentlich:**

   ```
   Edge-Agent ──schreibt──▶ /dev/shm/stallwache-<kamera>/ki-kaesten.json (RAM)
   Handy ──Login──▶ Webapp ──Token──▶ Funnel ──▶ fern-proxy.py ──liest──▶ Datei
   ```

   - Der Agent schreibt **im Analyse-Modus** nach jeder Analyse (etwa 1/s,
     nach den Alarmen) eine kleine JSON-Datei: Koordinaten relativ zum Bild
     (0..1), Aufnahmezeit des Bilds, Alarmschwelle. Atomar (temporäre Datei,
     dann `os.replace`), lesbar für den Proxy (0644), im Arbeitsspeicher.
   - `fern-proxy.py` liefert sie nur mit Token, nur frisch (§3) und nur
     unter genau einem Pfad. Die go2rtc-API bleibt unberührt.
   - Die Webapp reicht sie nur hinter dem App-Login weiter; die
     Fernzugriff-Route prüft die Sitzung zusätzlich selbst
     (`fernzugriff-spezifikation.md` §1).
   - Die Kachel prüft jede Antwort streng: Nur Zahlen und die zwei bekannten
     Klassen gelangen ins DOM, nie Text vom Stall-Rechner.
5. **Stille Degradation:** Schreibfehler, voller RAM oder fehlender Ordner
   stoppen die Analyse nie. Der Agent protokolliert höchstens eine Warnung
   je Stunde und analysiert weiter. Fällt die KI aus, läuft das Video
   unverändert weiter; die Statuszeile sagt, warum keine Kästen kommen.
6. **Datenschutz:** Die Datei enthält keine Bilder, nur Kästen, Nummern und
   Konfidenzen. Sie verlässt den Stall-Rechner nur über den ausdrücklich
   eingerichteten Fernzugriff und nur auf Abruf eines angemeldeten Nutzers.

## 2. Grenzen

- **Silent Mode zeigt nichts.** Ohne Modell gibt es keine Analyse und damit
  keine Kästen. Die Statuszeile sagt das (§5).
- **Nur die Stallwache, nur mit Fernzugriff.** Die Tuya-Kameras haben keinen
  Weg vom Stall-Rechner zur Webapp außer über Vercel; dafür braucht es eine
  eigene Entscheidung.
- **Die ID ist die Nummer des Trackers, keine Ohrmarke.** Nach einem
  Neustart des Agenten bekommt dieselbe Kuh eine neue Nummer (Skill
  `bytetrack-tuning`, Grenzen). Die Statuszeile sagt das.
- **Ein Kalb kann als „Kuh“ erscheinen.** Das Modell kennt keine Klasse
  „Kalb“; was es als `kuh` erkennt, bekommt einen grünen Kasten.
- **Fruchtblase und Kälberfüße tragen keine Kuh-Nummer.** Die Austreibung
  wird bewusst ohne Tracker erkannt (Recall vor ID, Skill
  `bytetrack-tuning`). Der Kasten zeigt, wo, die Nummer der Kuh daneben
  ergibt sich aus dem Bild.
- **Versatz ist geschätzt.** Der Zuschlag (1,5 s) gilt für go2rtc-HLS und
  ist am Gerät zu prüfen (Kriterium 8). Bei schneller Bewegung (Aufstehen)
  können Kästen kurz neben der Kuh liegen.
- **Analyse langsamer als alle 3 s** (überlastete CPU): Für viele Momente
  gibt es keine passende Erkennung, die Kästen setzen aus und die
  Statuszeile sagt „keine Erkennung zum gezeigten Moment“.
- **Seitenverhältnis:** Analysiert der Agent ein anderes Format als das
  Livebild (z. B. 4:3-Unterstrom zu 16:9), wären die Kästen verschoben. Die
  Kachel blendet sie dann aus und sagt es (§5).
- **Datenverbrauch:** wenige hundert Bytes je Sekunde (gemessen 661 Bytes
  bei 8 Kühen und einer Fruchtblase), also unter 3 MB je Stunde, neben dem
  Video vernachlässigbar. Abrufe nur, solange der Schalter an, die Kachel
  im Bild und der Tab sichtbar ist.

## 3. Schwellenwerte und Konstanten

| Name | Wert | Wo | Warum |
| --- | --- | --- | --- |
| Alarmschwelle (rot, „ALARM“) | `logik.override_konfidenz` (0,80) | Agent → JSON `alarm_ab`, `alarm` | dieselbe Regel wie der Alarm, ≥ |
| Anzeige ab | 0,25 | Agent | darunter Rauschen |
| Frische | 10 s | fern-proxy (Dateizeit, Uhr des Stall-Rechners), Kachel (neueste Zeit steht still, Uhr des Handys) | älter → „nicht aktuell“, nie alte Kästen als aktuell |
| Höchstgröße | 64 KB | fern-proxy | Schutz vor falscher Datei am Pfad |
| Abruftakt | 1 s | Kachel | wie die Analyse |
| Puffer | 30 s | Kachel | deckt den Versatz des Videos |
| Zuschlag zum Versatz | 1,5 s | Kachel | Weg Kamera → go2rtc → Playlist, Schätzwert |
| größte Lücke | 3 s | Kachel | ältere Erkennung → keine Kästen |
| Seitenverhältnis | ±3 % | Kachel | sonst Kästen ausgeblendet |
| höchstens Einträge | 200 Kühe, 200 Objekte | Kachel | Schutz vor unsinnigen Antworten |
| Warnung bei Schreibfehler | höchstens 1 je Stunde | Agent | Log-Flut auf der Karte vermeiden |

## 4. Konfiguration

- **Edge-Agent:** Pfad aus `ki_ansicht.datei` in `config.yaml`, sonst aus
  der Umgebung `KI_ANSICHT_DATEI`; leer = aus. Ein `ki_ansicht`-Eintrag,
  der kein Abschnitt ist, wird mit Warnung ignoriert.
  `edge-agent/docker-compose.yml` setzt beides für den Container:
  - Bind `/dev/shm/stallwache-${KAMERA}:/ki-ansicht`,
  - `KI_ANSICHT_DATEI=/ki-ansicht/ki-kaesten.json` (mit
    `KI_ANSICHT_DATEI=` leer abschaltbar).

  Wer den Agenten per Compose betreibt, muss nichts eintragen. **Betrieb per
  systemd** (`setup.sh`): in `config.yaml`
  `ki_ansicht.datei: /dev/shm/stallwache-stallwache/ki-kaesten.json`.
- **fern-proxy.py:** `KI_ANSICHT_DATEI`, Default
  `/dev/shm/stallwache-stallwache/ki-kaesten.json`. Pfad
  `GET /api/ki-kaesten` (Token wie bei allen Pfaden), bewusst ohne Endung:
  Der Matcher in `middleware.ts` nimmt `*.jpg`, `*.png` usw. vom Login aus.
- **Webapp:** kein neues Env. Der Schalter erscheint, wenn
  `NEXT_PUBLIC_STALLWACHE_FERN=1` gesetzt ist und die Stallwache das
  Hauptbild ist. `lib/fern.ts` hat `ki-kaesten` in der Allowlist (Spiegel
  von `fern-proxy.py`).

## 5. UI-Texte

| Lage | Text |
| --- | --- |
| Schalter | „KI-Kästen“ (an: grün hinterlegt, `aria-pressed`) |
| Kuh | „Kuh #12 · 52°“, ohne gültigen Winkel „Kuh #12“ |
| Objekt mit Alarm | „Fruchtblase 91 % ALARM“, „Kälberfüße 87 % ALARM“ |
| Objekt unter Schwelle | „Kälberfüße? 79 % (Alarm ab 80 %)“ |
| Statuszeile, Kästen da | „KI · 2 Kühe · Versatz ≈ 4 s · Nr. von der KI, nicht Ohrmarke“ |
| Video läuft noch nicht | „KI-Kästen erscheinen, sobald das Livebild läuft.“ |
| keine Erkennung zum gezeigten Moment | „KI-Kästen: keine Erkennung zum gezeigten Moment.“ |
| Seitenverhältnis weicht ab | „KI-Kästen ausgeblendet – Analysebild und Livebild haben verschiedene Seitenverhältnisse.“ |
| 404, noch nie etwas gekommen | „Keine KI-Kästen – vom Stall-Rechner kommen gerade keine Erkennungen (z. B. noch kein Modell, Agent aus, Kamera ohne Bild oder dort nicht eingerichtet).“ |
| neueste Erkennung älter als 10 s (auch 404 danach) | „KI-Kästen nicht aktuell – letzte Erkennung 14:31:40.“ |
| Login abgelaufen (401) | „KI-Kästen nicht erreichbar – bitte neu anmelden.“ |
| Fernzugriff gestört (Netzfehler, 5xx, kaputte Antwort) | „KI-Kästen nicht erreichbar – Fernzugriff zum Stall gestört.“ |
| Beim Laden | „KI-Kästen laden …“ |

Die Statuszeile liegt unten über dem Bild und ist am Handy einzeilig. Kästen
werden nur im Zustand „aktuell“ gezeichnet. Bei „Datensparen“ startet das
Einschalten der Kästen auch das Livebild, denn ohne Video gibt es nichts,
worüber sie liegen könnten.

## 6. Abnahmekriterien

Automatisch (vor dem Merge):
1. Agent-Logiktest (`edge-agent/tests/test_ki_ansicht.py`):
   - Koordinaten relativ und auf das Bild begrenzt; -1 fällt weg;
   - 0,913 → 91 mit Alarm, 0,7996 → 79 ohne, genau 0,80 → Alarm,
     genau 0,25 → angezeigt, darunter nicht; Schwelle aus der Logik;
   - atomar geschrieben, 0644, < 1 KB bei 2 Kühen und 2 Objekten;
   - ein Schreibfehler stoppt nichts, höchstens 1 Warnung je Stunde;
   - Aufruf nur im Analyse-Modus, nach den Alarmen, mit der Aufnahmezeit;
   - Compose-Bind und `KI_ANSICHT_DATEI`.
2. fern-proxy-Test: ohne Token 403, falscher Pfad 404. Datei fehlt → 404,
   älter als 10 s → 404, größer als 64 KB → 404. Frisch → 200 mit
   `application/json` und `Cache-Control: no-store`. Gesperrt bleiben u. a.
   `/api/ki-kaesten/../config`, `/api/ki-kaesten.json`, `/api/ki-ansicht`.
3. `tests/fern.test.ts`: `ki-kaesten` ist erlaubt, ohne Parameter; andere
   Pfade bleiben gesperrt. `tests/middleware.test.ts`: Die Middleware
   erfasst alle Fernzugriff-Pfade.
4. `tests/ki-ansicht.test.ts`:
   - strenge Prüfung der Antwort (auch Klassennamen mit HTML → verworfen);
   - Puffer und Wahl nach Versatz, Lücke > 3 s → keine Kästen;
   - Versatz aus Playlist-Ende und Wiedergabe, Rechteck bei object-contain,
     Seitenverhältnis;
   - Beschriftungen; Zustände und Texte wie §5.
5. E2E im Browser (`tests/e2e/ki-kaesten.mjs`) mit echtem HLS-Livevideo
   (hls.js) und nachgebildeten Erkennungen, Stall-Uhr 1 h daneben:
   - Schalter nur bei der Stallwache; vorher keine Abrufe;
   - Kästen an der richtigen Stelle (±1 %), Beschriftungen ganz im Bild und
     nicht unter dem Schalter; ALARM bleibt sichtbar, wenn Kälberfüße an
     derselben Stelle liegen;
   - die gezeigte Erkennung liegt um den Versatz hinter der neuesten;
   - LIVE bleibt; Klick durch die Kästen öffnet das Vollbild, dort Kästen;
   - Takt 1/s, im verborgenen Tab keine Abrufe;
   - Texte für 404, „nicht aktuell“, Seitenverhältnis, 502, 401;
   - Datensparen: Einschalten startet das Livebild.
6. `npm run typecheck && npm run lint && npm test && npm run build`,
   `python3 edge-agent/tests/alle_tests.py`. Merge ohne `qa-waechter`-Runde
   auf Anweisung des Betreibers („Merge ohne qa“).

Am Gerät (erst mit Modell, Beweispflicht):
7. Die Kästen zeigen dieselbe „Kuh #ID“ wie der nächste Telegram-Alarm.
8. **Versatz:** Kuh steht auf → der Kasten folgt ihr im Video innerhalb von
   1 s. Sonst `KI_ZUSCHLAG_S` in `lib/ki-ansicht.ts` nachstellen.
9. CPU-Last des Agenten auf der A6-3650 steigt messbar nicht (JSON statt
   JPEG; gemessen 0,4 ms je Schreiben auf dem Testrechner).
10. Silent Mode: Statuszeile zeigt den 404-Text aus §5, das Video läuft.
11. Analyse-Rate am Stall-Rechner ≤ 3 s je Bild, sonst setzen die Kästen
    aus (§2).

## 7. Risiken

1. **Kästen neben der Kuh** (Versatz falsch geschätzt): Kriterium 8 misst
   es; der Zuschlag ist eine Konstante. Lieber keine Kästen als falsche: Bei
   Lücken > 3 s und abweichendem Seitenverhältnis bleiben sie weg.
2. **Verwechslung mit Tieridentität:** Die Statuszeile sagt „Nr. von der
   KI, nicht Ohrmarke“.
3. **Veraltete Kästen als aktuell gezeigt:** Die Frische wird doppelt
   geprüft: im Proxy anhand der Dateizeit, in der Kachel daran, ob sich die
   neueste Erkennungszeit weiterbewegt (Handy-Uhr).
4. **Fehlalarm-Eindruck durch Objekte unter der Schwelle:** gelb,
   gestrichelt, mit Fragezeichen und „Alarm ab 80 %“; rot nur mit Alarm.
5. **Ein zusätzlicher Pfad im öffentlichen Proxy:** Er liefert genau eine
   Datei mit fester Größengrenze, nur mit Token und nur per GET. Er führt
   keine Pfadangabe des Aufrufers aus. Die Kachel übernimmt keinen Text aus
   der Antwort.

## 8. Umsetzung

| Teil | Datei | Prüfung |
| --- | --- | --- |
| Kästen als JSON, atomar schreiben | `edge-agent/main.py` (`KiAnsicht`) | `edge-agent/tests/test_ki_ansicht.py` |
| RAM-Ordner und Pfad | `edge-agent/docker-compose.yml`, `config.example.yaml` (`ki_ansicht`) | ebenda |
| Ausliefern am Stall | `bridge/fern-proxy.py` (`lies_ki_ansicht`) | `edge-agent/tests/test_fern_proxy.py` |
| Allowlist, Status | `lib/fern.ts`, `app/api/stallwache/fern/[...pfad]/route.ts` | `tests/fern.test.ts`, `tests/middleware.test.ts` |
| Prüfen, Puffern, Versatz, Texte | `lib/ki-ansicht.ts` | `tests/ki-ansicht.test.ts` |
| Overlay und Schalter | `components/KiKaesten.tsx`, `components/CameraStream.tsx` (`onVideo`), `components/StallblickApp.tsx` | `tests/e2e/ki-kaesten.mjs` |

**Inbetriebnahme am Stall-Rechner**, sobald ein Modell läuft:
1. Agent mit `ANALYSE=1 docker compose up -d --build` neu starten. Compose
   bindet `/dev/shm/stallwache-stallwache` ein und setzt den Pfad
   (systemd-Betrieb: §4).
2. `fern-proxy.py` aktualisieren (`git pull`, dann
   `sudo systemctl restart stallwache-fern`). Der Default-Pfad passt, kein
   neues Env nötig.
3. Webapp deployen (Merge). Der Schalter erscheint bei aktivem
   Fernzugriff (`NEXT_PUBLIC_STALLWACHE_FERN=1`).
