---
name: pwa-abnahme
description: Abnahmeprüfung der mobilen PWA — Installierbarkeit, Service Worker, Offline-Betrieb, Aktions-Warteschlange, Bild-Replay und Datensparen am echten Gerät durchspielen. Nutzen nach Änderungen an public/sw.js, lib/offline.ts, app/layout.tsx, dem Manifest oder den vier Bereichen, sowie vor jeder Übergabe an den Betrieb.
---

# PWA-Abnahme (installierbar, offlinefähig, weckfähig)

Die PWA-Eigenschaften haben eine unangenehme Gemeinsamkeit: **Sie fallen
still aus.** Ein kaputter Service Worker sieht bei bestehender Verbindung
exakt aus wie ein funktionierender — der Unterschied zeigt sich erst im
Funkloch, also genau dann, wenn niemand mehr etwas reparieren kann.

Diese Prozedur erzwingt den Ausfall im Trockenen.

## Teil A — Automatisiert (Orchestrator)

### A1. Auslieferung

```bash
for p in / /alarme /steuerung /einstellungen /offline \
         /sw.js /manifest.webmanifest /icon-192.png /icon-512.png; do
  printf "%-24s %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code} %{content_type}' "$BASIS$p")"
done
```

Alle 200. **`/sw.js` muss `application/javascript` sein** — bei aktivem
Passwortschutz ist der Pfad in `middleware.ts` von der Session-Prüfung
ausgenommen. Wird er wieder eingefangen, liefert er die Login-Seite als HTML,
der Browser verweigert die Registrierung, und die App verliert Offline-
Betrieb *und* Push, ohne dass irgendwo ein Fehler erscheint. Das ist der
teuerste stille Ausfall dieser Codebasis — er gehört an den Anfang jeder
Abnahme.

### A2. Manifest

```bash
curl -s "$BASIS/manifest.webmanifest" | python3 -m json.tool
```

`name`, `start_url`, `display: standalone`, mindestens ein 192er- und ein
512er-PNG, davon eines `purpose: maskable`.

### A3. Browser-Smoketest

Chromium headless (`/opt/pw-browsers/chromium`), Viewport **390×844**, je
Bereich: keine Konsolenfehler, Tab-Leiste mit vier Zielen vorhanden,
erwartete Überschriften da. Screenshots ansehen, nicht nur den Exit-Code —
ein Layout kann fehlerfrei und trotzdem unbrauchbar sein.

Beim Vergleich von Texten unempfindlich gegen Groß-/Kleinschreibung prüfen:
Die Abschnittslabels sind per CSS in Versalien gesetzt, `innerText` gibt sie
so zurück, und ein wörtlicher Vergleich meldet dann Fehler, die keine sind.

Erwartete Nicht-Fehler: `/api/tuya/geraete` antwortet ohne Tuya-Konfiguration
mit 503, was der Browser als Konsolenfehler protokolliert. Die Seite zeigt
dafür den Hinweistext — das ist korrektes Verhalten, kein Befund.

## Teil B — Am echten Gerät (Betreiber, angeleitet)

Diese Punkte lassen sich headless nicht ehrlich prüfen.

### B1. Installation

- Android/Chrome: Menü → *App installieren*.
- iOS/Safari: Teilen → *Zum Home-Bildschirm*.
- Startet ohne Browser-Adressleiste, Symbol und Name stimmen.

### B2. Offline lesen

1. App öffnen, Alarme laden lassen (Puffer füllt sich).
2. **Flugmodus.**
3. App schließen, neu öffnen → Oberfläche startet, unterer Streifen meldet
   „Offline – angezeigt wird der zuletzt bekannte Stand".
4. Alarme-Tab zeigt die zuletzt geladenen Ereignisse.
5. Einen Alarm mit Bild öffnen → **Replay läuft aus dem Cache**.
6. Eine nie besuchte Seite aufrufen → `/offline`-Seite statt Browserfehler.

### B3. Offline handeln (Aktions-Warteschlange)

1. Im Flugmodus einen Alarm **„Gesehen"** tippen → verschwindet sofort
   optisch; oben meldet der Streifen die offene Aktion.
2. Einstellungen → *Gerät & Diagnose* → „Nicht gesendete Aktionen" ≥ 1.
3. **Flugmodus aus.**
4. Innerhalb weniger Sekunden geht die Aktion raus, Zähler auf 0.
5. Serverseitig prüfen: `GET /api/events` → das Ereignis trägt `quittiert`.

Auf iOS gibt es keinen Background Sync; dort geht die Warteschlange beim
nächsten App-Start raus. Das ist erwartet — beim Testen die App einmal in den
Vordergrund holen.

### B4. Datensparen

- Dashboard zeigt zunächst ein Standbild mit „Live starten"; Video läuft
  erst auf Tippen. (Der Knopf erscheint nur, wenn die Kamera erreichbar ist —
  bei „Offline" fehlt er absichtlich.)
- Alarmbilder werden erst auf Tippen geladen.
- Beide Schalter in den Einstellungen wirken sofort.

### B5. Push

Vollständig in Skill `push-live-schalten`, inklusive Nachtprobe. Hier nur
die Verschränkung prüfen: Eine Benachrichtigung antippen öffnet den
**richtigen** Alarm (`/alarme?id=…`), und die Aktion „Gesehen" quittiert ihn
auch aus dem gesperrten Zustand heraus.

## Teil C — Nach dem Ändern des Service Workers

`public/sw.js` wird vom Browser aggressiv zwischengespeichert. Nach jeder
Änderung:

1. `VERSION` in `sw.js` hochziehen, wenn sich Cache-Inhalte oder -Strategien
   geändert haben — die `activate`-Phase räumt alle Caches weg, deren Name
   nicht mit der aktuellen `VERSION` beginnt.
2. Am Gerät: Entwicklertools → Application → Service Workers → *Update on
   reload*, oder App deinstallieren und neu installieren.
3. **Schema-Änderungen an IndexedDB immer an beiden Stellen** — `public/sw.js`
   und `lib/offline.ts` teilen sich dieselbe Datenbank (`stallwache`).
   Auseinanderlaufende Schemata äußern sich als stumm verschluckte Alarme,
   nicht als Fehler.

## Abnahmekriterium

Bestanden ist die Abnahme erst, wenn **B2 und B3 am echten Gerät gelaufen
sind**. Teil A allein beweist nur, dass die Dateien ausgeliefert werden — er
beweist nicht, dass die App im Stall noch bedienbar ist.

## Rollenverteilung

| Teil | Wer |
| --- | --- |
| A (Auslieferung, Manifest, Smoketest) | Orchestrator (dieser Skill) |
| B (Installation, Offline, Warteschlange, Datensparen) | Betreiber, angeleitet |
| C (nach SW-Änderung) | Orchestrator, Ergebnis an Betreiber |

## Verwandt

- `push-live-schalten` — Alarmweg scharfschalten
- `stallblick-deploy` — Build/Deploy davor
- `ki-wache-smoketest` — Ereigniskette Agent → API → Dashboard
