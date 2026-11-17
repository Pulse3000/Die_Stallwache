# CLAUDE.md — Stallblick / KI-Wache

Kamerabasierte Brunst- und Kalbeüberwachung für den Betrieb „Oberer
Stollenhof". Zwei Teile in einem Repo: die **Webapp** (Next.js-PWA auf
Vercel: Livebild, Alarme, Steuerung, Analytik) und der **Edge-Agent**
(Python im Stall: YOLO-Pose + ByteTrack, Regeln, Telegram). Sprache in Code,
Doku und Commits: Deutsch.

Diese Datei wird in jeder Sitzung geladen. Sie bleibt kurz; Einzelheiten
stehen in `docs/` und in den Skills. Alles hier ist gegen den Code geprüft —
`npm run geruest` hält es so.

## Einstieg in drei Schritten

1. **Was ist zu tun?** → [`docs/arbeitsvorrat.md`](docs/arbeitsvorrat.md):
   abarbeitbare Pakete mit Abnahmekriterien, getrennt nach Agent und Betreiber.
2. **Was ist der Stand?** → [`docs/roadmap.md`](docs/roadmap.md): Single
   Source of Truth für „gebaut, offen, blockiert".
3. **Wer macht was?** → [`docs/agenten-orchestrierung.md`](docs/agenten-orchestrierung.md):
   Agenten, Skills, Entscheidungsbaum „Wann was?".

Bei „läuft das System?" zuerst Skill `betriebs-bereitschaft`.

## Regeln, die nie verhandelt werden

1. **Austreibung nie unterdrücken.** Fruchtblase oder Kälberfüße ab
   Konfidenz 0.80 melden sofort, ohne Zeitfilter und ohne Cooldown. Keine
   Änderung darf diesen Weg verzögern, filtern oder hinter eine Bedingung
   stellen. Recall geht hier vor Präzision.
2. **Sonst: Ruhe vor Fülle.** Kalbeverdacht und Brunst melden nur bei
   zeitlicher Evidenz. Nie einen Zeitfilter durch einen Einzelbild-Trigger
   ersetzen. Keine Test- oder Probealarme an den Landwirt.
3. **Kein Alarm ohne Modell-Befund.** Nichts erfinden, nichts aus Bewegung
   oder Anwesenheit ableiten. Jeder Alarm trägt Bild und Kuh-ID.
4. **Schwellenwerte ändert nur der Betreiber.** Die Referenzwerte unten sind
   fest. Änderung nur mit dokumentierter Entscheidung in `docs/roadmap.md`,
   danach Treue-Befund vom Agenten `ki-wache`.
5. **Schweigen ist kein OK.** Fehlt ein Lebenszeichen, ein Modell oder der
   Speicher, heißt der Status `UNBEKANNT` mit Grund — nie `OK`.
6. **Die Analyse wartet nie auf das Netz.** Telegram, Dashboard, MQTT und
   Uploads laufen entkoppelt; ihr Ausfall stoppt keine Bildauswertung.
7. **Video verlässt den Hof nicht.** Ins Netz gehen nur Ereignisse und
   einzelne Alarmbilder. Kein Abo, keine Cloud-Videoanalyse, 0 € laufend.
8. **Tierart-neutral.** Klassen, Keypoints und Schwellen bleiben
   Konfiguration; im Edge-Agenten keine Rind-Festverdrahtung neu einführen.
9. **Geheimnisse bleiben draußen.** Nie ins Repo, nie ins Log, nie in eine
   `NEXT_PUBLIC_*`-Variable. Neue Variablen in `.env.example` beschreiben.
10. **Beweispflicht.** „Fertig" heißt: geprüft, mit Beleg. Was nur am echten
    Gerät oder Stream prüfbar ist, wird als **offen** gemeldet, nicht als grün.

### Referenzwerte der Erkennung (`edge-agent/config.example.yaml`)

| Regel | Wert |
| --- | --- |
| Kalbeverdacht | Schwanzwinkel > 45° (`spine_end→tail_base` gegen `tail_base→tail_tip`) in > 20 % der Bilder eines 30-min-Fensters, je Kuh-ID |
| Austreibung | `amniotic_sac` oder `calf_legs`, Konfidenz ≥ 0.80 → Sofort-Alarm |
| Eskalation | Austreibung nach 60 min weiter sichtbar → einmaliger Kontroll-Alarm |
| Brunstverdacht | Aufsprung: zwei Kuh-Boxen, IoU > 0.15, eine oberhalb, ≥ 4 s |
| Cooldown | 15 min je Kuh-ID und Alarmtyp — gilt **nicht** für Austreibung und Eskalation |
| Totmann | 5 min ohne Bild → genau eine Meldung, eine Entwarnung |

**Falle:** Andere Vorgaben nennen für einen Cloud-Layer abweichende Werte
(60 % statt 20 %, Keypoint `back_mid`, Sofort-Alarm nur bei Fruchtblase). Das
ist eine **offene Betreiber-Entscheidung** (Roadmap, Zeile „GCP-Stallwache-
Vorgabe vs. Edge-Regeln"), kein Auftrag. Bis sie fällt, gelten die Werte
dieser Tabelle; den Keypoint `back_mid` gibt es im Modell nicht.

## Befehle

```bash
npm run pruefen      # ALLES: Typecheck, Lint, Web-Tests, Gerüst, Agent-Tests, Build
npm run typecheck    # tsc --noEmit
npm run lint         # eslint
npm test             # Web-Logiktests (node --test, ohne Build)
npm run geruest      # Doku/Skills/Agenten gegen den Code (scripts/geruest-pruefung.mjs)
npm run test:agent   # Edge-Agent-Logiktests, kompakte Ausgabe
npm run build        # Produktions-Build
npm run dev          # Dev-Server auf Port 3000
```

- Die Agent-Tests brauchen außer `numpy` kein Paket: `cv2`, `yaml`,
  `requests`, torch werden gestubbt. Zwei Dateien (Freeze-Watchdog) rechnen
  mit echtem `numpy`; fehlt es, sind sie rot. **Sonst nichts installieren**
  (kein torch, kein ultralytics).
  Eine einzelne Datei: `python3 edge-agent/tests/test_versand.py`.
- Die Webapp läuft ohne jede Zugangsdaten; fehlende Bausteine antworten mit
  503 und einem Hinweistext. Das ist Absicht, kein Fehler.
- Der SessionStart-Hook (`.claude/hooks/session-start.sh`) installiert die
  npm-Pakete in Cloud-Sitzungen selbst.

## Arbeitsablauf

1. **Entscheidung vor Code.** Neue Regel oder neues Verhalten zuerst in die
   Spezifikation (`docs/*-spezifikation.md`) und die Roadmap, dann Code.
2. **Tests zuerst** aus den Abnahmekriterien der Spezifikation.
3. **Klein bleiben.** Ein Paket aus dem Arbeitsvorrat je PR. Nichts
   „vorbauen", dessen Voraussetzung fehlt (Skill `spezifikation-umsetzen`).
4. **`npm run pruefen` grün**, bevor irgendetwas als fertig gilt.
5. **Fachprüfung** bei Änderungen an `edge-agent/main.py` oder Schwellen:
   Agent `ki-wache`. **Abnahme vor Merge:** Agent `qa-waechter`. Befunde
   prüfen und selbst einarbeiten, nicht durchreichen.
6. **Doku nachziehen:** Roadmap-Status, betroffene Spezifikation, bei neuen
   Skills das Handbuch. `npm run geruest` meldet, was fehlt.
7. **PR als Entwurf** auf dem Arbeitsbranch; Commit-Texte sagen, was sich für
   den Betrieb ändert.

### Merge und Auslieferung

Ein Merge auf `main` ist ein **Produktions-Deploy** (Vercel,
`https://stallwache.vercel.app`). Der Betreiber erlaubt Agenten, eigene PRs
selbst zu mergen — nur wenn alles gilt: `npm run pruefen` grün, CI grün,
Vercel-Preview „Ready", keine offenen Review-Threads, kein Konflikt. Danach
Live-Check nach Skill `stallblick-deploy`. Fremde PRs nie mergen.

Kein Force-Push (per Repo-Regel gesperrt). Nach einem Squash-Merge den Branch
vorwärts bauen, siehe Handbuch, Muster 5.

## Karte

| Ort | Inhalt |
| --- | --- |
| `app/`, `components/`, `lib/` | Webapp. Logik ohne Framework-Importe liegt in `lib/` und ist mit `npm test` prüfbar |
| `app/api/events/` + `lib/events.ts` | Ingest der Alarme (Token `EDGE_INGEST_TOKEN`), Speicher, Bilder, Quittierung |
| `lib/stall-status.ts` | Statusabfrage `OK`/`WARNUNG`/`KRITISCH`/`UNBEKANNT` |
| `middleware.ts` + `lib/auth.ts` | Passwortschutz der ganzen App **und** Ausnahme für `/sw.js` |
| `public/sw.js`, `lib/offline.ts` | Service Worker, Offline-Puffer, Push |
| `edge-agent/main.py` | Der Agent im Stall (eine Datei, ~3000 Zeilen). Defaults: `config.example.yaml` |
| `edge-agent/tests/` | Logiktests, Einstieg `hilfe.py` (`lade_main`, `Pruefer`) |
| `edge-agent/training/` | Datensatz-Split, Abnahme-Gates, Colab-Training, Modellkarte |
| `bridge/` | go2rtc + `fern-proxy.py` (Fernzugriff über Tailscale Funnel) |
| `cloud-functions/` | Pub/Sub → Firestore-Sink (optional) |
| `docs/` | Vision, Roadmap, Arbeitsvorrat, Spezifikationen, Handbuch |
| `.claude/` | Agenten, Skills, Hook, Berechtigungen |
| `AGENTS.md` | Nur das Runbook der Base44-Dev-Umgebung (Docker) |

Kameras: `stallwache` (Hauptkamera, Fernzugriff), `futterwache`,
`abkalbebox`, `weidewache` (Tuya-Cloud). Fünf Bereiche: Dashboard, Alarme,
Steuerung, Analytik, Einstellungen; dazu `/wache` als Detailsicht.

## Agenten

| Agent | Wofür | Darf nicht |
| --- | --- | --- |
| `ki-wache` | Erkennungslogik prüfen und erklären, Alarmtexte formulieren | Dateien ändern, Schwellen lockern |
| `qa-waechter` | Build, Auth-Kette, Routen, PWA, Logiktests, Browser-Smoke | Fixes anwenden, committen |
| `markt-analyst` | Wettbewerb recherchieren, Tabellenzeilen liefern | Dateien ändern |

Aufträge an Agenten sind abgeschlossen formuliert: Ziel, betroffene Dateien,
Erfolgskriterium, Verbot außerhalb des Mandats. Der Auftrag an den
Fachexperten endet mit „widersprich, wenn es fachlich nicht trägt".

## Bekannte Fallen

- **`/sw.js` und der Passwortschutz:** Fängt die Middleware den Pfad ein,
  kommt HTML statt JavaScript; Offline-Betrieb und Push fallen still aus.
  Nach jeder Änderung an `middleware.ts` mit gesetztem `STALLBLICK_PASSWORT`
  gegenprüfen (`qa-waechter`, Punkt 6).
- **`next build` und `next dev` teilen sich `.next`.** Nicht gleichzeitig.
- **Testserver beenden:** nie `pkill -f "next start"` (trifft die eigene
  Shell). Mit `node node_modules/next/dist/bin/next start -p <Port> &`
  starten, PID merken, per PID beenden, Port prüfen.
- **`edge-agent/__pycache__`** nach `py_compile` löschen; nie einchecken.
- **Stall-Adressen (`*.ts.net`) sind aus Cloud-Sitzungen nicht erreichbar.**
  Ein Abbruch von dort beweist nichts (Skill `stallwache-live-schalten`).
- **Erwartetes Rot im Browser:** `/api/tuya/geraete` → 503 ohne Tuya-Daten,
  abgebrochene Next-Prefetches (`?_rsc=`). Keine Befunde.
- **Zwei Namen, eine Kamera:** Abkalbebox hieß „Stallbox"; alte Routen und
  Variablen bleiben als Alias, weil App und Agenten sie fest eingetragen haben.

## Wann nachfragen statt handeln

Fragen, wenn eine Aufgabe Schwellenwerte oder Alarmverhalten ändert, Geld
kostet, Zugangsdaten braucht, einen Eingriff am Stall-Rechner verlangt oder
zwei Dokumente einander widersprechen. In allen anderen Fällen: begründete
Annahme treffen, im PR benennen, weiterarbeiten.

## Modellneutralität

Dieses Gerüst hängt an keinem bestimmten Modell. In Agenten, Skills, Code
und Doku stehen keine Modellnamen; Agenten nageln kein `model:` fest.
Was ein Schritt an Sorgfalt braucht, steht als prüfbares Kriterium da — nicht
als Erwartung an das Urteilsvermögen der ausführenden Sitzung.
