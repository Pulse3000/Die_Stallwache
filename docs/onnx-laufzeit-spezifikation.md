# ONNX-Laufzeit, Bildqualitäts-Gate, Kamerapräfix (B19–B21)

**Status:** 🔄 umgesetzt in `edge-agent/main.py` (05.11.2026). Review-Auflagen von `qa-waechter` und `ki-wache`
in drei Runden eingearbeitet; **qa-waechter: Freigabe, ki-wache: einverstanden** (10.11.2026). Testsuite grün. **Nicht scharfschalten**, bevor §6 entschieden ist: Gate D mit 1 Kern
nicht bestanden, vorbestehende Vertragsabweichungen 7a–7c.

Beschlüsse: B19–B21 (01.11.2026, vom Landwirt delegiert, Wortlaut in `ENTSCHEIDUNGEN.md` des Projekts und
`edge-agent/aufnahmen/_training_v1/ENTSCHEIDUNGEN_B18-B22.md`). Diese Datei ist die Begründung der Zahlen im Code.
Abweichungen vom Übergabe-Entwurf: §5.

## 0. Ort der Umsetzung

Inferenzpfad ist `edge-agent/main.py` (`InferenceEngine`). Begründung:

- Er ist der einzige Pfad im Repo, der `modell.pfad` und den Label-Vertrag nutzt (`modell.klassen`, `modell.keypoints`).
- Er läuft als Container `stallblick-agent` (`edge-agent/deploy-stallwache-lela/`).
- Sein Silent Mode hat den Trainingsdatensatz v1 gesammelt.

Nicht Teil dieser Umsetzung sind zwei andere Pfade:

- `kuhwatch/app/`: älterer Container mit Generaldetektor (COCO-Klassen, Unruhe-Alarm), ohne Label-Vertrag.
- Der Gateway-Code (`wache.py`, `pipeline.py`, `kalibrierung.py`): liegt nur in den Projekt-Dokumenten, nicht auf dem Hof-Rechner.

Welche Codebasis die scharfe Stallwache wird, entscheidet der Landwirt (§6).

## B19 – ONNX-Runtime-Inferenz

| Punkt | Festlegung |
| --- | --- |
| Grundsatz | `modell.pfad` = `.onnx` → ONNX Runtime (CPU). Vorverarbeitung und Dekodierung sind wörtlich aus `abnahme_gates.py` übernommen (`OnnxModell`, `dekodiere_pose`): quadratische Letterbox (Rand 114), RGB, /255, Mehrfach-Label für Fruchtblase und Kälberfüße, NMS je Klasse. Kein PyTorch-Faltungsaufruf im Laufzeitpfad. |
| Grenzen | Austreibung und Eskalation nie hinter Tracker, Fenster, Qualitätsfilter oder Kuh-Erkennung: Klassen 1/2 gehen aus **jedem** Bild ungetrackt in die Logik. Kein Frame-Upload (B7), keine laufenden Kosten (B8). Einzige neue Abhängigkeit: `onnxruntime`. Ultralytics bleibt nur für ByteTrack. |
| Schwellen | Logik (Schwanzwinkel, Brunst, Austreibung) sieht Objekte ab **0.25** (wie die Gates). ByteTrack bekommt Kuh-Boxen schon ab **0.10** (wie bisher Ultralytics `model.track`). Dekodierung ab 0.10 plus Filter ≥ 0.25 ergibt exakt die Objekte der Dekodierung ab 0.25, weil NMS nur von höher bewerteten Boxen abhängt; geprüft an 300 Zufallsausgaben. NMS-IoU 0.7. Austreibung ab `logik.override_konfidenz` (0.80, unverändert). Keypoint ab Sichtbarkeit **0.5** sichtbar, sonst kein Schwanzwinkel. Das ist dieselbe Schwelle, mit der Ultralytics 8.3.40 (Version im Agent-Image, `Keypoints.__init__`) unsichtbare Punkte bisher auf (0, 0) setzte. |
| Config | `modell.pfad: modelle/best_v1.onnx` · `modell.threads: 0` (= alle Kerne, die der Prozess bekommt: CPU-Affinität, Docker-Quote oder systemd `CPUQuota`; `cpus: 1` → 1) · `modell.konfidenz_min: 0.25` · `modell.tracker_konfidenz_min: 0.10` · `modell.nms_iou: 0.7` · `modell.keypoint_sichtbar_min: 0.5` · Bildgröße aus dem ONNX-Eingang. |
| Tracking | ByteTrack (Ultralytics `BYTETracker`, `tracker-kuh.yaml`) bekommt **nur Klasse `kuh`** als Pixel-xyxy + conf. Keypoints und Box der Kuh stammen aus der Detektion, wie in den Gates. Die bisherige Track-Box war Kalman-geglättet; das wirkt auf die Aufsprung-Heuristik. Die Track-ID kommt über den Detektionsindex (Ultralytics 8.3.40 und 8.4 geprüft). Kuh ohne bestätigten Track: ID −1, die Logik ignoriert sie wie bisher. Bilder ohne Kuh-Detektion und Defektbilder schreiben den Tracker nicht fort, wie `model.track` in 8.3. |
| Fehlerfälle | Modell lädt nicht (kein `.onnx`, Datei fehlt, Ausgabeform ≠ `4 + Klassen + 3 × Keypoints`, **Probe-Inferenz** auf einem Graubild scheitert, z. B. bei nicht quadratischem Eingang oder float16): Der Agent bleibt im Silent Mode. Er meldet das **einmal je Start per Telegram** (Text unten) und danach im Tagesbericht. ByteTrack fehlt beim Start: Austreibung aktiv, Meldung „eingeschränkt“. Laufzeitfehler, die länger als `stream.totmann_minuten` anhalten, ergeben je Episode eine Meldung, die Entwarnung kommt still. Das gilt für die ganze Auswertung („KI-WACHE AUS“) und für ByteTrack („EINGESCHRÄNKT“, nur wenn der Tracker wirklich lief). Eine Episode endet erst, wenn in der Frist mehr als 50 % der Durchläufe gut waren (`qualitaet.degradiert_anteil`, wie die Erholungsregel von B20). |
| Abnahme | (1) Unit-Test: Adapter == `dekodiere_pose` für feste Rohausgaben, Quelltext-Wächter gegen `abnahme_gates.py`. (2) Hof-Rechner: ≥ 1 FPS Ende-zu-Ende mit **1 Thread** (Container `cpus: 1`): **nicht erfüllt**, §3 und §6. (3) Identische Detektionen Agent vs. `abnahme_gates.py` auf 20 Bildern eines Val-Stalltags; vorläufig erfüllt, verbindlich mit `best_v1.onnx`. Gate B rechnet wie der Agent nur mit sichtbaren Punkten. Neues Gate **B2**: erhobene Schwänze dürfen höchstens 10 Prozentpunkte seltener messbar sein als anliegende (je n ≥ 30, wie Gate B). |
| Risiken | Abweichende Vorverarbeitung verfälscht die Gates; Gegenmittel: wörtliche Kopie plus Wächtertest. Zu viele Threads unter einer Quote drosseln; Gegenmittel: Thread-Zahl aus der Quote. Sichtbarkeit < 0.5 nimmt Bilder aus dem Nenner des Fensters, deshalb „Schwanzwinkel messbar: x %“ im Tagesbericht und Gate B2. Das Tracker-Verhalten hängt an der Ultralytics-Version im Image (8.3.40). |

## B20 – Bildqualitäts-Gate

| Punkt | Festlegung |
| --- | --- |
| Grundsatz | Jedes Bild im Analyse-Modus bekommt vor der Auswertung `defekt_anteil` (wörtlich aus `bildqualitaet.py`). Ein Defektbild liefert keine Kuh-Information. Es trägt nicht zum Schwanzwinkel-Fenster bei und macht keinen Tracker-Schritt. Aufsprung-Paare überstehen eine Lücke ohne auswertbares Bild nur bis `brunst_min_dauer_s`, bei längerer Lücke wird neu gemessen. Eine Kalibrierung gibt es im Agenten noch nicht; sobald sie kommt, gilt dieselbe Regel. |
| Grenzen | Austreibung und Eskalation laufen auf Defektbildern unverändert. Kein Bild wird für die Austreibung verworfen. Auf Defektbildern **hält die Uhr** der Austreibungs-Episode an, je Bild höchstens 2 Bildabstände (`2 / ziel_fps`): Nur intakte Minuten zählen für die 30-min-Frist. Ein Stream-Ausfall davor zählt wie bisher, den meldet der Totmann. Sonst käme die Eskalation nach einer Streifen-Phase bis zu 37 min zu spät. Neu starten wäre falsch, weil die Episode dann nachts nie endete und eine zweite Kalbung eine falsche oder gar keine Eskalation bekäme (Nachprüfung 10.11.). Austreibungs-Alarm auf einem Defektbild trägt den Zusatz „Bild gestreift – bitte Bildserie prüfen.“. Ein Fehler in der Qualitätsprüfung lässt das Bild als intakt durch. |
| Schwellen | `defekt_anteil` > 0.04 = Defektbild. Bildstörungs-Info, wenn > 50 % Defektbilder in den letzten 10 min (erst bei vollem Fenster), 1× je Episode, Ende nach 10 min ununterbrochen ≤ 50 %, Bildlücke > 10 min → Fenster füllt sich neu. **Blind:** Kommen `stream.totmann_minuten` lang nur gestreifte Bilder, ist das funktional ein Stream-Ausfall. Dann gibt es eine Telegram-Meldung mit Ton wie beim Totmann. Die Entwarnung kommt still, erst wenn in der Frist > 50 % der Bilder intakt waren; ein einzelnes intaktes Bild beendet die Episode nicht. Keine neue Zahl. |
| Config | `qualitaet.schwelle_defekt: 0.04` · `qualitaet.degradiert_anteil: 0.5` · `qualitaet.fenster_min: 10` · Abschalten: `schwelle_defekt: 1.0`. |
| UI-Texte | Dashboard (`typ: info`, kein Telegram, B12): „Bildstörungen (stallwache): 63 % der Bilder der letzten 10 min gestreift. Fruchtblase/Kälberfüße: Jedes Bild wird weiter geprüft, gestreifte Bildteile sind aber nicht auswertbar. Wehen-Verdacht nur aus ungestörten Bildern. Bitte Livebild und Stall-WLAN prüfen.“ Telegram (blind): „🔴 KI-WACHE BLIND (stallwache): Seit 5 min nur gestreifte Bilder – Fruchtblase und Kälberfüße sind so nicht sicher erkennbar. Bitte Abkalbekandidatinnen selbst kontrollieren und Kamera/WLAN prüfen. Entwarnung kommt automatisch.“ Tagesbericht: „Bildstörungen: 12 % der Bilder (318 von 2650) · Phasen über 50 %: 1×“. |
| Abnahme | Tests: Defektbild verändert das 30-min-Fenster nicht · Austreibung > 0.80 auf Defektbild → Sofort-Alarm mit Zusatz · Eskalation auf Defektbildern · 31 min Streifen beenden die Episode nicht · Aufsprung übersteht ein Defektbild, aber nicht 10 min · Info genau 1× je Episode · kein Telegram für die Info · Blind-Meldung nach 5 min, Entwarnung beim ersten ungestörten Bild · Zähler im Tagesbericht · Wächtertest `defekt_anteil`. Hof-Rechner: Kalibrierpfad und Agentenpfad klassifizieren dieselben Bilder gleich. |
| Risiken | Fehlalarm des Filters an Gittern führt zu weniger Schwanzwinkel-Bildern; die Quote im Tagesbericht beobachten. Die Schwelle ist an 36 Stichproben kalibriert. **Unbewiesene Vermutung zur Ursache:** Der Agent liest 1 Bild/s aus einem RTSP-Strom mit 15–25 FPS, ohne ihn leer zu lesen. Puffer-Überlauf und Paketverlust würden genau solche Streifen erzeugen, vor allem nachts (IR-Rauschen, höhere Bitrate). Test: das Livebild in der App nachts prüfen. Zeigt es keine Streifen, liegt die Ursache im Lesemuster des Agenten; Abhilfe wäre ein Lese-Thread, der nur das jüngste Bild behält. |

## B21 – Kamerapräfix im Silent Mode

| Punkt | Festlegung |
| --- | --- |
| Grundsatz | Silent-Mode-Bilder heißen `<kamera>_<YYYYmmdd-HHMMSS>.jpg` in **UTC**, unabhängig von der Zeitzone des Rechners. Bisher galt die Ortszeit des Prozesses: im Container UTC, unter systemd Europe/Berlin. Der Kameraname kommt aus `stream.kamera`, nur `a–z0–9`, und beginnt mit einem Buchstaben. |
| Grenzen | Bestehende Dateien werden nicht umbenannt. Die Werkzeuge lesen beide Formen: `cvat_zu_yolo_pose.py`, `abnahme_gates.py`, `stall_sichtung.py` (Suche im Namen) und `datensatz_inventur.py` (Vorlage; Präfix optional, Stalltag jetzt UTC → Europe/Berlin − 12 h wie der Konverter). |
| Abnahme | Test auf Namensmuster und UTC (auch bei `TZ=Europe/Berlin`). Werkzeuge erkennen beide Formen. Konsistenztest Label-Vertrag: CVAT-Schema v2 (`cvat_labels_stallwache_v2.json` im Repo, identisch mit der Trainingskopie) mit Box `kuh`, Skelett `kuh_pose` (spine_end, tail_base, tail_tip), `amniotic_sac`, `calf_legs` und Tag `geprueft`. Konverter, Gates und Edge-Konfig: Klassen `kuh, amniotic_sac, calf_legs` (0–2), Keypoints in derselben Reihenfolge, `flip_idx [0, 1, 2]`. |

## Meldungstexte bei Ausfall (Telegram, Wortlaut im Code)

Weckregel (B12-Auslegung, Ergänzung zu B20 vom 10.11.): „AUS“ und „BLIND“ wecken (Totmann-Prinzip); „EINGESCHRÄNKT“ weckt
zur Laufzeit nur im Wach-Modus, sonst Dashboard und Tagesbericht, weil die Austreibung weiterläuft. Entwarnungen gehen
still raus, auf demselben Kanal wie die Meldung, auch die des Stream-Totmanns. Der Tagesbericht nennt laufende Episoden im Modus („blind …“, „eingeschränkt …“, „KI-Wache AUS …“).


- **Modell lädt nicht:** „🔴 KI-WACHE AUS (stallwache): Es gibt KEINE Alarme – auch nicht bei Fruchtblase oder Kälberfüßen. Grund: {Grund}. Bis zur Behebung Abkalbekandidatinnen selbst kontrollieren. Behebung: {Handgriff} Technik: {Fehler}“
  - Gründe und Handgriffe: `.pt` statt `.onnx` · Datei nicht gefunden · Modell passt nicht zu Klassen/Keypoints · lässt sich nicht laden oder ausführen
  - Tagesbericht: „Modus: KI-Wache AUS – Modell nicht geladen (nur Bildersammlung)“
- **ByteTrack fehlt oder fällt aus:** „🟠 KI-WACHE EINGESCHRÄNKT (stallwache): Fruchtblase und Kälberfüße werden weiter gemeldet. AUS sind Wehen-Verdacht (Schwanzwinkel) und Brunst, weil die Kuh-Wiedererkennung fehlt. …“
- **Auswertung fällt dauerhaft aus:** „🔴 KI-WACHE AUS (stallwache): Die Bildauswertung schlägt seit 5 min fehl – es gibt KEINE Alarme, auch nicht bei Fruchtblase oder Kälberfüßen. …“, mit Entwarnung
- **Nur gestreifte Bilder:** siehe B20.

## 3. Messungen am Hof-Rechner (05.11.2026)

Cowork-VM auf dem Hof-Rechner (AMD A6-3650, 2 vCPU, ohne SSSE3/SSE4.1/AVX), ONNX Runtime 1.23, Laufzeittest-Modell
`laufzeittest_yolov8n-pose_3kpt_640.onnx` (YOLOv8n-Pose, Zufallsgewichte, gleiche Rechenlast wie `best_v1.onnx`),
30 Bilder 2560×1440 vom Val-Stalltag 2026-10-18.

| Messung | 1 Thread (= Container `cpus: 1`) | 2 Threads |
| --- | --- | --- |
| `abnahme_gates.py laufzeit` Ende-zu-Ende (Lesen + Qualität + Inferenz) | 0,94 FPS (kalter Plattencache: 0,72) | – |
| nur Inferenz | 1,02 FPS | – |
| Agentenpfad `werte_bild_aus` (Qualität + ONNX + Dekodierung + Logik) | 1,05 FPS (951 ms) | 1,83 FPS (547 ms) |
| Agentenpfad + JPEG-Lesen (64 ms) | 0,99 FPS | 1,64 FPS |

Gate D (≥ 1 FPS Ende-zu-Ende) besteht mit 2 Kernen, mit 1 Kern nicht. Die Rechenarbeit je Bild beträgt in beiden Fällen
etwa 1 Kern-Sekunde. Bei `ziel_fps: 1.0` erzeugt `cpus: 2` deshalb im Mittel dieselbe Wärme wie heute ein voll
ausgelasteter Kern; der zweite Kern verkürzt nur die Spitze.

Weitere Belege:

- **B19 (3), vorläufig:** 20 von 20 Bildern desselben Val-Stalltags liefern im Agenten exakt die Objekte von
  `abnahme_gates.OnnxModell`. Das sind 17 240 Objekte, davon 11 480 Austreibungsklassen. Verglichen wurde mit
  Kandidatenschwelle 0,001, weil die Zufallsgewichte Scores unter 0,005 liefern.
- **B20:** Kalibrierpfad und Agentenpfad klassifizieren 556 von 556 Bildern gleich. Alle 302 aussortierten Defektbilder
  werden erkannt, alle 254 intakten Manifest-Bilder bleiben intakt. Die mittlere Abweichung des Anteils beträgt
  0,0004. `defekt_anteil` braucht am Vollbild 12 ms (Median).
- **ByteTrack:** Der echte `BYTETracker` mit `tracker-kuh.yaml` besteht unter Ultralytics 8.3.40 und 8.4.197. Eine
  image-nahe Umgebung (Python 3.11, numpy 1.26, OpenCV 4.10, ONNX Runtime 1.31) lässt die ganze Suite grün laufen
  (Cloud-Sitzung; in der VM fehlt Ultralytics).
- **Smoke:** Der Silent Mode schreibt `stallwache_<UTC>.jpg`. Der Analyse-Modus lädt das ONNX mit 1 Thread und
  Probe-Inferenz und meldet einen fehlenden Tracker als „eingeschränkt“. Eine fehlende Modelldatei führt zu
  „KI-WACHE AUS“, Silent Mode und Datensammlung.

## 4. Praxis-Abnahmen (gehören in den PR als offene Punkte)

1. Laufzeit **im Container** (`cpus: 1` bzw. 2) mit echtem RTSP. Gate D um p99-Bildabstand und Bildalter ergänzen
   (Kamera-OSD-Zeit gegen Agentenzeit). Aus der Sitzung nicht erreichbar.
2. B19 (3) mit `best_v1.onnx` auf 20 gelabelten Val-Bildern (nach dem ersten Training), Gates B und B2.
3. `bytetrack-tuning` mit dem ersten Modell (ID-Wechsel nachts).
4. B20: Defektquote der ersten Analyse-Nächte im Tagesbericht gegen die 11,7 % aus dem Datensatz halten.
5. Telegram-Zustellung der neuen Systemmeldungen am Handy prüfen.

## 5. Abweichungen und Ergänzungen gegenüber dem Übergabe-Entwurf (`UEBERGABE_AGENT_B19-B21.md`)

| Entwurf | Umsetzung | Grund |
| --- | --- | --- |
| UI-Text „… Schwanzwinkel-Auswertung pausiert.“ | Text „Bildstörungen …“ (B20) | Es fallen nur Defektbilder heraus. Ob gestreifte Bildteile eine Fruchtblase zeigen, ist ungeprüft; der Text verspricht das nicht mehr (ki-wache). |
| Kandidaten ab 0.25 (auch Tracker) | Tracker ab 0.10, Logik ab 0.25 | Mit 0.25 verliert eine Kuh, die länger als 90 Bilder unter 0.25 fällt (nachts, seltene Liegepose), ihre ID. Jede neue ID startet das 30-min-Fenster neu (ki-wache, mit echtem BYTETracker simuliert). Die Gate-Gültigkeit bleibt (300/300). |
| `modell.threads` Standard „alle Kerne“ | alle Kerne, **die der Prozess bekommt** | Im Container sieht ONNX Runtime 4 Kerne, die Quote erlaubt 1 → Drosselung. |
| Validierung `pytest -q` | `python3 edge-agent/tests/alle_tests.py` | Konvention des Repos (kein pytest auf dem Hof-Rechner). Rückgabewert 77 = übersprungen (Abhängigkeit oder Daten fehlen), getrennt ausgewiesen; datenabhängige Prüfungen stehen in eigenen Dateien. |
| — | Keypoint-Sichtbarkeit ≥ 0.5 | Bisher setzte Ultralytics 8.3.40 unsichtbare Punkte auf (0, 0). Daraus entstanden Scheinwinkel, z. B. 146° bei verdeckter Schwanzspitze, und damit falsche Kalbeverdachts-Treffer. |
| — | `.pt` startet nicht mehr den Analyse-Modus | Auf dem Hof-Rechner bricht PyTorch bei jeder Faltung ab, und die Gates gelten nur für ONNX. |
| — | Kuh-Box = Detektionsbox statt geglätteter Track-Box | So ist sie gleich den Gates. Die Aufsprung-Heuristik sieht ungeglättete Boxen (qa-waechter N6). |
| — | Probe-Inferenz, Ausfall-Wächter (Auswertung, Tracker, blind) | Ein Modell, das lädt, aber nicht läuft, und ein Dauerfehler zur Laufzeit wären sonst still gewesen (qa-waechter M1, ki-wache). |
| — | Brunst-Lücke ≤ `brunst_min_dauer_s`, Austreibungs-Episode nur über intakte Bilder | Sonst „Aufsprung 601 s“ aus zwei Einzelbildern bzw. Eskalation bis 37 min zu spät (ki-wache). |
| — | Gate B nur mit sichtbaren Punkten, neues Gate B2 (Messbarkeit, je n ≥ 30) | Gate B hätte sonst nicht für den Agenten gegolten (ki-wache). |
| — | Austreibungs-Uhr auf Defektbildern anhalten (nicht neu starten, je Bild ≤ 2 Bildabstände), Wächter mit Erholungs-Hysterese, Tracker-Wächter nur nach echtem Aufruf, Weckregel | Nachprüfung 10.11.: Neustart der Frist hielt die Episode nachts offen; ein intaktes Bild beendete Blind-Episoden (19 Meldungen je Stunde); „nicht aufgerufen“ galt als gesund. |

## 6. Offene Entscheidungen für den Landwirt (vor dem Scharfschalten)

1. **Gate D:** `cpus: 2` für `stallblick-agent` (Empfehlung; bei `ziel_fps: 1.0` gleiche mittlere Last), am besten
   zusammen mit Punkt 3. Alternativ `cpus: 1` lassen und Gate D per Beschluss lockern. Kein 512er-Eingang: neues
   Training, Recall-Risiko für kleine Fruchtblasen.
2. **Scharfe Stallwache** in `edge-agent` oder im Gateway-Code (`wache.py`/`pipeline.py` mit Kalibrierung)? Die hier
   gebauten Teile (Dekodierung, Qualitäts-Gate, Wächter) sind in beide übertragbar.
3. **`kuhwatch-stallwache` abschalten**, sobald `best_v1.onnx` scharf ist. Zwei Erkennungs-Apps bedeuten doppelte
   Telegram-Alarme und zwei Kerne Dauerlast.
4. **Vorbestehende Abweichungen vom Vertrag (ki-wache 7a–c), nicht Teil von B19–B21:**
   - a) **Scharfschalt-Sperre, kein Wahlpunkt:** Die Austreibung läuft im `Notifier` durch den 15-min-Cooldown.
     Ein Fehlalarm um 02:00 verzögert eine echte Fruchtblase ab 02:10 bis 02:15. Der Vertrag verbietet das,
     Gate A2 setzt keinen Cooldown voraus. Zu entscheiden ist nur das Wie. Vorschlag: kein Cooldown; bei
     anhaltender Erkennung ohne Quittung Wiederholung nach +5 min; ❌ hebt die Sperre sofort auf.
   - b) Der Kalbeverdacht urteilt schon ab 20 Bildern (Wach-Modus ab 10 Bildern und 10 %). Koten mit 5 Bildern
     Schwanz hoch löst nach 20 s Alarm aus, faktisch ein Einzelereignis-Trigger. Vorschlag: Urteil erst ab 20 min
     Fensterabdeckung und ≥ 50 % der erwarteten Bilder (Beschluss nötig).
   - c) Telegram-, Dashboard- und Feedback-Aufrufe laufen synchron in der Schleife. Hängt `getUpdates`, wertet der
     Agent in 10 min nur rund 55 statt 571 Bilder aus. Vorschlag: Versand und Abruf in einen Worker-Thread.
     Solange das so ist, kommen bei hängendem Netz nur ~alle 10 s Bilder; die auf 2 Bildabstände gedeckelte
     Uhr-Pause zählt dann den Großteil der Defekt-Zeit als intakt (Austreibungs-Episode kann früher enden).
   - d) Rohwinkel mit Anteil 0.20 statt B16 (kalibrierter Ausschlag, 60 %). Bekannt.
