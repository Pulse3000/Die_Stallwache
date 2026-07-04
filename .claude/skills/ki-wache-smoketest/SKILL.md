---
name: ki-wache-smoketest
description: End-to-End-Test der KI-Wache (Ingest-API-Auth-Kette + Dashboard-Anzeige). Nutzen nach Änderungen an /api/events, lib/events.ts, WacheDashboard oder dem Edge-Agent-Reporting.
---

# KI-Wache: End-to-End-Smoke-Test

Prüft die komplette Alarmkette: Ingest-API-Sicherheit → Ereignis-Speicherung →
Dashboard-Anzeige. Referenzverhalten, das nie brechen darf.

## Auth-Kette (Soll-Verhalten von POST /api/events)

| Situation | Erwartet |
| --- | --- |
| `EDGE_INGEST_TOKEN` nicht gesetzt | **503** („Ingest nicht konfiguriert") |
| Falscher/fehlender `x-ingest-token`-Header | **401** |
| Gültiger Token, gültiger Body | **201** + `{ok: true, id}` |
| Gültiger Token, unbekannter `typ` oder fehlende `nachricht` | **400** |

## Ablauf

1. Server ohne Token starten (`npm start -- -p 3100`) → POST muss 503 liefern.
2. Server mit Token starten (`EDGE_INGEST_TOKEN=test123 npx next start -p 3101`):
   - POST mit falschem Token → 401
   - POST gültig → 201, z. B.:
     `{"typ":"austreibung","kuhId":"Kuh #7","nachricht":"Test","konfidenz":0.9,"kamera":"stallwache"}`
   - GET `/api/events` → gepostetes Ereignis erscheint, `quelle: "edge-agent"`
3. Dashboard prüfen (Playwright, Chromium `/opt/pw-browsers/chromium`):
   - `/wache` auf Port 3101: Alarm sichtbar, Kachel „Kalbung (24 h)" zählt hoch,
     „Edge-Agent … zuletzt HH:MM" gefüllt.
   - `/wache` auf Port 3100 (leerer Store): Demo-Hinweis („Demo-Daten") sichtbar.
4. Gültige `typ`-Werte: `kalbeverdacht | austreibung | brunstverdacht | info`
   (Quelle: `lib/events.ts`, `EREIGNIS_TYPEN`).

## Hinweise

- Der Store ist In-Memory pro Serverless-Instanz — auf Vercel können GET/POST
  auf verschiedenen Instanzen landen; für Tests immer lokal prüfen.
- Nach dem Test alle `next start`-Prozesse beenden (`pkill -f "next start"`).
