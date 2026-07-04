---
name: tuya-futterwache
description: Schließt die Tuya-Cloud-Anbindung der Futterwache ab, sobald Access ID, Access Secret und Device ID vorliegen. Nutzen bei "Tuya", "Futterwache Cloud", "Kamera-API verbinden".
---

# Futterwache über Tuya-Cloud anbinden

Die Server-Seite ist fertig vorbereitet: `lib/tuya.ts` (signierte OpenAPI-Calls,
Token-Cache) und `GET /api/futterwache/stream` (liefert kurzlebige HLS-URL,
503 solange unkonfiguriert). Es fehlen nur die Zugangsdaten und die
Frontend-Umschaltung.

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
3. Frontend umschalten (erst wenn Schritt 2 grün): In `CameraStream` für die
   Futterwache statt go2rtc-Snapshot die HLS-URL von
   `/api/futterwache/stream` abspielen (hls.js ist bereits Dependency).
   Vorschau-Prinzip beibehalten: HLS nur laden, wenn die Futterwache Hauptbild
   ist; als Vorschau weiterhin Einzelbilder (Canvas-Frame aus dem HLS-Stream
   alle 5 s oder go2rtc-Snapshot als Fallback). Kein zweiter hochpriorisierter
   Dauerstream auf dem Startscreen!
4. Tuya-URLs laufen nach kurzer Zeit ab → bei HLS-Fehler neue URL von der
   Route holen (sie allokiert pro Aufruf frisch).
5. `stallblick-deploy`-Skill ausführen (Build → Smoke → Deploy → Live-Check).

## Sicherheitsregeln

- Zugangsdaten niemals ins Repo, nie in `NEXT_PUBLIC_*`-Variablen, nie im
  Klartext in Chats/PRs zitieren.
- Nach Einrichtung empfehlen: Secret im Tuya-Portal rotieren, falls es zuvor
  ungeschützt geteilt wurde.
