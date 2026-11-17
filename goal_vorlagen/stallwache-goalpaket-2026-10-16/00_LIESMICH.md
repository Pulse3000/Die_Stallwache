# Goal-Paket Stallwache — 16.10.2026

Vier Sessions (Wächter, Trainer, Bauleiter, Späher) nach agentic build loop:
**Spezifikation + Tests zuerst → Plan-Modus → `/goal` gegen die Tests → Diff-Review + qa-waechter.**
Fokus: Edge-Erkennungslogik und Tagesreport-Punkte 2, 3, 4.

## Prüfstand (in dieser Sitzung belegt)

| Artefakt | Beleg |
|---|---|
| `kuhwatch/erkennung/` + Vertragstests | 58/58 grün; 12/12 Mutationen (u. a. Codestand-Fehler E1–E3, E5–E7) werden rot |
| `kuhwatch/tools/datensatz_inventur.py` | 18/18 grün; 5/5 Mutationen werden rot |
| Label-Vertrag (CVAT, YAML, Edge-Konfig) | 3/3 Konsistenztests grün |
| `Die_Stallwache/scripts/smoke-lagebericht.sh` | grün gegen vertragstreue, rot gegen vertragsbrüchige Attrappe |
| `Die_Stallwache/tools/radar_check.py` | Selbsttest grün |

## Ablage

| Datei im Paket | Ziel |
|---|---|
| `kuhwatch/*` | Repo kuhwatch (Branch je Session: `waechter/erkennungsvertrag`, `trainer/inventur`) |
| `Die_Stallwache/*` | Repo Die_Stallwache (Branches `bauleiter/lagebericht`, `spaeher/radar-2`) |
| `01_BESCHLUSSVORLAGEN_B15-B17.md` | Entscheidung → Eintrag in `ENTSCHEIDUNGEN.md` (Dirigent) |

Wächter und Trainer arbeiten im selben Repo, aber in getrennten Verzeichnissen und Branches.
Eine Rolle je Session.

## Reihenfolge

0. **B15–B17 entscheiden** (Vorlagen in `01_…`). Ohne B15 kein Labelstart.
1. Dateien in die Branches einchecken.
2. Je Session: Plan-Modus-Prompt → Plan prüfen und freigeben → Plan-Modus verlassen → Goal-Vertrag mit `/goal` starten.
3. Diff lesen, qa-waechter, Merge.

## Betreiber-Aktionen (Mensch, nicht delegierbar)

- [ ] B15–B17 entscheiden
- [ ] `REPORT_READ_TOKEN` erzeugen (z. B. `openssl rand -hex 32`), in Vercel (Production) und als Secret der Report-Routine hinterlegen — nie in Prompt oder Repo
- [ ] PR #70 deployen, falls die Plan-Antwort des Bauleiters zeigt, dass `/api/events` nach Firestore schreibt
- [ ] Report-Routine um den Abschnitt unten ergänzen
- [ ] Nach dem Trainer-Goal: CVAT-Pilot mit 10 Bildern (Schritte in `kuhwatch/GOAL_BRIEF_trainer.md`)

### Ergänzung für den Prompt der Tagesreport-Routine

```
Vor Punkt 2 und 3: GET $LAGEBERICHT_URL?stunden=12 mit Header x-report-token: $REPORT_READ_TOKEN.
200 → Punkt 2 aus zaehler (kalbeverdacht, austreibung, brunstverdacht) und passenden letzte_ereignisse;
      Punkt 3 aus info-Ereignissen und letztes_lebenszeichen (Kamera ohne Lebenszeichen > 24 h nennen).
503 → den Body wörtlich als Einschränkung berichten. Keine Werte ohne erfolgreichen Abruf.
Punkt 4 zusätzlich: Abschnitt „Datensatz (Silent Mode)" aus docs/metriken.md zitieren, sobald vorhanden.
```

---

## Session A — Wächter (kuhwatch): Edge-Erkennungslogik

**Plan-Modus-Prompt**

```
Plan-Modus, keine Logik schreiben. Lies GOAL_BRIEF_waechter.md und docs/erkennungsvertrag.md.
Beantworte die sechs Plan-Fragen aus dem Brief mit Dateipfaden und Belegen (Code-Stellen,
gemessene Werte). Schlage danach die Modulstruktur vor: Ort von erkennung/, Adapter
Modellausgabe → Frame, ersetzte Stellen, Integrationstests I0–I6. Warte auf Freigabe.
```

**Goal-Vertrag**

```
**Objective:** Die Edge-Erkennung in kuhwatch erfüllt den Erkennungsvertrag v1 (docs/erkennungsvertrag.md) gemäß freigegebenem Plan.
**Read first:** GOAL_BRIEF_waechter.md, docs/erkennungsvertrag.md, erkennung/, tests/test_erkennungsvertrag.py, tests/test_vertrag_konsistenz.py, freigegebener Plan
**Constraints:** Schwellen nur aus der Konfig, Werte nur gemäß B15–B17; Austreibung und Eskalation nie hinter Sperre, Fenster oder Kuh-Erkennung; kein Video- oder Frame-Upload (B7); keine neuen Abhängigkeiten; ENTSCHEIDUNGEN.md nicht anfassen; keine Tests löschen, überspringen, abschwächen und keine Schwellen ändern, um grün zu werden (einzige Ausnahme: Import-Zeile laut Plan); nur im Plan genannte Dateien ändern, kein Refactoring daneben
**Validate:** `pytest -q` (gesamte Suite) nach jeder Änderung
**Document:** Dokumentiere jede Änderung knapp und gezielt — neue .md-Dateien anlegen oder bestehende Doku aktualisieren (Abschnitt „Umsetzung" in docs/erkennungsvertrag.md); am Ende 1–3 Zeilen „Grenzen dieser Session" an CLAUDE.md anhängen.
**Checkpoints:** ein Checkpoint je Vertragspunkt (V0–V7, danach I0–I6); Fortschritt kurz loggen
**Stop when:** gesamte Suite inkl. I0–I6 grün und PR mit Prüfbericht offen (Merge erst nach qa-waechter), ODER derselbe Test drei Läufe in Folge rot (Spezifikation melden, Test nicht ändern), ODER Code müsste zwischen Repos verschoben werden — dann pausieren und fragen
```

## Session B — Trainer (kuhwatch): Tagesreport-Punkt 4

**Plan-Modus-Prompt**

```
Plan-Modus, keine Logik. Lies GOAL_BRIEF_trainer.md. Beantworte die fünf Plan-Fragen mit Pfaden
und drei echten Dateinamen aus dem Silent-Mode-Ordner. Schlage vor, wie die Inventur auf die
echten Aufnahmen zugreift — nur lesend. Warte auf Freigabe.
```

**Goal-Vertrag**

```
**Objective:** Punkt 4 des Tagesreports wird messbar: tools/datensatz_inventur.py liefert aus den echten Silent-Mode-Aufnahmen den Abschnitt „Datensatz (Silent Mode)" für docs/metriken.md.
**Read first:** GOAL_BRIEF_trainer.md, tools/datensatz_inventur.py, tests/test_datensatz_inventur.py, tests/test_vertrag_konsistenz.py, training/, .env.example, freigegebener Plan
**Constraints:** nur lesen — keine Bilder verschieben, löschen, umbenennen oder hochladen; Label-Vertrag unverändert (kuh mit spine_end, tail_base, tail_tip in dieser Reihenfolge; amniotic_sac; calf_legs; keine Klasse „kalbt"); Split nur nach Stall-Tagen; Schwellen nur mit Stichprobenbeleg ändern; keine neuen Abhängigkeiten; keine Tests abschwächen
**Validate:** `pytest -q tests/test_datensatz_inventur.py tests/test_vertrag_konsistenz.py`, danach `python tools/datensatz_inventur.py <aufnahmen-pfad> --md metriken-datensatz.md --json inventur.json`
**Document:** Dokumentiere jede Änderung knapp und gezielt — neue .md-Dateien anlegen oder bestehende Doku aktualisieren; am Ende 1–3 Zeilen „Grenzen dieser Session" an CLAUDE.md anhängen.
**Checkpoints:** Checkpoints: echtes Dateinamensmuster als Testfall → Lauf auf echten Aufnahmen → Stichprobe Lichtphasen → Prüfbericht; Fortschritt kurz loggen
**Stop when:** Tests grün inkl. neuem Testfall mit echtem Dateinamensmuster, Inventur auf echten Aufnahmen gelaufen und PR mit Prüfbericht (einzigartige Bilder, B9-Status, Stall-Tage, Split) offen, ODER die Aufnahmen sind aus dieser Session nicht lesbar — dann den Befehl für den Betreiber ausgeben und anhalten
```

## Session C — Bauleiter (Die_Stallwache): Tagesreport-Punkte 2 und 3

**Plan-Modus-Prompt**

```
Plan-Modus, keine Logik. Lies GOAL_BRIEF_bauleiter.md, docs/lagebericht-vertrag.md, die Route
/api/events und PR #70. Beantworte die sechs Plan-Fragen mit Pfaden. Schlage die Dateistruktur
der neuen Route und den Testansatz für die beiden 503-Fälle vor. Warte auf Freigabe.
```

**Goal-Vertrag**

```
**Objective:** Tagesreport-Punkte 2 und 3 erhalten eine lesbare Quelle: GET /api/lagebericht gemäß docs/lagebericht-vertrag.md.
**Read first:** GOAL_BRIEF_bauleiter.md, docs/lagebericht-vertrag.md, scripts/smoke-lagebericht.sh, Route /api/events, docs/roadmap.md, freigegebener Plan
**Constraints:** Ingest-Vertrag /api/events unverändert (201/401/400/503); Datenquelle ist die Persistenz, in die /api/events heute schreibt — keine zweite; eigener Lese-Token REPORT_READ_TOKEN, Vergleich in konstanter Zeit; keine Bilder, Keypoints oder Rohdaten in der Antwort; Cache-Control: no-store; keine neuen Pakete oder Dienste (B8); keine Secrets im Repo; Smoke nie gegen Production; keine Tests abschwächen
**Validate:** `npm run build` und `bash scripts/smoke-lagebericht.sh` gegen `npm run dev` nach jeder Änderung
**Document:** Dokumentiere jede Änderung knapp und gezielt — neue .md-Dateien anlegen oder bestehende Doku aktualisieren (Abschnitt „Umsetzung" in docs/lagebericht-vertrag.md, docs/roadmap.md); am Ende 1–3 Zeilen „Grenzen dieser Session" an CLAUDE.md anhängen.
**Checkpoints:** Checkpoints: Route + 401/400 → 200-Body → 503-Unit-Tests → Smoke grün; Fortschritt kurz loggen
**Stop when:** Build und Smoke grün, 503-Fälle als Unit-Test grün, PR mit Prüfbericht offen (Merge erst nach qa-waechter), ODER die Persistenz von /api/events ist nicht auffindbar oder nicht lesbar — dann anhalten und berichten
```

## Session D — Späher (Die_Stallwache): Radar #2

Kein Plan-Modus nötig (keine Code-Struktur). Alternativ kann der Radar auch direkt im
Claude-Chat laufen — er braucht nur Websuche, kein Repo.

**Goal-Vertrag**

```
**Objective:** Radar #2 (fällig 10/2026) als Abschnitt in docs/wettbewerbsanalyse.md nach Skill wettbewerbs-radar, mit den Evidenzfragen F1–F3 zur Erkennungslogik.
**Read first:** GOAL_BRIEF_spaeher.md, Skill wettbewerbs-radar, Radar #1 (Stand 14.07.2026), tools/radar_check.py (Format: --selbsttest)
**Constraints:** nur Deltas seit 14.07.2026, jede Zeile mit Quelle und Datum; Suche auf Deutsch und Englisch; Prinzipien-Filter auf jede Idee; nur Vorschläge — ENTSCHEIDUNGEN.md nicht anfassen; keine Konten, Käufe, Formulare, Abos; nicht frei zugängliche Quellen als solche vermerken, nicht umgehen; keine Aussage ohne Quelle
**Validate:** `python tools/radar_check.py docs/wettbewerbsanalyse.md`
**Document:** Dokumentiere jede Änderung knapp und gezielt — neue .md-Dateien anlegen oder bestehende Doku aktualisieren.
**Checkpoints:** je ein Checkpoint für Kamera-KI, Tier-Sensorik, Rand, F1, F2, F3, Beschlussvorschläge; Fortschritt kurz loggen
**Stop when:** radar_check meldet „ok" und der PR mit dem Abschnitt ist offen
```
