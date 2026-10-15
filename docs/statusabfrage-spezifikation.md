# Spezifikation: Statusabfrage („Status in der Stallwache?“)

Schließt den offenen Folgeschritt aus der Roadmap-Zeile
„Pub/Sub → Firestore-Sink für Statusabfragen“: einen **token-geschützten
Lese-Endpunkt** `GET /api/stall-status`, den der Landwirt (App-Session) und
externe Routinen (z. B. der KuhWatch-Tagesreport, per Lese-Token) abfragen
können. Entwurf und Übernahme: Orchestrator (14.10.2026).
**Status: umgesetzt, Abnahme am realen Agenten offen** (Abschnitt 7).

## 0. Grundsatz

1. **Schweigen ist kein „OK“.** Die Statusabfrage sagt nur dann `OK`, wenn
   der Edge-Agent für diese Kamera ein *aktuelles* Lebenszeichen geschickt
   hat, im Analyse-Modus läuft und ein Bild bekommt. Fehlt eines davon, heißt
   die Antwort `UNBEKANNT` — mit Grund. Das ist Vision-Prinzip 6 („kein
   stiller Ausfall“) auf der Abfrageseite.
2. **Keine zweite Alarmlogik in der Cloud.** Die Statusabfrage *liest* die
   Befunde des Edge-Agenten und ordnet sie ein. Sie bewertet keine Rohdaten
   neu, löst keine Benachrichtigung aus und erfindet keine Befunde. Damit
   bleibt der Edge-Agent die einzige Stelle, die über Alarme entscheidet
   (keine Doppel-Alarme, „Ruhe vor Fülle“).
3. **Verdacht ≠ Beweis.** Jede Einordnung nennt ihre Evidenzart:
   *modellbasiert* (Objekterkennung Fruchtblase/Kälberfüße, mit Konfidenz)
   oder *regelbasiert* (Zeitfilter Schwanzwinkel bzw. Aufsprung-Heuristik —
   Verdacht ohne Objekt-Evidenz).

## 1. Grenzen

| Grenze | Folge |
| --- | --- |
| Die Austreibung trägt **keine Kuh-ID** — Fruchtblase/Kälberfüße sind Objekte, kein Teil eines Kuh-Tracks (`edge-agent/main.py`, `LogicEngine.bewerte`) | Austreibung und Eskalation zählen für die **Kamera (Bucht)**, nicht für eine Kuh. Die Kuh-Liste darunter kann `OK` zeigen, während die Bucht `KRITISCH` ist — das ist korrekt, nicht widersprüchlich |
| Die Eskalation kommt heute mit `kuhId: "Eskalation"` an (Markierung statt Tier) | wird als Kamera-Ereignis gewertet, nie als Kuh |
| Die App kennt nur **gesendete** Alarme, nicht den internen Cooldown-Zustand des Agenten | Cooldown-Ende = letzter Alarm je (Kuh, Typ) + `STATUS_COOLDOWN_MINUTEN` (muss `telegram.cooldown_minuten` des Agenten entsprechen, Default beide 15). Rein informativ |
| Ohne KV-Store (oder bei einem KV-Lesefehler) liest jede Serverless-Instanz nur ihren eigenen Puffer. Ein Alarm, der auf einer anderen Instanz oder vor einem Redeploy einging, fehlt dort — das Lebenszeichen kommt trotzdem an | Antwortfeld `speicher: "instanz"`; dann gibt es **höchstens `UNBEKANNT`, nie `OK`** (Grund: „keine dauerhafte Ereignisablage“). Echte Befunde (`WARNUNG`/`KRITISCH`) bleiben sichtbar, mit Hinweis. **Folge: Bis der KV-Store verknüpft ist, sagt die Statusabfrage nie `OK`** — ehrlich, und ein weiterer Grund für die Roadmap-Zeile „Ereignis-Persistenz“. Befund `qa-waechter` (14.10.2026): vorher meldete eine frische Instanz nach Redeploy `OK`, obwohl 1 min zuvor eine unquittierte Austreibung eingegangen war |
| Ältere Agenten senden kein Lebenszeichen je Kamera | Rückfall auf den globalen `letzterKontakt`; Modus und Bildzustand sind dann unbekannt → höchstens `UNBEKANNT`, nie `OK` |
| Video verlässt den Hof nicht | Die Statusabfrage liefert Text und Ereignis-Metadaten, keine Bilder (die bleiben unter `/api/events/<id>/bild/<n>` hinter der Session) |

## 2. Regeln und Schwellenwerte

Auswertungsfenster: **12 h** (Parameter `stunden`, 1–72).

| Stufe | Bedingung (je Kamera bzw. je Kuh) |
| --- | --- |
| `KRITISCH` | mind. eine **unquittierte** Austreibung (inkl. Eskalation) im Fenster |
| `WARNUNG` | mind. ein **unquittierter** Kalbe- oder Brunstverdacht im Fenster |
| `OK` | keine unquittierten Alarme im Fenster **und** Datenlage aktuell (siehe unten) |
| `UNBEKANNT` | keine unquittierten Alarme, aber Datenlage **nicht** aktuell |

- Quittierte Alarme werden aufgeführt („gesehen um …“), heben die Stufe aber
  nicht an — der Landwirt hat sie bereits wahrgenommen.
- Die Kamera-Stufe ist das Maximum aus Kamera-Ereignissen und allen Kühen
  dieser Kamera; die Gesamtstufe das Maximum aller Kameras
  (`KRITISCH` > `WARNUNG` > `UNBEKANNT` > `OK`).
- **Datenlage aktuell** heißt: Lebenszeichen der Kamera jünger als
  `STATUS_LEBENSZEICHEN_MAX_MINUTEN` (Default **15** = drei verpasste
  5-Minuten-Lebenszeichen), Modus `analyse`, Bild vorhanden **und**
  Ereignisliste aus dem dauerhaften Store (`speicher: "kv"`). Demo-Daten
  sind nie aktuell.

### Lebenszeichen (Erweiterung des Ingest-Vertrags, abwärtskompatibel)

Der leere Stapel war schon bisher ein gültiges Lebenszeichen. Neu ist ein
**optionales** Feld daneben:

```json
{ "ereignisse": [],
  "lebenszeichen": { "kamera": "stallwache", "modus": "analyse", "bild": true } }
```

- `modus`: `analyse` | `silent`; `bild`: Stream liefert verwertbare Frames
  (letzter Frame < 2 min alt, Freeze-Watchdog meldet keinen Defekt).
- Alte Agenten ohne Feld funktionieren unverändert; der Server ignoriert ein
  fehlerhaftes Feld, statt den Stapel abzulehnen.
- Das Ereignis-Schema (`typ`, `kuhId`, `kamera`, `nachricht`, `konfidenz`)
  bleibt **unverändert**.

Der Agent sendet es in einem eigenen Daemon-Thread mit 10-s-Timeout — ein
toter Uplink kann die Analyseschleife damit nicht aufhalten.

## 3. Konfiguration

| Ort | Schlüssel | Default | Bedeutung |
| --- | --- | --- | --- |
| Webapp | `STATUS_READ_TOKEN` | leer | Lese-Token für externe Routinen (Header `x-status-token`). Leer = nur App-Session |
| Webapp | `STATUS_COOLDOWN_MINUTEN` | 15 | Spiegel von `telegram.cooldown_minuten` |
| Webapp | `STATUS_LEBENSZEICHEN_MAX_MINUTEN` | 15 | ab diesem Alter gilt eine Kamera als „ohne Lebenszeichen“ |
| Edge | `dashboard.lebenszeichen_minuten` | 5 | Intervall des Lebenszeichens; 0 = aus |

Der Lese-Token ist bewusst **ein anderer** als `EDGE_INGEST_TOKEN`: Wer den
Status lesen darf, darf keine Ereignisse einspeisen.

## 4. Schnittstelle

`GET /api/stall-status?stunden=12&kamera=stallwache&kuh=42`

| Fall | Antwort |
| --- | --- |
| Header `x-status-token` korrekt | 200 |
| Header gesetzt, aber falsch | 401 |
| Header gesetzt, `STATUS_READ_TOKEN` nicht konfiguriert oder gleich `EDGE_INGEST_TOKEN` | 503 |
| kein Header | App-Session wie jede andere Route (Middleware) |

`kuh` vergleicht die Nummer exakt (`42` trifft „Kuh #42“, nicht „Kuh #420“).

## 5. Texte (Deutsch, ruhig, mit Kuh-ID und Uhrzeit in Ortszeit)

| Lage | Text |
| --- | --- |
| OK | „Stallwache: OK – keine offenen Alarme in den letzten 12 h. Analyse läuft, letztes Lebenszeichen 16:02.“ |
| kein Lebenszeichen | „Stallwache: UNBEKANNT – letztes Lebenszeichen 15:10 (vor 52 min). Keine Aussage über die Tiere möglich.“ |
| Silent Mode | „Stallwache: UNBEKANNT – Silent Mode (Datensammlung), Tiere werden noch nicht analysiert. Keine Aussage über die Tiere möglich.“ |
| Kamera blind | „Stallwache: UNBEKANNT – Kamera liefert kein Bild. Keine Aussage über die Tiere möglich.“ |
| ohne KV-Store | „Stallwache: UNBEKANNT – keine dauerhafte Ereignisablage (KV-Store fehlt oder nicht erreichbar) – Alarme anderer App-Instanzen oder von vor einem Neustart wären hier nicht sichtbar. Keine Aussage über die Tiere möglich.“ |
| Demo | „Noch kein Edge-Agent verbunden – angezeigt werden Demo-Daten, kein Stallzustand.“ |
| Kalbeverdacht | „Kuh #42: WARNUNG – Kalbeverdacht 02:14, offen (regelbasiert, Verdacht ohne Objekt-Evidenz). Folgemeldungen gleicher Art gebündelt bis 02:29.“ |
| Austreibung | „Stallwache: KRITISCH – Austreibung 03:12, offen (modellbasiert, Konfidenz 87 %).“ |

## 6. Abnahmekriterien

Automatisiert (`tests/stall-status.test.ts`, `edge-agent/tests/test_lebenszeichen.py`):

1. Leerer Speicher mit Demo-Daten → Gesamtstufe `UNBEKANNT`, nie `OK`.
2. Aktuelles Lebenszeichen, Modus `analyse`, Bild da, keine Alarme → `OK`.
3. Lebenszeichen älter als 15 min → `UNBEKANNT` mit Altersangabe.
4. Modus `silent` → `UNBEKANNT` mit Silent-Mode-Text.
5. `bild: false` → `UNBEKANNT` mit Kamera-Text.
6. Unquittierte Austreibung ohne Kuh-ID → Kamera `KRITISCH`, erscheint nicht als Kuh.
7. `kuhId: "Eskalation"` → Kamera-Ereignis, keine Kuh „Eskalation“.
8. Unquittierter Kalbeverdacht → Kuh und Kamera `WARNUNG`, Evidenz `regelbasiert`.
9. Quittierter Alarm → aufgeführt, Stufe bleibt `OK`.
10. Alarme außerhalb des Fensters zählen nicht.
11. Cooldown-Ende = letzter Alarm (Kuh, Typ) + 15 min; abgelaufen → nicht mehr aufgeführt.
12. `kuh=42` trifft „Kuh #42“, nicht „Kuh #420“.
13. Kamera-Filter liefert nur die gewünschte Kamera.
14. Altes Lebenszeichen ohne Kamera (nur globaler Kontakt) → höchstens `UNBEKANNT`.
14a. `speicher: "instanz"` (kein KV, Lesefehler, Instanzwechsel nach Redeploy) → nie `OK`; offene Alarme bleiben `WARNUNG`/`KRITISCH` mit Hinweis.
14b. `STATUS_READ_TOKEN` gleich `EDGE_INGEST_TOKEN` → 503.
15. Agent: Lebenszeichen enthält Kamera, Modus und Bildzustand; Intervall wird eingehalten; ein Netzfehler wirft nicht und blockiert nicht; `lebenszeichen_minuten: 0` sendet nichts; ohne Dashboard-URL/Token sendet er nichts.

Am realen System (Beweispflicht, offen):

16. Agent im Stall 30 min laufen lassen → `GET /api/stall-status` zeigt
    `OK` mit Lebenszeichen ≤ 5 min.
17. Netzwerkkabel/WLAN des Stallrechners trennen → nach spätestens 15 min
    `UNBEKANNT`; Analyse läuft lokal ohne Verzögerung weiter (Log prüfen).
18. Kamera abziehen → `UNBEKANNT` „Kamera liefert kein Bild“ innerhalb von
    ~7 min (2-min-Bildgrenze + 5-min-Intervall).

## 7. Risiken

1. **Cooldown-Spiegel driftet**, wenn `telegram.cooldown_minuten` am Agenten
   geändert wird, `STATUS_COOLDOWN_MINUTEN` aber nicht. Folge: falsche
   Info-Zeile, kein falscher Alarm. Gegenmaßnahme: beide in der Doku
   nebeneinander nennen.
2. **Ohne KV nie `OK`**: Bis der KV-Store verknüpft ist, antwortet die
   Statusabfrage bei ruhigem Stall immer `UNBEKANNT`. Das ist gewollt (ein
   Instanzpuffer kann Alarme verlieren), macht die Abfrage aber erst mit
   KV-Store wirklich nützlich — Roadmap P1 „Ereignis-Persistenz“.
3. **Lebenszeichen liefert den Offline-Puffer nicht nach.** Gepufferte Alarme
   gehen weiterhin erst mit dem nächsten Alarm raus. Bewusst getrennt, weil
   Puffer-Zugriff aus zwei Threads eine Sperre bräuchte, die den Hauptpfad
   verlangsamen kann — eigener Folgeschritt.
4. **Lese-Token im Klartext bei der Routine.** Er erlaubt nur Lesen von
   Ereignis-Metadaten (keine Bilder, kein Ingest). Rotation = Env-Wert
   ändern + Redeploy.

## 8. Offener Widerspruch zur GCP-Stallwache-Vorgabe (Entscheidung Betreiber)

Die Betriebsanweisung für LELA beschreibt für den GCP-Layer eine eigene
Klassifikation (PRIO 1/2/3). Sie weicht in drei Punkten von den beschlossenen
Edge-Regeln (`edge-agent/SYSTEM_PROMPT.md`) ab. Diese Spezifikation setzt
**keine** davon um, sondern benennt sie:

| Punkt | Edge (umgesetzt) | GCP-Vorgabe | Folge |
| --- | --- | --- | --- |
| Winkel-Vektoren | Rücken `spine_end→tail_base` (zeigt **nach hinten**) gegen `tail_base→tail_tip` | `tail_base→back_mid` (zeigt **nach vorn**) gegen `tail_base→tail_tip` | Bei kollinearen Rückenpunkten gilt θ_GCP = 180° − θ_Edge. „> 45°“ beschreibt damit **verschiedene Haltungen**. Den Keypoint `back_mid` hat das Modell nicht (vorgesehen ist `spine_mid` erst im 2. Training) |
| Anteil im 30-min-Fenster | > 20 % | > 60 % | dreifach strengere Schwelle, spätere Warnung |
| Sofort-Alarm | `amniotic_sac` **oder** `calf_legs` > 0.80 | nur `amniotic_sac` > 0.80 | Kälberfüße ohne sichtbare Fruchtblase (Blase bereits gerissen) würden keinen Sofort-Alarm auslösen → Recall-Risiko |

`atan2(|u×v|, u·v)` und `arccos(u·v / |u||v|)` liefern denselben Winkel; der
Unterschied liegt allein in der Vektorrichtung, nicht in der Formel.

**Empfehlung des Orchestrators:** Edge-Regeln beibehalten und den GCP-Layer
auf Speichern/Auswerten (PRIO 3) beschränken. Eine zweite, abweichende
Alarmlogik in der Cloud erzeugt Doppel- oder Gegen-Alarme und bräuchte
laufende Telemetrie-Uploads statt Einzelereignisse (Edge-First). Wer die
GCP-Werte will, ändert sie **am Edge** — mit Beschluss in
`wettbewerbsanalyse.md` und Test am realen Stream.
