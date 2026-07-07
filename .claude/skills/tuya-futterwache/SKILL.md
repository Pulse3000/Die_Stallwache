---
name: tuya-futterwache
description: Schließt die Tuya-Cloud-Anbindung der Futterwache ab, sobald Access ID, Access Secret und Device ID vorliegen. Nutzen bei "Tuya", "Futterwache Cloud", "Kamera-API verbinden".
---

# Futterwache über Tuya-Cloud anbinden

Server- UND Frontend-Seite sind fertig gebaut: `lib/tuya.ts` (signierte
OpenAPI-Calls, Token-Cache), `GET /api/futterwache/stream` (kurzlebige HLS-URL,
503 solange unkonfiguriert) und `components/CameraStream.tsx` (Tuya-Pfad mit
go2rtc-Fallback, Ablauf-Neuabruf). **Es fehlen nur noch die Zugangsdaten** —
sobald die `TUYA_*`-Env-Vars in Vercel gesetzt sind, läuft die Futterwache als
Hauptbild automatisch über Tuya.

## Voraussetzungen (vom Nutzer)

Aus [iot.tuya.com](https://iot.tuya.com) → Cloud → Projekt:
1. **TUYA_ACCESS_ID** (Access ID / Client ID)
2. **TUYA_ACCESS_SECRET** (Access Secret — der `sk-EU…`-Key des Nutzers ist
   vermutlich dieser Wert)
3. **TUYA_DEVICE_ID** (Projekt → Devices → Futterwache)
4. Region prüfen: EU-Default `https://openapi.tuyaeu.com` (`TUYA_API_BASE`
   nur bei anderer Region setzen)

Wichtig: In der Tuya-Projekt-Konsole muss die API **"IoT Video Live Stream"**
(bzw. IPC Open Service) abonniert und das Gerät mit dem Projekt verknüpft sein
(App-Konto unter "Link Tuya App Account" verknüpfen) — sonst kommt Fehler 1106
(permission deny) oder 28841105 (API nicht abonniert).

## Schritte

1. Env-Vars setzen: **der Nutzer** trägt die drei Werte in Vercel ein
   (Settings → Environment Variables, Production); Secret-Store-Schreibzugriff
   aus der Session ist gesperrt. Lokal: `.env.local`.
2. Testen: `curl -s https://die-stallwache.vercel.app/api/futterwache/stream`
   → erwartet `{"url":"https://…m3u8","typ":"hls"}`; bei Fehler liefert die
   Route die Tuya-Fehlermeldung im Feld `fehler` (Codes oben beachten).
3. Frontend ist **bereits umgesetzt** (`components/CameraStream.tsx`,
   `camera.tuyaFaehig`): Futterwache als Hauptbild holt die HLS-URL von
   `/api/futterwache/stream`, bei fatalem HLS-Fehler eine frische (Tuya-URLs
   laufen ab), und fällt bei 503 automatisch auf go2rtc zurück. Vorschau bleibt
   leichtgewichtig (go2rtc-Snapshot oder ruhiger Platzhalter — kein zweiter
   Dauerstream). Reines go2rtc erzwingen: `NEXT_PUBLIC_FUTTERWACHE_TUYA=0`.
4. `stallblick-deploy`-Skill ausführen (Build → Smoke → Deploy → Live-Check).

## Sicherheitsregeln

- Zugangsdaten niemals ins Repo, nie in `NEXT_PUBLIC_*`-Variablen, nie im
  Klartext in Chats/PRs zitieren.
- Nach Einrichtung empfehlen: Secret im Tuya-Portal rotieren, falls es zuvor
  ungeschützt geteilt wurde.
