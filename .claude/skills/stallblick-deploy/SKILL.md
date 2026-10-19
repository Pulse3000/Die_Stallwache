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
2. **Smoke-Test lokal** (ohne `STALLBLICK_PASSWORT`, also ohne Login):
   `node node_modules/next/dist/bin/next start -p 3100 &` und die PID (`$!`)
   merken — nicht `npm start`: `kill` trifft dann nur den npm-Wrapper, der
   `next-server` bleibt verwaist auf dem Port und spätere Messungen laufen
   ohne Fehlermeldung gegen den alten Stand. Dann:
   - `curl -s -o /dev/null -w '%{http_code}' http://localhost:3100/` → 200
   - `curl -s -o /dev/null -w '%{http_code}' http://localhost:3100/wache` → 200
   - `curl -s http://localhost:3100/api/events` → JSON mit `ereignisse`
   Bei UI-Änderungen: Playwright-Screenshot (Chromium: `/opt/pw-browsers/chromium`,
   Viewport 390×844) und visuell prüfen. Danach `kill <PID>` und prüfen, dass
   der Port frei ist: `curl -s -o /dev/null http://localhost:3100/login` muss
   fehlschlagen (Exit 7). Nicht mit `ss`/`lsof` prüfen — die fehlen hier bzw.
   zeigen in der Sandbox nichts an.
3. **Deploy:** Ein Merge auf `main` deployt Vercel selbst (Git-Integration).
   Dann nur warten, bis das Produktions-Deployment des Merge-Commits `READY`
   ist und `stallwache.vercel.app` als Alias trägt (Vercel-MCP
   `list_deployments`/`get_deployment`, `meta.githubCommitSha` vergleichen).
   Nur ohne Merge von Hand: `npx vercel deploy --prod --yes < /dev/null` (im
   Hintergrund starten; wartet die CLI auf Device-Login, dem Nutzer die
   `vercel.com/oauth/device`-URL samt Code geben).
4. **Live-Check:** Produktion läuft mit Passwortschutz (`STALLBLICK_PASSWORT`,
   `middleware.ts`). Ohne Session muss gelten:
   - `/login` → 200
   - `/` und `/wache` → 307 auf `/login?weiter=…`
   - `GET /api/events` → 401 `{"fehler":"Nicht angemeldet"}`
   - `/sw.js` → 200, Content-Type beginnt mit `application/javascript`;
     `/manifest.webmanifest` → 200
   - `POST /api/events` ohne Token oder mit falschem Token → 401
     `{"fehler":"Ungültiger Token."}` — niemals 201

   Nicht als „grün“ werten, sondern dem Nutzer melden:
   - `/` oder `/wache` ohne Session → 200: Der Passwortschutz ist in
     Produktion aus.
   - `POST /api/events` → 503: `EDGE_INGEST_TOKEN` fehlt, der Edge-Agent kann
     keine Meldung zustellen (lokal ohne Token ist 503 richtig).
5. **Git:** Änderungen committen und auf den Arbeitsbranch pushen; ohne offenen
   PR einen Draft-PR anlegen.

## Wichtige Eigenheiten

- Produktions-Alias: `stallwache.vercel.app` (alt `die-stallwache.vercel.app` leitet per 307 dorthin um) (Team `stallwache`,
  Projekt `die-stallwache`, `team_7af87ADvim4feu9IPsZoUFq8`).
- Env-Vars (`EDGE_INGEST_TOKEN`, `STALLWACHE_FERN_TOKEN`, …) nur der Nutzer
  im Vercel-Dashboard setzen lassen — Schreibzugriff auf den Secret-Store ist
  in dieser Umgebung gesperrt.
- Kein manueller Deploy nötig, wenn nur `edge-agent/`, `docs/` oder `.claude/`
  geändert wurden (läuft nicht auf Vercel). Vercel baut beim Merge trotzdem
  ein Produktions-Deployment (kein `ignoreCommand` in `vercel.json`); den
  Live-Check aus Schritt 4 danach wie gewohnt ausführen.
