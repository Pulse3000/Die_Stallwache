---
name: neue-kamera
description: Nimmt eine weitere Kamera in Stallblick auf — Konfigurationseintrag, Stream-Route, Env-Variablen, Edge-Agent-Zuordnung, Abnahme. Nutzen bei "neue Kamera", "Kamera hinzufügen", "fünfte Kamera", "Kamera umbenennen" oder wenn ein neues Tuya-Gerät vom Typ Kamera auftaucht.
---

# Eine weitere Kamera aufnehmen

Der Betrieb wächst in Kameras, nicht in Features. Die Zuordnung ist seit dem
Vier-Kamera-Ausbau datengetrieben: **eine neue Kamera braucht genau einen
Codeeintrag**, alles andere leitet sich daraus ab. Diese Prozedur hält das so
— und nennt die Stellen, die man trotzdem leicht vergisst.

## Vorab entscheiden: Bridge oder Tuya-Cloud?

| | Bridge (RTSP → go2rtc/MediaMTX) | Tuya-Cloud |
| --- | --- | --- |
| Latenz | niedrig (WebRTC) | höher (HLS, ~10–20 s) |
| Voraussetzung | Hardware im Stall-LAN | nur Geräte-ID |
| Video verlässt den Hof | nein | ja (Tuya-CDN) |
| Wofür | **Hauptkamera im Abkalbebereich** | Zweitkameras, schneller Einstieg |

Faustregel: Die Kamera, auf die es beim Kalben ankommt, gehört an die Bridge.
Alles Weitere darf über die Cloud laufen.

## Schritt 1 — Kennung festlegen

Kleingeschrieben, ohne Umlaute, stabil: `weidewache`, `abkalbebox`. Die
Kennung taucht in Route, Env-Variablen, Stream-Namen und den Ereignissen des
Edge-Agenten auf — **eine spätere Umbenennung ist teurer als fünf Minuten
Nachdenken**. Wie teuer, zeigt der Alt-Pfad `/api/stallbox/stream`, den es
nur deshalb noch gibt.

## Schritt 2 — Eintrag in `lib/config.ts`

Ein Objekt in `CAMERAS`, plus die Kennung im `CameraId`-Typ:

```ts
{
  id: "weidewache",
  name: "Weidewache",
  streamName: process.env.NEXT_PUBLIC_STREAM_NAME_4?.trim() || "weidewache",
  ort: "Weide",
  tuyaFaehig: WEIDEWACHE_TUYA,
  tuyaEndpoint: "/api/weidewache/stream",
}
```

Was sich daraus **von selbst** ergibt und nicht angefasst werden muss:
Kamerakarten und Reihenfolge auf dem Dashboard, Statusraster, Startkamera-
Auswahl in den Einstellungen, Rundlauf beim „Tauschen". Wer hier zusätzlich
Kennungen aufzählt, baut die Drift ein, die dieser Umbau gerade beseitigt hat.

## Schritt 3 — Nur bei Tuya: Kennung und Route

1. `lib/tuya.ts`: Kennung in `TuyaKameraId`, Geräte-ID in `DEVICE_IDS`,
   Anzeigename in `KAMERA_NAMEN`, Variablenname in `KAMERA_ENV`. Die vier
   Einträge gehören zusammen — fehlt einer, wird die 503-Meldung ungenau.
2. Neue Route `app/api/<kennung>/stream/route.ts`, sechs Zeilen:

```ts
import { kameraStreamAntwort } from "@/lib/kamera-stream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  return kameraStreamAntwort("weidewache");
}
```

Der CORS-Proxy (`/api/futterwache/proxy`) ist generisch und braucht nichts.

## Schritt 4 — Env-Variablen

In `.env.example` dokumentieren, in Vercel setzen (Production!):

| Variable | Wofür |
| --- | --- |
| `NEXT_PUBLIC_STREAM_NAME_<n>` | Stream-/Pfadname auf der Bridge |
| `NEXT_PUBLIC_<KENNUNG>_TUYA` | `0` erzwingt die Bridge |
| `TUYA_DEVICE_ID_<KENNUNG>` | nur bei Tuya |

**Geräte-IDs gehören nie ins Repository** — es ist öffentlich, und dort hat
weder der Gerätebestand des Hofes noch dessen Netz etwas zu suchen.

## Schritt 5 — Bridge-Seite (falls Bridge)

Stream unter demselben Namen in der Bridge-Konfiguration anlegen
(`bridge/`), Kamera-Zugangsdaten dort hinterlegen. Prüfen:
`<BRIDGE_URL>/api/frame.jpeg?src=<streamName>` liefert ein Bild.

## Schritt 6 — Edge-Agent (falls die Kamera analysiert werden soll)

Nicht jede Kamera muss überwacht werden — eine Weidekamera liefert im Winter
nichts. Wenn doch: In `config.yaml` `stream.kamera` auf die Kennung setzen
(erscheint so in jedem Ereignis) und die Quelle wählen — Bridge-RTSP oder
`stream.quelle_api: /api/<kennung>/stream` für den Cloud-Weg ohne Bridge.

Pro Kamera **ein eigener Agent-Prozess mit eigener `config.yaml`**. Ein
Prozess für mehrere Kameras würde die Zeitfenster der Erkennungslogik
vermischen — jede Kuh-ID gehört zu genau einem Stream.

## Schritt 7 — Abnahme

```bash
# Route antwortet und nennt bei fehlender ID die richtige Variable
curl -s "$B/api/<kennung>/stream"

# Kamera erscheint in der Geräteübersicht
curl -s "$B/api/tuya/geraete" | python3 -m json.tool

# Gesamtbild
bash .claude/skills/betriebs-bereitschaft/bereitschaft.sh "$B"
```

Dann `npm run build`, `npx tsc --noEmit`, `npx eslint .` und ein Blick aufs
Dashboard im Handy-Format (Skill `pwa-abnahme`, Teil A3). Bei mehr als vier
Kameras das Statusraster prüfen — es steht auf zwei Spalten und wird ab
sechs Kameras zu lang; dann ist der Zeitpunkt für eine kompaktere Darstellung
gekommen, nicht früher.

## Was NICHT passieren darf

- **Keine Kamera-Galerie.** Vision-Nicht-Ziel: „keine Galerie mit 16
  Kamerakacheln". Ab etwa sechs Kameras ist die Frage nicht mehr „wie zeigen
  wir alle", sondern „welche ist die wichtigste" — dann gehört die Auswahl
  gefiltert, nicht die Kachel verkleinert.
- **Keine Kennung ändern, ohne den Alt-Pfad zu behalten.** Android-App und
  laufende Edge-Agenten haben Pfade fest konfiguriert; ein 404 schaltet dort
  still das Livebild ab.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| 1–3 (Code) | Orchestrator (dieser Skill) |
| 4 (Env in Vercel), 5 (Bridge) | Betreiber |
| 6 (Agent-Prozess) | Betreiber, angeleitet |
| 7 (Abnahme) | Orchestrator |
