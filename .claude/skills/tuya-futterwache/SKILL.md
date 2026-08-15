---
name: tuya-futterwache
description: Schließt die Tuya-Cloud-Anbindung einer Kamera (Stallwache, Futterwache, Abkalbebox, Weidewache) ab, sobald Access ID, Access Secret und die kameraeigene Device ID vorliegen. Nutzen bei "Tuya", "Futterwache/Abkalbebox Cloud", "Kamera-API verbinden", "Kalbeüberwachung ohne Bridge".
---

# Kamera über Tuya-Cloud anbinden

Server- UND Frontend-Seite sind fertig gebaut: `lib/tuya.ts` (signierte
OpenAPI-Calls, Token-Cache, mehrere Geräte über dasselbe Projekt),
`GET /api/stallwache/stream`, `/api/futterwache/stream` bzw.
`/api/stallbox/stream` (kurzlebige HLS-URL, 503 solange unkonfiguriert) und
`components/CameraStream.tsx` (Tuya-HLS mit Ablauf-Neuabruf). **Es fehlen nur
noch die Zugangsdaten** — sobald die `TUYA_*`-Env-Vars in Vercel gesetzt sind,
läuft die jeweilige Kamera als Hauptbild automatisch über Tuya.
`GET /api/<kamera>/stream` — stallwache | futterwache | abkalbebox |
weidewache (kurzlebige HLS-URL, 503 solange unkonfiguriert) und
`components/CameraStream.tsx` (Tuya-Pfad mit Bridge-Fallback,
Ablauf-Neuabruf). **Es fehlen nur noch die Zugangsdaten** — sobald die
`TUYA_*`-Env-Vars in Vercel gesetzt sind, läuft die jeweilige Kamera als
Hauptbild automatisch über Tuya.

**Sonderfall Stallwache (Hauptkamera, Abkalbebereich):** Sie trägt die
Kalbe- und Brunsterkennung. Tuya ist dort **opt-in** — zusätzlich zur
Device-ID muss `NEXT_PUBLIC_STALLWACHE_TUYA=1` gesetzt werden, damit
bestehende Bridge-Höfe ihr Verhalten behalten. Mit beidem läuft die
komplette Überwachung ohne Bridge; im Edge-Agenten dazu `stream.url` leer
lassen und `stream.quelle_api: /api/stallwache/stream` setzen.

## Voraussetzungen (vom Nutzer)

Aus [iot.tuya.com](https://iot.tuya.com) → Cloud → Projekt:
1. **TUYA_ACCESS_ID** (Access ID / Client ID) — gilt projektweit, für alle Kameras gleich
2. **TUYA_ACCESS_SECRET** (Access Secret — der `sk-EU…`-Key des Nutzers ist
   vermutlich dieser Wert) — ebenfalls projektweit
3. Pro Kamera eine eigene Geräte-ID (Projekt → Devices):
   **TUYA_DEVICE_ID_STALLWACHE**, **TUYA_DEVICE_ID_FUTTERWACHE**,
   **TUYA_DEVICE_ID_STALLBOX**
   **TUYA_DEVICE_ID_ABKALBEBOX**, **TUYA_DEVICE_ID_WEIDEWACHE**
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
2. Testen (App-Login blockiert direktes Curl von außen – lokal oder per
   Vercel-Runtime-Logs prüfen): erwartet `{"url":"https://…m3u8","typ":"hls"}`
   von `/api/<kamera>/stream`; bei Fehler liefert die Route die
   Tuya-Fehlermeldung im Feld `fehler` (Codes oben beachten). Erwartete Kette
   pro Route: **503** ohne Env-Vars → **401** ohne App-Session → **502** bei
   Tuya-Fehler → **200** mit gültigen Zugangsdaten.
3. Frontend ist **bereits umgesetzt** (`components/CameraStream.tsx`,
   `camera.tuyaEndpoint`): Jede Kamera holt als Hauptbild ihre HLS-URL vom
   eigenen Endpoint und bei fatalem HLS-Fehler eine frische (Tuya-URLs laufen
   ab). Einen Bridge-Fallback gibt es seit der Tuya-Umstellung nicht mehr —
   bei 503 bleibt die Kachel beim Wartehinweis. Die Vorschau zeigt bewusst
   einen ruhigen Platzhalter (kein zweiter Dauerstream, keine zusätzliche
   Allokation). Dieselbe Logik in der Android-App: `Der-Stallblick`
   (`KameraStreamView.kt`).
   `camera.tuyaFaehig`/`camera.tuyaEndpoint`): Jede Tuya-fähige Kamera holt als
   Hauptbild ihre HLS-URL vom eigenen Endpoint, bei fatalem HLS-Fehler eine
   frische (Tuya-URLs laufen ab), und fällt bei 503 automatisch auf go2rtc
   zurück. Vorschau bleibt leichtgewichtig (go2rtc-Snapshot oder ruhiger
   Platzhalter — kein zweiter Dauerstream). Reine Bridge erzwingen:
   `NEXT_PUBLIC_FUTTERWACHE_TUYA=0`, `NEXT_PUBLIC_ABKALBEBOX_TUYA=0` bzw.
   `NEXT_PUBLIC_WEIDEWACHE_TUYA=0`. Die Stallwache ist umgekehrt verdrahtet
   (opt-in): ohne `NEXT_PUBLIC_STALLWACHE_TUYA=1` bleibt sie auf der Bridge.
4. `stallblick-deploy`-Skill ausführen (Build → Smoke → Deploy → Live-Check).

## Sicherheitsregeln

- Zugangsdaten niemals ins Repo, nie in `NEXT_PUBLIC_*`-Variablen, nie im
  Klartext in Chats/PRs zitieren.
- Nach Einrichtung empfehlen: Secret im Tuya-Portal rotieren, falls es zuvor
  ungeschützt geteilt wurde.
