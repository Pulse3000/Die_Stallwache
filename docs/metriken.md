# Erkennungs-Metriken (öffentlich)

Kommerzielle Systeme verkaufen Vertrauen über Peer-Review-Studien (CattleEye,
CowFIT). Der Open-Source-Gegenzug von Stallblick: **Wir veröffentlichen unsere
eigenen Erkennungsraten** — auf echten Clips aus dem eigenen Stall, mit
nachvollziehbarer Methodik. Blackbox-Abos können das nicht.

> Status: **Vorlage** — wird nach der ersten Trainingsrunde
> (Silent Mode → CVAT → Colab, siehe `edge-agent/README.md`) erstmals gefüllt.

## Methodik

1. **Testset:** Mindestens 30 annotierte Clips (à 1–5 min) aus dem eigenen
   Stall, die NICHT im Training waren; alle Lichtverhältnisse (Tag, Dämmerung,
   IR-Nacht) vertreten. Ereignis-Clips (Kalbung/Aufsprung) und ereignisfreie
   Clips (inkl. bekannter Fehlalarm-Quellen: Koten, Fliegenabwehr, Schatten).
2. **Auswertung:** Edge-Agent im Analyse-Modus über die Clips laufen lassen
   (`stream.url` auf Datei setzen — OpenCV liest auch Videodateien);
   ausgelöste Alarme gegen die Annotation halten.
3. **Ereignis-Ebene, nicht Frame-Ebene:** Ein Kalbeverdachts-Alarm zählt als
   Treffer, wenn er innerhalb des annotierten Ereignisfensters liegt.
4. **Jede Zeile mit Modellversion und Datum** — Verläufe zeigen, ob
   Nachtraining wirkt.

## Ergebnisse

| Datum | Modell | Ereignis | Fusion | Testclips | Precision | Recall | Fehlalarme/Nacht | Bemerkung |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| _tbd_ | best-v1 | Kalbeverdacht (Schwanzwinkel) | – | – | – | – | – | nach 1. Training |
| _tbd_ | best-v1 | Austreibung (Fruchtblase/Füße) | – | – | – | – | – | |
| _tbd_ | best-v1 | Brunstverdacht (Aufsprung) | aus | – | – | – | – | Baseline solo |
| _tbd_ | best-v1 | Brunstverdacht (Aufsprung) | plausibilisieren | – | – | – | – | Abnahme Brunst-Fusion: ≥ 50 % weniger Fehlalarme bei gehaltenem Recall ([Spez](./brunst-fusion-spezifikation.md) § 6) |

Die Spalte **Fusion** gilt nur für Brunstverdacht
(`aus | annotieren | plausibilisieren`, siehe
[`brunst-fusion-spezifikation.md`](./brunst-fusion-spezifikation.md));
für alle anderen Ereignisse steht dort „–". Der `plausibilisieren`-Modus
darf erst scharfgeschaltet werden, wenn seine Zeile die Halbierung belegt.

**Zielwerte** (aus `docs/vision.md`): Recall Austreibung → 100 % („keine
verpasste Kalbung"), Fehlalarme < 1/Nacht im eingeschwungenen Zustand.
Feature-spezifische Zielwerte: Lahmheit-Nullprobe und Festliege-Nacht-
Nullprobe stehen in den jeweiligen Spezifikationen.

## Definitionen

- **Precision** = erkannte echte Ereignisse / alle Alarme (wie oft hat der
  Alarm recht?)
- **Recall** = erkannte echte Ereignisse / alle echten Ereignisse (wie viel
  verpasst das System?)
- **Fehlalarme/Nacht** = Alarme ohne echtes Ereignis pro 12-h-Nachtfenster,
  gemessen über mindestens 7 Nächte
