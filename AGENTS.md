# AGENTS.md — Base44 Entwicklungsumgebung

## Starten (Runbook)

```bash
docker compose -f docker-compose.base44.yml up -d --build
docker compose -f docker-compose.base44.yml logs -f web
```

* Ein einzelner Next.js-16-Dev-Server (`npm run dev`) auf **Port 3000** —
  kein DB-Service, keine Migrationen, kein Seed.
* `npm ci` laeuft bei jedem Containerstart aus dem gemounteten Lockfile;
  `node_modules` liegt im Named Volume `node_modules`, damit der Bind-Mount
  es nicht verdeckt.
* Es gibt **kein** Produktions-Image und keinen `next build` im Dev-Betrieb:
  der Quellcode ist live gemountet, Aenderungen greifen per HMR
  (`WATCHPACK_POLLING=true` wegen Bind-Mount ohne inotify-Ereignisse).

## Nicht offensichtlich

* **`allowedDevOrigins` in `next.config.mjs` ist Pflicht.** Der Preview-Proxy
  reicht den Browser-Origin durch; ohne die Allowlist blockiert Next.js
  Dev-Assets und HMR. Die Werte kommen aus `BASE44_PUBLIC_HOST_SUFFIX` /
  `BASE44_SANDBOX_HOST_DOMAIN` (compose `environment:`) und sind
  umgebungsspezifisch — nie hart eintragen.
* **Die App laeuft vollstaendig ohne Zugangsdaten.** Alle Integrationen sind
  optional und degradieren sichtbar statt zu crashen:
  * Ohne Bildweg (weder Fernzugriff/Tuya noch Bridge) zeigt die Kachel
    „Noch kein Livebild eingerichtet". `NEXT_PUBLIC_BRIDGE_URL` bleibt im
    Normalfall leer (`docs/fernzugriff-spezifikation.md` §2).
  * Ohne `TUYA_ACCESS_ID`/`TUYA_ACCESS_SECRET` antwortet
    `GET /api/tuya/geraete` mit **503 by design**; die Steuerung zeigt
    „Tuya nicht konfiguriert".
  * Ohne `KV_REST_API_URL`/`KV_REST_API_TOKEN` liefert `/api/events`
    Demo-Ereignisse aus dem In-Memory-Ringpuffer (`lib/events.ts`).
  * Push (FCM), Pub/Sub, GCS und der Assistent (Vertex/Gemini) sind ebenfalls
    optional — die App bleibt ohne sie nutzbar.
* **Passwort-Gate:** `middleware.ts` + `lib/auth.ts` schuetzen die App nur,
  wenn `STALLBLICK_PASSWORT` gesetzt ist. Fuer eine offene Preview leer
  lassen.
* Bridge (`bridge/`) und Edge-Agent (`edge-agent/`) gehoeren **nicht** in den
  Dev-Stack: die Bridge laeuft auf Hardware im Stall-LAN, der Agent ist ein
  Python-Prozess, der gegen die Webapp spricht.
* Der Dev-Server kompiliert Routen beim ersten Aufruf — die erste Navigation
  auf einen Bereich braucht ein bis zwei Sekunden.

## Pruefen

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/          # 200
curl -s http://localhost:3000/ | grep -o turbopack                        # Dev-Quelle
curl -s "http://localhost:3000/api/events?stunden=24" | head -c 200       # Demo-Events
npm test                                                                  # 24 Checks, ohne Build
```

Produktions-Build zur Kontrolle (baut aktuell fehlerfrei):

```bash
docker compose -f docker-compose.base44.yml exec -T web npm run build
```

Achtung: `next build` und `next dev` teilen sich `.next`. Ein Build neben
einem laufenden Dev-Server stoert dessen Zustand — danach
`docker compose -f docker-compose.base44.yml restart web`.

Erwartung ohne Zugangsdaten: fuenf Bereiche rendern (`/`, `/alarme`,
`/steuerung`, `/analytik`, `/einstellungen`), Kopf z. B. „0 von 3 online ·
1 pausiert" mit rotem Punkt (korrekt: alle Stream-Endpunkte antworten 503;
Regeln in `docs/vorschau-status-spezifikation.md`),
`/api/events` liefert Demo-Daten, `/api/tuya/geraete` → 503.

## Merge-Freigabe

Der Betreiber erlaubt Agenten dauerhaft, eigene PRs gegen `main` selbst zu
mergen (Merge = Vercel-Produktionsdeploy) – aber nur, wenn
`npm run typecheck && npm run lint && npm test && npm run build` grün ist,
die Vercel-Preview „Ready" meldet, keine Review-Threads offen sind und kein
Merge-Konflikt besteht. Danach Live-Check laut
`.claude/skills/stallblick-deploy/SKILL.md`.
