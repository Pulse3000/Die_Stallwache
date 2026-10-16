---
name: stallwache-live-schalten
description: Go-Live der Stallwache-Hauptkamera — entweder über die Tuya-Cloud (ohne Bridge, Device ID + NEXT_PUBLIC_STALLWACHE_TUYA=1) oder über den Fernzugriff zum Stall-Rechner (go2rtc + fern-proxy.py hinter Tailscale Funnel, NEXT_PUBLIC_STALLWACHE_FERN=1). Livebild und KI-Wache-Kette end-to-end verifizieren. Nutzen bei "Stallwache live schalten", "Device ID ist ...", "Funnel läuft", "Fernzugriff ist eingerichtet", "Bridge ist online" oder wenn die Stallwache-Kachel dauerhaft den Platzhalter zeigt.
---

# Stallwache live schalten

Der wartende Meilenstein des Projekts: Sobald die Hauptkamera im
Abkalbebereich ein Bild liefert, schaltet diese Prozedur sie in der Webapp
live — und damit die gesamte Modell-Kette frei (Silent Mode → Skill
`modell-training`).

## Welcher Weg?

Es gibt **zwei** Wege ans Livebild. Der Betreiber sagt, welcher vorliegt:

| | **A — Tuya-Cloud** (kein Gerät im Stall) | **B — Fernzugriff** (go2rtc im Stall-LAN, Tailscale Funnel) |
| --- | --- | --- |
| Voraussetzung | Kamera hängt im Tuya-Projekt, Device ID liegt vor | Stall-Rechner mit go2rtc, `bash bridge/fern-einrichten.sh` gelaufen |
| Zu setzen | `TUYA_DEVICE_ID_STALLWACHE` **und** `NEXT_PUBLIC_STALLWACHE_TUYA=1` | `STALLWACHE_FERN_URL`, `STALLWACHE_FERN_TOKEN`, `NEXT_PUBLIC_STALLWACHE_FERN=1` |
| Hardware | keine | Mini-PC / Raspberry Pi im Stall-LAN |

`NEXT_PUBLIC_BRIDGE_URL` bleibt in beiden Wegen **leer**. go2rtc ist nie
öffentlich und erlaubt keine Cross-Origin-Abrufe. Eine gesetzte Adresse wäre
eine tote Ausweichroute, auf die die Kachel nach dem ersten Aussetzer
bis zum Neuaufbau der Kachel wechselt (`docs/fernzugriff-spezifikation.md` §2). Ein
Cloudflare-Tunnel ist nicht mehr vorgesehen. Die Stallwache ist bei Tuya
bewusst **opt-in** (anders als die Zweitkameras), siehe `lib/config.ts`.

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

## Weg B — über den Fernzugriff (Tailscale Funnel)

### B1 — Funnel von außen prüfen (vor jeder Änderung)

```bash
# Ohne Token muss der Proxy sperren: 403 = Funnel steht, Proxy antwortet.
curl -s -o /dev/null -w "%{http_code}\n" "https://GERAET.TAILNET.ts.net:8443/api/stream.m3u8"
```

Erwartet: `403`. Bricht die Verbindung ab (`000`, Reset beim TLS-Aufbau),
ist der Funnel gestört. Dann **nicht weitermachen**. Der Betreiber prüft am
Stall-Rechner `tailscale funnel status`, `systemctl status stallwache-fern`,
`docker ps` (go2rtc) und in der Tailscale-Verwaltung HTTPS-Zertifikate sowie
`nodeAttrs` „funnel“. Den Token-Test mit `200` macht nur der Betreiber
(`fern-einrichten.sh` prüft ihn selbst), der Token gehört nicht in die Session.

### B2 — Env-Variablen setzen (Betreiber)

```bash
vercel env add STALLWACHE_FERN_URL production           # https://GERAET.TAILNET.ts.net:8443
vercel env add STALLWACHE_FERN_TOKEN production         # Ausgabe von fern-einrichten.sh (geheim)
vercel env add NEXT_PUBLIC_STALLWACHE_FERN production   # Wert: 1
```

- `NEXT_PUBLIC_BRIDGE_URL` (und Alias `NEXT_PUBLIC_GO2RTC_URL`) **nicht** setzen.
- Ohne aktiven App-Login (`STALLBLICK_PASSWORT`) verweigert der Fernzugriff
  den Dienst (fail-closed).

---

## Schritt 3 — Redeploy auslösen (beide Wege)

Leerer Commit auf `main` (Git-Integration deployt automatisch) oder
`vercel --prod`. Warten bis der Deploy „Ready" ist.

## Schritt 4 — End-to-End verifizieren

1. **Login-Gate:** `/` antwortet 307 → `/login` (Schutz weiter aktiv).
2. **Beide Wege:** eingeloggt `GET /api/stallwache/stream` →
   `{"url":"…","typ":"hls"}`. Bei Fehler steht die Ursache im Feld `fehler`
   (Weg A: Tuya-Codes siehe A1; Weg B: „Stall-Rechner nicht erreichbar“ bzw.
   „antwortet mit <Code>“ → zurück zu B1).
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
entfernen (`NEXT_PUBLIC_STALLWACHE_TUYA` bzw. `NEXT_PUBLIC_STALLWACHE_FERN`) +
Redeploy → Webapp zeigt wieder den sauberen Wartezustand (Fehlerzustand ist
schlimmer als Wartezustand). Dann Schritt A1 bzw. B1 wiederholen.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Device ID bzw. Funnel/Fernzugriff bereitstellen, Env-Vars eintragen | Betreiber |
| Prüfung, Redeploy, Verifikation, Nacharbeiten | Orchestrator (dieser Skill) |
| Tuya-Fehlercodes eingrenzen | Skill `tuya-diagnose` |
| Smoke der Ereignis-Kette | Skill `ki-wache-smoketest` |
