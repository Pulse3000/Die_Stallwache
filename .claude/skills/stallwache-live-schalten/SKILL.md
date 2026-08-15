---
name: stallwache-live-schalten
description: Go-Live der Stallwache-Hauptkamera — entweder über die Tuya-Cloud (ohne Bridge, Device ID + NEXT_PUBLIC_STALLWACHE_TUYA=1) oder über die Bridge (Cloudflare-Tunnel-Hostname). Livebild und KI-Wache-Kette end-to-end verifizieren. Nutzen bei "Stallwache live schalten", "Device ID ist ...", "Tunnel läuft", "Hostname ist ...", "Bridge ist online" oder wenn die Stallwache-Kachel dauerhaft den Platzhalter zeigt.
---

# Stallwache live schalten

Der wartende Meilenstein des Projekts: Sobald die Hauptkamera im
Abkalbebereich ein Bild liefert, schaltet diese Prozedur sie in der Webapp
live — und damit die gesamte Modell-Kette frei (Silent Mode → Skill
`modell-training`).

## Welcher Weg?

Es gibt **zwei** Wege ans Livebild. Der Betreiber sagt, welcher vorliegt:

| | **A — Tuya-Cloud** (kein Gerät im Stall) | **B — Bridge** (go2rtc/MediaMTX im Stall-LAN) |
| --- | --- | --- |
| Voraussetzung | Kamera hängt im Tuya-Projekt, Device ID liegt vor | Cloudflare-Tunnel-Hostname liegt vor |
| Zu setzen | `TUYA_DEVICE_ID_STALLWACHE` **und** `NEXT_PUBLIC_STALLWACHE_TUYA=1` | `NEXT_PUBLIC_BRIDGE_URL` |
| Hardware | keine | Raspberry Pi / Mini-PC / Stall-Handy |

Beides zusammen ist erlaubt und die robusteste Variante: Ist Tuya aktiv und
zusätzlich eine Bridge gesetzt, dient die Bridge als Fallback. Die Stallwache
ist bei Tuya bewusst **opt-in** (anders als die Zweitkameras), damit
bestehende Bridge-Höfe ihr Verhalten unverändert behalten — siehe
`lib/config.ts`.

---

## Weg A — über die Tuya-Cloud

### A1 — Voraussetzungen (vom Betreiber)

1. Kamera im selben Tuya-Cloud-Projekt wie die Zweitkameras verknüpft
   (`iot.tuya.com` → Cloud → Projekt → *Link Tuya App Account*).
2. API **„IoT Video Live Stream"** im Projekt abonniert.
3. **Device ID** der Stallwache (Projekt → Devices).

Access ID und Secret gelten projektweit — laufen die Zweitkameras bereits,
fehlt nur die Device ID. Fehlercodes bei Problemen: `1106` (App-Konto nicht
verknüpft), `28841105` (API nicht abonniert); Eingrenzung: Skill
`tuya-diagnose`.

### A2 — Env-Variablen setzen

```bash
vercel env add TUYA_DEVICE_ID_STALLWACHE production    # serverseitig, nie NEXT_PUBLIC
vercel env add NEXT_PUBLIC_STALLWACHE_TUYA production  # Wert: 1
```

Secret-Store-Schreibzugriff aus der Session ist gesperrt — der **Betreiber**
trägt die Werte ein (Vercel → Settings → Environment Variables → Production).
Fehlt die Device ID, antwortet `/api/stallwache/stream` bewusst mit **503**
und die Kachel bleibt beim Wartehinweis.

`NEXT_PUBLIC_*` wird beim **Build** eingebacken → Redeploy ist Pflicht.

---

## Weg B — über die Bridge

### B1 — Bridge von außen prüfen (vor jeder Änderung)

```bash
# go2rtc-API erreichbar? Stream 'stallwache' registriert?
curl -s https://HOSTNAME/api/streams | head -c 400
# Snapshot liefert ein JPEG? (go2rtc-Snapshot-API)
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" \
  "https://HOSTNAME/api/frame.jpeg?src=stallwache"
```

Erwartet: JSON mit `stallwache`-Eintrag bzw. `200 image/jpeg`. Wenn nicht →
Fehlersuche in `bridge/termux/README.md` (Logs: `logs/go2rtc.log`,
`logs/cloudflared.log`), NICHT weitermachen.

### B2 — Env-Variable setzen

```bash
vercel env add NEXT_PUBLIC_BRIDGE_URL production   # Wert: https://HOSTNAME
```

- `NEXT_PUBLIC_BRIDGE_TYPE` nur bei MediaMTX auf `mediamtx` setzen
  (Default go2rtc stimmt für die Termux-Bridge).
- Alias `NEXT_PUBLIC_GO2RTC_URL` ist Alt-Name — nicht zusätzlich setzen.

---

## Schritt 3 — Redeploy auslösen (beide Wege)

Leerer Commit auf `main` (Git-Integration deployt automatisch) oder
`vercel --prod`. Warten bis der Deploy „Ready" ist.

## Schritt 4 — End-to-End verifizieren

1. **Login-Gate:** `/` antwortet 307 → `/login` (Schutz weiter aktiv).
2. **Weg A zusätzlich:** eingeloggt `GET /api/stallwache/stream` →
   `{"url":"…","typ":"hls"}`. Bei Fehler steht die Tuya-Meldung im Feld
   `fehler` (Codes siehe A1).
3. **Livebild:** eingeloggt auf `/` — Stallwache-Kachel zeigt Video statt
   Platzhalter. Headless-Prüfung: Playwright, `video`-Element mit
   `readyState >= 2` auf der Hauptkachel.
4. **Rollentausch:** Kachel-Klick tauscht Haupt-/Vorschaurolle ohne
   Remount-Ruckler.
5. **Kette komplett:** Betreiber startet den Edge-Agent
   (`bash edge-agent/setup.sh`) → Startmeldung „Silent Mode" erscheint unter
   `/wache` („Edge-Agent … zuletzt HH:MM"). Bei Weg A dort `stream.url` leer
   lassen und `stream.quelle_api: /api/stallwache/stream` setzen.

## Schritt 5 — Anschlussarbeiten

- `docs/roadmap.md`: Meilenstein-Abschnitt aktualisieren.
- Betreiber informieren: Ab jetzt sammelt der Silent Mode Trainingsbilder —
  in 1–2 Wochen weiter mit Skill `modell-training`.
- Skill `bytetrack-tuning` vormerken (nach dem ersten `best.pt`).

## Rollback

Kachel schwarz/Fehler nach Go-Live: die gesetzte Variable in Vercel wieder
entfernen (`NEXT_PUBLIC_STALLWACHE_TUYA` bzw. `NEXT_PUBLIC_BRIDGE_URL`) +
Redeploy → Webapp zeigt wieder den sauberen Wartezustand (Fehlerzustand ist
schlimmer als Wartezustand). Dann Schritt A1 bzw. B1 wiederholen.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Device ID bzw. Tunnel/Hostname bereitstellen, Env-Vars eintragen | Betreiber |
| Prüfung, Redeploy, Verifikation, Nacharbeiten | Orchestrator (dieser Skill) |
| Tuya-Fehlercodes eingrenzen | Skill `tuya-diagnose` |
| Smoke der Ereignis-Kette | Skill `ki-wache-smoketest` |
