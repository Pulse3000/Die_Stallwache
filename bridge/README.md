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

## go2rtc-Login (Pflicht)

go2rtc nimmt ohne Login aus dem ganzen Stall-WLAN Befehle an, auch „einfache“
POST-Anfragen einer beliebigen Webseite, die ein Gerät im WLAN öffnet. Damit
ließe sich go2rtc beenden oder das Bild an einen fremden Server weiterleiten.
Fehlendes CORS verhindert nur das Lesen der Antwort. Deshalb in `bridge/.env`:

```bash
GO2RTC_API_USER=stallwache
GO2RTC_API_PASS=<openssl rand -hex 16>   # nur Buchstaben/Ziffern
```

Danach `docker compose up -d`. Der Fernzugriff (`fern-proxy.py`) spricht go2rtc
über 127.0.0.1 an und braucht keinen Login. Der Edge-Agent braucht ihn für
seinen Snapshot-Fallback: `stream.fallback_snapshot_url =
http://BENUTZER:PASSWORT@<ip>:1984/api/frame.jpeg?src=stallwache`. Er schickt
die Daten als Basic-Auth und schreibt sie nie ins Log. **Nie** `tailscale
serve`/`funnel` direkt auf Port 1984 setzen: Das käme als 127.0.0.1 an und
umginge den Login. Begründung: [`docs/fernzugriff-spezifikation.md`](../docs/fernzugriff-spezifikation.md) §1.2.

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
8443 nur für den Proxy und gibt drei Werte für Vercel aus
(`STALLWACHE_FERN_URL` **mit `:8443`**, `STALLWACHE_FERN_TOKEN`, `NEXT_PUBLIC_STALLWACHE_FERN=1`).
Der Selbsttest prüft:
- ohne Schlüssel 403,
- go2rtc-API 404,
- ein HLS-Manifest von der Kamera (`HLS=200-leer` heißt: `TAPO_IP` oder Kamerakonto in `.env` stimmt nicht),
- HTTPS über den Tailscale-Namen (`HTTPS=000` heißt: HTTPS-Zertifikate in der Tailscale-Verwaltung einschalten).
Danach in Vercel eintragen und neu deployen. Voraussetzung: HTTPS und Funnel
sind in der Tailscale-Verwaltung für das Gerät erlaubt.

**Abschalten:** `NEXT_PUBLIC_STALLWACHE_FERN` und die beiden `STALLWACHE_FERN_*`
in Vercel entfernen (neu deployen) und `sudo tailscale funnel --https=8443 off`.

**Prüfen von außen** (Handy über Mobilfunk, Tailscale aus):
`https://<gerät>.<tailnet>.ts.net:8443/api/stream.m3u8` muss **403** liefern.
Dann arbeitet der Funnel, und der Proxy sperrt Anfragen ohne Token. Lädt die
Seite gar nicht, ist der Funnel gestört. Dann prüfen:
- `tailscale status` (Gerät verbunden, Key nicht abgelaufen),
- in der Tailscale-Verwaltung HTTPS-Zertifikate und `nodeAttrs` „funnel“,
- ob der Name öffentlich auflöst (`nslookup <gerät>.<tailnet>.ts.net 1.1.1.1`).

`tailscale funnel status` allein reicht nicht: Es zeigt nur die lokale
Einstellung. Reihenfolge und Hintergrund: `docs/fernzugriff-spezifikation.md` §5.2.

## Umstieg von Cloudflare (ältere Installationen)

```bash
docker stop stallwache-tunnel && docker rm stallwache-tunnel
cd ~/Die_Stallwache && git pull
# CLOUDFLARE_TUNNEL_TOKEN aus bridge/.env (bzw. bridge/mediamtx/.env) löschen
cd bridge && docker compose up -d --remove-orphans   # MediaMTX: cd bridge/mediamtx
```

Danach sind noch drei Schritte nötig:
- im Cloudflare-Zero-Trust-Dashboard den Tunnel löschen (der Token wird damit ungültig);
- den DNS-Eintrag des früheren Public Hostname entfernen;
- in Vercel `NEXT_PUBLIC_BRIDGE_URL` leeren und neu deployen.
