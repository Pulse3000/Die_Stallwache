---
name: persistenz-live-schalten
description: Go-Live der Ereignis-Persistenz, sobald der Betreiber den Vercel-KV-/Upstash-Store mit dem Projekt verknüpft hat — Env-Variablen prüfen, Redeploy, instanzübergreifende Persistenz end-to-end verifizieren, Roadmap-Folgepunkte entsperren. Nutzen bei "KV-Store angelegt", "Storage verknüpft", "Persistenz aktivieren" oder wenn das Dashboard nach Deploys Ereignisse verliert.
---

# Ereignis-Persistenz live schalten (KV-Store → Dashboard-Historie)

Der KV-Adapter in `lib/events.ts` ist fertig und **aktiviert sich selbst**,
sobald `KV_REST_API_URL` + `KV_REST_API_TOKEN` existieren (legt Vercel beim
Verknüpfen eines Stores automatisch an). Diese Prozedur verifiziert den
Go-Live und räumt die Roadmap nach.

## Voraussetzung (vom Betreiber, 2 Klicks)

Vercel-Dashboard → Projekt `die-stallwache` → **Storage** → Create →
**Upstash Redis** (bzw. „Vercel KV") → mit dem Projekt verknüpfen. Nur das —
keine Werte kopieren, keine Config anfassen.

## Schritt 1 — Env-Variablen bestätigen

Im Vercel-Dashboard (Settings → Environment Variables) müssen
`KV_REST_API_URL` und `KV_REST_API_TOKEN` erschienen sein (Production).
Fehlen sie: Store-Verknüpfung prüfen, NICHT von Hand anlegen.

## Schritt 2 — Redeploy

Env-Variablen greifen erst mit dem nächsten Deployment: leerer Commit auf
`main` (Git-Integration deployt) oder Redeploy im Dashboard. Warten bis
„Ready".

## Schritt 3 — End-to-End verifizieren (instanzübergreifend)

Der entscheidende Unterschied zum In-Memory-Fallback: Ereignisse überleben
Instanzwechsel und Deploys.

1. **Ingest:** `POST /api/events` mit gültigem `x-ingest-token` →
   201 (`{"typ":"info","nachricht":"Persistenz-Go-Live-Test"}`).
2. **Sofort-Lesen:** `GET /api/events` (eingeloggt) → Ereignis vorhanden,
   `quelle: "edge-agent"`, `letzterKontakt` gesetzt.
3. **Persistenz-Beweis:** erneutes Redeploy auslösen (neue Instanzen) →
   `GET /api/events` zeigt das Test-Ereignis **weiterhin** — vorher wäre es
   mit der Instanz verschwunden. Alternativ 15–30 min warten (Serverless-
   Instanzrotation) und erneut lesen.
4. **Fail-open-Gegenprobe bleibt gültig:** Der Ingest darf auch bei
   KV-Störung nie blockieren (bereits durch `edge-agent`-unabhängige
   Testabdeckung in dieser Codebasis belegt; kein erneuter Test nötig).

## Schritt 4 — Aufräumen & entsperren

- Test-Ereignis kann bleiben (Ringpuffer 200) oder via Upstash-Konsole
  (`DEL kiwache:ereignisse kiwache:kontakt`) entfernt werden.
- `docs/roadmap.md`: P1 Ereignis-Persistenz auf ✅; die Blocker-Vermerke
  von **Kalbe-Akte** (P3) und **7-Tage-Trend** (P3) aktualisieren — beide
  hängen danach nur noch am Modell bzw. an der Umsetzung.
- Betreiber informieren: Dashboard-Historie ist jetzt dauerhaft; der
  Demo-Daten-Hinweis verschwindet mit dem ersten echten Ereignis endgültig.

## Rollback

Store-Verknüpfung im Vercel-Dashboard lösen + Redeploy → der Adapter fällt
automatisch auf In-Memory zurück (Fail-open ist eingebaut); das Dashboard
verhält sich wieder wie vor dem Go-Live. Keine Code-Änderung nötig.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Store anlegen/verknüpfen (2 Klicks) | Betreiber |
| Schritte 1–4 ausführen | Orchestrator (dieser Skill) |
| Smoke der Ereignis-Kette danach | Skill `ki-wache-smoketest` |
