# Agenten-Orchestrierung & Skill-Playbook

Wie die spezialisierten Agenten und Skills von Stallblick zusammenspielen —
das Betriebshandbuch für die autonome Weiterentwicklung. Prinzip: **Der
Hauptagent orchestriert und entscheidet; Subagenten recherchieren und prüfen;
Skills kapseln wiederkehrende Abläufe.**

## Rollen

| Rolle | Wer | Darf | Darf nicht |
| --- | --- | --- | --- |
| **Orchestrator** | Hauptagent (diese Session) | delegieren, entscheiden, committen, mergen | Prüfergebnisse blind übernehmen |
| **Rechercheur** | Agent `markt-analyst` | WebSearch, lesen, Bericht liefern | Dateien ändern |
| **Prüfer** | Agent `qa-waechter` | Build/Tests/Smoke ausführen, Befund liefern | committen/pushen, Fixes anwenden |

Skills sind keine Agenten, sondern **Prozeduren**, die der Orchestrator (oder
ein Agent) aufruft: `stallblick-deploy`, `ki-wache-smoketest`,
`wettbewerbs-check`, `tuya-futterwache`, `security-sweep`.

## Delegations-Entscheidung: Wann was?

```
Neue Aufgabe
├─ Marktfrage / "Konkurrenz" / Feature-Wahl   → Agent markt-analyst (+ Skill wettbewerbs-check)
├─ Vor Merge / Deploy / nach neuer Route       → Agent qa-waechter
├─ Sicherheitsrelevante Route geändert         → Skill security-sweep (ggf. via qa-waechter)
├─ Ausliefern                                  → Skill stallblick-deploy
├─ Ereignis-API/Dashboard geändert             → Skill ki-wache-smoketest
└─ Tuya-Zugangsdaten liegen vor                → Skill tuya-futterwache
```

## Koordinationsmuster (bewährt in dieser Session)

1. **Parallelisieren:** Rechercheur/Prüfer im Hintergrund starten, während der
   Orchestrator am Code weiterarbeitet. Nicht auf einen Agenten warten, wenn
   die nächste Aufgabe unabhängig ist.
2. **Einarbeiten statt Durchreichen:** Agentenberichte sind Input, keine
   Wahrheit. Der Orchestrator prüft Plausibilität, wählt aus und schreibt das
   Ergebnis selbst in `docs/` bzw. Code — der `markt-analyst` liefert z. B.
   fertige Tabellenzeilen, eingebaut werden sie vom Orchestrator.
3. **Entscheidung vor Code:** Produktentscheidungen landen zuerst in
   `docs/wettbewerbsanalyse.md` (Was/Warum) und `docs/roadmap.md` (Status);
   Code folgt der Entscheidung, nie umgekehrt.
4. **Verifizieren vor Merge:** Kein Merge ohne grünen `qa-waechter`-Befund
   bzw. lokal grüne Build-/Smoke-/Sicherheits-Suite. Reine Sicherheits-Fixes
   dürfen im Selbst-Review-Modus direkt gemergt werden.
5. **Nicht-destruktiv bleiben:** Nach einem Squash-Merge trägt der Feature-
   Branch veraltete Historie — statt Force-Push einen **neuen Branch** vom
   frischen `main` aufmachen (so geschehen bei PR #9/#10).

## Leitplanken für jede Delegation

- Subagenten bekommen einen **präzisen, abgeschlossenen Auftrag** mit
  Erfolgskriterien und dem klaren Verbot, außerhalb ihres Mandats zu handeln
  (Rechercheur ändert nichts, Prüfer committet nichts).
- Jede Delegation nennt die **relevanten Dateien/Pfade**, damit der Agent nicht
  kalt suchen muss.
- Der Orchestrator hält die **Produktprinzipien** (`docs/vision.md`) hoch:
  kamerabasiert, Edge-First, 0 €/Kuh/Jahr, „Ruhe vor Fülle". Kein Agent
  erweitert den Scope eigenmächtig.

## Reifegrad-Regel

Bei einem reifen Codestand ist **Härtung/Vereinfachung wertvoller als neue
Features**. Idle-Zeit → `security-sweep` oder ein Bug-Hunt-Pass, nicht noch
eine Feature-Runde. Drei „nichts zu tun"-Durchläufe = zurückfahren auf einen
kurzen Statuscheck.
