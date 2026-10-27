# Spezifikation: KI-Ansicht der Stallwache (Kühe mit Kasten und ID)

Stand: 27.10.2026 · Entscheidung des Betreibers: „auf der Webseite bei zum
Beispiel dem Stallwache-Stream die Kühe in der Box mit der zugehörigen ID
anzeigen“. Gewählt wurde die **KI-Ansicht mit 1 Bild/s** statt eines
Overlays auf dem Livevideo.
**Status: umgesetzt, automatische Abnahme (§6, 1–6) bestanden. Sichtbar wird
etwas erst mit einem eigenen Modell** (der Agent läuft im Silent Mode);
Kriterien 7–10 am Gerät offen.

## 1. Grundsatz

1. **Gezeigt wird, was der Agent gesehen hat, nicht das Livevideo.** Die
   Kachel der Stallwache bekommt einen Schalter „KI-Ansicht“. Ist er an,
   liegt über dem Video das Bild, das der Edge-Agent zuletzt analysiert
   hat, mit eingezeichneten Kästen und Beschriftung. Kasten und Bild
   stammen aus demselben Frame. Ein Overlay auf dem Livevideo hinge dem
   Bild hinterher, beim Tuya-Stream um 5–15 s (verworfene Variante).
2. **Was eingezeichnet wird:**
   - jede getrackte Kuh mit grünem Kasten und „Kuh #ID“, dahinter der
     Schwanzwinkel, wenn die Keypoints gültig sind („Kuh #12 52 Grad“). Das
     ist dieselbe Nummer wie in den Alarmen;
   - Fruchtblase und Kälberfüße mit rotem Kasten, Name und Konfidenz
     („Fruchtblase 0.91“, „Kaelberfuesse 0.87“);
   - oben links Kamera und Uhrzeit des Bilds („stallwache 14:32:05“).

   Die Bildschrift von OpenCV (Hershey) kennt nur ASCII, daher „Grad“
   statt „°“ und „ae/ue“ statt Umlaut. Alle Schriften haben eine dunkle
   Kontur, damit sie auf hellem Fell wie auf dunklem Stroh lesbar bleiben.
3. **Der Weg ist der vorhandene Fernzugriff, nichts Neues ist öffentlich:**

   ```
   Edge-Agent ──schreibt──▶ /dev/shm/stallwache-<kamera>/ki-ansicht.jpg (RAM)
   Handy ──Login──▶ Webapp ──Token──▶ Funnel ──▶ fern-proxy.py ──liest──▶ Datei
   ```

   - Der Agent schreibt das Bild **im Analyse-Modus** nach jeder Analyse,
     also etwa einmal je Sekunde, atomar (temporäre Datei, dann
     `os.replace`) und in den Arbeitsspeicher (`/dev/shm`): Kein
     Plattenverschleiß, kein Netzverkehr, solange niemand hinsieht.
   - `fern-proxy.py` liefert die Datei nur mit dem Token aus, nur wenn sie
     frisch ist (§3), und nur unter genau einem Pfad. Die go2rtc-API
     bleibt unberührt.
   - Die Webapp reicht das Bild nur hinter dem App-Login weiter
     (fail-closed wie das HLS, `fernzugriff-spezifikation.md` §1).
4. **Stille Degradation:** Schreibfehler, volle Platte oder fehlender
   Ordner stoppen die Analyse nie. Der Agent protokolliert höchstens eine
   Warnung je Stunde und analysiert weiter.
5. **Datenschutz:** Das Bild verlässt den Stall-Rechner nur über den
   ausdrücklich eingerichteten Fernzugriff und nur auf Abruf eines
   angemeldeten Nutzers. Ohne Fernzugriff bleibt es im RAM des
   Stall-Rechners.

## 2. Grenzen

- **Silent Mode zeigt nichts.** Ohne Modell gibt es keine Analyse und
  damit keine KI-Ansicht. Die Kachel sagt das ausdrücklich (§5), statt ein
  leeres oder altes Bild zu zeigen.
- **Nur die Stallwache, nur mit Fernzugriff.** Die Tuya-Kameras
  (Futterwache, Abkalbebox, Weidewache) haben keinen Weg vom Stall-Rechner
  zur Webapp, außer über Vercel. Ein Bild je Sekunde über Vercel und den
  KV-Store sprengt die Freikontingente (≈ 86 400 Schreibvorgänge je Tag
  und Kamera). Für sie braucht es eine eigene Entscheidung.
- **Die ID ist die Nummer des Trackers, keine Ohrmarke.** Nach einem
  Neustart des Agenten bekommt dieselbe Kuh eine neue Nummer (Skill
  `bytetrack-tuning`, Grenzen). Die Kachel sagt das in der Fußzeile.
- **1 Bild je Sekunde, nicht flüssig.** Die Ansicht dient der
  Nachvollziehbarkeit („welche Kuh meint der Alarm?“), nicht dem Zuschauen.
- **Datenverbrauch am Handy:** ein JPEG je Sekunde (≈ 50–80 KB bei 960 px),
  also etwa 200–300 MB je Stunde. Bei „Datensparen“ alle 5 s. Abrufe nur,
  solange der Tab sichtbar ist (`sichtbaresIntervall`).

## 3. Schwellenwerte und Konstanten

| Name | Wert | Wo | Warum |
| --- | --- | --- | --- |
| Bildbreite | 960 px | Agent | lesbare Beschriftung am Handy, ≈ 60 KB |
| JPEG-Qualität | 70 | Agent | Kästen und Schrift bleiben scharf |
| Frische | 10 s | fern-proxy (Dateizeit, Uhr des Stall-Rechners), Kachel (Bildzeit steht still, Uhr des Handys) | älter → „nicht aktuell“, nie ein altes Bild als aktuell; eine falsch gehende Uhr am Stall-Rechner stört die Kachel nicht |
| Höchstgröße | 2 MB | fern-proxy | Schutz vor falscher Datei am Pfad |
| Abruftakt | 1 s, bei Datensparen 5 s | Kachel | wie die Analyse, sparsam auf Wunsch |
| Warnung bei Schreibfehler | höchstens 1 je Stunde | Agent | Log-Flut auf der Karte vermeiden |

## 4. Konfiguration

- **Edge-Agent:** Pfad aus `ki_ansicht.datei` in `config.yaml`, sonst aus
  der Umgebung `KI_ANSICHT_DATEI`; leer = aus.
  `edge-agent/docker-compose.yml` setzt beides für den Container:
  - Bind `/dev/shm/stallwache-${KAMERA}:/ki-ansicht`,
  - `KI_ANSICHT_DATEI=/ki-ansicht/ki-ansicht.jpg`.

  Wer den Agenten per Compose betreibt, muss also nichts eintragen.
- **fern-proxy.py:** `KI_ANSICHT_DATEI`, Default
  `/dev/shm/stallwache-stallwache/ki-ansicht.jpg`. Der neue Pfad heißt
  `GET /api/ki-ansicht` (Token wie bei allen Pfaden), bewusst ohne
  Endung: Der Matcher in `middleware.ts` nimmt `*.jpg` vom Login aus.
  Zusätzlich prüft die Fernzugriff-Route die Sitzung selbst.
- **Webapp:** kein neues Env. Der Schalter erscheint, wenn
  `NEXT_PUBLIC_STALLWACHE_FERN=1` gesetzt ist und die Stallwache das
  Hauptbild ist. `lib/fern.ts` bekommt `ki-ansicht` in die Allowlist
  (Spiegel von `fern-proxy.py`).

## 5. UI-Texte

| Lage | Text |
| --- | --- |
| Schalter | „KI-Ansicht“ (an) / „Video“ (zurück) |
| Fußzeile, Bild da | „KI-Ansicht · Stand 14:32:05 · Nummern vom Tracker, keine Ohrmarken“ |
| 404 vom Agenten, kein Bild | „Keine KI-Ansicht – der Edge-Agent analysiert gerade nicht (Silent Mode ohne Modell oder Agent aus).“ |
| Bild älter als 10 s | „KI-Ansicht nicht aktuell – letztes Bild von 14:31:40.“ |
| Login abgelaufen (401) | „KI-Ansicht nicht erreichbar – bitte neu anmelden.“ |
| Fernzugriff gestört (Netzfehler, 5xx) | „KI-Ansicht nicht erreichbar – Fernzugriff zum Stall gestört.“ |
| Beim Laden | „KI-Ansicht lädt …“ |

Solange die KI-Ansicht an ist, entfallen „LIVE“ und „Live starten“ an der
Kachel; ein altes Bild bleibt abgeblendet stehen, bis ein neues kommt.

## 6. Abnahmekriterien

Automatisch (vor dem Merge):
1. Agent-Logiktest: Kasten und „Kuh #ID“ werden gezeichnet, Fruchtblase
   rot mit Konfidenz, Breite 960 px. Geschrieben wird atomar: Ein Leser
   sieht nie eine halbe Datei. Ein Schreibfehler stoppt die Schleife nicht
   und loggt höchstens einmal je Stunde. Im Silent Mode wird nichts
   geschrieben.
2. fern-proxy-Test: ohne Token 403, falscher Pfad 404. Datei fehlt → 404,
   älter als 10 s → 404, größer als 2 MB → 404. Frisch → 200 mit
   `image/jpeg`, `Cache-Control: no-store` und `X-Bild-Zeit`.
3. `tests/fern.test.ts`: `ki-ansicht` ist erlaubt, ohne Parameter;
   andere Pfade bleiben gesperrt. `tests/middleware.test.ts`: Die
   Middleware erfasst alle Fernzugriff-Pfade (keiner fällt unter die
   Ausnahme für statische Bilder).
4. Route: reicht `X-Bild-Zeit` nur als Ganzzahl durch.
5. E2E im Browser mit nachgebildeter Route:
   - Schalter nur bei der Stallwache und nur mit Fernzugriff.
   - Bild wird je Sekunde neu geladen, im verborgenen Tab nicht.
   - Texte für 404, „nicht aktuell“ und „gestört“ wie §5.
6. `npm run typecheck && npm run lint && npm test && npm run build`,
   `python3 edge-agent/tests/alle_tests.py`, `qa-waechter` grün.

Am Gerät (erst mit Modell, Beweispflicht):
7. KI-Ansicht zeigt dieselbe „Kuh #ID“ wie der nächste Telegram-Alarm.
8. Abstand zwischen Uhrzeit im Bild und Uhr am Handy ≤ 3 s.
9. CPU-Last des Agenten auf der A6-3650 steigt um höchstens 5 %.
10. Silent Mode: Kachel zeigt den 404-Text aus §5.

## 7. Risiken

1. **CPU auf dem alten Stall-Rechner:** Zeichnen, Verkleinern und
   JPEG-Kodieren je Sekunde. Gegenmaßnahme: erst verkleinern, dann zeichnen
   und kodieren. Kriterium 9 misst es.
2. **Verwechslung mit Tieridentität:** Die Fußzeile nennt die Nummern
   ausdrücklich „vom Tracker“.
3. **Veraltetes Bild als aktuell gezeigt:** Die Frische wird doppelt
   geprüft: im Proxy anhand der Dateizeit, in der Kachel daran, ob sich
   `X-Bild-Zeit` weiterbewegt (Handy-Uhr).
4. **Ein zusätzlicher Pfad im öffentlichen Proxy:** Er liefert genau eine
   Datei mit fester Größengrenze, nur mit Token und nur per GET. Er führt
   keine Pfadangabe des Aufrufers aus.

## 8. Umsetzung

| Teil | Datei | Prüfung |
| --- | --- | --- |
| Zeichnen und atomar schreiben | `edge-agent/main.py` (`KiAnsicht`) | `edge-agent/tests/test_ki_ansicht.py` |
| RAM-Ordner und Pfad | `edge-agent/docker-compose.yml`, `config.example.yaml` (`ki_ansicht`) | ebenda |
| Ausliefern am Stall | `bridge/fern-proxy.py` (`lies_ki_ansicht`) | `edge-agent/tests/test_fern_proxy.py` |
| Allowlist, Status, Bildzeit | `lib/fern.ts`, `app/api/stallwache/fern/[...pfad]/route.ts` | `tests/fern.test.ts` |
| Zustand und Texte der Kachel | `lib/ki-ansicht.ts`, `components/KiAnsicht.tsx`, `components/StallblickApp.tsx` | `tests/ki-ansicht.test.ts`, `tests/e2e/ki-ansicht.mjs` |

Gemessen (Testrechner, nicht die A6-3650): Verkleinern, Zeichnen,
Kodieren und Schreiben eines 1080p-Bilds ≈ 35 ms, JPEG ≈ 20 KB.

**Inbetriebnahme am Stall-Rechner**, sobald ein Modell läuft:
1. Agent mit `ANALYSE=1 docker compose up -d --build` neu starten. Compose
   bindet `/dev/shm/stallwache-stallwache` ein und setzt den Pfad.
2. `fern-proxy.py` aktualisieren (`git pull`, dann
   `sudo systemctl restart stallwache-fern`). Der Default-Pfad passt, kein
   neues Env nötig.
3. Webapp deployen (Merge). Der Schalter erscheint bei aktivem
   Fernzugriff (`NEXT_PUBLIC_STALLWACHE_FERN=1`).
