# Fernzugriff: Tailscale statt Cloudflare

Stand: 15.10.2026 · Entscheidung des Betreibers: „remove cloudflare, change to
tailscale". Das Dokument legt fest, wie das Livebild der Stallwache von
außerhalb des Stall-LANs erreichbar ist. Die Tuya-Kameras (Futterwache,
Abkalbebox, Weidewache) laufen über die Tuya-Cloud und sind davon nicht
berührt.

## 1. Grundsatz

1. **Ein einziger öffentlicher Weg ins Stall-LAN:**

   ```
   Handy ──Login──▶ Webapp (Vercel) ──Token──▶ Tailscale Funnel :8443 ──▶ fern-proxy.py ──▶ go2rtc ──▶ Tapo
   ```

   - `bridge/fern-proxy.py` ist das Einzige, was öffentlich erreichbar ist.
   - Er lässt nur das HLS der Stallwache durch (SD-Stream) und verlangt den Header `x-stallwache-token`. Alles andere beantwortet er mit 403 oder 404.
   - Die Webapp reicht das Bild nur hinter dem App-Login weiter (`lib/fern.ts`).
2. **go2rtc ist nie öffentlich.** Seine API kann Befehle auf dem Stall-Rechner ausführen. Sie bleibt im LAN bzw. Tailnet und bekommt keine CORS-Freigabe (`api.origin`). Mit einer solchen Freigabe könnte jede Webseite, die ein Gerät im Tailnet öffnet, diese API ansprechen.
3. **Kein Cloudflare-Tunnel mehr.** Er wird aus Compose-Dateien, Vorlagen und Anleitungen entfernt. Gründe:
   - Er war ein **zweiter öffentlicher Zugang** zu go2rtc ohne Token-Schutz. Laut Anleitung zeigte der Public Hostname auf `http://localhost:1984`, also auf die komplette go2rtc-API.
   - Seit dem 14.10.2026 lief er auf dem Stall-Rechner in einer Neustart-Schleife (`Restarting (255)`), hat also nichts geleistet.
   - Zwei Zugangswege bedeuten doppelte Wartung und doppelte Angriffsfläche.
4. **Der Cloud-Transcoder (`cloud-transcoder/`) ist entfernt** (Entscheidung des Betreibers, Abnahme nach dem Merge von #79). Er stellte go2rtc auf einem VPS öffentlich ins Internet, mit der kompletten API hinter Caddy und nur optionaler Basic-Auth. Das widerspricht Punkt 2. Von der Webapp aus funktionierte er ohnehin nur mit einer CORS-Freigabe.
5. **Die Termux-Bridge (`bridge/termux/`) ist eingestellt.** Sie hing vollständig am Cloudflare-Tunnel. Die Tailscale-App für Android kann weder `serve` noch Funnel, ein Ersatzweg ohne Cloudflare existiert also nicht (Entscheidung des Betreibers). Der Edge-Agent unter Termux (`edge-agent/termux/`, Silent Mode) ist davon unabhängig und bleibt.

## 2. Grenzen

- **Ohne Funnel kein Livebild der Stallwache von außen.** Die Alarme des Edge-Agenten (Telegram, App-Meldungen) gehen direkt ins Internet und hängen nicht am Funnel.
- **Direktzugriff der Webapp auf go2rtc (`NEXT_PUBLIC_BRIDGE_URL`) funktioniert nicht und wird nicht mehr empfohlen.**
  - Es gibt keinen öffentlichen Port, und go2rtc erlaubt keine Cross-Origin-Abrufe. Damit scheitern WebRTC und hls.js aus `https://<app>.vercel.app` auch im Tailnet.
  - Ist die Variable trotzdem gesetzt, wechselt die Kachel nach dem ersten Fehlschlag des Stream-Endpunkts auf diese tote Bridge und bleibt dort (`components/CameraStream.tsx`, `startTuya`). Das gilt auch für die Tuya-Kameras. Zurückgesetzt wird erst, wenn die Kachel neu aufgebaut wird (Neuladen, Rollenwechsel, Ein-/Ausblenden).
  - Ohne die Variable versucht sie den Fernzugriff erneut (`scheduleReconnect`).
  - **Folge:** `NEXT_PUBLIC_BRIDGE_URL` in Vercel leer lassen. Dadurch fallen die go2rtc-Vorschaubilder weg, die ohnehin nur im Tailnet luden. Der Snapshot-Knopf meldet „Snapshot nicht verfügbar – nur mit Bridge-Direktzugriff“.
- **Android-App (eigenes Repo):** Sie spielt die Bridge nativ ab, ohne CORS, bekommt das Bild der Stallwache also nur im Tailnet. Einen Passwort-Login hat sie nicht. Bei aktivem `STALLBLICK_PASSWORT` (Voraussetzung für den Fernzugriff) antworten ihr die Webapp-Endpunkte mit 401.
- **Wartung von go2rtc** (WebUI, Stream-Test) läuft nur im Tailnet: `http://<tailnet-IP>:1984` von einem Gerät mit aktiver Tailscale-App.
- **MediaMTX-Variante (`bridge/mediamtx/`):** `fern-proxy.py` kennt nur go2rtc-Pfade. Ohne Cloudflare hat MediaMTX daher **keinen** Fernzugriff, sondern nur Zugriff im LAN bzw. Tailnet. Das ist nicht am Gerät erprobt. Der Standard bleibt go2rtc.

## 3. Konfiguration

**Stall-Rechner (einmalig, Betreiber):**

```bash
cd ~/Die_Stallwache/bridge && bash fern-einrichten.sh   # Funnel :8443 nur für den Proxy
```

Voraussetzung: In der Tailscale-Verwaltung sind für das Gerät **HTTPS-Zertifikate** (DNS) und **Funnel** (Access controls → `nodeAttrs` `funnel`) erlaubt.

**Vercel (Production, Betreiber):**

| Variable | Wert |
| --- | --- |
| `STALLWACHE_FERN_URL` | `https://<gerät>.<tailnet>.ts.net:8443` |
| `STALLWACHE_FERN_TOKEN` | Ausgabe von `fern-einrichten.sh` (geheim) |
| `NEXT_PUBLIC_STALLWACHE_FERN` | `1` |
| `NEXT_PUBLIC_BRIDGE_URL` | **leer / entfernen** (siehe §2) |

**Umstieg von Cloudflare (Stall-Rechner):**

```bash
docker stop stallwache-tunnel && docker rm stallwache-tunnel
cd ~/Die_Stallwache && git pull          # Compose-Datei ohne cloudflared
# CLOUDFLARE_TUNNEL_TOKEN aus bridge/.env (bzw. bridge/mediamtx/.env) löschen
cd bridge && docker compose up -d --remove-orphans   # MediaMTX: cd bridge/mediamtx
```

Danach sind noch drei Schritte nötig:
- im Cloudflare-Zero-Trust-Dashboard den Tunnel löschen (der Token wird damit ungültig);
- den DNS-Eintrag des früheren Public Hostname entfernen;
- in Vercel `NEXT_PUBLIC_BRIDGE_URL` leeren und neu deployen.

## 4. Abnahmekriterien

Automatisiert / im Repo:

1. In `bridge/docker-compose.yml` und `bridge/mediamtx/docker-compose.yml` gibt es keinen `cloudflared`-Dienst mehr. Beide Dateien sind gültiges YAML.
2. Im Repo steht „Cloudflare“ nur noch in dieser Entscheidung, in der Roadmap und in Rückbau-Hinweisen. `bridge/termux/` und `cloud-transcoder/` existieren nicht mehr. Kein UI-Text und keine Anleitung empfiehlt mehr, `NEXT_PUBLIC_BRIDGE_URL` zu setzen.
3. `npm test`, `tsc --noEmit`, `npm run lint` und `npm run build` sind grün. Im Code ändern sich nur Kommentare (#79) und zwei Hinweistexte (#81: Kachel ohne Bildweg, Snapshot-Meldung).

Am realen Gerät (Beweispflicht, Betreiber + Orchestrator):

4. `docker ps` zeigt keinen `stallwache-tunnel`. `docker compose up -d --remove-orphans` startet nur go2rtc.
5. Über Mobilfunk ohne Tailscale liefert `https://<gerät>.<tailnet>.ts.net:8443/api/stream.m3u8` die Antwort **403**. Der Funnel arbeitet also, und der Proxy sperrt Anfragen ohne Token.
6. Eingeloggt liefert `GET /api/stallwache/stream` den Status `200 {"url":…,"typ":"hls"}`, und die Kachel zeigt das Livebild.
7. Bei abgeschaltetem Funnel zeigt die Kachel den Verbindungs-Hinweis und es gibt keine Seitenfehler. Wird der Funnel wieder eingeschaltet, kommt das Bild ohne Neuladen zurück (mit leerer `NEXT_PUBLIC_BRIDGE_URL`).

## 5. Risiken

1. **Ein einziger Weg.** Fällt der Funnel aus, gibt es von außen kein Livebild der Stallwache. Das wird bewusst in Kauf genommen: Ein zweiter Weg wäre eine zweite Angriffsfläche. Die Alarmkette hängt nicht daran.
2. **Funnel ist aktuell gestört (offen).** Seit dem 14.10.2026, 05:57, erreicht keine Anfrage von außen mehr den Proxy. Ein Test von außen bricht beim TLS-Aufbau ab („connection reset“), obwohl `tailscale funnel status` den Funnel als eingeschaltet meldet. Die Ursache wird am Gerät geklärt: Freigaben in der Tailscale-Verwaltung, `tailscaled`-Log.
3. **Diagnose.** `lib/fern.ts` verwirft die Fehlerursache (DNS, TLS, Reset). Man sieht nur „Stall-Rechner nicht erreichbar“. Eine bessere Meldung ist ein eigener, kleiner Folgeschritt.
4. **Funnel-Kontingente** (Bandbreite, Ports 443/8443/10000) setzt Tailscale. Für einen SD-HLS-Stream mit einem Zuschauer ist das unkritisch.
