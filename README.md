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
| `docs/` | Vision, Roadmap (SSOT), Wettbewerbsanalyse, Metriken, 4 Feature-Spezifikationen, Orchestrierungs-Handbuch |
| `.claude/` | 3 Projekt-Agenten + 12 Skills für die autonome Weiterentwicklung |

## Live

Deployt auf Vercel: **https://die-stallwache.vercel.app**
(eine Kamera-Kachel bleibt beim Wartehinweis, bis ihre `TUYA_DEVICE_ID_*`
gesetzt ist und das Gerät in der Tuya-Cloud online ist).

## Tech-Stack

Next.js 16 (App Router) · React 19 · Tailwind CSS · hls.js · Tuya OpenAPI ·
Upstash Redis (optional) · Python (OpenCV, Ultralytics)

---

## Status & Roadmap

Software komplett: Sehen ✅ · Verstehen ✅ · Handeln ✅ · Verbessern ✅ —
jedes Feature ist gebaut oder implementierungsreif spezifiziert. Der Weg zum
scharfen System: Silent Mode starten (`bash edge-agent/setup.sh`) → 1–2
Wochen Bilder → erstes Training. **Single Source of Truth für den
Umsetzungsstand: [`docs/roadmap.md`](docs/roadmap.md).**
