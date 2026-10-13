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
