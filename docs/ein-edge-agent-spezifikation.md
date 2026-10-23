# Spezifikation: Ein Edge-Agent (kuhwatch geht im Edge-Agenten auf)

Entscheidung: Betreiber, 23.10.2026 („Mache aus den beiden Agenten 1“).
Entwurf und Umsetzung: Orchestrator. **Status: im Repo umgesetzt, das
Container-Image ist an einem echten RTSP-Stream geprüft. Der Umstieg auf
stallwache-lela ist offen (Betreiber; Skript liegt bereit).**

## 0. Ausgangslage

Zwei Agenten erledigten dieselbe Aufgabe:

| | kuhwatch | Edge-Agent (`edge-agent/main.py`) |
| --- | --- | --- |
| Läuft auf | stallwache-lela (Docker) | Referenz im Repo, `setup.sh`/systemd, Termux |
| Modell | allgemeines COCO-Modell `yolov8n.onnx` | eigenes YOLO-Pose-Modell (`best.pt`) nach Abnahme |
| Erkennung | „Unruhe“: Box springt > 25 px in ≥ 20 % eines 30-min-Fensters → „Abkalbung-Alarm“ | Kalbeverdacht (Schwanzwinkel), Austreibung (Fruchtblase/Kälberfüße), Eskalation, Brunst |
| Ohne Modell | – (Modell ist Pflicht) | Silent Mode: Trainingsbilder sammeln |
| Alarmwege | Telegram | Telegram (Album, Feedback-Tasten), Dashboard/Push, MQTT |
| Robustheit | Bildgreifer, Totmann (erst seit kuhwatch#2) | Bildgreifer, Totmann, Lebenszeichen, Freeze-Watchdog, Offline-Puffer, Versand-Entkopplung |
| Tests | 35 Checks | rund 470 Checks |
| Gerätewissen | alte CPU ohne AVX, gepinnte Pakete, Offline-Wheels, Docker, Temperaturwächter | – |

Jeder Fix musste zweimal gebaut werden, zuletzt die Bildfrische. Auf dem
Stallrechner lief ausgerechnet der schwächere Agent. Er sammelte keine
Trainingsbilder und blockierte damit den nächsten Meilenstein (erstes
Modell).

## 1. Grundsatz

1. **Es gibt genau einen Edge-Agenten: `edge-agent/main.py`.** kuhwatch wird
   nicht weiterentwickelt. Sein Repo bleibt nur für den Rückweg bestehen.
2. **Übernommen wird das Gerätewissen von kuhwatch, nicht seine Erkennung.**
3. **Der Unruhe-Alarm entfällt.** Er war kein Modell-Befund. Er beruhte auf
   COCO-Boxen inklusive Person, Bus und Zug, und Bewegung ist kein
   Geburtszeichen. Er widerspricht damit „keine Alarme ohne Modell-Befund“.
   Auf stallwache-lela läuft der Agent im **Silent Mode**, bis ein eigenes
   Modell die Abnahme besteht (Skill `modell-training`).
4. **Widerspruch, ausdrücklich:** Bis zum ersten Modell meldet der
   Stallrechner keine Kalbung. Fachlich tat er das vorher auch nicht. Neu
   ist nur, dass es ehrlich angezeigt wird: Das Lebenszeichen meldet
   `silent`, die Statusabfrage sagt `UNBEKANNT` statt `OK`. Totmann,
   Freeze-Watchdog und Tagesbericht laufen.
5. **Eine Instanz je Kamera**, wie im Edge-Agenten bisher. Aus den
   `RTSP_URLS` von kuhwatch wird je Kamera ein Container.

## 2. Regeln

| Nr. | Regel |
| --- | --- |
| U1 | **Alte CPU ohne AVX:** `modell.alte_cpu: auto` (Default) aktiviert den Modus, wenn `/proc/cpuinfo` kein `avx` meldet. `true`/`false` erzwingen bzw. verbieten ihn. Im Modus wird vor dem Laden des Modells oneDNN in torch ausgeschaltet (`torch.backends.mkldnn.enabled = False`) und `torchvision.ops.nms` durch eine NumPy-NMS ersetzt. Der kompilierte Operator bricht auf der A6-3650 mit SIGILL ab. Ein ONNX-Modell (`modell.pfad` auf `.onnx`) läuft über onnxruntime. Der Silent Mode lädt kein torch und braucht nichts davon. *Nebenbefund:* kuhwatch rief `torch.backends.mkldnn.set_enabled(False)` auf. Diese Funktion gibt es nicht, und der Fehler wurde verschluckt. oneDNN war dort also nie aus; es fiel nur nicht auf, weil die Inferenz über onnxruntime lief. |
| U2 | **Tierklassen:** `modell.tier_klassen` (Default `[kuh]`). Nur Boxen dieser Klassen werden als Tier getrackt und gehen in Schwanzwinkel und Brunst ein. Bisher galt jede Box als Kuh, die nicht Fruchtblase oder Kälberfüße war. Mit einem allgemeinen Modell hätte ein Mensch hinter einer Kuh einen Brunstverdacht auslösen und ihr die Track-ID stehlen können. Dieselben Klassen gehen samt Fruchtblase und Kälberfüßen als Filter an den Tracker (`classes=`). Für das Standardmodell (`kuh`, `amniotic_sac`, `calf_legs`) ändert sich nichts. |
| U3 | **Container für den Stallrechner:** `edge-agent/Dockerfile` auf `python:3.11-slim`, Pakete auf die auf stallwache-lela erprobten Versionen gepinnt (`requirements-geraet.txt`: numpy < 2, opencv-python-headless 4.10.0.84). Build-Argument `ANALYSE=1` ergänzt das Analyse-Rezept von kuhwatch: torch 2.1.2/torchvision 0.16.2 (CPU), ultralytics 8.3.40, lapx, onnxruntime. Offline-Wheels in `edge-agent/wheels/` (torch ohne AVX, onnxruntime) werden danach ohne Abhängigkeiten darüber installiert. `docker-compose.yml`: Host-Netz (go2rtc auf `localhost`), 1 CPU, 4 GB, Log-Rotation, Daten in `edge-agent/daten/<kamera>/`. |
| U4 | **Temperaturwächter:** aus kuhwatch nach `edge-agent/deploy/tempguard/`. Grenzwerte unverändert: Warnung 80 °C, kritisch 85 °C (Container pausieren, Takt auf 1,6 GHz), Entwarnung 75 °C. Neu: Er pausiert alle Container, deren Name `stallwache-agent` enthält, und liest Telegram aus `/etc/stallwache/tempguard.env` statt aus `kuhwatch/.env`. |
| U5 | **Umstieg in einem Befehl:** `edge-agent/deploy/umstieg-von-kuhwatch.sh` baut das Image und erzeugt aus `kuhwatch/.env` die `config.yaml` (Silent Mode, erste URL = `stallwache`, Telegram übernommen, Rechte 600, Zugangsdaten nie im Terminal). Es stoppt kuhwatch, ohne etwas zu löschen (`restart=no`), startet den Agenten und stellt den Temperaturwächter um. `--trocken` zeigt nur, was passieren würde. Der Rückweg steht am Ende der Ausgabe. Weitere URLs aus `RTSP_URLS` werden genannt, aber nicht eingerichtet (Skill `neue-kamera`). |
| U6 | **Quelle unverändert:** Der Agent liest dieselbe Kamera-URL wie kuhwatch. Den go2rtc-Restream (`rtsp://127.0.0.1:8554/stallwache`) erst nehmen, wenn die beiden go2rtc auf dem Gerät zusammengelegt sind (Roadmap, Fernzugriff). |

## 3. Konfiguration (neu in `config.example.yaml`)

```yaml
modell:
  tier_klassen: [kuh]   # nur diese Klassen sind Tiere (Tracking, Winkel, Brunst)
  alte_cpu: auto        # auto | true | false — CPU ohne AVX (z. B. AMD A6-3650)
```

`SILENT_MODE` von kuhwatch hat keine Entsprechung. Der Edge-Agent schickt
Systemmeldungen (Start, Totmann, Tagesbericht 20:00) an Telegram, sobald ein
Token gesetzt ist. Alarme gibt es im Silent Mode ohnehin keine.

## 4. Abnahmekriterien

| Nr. | Kriterium | Wo |
| --- | --- | --- |
| 1 | `alte_cpu: auto` erkennt die Flags der A6-3650 (kein `avx`) und schaltet ein; mit `avx` aus; `true`/`false` gewinnen; ohne `/proc/cpuinfo` aus | Logiktest |
| 2 | NumPy-NMS liefert dieselben Indizes wie eine Referenz-NMS | Logiktest (mit numpy) |
| 3 | Mensch neben/hinter Kuh: keine Tierbeobachtung, kein Brunstverdacht. Fruchtblase meldet unabhängig von `tier_klassen`. Tracker bekommt den Klassenfilter | Logiktest |
| 4 | Silent Mode lädt kein torch/ultralytics | Logiktest |
| 5 | Image `ANALYSE=0` baut. Der Container speichert im Silent Mode gegen einen echten RTSP-Stream Trainingsbilder mit frischem Inhalt | Teststrecke + Docker |
| 6 | Image `ANALYSE=1` baut. Ein ONNX-Modell lädt mit `alte_cpu: true` (oneDNN aus, NMS ersetzt), die Inferenz läuft | Docker |
| 7 | Umstiegsskript `--trocken`: erzeugt `config.yaml` mit Rechten 600, kein Geheimnis in der Ausgabe, kein Container wird gestoppt | Docker |
| 8 | **Am Gerät:** Umstieg ausgeführt, kuhwatch gestoppt, Agent im Silent Mode. Trainingsbilder landen in `daten/stallwache/aufnahmen/`. Totmann-Probe (Kamera 5 min trennen): genau eine Meldung und eine Entwarnung. Der Temperaturwächter pausiert den neuen Container | stallwache-lela, offen |

### Ergebnis (23.10.2026)

| Nr. | Ergebnis |
| --- | --- |
| 1 | ✅ `test_ein_agent.py`: Flags der A6-3650 → an, mit `avx` → aus, `true`/`false` gewinnen, ohne Flags → aus |
| 2 | ✅ NumPy-NMS = Referenz in 200/200 Zufallsfällen. Im Analyse-Image hat ultralytics 8.3.40 sie tatsächlich aufgerufen |
| 3 | ✅ Mensch hinter Kuh: Gegenprobe mit Mensch als Tier ergibt einen Brunstverdacht, mit `tier_klassen [cow]` keinen. Fruchtblase meldet unabhängig. Echtes ultralytics mit `yolov8n.onnx` auf `bus.jpg`: 5 Rohboxen (Bus, Personen), mit `[cow]` 0 Tiere, Gegenprobe `[person]` 3 getrackte IDs |
| 4 | ✅ Silent Mode: kein torch/ultralytics in `sys.modules` |
| 5 | ✅ Image `ANALYSE=0` (128 MB komprimiert) gegen MediaMTX-Teststream: Trainingsbilder alle 10 s, Inhalt aus derselben Sekunde wie der Dateiname (erstes Bild nach dem Verbindungsaufbau 1,6 s) |
| 6 | ✅ Image `ANALYSE=1` (619 MB): torch 2.1.2+cpu, ultralytics 8.3.40, numpy 1.26.4, onnxruntime. Mit `alte_cpu: true` ist oneDNN aus und die NMS ersetzt, Inferenz 0,21 s je Bild. **Befund dabei:** ultralytics installiert fehlende Pakete zur Laufzeit per pip nach. Im Test zog ein ONNX-Export numpy 2.4 nach, danach brach torch ab („Numpy is not available“). Im Image steht deshalb `YOLO_AUTOINSTALL=false` |
| 7 | ✅ Trockenlauf gegen nachgestelltes kuhwatch (Container + `.env` mit Passwort und Token): Ausgabe ohne Geheimnisse, `config.yaml` mit Rechten 600, nichts gestoppt, nichts abgelegt. Echtlauf (`--ohne-tempguard`): kuhwatch gestoppt mit `restart=no`, Agent läuft, erstes Trainingsbild nach 4 s, das Kamera-Passwort steht nicht im Log. Rückweg mit den ausgegebenen Befehlen: kuhwatch läuft wieder. Temperaturwächter: pausiert nur `stallwache-agent-*`, ein unbeteiligter Container läuft weiter, Fortsetzen geht |
| 8 | offen (Betreiber, am Gerät) |

### Prüfung durch qa-waechter (23.10.2026)

**Freigabe ja.** Ergebnisse:
- Webapp: `typecheck`, `lint`, `npm test` (100/100) und `build` grün.
- Edge-Agent: 514 Checks, zwei Läufe ohne Abweichung.
- shellcheck: keine Meldung.
- Konverter mit Canary-Geheimnissen: Keines landet in der Ausgabe, `$(…)` wird nicht ausgeführt.
- `tempguard.env` ist nicht anfällig für Injection.
- Webapp-Regression (Ingest-Auth, `/sw.js`, Manifest) ohne Befund.

Zwei Befunde, beide vor dem Merge behoben:

- **B1:** Das Umstiegsskript las Telegram-Token und Chat-ID für den
  Temperaturwächter ohne Anführungszeichen-/CR-Bereinigung, anders als der
  Python-Konverter. Bei `TELEGRAM_BOT_TOKEN="…"` oder einer `.env` mit
  Windows-Zeilenenden kamen die Temperaturwarnungen deshalb still nicht an.
  Jetzt bereinigt `env_wert` die Werte genauso wie der Konverter.
- **B2 (bestand schon auf `main`):** Fehlermeldungen von requests nennen die
  Telegram-URL samt Bot-Token. Solange Telegram nicht erreichbar war, stand
  der Token alle 10 s im Log, und im Container ist das per `docker logs`
  lesbar. Jetzt schwärzt ein `GeheimFilter` den Token in jeder Logzeile des
  Agenten, auch in Tracebacks (`test_geheimnisse.py`, 7 Checks; ohne den Filter
  scheitern 3).

Nebenbei: `DASHBOARD_TOKEN` steht beim Erzeugen der `config.yaml` nicht mehr
in der Prozessliste.

## 5. Risiken

1. **Keine Kalbe-Meldung bis zum ersten Modell** (Grundsatz 4). Gegenmittel
   ist der Meilenstein selbst: Ab jetzt sammelt der Stallrechner die Bilder
   dafür.
2. **Pakete auf der alten CPU:** Neuere numpy-/OpenCV-Wheels können eine
   höhere SIMD-Basis voraussetzen. Deshalb sind die auf dem Gerät erprobten
   Versionen gepinnt.
3. **Analyse-Image am Gerät ungetestet.** Die Offline-Wheels liegen nur
   dort. Das Rezept ist das von kuhwatch, nur jetzt mit wirksamem
   oneDNN-Schalter.
4. **Kamera-Verbindungen:** Die Tapo-Kamera erlaubt nur wenige gleichzeitige
   RTSP-Verbindungen. Der Agent ersetzt die Verbindung von kuhwatch,
   zusätzlich ist keine nötig. Beide gleichzeitig laufen zu lassen, ist
   nicht vorgesehen.
5. **Tagesbericht neu im Telegram-Chat** (20:00). Wer das nicht will, setzt
   `telegram.digest_uhrzeit` leer.
