---
name: spezifikation-umsetzen
description: Führt eine der implementierungsreifen Spezifikationen aus docs/ in gemergten Code über — Voraussetzung prüfen, Umfang auf den unblockierten Teil schneiden, Tests zuerst aus der Abnahmetabelle, Config und Doku mitziehen, Roadmap-Status nachführen. Nutzen bei "Festliege/Brunst-Fusion/Kalbe-Akte/Lahmheit/Eskalation umsetzen", "der Blocker ist weg", "wir haben jetzt ein Modell" oder wenn eine Spezifikation von 🔄 auf ✅ soll.
---

# Spezifikation in Code überführen

Im Repo liegen fünf implementierungsreife Spezifikationen. Sie sind bewusst
**vor** dem Code entstanden (Muster 6 in `docs/agenten-orchestrierung.md`:
blockierte Ideen werden spezifiziert statt halb gebaut). Diese Prozedur ist der
Rückweg: von der Spezifikation zu gemergtem, verifiziertem Code — ohne dass
unterwegs Zahlen, Grenzen oder Risiken verloren gehen.

**Der häufigste Fehler ist nicht ein Bug, sondern stillschweigende
Umfangserweiterung:** Die Spezifikation beschreibt den Endzustand, die
Voraussetzung ist aber nur zur Hälfte erfüllt. Dann entsteht Code, der auf ein
Modell wartet, das es nicht gibt — halb gebaut, genau das, was die
Spezifikations-Pipeline verhindern sollte.

## Schritt 0 — Welche Spezifikation, welcher Teil ist frei?

| Spezifikation | Voraussetzung | Was **ohne** sie umsetzbar ist |
| --- | --- | --- |
| [`eskalationskette-spezifikation.md`](../../docs/eskalationskette-spezifikation.md) | KV-Store verknüpft (Roadmap P1); Weckton zusätzlich: MQTT-Broker + Weckgerät **im Haus** | **Stufen 1–2 komplett** (Wiederholung, zweiter Empfänger, Zustandsdatei, Quittierungsabfrage) — modellunabhängig. `weckruf.aktiv: false` bleibt, bis §9 der Spec abgearbeitet ist |
| [`festliege-spezifikation.md`](../../docs/festliege-spezifikation.md) | erstes `best.pt`; Seitenlage zusätzlich: Klasse `kuh_seitenlage` im 2. Training | Klassengerüst `FestliegeWaechter` mit injizierbarem `jetzt` + Logiktests (Geometrie stubbar) |
| [`brunst-fusion-spezifikation.md`](../../docs/brunst-fusion-spezifikation.md) | Modell + zwei Kameras auf dieselbe Bucht + Broker | MQTT-Peer-Topologie und Zeit-Koinzidenz sind ohne Modell testbar |
| [`kalbe-akte-spezifikation.md`](../../docs/kalbe-akte-spezifikation.md) | Modell (Teil-Akte); 2. Training (Voll-Akte) | Akten-Format und stille Zustellung |
| [`lahmheit-spezifikation.md`](../../docs/lahmheit-spezifikation.md) | Keypoint `spine_mid` im 2. Training + eigene Validierung | nichts Sinnvolles — bewusst warten |

Steht die Voraussetzung **nicht**: Umfang auf die freie Spalte schneiden,
Feature per Default `aktiv: false` ausliefern und das im Commit sagen. Nie den
Rest „vorbauen".

## Schritt 1 — Die Spezifikation vollständig lesen, nicht überfliegen

Jede dieser Dateien enthält mindestens einen Abschnitt „ehrliche Grenze" oder
„Risiken", der eine naheliegende Implementierung **ausschließt**. Beispiele, die
schon Code verhindert haben:

- Festliege: Brustlage vs. Seitenlage ist aus Box + Topline **nicht** trennbar
  → Geometrie nur für die Zeitregel, Seitenlage ausschließlich als Objektklasse.
- Eskalation: `info` eskaliert nie — **hart im Code**, nicht als Config-Default,
  sonst weckt jeder nächtliche WLAN-Ausfall das Haus.
- Eskalation: `retain: false` auf dem MQTT-`set`-Topic; eine retained
  „an"-Nachricht ist der Ton, den niemand stoppen kann.

Wer diese Absätze überspringt, baut den Fehler ein, den die Spezifikation
bereits gefunden hat.

## Schritt 2 — Tests vor Code, direkt aus der Abnahmetabelle

Jede Spezifikation hat einen Abschnitt „Abnahmekriterien" bzw.
„Verifikationsplan". Der **Offline-Logikteil** davon ist die Testdatei — 1:1,
in derselben Reihenfolge, mit denselben Zahlen.

```bash
# Muster: edge-agent/tests/hilfe.py + injiziertes `jetzt`, pures Python
python3 edge-agent/tests/alle_tests.py
```

Regeln, die sich bewährt haben:

- **Injizierbares `jetzt`** in jeder zeitbasierten Klasse (Vorbild
  `TotmannWaechter`). Ohne das ist eine 50-Minuten-Kette nicht testbar.
- **Kein `sleep` in Tests.** Zeit wird gesetzt, nicht abgewartet.
- Die Testdatei in `edge-agent/tests/alle_tests.py` eintragen, sonst läuft sie
  im `qa-waechter`-Durchgang (Prüfpunkt 7) nicht mit.
- Praxis-Abnahmen (Hörprobe, Nacht-Nullprobe, Kamerawinkel) kann keine Suite
  ersetzen — sie gehören als offener Punkt in den PR, nicht als „grün".

## Schritt 3 — Code, Config und Texte gemeinsam

Eine Spezifikation ist erst umgesetzt, wenn alle vier Teile da sind:

| Teil | Wohin | Fallstrick |
| --- | --- | --- |
| **Logik** | eigene Klasse in `edge-agent/main.py`, offline testbar | keine Kamera-/Netz-Abhängigkeit im Entscheidungsteil |
| **Config** | Block aus der Spec nach `edge-agent/config.example.yaml` | Kommentare **ASCII** (ae/oe/ue), Default `aktiv: false`, Zeiten in Minuten |
| **Texte** | die fertigen Alarmtexte aus der Spec, wörtlich | nicht umformulieren — sie sind vom `ki-wache` auf Modell-Evidenz geprüft |
| **Ereignistyp** | nur falls die Spec einen **neuen** verlangt | dann zwingend `lib/ereignis-modell.ts` **und** `app/api/events/route.ts`, sonst antwortet das Dashboard 400 und nur Telegram funktioniert |

Neue App-Route dabei? Dann prüfen, ob sie eine Ausnahme in `middleware.ts`
braucht (Token statt Session) — und die Ausnahme so eng wie möglich fassen.

## Schritt 4 — Verifizieren

1. Agent `qa-waechter` (voller Durchgang) — er kennt die Ingest-Auth-Kette, die
   Allowlist-Gegenprobe und die PWA-Auslieferung.
2. Agent `ki-wache` **zusätzlich**, wenn Erkennungslogik, Schwellenwerte oder
   Alarmtexte berührt sind: „Bildet der Code die Spezifikation treu ab, und wo
   nicht?" Ausdrücklich um Widerspruch bitten — er hat schon Entscheidungen
   korrigiert (das Weckgerät gehört ins Haus, nicht in den Stall).
3. Bei sicherheitsrelevanten Routen zusätzlich Skill `security-sweep`.

## Schritt 5 — Doku nachführen (gehört in denselben Commit)

- `docs/roadmap.md`: Eintrag 🔒/⏳/🔄 → ✅ **nur für den wirklich gebauten
  Teil**; der Rest bleibt mit benanntem Blocker stehen.
- Die Spezifikationsdatei selbst: Statuszeile oben aktualisieren
  („spezifiziert" → „umgesetzt, Stufen 1–2"). Die Spec wird **nicht** gelöscht —
  sie ist die Begründung der Zahlen im Code.
- `docs/agenten-orchestrierung.md`: Delegationsbaum ergänzen, falls ein neuer
  Störungsfall entstanden ist.
- Abweichungen von der Spezifikation **explizit im Commit benennen** samt
  Grund. Eine stille Abweichung macht die Spec zur Lüge.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Umfang schneiden, Code schreiben, committen | Orchestrator |
| Treue-Befund gegen die Spezifikation | Agent `ki-wache` |
| Build/Tests/Smoke vor dem Merge | Agent `qa-waechter` |
| Praxis-Abnahmen (Hörprobe, Nachtprobe, Kamerawinkel) | Betreiber — im PR als offener Punkt führen |
