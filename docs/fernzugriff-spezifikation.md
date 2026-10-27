# Fernzugriff: Tailscale statt Cloudflare

Stand: 15.10.2026, §5.2 am 22.10.2026, §5.3 am 20.10.2026 · Entscheidung des Betreibers: „remove cloudflare, change to
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
   - Einzige Ausnahme von „nur HLS“: `GET /api/ki-kaesten`, Kästen und Kuh-Nummern der letzten Analyse des Edge-Agenten als kleines JSON (keine Bilder). Der Proxy liest es aus einer festen Datei im RAM (nicht über go2rtc), nur mit Token, nur frisch und höchstens 64 KB groß ([`ki-ansicht-spezifikation.md`](./ki-ansicht-spezifikation.md)).
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
2. **Funnel von außen nicht erreichbar (behoben 22.10.2026).** Der Fernzugriff hat von außen nie funktioniert, bis am 21. und 22.10. fünf Ursachen nacheinander behoben waren. Jede verdeckte die nächste:
   1. **Funnel beim Kontrollserver nicht registriert:** Der öffentliche Name existierte nicht (NXDOMAIN, Befund 19.10.), obwohl `tailscale funnel status` „on“ zeigte; das liest nur die lokale Konfiguration. Behoben mit `sudo tailscale funnel reset` und erneutem `fern-einrichten.sh`.
   2. **HTTPS-Zertifikate im Tailnet nicht eingeschaltet:** Das `tailscaled`-Log zeigte bei jedem Funnel-Abruf „TLS handshake error … your Tailscale account does not support getting TLS certs“. `tailscale cert` scheiterte mit 500. Behoben in der Tailscale-Verwaltung unter DNS → HTTPS Certificates, danach zur Kontrolle `cd /tmp && sudo tailscale cert <gerät>.<tailnet>.ts.net && sudo rm -f /tmp/<gerät>.<tailnet>.ts.net.*`. Der Befehl legt Zertifikat und privaten Schlüssel ins aktuelle Verzeichnis, deshalb `/tmp` und danach löschen. Serve holt sich das Zertifikat sonst selbst. Im CT-Log (crt.sh) gab es für das ganze Tailnet bis dahin kein Zertifikat.
   3. **`STALLWACHE_FERN_URL` in Vercel ohne `:8443`:** Die Abrufe kamen auf Port 443 an. Das Log zeigte „handleIngress: got ingress conn for unconfigured "<gerät>…:443"; rejecting“, die App „Verbindung abgebrochen (ECONNRESET)“. Behoben durch die URL mit Port.
   4. **Neuer Schlüssel griff nicht:** `fern-einrichten.sh` startete einen laufenden Proxy nicht neu. Nach `rm /etc/stallwache-fern.env` lieferte der Selbsttest deshalb `403 · 403 · 403`. Im Skript behoben: Der Dienst wird immer neu gestartet.
   5. **Falsche Kamera-IP in `bridge/.env`:** Unter `TAPO_IP` stand ein anderes Gerät, Port 554 zu, TTL 128. go2rtc lieferte deshalb ein leeres Manifest (200, 0 Byte), und der Selbsttest meldete trotzdem `HLS=200`. Behoben durch die richtige IP. Der Selbsttest verlangt jetzt ein Manifest (`#EXTM3U`), prüft HTTPS am Gerät und ob der Name öffentlich auflöst.

   **Nachweis 22.10.2026, 15:41 UTC:**
   - Eingeloggt liefert `GET /api/stallwache/stream` den Status 200.
   - 21 s HLS über die App ergaben 22 Segmente; daraus wurden 373 Bilder (H.264, 640×360) entschlüsselt. Der Kamera-Zeitstempel des letzten Bilds passt zur Abrufzeit.
   - Die Kachel zeigt keinen Platzhalter mehr. Kriterium 6 ist damit erfüllt.
   - Kriterium 5 ist sachlich belegt: Der Abruf über Vercel kommt von außerhalb des Tailnets und läuft durch Funnel und Proxy. Der wörtliche Test über Mobilfunk (403) steht noch aus. Der lokale 403 am Gerät lief vermutlich über MagicDNS direkt an die 100.x-Adresse und belegt nur Zertifikat und Proxy.

   **Nebenbefunde:**
   - Die Warnung „invalid-packet-filter … unlocked nodes; rejecting all packets“ erschien beim Neustart von `tailscaled` nur vorübergehend und war nicht die Ursache. Tailnet Lock ist nicht eingeschaltet.
   - Ein Verbindungsabbruch, gemessen aus einer Claude-Cloud-Sitzung, ist nicht aussagekräftig: Deren Proxy liefert ihn auch für erfundene ts.net-Namen. Aussagekräftig ist von dort nur die DNS-Abfrage (`https://dns.google/resolve?name=<gerät>.<tailnet>.ts.net&type=A`) oder die Fehlermeldung der App (§5.3).

   **Klärung bei einem erneuten Ausfall**, in dieser Reihenfolge:
   1. Die Fehlermeldung der App lesen (§5.3):
      - `ENOTFOUND`: Name bzw. Funnel-Registrierung,
      - `ECONNRESET`: Port in der URL oder Zertifikat,
      - „antwortet mit 403“: Schlüssel,
      - leeres Bild: Kamera.
   2. Am Gerät `tailscale status --json` lesen: `BackendState` muss `Running` sein, `Self.Online` true, `Self.Expired` false. `Self.DNSName` (ohne Punkt am Ende) muss genau dem Host in `STALLWACHE_FERN_URL` entsprechen.
   3. Dann `sudo journalctl -u tailscaled --since '-15 min' | grep -iE 'ingress|TLS handshake'`:
      - „unconfigured …:443“ heißt: Port fehlt in der URL.
      - „does not support getting TLS certs“ heißt: HTTPS-Zertifikate aus.
      - Keine Zeile heißt: Der Abruf erreicht das Gerät nicht. Dann `sudo systemctl restart tailscaled`; Kandidat ist der Tailscale-Fehler tailscale/tailscale#21114.
   4. `fern-einrichten.sh` erneut ausführen. Der Selbsttest prüft Proxy, Kamerabild (Manifest), HTTPS am Gerät und den öffentlichen Namen. Bei leerem Manifest, HTTPS-Fehler (je nach curl-Fehlercode) und fehlendem öffentlichen Namen gibt er einen eigenen Hinweis. `HTTPS=403` belegt nur Zertifikat und Proxy am Gerät, nicht den Weg über das Funnel-Relay.
3. **Diagnose (erledigt 20.10.2026).** `lib/fern.ts` nennt die Ursache eines gescheiterten Abrufs in der Fehlermeldung und im Vercel-Log, z. B. „Stall-Rechner nicht erreichbar – Name nicht auflösbar (ENOTFOUND)“. Unterschieden werden DNS, Zeitüberschreitung, abgelehnte bzw. abgebrochene Verbindung, Netz und TLS. Weitergegeben werden nur feste Texte und Fehlercodes, nie Hostname, IP oder Token. Die Oberfläche wertet weiter nur den Status 502 aus.
4. **Funnel-Kontingente** (Bandbreite, Ports 443/8443/10000) setzt Tailscale. Für einen SD-HLS-Stream mit einem Zuschauer ist das unkritisch.
5. **go2rtc-Login nur wirksam, wenn gesetzt.** Bleiben `GO2RTC_API_USER`/`GO2RTC_API_PASS` leer, ist die API ohne Login (§1.2). Der Bereitschafts-Check kann das von außen nicht sehen. Kriterium 9 prüft es am Gerät.
6. **Status der Vorschau-Kacheln** (erledigt mit #82): Ohne Bridge meldet eine ungeprüfte Vorschau „Ungeprüft“ statt „Lädt“ oder eines übernommenen „Online“, und der Kopf zeigt kein „0 von 3 Kameras online“ mehr, solange die Kameras senden. Regel: [`vorschau-status-spezifikation.md`](./vorschau-status-spezifikation.md).
