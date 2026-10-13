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

## Fernzugriff ohne Tailscale-App (Stallwache/Tapo)

Standardmäßig sieht man das Tapo-Bild in der Webapp nur mit aktiver
Tailscale-App, weil go2rtc nur im Tailnet erreichbar ist. Für den Zugriff von
jedem Gerät (mit App-Login) geht das Video über die Webapp:

```
Handy ──(Login)──▶ Webapp (Vercel) ──Token──▶ Funnel ──▶ fern-proxy.py ──▶ go2rtc ──▶ Tapo
```

* **`fern-proxy.py`** (nur Python-Standardbibliothek) ist das Einzige, was
  öffentlich wird. Es lässt nur das HLS der Stallwache durch (SD-Stream, Quelle
  fest eingestellt), verlangt den geheimen Header `x-stallwache-token` und
  antwortet sonst 403/404. go2rtc selbst bleibt im Tailnet: seine API könnte
  Befehle auf dem Stall-Rechner ausführen und darf nie ins Netz.
* **Webapp** (`lib/fern.ts`, `/api/stallwache/fern/…`): holt das HLS mit dem
  Schlüssel und reicht es hinter dem App-Login weiter. Ohne aktiven Login
  (`STALLBLICK_PASSWORT`) verweigert sie den Dienst (fail-closed). Ist der
  Stall-Rechner nicht erreichbar, fällt die Kachel auf die Bridge (Tailscale)
  zurück.

**Einrichtung** auf dem Stall-Rechner (einmalig):

```bash
cd ~/Die_Stallwache/bridge && bash fern-einrichten.sh
```

Das Skript startet den Proxy als Dienst, schaltet `tailscale funnel` auf Port
8443 nur für den Proxy, prüft 403/404/200 und gibt drei Werte für Vercel aus
(`STALLWACHE_FERN_URL`, `STALLWACHE_FERN_TOKEN`, `NEXT_PUBLIC_STALLWACHE_FERN=1`).
Danach in Vercel eintragen und neu deployen. Voraussetzung: HTTPS und Funnel
sind in der Tailscale-Verwaltung für das Gerät erlaubt.

**Abschalten:** `NEXT_PUBLIC_STALLWACHE_FERN` und die beiden `STALLWACHE_FERN_*`
in Vercel entfernen (neu deployen) und `sudo tailscale funnel --https=8443 off`.
