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
  * Ohne `NEXT_PUBLIC_BRIDGE_URL` zeigt das Dashboard „Warte auf Bridge".
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
`/steuerung`, `/analytik`, `/einstellungen`), 0 von 4 Kameras online,
`/api/events` liefert Demo-Daten, `/api/tuya/geraete` → 503.
