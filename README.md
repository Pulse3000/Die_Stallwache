# 🐄 Stallblick — das Dritte Auge im Stall

**Live-Überblick über die Stallkameras + KI-Wache für Brunst- und
Kalbeerkennung.** Betrieb: Oberer Stollenhof. Leitsatz: *Jeder Betrieb, egal
wie klein, verdient eine Nachtwache, die niemals blinzelt — ohne 45.000 €
auszugeben und ohne einen Sensor im Pansen.* (Vision, Prinzipien und
Zielbild: [`docs/vision.md`](docs/vision.md).)

Die mobil-optimierte Webapp zeigt **Stallwache** (Hauptkamera), **Futterwache**
und **Stallbox** — alle drei live über die **Tuya-Cloud**; Rollenwechsel ohne
Seiten-Neuaufbau, Vollbild, Snapshot, Ereignisliste.
Ein gemeinsames Passwort schützt die ganze App (`STALLBLICK_PASSWORT`).
Unter **`/wache`** läuft das KI-Alarm-Dashboard.
Die App ist eine **installierbare PWA** (Android & iOS, „Zum Home-Bildschirm
hinzufügen") mit fünf Bereichen: **Dashboard** (Livebild + letzte Alarme),
**Alarme** (Aktivitätsprotokoll mit Bild-Replay), **Steuerung** (Tuya-Geräte
+ Freitext-/Sprachanfragen), **Analytik** (Verlauf, Tagesgang, Brunstrhythmus)
und **Einstellungen** (Push, Datensparen, Kameras). Vier Kameras:
**Stallwache** (Hauptkamera, WebRTC/HLS — wahlweise
auch über die Tuya-Cloud) sowie **Futterwache**, **Abkalbebox** und
**Weidewache** über die Tuya-Cloud — Rollenwechsel ohne Seiten-Neuaufbau,
Vollbild, Snapshot. Dazu die **Powerwache**, eine Steckdose mit Stromzähler,
in der Steuerung. Ein gemeinsames Passwort schützt die ganze App
(`STALLBLICK_PASSWORT`). Unter **`/wache`** liegt weiterhin die Detailsicht
auf Erkennungslogik und Systemmeldungen.

**Was der Edge-Agent heute kann** (`edge-agent/`, lokal im Stall oder gegen
die Tuya-Cloud): Silent-Mode-Datensammlung, Kalbeverdacht (45°/30 min/20 %),
Austreibungs-Sofortalarm, Eskalation bei Geburtsstillstand, Brunst-Heuristik,
Telegram-Bildserien, Tagesbericht, Wach-Modus — plus zwei Features, die kein
Wettbewerber hat: **Stream-Totmann-Meldung** („das dritte Auge ist blind")
und die **Ein-Tipp-Feedback-Schleife** (❌ Fehlalarm → Bildserie wird
automatisch Trainingsmaterial). Vier weitere Features sind
implementierungsreif spezifiziert (Festliege-Wächter, Brunst-Fusion,
Kalbe-Akte, Lahmheit — siehe `docs/*-spezifikation.md`).

---

## Die App am Handy

Gebaut für die Hand, die gerade noch am Melkzeug war — und für ein Netz, das
im Stall regelmäßig wegbricht.

| Bereich | Was er beantwortet |
| --- | --- |
| **Dashboard** | „Muss ich raus?" — Livebild der gewählten Kamera, Zähler der letzten 24 h, die drei jüngsten Alarme. Eine laufende Austreibung färbt die Kachel rot. |
| **Alarme** | Aktivitätsprotokoll, filterbar nach Art (Kalbung/Brunst/System) und Zeitraum (24 h / 3 / 7 Tage). Jeder Alarm bringt seine **Bildserie** mit: abspielbar wie ein kurzer Film, damit man sieht, worauf das Modell reagiert hat. „Gesehen" quittiert ihn. |
| **Steuerung** | Tränken, Licht und Sensoren über die Tuya-Cloud schalten; die Bedienelemente entstehen aus dem, was das Gerät selbst meldet. Dazu Freitext- und **Sprachanfragen**: „Zeig mir alle Aktivitäten von Kuh #42". |
| **Analytik** | „Was erzählt die Herde über Wochen?" — Verlauf (7/14/30 Tage), **Tagesgang** (wann in der Nacht passiert es?), **Brunstrhythmus je Kuh** mit Prognose des nächsten Termins, Reaktionszeit und Bestätigungsquote. |
| **Einstellungen** | Push-Benachrichtigungen an/aus und pro Alarmart, Datensparen, Startkamera, Diagnose. |

**Push (Firebase Cloud Messaging).** Kalbeverdacht und Brunstverdacht kommen
als normale Meldung, die **Austreibung** als dringender Alarm, der sich nicht
von selbst schließt und stärker vibriert — nachts um drei ist das der
Unterschied. Direkt aus der Benachrichtigung lässt sich der Alarm öffnen oder
quittieren. Der Probealarm in den Einstellungen prüft die ganze Kette
einmal bewusst durch, statt sie im Ernstfall zu testen.
*iOS: Web-Push gibt es nur in der installierten PWA, nicht im Safari-Tab.*

**Analytik.** Dashboard und Alarme beantworten „muss ich jetzt raus?"; die
Analytik beantwortet die Fragen, die man erst nach Wochen stellen kann. Der
**Tagesgang** legt alle Ereignisse über 24 Stunden übereinander und zeigt
schwarz auf weiß, welcher Anteil in die Stunden fällt, in denen niemand im
Stall steht. Der **Brunstrhythmus** rechnet aus den Abständen der
Brunstmeldungen je Kuh den persönlichen Zyklus aus, prognostiziert den
nächsten Termin (nur bei plausiblen 18–24 Tagen — aus einem
6-Tage-„Zyklus" entsteht bewusst kein Datum) und markiert auffällige
Abstände. Dazu die **Reaktionszeit** (Median, nicht Mittelwert: eine Nacht
mit dem Handy im Haus darf die Zahl nicht kippen) und die
**Bestätigungsquote** — wie viele Kalbeverdachte mündeten in eine
Austreibung. Gerechnet wird serverseitig (`/api/analytik`): gemessen ~10 kB
Bericht statt ~48 kB Rohliste. Ohne Chart-Bibliothek, die Diagramme sind
antippbare CSS-Balken.

**Datensparend.** Ein Livestream kostet im Mobilfunk ein Vielfaches einer
Ereignisliste. Deshalb zeigt das Dashboard zunächst ein Standbild und startet
Video erst auf Tippen; Alarmbilder wandern erst über die Leitung, wenn ein
Alarm geöffnet wird. Beides ist abschaltbar.

**Offline.** Fällt das Netz aus, bleibt die App bedienbar: Die Oberfläche
kommt aus dem Cache, der letzte Ereignisstand und alle per Push empfangenen
Alarme liegen lokal (IndexedDB), Alarmbilder bleiben abspielbar.
Quittierungen und Geräteschaltungen wandern in eine Warteschlange und gehen
beim nächsten Kontakt raus. Auf der anderen Seite puffert der Edge-Agent
seine Ereignisse auf der Platte — auch über einen Neustart hinweg — und
liefert sie als Stapel mit dem **ursprünglichen** Zeitstempel nach: Die
Kalbung war um 03:12, nicht um 07:40.

**Anbindung an die GCP-Architektur.** Jedes eingehende Ereignis wird optional
in ein Pub/Sub-Topic gespiegelt (`PUBSUB_TOPIC`), an dem die vorhandenen
Cloud Functions und die YOLO-Nachanalyse auf der Compute Engine hängen. Der
Alarmweg zum Landwirt bleibt davon unabhängig: Ein Ausfall von Pub/Sub oder
FCM blockiert den Ingest nie.

**Datensatz-Archiv (Cloud Storage).** Trainingsbilder aus dem Silent Mode und
die per Feedback markierten Fehlalarm-Bilder liegen sonst ausschließlich auf
der Platte des Stallrechners — meist ein ausgemusterter Laptop ohne Backup.
Mit `dashboard.archiv: true` im Agenten und `GCS_BUCKET` in Vercel wandert
eine Zweitkopie über `POST /api/datensatz` nach Google Cloud Storage. Der
Agent braucht dafür **keine** GCP-Zugangsdaten — er nutzt seinen ohnehin
vorhandenen `EDGE_INGEST_TOKEN`, die Schlüssel bleiben in Vercel. Der Upload
läuft in einem Hintergrund-Thread mit begrenzter Warteschlange: Läuft sie
voll, werden Bilder verworfen statt gestaut — die 1-FPS-Analyseschleife
wartet nie auf das Netz. Es verlässt weiterhin **kein Videostream** den Hof,
nur einzelne komprimierte JPEGs.

## Verhaltens-Schicht, kein NVR

Frigate, Viseron & Co. erkennen *Objekte* („Kuh im Bild"); Stallblick erkennt
**Verhaltensphasen** („Kuh in der Austreibungsphase", „Duldung seit 6 s").
Stallblick ersetzt deshalb keinen NVR — es läuft **parallel** dazu auf
denselben Kameras. Wer bereits Frigate betreibt, behält
es für Aufzeichnung/Zonen und lässt den Stallblick-Edge-Agenten zusätzlich
laufen; wer nichts davon hat, braucht nur diesen Stack. Details und
DIY-Marktvergleich: [`docs/wettbewerbsanalyse.md`](docs/wettbewerbsanalyse.md).

## Kein Gerät im Stall: alles über die Tuya-Cloud

Eine RTSP-Kamera lässt sich weder direkt in ein `<video>`-Tag stecken noch aus
dem Internet erreichen — eine in der Cloud (Vercel) gehostete Webapp kommt an
eine private LAN-Adresse nie heran. Früher löste das eine **Bridge**
(go2rtc/MediaMTX) auf einem Gerät im Stall. Seit alle Kameras Tuya-fähig sind,
entfällt das:
Kameras, die schon in der **Tuya-Cloud** hängen (Stallwache, Futterwache,
Abkalbebox, Weidewache), brauchen keine Bridge — weder fürs Livebild (Webapp:
`TUYA_*`-Env-Variablen) noch für die KI-Datensammlung:

```
Tuya-Kamera  ──▶  Tuya-Cloud  ──kurzlebige HLS-URL──▶  Webapp (Proxy)  ──HTTPS──▶  Browser / App
```

* Die Kamera schickt ihr Bild **selbst** in die Tuya-Cloud — kein Gerät im
  Stall, keine Portfreigabe, kein Cloudflare Tunnel.
* Die Webapp holt pro Zugriff serverseitig eine **kurzlebige HLS-URL**
  (`lib/tuya.ts`) und reicht sie über einen eigenen Proxy durch (Tuyas CDN
  setzt keine CORS-Header).
* **Keine Kamera-Zugangsdaten im Frontend** — die `TUYA_*`-Variablen bleiben
  serverseitig.
Der Agent meldet sich an der Webapp an, holt die kurzlebige HLS-URL selbst
und sammelt im Silent Mode Trainingsbilder — der erste Schritt zum eigenen
Modell (`.claude/skills/modell-training`). Läuft auch auf einem
Android-Handy per Termux ([`edge-agent/termux/`](edge-agent/termux/)).

### Hauptkamera über Tuya (Kalbeüberwachung ganz ohne Bridge)

Auch die **Stallwache** — die Kamera im Abkalbebereich, auf der die Kalbe- und
Brunsterkennung läuft — kann direkt aus der Tuya-Cloud kommen. Damit braucht
ein Betrieb für die vollständige Überwachung überhaupt keine Bridge:

| Variable | Ort | Wert |
| --- | --- | --- |
| `TUYA_ACCESS_ID` / `TUYA_ACCESS_SECRET` | Vercel (serverseitig) | aus dem Tuya-Cloud-Projekt |
| `TUYA_DEVICE_ID_STALLWACHE` | Vercel (serverseitig) | Geräte-ID der Kamera |
| `NEXT_PUBLIC_STALLWACHE_TUYA` | Vercel | `1` |

Im Edge-Agenten dazu `stream.url` leer lassen und
`stream.quelle_api: /api/stallwache/stream` setzen — App und Agent sehen dann
dieselbe Quelle. Tuya ist für die Hauptkamera bewusst **opt-in**: Ohne
`NEXT_PUBLIC_STALLWACHE_TUYA=1` bleibt es beim bisherigen Bridge-Verhalten.
Ist zusätzlich eine Bridge konfiguriert, dient sie als automatischer Fallback.

## Warum (später) eine Bridge?

Die Tapo TCA72 liefert **nur lokal** einen RTSP-Stream
(`rtsp://…@192.168.178.117:554/stream1`). Eine in der Cloud (Vercel) gehostete
Webapp kann diese private LAN-Adresse **niemals direkt** erreichen, und Browser
spielen RTSP ohnehin nicht ab.

Die frühere Bridge-Konfiguration liegt als Legacy unter
[`_archiv/`](_archiv/README.md) — relevant nur noch für Kameras ohne
Cloud-Anbindung.

---

## 1. Tuya-Projekt einrichten (einmalig)

Auf [iot.tuya.com](https://iot.tuya.com) → *Cloud* → Projekt anlegen, dort die
API **„IoT Video Live Stream"** abonnieren und das App-Konto unter *Link Tuya
App Account* verknüpfen (sonst Fehler 1106 bzw. 28841105). Danach notieren:

* **Access ID** und **Access Secret** (gelten projektweit für alle Kameras)
* pro Kamera die **Device ID** unter *Projekt → Devices*

## 2. Webapp konfigurieren & deployen

```bash
cp .env.example .env.local
#  -> TUYA_ACCESS_ID / TUYA_ACCESS_SECRET eintragen
#  -> TUYA_DEVICE_ID_STALLWACHE / _FUTTERWACHE / _STALLBOX eintragen

npm install
npm run dev      # lokal: http://localhost:3000
```

**Deploy auf Vercel:** Repo importieren und die `TUYA_*`-Variablen unter
*Settings → Environment Variables* setzen (**nie** als `NEXT_PUBLIC_*`) —
fertig. Die App ist als PWA installierbar (Homescreen).

Kameras ohne hinterlegte Device ID antworten bewusst mit **503**; ihre Kachel
bleibt dann beim Wartehinweis, die übrigen laufen normal weiter.

## Der Edge-Agent braucht ebenfalls keine Bridge

Die KI-Datensammlung läuft über dieselbe Cloud-Quelle:

```bash
bash edge-agent/setup.sh     # Quelle "1 = Cloud ohne Bridge" (Default)
```

Der Agent meldet sich an der Webapp an, holt die kurzlebige HLS-URL selbst
und sammelt im Silent Mode Trainingsbilder — der erste Schritt zum eigenen
Modell (`.claude/skills/modell-training`). Läuft auch auf einem
Android-Handy per Termux ([`edge-agent/termux/`](edge-agent/termux/)).

---

## Projektstruktur

| Pfad | Inhalt |
| --- | --- |
| `app/` | Next.js App Router – Stallblick-Startseite (mobil optimiert) |
| `components/StallblickApp.tsx` | Hauptscreen: Kamera-Karten, Rollenwechsel, Vollbild, Status, Ereignisse |
| `components/CameraStream.tsx` | Kamera-Container: Tuya-HLS im Hauptbild, ruhiger Platzhalter als Vorschau |
| `lib/config.ts` + `lib/tuya.ts` | Kamera-Liste bzw. signierte Tuya-OpenAPI-Aufrufe (Token-Cache, Stream-Allokation) |
| `app/api/*/stream/` | Pro Kamera ein Endpoint für die kurzlebige HLS-URL; `app/api/futterwache/proxy/` = CORS-Proxy für alle drei |
| `app/wache/` + `app/api/events/` | **KI-Wache**: Alarm-Dashboard & Ingest-API (persistiert automatisch, sobald ein Vercel-KV-Store verknüpft ist) |
| `edge-agent/` | Python-Agent (YOLO-Pose + ByteTrack): Kalbe-/Brunsterkennung, Totmann, Feedback-Schleife; `setup.sh` = Ein-Befehl-Einrichtung |
| `edge-agent/tests/` | Offline-Testsuite (52 Checks, pures Python ohne Installation) |
| `_archiv/` | Legacy: frühere Bridge (go2rtc/MediaMTX, Cloudflare Tunnel) und Cloud-Transcoder — seit der Tuya-Umstellung nicht mehr im Einsatz |
| `app/` | Next.js App Router – die fünf PWA-Bereiche (`/`, `/alarme`, `/steuerung`, `/analytik`, `/einstellungen`) |
| `components/StallblickApp.tsx` | Dashboard-Hauptscreen: Kamera-Karten, Rollenwechsel, Vollbild, Datensparen |
| `components/CameraStream.tsx` | Kamera-Container: WebRTC/HLS (Hauptbild) bzw. Snapshot-Polling (Vorschau) |
| `components/AlarmListe.tsx` + `AlarmBilder.tsx` | Aktivitätsprotokoll mit Filtern, Bild-Replay und Quittierung |
| `components/GeraeteSteuerung.tsx` + `Assistent.tsx` | Tuya-Schaltflächen aus dem Gerätemodell; Freitext-/Sprachanfragen |
| `lib/analytik.ts` + `components/AnalytikApp.tsx` | Langzeitauswertung (rein rechnende Schicht) und die antippbaren Diagramme dazu |
| `tests/` | Testsuite der Auswertungslogik (24 Checks, `npm test`, ohne Build und ohne Zusatzpaket) |
| `public/sw.js` + `lib/offline.ts` | Service Worker (Offline-Shell, Push, Background Sync) und der lokale Puffer dazu |
| `lib/push.ts` + `lib/gcp.ts` | FCM-Versand (HTTP v1) und Service-Account-Auth ohne Zusatzpaket |
| `lib/pubsub.ts` | Spiegelung jedes Ereignisses in die bestehende GCP-Architektur |
| `lib/config.ts` | Kamera- & Bridge-Konfiguration (go2rtc/MediaMTX) aus Umgebungsvariablen |
| `app/wache/` + `app/api/events/` | **KI-Wache**: Detailsicht & Ingest-API (persistiert automatisch, sobald ein Vercel-KV-Store verknüpft ist) |
| `edge-agent/` | Python-Agent (YOLO-Pose + ByteTrack): Kalbe-/Brunsterkennung, Totmann, Feedback-Schleife; `setup.sh` = Ein-Befehl-Einrichtung |
| `edge-agent/tests/` | Offline-Testsuite (77 Checks, pures Python ohne Installation) |
| `bridge/` | go2rtc (Default) + Cloudflare Tunnel; `bridge/termux/` = Android-Weg, `bridge/mediamtx/` = WHEP-Alternative |
| `docs/` | Vision, Roadmap (SSOT), Wettbewerbsanalyse, Metriken, 4 Feature-Spezifikationen, Orchestrierungs-Handbuch |
| `.claude/` | 3 Projekt-Agenten + 12 Skills für die autonome Weiterentwicklung |

## Live

Deployt auf Vercel: **https://die-stallwache.vercel.app**
(eine Kamera-Kachel bleibt beim Wartehinweis, bis ihre `TUYA_DEVICE_ID_*`
gesetzt ist und das Gerät in der Tuya-Cloud online ist).
Deployt auf Vercel: **https://stallwache.vercel.app**
(zeigt „Warte auf Bridge", bis `NEXT_PUBLIC_BRIDGE_URL` gesetzt und die Bridge im Stall verbunden ist).

## Android-App (Der Stallblick)

Der komplette Stallblick-Funktionsumfang ist zusätzlich als **native
Android-App** portiert: [Der-Stallblick](https://github.com/Pulse3000/Der-Stallblick).
Die Kamera-Streams laufen dort ohne Browser-Umwege direkt in der APK
(Media3/ExoPlayer statt hls.js):

* **Stallwache** → Bridge-HLS (go2rtc `api/stream.m3u8` bzw. MediaMTX
  `index.m3u8`), Vorschau per go2rtc-Snapshot-Polling. In der Webapp
  alternativ über die Tuya-Cloud (`/api/stallwache/stream`, siehe „Ohne
  Bridge starten"); die Android-App nutzt bislang nur den Bridge-Weg.
* **Futterwache/Abkalbebox/Weidewache** → Tuya-Cloud: wahlweise über die Webapp-Endpoints
  (`/api/<kamera>/stream`) oder direkt über die Tuya-OpenAPI (HMAC-SHA256 in
  Kotlin portiert); Bridge als Fallback. Der CORS-Proxy der Webapp wird nativ
  nicht benötigt.
* **KI-Wache** → die App spiegelt `GET /api/events` in ihre lokale Datenbank;
  Alarme erscheinen als Overlay auf dem Handy. Die App nutzt keinen
  Passwort-Login — die Webapp läuft ohne `STALLBLICK_PASSWORT`.

## Tech-Stack

Next.js 16 (App Router) · React 19 · Tailwind CSS · hls.js · Tuya OpenAPI ·
Upstash Redis (optional) · Python (OpenCV, Ultralytics)
Next.js 16 (App Router) · React 19 · Tailwind CSS · hls.js · PWA (eigener
Service Worker, IndexedDB, Background Sync) · Firebase Cloud Messaging ·
Google Pub/Sub · Google Cloud Storage (optional) · Vertex AI / Gemini ·
Tuya OpenAPI · go2rtc/MediaMTX · Cloudflare Tunnel · Upstash Redis (optional) ·
Python (OpenCV, Ultralytics)

---

## Status & Roadmap

Software komplett: Sehen ✅ · Verstehen ✅ · Handeln ✅ · Verbessern ✅ —
jedes Feature ist gebaut oder implementierungsreif spezifiziert. Der Weg zum
scharfen System: Silent Mode starten (`bash edge-agent/setup.sh`) → 1–2
Wochen Bilder → erstes Training. **Single Source of Truth für den
Umsetzungsstand: [`docs/roadmap.md`](docs/roadmap.md).**
