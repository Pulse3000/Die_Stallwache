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

| Datum | Modell | Ereignis | Testclips | Precision | Recall | Fehlalarme/Nacht | Bemerkung |
| --- | --- | --- | --- | --- | --- | --- | --- |
| _tbd_ | best-v1 | Kalbeverdacht (Schwanzwinkel) | – | – | – | – | nach 1. Training |
| _tbd_ | best-v1 | Austreibung (Fruchtblase/Füße) | – | – | – | – | |
| _tbd_ | best-v1 | Brunstverdacht (Aufsprung) | – | – | – | – | |

**Zielwerte** (aus `docs/vision.md`): Recall Austreibung → 100 % („keine
verpasste Kalbung"), Fehlalarme < 1/Nacht im eingeschwungenen Zustand.

## Definitionen

- **Precision** = erkannte echte Ereignisse / alle Alarme (wie oft hat der
  Alarm recht?)
- **Recall** = erkannte echte Ereignisse / alle echten Ereignisse (wie viel
  verpasst das System?)
- **Fehlalarme/Nacht** = Alarme ohne echtes Ereignis pro 12-h-Nachtfenster,
  gemessen über mindestens 7 Nächte
