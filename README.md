# 🐄 Stallblick

**Schneller, ruhiger Überblick über zwei Stallkameras.**

Eine schlanke, mobil-optimierte Kamera-Mini-App: **Stallwache** (Hauptkamera,
standardmäßig groß, WebRTC/HLS-Livestream) und **Futterwache** (Zweitkamera,
ressourcenschonende Snapshot-Vorschau). Rollenwechsel per „Tauschen" /
„Als Hauptbild" bindet nur die Kamera-Container um – kein Seiten-Neuaufbau.
Vollbild, Snapshot, kompakter Statusblock und nachgelagert geladene
Ereignisliste inklusive.

---

## Warum eine Bridge?

Die Tapo TCA72 liefert **nur lokal** einen RTSP-Stream
(`rtsp://…@192.168.178.117:554/stream1`). Eine in der Cloud (Vercel) gehostete
Webapp kann diese private LAN-Adresse **niemals direkt** erreichen, und Browser
spielen RTSP ohnehin nicht ab.

Lösung (Standardweg, auch von go2rtc/RTSPtoWeb empfohlen):

```
Tapo TCA72  ──RTSP──▶  go2rtc (im Stall-LAN)  ──WebRTC/HLS──▶  Cloudflare Tunnel ──HTTPS──▶  Browser / Webapp
```

* **go2rtc** wandelt RTSP in browser-taugliches **WebRTC** (< 1 s Latenz) bzw.
  **HLS** (Fallback) um.
* **Cloudflare Tunnel** macht go2rtc **24/7 ohne Portfreigabe** per HTTPS erreichbar.
* Die Webapp spricht ausschließlich mit go2rtc – **keine Kamera-Zugangsdaten im Frontend**.

---

## 1. Bridge im Stall einrichten (einmalig)

Auf einem Gerät im selben Netz wie die Kamera (Raspberry Pi, Mini-PC, NAS …) mit
Docker:

```bash
cd bridge
cp .env.example .env
#  -> TAPO_PASS und CLOUDFLARE_TUNNEL_TOKEN eintragen
docker compose up -d
docker compose logs -f
```

**Voraussetzungen an der Kamera:** In der Tapo-App unter *Erweiterte
Einstellungen → Kamerakonto* ein Konto anlegen (hier: Benutzer `Stallwache`).
Genau diese Daten nutzt go2rtc für RTSP.

**Cloudflare Tunnel:** Im [Zero-Trust-Dashboard](https://one.dash.cloudflare.com)
einen *Named Tunnel* erstellen, Token in `.env` eintragen und einen *Public
Hostname* (z. B. `stallwache.deine-domain.de`) auf `http://localhost:1984`
zeigen lassen.

> Kein eigene Domain? Für einen schnellen Test geht auch
> `cloudflared tunnel --url http://localhost:1984` (liefert eine zufällige
> `*.trycloudflare.com`-URL).

Prüfen: `https://stallwache.deine-domain.de` öffnet das go2rtc-Webinterface und
zeigt den Stream `stallwache`.

---

## 2. Webapp konfigurieren & deployen

```bash
cp .env.example .env.local
#  -> NEXT_PUBLIC_GO2RTC_URL = https://stallwache.deine-domain.de

npm install
npm run dev      # lokal: http://localhost:3000
```

**Deploy auf Vercel:** Repo importieren und die Umgebungsvariable
`NEXT_PUBLIC_GO2RTC_URL` (und optional `NEXT_PUBLIC_STREAM_NAME` sowie
`NEXT_PUBLIC_STREAM_NAME_2` für die Futterwache) setzen – fertig.
Die App ist als PWA installierbar (Homescreen).

---

## Projektstruktur

| Pfad | Inhalt |
| --- | --- |
| `app/` | Next.js App Router – Stallblick-Startseite (mobil optimiert) |
| `components/StallblickApp.tsx` | Hauptscreen: Kamera-Karten, Rollenwechsel, Vollbild, Status, Ereignisse |
| `components/CameraStream.tsx` | Kamera-Container: WebRTC/HLS (Hauptbild) bzw. Snapshot-Polling (Vorschau) |
| `lib/config.ts` | Kamera- & go2rtc-Konfiguration aus Umgebungsvariablen |
| `bridge/` | go2rtc + Cloudflare Tunnel (Docker Compose) für das Stall-Netz |

## Live

Deployt auf Vercel: **https://die-stallwache.vercel.app**
(zeigt „Warte auf Bridge", bis `NEXT_PUBLIC_GO2RTC_URL` gesetzt und die Bridge im Stall verbunden ist).

## Tech-Stack

Next.js 16 (App Router) · React 19 · Tailwind CSS · hls.js · go2rtc · Cloudflare Tunnel

---

## Roadmap

1. ✅ **Livestream 24/7 abrufbar** (dieses Repo, Webapp live auf Vercel; Wiedergabe-Pipeline end-to-end mit Headless-Chromium verifiziert)
2. ⏳ KI-Erkennung Brunst & Kalbung (YOLO-basiert, vgl. Stallsimulator)
3. ⏳ Alarmierung (z. B. Telegram) bei erkannten Ereignissen
