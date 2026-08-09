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
| **Fachexperte** | Agent `ki-wache` | Erkennungslogik prüfen/erklären, Logik-Simulationen, Alarm-Texte formulieren | Dateien ändern, Schwellenwerte lockern |

Skills sind keine Agenten, sondern **Prozeduren**, die der Orchestrator (oder
ein Agent) aufruft. Sie zerfallen in drei Gruppen:

| Gruppe | Skills | Wofür |
| --- | --- | --- |
| **Scharfschalten** (einmalig je Baustein) | `stallwache-live-schalten`, `persistenz-live-schalten`, `push-live-schalten`, `tuya-futterwache`, `modell-training` | Einen fertig gebauten, aber schlafenden Baustein in Betrieb nehmen — und den Betrieb **beweisen**, nicht nur konfigurieren |
| **Prüfen & Ausliefern** | `stallblick-deploy`, `ki-wache-smoketest`, `pwa-abnahme`, `security-sweep` | Vor und nach jeder Auslieferung |
| **Betrieb & Störung** | `tuya-diagnose`, `fehlalarm-triage`, `bytetrack-tuning`, `wettbewerbs-check` | Wenn im laufenden Betrieb etwas klemmt oder nachgeschärft wird |

Die Scharfschalt-Skills teilen ein Muster, das sich bewährt hat: Die App
**degradiert still**, wenn ein Baustein fehlt (kein Push, keine Persistenz,
kein Livebild — aber alles andere läuft weiter). Das ist im Betrieb richtig
und in der Abnahme gefährlich, weil „läuft" und „läuft halb" gleich aussehen.
Jeder dieser Skills endet deshalb mit einem Beweis am echten Gerät, nicht mit
einer gesetzten Variablen.

## Delegations-Entscheidung: Wann was?

```
Neue Aufgabe
├─ Marktfrage / "Konkurrenz" / Feature-Wahl   → Agent markt-analyst (+ Skill wettbewerbs-check)
├─ Vor Merge / Deploy / nach neuer Route       → Agent qa-waechter
├─ Erkennungslogik/Schwellenwerte betroffen    → Agent ki-wache (Treue-Befund vor Merge)
├─ Alarm-/Landwirt-Texte formulieren           → Agent ki-wache
├─ Sicherheitsrelevante Route geändert         → Skill security-sweep (ggf. via qa-waechter)
├─ Ausliefern                                  → Skill stallblick-deploy
├─ Ereignis-API/Dashboard geändert             → Skill ki-wache-smoketest
├─ Tuya-Zugangsdaten liegen vor                → Skill tuya-futterwache
├─ Tuya meldet "sign invalid"/"clientId"       → Skill tuya-diagnose
├─ Tunnel-Hostname gemeldet                    → Skill stallwache-live-schalten
├─ KV-Store verknüpft                          → Skill persistenz-live-schalten
├─ Firebase eingerichtet / Push fehlt          → Skill push-live-schalten
├─ sw.js, Offline-Puffer, Manifest, Tabs       → Skill pwa-abnahme
├─ Bridge läuft, Modell fehlt                  → Skill modell-training
├─ Analyse-Modus läuft, Fehlalarme kommen      → Skill fehlalarm-triage
└─ ID-Wechsel / Alarme bleiben aus             → Skill bytetrack-tuning
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
5. **Nicht-destruktiv bleiben — Historie vorwärts bauen:** Nach einem
   Squash-Merge trägt der Feature-Branch veraltete Historie. Force-Push ist
   dafür der falsche Reflex und inzwischen ohnehin durch eine
   Repository-Regel gesperrt (`GH013: Cannot force-push to this branch`).
   Der saubere Weg, wenn der Branchname erhalten bleiben muss:

   ```bash
   git checkout -B <branch> origin/<branch>   # alte Remote-Historie
   git merge origin/main                      # Squash-Stand vorwärts holen
   git cherry-pick <neuer-commit>             # eigene Arbeit obendrauf
   git push origin <branch>                   # normaler Fast-Forward
   ```

   Der Merge ist inhaltlich ein No-Op (der Squash-Commit hat denselben Baum
   wie der Branch-Commit — mit `git diff <alt> <squash>` vorher belegen), und
   der PR zeigt danach exakt die neuen Dateien gegenüber `main`. Nur wenn der
   Name frei wählbar ist, bleibt ein frischer Branch die einfachere Variante.
6. **Spezifikations-Pipeline (für blockierte Ideen):** Marktbefund
   (`markt-analyst`) → Produktentscheidung (Orchestrator, dokumentiert in
   `wettbewerbsanalyse.md`/`roadmap.md`) → Fachspezifikation (`ki-wache`,
   Struktur: Grundsatz → ehrliche Grenzen → Regeln mit Zahlen → Config →
   fertige Texte → Abnahmekriterien → Risiken) → Code erst, wenn die
   Voraussetzung real ist. Blockierte Ideen werden spezifiziert statt halb
   gebaut (so entstanden Festliege #26, Brunst-Fusion #27, Kalbe-Akte #31,
   Lahmheit #32). Fällt der Fachagent aus (z. B. API-Überlastung), entwirft
   der Orchestrator nach dessen Mandat und vermerkt die Provenienz.

## Leitplanken für jede Delegation

- Subagenten bekommen einen **präzisen, abgeschlossenen Auftrag** mit
  Erfolgskriterien und dem klaren Verbot, außerhalb ihres Mandats zu handeln
  (Rechercheur ändert nichts, Prüfer committet nichts).
- Jede Delegation nennt die **relevanten Dateien/Pfade**, damit der Agent nicht
  kalt suchen muss.
- Der Orchestrator hält die **Produktprinzipien** (`docs/vision.md`) hoch:
  kamerabasiert, Edge-First, 0 €/Kuh/Jahr, „Ruhe vor Fülle". Kein Agent
  erweitert den Scope eigenmächtig.
- **Tierart-Neutralität wahren:** Im Edge-Agenten keine Rind-Hardcodierung
  neu einführen (Klassen, Keypoints, Schwellen bleiben Konfiguration) —
  hält die dokumentierte Zweitmarkt-Option Abfohlen offen, kostet nichts.

## Reifegrad-Regel

Bei einem reifen Codestand ist **Härtung/Vereinfachung wertvoller als neue
Features**. Idle-Zeit → `security-sweep` oder ein Bug-Hunt-Pass, nicht noch
eine Feature-Runde. Drei „nichts zu tun"-Durchläufe = zurückfahren auf einen
kurzen Statuscheck.
