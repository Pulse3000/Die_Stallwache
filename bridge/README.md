# Bridge-Wahl: go2rtc oder MediaMTX

Beide wandeln den lokalen RTSP-Stream der Kameras in browser-taugliches
WebRTC/HLS um und werden per Cloudflare Tunnel öffentlich erreichbar gemacht.
Stallblick unterstützt beide über `NEXT_PUBLIC_BRIDGE_TYPE` (siehe
`.env.example` im Repo-Root) — der Wechsel ist reine Konfiguration, kein
Code-Unterschied im Frontend nötig.

| | **go2rtc** (`/bridge`, Default) | **MediaMTX** (`/bridge/mediamtx`) |
| --- | --- | --- |
| WebRTC-Signaling | eigene JSON-API | WHEP-Standard (interoperabel mit anderen WHEP-Clients/Playern) |
| Snapshot (JPEG) | ✅ eingebaut (`/api/frame.jpeg`) | ❌ nicht vorhanden – Stallblick zeigt in der Vorschau einen ruhigen Platzhalter statt Thumbnail |
| Setup-Komplexität | 1 Container | 2 Container (MediaMTX + Caddy, da HLS/WebRTC getrennte Ports sind) |
| Protokoll-Flexibilität | sehr breit (auch ONVIF, ffmpeg-Quellen, Re-Encoding) | breit, Fokus auf Standardprotokolle (RTSP/RTMP/HLS/WebRTC/SRT) |
| Pflege/Community | aktiv, kleinerer Kreis | sehr aktiv, große Community (ex-rtsp-simple-server) |

## Wann welche Wahl?

- **go2rtc (Default):** Du willst die Live-Vorschau-Miniaturbilder
  (Snapshot-Polling) auf dem Startscreen — das ist die runde Stallblick-Erfahrung.
  Empfohlen für die meisten Betriebe.
- **MediaMTX:** Du bevorzugst Standardprotokolle (WHEP/WHIP statt
  proprietärer API), planst evtl. weitere WHEP-fähige Clients/Player, oder
  hattest mit go2rtc Kompatibilitätsprobleme mit deiner Kamera. Die
  Vorschau-Kachel zeigt dann einen Platzhalter statt eines Live-Thumbnails.

## Kein Raspberry Pi/Mini-PC zur Hand?

Falls nur ein Android-Handy verfügbar ist, das dauerhaft im Stall-WLAN
bleiben kann: [`bridge/termux/`](termux/README.md) beschreibt, wie go2rtc und
cloudflared direkt unter Termux (Linux-Terminal für Android, kein Root)
laufen — ohne Docker. **iOS/Apple-Geräte funktionieren dafür nicht** (Apple
erlaubt keine dauerhaften Hintergrundprozesse). Weniger zuverlässig als
dedizierte Hardware, aber ein funktionierender Einstieg ohne Zusatzkauf.

## Einrichtung

Beide Wege sind identisch aufgebaut (`cp .env.example .env`, Werte eintragen,
`docker compose up -d`) — siehe die jeweiligen Ordner:

```bash
# go2rtc (Default)
cd bridge && cp .env.example .env && docker compose up -d

# MediaMTX-Alternative
cd bridge/mediamtx && cp .env.example .env && docker compose up -d
```

In der Webapp (Vercel-Env oder `.env.local`):

```bash
NEXT_PUBLIC_BRIDGE_URL=https://stallwache.example.com   # ersetzt NEXT_PUBLIC_GO2RTC_URL
NEXT_PUBLIC_BRIDGE_TYPE=mediamtx                          # weglassen/= go2rtc fuer den Default
```

`NEXT_PUBLIC_GO2RTC_URL` funktioniert als Alt-Name weiterhin (Alias für
`NEXT_PUBLIC_BRIDGE_URL`), damit bestehende Deployments nicht angepasst
werden müssen.
