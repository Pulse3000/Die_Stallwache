# Spezifikation: Quittierungs-getriebene Nacht-Eskalation mit lokalem Weckkanal

Implementierungsreife Regeln für die P1-Entscheidung aus
[`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md) §4 („Entscheidungen aus der
Alarmweg-Analyse"). Marktbefund August 2026: *niemand* eskaliert auf
ausbleibende Reaktion — alle Wettbewerber eskalieren inhaltlich oder gar nicht.
Entwurf: Agent `ki-wache` (09.08.2026), Entscheidung und Übernahme:
Orchestrator. **Status: spezifiziert — Stufen 1–2 sind modellunabhängig sofort
umsetzbar, die Weckton-Stufe erst nach Broker, Weckgerät und aktivierter
Ereignis-Persistenz** (siehe Risiko 10 und die Ausrollreihenfolge in §9).

## 0. Grundsatz und Abgrenzung

Es gibt ab hier **zwei verschiedene Eskalationen**, die nie verwechselt werden
dürfen:

| | Auslöser | Frage | Ort | Vorhanden |
| --- | --- | --- | --- | --- |
| **Inhaltliche Eskalation** | `logik.eskalation_minuten` (60 min ohne Geburtsfortschritt) | „Geht es der Kuh schlecht?" | `LogicEngine.bewerte()` | ✅ `edge-agent/main.py` |
| **Reaktions-Eskalation** (diese Spec) | Alarm N Minuten unquittiert | „Hat es jemand gesehen?" | neue Klasse `EskalationsKette` | ⏳ |

Die zweite kennt den Tierzustand nicht und darf ihn nie behaupten. Sie
eskaliert ausschließlich **Zustellung**, nie Diagnose. Beide laufen
gleichzeitig: Die inhaltliche Eskalation erzeugt einen Alarm, der seinerseits
reaktions-eskaliert — mit eigenem, schärferem Profil (§2.3).

Leitplanke gegen „Ruhe vor Fülle": Die Kette macht **keinen einzigen Alarm
mehr**, sie macht bestehende Alarme **hartnäckiger**. Wer quittiert, hört exakt
so viel wie heute. Die zusätzliche Lautstärke bezahlt ausschließlich, wer nicht
reagiert.

## 1. Regelwerk: Was eskaliert, was nie

| Ereignistyp | Eskaliert? | Weckton? | Begründung |
| --- | --- | --- | --- |
| **`austreibung`** (Objekt-Override ≥ 0.80) | **ja, immer** | **ja** | Vision-Prinzip 5 „keine verpasste Kalbung". Der einzige Alarm, dessen Verpassen ein Kalb kostet. Nicht einzeln abschaltbar, nur über `eskalation.aktiv: false` |
| **`austreibung`, Eskalations-Variante** (inhaltliche Eskalation) | **ja, verkürzt** | **ja** | Hier sind bereits 60 min Geburtsstillstand vergangen — das Zeitbudget des Kalbes ist verbraucht. Halbe Stufenzeiten |
| **`festliege_seitenlage`** (sobald das Feature existiert) | **ja, verkürzt** | **ja** | Aufblähgefahr, Minuten-Budget ([`festliege-spezifikation.md`](./festliege-spezifikation.md) §2) |
| **`festliege`** (4-h-Regel, auch postpartum) | **ja, flach** | **nein** | Zeitbudget Stunden, nicht Minuten. Eine Wiederholung nach 30 min, dann Schweigen. Eine Sirene für einen Liegeplatz-Verdacht wäre der schnellste Weg zum Abschalten des Features |
| **`kalbeverdacht`** (Schwanzwinkel-Statistik) | **nur im Wach-Modus, flach** | **nein** | Vorlauf 2–12 h — kein Grund, in 15 Minuten zu wecken. Zugleich der Typ mit der höchsten Fehlalarmlast (regelbasiert, `konfidenz: null`). Im Wach-Modus ist der Landwirt bewusst in Alarmbereitschaft: dort **eine** Wiederholung nach 20 min |
| **`brunstverdacht`** | **nie** | **nie** | Duldung dauert 8–18 h, der nächste Zyklus kommt in 21 Tagen. Kosten eines verpassten Aufsprungs: eine Rast. Kosten einer Sirene um 3 Uhr für einen Aufsprung: das Feature |
| **`info`** (Start, Digest, Totmann, Kalbe-Akte) | **nie** | **nie** | **Sicherheitskritisch:** Die Totmann-Meldung („das dritte Auge ist blind") tritt genau dann auf, wenn WLAN oder Kamera weg sind — also genau dann, wenn auch die Quittierungsabfrage scheitert. Dürfte sie eskalieren, löste **jeder nächtliche WLAN-Ausfall den Weckton aus**. Gehört als **harte Ausschlussliste in den Code**, nicht als Config-Default |

**Kein neuer Ereignistyp.** Alle Eskalationsmeldungen gehen als der **Typ des
Ursprungsalarms** raus (Stufe 1 einer Austreibung ist wieder
`typ: "austreibung"`). Das vermeidet die Whitelist-Erweiterung in
`lib/ereignis-modell.ts` und `app/api/events/route.ts` vollständig — dieselbe
Entscheidung wie bei der Kalbe-Akte.

`festliege`/`festliege_seitenlage` existieren noch nicht als Ereignistypen
(blockiert bis zum ersten Modell). Ihre Profile stehen hier mit, werden aber
erst mit dem Feature scharf.

## 2. Stufenmodell

### 2.1 Das Zeitbudget, aus dem sich alles ableitet

Stadium II (Austreibung) dauert bei der Kuh typisch 30–70 min, bei der Färse
länger. Die geburtshilfliche Faustregel: **kein Fortschritt binnen 30–60 min
nach Erscheinen von Fruchtblase oder Füßen → eingreifen** (genau darauf steht
`logik.eskalation_minuten: 60`). Reißt die Nabelschnur bei falscher Lage, hat
das Kalb Minuten.

Rückwärts gerechnet: Der Mensch muss **spätestens 20–25 Minuten nach dem
Erstalarm im Stall stehen**, damit im 30-Minuten-Kontrollfenster noch
Handlungsreserve bleibt. Bei einem Weg Haus→Stall von ~5 min heißt das: **die
letzte Weckstufe muss bei +15 min gefeuert haben.** Alle anderen Zahlen sind
die Aufteilung dieser 15 Minuten auf drei Versuche — sie sind nicht geraten,
sie sind das Budget.

### 2.2 Stufen (Profil `austreibung`, Default)

| Stufe | Zeit | Kanal | Warum genau diese Minutenzahl |
| --- | --- | --- | --- |
| **0** | +0 | bestehende Kette: Telegram-Album + Push (dringend, `requireInteraction`) + Dashboard | unverändert |
| **1** | **+5 min** | Wiederholung an dieselben Empfänger — neues Ereignis via `POST /api/events` (löst automatisch erneuten Push aus) plus kurze Telegram-Nachricht ohne Bildserie | Aufwachen, Handy greifen, entsperren, tippen: realistisch 1–3 min. 5 min liegt sauber darüber — wer bis dahin nicht quittiert hat, hat den Alarm *nicht gehört*, nicht *noch nicht bearbeitet*. Kürzer wäre Doppelklingeln bei jemandem, der ohnehin schon aufsteht |
| **2** | **+10 min** | zweiter Empfänger (`eskalation.zweiter_empfaenger.telegram_chat_id`): Partnerin, Altenteiler, Azubi, Nachbar | Ein unabhängiger Mensch als Redundanz, **bevor** der Krachmacher kommt — exakt das Muster des Stall-Autodialers (Nummer 2, wenn Nummer 1 nicht abnimmt). 5 min nach Stufe 1: derselbe Reaktionsspielraum wie Empfänger 1 |
| **3** | **+15 min** | lokaler Weckton per MQTT (§4) | Nach 15 min ohne jede Reaktion ist die Zustellkette faktisch tot — entweder schläft der Hof durch oder die Leitung ist weg. Der Mensch ist dann gegen +20 min im Stall, also mit Reserve innerhalb des 30-min-Kontrollfensters. Später wäre fahrlässig; früher hätte der Weckton seine soziale Rechtfertigung nicht verdient (er weckt den ganzen Haushalt) |
| **3b** | Ton **max. 5 min**, dann 10 min Pause, dann Zyklus 2 und 3 | derselbe Kanal | Dauerton macht taub und wird abgeklemmt. Drei Zyklen decken +15 bis ~+50 min ab |
| **Ende** | nach 3 Zyklen (~+50 min) | **Schweigen** + Eintrag im Tagesbericht | Wenn nach 50 min niemand reagiert, ist niemand auf dem Hof. Eine bis Sonnenaufgang schrillende Sirene in einem leeren Hof schadet den Tieren und den Nachbarn, ohne irgendetwas zu retten |

### 2.3 Profiltabelle aller Typen

| Profil | Stufe 1 | Stufe 2 | Weckton | Zyklen |
| --- | --- | --- | --- | --- |
| `austreibung` | 5 min | 10 min | 15 min | 3 |
| `austreibung_eskalation` (Komplikation) | 3 min | 6 min | 9 min | 3 |
| `festliege_seitenlage` | 3 min | 6 min | 10 min | 3 |
| `festliege` (inkl. postpartum) | 30 min | — | nein | 0 |
| `kalbeverdacht` (nur `wach_modus`) | 20 min | — | nein | 0 |
| `brunstverdacht`, `info` | — | — | nie | — |

Zwei Verkürzungen greifen in diese Zeiten ein: **toter Uplink** (§2.4, Weckton
bei +8) und **kein zweiter Empfänger** (§2.5, Weckton bei +10). Beide ziehen
nur vor, nie hinaus.

### 2.4 Leitungsbewusste Verkürzung (`uplink_tot_verkuerzung: true`)

Der ehrliche Schwachpunkt der Kette: **Stufe 1 und 2 laufen über dieselbe
Leitung, die im Offline-Fall tot ist.** Bei Netzausfall verpufft eine
Push-Wiederholung wirkungslos und verbrennt trotzdem 10 Minuten Kalbezeit.

Regel: Sind **beide** Kanäle beim letzten Versuch auf Transportebene
gescheitert (Telegram *und* Dashboard), gilt der Uplink als tot → Stufe 2 wird
übersprungen und der **Weckton auf +8 min vorgezogen**. Scheitert nur einer
(z. B. Vercel-Störung bei intaktem Telegram), bleibt das Normalprofil — der
überlebende Kanal hat seine Chance verdient.

Das ist die einzige Stelle, an der die Architektur-Entscheidung **erweitert**
wird: „Fehlerfall führt zum Wecken" ist richtig, aber daraus folgt nicht, dass
man erst 15 Minuten lang in eine tote Leitung ruft.

### 2.5 Verkürzung ohne zweiten Empfänger (`kein_zweiter_empfaenger_verkuerzung`)

Derselbe Denkfehler noch einmal, nur mit **intakter** Leitung und stummem
Endgerät: iOS Focus und „Nicht stören" schalten Push von Drittanbieter-Apps
nachts stumm — nur der System-Wecker und Apples *Critical Alerts* brechen
durch, und Web-Push erreicht diese Stufe nicht. Hat Stufe 0 nicht geweckt,
**weil das Betriebssystem sie stummgeschaltet hat**, dann weckt Stufe 1 aus
demselben Grund auch nicht.

Regel: Ist `zweiter_empfaenger.telegram_chat_id` leer, entfällt Stufe 2
ohnehin — dann rückt der Weckton von +15 auf **+10 min**. Ist ein zweiter
Empfänger konfiguriert, bleibt es bei 15 min: Ein zweiter wacher Mensch ist
die bessere Redundanz als ein Krachmacher.

Zum Maßstab: Die gesamte Autodialer-Nachbarkategorie lässt ihren lokalen
Signalgeber **binnen 60 Sekunden** losgehen, parallel zu den Anrufen — nicht
nach 15 Minuten. Unsere Stufe 3 liegt um mehr als den Faktor 10 später. Das
ist verteidigbar, aber nur mit zwei Argumenten, die man mitsagen muss:
Deren Auslöser ist deterministisch (ein Kontakt öffnet), unserer ist
probabilistisch mit Fehlalarmrate; und deren Hupe hängt draußen und kostet
sozial nichts, unsere weckt ein Schlafzimmer. Als „vom Autodialer abgeschaut"
verkauft wäre unsere Zeitachse schlicht falsch — die Kategorie würde bei +0
läuten.

## 3. Abfragelogik der Quittierung

### 3.1 Woher der Agent die Ereignis-ID bekommt

`Notifier._dashboard()` verwirft heute die Antwort. Die Antwort enthält die ID
bereits:

- **Stapel-POST** → `{"ok":true,"angenommen":N,"ergebnisse":[{"id":…}, …]}`,
  positionsgleich zum gesendeten Stapel — das eigene Ereignis ist
  `ergebnisse[-1]`.
- **Einzel-POST** → `{"ok":true,"id":…,"push":N,"pubsub":bool}`.

`_dashboard()` muss die ID also nur noch zurückgeben. Das Feld `push` (Zahl
zugestellter Geräte) wird mitgeloggt — es ist die einzige echte
Zustellinformation, die wir haben, und die Vorarbeit für den Alarmweg-TÜV (P2).

Scheitert der POST, gibt es keine ID → **die Eskalation läuft trotzdem**, nur
ohne Abfragemöglichkeit (= dauerhaft unquittiert). Genau der gewollte
Fehlerfall.

### 3.2 Abfrage-Endpunkt

```
GET /api/events/quittierungen?ids=<id1>,<id2>,…        (max. 20 IDs)
Header: x-ingest-token: EDGE_INGEST_TOKEN

200 {"stand":"2026-08-09T03:17:02Z",
     "quelle":"edge-agent",
     "quittiert":{"<id1>":"2026-08-09T03:16:44Z","<id2>":null},
     "unbekannt":["<id3>"]}
400 ids fehlt / > 20 · 401 falscher Token · 503 Ingest nicht konfiguriert
```

Nötig: eine Middleware-Ausnahme analog zum Ingest in `middleware.ts` (dort
steht heute nur `POST /api/events`). Antwortgröße ~150 Byte statt ~5 kB.

`"quelle":"demo"` ist wichtig: Liefert der Store Demodaten, sind alle echten
IDs unbekannt — der Agent loggt dann „App im Demo-Modus, Quittierung nicht
belastbar" statt stumm zu eskalieren.

**Rückfallweg ohne jede App-Änderung** (für ein gestuftes Ausrollen): Der Agent
meldet sich wie `CloudQuelle` mit `stream.app_passwort` an und liest
`GET /api/events?typ=austreibung&stunden=2&limit=20`; das Feld `quittiert`
steckt bereits im `StallEreignis`. Kostet ~5 kB pro Abfrage statt 150 Byte; der
401-Reanmeldepfad aus `CloudQuelle.hole_url()` ist wiederverwendbar.

### 3.3 Takt, Timeout, Fehlerverhalten

| Punkt | Regel |
| --- | --- |
| **Takt** | alle **30 s**, aber **nur solange mindestens eine Eskalation offen ist**. Im Normalbetrieb: null Abfragen. Der Agent ist kein Herzschlag-Dienst — dafür gibt es `letzterKontakt` |
| **Warum 30 s** | Die Stufen liegen Minuten auseinander; 30 s Auflösung kostet schlimmstenfalls eine halbe Minute und hält den Datenverbrauch bei ~0 |
| **Timeout** | 10 s, kein Retry innerhalb des Ticks (der nächste Tick *ist* der Retry) |
| **Fehler / Timeout / 401 / 5xx** | → „unbekannt" → **gilt als unquittiert**, Kette läuft weiter. Fehler werden gezählt: ab 3 Fehlversuchen in Folge gilt der Uplink für §2.4 als tot |
| **`unbekannt`-IDs** (aus dem Ringpuffer gefallen, KV leer) | ebenfalls **unquittiert** — der Fehler weckt, er schweigt nicht |
| **Sperre der Analyse** | nie: Abfrage in eigenem `try/except`, wie alle Notifier-Wege |

### 3.4 Drei Quittierungswege (bewusst redundant)

1. **App/Push** — `POST /api/events/[id]/quittieren`, auch direkt aus der
   Benachrichtigung (`public/sw.js`), mit Offline-Warteschlange. Der Agent
   sieht es über die Abfrage.
2. **Telegram-Inline-Button** — nutzt die vorhandene `FeedbackSchleife`
   (10-s-Poll). Neuer Button **„👁 Gesehen"** mit
   `callback_data: quit:<eskalations-id>`, nur bei eskalierenden Typen.
   Zusätzlich: **jedes Votum auf „✅ Treffer" oder „❌ Fehlalarm" quittiert
   implizit** — wer abstimmt, hat den Alarm offensichtlich gesehen.
   „❌ Fehlalarm" bricht die Kette sofort ab und schaltet einen laufenden
   Weckton aus.
3. **Lokaler Taster** — MQTT-Topic `…/weckruf/quittung` (§4). **Der einzige
   Weg, der bei totem Internet funktioniert** — und damit der einzige, der den
   Weckton stoppen kann, wenn der Weckton der einzige funktionierende Kanal
   ist. Nicht optional, und seit der Hardware-Recherche auch Pflichtteil der
   Einkaufsliste: Ein Home-Assistant-Nutzer gab die Sirene-als-Wecker-Lösung
   auf, **weil kein physischer Stopp-Taster existierte**. Ein Weckton, den man
   nur per App stoppen kann, wird beim ersten Fehlalarm abgeklemmt — und
   danach weckt gar nichts mehr.

Eine Quittierung über Weg 2 oder 3 stoppt die Kette lokal, lässt aber den
Dashboard-Eintrag offen (der Agent kann `quittieren` nicht aufrufen — der
Endpunkt verlangt eine Session, und das ist richtig so). Das ist ehrlich: Die
App zeigt den Alarm weiter als offen, bis der Landwirt sie öffnet. Der
Alarmtext sagt das (§6).

### 3.5 Neustart-Sicherheit

Zustandsdatei `eskalation-zustand.json`, atomar geschrieben (tmp + `replace`,
exakt wie `_puffer_sichern()`), neben `alarm-puffer.jsonl`.

```json
{"gesichert":"…","offen":{"<esk-id>":{"typ":"austreibung","kuhId":"Kuh #42",
  "start":1754706727.0,"stufe":2,"ids":["<ev1>","<ev2>"],"evidenz":7,
  "zyklen":0,"weckton_seit":null}},
 "erledigt":{"<esk-id>":{"ts":…,"grund":"quittiert"}}}
```

| Regel | Zweck |
| --- | --- |
| **`eskalations_id = typ \| kuhId \| episoden_start_iso`** | Episodenbezug statt (Kuh, Typ). Eine neue Episode (30 min ohne frischen Alarm desselben Schlüssels, gleiche Semantik wie der `austreibung_zuletzt`-Reset) darf wieder eskalieren; eine wieder eingespielte alte nicht |
| **`erledigt`-Liste, TTL 24 h** | **Beantwortet die Kernfrage: Ein quittierter Alarm eskaliert nach einem Neustart nie wieder.** Der Eintrag wird beim Laden vor `offen` ausgewertet und gewinnt immer |
| **`stufe` ist monoton** | Nach Neustart wird keine bereits gefeuerte Stufe wiederholt — kein Doppel-Push, kein zweiter Weckton für dieselbe Stufe |
| **Karenz `karenz_nach_start_s: 120`** | Nach Prozessstart 2 min lang keine neue Stufe. Ein Neustart passiert typischerweise nach Stromausfall — genau dann brauchen WLAN, Broker und Uplink eine Minute. Ohne Karenz löst jeder Crash-Loop sofort den Weckton aus |
| **`max_alter_h: 6`** | Ältere offene Einträge verfallen beim Laden. Eine Austreibung von vor 6 h ist entschieden |
| **Uhrenschutz** | Erkennt der Agent beim Laden `jetzt < gesichert - 60 s` (Pi ohne RTC, NTP-Sprung), wird `start` so verschoben, dass die erreichte Stufe erhalten bleibt und die Restzeiten neu laufen — statt aus einem Sprung heraus drei Stufen zu feuern |
| **Höchstens eine Stufe pro Tick** | Zweite Verteidigungslinie gegen Uhrensprünge. In der Simulation belegt: 60-min-Sprung ⇒ Stufe 1, dann Stufe 2, dann Weckton über drei Ticks, nicht alles auf einmal |
| **Datei defekt/unlesbar** | verwerfen, `log.error`, **kein** Weckton. Die einzige Stelle mit „Fehler ⇒ Stille": Es gibt keinen bekannten Alarm zu eskalieren, und die Erkennung läuft weiter und alarmiert neu |

## 4. MQTT-Vertrag für den Weckkanal

Der Agent muss dafür erstmals **abonnieren**, nicht nur publizieren (`_mqtt()`
ist heute reines `publish`). Empfohlene Bauform: eigene Klasse `Weckkanal`,
damit `EskalationsKette` rein entscheidend und offline testbar bleibt.

> **Wo das Weckgerät hängt: im Haus.** Nicht im Stall, nicht über der
> Abkalbebox — Begründung in Risiko 2. Diese Festlegung ist Teil des Vertrags,
> nicht Geschmackssache.
>
> **Und welches Gerät:** eines mit **tiefem Ton (~520 Hz) oder ein
> Vibrationskissen**, geschaltet über einen MQTT-Zwischenstecker mit
> geräteseitiger Abschaltzeit. Begründung und Einkaufsliste in
> [`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md) §1d — die Kurzfassung:
> Ein 3100-Hz-Piepser weckt viele Menschen selbst bei 95 dB(A) am Kopfkissen
> nicht, ein 520-Hz-Ton ist 4- bis 12-mal wirksamer. Praktisch jede billige
> Sirene liegt im Hochtonbereich.

### 4.1 Topics

| Topic | Richtung | Retain | Zweck |
| --- | --- | --- | --- |
| `<basis_topic>/weckruf/set` | Agent → Gerät | **false** | Befehl an/aus |
| `<basis_topic>/weckruf/status` | Agent → Welt | **true** | Zustandsanzeige für Home Assistant/Dashboard; erkennt einen laufenden Weckton nach Broker-Neustart |
| `<basis_topic>/weckruf/quittung` | Taster → Agent | false | lokale Quittierung/Stopp |
| optional `<roh_topic>` (z. B. `cmnd/hausgong/POWER`) | Agent → dummes Gerät | false | Tasmota/Shelly direkt, ohne Home Assistant |

**`retain: false` auf `set` ist nicht verhandelbar.** Eine retained
„an"-Nachricht startet das Weckgerät nach jedem Broker-Neustart erneut — das
ist genau der Ton, den niemand stoppen kann. Betriebsweite Topics (nicht
`<kamera>/…`), weil das Weckgerät physisch einmal existiert.

### 4.2 Nutzlast

```json
{ "zustand": "an", "grund": "unquittiert", "stufe": 3, "zyklus": 1,
  "typ": "austreibung", "kuhId": "Kuh #42", "kamera": "stallwache",
  "alarm_seit": "2026-08-09T03:12:07Z", "max_dauer_s": 300,
  "nachricht": "Kuh #42: Austreibung seit 15 Minuten unbestätigt" }
```

Aus: `{"zustand":"aus","grund":"quittiert|zeitlimit|episode_beendet|agent_stop","kuhId":…}`
— `grund` immer mitschicken, das ist die Forensik für „warum hat es nachts
gepfiffen".

QoS 1 (mindestens einmal; ein doppeltes „an" ist harmlos, ein verlorenes „an"
nicht). `weckruf.json: false` schaltet auf die reinen Nutzlasten
`nutzlast_an`/`nutzlast_aus` für dumme Geräte.

### 4.3 Ausschalten — vier unabhängige Wege

1. **Quittierung** (App / Telegram-Button / lokaler Taster) → „aus" binnen
   einer Tick-Periode (≤ 30 s; bei Telegram/Taster ≤ 10 s).
2. **Selbstabschaltung** nach `max_dauer_s` (Default **300 s**) — hart im
   Agenten, unabhängig von jeder Quittierung.
3. **Geräteseitiger Totmann (Pflicht, nicht „empfohlen"):** Der Ton muss auch
   dann verstummen, wenn der Agent-Rechner ausfällt — der einzige Mechanismus,
   der ohne lebenden Agenten funktioniert. Die gute Nachricht aus der
   Hardware-Recherche (§1d der Wettbewerbsanalyse): Das ist **keine
   Automations-Bastelei, sondern eine Geräteeigenschaft für 18 €.** Ein Shelly
   Gen2 kennt `toggle_after` — die MQTT-Nutzlast `on,300` schaltet nach 300 s
   selbsttätig ab; Tasmotas `PulseTime` tut dasselbe ausdrücklich
   hardwareseitig, „ensuring that in case of a connection error, a switch-off
   is safe". Fallback für Geräte ohne diese Eigenschaft: Auffrisch-„an" alle
   `wiederholung_s` (20 s), Automation schaltet nach 60 s ohne Auffrischen ab.
4. **Last Will (LWT):**
   `will_set("<basis_topic>/weckruf/set", '{"zustand":"aus","grund":"agent_weg"}', qos=1, retain=False)`
   plus retained LWT auf `…/status`. Stirbt die MQTT-Verbindung, schaltet der
   **Broker** ab.

Zusätzlich: jedes „aus" **dreimal im Abstand von 2 s** senden. Ein verlorenes
Ausschaltkommando ist der teuerste Paketverlust dieses Systems.

### 4.4 Selbsttest und Broker-Totmann

Beim Agentenstart (wenn `weckruf.aktiv`): Verbindungsprüfung und ein
`{"zustand":"selbsttest"}` auf `…/status`. Kein Broker erreichbar → **genau
eine** Telegram-Nachricht, Muster `TotmannWaechter` (genau eine pro Episode,
genau eine Entwarnung). Ein stiller Weckkanal ist ein gebrochenes Versprechen
und muss so laut sein wie ein blindes Auge.

**Mehrere Agenten:** Nur **ein** Agent bekommt `weckruf.aktiv: true`
(„Weckruf-Meister", üblicherweise die Stallwache). Die anderen eskalieren bis
Stufe 2 und melden ihren Weckton-Wunsch auf `…/weckruf/anforderung`, den der
Meister ausführt. Ohne diese Regel schalten zwei Agenten dasselbe Gerät
gegeneinander an und aus.

## 5. Konfig-Schema (für `config.example.yaml`, bei Umsetzung)

```yaml
eskalation:
  # Quittierungs-getriebene Nacht-Eskalation: Bleibt ein dringender Alarm
  # unquittiert, wird er wiederholt, dann an einen zweiten Empfaenger
  # geschickt, dann per lokalem Weckton hoerbar gemacht. Der Timer laeuft
  # AM EDGE: Ist die App nicht erreichbar, gilt der Alarm als unquittiert
  # und die Kette laeuft weiter (Fehlerfall weckt, statt zu schweigen).
  aktiv: false                     # ganz aus -> Alarme genau wie bisher

  # --- Abfrage der Quittierung ---
  quittung_url: ""                 # leer -> aus dashboard.url abgeleitet
                                   #   (.../api/events/quittierungen)
  abfrage_intervall_s: 30          # nur solange eine Eskalation offen ist
  abfrage_timeout_s: 10
  fehler_bis_uplink_tot: 3         # Fehlversuche in Folge -> Leitung gilt als tot
  uplink_tot_verkuerzung: true     # beide Kanaele tot -> Stufe 2 ueberspringen,
                                   #   Weckton vorziehen (nicht in eine tote
                                   #   Leitung rufen, waehrend das Kalb wartet)
  kein_zweiter_empfaenger_verkuerzung: true
                                   # kein zweiter Empfaenger konfiguriert ->
                                   #   Weckton bei +10 statt +15 min. Stufe 1
                                   #   wiederholt denselben Kanal, den iOS
                                   #   nachts stummschaltet - hat Stufe 0 nicht
                                   #   geweckt, weckt Stufe 1 auch nicht.

  # --- Neustart-Sicherheit ---
  zustand_datei: eskalation-zustand.json
  karenz_nach_start_s: 120         # nach Prozessstart keine neue Stufe
  max_alter_h: 6                   # aeltere offene Ketten verfallen
  erledigt_ttl_h: 24               # quittierte IDs bleiben so lange gesperrt
  episode_ende_min: 30             # so lange ohne frischen Alarm -> neue Episode

  # --- Sicherung gegen Geister-Wecktoene ---
  evidenz_min_erkennungen: 2       # Weckton nur, wenn der Ausloeser in >= 2
                                   #   Frames bestaetigt wurde (ein einzelner
                                   #   Fehlframe darf nie das Haus wecken)

  # --- Stufenprofile (Minuten ab Erstalarm; [] = Typ eskaliert nicht) ---
  profile:
    austreibung:              {stufen: [5, 10, 15], weckton: true}
    austreibung_eskalation:   {stufen: [3, 6, 9],   weckton: true}
    festliege_seitenlage:     {stufen: [3, 6, 10],  weckton: true}
    festliege:                {stufen: [30],        weckton: false}
    kalbeverdacht:            {stufen: [20],        weckton: false,
                               nur_wach_modus: true}
    brunstverdacht:           {stufen: [],          weckton: false}
    # info eskaliert NIE (im Code fest, nicht konfigurierbar) - sonst wuerde
    # die Totmann-Meldung bei WLAN-Ausfall den Weckton ausloesen.

  zweiter_empfaenger:
    telegram_chat_id: ""           # Partner/Altenteiler/Nachbar; leer -> Stufe 2
                                   #   entfaellt, Kette geht direkt zu Stufe 3
    zeitfenster: ""                # z. B. "21:00-06:00"; leer = rund um die Uhr

weckruf:
  # Lokaler Weckton ueber MQTT im Stall-LAN - bewusst NICHT ueber Tuya:
  # Tuya ist cloudgebunden und faellt mit derselben Leitung aus.
  # WICHTIG: Das Weckgeraet gehoert INS HAUS (Schlafzimmer), nicht ueber die
  # Abkalbebox - eine Sirene ueber der kalbenden Kuh hemmt die Wehen.
  aktiv: false                     # setzt mqtt.host voraus
  topic: ""                        # leer -> <mqtt.basis_topic>/weckruf/set
  status_topic: ""                 # leer -> <mqtt.basis_topic>/weckruf/status
  quittung_topic: ""               # leer -> <mqtt.basis_topic>/weckruf/quittung
  json: true                       # false -> nur nutzlast_an/nutzlast_aus
  nutzlast_an: "ON"
  nutzlast_aus: "OFF"
  roh_topic: ""                    # z. B. cmnd/hausgong/POWER (Tasmota/Shelly)
  qos: 1
  max_dauer_s: 300                 # harte Selbstabschaltung je Zyklus
  wiederholung_s: 20               # Auffrisch-Takt -> geraeteseitiger Totmann
  zyklen: 3                        # danach Schweigen + Eintrag im Tagesbericht
  pause_min: 10                    # Ruhe zwischen zwei Zyklen
  zeitfenster: ""                  # leer = rund um die Uhr (eine verpasste
                                   #   Kalbung mittags ist genauso toedlich)
  selbsttest_beim_start: true      # Broker nicht erreichbar -> genau eine
                                   #   Telegram-Meldung (Muster Totmann)
```

**„Ganz aus"** ist `eskalation.aktiv: false` — der Default. Dann verhält sich
der Agent exakt wie heute: kein Zustandsfile, keine Abfrage, kein Topic.

## 6. Alarmtexte

Nachts um drei gelesen: Kuh-ID zuerst, dann was zu tun ist, dann wie man es
abstellt.

**Zusatz am Erstalarm** (nur bei eskalierenden Typen, an den bestehenden Text
angehängt):
> „Bitte in der App oder hier mit ‚👁 Gesehen' bestätigen — sonst wiederholt
> sich dieser Alarm und weckt um 03:27 Uhr den Weckton im Haus."

**Stufe 1 (+5 min):**
> „⚠️ NOCH NICHT BESTÄTIGT — Kuh #42: Die Austreibungsphase läuft seit
> 5 Minuten und niemand hat den Alarm gesehen. Bitte in den Abkalbebereich und
> hier auf ‚👁 Gesehen' tippen."

**Stufe 2 (+10 min, an den zweiten Empfänger):**
> „⚠️ HILFE NÖTIG — Kuh #42 ist seit 10 Minuten in der Austreibungsphase, der
> erste Alarm wurde nicht bestätigt. Bitte im Abkalbebereich nachsehen oder den
> Betriebsleiter wecken."

**Stufe 3 (+15 min, Weckton):**
> „🚨 WECKTON LÄUFT — Kuh #42: Austreibung seit 15 Minuten, kein Alarm
> bestätigt. Der Weckruf im Haus läuft für höchstens 5 Minuten. Ausschalten:
> hier ‚🔕 Weckton aus', in der App quittieren oder den Taster drücken."

**Zyklus 2/3:**
> „🚨 WECKTON ZUM 2. MAL — Kuh #42, seit 30 Minuten unbestätigt. Falls niemand
> auf dem Hof ist: bitte Nachbarn oder Tierarzt anrufen."

**Aufgabe nach dem letzten Zyklus** (still, `disable_notification`):
> „Weckruf beendet — Kuh #42: 3 Zyklen ohne Quittierung, Alarm von 03:12 Uhr
> bleibt unbestätigt. Der Eintrag steht im Tagesbericht; bitte beim nächsten
> Stallgang zuerst in den Abkalbebereich."

**Quittiert** (still, nur wenn mindestens Stufe 1 gefeuert hat):
> „Quittiert um 03:19 Uhr (Telegram) — Kuh #42, Weckton gestoppt, keine weitere
> Eskalation. Hinweis: In der App steht der Alarm weiterhin als offen, bis du
> ihn dort öffnest."

**Bei totem Uplink** (ersetzt den Stufe-3-Text, weil er ohnehin nur lokal oder
nachträglich ankommt):
> „🚨 WECKTON LÄUFT — Kuh #42: Austreibung seit 8 Minuten. Die App war nicht
> erreichbar, deshalb konnte nicht geprüft werden, ob jemand den Alarm gesehen
> hat, und der Weckton wurde vorgezogen. Bitte in den Stall."

**Weckkanal gestört** (`info`, genau einmal pro Episode):
> „Weckkanal nicht verfügbar: Der MQTT-Broker im Stall-LAN antwortet nicht —
> ein nächtlicher Weckton kann derzeit nicht ausgelöst werden. Bitte Broker und
> Weckgerät prüfen."

**Tagesbericht-Ergänzung** (eine Zeile in `digest_tick`):
> „Eskalationen: 2 (davon 1 mit Weckton) · Ø Quittierungszeit 3,4 min ·
> 0 unbestätigt geblieben"

## 7. Abnahmekriterien

### 7.1 Offline-Logiktests (`edge-agent/tests/test_eskalation.py`, Stil `hilfe.Pruefer` mit injiziertem `jetzt`)

Die Szenarien 1–8 sind gegen eine Referenzimplementierung simuliert (27/27
grün) und damit als widerspruchsfrei belegt — sie sind direkt als Testtabelle
übernehmbar.

1. **Volle Kette:** Stufe 1 bei 5, Stufe 2 bei 10, Weckton bei 15, Weckton-Aus
   bei 20, Zyklus 2 bei 30, Zyklus 3 bei 45, „aufgegeben" danach.
2. **Quittierung stoppt in jeder Stufe** (bei 3 / 7 / 12 / 17 min): keine
   weitere Stufe, kein Weckton, und bei Quittierung während des Tons ein
   sofortiges „aus".
3. **Neustart mitten in der Eskalation** (Zustandsdatei nach Stufe 2, neue
   Instanz): keine Wiederholung von Stufe 1/2, kein Weckton innerhalb der
   120-s-Karenz, Weckton danach zur richtigen Zeit.
4. **Neustart nach Quittierung:** vollständige Stille — kein erneutes Öffnen,
   kein Weckton.
5. **App nicht erreichbar** (injizierter Client, der wirft): Kette läuft
   vollständig bis zum Weckton durch; mit `uplink_tot_verkuerzung` bei +8 statt
   +15; der Alarmtext enthält „konnte nicht geprüft werden".
6. **Evidenz-Gate:** Auslöser mit nur einer Erkennung → Stufe 1 und 2 laufen
   (Push kostet nichts), **Weckton wird unterdrückt** und protokolliert.
7. **Brunst und Info eskalieren nie** — auch nicht mit manipulierter Config.
8. **Uhrensprung 60 min vorwärts:** höchstens eine Stufe pro Tick (drei Ticks
   bis zum Weckton), keine Stufenkaskade.

Ergänzend ohne Simulationsbeleg, aber gleich verbindlich:

9. **Defekte Zustandsdatei** → Start ohne Weckton, Fehler im Log.
10. **Weckton-Ende:** `max_dauer_s` schaltet auch ohne jede Quittierung ab;
    nach `zyklen` ist endgültig Ruhe.
11. **Kalbeverdacht** eskaliert nur bei `wach_modus: true` und nie mit Weckton.
12. **Neue Episode nach Aufgabe:** derselbe Kuh/Typ 2 h später → neue
    `eskalations_id` → eskaliert wieder.
13. **Verkürzung ohne zweiten Empfänger:** leere
    `zweiter_empfaenger.telegram_chat_id` → Weckton bei +10 statt +15 min;
    gesetzter Zweitempfänger → unverändert +15 min.

### 7.2 Integrationstest gegen die echte App (einmalig bei Inbetriebnahme)

14. Alarm senden → ID aus der Antwort lesen → Abfrage liefert `null` → in der
    App quittieren → nächste Abfrage liefert Zeitstempel → Kette schließt.
    **Gemessen:** Zeit vom Tippen bis zum Kettenabbruch ≤ 35 s.
15. Falscher Token → 401 → gilt als unquittiert; fehlende Ingest-Env → 503 →
    dito.
16. Quittierung aus der **Push-Benachrichtigung** (nicht aus der geöffneten
    App) wirkt genauso.
17. **Offline-Warteschlange:** im Flugmodus quittieren, danach online → die
    Warteschlange spielt nach, der Agent erkennt es. Erwartetes und zu
    dokumentierendes Ergebnis: Hat der Ton in der Zwischenzeit ausgelöst, war
    das korrektes Verhalten.

### 7.3 Weckkanal-Abnahme (Praxis, Pflicht vor dem Scharfschalten)

18. **Hörprobe im Schlafzimmer bei geschlossener Tür.** Gemessen: Sekunden vom
    MQTT-Kommando bis zum hörbaren Ton (Ziel < 3 s).
19. **Alle vier Ausschaltwege einzeln geprüft:** Quittierung, `max_dauer_s`,
    geräteseitiger Totmann (Agent hart beenden → Ton verstummt binnen 60 s),
    LWT (Netzwerkkabel ziehen → Broker schaltet ab).
20. **Broker-Neustart während laufendem Ton** → der Ton startet **nicht** von
    selbst neu (Retain-Prüfung).
21. **Trockenübung `--eskalations-probe`:** ganze Kette mit 10-fach gestauchten
    Zeiten inklusive 3 s Ton. Gehört in die wöchentliche
    Alarmweg-TÜV-Routine (P2).
22. **Nacht-Nullprobe:** 7 Nächte im Normalbetrieb mit sofortiger Quittierung →
    **0 Wecktöne**. Erst danach gilt die Kette als eingeschwungen.

## 8. Risiken und Fehlerfälle

1. **Fehlalarm wird zum Weckton.** Die Fehlalarmrate der Erkennung ist ab
   Stufe 3 direkt die nächtliche Weckrate. Gegenmittel:
   `evidenz_min_erkennungen: 2` (bei 1 FPS erfüllt das jede echte Austreibung
   binnen 2 s, ein Einzelframe-Geist nie), Weckton nur für objektbasierte Typen
   (Konfidenz ≥ 0.80), „❌ Fehlalarm" bricht sofort ab. **Restrisiko bleibt und
   ist der stärkste Grund, die Kette erst nach belegter Fehlalarmrate < 1/Nacht
   scharfzuschalten** ([`metriken.md`](./metriken.md)).
2. **Eine Sirene im Stall stoppt die Geburt.** Fachlicher Widerspruch gegen die
   naheliegende Umsetzung: Stress im Stadium II hemmt die
   Oxytocin-Ausschüttung — ein Ton über der kalbenden Kuh kann die Austreibung
   verzögern und damit genau das Kalb gefährden, das der Alarm retten soll.
   Zusätzlich Vision-Prinzip 4 („Tierwohl ohne Eingriff"). **Das Weckgerät
   gehört ins Haus** (Funkgong, Summer oder Lampe im Schlafzimmer) — genau wie
   beim Autodialer-Vorbild, dessen Funk-Summer im Wohnhaus hängt. Steht nur ein
   Gerät im Stall zur Verfügung: **Lampe statt Ton.** Gehört als Kommentar in
   die Config und in die README.
3. **Quittierung hängt in der Offline-Warteschlange.** Der Landwirt ist wach,
   hat getippt, ist unterwegs — und der Ton kommt trotzdem, weil sein Handy
   kein Netz hat. Systematisch nicht vermeidbar (deshalb die drei redundanten
   Wege, davon einer im LAN). Der Alarmtext muss den Taster und den
   Telegram-Button nennen.
4. **Netzausfall + echter Alarm = Weckton.** Das ist gewollt, muss aber vorher
   kommuniziert sein, sonst wirkt es wie ein Defekt. Gehört in die README und
   in den Tagesbericht („Weckton ausgelöst, Grund: App nicht erreichbar").
5. **Crash-Loop weckt wiederholt.** Abgesichert durch monotone `stufe` +
   `karenz_nach_start_s` + Zustandsdatei; ohne alle drei feuert jeder Neustart
   erneut.
6. **Uhrensprung auf Systemen ohne RTC** (Raspberry Pi). Abgesichert durch den
   Uhrenschutz beim Laden und „eine Stufe pro Tick".
7. **Zwei Agenten, ein Weckgerät** → Gegeneinander-Schalten. Abgesichert durch
   genau einen `weckruf.aktiv`-Meister.
8. **Retained „an"** → Dauerton nach Broker-Neustart. Der klassische Fehler
   dieser Bauform; `retain: false` ist Pflichtbestandteil, nicht Stilfrage.
9. **Agent stirbt bei laufendem Ton** → LWT + geräteseitiger Totmann. Ohne
   mindestens einen der beiden ist der Ton unstoppbar.
10. **Ereignis-ID unbekannt, weil kein KV verknüpft ist.** Ohne Persistenz lebt
    die Ereignisliste pro Serverless-Instanz — eine andere Instanz kennt die ID
    nicht, meldet „unbekannt", und die Kette eskaliert, **obwohl quittiert
    wurde**. **Das ist der ernsteste Fehlerfall dieser Spec: Die Kette setzt
    aktivierte Ereignis-Persistenz (Roadmap P1) praktisch voraus.** Bis dahin
    bleibt `weckruf.aktiv: false` — Stufen 1–2 sind unschädlich, der Weckton
    wäre es nicht.
11. **Stufe 1 löst über den Ingest erneut Push aus** — beabsichtigt, aber
    `PUSH_MAX_ALTER_MINUTEN` (Default 30) muss größer bleiben als der letzte
    Stufenzeitpunkt, sonst schluckt der Nachlieferungsfilter die späten
    Wiederholungen. Bei den vorgeschlagenen Zeiten (max. 15 min) unkritisch,
    bei einer späteren Verlängerung der Profile zu prüfen.
12. **Feedback-Buttons und `getUpdates`:** Der Telegram-Quittierungsweg erbt
    die bestehende Einschränkung — der Bot darf keinen Webhook betreiben.
13. **Stromausfall legt die ganze Kette still — und niemand erfährt es.**
    Rechner, Router, Broker und Weckgerät hängen am selben Netz; fällt es aus,
    ist die Kette tot, und der Totmann-Wächter kann es nicht melden, weil der
    Uplink mit ausfällt. Genau der stille Ausfall aus Vision-Prinzip 6, nur
    eine Ebene tiefer. Die Nachbarkategorie hat das gelöst und wir nicht: Die
    Fachliteratur fordert ≥ 2 h Notstrom, das kommerzielle Agrar-Wählgerät
    liefert 30 h, der Sigloo-Empfänger 36–48 h. Gegenmittel und zugleich
    Roadmap-P2: eine USV (~40 €) an Rechner, Router und Broker; ein
    batteriebetriebener Funkgong oder eine akkugepufferte Zigbee-Sirene deckt
    die Geräteseite ab. **Bis dahin gehört die Lücke ausgesprochen** — in die
    README und in den Tagesbericht —, statt sie in der Nacht auffliegen zu
    lassen, für die wir werben.

### Was an dieser Spezifikation nicht belegt ist

Die Kette beruht auf der These, dass Landwirte nächtliche Alarme verschlafen
und App-Push allein nicht ausreicht. Die Recherche fand dafür **keinen
einzigen dokumentierten Fall** — kein Forenbeitrag, kein Fachartikel, in dem
ein Landwirt sagt, er habe einen Kalbealarm verschlafen. Was es gibt, sind
gemessene Schlafdaten (Ø 6 h 15 min in der Abkalbesaison, Kontrolle „alle 2–3
Stunden"), das dokumentierte Stummschalt-Verhalten von iOS Focus, und die
Tatsache, dass die gesamte Nachbarkategorie einen netzunabhängigen Weckkanal
für nötig hält. Das ist eine **plausible Herleitung, kein Beweis** — und die
Nacht-Nullprobe (§7.3 Punkt 22) ist deshalb nicht nur eine Abnahme, sondern
der erste eigene Datenpunkt.

## 9. Bewertung der Architektur-Entscheidung und Ausrollreihenfolge

Der Fachexperte wurde ausdrücklich um Widerspruch gebeten, falls die
Architektur-Entscheidung aus [`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md)
§4 (Timer am Edge, „unerreichbar = unquittiert", MQTT statt Tuya) fachlich
nicht trägt. **Er widerspricht ihr nicht:** Die Cloud kann bei toter Leitung
weder feststellen, ob jemand geweckt wurde, noch einen Ton auslösen;
„unerreichbar = unquittiert" ist die einzige Ausfallrichtung, die mit
Prinzip 5 verträglich ist. Drei Präzisierungen kamen aus der Detailplanung
hinzu und sind oben eingearbeitet:

- **Die Kette ist im Offline-Fall dünner, als sie aussieht.** Stufe 1 und 2
  laufen über dieselbe tote Leitung. Ohne die leitungsbewusste Verkürzung
  (§2.4) bedeutet „offline" faktisch: 15 Minuten Schweigen, dann Ton. Das ist
  verschenkte Kalbezeit.
- **Die reaktionsgetriebene Eskalation braucht ein Evidenz-Ventil**, das die
  inhaltliche nicht braucht. Die inhaltliche eskaliert nach 60 min anhaltender
  Erkennung — sie ist durch ihre Dauer selbst plausibilisiert. Die
  reaktionsgetriebene kann schon 15 min nach einem einzigen Frame den Ton
  ziehen. Deshalb `evidenz_min_erkennungen: 2`.
- **Ohne Ereignis-Persistenz ist die Abfrage nicht belastbar** (Risiko 10).

Daraus die verbindliche Reihenfolge:

1. **KV/Upstash-Store verknüpfen** (Roadmap P1, aktiviert sich selbst)
2. **Stufen 1–2 scharf** — modellunabhängig, keine Hardware, kein Ton
3. **Fehlalarmrate über 7 Nächte messen** (< 1/Nacht, [`metriken.md`](./metriken.md))
4. **Weckgerät im Haus installieren, §7.3 abnehmen, dann Weckton scharf**

## Ansatzpunkte im Code (bei Umsetzung)

| Datei | Änderung |
| --- | --- |
| `edge-agent/main.py` | `Notifier._dashboard()` gibt die Ereignis-ID zurück; `_mqtt()` wird um Subscribe erweitert; neue Klassen `EskalationsKette` und `Weckkanal` (Bauform-Vorbild: `TotmannWaechter`); Hauptschleife bekommt den `tick()`; `digest_tick()` bekommt die Eskalationszeile |
| `edge-agent/config.example.yaml` | Blöcke `eskalation` und `weckruf` aus §5 |
| `edge-agent/tests/test_eskalation.py` | Testtabelle aus §7.1 |
| `app/api/events/quittierungen/route.ts` | neuer Abfrage-Endpunkt (§3.2) |
| `middleware.ts` | Ausnahme für den neuen Endpunkt (Token statt Session) |
| `README.md` | „Netzausfall löst den Weckton aus", „Weckgerät gehört ins Haus", die Einkaufsliste aus [`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md) §1d (Zwischenstecker + tieffrequentes Weckgerät + Taster, ~66 €) und die offene Notstrom-Lücke (Risiko 13) |
