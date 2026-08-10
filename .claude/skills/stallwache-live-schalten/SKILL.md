---
name: stallwache-live-schalten
description: Go-Live der Stallwache-Hauptkamera über die Tuya-Cloud — Gerät prüfen, TUYA_DEVICE_ID_STALLWACHE in Vercel setzen, Redeploy, Livebild und KI-Wache-Kette end-to-end verifizieren. Nutzen bei "Stallwache live schalten", "Device ID ist ...", "Kamera ist verknüpft" oder wenn die Stallwache-Kachel dauerhaft den Platzhalter zeigt.
---

# Stallwache live schalten (Tuya-Cloud → Webapp)

Der wartende Meilenstein des Projekts: Sobald die Stallwache-Kamera im
Tuya-Projekt verknüpft ist und der Betreiber ihre Device ID meldet, schaltet
diese Prozedur die Hauptkamera live — und damit die gesamte Modell-Kette frei
(Silent Mode → Skill `modell-training`).

> Seit der Tuya-Umstellung gibt es **keine Bridge** mehr (kein go2rtc/MediaMTX,
> kein Cloudflare-Tunnel, kein Gerät im Stall). Die Legacy-Konfiguration liegt
> unter `_archiv/` und ist für diesen Ablauf irrelevant.

## Voraussetzung (vom Betreiber)

1. Die Kamera hängt im selben Tuya-Cloud-Projekt wie Futterwache/Stallbox
   (`iot.tuya.com` → Cloud → Projekt → *Link Tuya App Account*).
2. Die API **„IoT Video Live Stream"** ist im Projekt abonniert.
3. Die **Device ID** der Stallwache (Projekt → Devices).

Access ID und Secret gelten projektweit und sind bereits gesetzt, wenn
Futterwache/Stallbox laufen — dann fehlt nur noch die Device ID.

## Schritt 1 — Gerät prüfen (vor jeder Änderung)

Läuft eine der anderen Kameras bereits, ist die Kette grundsätzlich intakt.
Für die neue Kamera zählt nur: Ist sie im Projekt sichtbar und `online`?
Serverseitig prüfbar über die Tuya-Konsole (Projekt → Devices) oder nach
Schritt 2 direkt am Endpoint.

Typische Fehlercodes, falls die Allokation scheitert:

| Code | Bedeutung |
| --- | --- |
| `1106` | permission deny — App-Konto nicht mit dem Projekt verknüpft |
| `28841105` | API „IoT Video Live Stream" nicht abonniert |

## Schritt 2 — Env-Variable in Vercel setzen

Genau EINE Variable, vom Betreiber geliefert:

```bash
vercel env add TUYA_DEVICE_ID_STALLWACHE production   # Wert: die Device ID
```

- **Nie** als `NEXT_PUBLIC_*` — die Tuya-Werte bleiben serverseitig.
- Secret-Store-Schreibzugriff aus der Session ist gesperrt: Der **Betreiber**
  trägt den Wert ein (Vercel → Settings → Environment Variables → Production).
- Fehlt die Variable, antwortet `/api/stallwache/stream` bewusst mit **503**
  und die Kachel bleibt beim Wartehinweis — die anderen Kameras laufen weiter.

## Schritt 3 — Redeploy auslösen

Leerer Commit auf `main` (Git-Integration deployt automatisch) oder
`vercel --prod`. Warten bis der Deploy „Ready" ist.

## Schritt 4 — End-to-End verifizieren

1. **Login-Gate:** `/` antwortet 307 → `/login` (Schutz weiter aktiv).
2. **Endpoint:** eingeloggt `GET /api/stallwache/stream` → `{"url":"/api/futterwache/proxy?url=…","typ":"hls"}`.
   Bei Fehler steht die Tuya-Meldung im Feld `fehler` (Codes siehe Schritt 1).
3. **Livebild:** eingeloggt auf `/` — Stallwache-Kachel zeigt Video statt
   Platzhalter. Headless-Prüfung: Playwright, `video`-Element mit
   `readyState >= 2` auf der Hauptkachel.
4. **Rollentausch:** Kachel-Klick tauscht Haupt-/Vorschaurolle ohne
   Remount-Ruckler. Die Vorschau zeigt bewusst einen ruhigen Platzhalter
   (kein zweiter Dauerstream, keine zusätzliche Tuya-Allokation).
5. **Kette komplett:** Betreiber startet den Edge-Agent
   (`bash edge-agent/setup.sh`, Quelle „1 = Cloud ohne Bridge") → Startmeldung
   „Silent Mode" erscheint unter `/wache` („Edge-Agent … zuletzt HH:MM").

## Schritt 5 — Anschlussarbeiten

- `docs/roadmap.md`: Meilenstein-Abschnitt aktualisieren.
- Betreiber informieren: Ab jetzt sammelt der Silent Mode Trainingsbilder —
  in 1–2 Wochen weiter mit Skill `modell-training`.
- Skill `bytetrack-tuning` vormerken (nach dem ersten `best.pt`).

## Rollback

Kachel schwarz/Fehler nach Go-Live: `TUYA_DEVICE_ID_STALLWACHE` in Vercel
entfernen + Redeploy → Webapp zeigt wieder den sauberen Wartehinweis
(Fehlerzustand ist schlimmer als Wartezustand). Dann Schritt 1 wiederholen.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Kamera im Tuya-Projekt verknüpfen, Device ID liefern, Env-Var eintragen | Betreiber |
| Schritte 1, 3–5 ausführen | Orchestrator (dieser Skill) |
| Smoke der Ereignis-Kette | Skill `ki-wache-smoketest` |
