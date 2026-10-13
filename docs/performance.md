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
