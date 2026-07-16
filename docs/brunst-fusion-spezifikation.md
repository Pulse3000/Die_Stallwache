# Spezifikation: Zwei-Kamera-Brunst-Fusion

Implementierungsreife Regeln für Roadmap P2 („Aufsprung nur melden, wenn von
der Zweitkamera plausibilisiert, falls beide dieselbe Bucht sehen";
Forschungsbasis: [`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md)
Abschnitt 2 Punkt 4). Entwurf: Agent `ki-wache` (16.07.2026), Entscheidung
und Übernahme: Orchestrator. **Status: spezifiziert — Umsetzung erst mit
erstem Modell UND wenn beide Kameras dieselbe Bucht sehen.**

## 0. Precision/Recall-Grundsatz

Brunst hat ein Zeitbudget von Stunden (Duldung 8–18 h) — ein verpasster
Aufsprung ist kein Notfall, ein Fehlalarm um 3 Uhr untergräbt das Vertrauen.
Deshalb: **Precision-first, aber ohne Recall-Bruch bei Einzelkamera-Sicht.**
Die Fusion ist eine entfernbare Schicht zwischen `LogicEngine` und
`Notifier` — sie ändert keinen Schwellenwert und keinen Timer und fällt im
Zweifel zugunsten des Recalls aus (**fail-open**). Der reale Default dieses
Betriebs (Stallwache = Abkalbebereich, Futterwache = Futtertisch, getrennte
Blickfelder) bleibt unangetastet: Fusion greift nur bei ausdrücklich
konfigurierter `gemeinsame_bucht: true`.

## 1. Topologie: Peer-Austausch über den vorhandenen MQTT-Ausgang

| Option | Bewertung |
| --- | --- |
| (a) Ein Prozess, zwei Streams | Deterministisch, aber zwingt beide Kameras auf eine Maschine = gemeinsame Ausfalldomäne; verletzt die Code-Invariante „ein Prozess = eine Kamera". **Verworfen.** |
| (c) Fusion serverseitig (Vercel-Ingest) | Nicht tragfähig: In-Memory-Store pro Serverless-Instanz (keine verlässliche Korrelation), und der Server sieht das Ereignis erst NACH dem Telegram-Versand — kann den primären Alarm nie zurückhalten. **Verworfen.** |
| **(b) MQTT-Peer-Austausch** | **Empfohlen.** Nutzt den vorhandenen MQTT-Ausgang, hält die Prozesse unabhängig (je Kamera eine Maschine), degradiert natürlich zu Solo. Preis: ein Mosquitto-Broker auf Bridge/Alt-Laptop (0 €). |

**Rückfall (zwingend, fail-open):** Kein Broker konfiguriert/erreichbar →
Fusion inaktiv, Solo wie heute. Peer stumm → nach Korrelationsfenster
Solo-Verhalten des Modus. **Broker-Totmann:** bleibt der Broker im
`plausibilisieren`-Modus `broker_totmann_s` (120 s) stumm, fällt der Agent
automatisch auf `annotieren` zurück — **Suppression setzt einen gesunden
Broker voraus.**

## 2. Korrelation: Zeit-Koinzidenz pro Bucht (keine Cross-Kamera-Geometrie)

Ehrliche Grenzen: **Cross-Kamera-IoU ist ohne Homographie unmöglich**, und
**ByteTrack-IDs sind kameralokal** („Kuh #7" ist auf beiden Kameras nicht
dasselbe Tier). Gematcht wird deshalb **pro Bucht über Zeit-Koinzidenz**:

Zwei Sichtungen gelten als derselbe Aufsprung, wenn (1) beide Kameras
`gemeinsame_bucht: true` konfiguriert haben, (2) beide `brunstverdacht`
sind und (3) das Peer-Signal binnen **`korrelation_fenster_s` = 30 s**
eintrifft (4 s Mindestdauer je Kamera + Blickwinkel-Versatz + Restskew;
kurz genug gegen Zufallskollisionen).

- **Uhren-Robustheit:** Es zählt die **lokale Empfangszeit** des
  Peer-Signals, nicht der Sender-Zeitstempel — LAN-MQTT stellt quasi sofort
  zu, das umgeht jede Uhren-Synchronisation.
- **Roh-Signal getrennt vom Nutzer-Alarm (verhindert Deadlock):** Jeder
  Agent publiziert seine rohe Sichtung sofort bei Erreichen der 4-s-Dauer
  auf `<basis_topic>/<kamera>/brunst_signal` — unabhängig von Gate,
  Cooldown, Paar-Stummschaltung. Der nutzersichtbare
  `<kamera>/brunstverdacht`-Topic bleibt gegated. Jeder Agent abonniert
  das `brunst_signal` der Peer-Kamera.

## 3. Fusions-Semantik: zwei Modi + Buchtschalter + Recall-Ventil

- **`gemeinsame_bucht: false` (Default):** Fusion übersprungen — Status quo.
- **`modus: annotieren` (empfohlener Einstieg):** Solo alarmiert wie heute
  (kein Recall-Verlust); Peer-Bestätigung reichert nur den Text an. Die
  **Mess-Rampe**: über `docs/metriken.md` wird die Bestätigungsquote
  sichtbar — ≈ 0 % entlarvt eine falsch gesetzte `gemeinsame_bucht`, bevor
  sie schadet.
- **`modus: plausibilisieren` (Opt-in nach Metrik-Beleg):** Bestätigt →
  Telegram mit „von beiden Kameras bestätigt". Unbestätigt → **Abwertung
  statt Löschung**: kein Weckton, aber Dashboard-Eintrag als `typ: info`.
  Das halbiert die Brunst-Fehlalarme (Solo-Geometrie-Artefakte bestätigt
  der zweite Winkel nicht).
- **Recall-Ventil:** Hält der Aufsprung **`solo_notfall_s` = 20 s** ohne
  Bestätigung an, feuert der Solo-Alarm trotzdem — eine so lange echte
  Duldung darf nicht verloren gehen.

`konfidenz` bleibt `null` (Brunst ist regelbasiert; erfundene Zahlen würden
Schema und Evidenz-Grundsatz verletzen) — die Bestätigung lebt nur im Text.

## 4. Anti-Spam-Interaktion

- Paar-Stummschaltung (1 h) und Cooldown (15 min) **unverändert**; die
  Fusion sitzt dazwischen und ändert weder Zeitpunkt noch Dauer.
  Abgewertete Sichtungen laufen als `info` über einen eigenen
  Cooldown-Schlüssel.
- **IDs nie gleichsetzen:** beide lokalen IDs als Herkunft — „stallwache:
  Kuh #7 auf Kuh #3 — zeitgleich von futterwache bestätigt (dort
  Kuh #5/#2)", nie „Kuh #7 = Kuh #5".
- Das Roh-Signal `brunst_signal` trägt kein Telegram, keine Buttons, keinen
  Cooldown — reine Peer-Koordination.

**Fertige Alarmtexte:**
- *Bestätigt:* „Aufsprungverhalten in der Bucht erkannt (stallwache: Kuh #7
  auf Kuh #3, Dauer 6 s) — von der Futterwache zeitgleich bestätigt. Zwei
  Blickwinkel einig: deutlicher Brunst-Hinweis, bitte Kuh #3 auf Duldung
  beobachten."
- *Unbestätigt (nur Dashboard, still):* „Einzelkamera-Aufsprung an der
  Stallwache (Kuh #7 auf Kuh #3), von der Futterwache nicht bestätigt — als
  Beobachtung vermerkt, kein Weckruf."
- *Recall-Ventil:* „Anhaltender Aufsprung an der Stallwache (Kuh #7 auf
  Kuh #3, seit 21 s) — trotz fehlender Zweitkamera-Bestätigung gemeldet, da
  ungewöhnlich lange Duldung. Bitte prüfen."

## 5. Konfig-Schema (für config.example.yaml, bei Umsetzung)

```yaml
brunst_fusion:
  aktiv: false               # Opt-in; aus = Status quo (jede Kamera solo)
  gemeinsame_bucht: false    # Sehen BEIDE Kameras dieselbe Bucht? Nur dann fusionieren.
  modus: annotieren          # annotieren = recall-sicher | plausibilisieren = praezisionsscharf
  peer_kamera: futterwache   # dieser Agent hoert <basis_topic>/<peer_kamera>/brunst_signal
  korrelation_fenster_s: 30  # Zeit-Koinzidenz; zaehlt die EMPFANGSZEIT, nicht den Peer-Zeitstempel
  solo_notfall_s: 20         # Recall-Ventil (0 = aus)
  broker_totmann_s: 120      # Broker stumm -> automatisch zurueck auf 'annotieren' (fail-open)
# Transport: vorhandener mqtt-Block; Fusion erfordert mqtt.host != "" (Mosquitto, 0 EUR).
```

## 6. Verifikationsplan

**Offline (pytest, injiziertes `jetzt` + injizierte Peer-Inbox; eigenständige
Klasse `BrunstFusion` im TotmannWaechter-Stil):** Bestätigung im Fenster;
Fenster-Rand (45 s → keine Bestätigung); `annotieren` ohne Peer → Solo;
`plausibilisieren` ohne Peer → dashboard-only; Recall-Ventil ≥ 20 s;
`gemeinsame_bucht: false` ignoriert Peer; Broker-Totmann → Rückfall ohne
Deadlock; Uhren-Skew (falscher Payload-Zeitstempel, Empfang zählt);
ID-Nichtgleichsetzung im Text.

**Praxis-Abnahme (`docs/metriken.md`):** Brunst-Fehlalarme/Nacht über
≥ 7 Nächte, Baseline solo vs. `plausibilisieren` — Ziel **≥ 50 % weniger
Fehlalarme bei nicht schlechterem Recall** (Ereignis-Ebene, annotierte
Clips). Erst nach diesem Beleg wird `plausibilisieren` scharfgeschaltet;
bis dahin ist `annotieren` die Rampe.

## Offene Risiken

1. **Broker als Suppressions-Voraussetzung:** Ein toter Broker darf nie
   still Alarme unterdrücken → `broker_totmann_s`-Rückfall ist
   Pflichtbestandteil, nicht Option.
2. **Falsch gesetztes `gemeinsame_bucht: true`** (getrennte Blickfelder als
   geteilt markiert) → `plausibilisieren` würde jeden echten Aufsprung
   unterdrücken. Absicherung: Default `false` + `annotieren`-Rampe, deren
   Bestätigungsquote ≈ 0 % die Fehlkonfiguration entlarvt.
3. **Zufalls-Koinzidenz in belebter Bucht** kann ein Solo-Artefakt
   fälschlich bestätigen — begrenzt durch das 30-s-Fenster und die
   Asymmetrie: Fehl-Bestätigung ergibt nur den Status-quo-Alarm; der
   Präzisionsgewinn kommt aus dem Vetorecht gegen Unbestätigte.
