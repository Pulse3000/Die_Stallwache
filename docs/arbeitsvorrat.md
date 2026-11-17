# Arbeitsvorrat

Die Roadmap ([`roadmap.md`](./roadmap.md)) sagt, **was** gebaut, offen oder
blockiert ist. Dieses Dokument sagt, **was als Nächstes zu tun ist** — in
Paketen, die eine Sitzung ohne Vorwissen abarbeiten kann.

## So wird damit gearbeitet

1. Das oberste freie Paket aus Abschnitt A nehmen. Reihenfolge = Priorität.
2. Ein Paket je PR. Nicht zwei Pakete mischen, nichts „nebenbei" mitbauen.
3. Die genannte Spezifikation ganz lesen, bevor Code entsteht. Fehlt eine
   Regel, zuerst die Spezifikation ergänzen (Entscheidung vor Code).
4. Die Abnahme des Pakets erfüllen **und** `npm run pruefen` grün.
5. Beim Abschluss: Paket hier löschen, Roadmap-Zeile nachführen. Der Stand
   steht nur in der Roadmap — hier steht nie „erledigt".
6. Pakete aus B, E und W führt der Agent **nicht** aus. Er darf sie
   vorbereiten (Befehle prüfen, Anleitung schärfen) und den Betreiber daran
   erinnern, mehr nicht.

Zeigt sich beim Arbeiten etwas Neues, das nicht ins Paket gehört: als neues
Paket hier eintragen, nicht sofort bauen.

---

## A — Agent kann sofort (keine Voraussetzung)

### A1 · Alarme fallen nie aus der Ereignisliste (P1, Härtung)

- **Ziel:** Ein Alarm im Auswertefenster darf nicht von Systemmeldungen aus
  der Liste gedrängt werden.
- **Warum:** Alarme und Systemmeldungen teilen sich eine Liste mit Obergrenze.
  Flackert ein Stream, kann ein älterer Alarm herausfallen; die Statusabfrage
  sagt dann `OK` statt `WARNUNG`/`KRITISCH`. Das bricht „Schweigen ist kein OK".
- **Lesen:** [`statusabfrage-spezifikation.md`](./statusabfrage-spezifikation.md)
  §9.7 Punkt 3; `lib/events.ts`.
- **Schritte:** Regel in §9 der Spezifikation festlegen (Alarme beim Kürzen
  bevorzugen **oder** getrennt speichern — die einfachere Variante wählen und
  begründen). Test zuerst: 200 Systemmeldungen nach einem Alarm, der Alarm
  bleibt abrufbar und der Status bleibt `WARNUNG`. Dann umsetzen, für den
  In-Memory-Puffer **und** den KV-Weg.
- **Abnahme:** neuer Test in `tests/` grün; bestehende Tests unverändert grün;
  Stapel-Ingest und Quittierung arbeiten wie zuvor (`qa-waechter`, Punkte 2–3).

### A2 · Funkloch und abgelaufener Login sind kein Kameraausfall (P2)

- **Ziel:** Der Live-Pfad färbt bei unklarer Antwort nicht rot.
- **Warum:** Mit Datensparen aus meldet ein Funkloch am Handy nach ~60 s
  „0 von 3 online". Der Landwirt hält die Kameras für ausgefallen.
- **Lesen:** [`vorschau-status-spezifikation.md`](./vorschau-status-spezifikation.md)
  §3 und §7 (Risiken 2 und 7); `lib/kamera-status.ts`,
  `components/CameraStream.tsx` (`startTuya`, `scheduleReconnect`).
- **Schritte:** Regel zuerst in §3/§7 der Spezifikation: Zuteilung per
  `pingAntwort` einordnen, unklar → „instabil" statt „offline"; bei „offline"
  aus dem Live-Pfad die Fälligkeit des Pings auf ≤ `PING_OFFLINE_MS` setzen.
  Reine Logik nach `lib/kamera-status.ts`, dort testen. Dann die Komponente.
- **Abnahme:** Unit-Tests in `tests/kamera-status.test.ts`; E2E nach dem
  Muster `tests/e2e/vorschau-status.mjs`: Datensparen aus, Stream-Endpunkte
  netzlos, nach 90 s nicht rot. Bestehende E2E-Skripte unverändert grün.
- **Prüfer:** Agent `qa-waechter` (Browser-Smoke, Screenshots ansehen).

### A3 · Notstrom-Lücke aussprechen (P2, Doku + Tagesbericht)

- **Ziel:** README und Tagesbericht sagen, dass bei Stromausfall die ganze
  Kette still ausfällt, solange keine USV steht.
- **Warum:** Der Totmann-Wächter kann einen Stromausfall nicht melden, weil der
  Uplink mit ausfällt. Ein verschwiegener stiller Ausfall ist der eigentliche
  Gegner (Vision, Prinzip 6).
- **Lesen:** Roadmap-Zeile „Notstrom-Lücke"; `eskalationskette-spezifikation.md`
  Risiko 13; `digest_tick` in `edge-agent/main.py`.
- **Schritte:** README-Abschnitt mit der Lücke und der Abhilfe (USV an
  Rechner, Router, Broker). Tagesbericht: eine Zeile, abschaltbar per Config
  (Default an), Text vom Agenten `ki-wache` formulieren lassen. Test für die
  Zeile und den Schalter.
- **Abnahme:** `npm run test:agent` grün mit neuem Check; `config.example.yaml`
  beschreibt den Schalter; kein zusätzlicher Telegram-Versand.

### A4 · Weckkanal-Einkaufsliste in die README (P1, nur Doku)

- **Ziel:** README nennt die Hardware für den lokalen Weckkanal, bevor die
  Weckton-Stufe gebaut wird.
- **Warum:** Ein 3100-Hz-Piepser weckt viele Menschen nicht; ein Weckton ohne
  Stopp-Taster wird beim ersten Fehlalarm abgeklemmt.
- **Lesen:** `wettbewerbsanalyse.md` §1d; Roadmap-Zeile „Weckkanal-Einkaufsliste".
- **Schritte:** Abschnitt mit den drei Teilen (Zwischenstecker mit
  geräteseitiger Abschaltzeit, tieffrequentes Weckgerät oder Vibrationskissen,
  lokaler Quittierungs-Taster), Richtpreise aus der Analyse, Hinweis „Gerät
  gehört ins Wohnhaus". Keine neuen Zahlen erfinden — nur übernehmen, was in
  der Analyse belegt ist.
- **Abnahme:** `npm run geruest` grün; jede Zahl steht so in §1d.

### A5 · WebRTC-Pfad: alte Läufe vom neuen trennen (P3, nur mit Bridge)

- **Ziel:** Ein alter Verbindungsversuch kann keinen neuen abbrechen.
- **Lesen:** `vorschau-status-spezifikation.md` §7 Risiko 8;
  `components/CameraStream.tsx` (`startBridgeWebrtc`).
- **Schritte:** Erst im Browser nachstellen (Befund belegen), dann im
  `catch` nur die eigene Verbindung schließen und nach jedem `await` das
  Ende-Flag `aus` prüfen. Risiko 8 nachführen.
- **Abnahme:** E2E-Skript, das den Wettlauf erzeugt und vor dem Fix rot ist.
  In der Produktion ohne Bridge tritt der Fehler nicht auf — deshalb P3.

### A6 · Kleine Punkte aus „Brunst zuerst" §9

- **Wach-Modus warnt**, wenn die Austreibung nicht scharf ist (er senkt sonst
  nur die Brunst-Mindestdauer). Code klein, Test dazu, Text von `ki-wache`.
- **Skill `fehlalarm-triage`** für die Brunst-Phase ergänzen: Modellfehler und
  Regelfehler getrennt führen (Punkt B5, Risiko 5 der Entscheidung).
- **Lesen:** [`brunst-zuerst-entscheidung.md`](./brunst-zuerst-entscheidung.md) §8–§9.
- **Nicht** aus dieser Liste bauen: B4 (Startmeldung) und die stille
  Nacht-Zustellung — beide warten auf eine Betreiber-Entscheidung (Abschnitt E).

### A7 · Migration `middleware.ts` → `proxy.ts` (P2, sicherheitskritisch)

- **Ziel:** Die von Next 16 als veraltet gemeldete Konvention ablösen, ohne
  dass sich am Schutz etwas ändert.
- **Warum:** An dieser einen Datei hängen der Passwortschutz der ganzen App
  **und** die Ausnahme für `/sw.js`. Fällt die Konvention in einem künftigen
  Major weg, verschwinden beide gleichzeitig und lautlos.
- **Schritte:** Vorher die Gegenprobe bei gesetztem `STALLBLICK_PASSWORT`
  aufzeichnen (Seiten 307 → `/login`, API 401, Ingest per Token 201, `/sw.js`
  200 als JavaScript, Statusabfrage mit Lese-Token). Dann umbenennen,
  `tests/middleware.test.ts` und alle Verweise in Doku, Skills und Agenten
  nachziehen. Danach dieselbe Gegenprobe — die Ergebnisse müssen gleich sein.
- **Abnahme:** Build ohne die Veraltet-Warnung; Gegenprobe vorher = nachher;
  Agent `qa-waechter`, Punkte 2 und 6. Nur als eigenes Paket, nie nebenbei.

### A8 · Wiederkehrend, wenn sonst nichts frei ist

Reifegrad-Regel: Härtung vor neuen Features. Skill `security-sweep` oder ein
gezielter Bug-Hunt auf einer Route. Drei Durchläufe ohne Befund → auf einen
kurzen Statuscheck zurückfahren (Skill `betriebs-bereitschaft`).

---

## B — Betreiber, am Gerät oder im Konto

Der Agent kann diese Schritte nicht ausführen. Reihenfolge = Wirkung.

| Nr. | Schritt | Danach |
| --- | --- | --- |
| B1 | **Kamera richten:** Stallwache auf die besamungsfähige Gruppe im Laufbereich, Kasten vor der Linse entfernen ([`brunst-zuerst-entscheidung.md`](./brunst-zuerst-entscheidung.md) §2, §9 B2) | Datensammlung für das erste Modell wird brauchbar |
| B2 | **Ein Agent statt zwei:** am Stall-Rechner `bash edge-agent/deploy/umstieg-von-kuhwatch.sh --trocken`, dann ohne `--trocken` ([`ein-edge-agent-spezifikation.md`](./ein-edge-agent-spezifikation.md), Kriterium 8) | Silent Mode sammelt Trainingsbilder; Lebenszeichen kommen in der App an |
| B3 | **KV-Store verknüpfen:** Vercel → Storage → Create → Upstash Redis → Projekt verknüpfen | Agent führt Skill `persistenz-live-schalten` aus; Paket W1 wird frei |
| B4 | **`STATUS_READ_TOKEN`** in Vercel setzen (anderer Wert als `EDGE_INGEST_TOKEN`) | Tagesreport bekommt Live-Daten statt `503` |
| B5 | **Firebase-Projekt** einrichten | Agent führt Skill `push-live-schalten` aus; Paket W2 wird frei |
| B6 | **Training:** Bilder labeln, Colab-Lauf, Abnahme (Skill `modell-training`, Gates K/Ü/D/E) | erstes Modell; Pakete W3–W6 werden frei |
| B7 | **Abnahmen am Gerät**, die in der Roadmap als „offen" stehen: Fernzugriff (Kriterien 4, 5, 7–10), Bildfrische (9–11), Versand-Entkopplung (12–13), Austreibungs-Takt (16–17), Statusabfrage (16–18, 25–26), Vorschau-Status (§6.10–6.12) | jeweilige Roadmap-Zeile von 🔄 auf ✅ |
| B8 | **Firestore-Sink:** `cloud-functions/pubsub-firestore-sink/einrichten.sh` in der Cloud Shell (optional, Langzeit-Ablage) | — |

## E — Entscheidungen des Betreibers

Bis zur Entscheidung gilt der heutige Stand. Der Agent setzt keine Variante
um und ändert keine Schwelle.

| Nr. | Frage | Unterlage |
| --- | --- | --- |
| E1 | Cloud-Vorgabe (60 %, `back_mid`, Sofort-Alarm nur Fruchtblase) oder Edge-Regeln behalten? Empfehlung in der Unterlage: Edge-Regeln behalten | [`statusabfrage-spezifikation.md`](./statusabfrage-spezifikation.md) §8 |
| E2 | Brunst-Verhaltensschicht (Entwurf v0.1): verwerfen oder für die Pose-Phase überarbeiten? | [`brunst-verhaltensschicht-spezifikation.md`](./brunst-verhaltensschicht-spezifikation.md) |
| E3 | Tuya-Kameras über go2rtc am Stall-Rechner abholen (weniger Verzögerung, dafür Tuya-Zugangsdaten im Stall)? Vorher Verzögerung messen | Roadmap, Zeile „Tuya-Kameras über go2rtc" |
| E4 | Mindestabdeckung des 30-min-Fensters nach langer Verdeckung — vor dem Scharfschalten der Kalbeüberwachung | Roadmap, Zeile „Training-Pipeline" |
| E5 | Erfolgsmaß Brunst (B1), Datensammlung für Phase 2 (B3), Startmeldung „Kalbung nicht überwacht" (B4), Brunst-Alarme nachts still zustellen | [`brunst-zuerst-entscheidung.md`](./brunst-zuerst-entscheidung.md) §9 |

## W — Wartet auf einen Auslöser

Sobald der Auslöser eintritt, wird das Paket zu einem A-Paket. Vorgehen immer
über den Skill `spezifikation-umsetzen` (Umfang auf den freien Teil schneiden).

| Nr. | Paket | Auslöser | Spezifikation |
| --- | --- | --- | --- |
| W1 | Nacht-Eskalation Stufen 1–2 (Push wiederholen, zweiter Empfänger); Weckton erst nach 7 Nächten Messung | B3 | [`eskalationskette-spezifikation.md`](./eskalationskette-spezifikation.md) |
| W2 | Alarmweg-TÜV (gesendet → zugestellt → quittiert, wöchentlicher Probealarm) | B5 | Roadmap, Zeile „Alarmweg-TÜV" |
| W3 | Festliege-Wächter | B6 | [`festliege-spezifikation.md`](./festliege-spezifikation.md) |
| W4 | Kalbe-Akte (Teil-Akte) | B6 | [`kalbe-akte-spezifikation.md`](./kalbe-akte-spezifikation.md) |
| W5 | Zwei-Kamera-Brunst-Fusion | B6 + zwei Kameras auf dieselbe Bucht + Broker | [`brunst-fusion-spezifikation.md`](./brunst-fusion-spezifikation.md) |
| W6 | Lahmheits-Frühwarnung | zweites Training mit Keypoint `spine_mid` + eigene Validierung | [`lahmheit-spezifikation.md`](./lahmheit-spezifikation.md) |
