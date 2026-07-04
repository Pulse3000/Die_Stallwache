---
name: stallblick-deploy
description: Baut, verifiziert und deployt Stallblick auf Vercel-Produktion. Nutzen bei "deploy", "auf Vercel bringen", "live stellen" oder nach jedem Feature-Merge.
---

# Stallblick: Build, Verifikation & Vercel-Deploy

Fester Ablauf für jedes Produktions-Deployment. Nie einen Schritt überspringen —
kaputte Deploys kosten Vertrauen ins „Dritte Auge".

## Schritte

1. **Build lokal:** `npm run build` — muss ohne Fehler durchlaufen.
   Bei Python-Änderungen zusätzlich `python3 -m py_compile edge-agent/main.py`.
2. **Smoke-Test lokal:** `npm start -- -p 3100` im Hintergrund, dann:
   - `curl -s -o /dev/null -w '%{http_code}' http://localhost:3100/` → 200
   - `curl -s -o /dev/null -w '%{http_code}' http://localhost:3100/wache` → 200
   - `curl -s http://localhost:3100/api/events` → JSON mit `ereignisse`
   Bei UI-Änderungen: Playwright-Screenshot (Chromium: `/opt/pw-browsers/chromium`,
   Viewport 390×844) und visuell prüfen.
3. **Deploy:** `npx vercel deploy --prod --yes < /dev/null` (im Hintergrund
   starten; wartet die CLI auf Device-Login, dem Nutzer die
   `vercel.com/oauth/device`-URL samt Code geben).
4. **Live-Check:** `https://die-stallwache.vercel.app/`, `/wache` und
   `/api/events` müssen 200 liefern; bei POST ohne Token muss `/api/events`
   503 (unkonfiguriert) oder 401 (falscher Token) liefern — niemals 201.
5. **Git:** Änderungen committen und auf den Arbeitsbranch pushen; ohne offenen
   PR einen Draft-PR anlegen.

## Wichtige Eigenheiten

- Produktions-Alias: `die-stallwache.vercel.app` (Team `stallwache`,
  Projekt `die-stallwache`, `team_7af87ADvim4feu9IPsZoUFq8`).
- Env-Vars (`EDGE_INGEST_TOKEN`, `NEXT_PUBLIC_GO2RTC_URL`, …) nur der Nutzer
  im Vercel-Dashboard setzen lassen — Schreibzugriff auf den Secret-Store ist
  in dieser Umgebung gesperrt.
- Kein Deploy nötig, wenn nur `edge-agent/`, `docs/` oder `.claude/` geändert
  wurden (läuft nicht auf Vercel).
