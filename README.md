# 🐄 Stallblick

**Schneller, ruhiger Überblick über zwei Stallkameras.**

Eine schlanke, mobil-optimierte Kamera-Mini-App: **Stallwache** (Hauptkamera,
standardmäßig groß, WebRTC/HLS-Livestream) und **Futterwache** (Zweitkamera,
ressourcenschonende Snapshot-Vorschau). Rollenwechsel per „Tauschen" /
„Als Hauptbild" bindet nur die Kamera-Container um – kein Seiten-Neuaufbau.
Vollbild, Snapshot, kompakter Statusblock und nachgelagert geladene
Ereignisliste inklusive.

---

## Verhaltens-Schicht, kein NVR

Frigate, Viseron & Co. erkennen *Objekte* („Kuh im Bild"); Stallblick erkennt
**Verhaltensphasen** („Kuh in der Austreibungsphase", „Duldung seit 6 s").
Stallblick ersetzt deshalb keinen NVR — es läuft **parallel** dazu auf
denselben RTSP-Streams der go2rtc-Bridge. Wer bereits Frigate betreibt, behält
es für Aufzeichnung/Zonen und lässt den Stallblick-Edge-Agenten zusätzlich
laufen; wer nichts davon hat, braucht nur diesen Stack. Details und
DIY-Marktvergleich: [`docs/wettbewerbsanalyse.md`](docs/wettbewerbsanalyse.md).

## Warum eine Bridge?

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
| `app/wache/` + `app/api/events/` | **KI-Wache**: Alarm-Dashboard & Ingest-API für Brunst-/Kalbeerkennung |
| `edge-agent/` | Python-Agent (YOLO-Pose + ByteTrack): Kalbe-/Brunsterkennung lokal im Stall, Telegram-Alarm |
| `bridge/` | go2rtc (Default) + Cloudflare Tunnel für das Stall-Netz |
| `bridge/mediamtx/` | MediaMTX-Alternative (WHEP-Standard) + Caddy + Cloudflare Tunnel |

## Live

Deployt auf Vercel: **https://die-stallwache.vercel.app**
(zeigt „Warte auf Bridge", bis `NEXT_PUBLIC_BRIDGE_URL` gesetzt und die Bridge im Stall verbunden ist).

## Tech-Stack

Next.js 16 (App Router) · React 19 · Tailwind CSS · hls.js · go2rtc/MediaMTX · Cloudflare Tunnel

---

## Roadmap

1. ✅ **Livestream 24/7 abrufbar** (Webapp live auf Vercel; Wiedergabe-Pipeline end-to-end mit Headless-Chromium verifiziert)
2. ✅ **KI-Erkennung Brunst & Kalbung** – Edge-Agent in `/edge-agent` (YOLOv8-Pose + ByteTrack, Schwanzwinkel-Zeitfilter, Fruchtblasen-Override, Aufsprung-Heuristik) + KI-Wache-Dashboard unter `/wache`
3. ✅ **Alarmierung** – Telegram-Bot (Foto + Warnung, 15-Min-Cooldown) und Dashboard-Ingest (`POST /api/events`, Token-gesichert)
4. ⏳ Eigenes Modell trainieren (Silent Mode → CVAT-Labeling → Colab-Training, Anleitung in `edge-agent/README.md`)
