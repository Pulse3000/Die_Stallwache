# 🐄 Stallblick — das Dritte Auge im Stall

**Live-Überblick über die Stallkameras + KI-Wache für Brunst- und
Kalbeerkennung.** Betrieb: Oberer Stollenhof. Leitsatz: *Jeder Betrieb, egal
wie klein, verdient eine Nachtwache, die niemals blinzelt — ohne 45.000 €
auszugeben und ohne einen Sensor im Pansen.* (Vision, Prinzipien und
Zielbild: [`docs/vision.md`](docs/vision.md).)

Die mobil-optimierte Webapp zeigt **Stallwache** (Hauptkamera, WebRTC/HLS),
**Futterwache** (läuft bereits live über die Tuya-Cloud) und **Stallbox**;
Rollenwechsel ohne Seiten-Neuaufbau, Vollbild, Snapshot, Ereignisliste.
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
denselben RTSP-Streams der go2rtc-Bridge. Wer bereits Frigate betreibt, behält
es für Aufzeichnung/Zonen und lässt den Stallblick-Edge-Agenten zusätzlich
laufen; wer nichts davon hat, braucht nur diesen Stack. Details und
DIY-Marktvergleich: [`docs/wettbewerbsanalyse.md`](docs/wettbewerbsanalyse.md).

## Ohne Bridge starten (empfohlener Einstieg)

Kameras, die schon in der **Tuya-Cloud** hängen (Futterwache, Stallbox),
brauchen keine Bridge — weder fürs Livebild (Webapp: `TUYA_*`-Env-Variablen)
noch für die KI-Datensammlung:

```bash
bash edge-agent/setup.sh     # Quelle "1 = Cloud ohne Bridge" (Default)
```

Der Agent meldet sich an der Webapp an, holt die kurzlebige HLS-URL selbst
und sammelt im Silent Mode Trainingsbilder — der erste Schritt zum eigenen
Modell (`.claude/skills/modell-training`). Läuft auch auf einem
Android-Handy per Termux ([`edge-agent/termux/`](edge-agent/termux/)).

## Warum (später) eine Bridge?

Die Tapo TCA72 liefert **nur lokal** einen RTSP-Stream
(`rtsp://…@192.168.178.117:554/stream1`). Eine in der Cloud (Vercel) gehostete
Webapp kann diese private LAN-Adresse **niemals direkt** erreichen, und Browser
spielen RTSP ohnehin nicht ab.

Lösung (Standardweg, auch von go2rtc/RTSPtoWeb empfohlen):

```
Tapo TCA72  ──RTSP──▶  Bridge (im Stall-LAN)  ──WebRTC/HLS──▶  Cloudflare Tunnel ──HTTPS──▶  Browser / Webapp
```

* Die **Bridge** wandelt RTSP in browser-taugliches **WebRTC** (< 1 s Latenz)
  bzw. **HLS** (Fallback) um – wahlweise **go2rtc** (Default) oder
  **MediaMTX** (Standard-WHEP-Protokoll). Entscheidungshilfe & Setup beider
  Varianten: [`bridge/README.md`](bridge/README.md).
* **Cloudflare Tunnel** macht die Bridge **24/7 ohne Portfreigabe** per HTTPS erreichbar.
* Die Webapp spricht ausschließlich mit der Bridge – **keine Kamera-Zugangsdaten im Frontend**.

---

## 1. Bridge im Stall einrichten (einmalig)

Auf einem Gerät im selben Netz wie die Kamera (Raspberry Pi, Mini-PC, NAS …) mit
Docker – **go2rtc** (Default) oder **MediaMTX** (Alternative,
[Entscheidungshilfe](bridge/README.md)):

```bash
cd bridge                # oder: cd bridge/mediamtx
cp .env.example .env
#  -> TAPO_PASS und CLOUDFLARE_TUNNEL_TOKEN eintragen
docker compose up -d
docker compose logs -f
```

**Voraussetzungen an der Kamera:** In der Tapo-App unter *Erweiterte
Einstellungen → Kamerakonto* ein Konto anlegen (hier: Benutzer `Stallwache`).
Genau diese Daten nutzt die Bridge für RTSP.

**Cloudflare Tunnel:** Im [Zero-Trust-Dashboard](https://one.dash.cloudflare.com)
einen *Named Tunnel* erstellen, Token in `.env` eintragen und einen *Public
Hostname* (z. B. `stallwache.deine-domain.de`) auf `http://localhost:1984`
zeigen lassen.

> Kein eigene Domain? Für einen schnellen Test geht auch
> `cloudflared tunnel --url http://localhost:1984` (liefert eine zufällige
> `*.trycloudflare.com`-URL).

Prüfen: `https://stallwache.deine-domain.de` öffnet das Bridge-Webinterface
(go2rtc) bzw. liefert die HLS-Playlist (MediaMTX) und zeigt den Stream `stallwache`.

---

## 2. Webapp konfigurieren & deployen

```bash
cp .env.example .env.local
#  -> NEXT_PUBLIC_BRIDGE_URL = https://stallwache.deine-domain.de
#  -> NEXT_PUBLIC_BRIDGE_TYPE = go2rtc  (oder mediamtx, falls diese Bridge genutzt wird)

npm install
npm run dev      # lokal: http://localhost:3000
```

**Deploy auf Vercel:** Repo importieren und die Umgebungsvariable
`NEXT_PUBLIC_BRIDGE_URL` (und optional `NEXT_PUBLIC_BRIDGE_TYPE`,
`NEXT_PUBLIC_STREAM_NAME` sowie `NEXT_PUBLIC_STREAM_NAME_2` für die
Futterwache) setzen – fertig. Die App ist als PWA installierbar (Homescreen).

---

## Projektstruktur

| Pfad | Inhalt |
| --- | --- |
| `app/` | Next.js App Router – Stallblick-Startseite (mobil optimiert) |
| `components/StallblickApp.tsx` | Hauptscreen: Kamera-Karten, Rollenwechsel, Vollbild, Status, Ereignisse |
| `components/CameraStream.tsx` | Kamera-Container: WebRTC/HLS (Hauptbild) bzw. Snapshot-Polling (Vorschau) |
| `lib/config.ts` | Kamera- & Bridge-Konfiguration (go2rtc/MediaMTX) aus Umgebungsvariablen |
| `app/wache/` + `app/api/events/` | **KI-Wache**: Alarm-Dashboard & Ingest-API (persistiert automatisch, sobald ein Vercel-KV-Store verknüpft ist) |
| `edge-agent/` | Python-Agent (YOLO-Pose + ByteTrack): Kalbe-/Brunsterkennung, Totmann, Feedback-Schleife; `setup.sh` = Ein-Befehl-Einrichtung |
| `edge-agent/tests/` | Offline-Testsuite (52 Checks, pures Python ohne Installation) |
| `bridge/` | go2rtc (Default) + Cloudflare Tunnel; `bridge/termux/` = Android-Weg, `bridge/mediamtx/` = WHEP-Alternative |
| `docs/` | Vision, Roadmap (SSOT), Wettbewerbsanalyse, Metriken, 4 Feature-Spezifikationen, Orchestrierungs-Handbuch |
| `.claude/` | 3 Projekt-Agenten + 12 Skills für die autonome Weiterentwicklung |

## Live

Deployt auf Vercel: **https://die-stallwache.vercel.app**
(zeigt „Warte auf Bridge", bis `NEXT_PUBLIC_BRIDGE_URL` gesetzt und die Bridge im Stall verbunden ist).

## Tech-Stack

Next.js 16 (App Router) · React 19 · Tailwind CSS · hls.js · Tuya OpenAPI ·
go2rtc/MediaMTX · Cloudflare Tunnel · Upstash Redis (optional) · Python
(OpenCV, Ultralytics)

---

## Status & Roadmap

Software komplett: Sehen ✅ · Verstehen ✅ · Handeln ✅ · Verbessern ✅ —
jedes Feature ist gebaut oder implementierungsreif spezifiziert. Der Weg zum
scharfen System: Silent Mode starten (`bash edge-agent/setup.sh`) → 1–2
Wochen Bilder → erstes Training. **Single Source of Truth für den
Umsetzungsstand: [`docs/roadmap.md`](docs/roadmap.md).**
