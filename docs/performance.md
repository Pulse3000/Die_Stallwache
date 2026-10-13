# Performance – Client-JS pro Route

Messung: `next build && next start`, Chromium (Playwright), Summe aller beim
Laden geholten Skripte nach `networkidle` + 1,5 s, **unkomprimiert**.
Skript zur Wiederholung: Seite laden und `resourceType === "script"`-Antworten
aufsummieren.

| Route | vorher | nachher | Δ |
| --- | --- | --- | --- |
| `/` (Livebild) | 1014,4 KB | 514,3 KB | **−49 %** |
| `/wache` | 521,1 KB | 521,1 KB | ±0 |

## Maßnahmen

1. **hls.js nur bei Bedarf laden** (`components/CameraStream.tsx`):
   statischer Import → `import("hls.js")` erst, wenn der Browser kein natives
   HLS kann und ein HLS-Pfad wirklich gestartet wird. Safari/iOS und
   WebRTC-Pfade laden die ~500 KB nie. Nur Typ-Import bleibt statisch.
2. `next.config.mjs`: `poweredByHeader: false`,
   `optimizePackageImports: ["three", "firebase"]` (PR #54).

## Warum `/wache` nicht weiter sinkt

Von 521 KB sind ~514 KB Next.js-/React-Runtime und das gemeinsame Layout
(Router, `PwaLaufzeit` mit Service-Worker/Offline-Queue, `TabLeiste`). Die
seiteneigene Logik (`WacheDashboard`) ist nur 6,8 KB. Weitere Einsparung ginge
nur durch Abbau von PWA-/Offline-Funktionen – ausgeschlossen.

## Übertragungsgröße (gzip, alle Ressourcen)

Gleiche Messung, aber jede Antwort mit gzip -9 komprimiert und nach Typ
summiert – das entspricht grob dem, was über Stall-WLAN/Mobilfunk geht.

| Route | vorher | nachher | Δ |
| --- | --- | --- | --- |
| `/` gesamt | 559,3 KB | 169,9 KB | **−70 %** |
| `/` davon Bild | 401,9 KB | 4,9 KB | −99 % |
| `/` davon JS | 147,3 KB | ~150 KB | ± Messrauschen (Prefetch-Zeitpunkt) |
| `/wache` gesamt | 160,0 KB | 160,0 KB | ±0 |

3. **Logo in Anzeigegröße ausliefern:** `logo-stallwache.jpg` (859×864 px,
   412 KB) wurde im Header mit 36 px und auf `/login` mit max. 220 px
   gezeigt. Jetzt `logo-stallwache-108.webp` (5 KB, 3× für Retina) im Header
   und `logo-stallwache-440.webp` (54 KB, 2×) auf `/login`, jeweils mit
   `width`/`height` gegen Layout-Springen. Das Original bleibt liegen.
4. **Header-Logo offline:** in die App-Shell von `public/sw.js`
   aufgenommen, `VERSION` → `stallwache-v3`.

JS ist auf beiden Routen zu ~95 % Next.js-/React-Runtime (~140 KB gzip);
eigener Code liegt unter 10 KB.

## Streams nur bei Sicht

Seit alle Kameras beim Öffnen live laufen, würden auch Kacheln streamen, die
niemand sieht: weiter unten auf der Seite oder in einem Tab im Hintergrund. Das
kostet Mobilfunkdaten, Akku und – bei Tuya – bei jedem Neuverbinden einen
API-Aufruf (begrenztes Kontingent).

5. **Pausieren statt streamen** (`lib/pausiert.ts`, `CameraStream.pausiert`):
   - Tab verborgen (Bildschirm aus, andere App) → **sofort** pausieren.
   - Kachel aus dem Bild gescrollt → nach **5 s** pausieren (kurzes
     Wegscrollen kostet keine neue Verbindung); 150 px Vorlauf am Bildrand.
   - Wieder sichtbar → sofort fortsetzen. Das Vollbild pausiert nie.
   - Beim Laden gelten Befunde erst nach 350 ms: Das Layout verschiebt sich
     anfangs noch (eine Kachel am Bildrand rutschte sonst nach dem ersten
     Befund nach unten, hatte sich aber schon verbunden).
   - Statusanzeige: pausierte Kacheln zeigen „Pausiert". Eine pausierte, nie
     verbundene Kachel zählt nicht als Störung („3 Kameras online · 1 pausiert"),
     eine zuvor online gewesene gilt weiter als online. „Offline" bleibt sichtbar.
6. **Schlankere hls.js-Puffer** (`maxBufferLength` 8 s, kein Rückpuffer):
   vier Player gleichzeitig, weniger Speicher.

**Messung** (Chromium 390×844, `tests/e2e/pausiert.mjs`, Stream-Endpunkte mit
503 beantwortet; gezählt werden Verbindungsversuche):

| Situation | vorher | nachher |
| --- | --- | --- |
| Laden: Kachel unterhalb des Bildschirms | verbindet sich sofort | 0 Anfragen |
| nach Scrollen zurück nach oben (5 s) | läuft weiter | pausiert |
| Tab verborgen, 12 s | alle Kacheln fragen weiter an | 0 Anfragen |
| Tab wieder sichtbar | – | sichtbare Kacheln verbinden sich neu |

Nicht gemessen sind Bytes echter Videostreams (lokal ohne Kameras); der Effekt
folgt daraus, dass pausierte Kacheln keine Segmente laden.
