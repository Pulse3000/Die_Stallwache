# AUFTRAG an Späher — Radar #2 (fällig 10/2026), Schwerpunkt Erkennungslogik

**Ziel:** Abschnitt „Radar #2 — <Datum>" in `docs/wettbewerbsanalyse.md` nach Skill
`wettbewerbs-radar`, ergänzt um den Pflichtabschnitt „Evidenz Erkennungslogik";
`python tools/radar_check.py docs/wettbewerbsanalyse.md` meldet „ok".

**Kontext (zuerst lesen):** Skill `wettbewerbs-radar` · Radar #1 (Stand 14.07.2026) ·
`docs/roadmap.md` · Beschlüsse B1–B17 · `tools/radar_check.py` (`--selbsttest` zeigt das Format)

## Evidenzfragen (Pflicht, je eine Tabellenzeile F1–F3)

| ID | Frage | Wofür |
|---|---|---|
| F1 | Schwanzheben vor der Kalbung: Häufigkeit, Dauer, Zeitanteil in den letzten 2–6 h; wie hoch wird der Schwanz gehalten (über die Waagrechte?) | B16 (Dominanz-Anteil) und die Messgrenze bei > ~41° über der Waagrechten |
| F2 | Frei nutzbare Bild-/Videodatensätze mit Fruchtblase oder Kälberfüßen, mit Lizenz | Trainer: Beimischung für seltene Klassen (nie Hauptquelle) |
| F3 | Veröffentlichte Erkennungsraten kamerabasierter Kalbe-/Austreibungserkennung, mit Nacht/IR-Anteil | Realismus des Abnahme-Gates „Recall 1.0" |

Antwort je Frage: Befund + Quelle + Datum — oder ausdrücklich „keine belastbare Quelle gefunden".

## Markt-Schwerpunkte

Lely Zeta (Preise nach NL-Start) · Lency CalvAlert (EU-Verfügbarkeit) · neue Edge-Kamera-Startups ·
Ankündigungen zur EuroTier 2026

## Definition of Done

- [ ] `radar_check` meldet „ok" (Pflichtabschnitte, Beobachtungsliste vollständig, Daten, F1–F3, Einstufungen)
- [ ] je Delta Quelle mit Datum; je Anbieter Suche auf Deutsch und Englisch
- [ ] jede Idee durch den Prinzipien-Filter; bei REJECT steht das verletzte Prinzip in der Begründung
- [ ] nicht frei zugängliche Quellen als „nicht frei zugänglich" vermerkt
- [ ] PR mit dem Abschnitt offen

## Verbote

- `ENTSCHEIDUNGEN.md` bearbeiten — der Späher liefert Vorschläge, keine Einträge
- Konten anlegen, kaufen, Formulare absenden, Newsletter abonnieren, Bezahlschranken umgehen
- Aussagen ohne Quelle; Preise ohne Datum

**Rückgabe:** PR-Link und die Beschlussvorschläge als Liste für den Dirigenten.
