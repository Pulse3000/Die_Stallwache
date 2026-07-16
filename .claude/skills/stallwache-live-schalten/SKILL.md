---
name: stallwache-live-schalten
description: Go-Live der Stallwache-Hauptkamera, sobald der Betreiber den Cloudflare-Tunnel-Hostnamen der Bridge meldet — Bridge prüfen, NEXT_PUBLIC_BRIDGE_URL in Vercel setzen, Redeploy, Livebild und KI-Wache-Kette end-to-end verifizieren. Nutzen bei "Tunnel läuft", "Hostname ist ...", "Bridge ist online" oder wenn die Stallwache-Kachel dauerhaft den Platzhalter zeigt.
---

# Stallwache live schalten (Bridge → Webapp)

Der wartende Meilenstein des Projekts: Die Termux-Bridge auf dem Stall-Handy
(`bridge/termux/install.sh`) liefert go2rtc + Cloudflare-Tunnel; sobald der
Betreiber den öffentlichen Hostnamen meldet, schaltet diese Prozedur die
Hauptkamera in der Webapp live — und damit die gesamte Modell-Kette frei
(Silent Mode → Skill `modell-training`).

## Voraussetzung (vom Betreiber)

Ein Hostname wie `https://stallwache.example.com` (Cloudflare Zero Trust →
Tunnel → Public Hostname auf `http://localhost:1984`). Nur der Hostname wird
gebraucht — keine Tokens, keine Passwörter.

## Schritt 1 — Bridge von außen prüfen (vor jeder Änderung)

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

## Schritt 2 — Env-Variable in Vercel setzen

Genau EINE Variable, vom Betreiber benannt bzw. geliefert:

```bash
vercel env add NEXT_PUBLIC_BRIDGE_URL production   # Wert: https://HOSTNAME
```

- `NEXT_PUBLIC_BRIDGE_TYPE` NICHT setzen (Default go2rtc stimmt für die
  Termux-Bridge; nur bei MediaMTX-Setup auf `mediamtx`).
- Alias `NEXT_PUBLIC_GO2RTC_URL` ist Alt-Name — nicht zusätzlich setzen.
- `NEXT_PUBLIC_*` wird beim **Build** eingebacken → Schritt 3 ist Pflicht.

## Schritt 3 — Redeploy auslösen

Leerer Commit auf `main` (Git-Integration deployt automatisch) oder
`vercel --prod`. Warten bis der Deploy „Ready" ist.

## Schritt 4 — End-to-End verifizieren

1. **Login-Gate:** `/` antwortet 307 → `/login` (Schutz weiter aktiv).
2. **Livebild:** eingeloggt auf `/` — Stallwache-Kachel zeigt Video statt
   Platzhalter (WebRTC; HLS-Fallback greift automatisch). Headless-Prüfung:
   Playwright, `video`-Element mit `readyState >= 2` auf der Hauptkachel.
3. **Vorschau-Snapshot:** Futterwache/Stallwache-Rollentausch (Kachel-Klick)
   funktioniert ohne Remount-Ruckler.
4. **Kette komplett:** Betreiber startet den Edge-Agent
   (`bash edge-agent/setup.sh`) → Startmeldung „Silent Mode" erscheint unter
   `/wache` („Edge-Agent … zuletzt HH:MM").

## Schritt 5 — Anschlussarbeiten

- `docs/roadmap.md`: Bridge-bezogene Zeilen auf ✅, Meilenstein-Abschnitt
  aktualisieren.
- Betreiber informieren: Ab jetzt sammelt der Silent Mode Trainingsbilder —
  in 1–2 Wochen weiter mit Skill `modell-training`.
- Skill `bytetrack-tuning` vormerken (nach dem ersten `best.pt`).

## Rollback

Kachel schwarz/Fehler nach Go-Live: `NEXT_PUBLIC_BRIDGE_URL` in Vercel
entfernen + Redeploy → Webapp zeigt wieder den sauberen Platzhalter
(Fehlerzustand ist schlimmer als Wartezustand). Dann Schritt 1 wiederholen.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Tunnel/Hostname bereitstellen, Handy pflegen | Betreiber |
| Schritte 1–5 ausführen | Orchestrator (dieser Skill) |
| Smoke der Ereignis-Kette | Skill `ki-wache-smoketest` |
