# AUFTRAG an Bauleiter — Lesbare Quelle für Tagesreport-Punkte 2 und 3

**Ziel:** `GET /api/lagebericht` gemäß `docs/lagebericht-vertrag.md`; Smoke-Skript und Build grün.

**Kontext (zuerst lesen):** `docs/lagebericht-vertrag.md` · `scripts/smoke-lagebericht.sh` ·
bestehende Route `/api/events` · PR #70 · `docs/roadmap.md` · Skill `stallblick-app-konventionen`

## Plan-Fragen (mit Pfaden beantworten)

1. Wohin persistiert `/api/events` heute (Dienst, Schlüssel/Collection, Felder)?
2. Was schreibt der Sink aus PR #70 wohin — und ist er deployt?
3. Vergleicht `/api/events` den Token in konstanter Zeit?
4. Nimmt `/api/events` `kamera: "stallbox"` an?
5. Liegen bereits Edge-Ereignisse in der Persistenz (Anzahl, jüngstes Datum)?
6. Dateistruktur der neuen Route; Testansatz für die beiden 503-Fälle.

## Definition of Done

- [ ] `bash scripts/smoke-lagebericht.sh` grün gegen `npm run dev`; `npm run build` grün; bestehende Tests grün
- [ ] 503-Fälle (Token nicht gesetzt / Persistenz nicht lesbar) als Unit-Test
- [ ] Ingest-Vertrag unverändert (201/401/400/503) — belegt durch Smoke und bestehende Tests
- [ ] Antwort ohne Bilder, Keypoints, Rohdaten (Smoke prüft Zusatzfelder und Feldlängen)
- [ ] `docs/lagebericht-vertrag.md` Abschnitt „Umsetzung", Eintrag in `docs/roadmap.md`, 1–3 Zeilen in `CLAUDE.md`
- [ ] PR offen mit Prüfbericht; Merge erst nach qa-waechter

## Verbote

- Ingest-Schema oder -Antwortcodes ändern
- zweite Persistenz erfinden oder Firestore lesen, wenn `/api/events` nicht dorthin schreibt
- neue Pakete oder externe Dienste (B8); Tokens oder Secrets im Repo
- Tests abschwächen; Smoke gegen Production laufen lassen

**Rückgabe:** PR-Link, Prüfbericht, Antworten auf die Plan-Fragen (sie zeigen, ob der Report
heute überhaupt Edge-Daten hätte).

## Nicht in diesem Auftrag

- B11-Transparenzkurve (Schwellenlinie = Konfigwert aus B16, nicht fest 20 %)
- `typ: eskalation` im Ingest (erst nach B17, Abnahme Wächter + Bauleiter)
