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
2. **go2rtc ist nie öffentlich und hat einen Login.** Seine API kann Befehle auf dem Stall-Rechner ausführen. Sie bleibt im LAN bzw. Tailnet und bekommt keine CORS-Freigabe (`api.origin`).
   - Fehlendes CORS verhindert nur, dass eine fremde Webseite Antworten **liest**. „Einfache“ POST-Anfragen sendet der Browser trotzdem. Ohne Login könnte also jede Webseite, die ein Gerät im Stall-WLAN oder Tailnet öffnet, go2rtc beenden (`POST /api/exit`) oder das Kamerabild an einen fremden Server weiterleiten (`POST /api/streams?src=…&dst=…`). Belegt im go2rtc-Quelltext, `internal/api/api.go` bzw. `internal/streams/api.go`, und verletzt „Video verlässt den Hof nie“.
   - Deshalb gilt Login-Pflicht über `GO2RTC_API_USER`/`GO2RTC_API_PASS` in `bridge/.env` (Entscheidung des Betreibers, 15.10.2026). Anfragen vom Stall-Rechner selbst (`fern-proxy.py` über 127.0.0.1) brauchen keinen Login, weil `local_auth` aus ist.
   - **Nie** `tailscale serve`/`funnel` direkt auf Port 1984 setzen: Solche Anfragen kämen als 127.0.0.1 an und umgingen den Login.
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
  - Ohne Einzelbild kann eine Vorschau-Kachel (Datensparen) ihr Bild nicht prüfen. Sie meldet „Ungeprüft“ statt „Lädt“ oder eines übernommenen „Online“ und zählt im Kopf weder als online noch als offline. Ein sparsamer Status-Ping erkennt echte Störungen. Regel, Takte und Abnahme: [`vorschau-status-spezifikation.md`](./vorschau-status-spezifikation.md).
- **Android-App (eigenes Repo):** Sie spielt die Bridge nativ ab, ohne CORS, bekommt das Bild der Stallwache also nur im Tailnet. Mit go2rtc-Login braucht sie dafür die Zugangsdaten; ob sie das kann, ist nicht geprüft. Einen Passwort-Login für die Webapp hat sie nicht. Bei aktivem `STALLBLICK_PASSWORT` (Voraussetzung für den Fernzugriff) antworten ihr die Webapp-Endpunkte mit 401.
- **Wartung von go2rtc** (WebUI, Stream-Test) läuft nur im LAN/Tailnet und mit Login: `http://<ip>:1984`.
- **Edge-Agent:** Sein Snapshot-Fallback ruft go2rtc über die LAN-Adresse ab und braucht den Login in `stream.fallback_snapshot_url` (`http://BENUTZER:PASSWORT@<ip>:1984/…`). Der Agent schickt ihn als Basic-Auth und schreibt ihn nie ins Log. Der RTSP-Restream (:8554) ist vom API-Login nicht betroffen.
- **MediaMTX-Variante (`bridge/mediamtx/`):** `fern-proxy.py` kennt nur go2rtc-Pfade. Ohne Cloudflare hat MediaMTX daher **keinen** Fernzugriff, sondern nur Zugriff im LAN bzw. Tailnet. Das ist nicht am Gerät erprobt. Der Standard bleibt go2rtc. Offen: `hlsAllowOrigin: "*"` erlaubt jeder Webseite im LAN/Tailnet, das Bild zu lesen. Wer MediaMTX einsetzt, muss das vorher einschränken. Auf dem Stall-Rechner läuft MediaMTX nicht.

## 3. Konfiguration

**Stall-Rechner (einmalig, Betreiber):**

```bash
cd ~/Die_Stallwache/bridge && bash fern-einrichten.sh   # Funnel :8443 nur für den Proxy
```

Voraussetzung: In der Tailscale-Verwaltung sind für das Gerät **HTTPS-Zertifikate** (DNS) und **Funnel** (Access controls → `nodeAttrs` `funnel`) erlaubt.

**go2rtc-Login (Stall-Rechner, Betreiber):** In `bridge/.env` beide Werte setzen und go2rtc neu starten:

```bash
GO2RTC_API_USER=stallwache
GO2RTC_API_PASS=$(openssl rand -hex 16)   # nur Buchstaben/Ziffern
cd ~/Die_Stallwache/bridge && docker compose up -d   # übernimmt die neuen Werte
```

Bleiben beide leer, läuft go2rtc ohne Login wie bisher (damit ein `git pull` die Bridge nicht lahmlegt). Danach im Edge-Agenten `stream.fallback_snapshot_url` um `BENUTZER:PASSWORT@` ergänzen und den Agenten neu starten. `edge-agent/setup.sh` fragt den Login bei Neueinrichtung ab.

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
7. Bei abgeschaltetem Funnel zeigt die Kachel den Verbindungs-Hinweis und es gibt keine Seitenfehler. Wird der Funnel wieder eingeschaltet, kommt das Bild ohne Neuladen zurück (mit leerer `NEXT_PUBLIC_BRIDGE_URL`). Das gilt auch für Safari/iOS (natives HLS): Ein Abbruch löst den erneuten Versuch aus.
8. Mit leerer `NEXT_PUBLIC_BRIDGE_URL` und Datensparen an zeigt der Kopf kein „0 von 3 Kameras online“, solange die Kameras senden, und keine Kachel meldet ungeprüft „Online“ ([`vorschau-status-spezifikation.md`](./vorschau-status-spezifikation.md) §6).
9. Mit gesetztem go2rtc-Login beantwortet go2rtc Anfragen aus dem LAN ohne Login mit **401**: `curl -s -o /dev/null -w '%{http_code}' http://<ip>:1984/api/streams`. Mit `-u BENUTZER:PASSWORT` kommt **200**. Der Fernzugriff (Kriterium 5/6) funktioniert unverändert.
10. Der Edge-Agent bekommt bei gestörtem RTSP über den Snapshot-Fallback weiter Bilder. Im Log erscheint das Passwort nicht.

## 5. Risiken

1. **Ein einziger Weg.** Fällt der Funnel aus, gibt es von außen kein Livebild der Stallwache. Das wird bewusst in Kauf genommen: Ein zweiter Weg wäre eine zweite Angriffsfläche. Die Alarmkette hängt nicht daran.
2. **Funnel von außen nicht erreichbar (offen, Befund 19.10.2026).**
   - **Befund:** Der öffentliche Name `stallwache-lela.<tailnet>.ts.net` existiert im DNS nicht (NXDOMAIN bei Google und Cloudflare). Die Webapp scheitert deshalb sofort (≈ 0,2 s, kein Timeout) mit „Stall-Rechner nicht erreichbar“. `tailscale funnel status` meldet trotzdem „on“, weil es nur die lokale Konfiguration liest. Den öffentlichen Eintrag legt Tailscale erst an, wenn sein Kontrollserver das Gerät als aktiven Funnel führt.
   - **Nie nachweislich erreichbar:** Bei der Einrichtung am 14.10.2026 um 05:57 (MESZ) meldete `fern-einrichten.sh` den Funnel als eingerichtet, der Selbsttest schlug aber fehl (`HLS=502`, go2rtc lief nicht). Kriterium 5 ist nie erfüllt worden. „05:57“ ist der Einrichtungszeitpunkt, kein Ausfallzeitpunkt.
   - **Messartefakt:** Der frühere Befund „Reset beim TLS-Aufbau“ stammt aus einer Claude-Cloud-Sitzung. Deren ausgehender Proxy setzt jede gescheiterte Verbindung beim TLS-Aufbau zurück, auch für einen frei erfundenen Namen (nachgestellt am 19.10.2026). Von dort zählt nur die DNS-Abfrage, z. B. `https://dns.google/resolve?name=<gerät>.<tailnet>.ts.net&type=A`. Der Test auf 403 läuft über Mobilfunk ohne Tailscale.
   - **Klärung am Gerät, in dieser Reihenfolge:**
     1. `tailscale status --json` lesen: `BackendState` muss `Running` sein, `Self.Online` true, `Self.Expired` false, und `Self.CapMap` muss `funnel` und `https` enthalten. Sonst neu anmelden bzw. die Freigaben in der Tailscale-Verwaltung nachtragen.
     2. Ist alles gesund: `sudo systemctl restart tailscaled`. Kandidat ist der offene Tailscale-Fehler tailscale/tailscale#21114 (Funnel-Registrierung geht nach einem Reconnect zum Kontrollserver verloren, gemeldet für 1.102.3–1.104.1).
     3. Hilft das nicht: `sudo tailscale funnel reset`, danach `fern-einrichten.sh` erneut ausführen. Der Selbsttest muss `HLS=200` zeigen, go2rtc muss also laufen.
   - **Nachweis:** Der Name löst öffentlich auf, und Kriterium 5 liefert 403.
3. **Diagnose (erledigt 20.10.2026).** `lib/fern.ts` nennt die Ursache eines gescheiterten Abrufs in der Fehlermeldung und im Vercel-Log, z. B. „Stall-Rechner nicht erreichbar – Name nicht auflösbar (ENOTFOUND)“. Unterschieden werden DNS, Zeitüberschreitung, abgelehnte bzw. abgebrochene Verbindung, Netz und TLS. Weitergegeben werden nur feste Texte und Fehlercodes, nie Hostname, IP oder Token. Die Oberfläche wertet weiter nur den Status 502 aus.
4. **Funnel-Kontingente** (Bandbreite, Ports 443/8443/10000) setzt Tailscale. Für einen SD-HLS-Stream mit einem Zuschauer ist das unkritisch.
5. **go2rtc-Login nur wirksam, wenn gesetzt.** Bleiben `GO2RTC_API_USER`/`GO2RTC_API_PASS` leer, ist die API ohne Login (§1.2). Der Bereitschafts-Check kann das von außen nicht sehen. Kriterium 9 prüft es am Gerät.
6. **Status der Vorschau-Kacheln** (erledigt mit #82): Ohne Bridge meldet eine ungeprüfte Vorschau „Ungeprüft“ statt „Lädt“ oder eines übernommenen „Online“, und der Kopf zeigt kein „0 von 3 Kameras online“ mehr, solange die Kameras senden. Regel: [`vorschau-status-spezifikation.md`](./vorschau-status-spezifikation.md).
