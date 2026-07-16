---
name: fehlalarm-triage
description: Branchenweit einzigartige Feedback-Schleife der KI-Wache — Telegram-Alarme als Treffer/Fehlalarm triagieren, Fehlalarm-Frames als Hard Negatives in den Trainingsordner überführen, Retraining-Zeitpunkt entscheiden und den Nordstern „<1 Fehlalarm/Nacht" in docs/metriken.md fortschreiben. Nutzen im Analyse-Modus bei jedem Fehlalarm-Review und vor jedem Nachtraining.
---

# Fehlalarm-Triage & Feedback-Schleife

Kein Wettbewerber (SaaS oder DIY) lässt den Landwirt das Modell verbessern —
Stallblick besitzt als einziges System die offene Kette
**Kamera → Modell → Training** und macht daraus eine Schleife. Diese Prozedur
verwandelt jeden Fehlalarm in Trainingsmaterial statt in Frust.

Voraussetzung: Analyse-Modus läuft (`best.pt` gesetzt, siehe Skill
`modell-training`); Alarme kommen mit 4-Frame-Bildserie per Telegram.

## 1. Triage am Handy (Landwirt, Sekunden pro Alarm)

Jeden Alarm anhand des Telegram-Albums einordnen:

| Urteil | Kriterium | Aktion |
| --- | --- | --- |
| **Treffer** | Verhalten real (Wehen/Aufsprung/Fruchtblase sichtbar) | nichts — zählt als Erfolg |
| **Fehlalarm** | Alltag fehlgedeutet (Koten, Fliegen, Spielverhalten, Lichtreflex) | **ein Tipp auf ❌ Fehlalarm** unter dem Alarm — die unannotierte Bildserie landet automatisch in `telegram.fehlalarm_ordner` (Default `aufnahmen/fehlalarme/JJJJ-MM-TT/`) |
| **Unklar** | Aus Bildern nicht entscheidbar | keinen Button drücken; Bilder manuell nach `unklar/` sichern — nicht als Negativ trainieren |

Die Buttons sind gebaut (`FeedbackSchleife` in `edge-agent/main.py`,
`telegram.feedback_buttons`): ✅/❌ unter jedem Alarm, Urteile erscheinen im
Tagesbericht. Manuelles Sichern ist nur noch der Fallback (z. B. wenn die
Buttons älterer Alarme abgelaufen sind — nur die letzten 20 bleiben
abstimmbar).

## 2. Buchführung (Orchestrator, wöchentlich)

- Fehlalarme pro Nacht zählen → Verlauf in `docs/metriken.md` eintragen
  (Nordstern: **< 1 Fehlalarm/Nacht** im eingeschwungenen Zustand).
- Muster erkennen: Häufen sich Fehlalarme zu einer Uhrzeit (IR-Umschaltung?),
  bei einer Kamera, bei einem Typ? Muster → gezielte Negativ-Sammlung.
- NIEMALS als Abkürzung die Referenz-Schwellenwerte lockern
  (45°/30 min/20 %, 0.80, IoU 0.15/≥4 s) — Wächter ist der Agent `ki-wache`;
  Schwellen-Drehen maskiert Modellschwächen statt sie zu beheben.

## 3. Retraining-Entscheidung

Nachtrainieren (Skill `modell-training`, Phase 5), wenn EINE Bedingung erfüllt:

- ≥ 30 verwertbare Fehlalarm-Frames gesammelt, ODER
- > 2 Fehlalarme/Nacht über eine Woche, ODER
- ein systematisches Muster (z. B. immer bei IR-Nacht) erklärbar und belegbar.

Ablauf: Fehlalarm-Frames in CVAT als „Background"/Negativ labeln → Datensatz
erweitern → Colab-Training → neues `best.pt` → 48 h beobachten →
`docs/metriken.md` aktualisieren.

## 4. Sonderfall Austreibung

Fehlalarme vom Typ `austreibung` werden trotzdem gesammelt, aber der
Override-Mechanismus (Konfidenz > 0.80 → Sofort-Alarm) bleibt unangetastet:
**Recall 100 % bei der Austreibung hat Vorrang** — lieber ein Fehlalarm mehr
als eine verpasste Kalbung. Reduktion nur über besseres Modell, nie über
Unterdrückung.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Triage am Handy | Landwirt |
| Wochenauswertung, Muster, Metriken | Orchestrator |
| Schwellenwert-Treue bewachen | Agent `ki-wache` |
| Retraining ausführen | Landwirt + Skill `modell-training` |
