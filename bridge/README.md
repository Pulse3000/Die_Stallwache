# Bridge-Wahl: go2rtc oder MediaMTX

Beide wandeln den lokalen RTSP-Stream der Kameras in browser-taugliches
WebRTC/HLS um. Sie selbst sind **nie öffentlich**. Von außen kommt das Bild
nur über den Fernzugriff (Tailscale Funnel → `fern-proxy.py` mit Token, siehe
unten und [`docs/fernzugriff-spezifikation.md`](../docs/fernzugriff-spezifikation.md)).
Den Fernzugriff gibt es nur für go2rtc. MediaMTX ist ohne ihn nur im LAN bzw.
Tailnet erreichbar. Einen Cloudflare-Tunnel gibt es nicht mehr.

| | **go2rtc** (`/bridge`, Default) | **MediaMTX** (`/bridge/mediamtx`) |
| --- | --- | --- |
| WebRTC-Signaling | eigene JSON-API | WHEP-Standard (interoperabel mit anderen WHEP-Clients/Playern) |
| Snapshot (JPEG) | ✅ eingebaut (`/api/frame.jpeg`) | ❌ nicht vorhanden – Stallblick zeigt in der Vorschau einen ruhigen Platzhalter statt Thumbnail |
| Setup-Komplexität | 1 Container | 2 Container (MediaMTX + Caddy, da HLS/WebRTC getrennte Ports sind) |
| Protokoll-Flexibilität | sehr breit (auch ONVIF, ffmpeg-Quellen, Re-Encoding) | breit, Fokus auf Standardprotokolle (RTSP/RTMP/HLS/WebRTC/SRT) |
| Pflege/Community | aktiv, kleinerer Kreis | sehr aktiv, große Community (ex-rtsp-simple-server) |

## Wann welche Wahl?

- **go2rtc (Default):** Einziger Weg mit Fernzugriff (`fern-proxy.py`).
  Empfohlen für alle Betriebe.
- **MediaMTX:** Nur wenn go2rtc mit deiner Kamera nicht zurechtkommt. Ohne
  Fernzugriff, also nur im LAN/Tailnet nutzbar und nicht am Gerät erprobt.

Die frühere Android-/Termux-Bridge ist eingestellt (15.10.2026). Sie hing am
Cloudflare-Tunnel, und die Tailscale-App für Android kann weder `serve` noch
Funnel. Der Edge-Agent unter Termux (`edge-agent/termux/`, Silent Mode) ist
davon unabhängig.

## Einrichtung

Beide Wege sind identisch aufgebaut (`cp .env.example .env`, Werte eintragen,
`docker compose up -d`) — siehe die jeweiligen Ordner:

```bash
# go2rtc (Default)
cd bridge && cp .env.example .env && docker compose up -d --remove-orphans

# MediaMTX-Alternative (nur LAN/Tailnet)
cd bridge/mediamtx && cp .env.example .env && docker compose up -d --remove-orphans
```

`--remove-orphans` räumt dabei einen alten `stallwache-tunnel`-Container
(cloudflared) mit ab, sofern er aus derselben Compose-Datei stammt. Sonst
hilft `docker rm -f stallwache-tunnel` (siehe „Umstieg von Cloudflare“).

**`NEXT_PUBLIC_BRIDGE_URL` in Vercel leer lassen.** Die Webapp kann go2rtc
nicht direkt abspielen: Es gibt keinen öffentlichen Port, und go2rtc erlaubt
bewusst keine Cross-Origin-Abrufe. Ist die Variable gesetzt, wechselt die
Kachel nach dem ersten Aussetzer des Fernzugriffs für die ganze Sitzung auf
diese tote Adresse. Ohne die Variable versucht sie den Fernzugriff erneut.
Begründung: [`docs/fernzugriff-spezifikation.md`](../docs/fernzugriff-spezifikation.md) §2.

## Fernzugriff (Stallwache/Tapo) über Tailscale Funnel

go2rtc ist nur im LAN bzw. Tailnet erreichbar. Für den Zugriff von jedem
Gerät (mit App-Login) geht das Video über die Webapp:

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
  Stall-Rechner nicht erreichbar, zeigt die Kachel den Verbindungshinweis und
  versucht es erneut.

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

**Prüfen von außen** (Handy über Mobilfunk, Tailscale aus):
`https://<gerät>.<tailnet>.ts.net:8443/api/stream.m3u8` muss **403** liefern.
Dann arbeitet der Funnel, und der Proxy sperrt Anfragen ohne Token. Lädt die
Seite gar nicht, ist der Funnel gestört: In der Tailscale-Verwaltung HTTPS-Zertifikate und
`nodeAttrs` „funnel“ prüfen.

## Umstieg von Cloudflare (ältere Installationen)

```bash
docker stop stallwache-tunnel && docker rm stallwache-tunnel
cd ~/Die_Stallwache && git pull
# CLOUDFLARE_TUNNEL_TOKEN aus bridge/.env löschen
cd bridge && docker compose up -d --remove-orphans
```

Danach den Tunnel im Cloudflare-Zero-Trust-Dashboard löschen, damit sein
Token ungültig wird.
