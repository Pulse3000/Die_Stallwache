# Spezifikation: Bildfrische (analysiert wird das Jetzt, nicht der Puffer)

Härtung nach der Reifegrad-Regel („Härtung vor Features“). Betrifft beide
Edge-Implementierungen: den Edge-Agenten (`edge-agent/main.py`) und
kuhwatch, das derzeit auf stallwache-lela läuft. Entwurf und Übernahme:
Orchestrator (23.10.2026). **Status: umgesetzt, an einem echten RTSP-Stream
gemessen (Teststrecke). Abnahme an der Stallkamera offen (Kriterien 9–10).**

## 0. Befund

OpenCV (FFmpeg-Backend) dekodiert einen Livestream streng der Reihe nach.
`cap.read()` liefert das *nächste* Bild im Puffer, nicht das aktuelle. Beide
Agenten lesen viel langsamer, als die Kamera sendet:

| Agent | Analysetakt | Kamera | Bilder je Lesevorgang im Video |
| --- | --- | --- | --- |
| Edge-Agent | 1 Bild/s (`ziel_fps`) + Inferenz | 15–25 fps | 1 von 25 gesendet, 24 bleiben im Puffer |
| kuhwatch | 1 Bild/5 s (`ANALYSIS_INTERVAL`) | 15–25 fps | 1 von 125 gesendet, 124 bleiben im Puffer |

`CAP_PROP_BUFFERSIZE = 1` (Edge-Agent) wirkt beim FFmpeg-Backend nicht.

**Messung (23.10.2026)** an einem echten RTSP-Stream: MediaMTX v1.9.3,
H.264 720p25, Sendezeit als Binärcode in jedes Bild eingebrannt
(`edge-agent/tests/bildfrische/`). Gemessen wurden die *unveränderten* Leser.

| Laufzeit | Bildalter kuhwatch | Bildalter Edge-Agent |
| --- | --- | --- |
| 7 s | 6,1 s | 6,3 s |
| 52 s | 50,7 s | 47,6 s |
| 102 s | 100,4 s | 96,6 s → Server trennt, Neuverbindung, Alter fällt auf ~1 s |
| 207 s | 204,6 s | 95,6 s (wächst wieder) |
| 227 s | **224,4 s** | 112,9 s |

Zwei aufeinanderfolgende analysierte Bilder lagen im Video **0,040 s**
auseinander (Median). Die Agenten glaubten, 1 Bild/s bzw. 1 Bild/5 s
auszuwerten. MediaMTX meldete „write queue is full“: Ab da verwirft der
Server Pakete, der Dekoder liefert verschmierte Bilder („error while
decoding MB“). Nach ~60 s trennt er den Leser. kuhwatch lebte danach noch
minutenlang vom lokalen Puffer.

### Folgen für die Erkennungslogik

1. **Austreibung (Recall 100 %):** Die Fruchtblase wird erst gemeldet, wenn
   der Puffer bei ihr ankommt — mit Minuten Verspätung. Das bricht das
   Kernversprechen „Alarm, bevor ein Mensch es bemerkt hätte“.
2. **Zeitfilter Kalbeverdacht:** Das „30-Minuten-Fenster“ enthält 1.800
   Bilder im Abstand von 40 ms, also **72 s Video**. Ein Schwanzheben beim
   Koten (15–30 s) füllt 20–40 % des Fensters, weit über der 20-%-Schwelle.
   Der Filter, der laut Vertrag Koten und Fliegenabwehr von Wehen trennen
   soll, ist damit faktisch ein Ein-Minuten-Filter.
3. **Brunst ≥ 4 s:** 4 s Uhrzeit entsprechen 3–4 Bildern, also ~0,15 s
   Video. Ein kurzes Anstoßen zählt als Aufsprung.
4. **kuhwatch-Unruhe:** Die 25-px-Bewegung wird zwischen Bildern im Abstand
   von 40 ms gemessen statt 5 s.
5. **Totmann-Meldung:** Nach dem Trennen durch den Server liefert der lokale
   Puffer weiter „Bilder“. Der Ausfall wird spät oder gar nicht bemerkt.
6. **Silent Mode:** Trainingsbilder tragen die Uhrzeit des Speicherns, zeigen
   aber Minuten Altes. Der Split nach Stalltagen liest die Zeit aus dem
   Dateinamen.
7. **Verschmierte Bilder** nach verworfenen Paketen gehen in Analyse,
   Freeze-Watchdog und Trainingsdatensatz.

Nicht betroffen sind das Snapshot-Polling (jede Anfrage holt das aktuelle
Bild) und das Abspielen einer Datei: Dort ist die Reihenfolge der Bilder die
Wahrheit.

## 1. Grundsatz

1. **Analysiert wird das jüngste Bild, das die Kamera geliefert hat — nie ein
   Bild aus dem Puffer.**
2. Ein Hintergrund-Thread je Kamera (*Bildgreifer*) liest den Livestream
   ständig mit und verwirft alles außer dem jüngsten Bild. Die
   Analyseschleife holt sich nur dann ein Bild, wenn sie eines braucht.
3. **Ohne nachgewiesene Frische gibt es kein Bild.** Hat der Greifer seit
   5 s kein neues Bild bekommen, liefert er nichts. Für Totmann und
   Lebenszeichen gilt das als Ausfall, für die Logik als fehlendes Bild.
   Lieber eine Lücke als ein Bild, das so tut, als sei es von jetzt.
4. **Der Verbindungsaufbau blockiert die Analyseschleife nie.** Der Greifer
   verbindet im eigenen Thread. Totmann, Tagesbericht und Feedback ticken
   weiter, auch wenn der Kamera-Host nicht antwortet. Dasselbe gilt für eine
   ausgefallene Kamera neben einer funktionierenden (kuhwatch, mehrere
   Kameras).
5. **Dateien bleiben sequenziell.** Replay und Fehlalarm-Budget
   (`training/abnahme.py`, `stream.url` auf eine Datei) lesen weiter Bild für
   Bild. Ein Greifer würde dort Bilder verwerfen.

## 2. Regeln

| Nr. | Regel |
| --- | --- |
| R1 | **Live oder Datei:** Live ist eine URL mit Schema `rtsp`, `rtsps`, `rtmp`, `rtmps`, `http`, `https`, `udp`, `tcp` oder `srt`. Alles andere ist eine Datei. |
| R2 | **Greifen statt Lesen:** Der Greifer ruft fortlaufend `grab()` auf (dekodieren, ohne Farbumwandlung). Nur auf Abruf folgt einmal `retrieve()`. Nur der Greifer-Thread berührt die `VideoCapture`; die Übergabe läuft über ein Ereignis. Das jüngste Bild ist damit immer das nach dem Abruf gegriffene. |
| R3 | **Frische:** Ein Abruf liefert nur ein Bild, wenn der letzte erfolgreiche `grab()` höchstens 5 s zurückliegt. Die Wartezeit auf die Übergabe ist auf 2 s begrenzt. |
| R4 | **Timeouts:** Öffnen und Lesen sind auf je 10 s begrenzt (`CAP_PROP_OPEN_TIMEOUT_MSEC`/`CAP_PROP_READ_TIMEOUT_MSEC`, sofern die OpenCV-Version sie kennt; sonst gilt der OpenCV-Standard von 30 s). |
| R5 | **Reconnect mit exponentiellem Backoff:** 5 → 10 → 20 → 40 → 60 s (Deckel). Zurückgesetzt wird erst nach dem ersten erfolgreich gegriffenen Bild. Die Cloud-Quelle holt bei jedem Versuch eine frische URL (wie bisher), jetzt im Greifer-Thread. |
| R6 | **Snapshot-Fallback (Edge-Agent):** Nach 5 Abrufen in Folge ohne frisches Livebild nutzt der Agent das Snapshot-Polling, sofern `fallback_snapshot_url` gesetzt ist (wie bisher). **Neu:** Sobald der Greifer wieder frisch ist, gewinnt der Livestream. Bisher blieb der Agent nach einem kurzen WLAN-Aussetzer für immer im Snapshot-Polling. Jeder Wechsel steht genau einmal im Log. |
| R7 | **Tracker je Kamera (kuhwatch):** Jede Kamera hat ihre eigene Modell- und ByteTrack-Instanz. Ein gemeinsamer Tracker vermischt die Bilder mehrerer Kameras. Kuh-IDs springen dann, und ein Kamerawechsel sieht aus wie eine Bewegung. |
| R9 | **Rückstand des Greifers:** Dekodiert der Rechner langsamer, als die Kamera sendet, entsteht der Puffer im Greifer selbst. Der Greifer vergleicht die Uhrzeit mit den Zeitstempeln des Streams (`CAP_PROP_POS_MSEC`, nur wenn sie steigen; Basis ist der Punkt mit dem kleinsten Rückstand). Ab 5 s Rückstand: Warnung im Log (höchstens 1×/h) mit dem Rat zum Substream. Ab 10 s: neu verbinden, das verwirft den Rückstand (Logzeile höchstens 1×/h mit Zähler). Quellen ohne Zeitstempel prüft er nie. |
| R8 | **Fehler des Greifers bleiben im Greifer.** Eine Ausnahme im Thread wird geloggt (voller Traceback höchstens einmal pro Stunde), die Verbindung geschlossen, der Backoff greift. Der Thread endet nie von selbst. |

## 3. Konfiguration

**Keine neuen Regler.** Frischegrenze (5 s), Übergabe-Wartezeit (2 s),
Timeouts (10 s), Rückstandsgrenzen (5 s/10 s) und Backoff-Stufen sind technische Konstanten, keine
Fachschwellen (wie `KEYPOINT_SICHTBAR_AB`). `stream.ziel_fps` behält seine
Bedeutung: der Takt, in dem die Analyse ein Bild abruft. Ebenso
`ANALYSIS_INTERVAL` in kuhwatch.

kuhwatch erhält die Totmann-Meldung des Edge-Agenten je Kamera
(`TOTMANN_MINUTES`, Default 5, 0 = aus). Ohne sie hieße Schweigen bei einem
Kameraausfall „alles ruhig“. Die Meldung folgt `SILENT_MODE` wie jede andere
Telegram-Nachricht von kuhwatch.

## 4. Texte

Keine neuen Alarmtexte im Edge-Agenten. Dort gibt es nur Logzeilen:

- `RTSP instabil – wechsle auf Snapshot-Polling.` (wie bisher)
- `Livestream wieder frisch – zurück vom Snapshot-Polling.` (neu)
- `Stream verbunden, Bildgreifer läuft.` / `Stream nicht erreichbar – nächster Versuch in N s.`

kuhwatch (Telegram, nur bei `SILENT_MODE=0`):

- Ausfall: `⚠️ Kamera N liefert seit M min kein Bild – das dritte Auge ist blind. Bitte Kamera, Strom und WLAN prüfen.`
- Entwarnung: `✅ Kamera N liefert wieder Bilder (Ausfall M min).`

## 5. Grenzen

- **CPU:** H.264 lässt sich nur vollständig dekodieren. Der Greifer
  dekodiert jedes gesendete Bild, das kostet Rechenzeit. Auf der Teststrecke
  waren es 2 % eines Kerns (Abschnitt 7). Auf der AMD A6-3650 von stallwache-lela ist
  mit einem Vielfachen zu rechnen. Wird die Last zu hoch, nimmt man den Substream der Kamera bzw.
  von go2rtc. Beide Agenten verkleinern ohnehin auf 640 px bzw. die
  Modellauflösung, der Hauptstream bringt der Analyse nichts.
- Der Bildgreifer behebt **nicht** die Fehlerkennungen des generischen
  COCO-Modells in kuhwatch (siehe Risiko 4). Er sorgt nur dafür, dass das
  Modell das richtige Bild sieht.

## 6. Abnahmekriterien

Teststrecke (reproduzierbar, `edge-agent/tests/bildfrische/README.md`):
MediaMTX, 25-fps-Quelle mit eingebrannter Sendezeit, Messung des Bildalters
je analysiertem Bild.

| Nr. | Kriterium | Wo |
| --- | --- | --- |
| 1 | Bildalter ≤ 1 s über ≥ 4 min bei 1 Bild/s (Edge-Agent) und 1 Bild/5 s (kuhwatch). Vorher bis 224 s | Teststrecke |
| 2 | Abstand aufeinanderfolgender analysierter Bilder im Video ≈ Analysetakt (1 s bzw. 5 s). Vorher 0,040 s | Teststrecke |
| 3 | Datei als Quelle: jedes Bild wird der Reihe nach gelesen, keines verworfen | Logiktest |
| 4 | Server gestoppt: spätestens 5 s danach kein Bild mehr. Server zurück: frisches Bild spätestens nach Backoff-Deckel + 5 s | Teststrecke + Logiktest |
| 5 | Nicht erreichbarer Host: ein Abruf kehrt in ≤ 2,5 s zurück, die Hauptschleife tickt weiter | Logiktest |
| 6 | Snapshot-Fallback nach 5 Abrufen ohne frisches Livebild. Rückkehr zum Livestream, sobald er frisch ist | Logiktest |
| 7 | kuhwatch: zwei Kameras haben getrennte Tracker. Eine tote Kamera bremst die andere nicht | Logiktest |
| 8 | kuhwatch: genau 1 Totmann-Meldung je Ausfall und genau 1 Entwarnung | Logiktest |
| 9 | **Am Gerät:** Nach ≥ 1 h Laufzeit weichen die Kamera-Uhr (OSD im Bild) und die Uhrzeit im Dateinamen eines Trainingsbilds (Edge-Agent) bzw. im Log (kuhwatch) um < 5 s ab | stallwache-lela, offen |
| 10 | **Am Gerät:** CPU-Last des Greifers mit dem echten Stream gemessen. Über 50 % eines Kerns wird auf den Substream umgestellt | stallwache-lela, offen |

## 7. Ergebnis der Messung nach der Umsetzung (23.10.2026)

Gleiche Teststrecke wie Abschnitt 0 (MediaMTX, 720p25, 2 Mbit/s), je 240 s,
Analyse mit 1 Bild/s und 0,4 s simulierter Inferenz (Edge-Agent) bzw. einem
Bild je 5 s (kuhwatch).

| Messung | Bildalter Median | Bildalter max | Abstand im Video (Median) | Abrufe ohne Bild |
| --- | --- | --- | --- | --- |
| früheres Lesemuster (`messung.py puffer`) | 56,9 s | 126,1 s | 0,040 s | 0 von 232 |
| Edge-Agent neu (`messung.py agent`) | **0,17 s** | **0,18 s** | **1,000 s** | 2 von 241 (Verbindungsaufbau) |
| kuhwatch neu (`tests/messe_bildalter.py`, 1 Bild je 5 s) | **0,17 s** | **0,17 s** | **5,04 s** | 2 von 50 (Verbindungsaufbau) |
| Edge-Agent neu, Rechner zu langsam (`--bremse 0.06`: 10 statt 25 Bilder/s) | 5,8 s | 11,2 s | 0,680 s | 6 von 147 (Neuverbindungen) |

**Ausfall (Kriterium 4), zwei Läufe:**

- MediaMTX 17:20:50 beendet, 17:21:03 neu gestartet. Der Greifer bemerkte
  das Ende sofort (Verbindung zu), versuchte es nach 5 s und 10 s erneut und
  war 17:21:08,5 verbunden. Ab dem nächsten Abruf lag das Bildalter wieder
  bei 0,17 s, also 5,5 s nach Rückkehr des Servers. Befund in diesem Lauf:
  Die Abrufe in den ersten 5 s nach dem Ende warteten je bis zu 2 s auf ein
  Bild, das ohne Verbindung nicht kommen konnte. Seitdem gilt nach dem
  Schließen der Verbindung kein Bild mehr als frisch.
- MediaMTX 17:23:06 beendet, 17:23:22 neu gestartet. Ab 17:23:06 kam
  „kein Bild“ ohne Wartezeit, im Takt von 1 s. Der Versuch um 17:23:21
  kam 1 s zu früh, der nächste folgte nach 20 s Backoff. Verbunden war der
  Greifer um 17:23:43,6, frisch ab 17:23:44,5, also 22 s nach Rückkehr. Das
  liegt innerhalb der Grenze Backoff-Deckel + 5 s = 65 s.

**Ganzer Agent (Kriterium 9 auf der Teststrecke):** `main.py` im Silent
Mode (Aufnahme alle 10 s) gegen den Teststream, 80 s. Alle 8
Trainingsbilder zeigen eine Sendezeit aus derselben Sekunde, die ihr
Dateiname nennt. Vorher hätte ein Bild nach 2 min Laufzeit rund 2 min alten
Inhalt unter der aktuellen Uhrzeit abgelegt.

Zum Fall „Rechner zu langsam“: Mit einer Neuverbindung erst ab 30 s Rückstand
pendelte das Bildalter bei 16–21 s. MediaMTX verwarf Pakete, die Bilder
waren verschmiert. Deshalb liegt die Grenze bei 10 s (R9).

**CPU:** Der ganze Messprozess (Greifer mit Dekodierung von 25 Bildern/s,
Abruf und Auswertung) brauchte 2 % eines Kerns (4-Kern-Cloud-Rechner).
Auf der A6-3650 bleibt das Kriterium 10 offen.

## 8. Risiken

1. **CPU auf alter Hardware** (Abschnitt 5). Gegenmittel: Substream.
   Kriterium 10 entscheidet.
2. **Hängender `grab()`** bei einem Stream, der keine Daten mehr liefert,
   die Verbindung aber offen hält: Der Lese-Timeout (10 s) beendet ihn.
   Bis dahin liefert die Frischegrenze (5 s) schon kein Bild mehr. Die
   Analyse wartet höchstens 2 s je Abruf.
3. **Kamera mit sehr niedriger Bildrate** (manche IR-Nachtmodi < 1 fps):
   Die Übergabe wartet bis zum nächsten gegriffenen Bild, höchstens 2 s.
   Unter 0,5 fps liefert ein Abruf manchmal nichts. Kriterium 9 zeigt das am
   Gerät.
4. **kuhwatch bleibt fachlich unbelegt:** Das generische COCO-Modell
   (`yolov8n.onnx`, Klassen inkl. Person/Bus/Zug) kennt weder Fruchtblase
   noch Keypoints. Die „Abkalbung“-Meldung beruht allein auf Bewegung der
   Boxen. Das widerspricht „keine Alarme ohne Modell-Befund“. Der Bildgreifer
   ändert daran nichts. Die Entscheidung kuhwatch oder Edge-Agent im Silent
   Mode auf stallwache-lela steht weiter aus (`roadmap.md`).
5. **Speicher:** Je Kamera wird ein Bild gehalten. Die Track-Historie von
   kuhwatch wuchs bisher mit jeder neuen ByteTrack-ID unbegrenzt. Jetzt wird
   sie wie im Edge-Agenten freigegeben, sobald eine ID länger als das
   Fenster nicht gesehen wurde.
