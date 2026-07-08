---
name: security-sweep
description: Gezielter Sicherheits-Bug-Hunt auf dem Stallblick-Code, besonders auf serverseitigen API-Routen (Ingest, Tuya-Proxy, Stream-Allokation). Nutzen vor Releases, nach neuen Routen oder bei "Sicherheit prüfen", "SSRF", "Injection", "Secrets".
---

# Security-Sweep: Stallblick

Fokussierter Sicherheitsdurchgang auf dem sicherheitskritischsten Code. Ziel:
Probleme vor Reviewern/Angreifern finden — Härtung bestehenden Codes, kein
neues Feature. Passt zum reifen Codestand (statt Scope-Ausweitung).

## Angriffsflächen (in dieser Reihenfolge prüfen)

1. **CORS-/Stream-Proxy** (`app/api/futterwache/proxy/route.ts`) — die
   heikelste Route, weil sie serverseitig fremde URLs abruft:
   - **SSRF via Redirect**: `fetch` muss `redirect: "manual"` nutzen und jede
     3xx-Antwort verwerfen. Sonst kann ein erlaubter Host auf einen internen
     Host (z. B. Cloud-Metadaten `169.254.169.254`) umleiten und die
     Host-Allowlist (die nur die *initiale* URL prüft) wird umgangen.
   - **Allowlist-Bypass**: Host-Prüfung muss mit führendem Punkt arbeiten
     (`.iot-11.com`), sonst matcht `eviliot-11.com`. Tarnhost-Test ist Pflicht.
   - **Protokoll**: nur `https:` zulassen (kein `http:`, kein `file:`).
   - **Kein offener Proxy**: nur bekannte Tuya-CDN-Hosts.
2. **Ingest-API** (`app/api/events/route.ts`): Token-Pflicht
   (`EDGE_INGEST_TOKEN`), ohne Token geschlossen (503), Feldlängen begrenzt,
   `typ` gegen Whitelist, kein ungefiltertes Echo von Eingaben.
3. **Tuya-Signierung** (`lib/tuya.ts`): Secrets nur serverseitig, niemals in
   `NEXT_PUBLIC_*`; keine Zugangsdaten in Logs/Fehlermeldungen.
4. **Secrets allgemein**: `grep` nach potenziellen Klartext-Tokens, prüfen dass
   `.env*` (außer `.env.example`) in `.gitignore` steht und nichts
   Sensibles committet wurde.

## Verifikationsmuster

- Sicherheits-Suite gegen die Proxy-Route (lokaler Server) fahren:
  fehlende/ungültige `url` → 400, nicht erlaubter Host + **Tarnhost** → 403,
  `http://` → 403, unerreichbarer erlaubter Host → 502.
- Redirect-Semantik separat belegen: `fetch(<redirector>, {redirect:"manual"})`
  gibt 301/302 zurück statt zu folgen → Guard verwirft.
- `next build` grün; keine Verhaltensänderung im Normalbetrieb.

## Leitplanken

- Nur Härtung, keine neuen Features. Kein Verwässern der Nutzererfahrung.
- Findings mit konkretem Angriffsszenario belegen (Eingabe → Fehlverhalten),
  nicht spekulativ. Reine Sicherheits-Fixes dürfen im Selbst-Review-Modus
  direkt gemergt werden, wenn Build + Suite grün sind.
