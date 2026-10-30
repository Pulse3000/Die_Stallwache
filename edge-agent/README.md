# 🧠 Stallblick Edge-Agent – KI-Brunst- & Kalbeerkennung

Der Agent analysiert die vorhandenen Stallblick-Kameras (Stallwache/Futterwache
über die go2rtc-Bridge) lokal im Stall und alarmiert bei Kalbe- oder
Brunstanzeichen per **Telegram**; zusätzlich meldet er jedes Ereignis an das
**KI-Wache-Dashboard** der Webapp (`/wache` auf Vercel).

> Die Bildanalyse läuft bewusst **nicht** in der Cloud: Vercel-Functions haben
> weder GPU noch Dauerprozesse, und der Video-Upload würde den Stall-Uplink
> sprengen. Edge-First ist hier der Standardweg.

---

## 0 € Hardware-Strategie (empfohlen)

**Es muss kein Gerät gekauft werden.** Der Trick: Kalbeanzeichen entwickeln
sich über Minuten (30-Minuten-Zeitfilter!) – **1 Frame pro Sekunde reicht
komplett**. Damit schafft ein YOLOv8**n**-Pose-Modell die Analyse auch auf
alter CPU-Hardware:

| Option | Kosten | Eignung |
| --- | --- | --- |
| **Bridge-Rechner mitbenutzen** (der Rechner, auf dem go2rtc läuft) | 0 € | ideal – liest den Stream über `localhost`, keine Netzlast |
| **Ausgemusterter Laptop/Büro-PC** (i5 ab ~2015) | 0 € | 2–5 FPS mit YOLOv8n – mehr als genug |
| **Altes Android-Handy (Termux)** | 0 € | nur für **Silent Mode** (Bilder sammeln) – Analyse-Modus (YOLO) läuft dort noch nicht, siehe [`termux/README.md`](termux/README.md) |
| **Google Colab (Free)** | 0 € | fürs **Training** des Modells (GPU gratis), nicht für 24/7-Inferenz |
| Raspberry Pi 5 + AI-Kit / Jetson Orin Nano | 100–600 € | späteres Upgrade, falls mehr Kameras/FPS gewünscht |

Auch **Training kostet nichts**: Colab Free stellt eine GPU, die Datensätze
(CVB, CattleEyeView) sind Open Source, das Labeling-Tool CVAT ist kostenlos.

---

## Schnellstart

**Ein Befehl genügt** — das Setup-Skript übernimmt venv, Pakete (Silent Mode
sofort, die großen Analyse-Pakete optional), die geführte Konfiguration
(Bridge-IP, Telegram-Bot, Dashboard-Token) und auf Wunsch den
systemd-Dauerbetrieb:

```bash
bash edge-agent/setup.sh
```

Wer jeden Schritt selbst machen will:

```bash
cd edge-agent
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
#  -> stream.url auf die Bridge-IP anpassen (RTSP-Restream von go2rtc, Port 8554)
#  -> telegram.token + chat_id eintragen (siehe unten)
#  -> dashboard.token = EDGE_INGEST_TOKEN aus Vercel

python3 main.py
```

### Als Container (Stall-Rechner, z. B. stallwache-lela)

Der Edge-Agent ist der **einzige** Agent im Stall. kuhwatch ist in ihm
aufgegangen (`docs/ein-edge-agent-spezifikation.md`). Das Image pinnt die
Pakete, die auf der alten AMD A6-3650 (ohne AVX) erprobt sind:

```bash
cd edge-agent
mkdir -p daten/stallwache && cp config.example.yaml daten/stallwache/config.yaml
#  -> Werte wie oben eintragen; tracker: /app/tracker-kuh.yaml
docker compose up -d --build                 # Silent Mode
ANALYSE=1 docker compose up -d --build       # erst mit eigenem Modell
KAMERA=futterwache docker compose -p futterwache up -d   # weitere Kamera
```

Auf einer CPU ohne AVX schaltet `modell.alte_cpu: auto` die nötigen
Ausweichwege ein (oneDNN aus, NumPy-NMS). Ein `.onnx`-Modell läuft dort über
onnxruntime. Offline-Wheels für die alte CPU gehören nach `wheels/`. Der
Temperaturwächter (`deploy/tempguard/`) pausiert den Agenten bei 85 °C.

**Umstieg von kuhwatch** in einem Befehl: `bash edge-agent/deploy/umstieg-von-kuhwatch.sh`.
Das Skript übernimmt Kamera und Telegram aus `kuhwatch/.env` und stoppt
kuhwatch, ohne es zu löschen. Danach startet es den Agenten im Silent Mode und
stellt den Temperaturwächter um. Mit `--trocken` zeigt es nur, was passieren
würde; den Rückweg nennt es am Ende.

**Token für die App (`dashboard.token`) später ändern.** Das Skript lässt eine
vorhandene `config.yaml` unverändert, ein zweiter Lauf hilft also nicht. Meldet
das Log `401 Client Error: Unauthorized`, passt der Token nicht zu
`EDGE_INGEST_TOKEN` in Vercel. Die `config.yaml` liegt im Klon dessen, der das
Skript ausgeführt hat (als `root` also unter `/root/Die_Stallwache/…`). Den
genauen Ordner zeigt `docker inspect -f '{{range .Mounts}}{{.Source}}{{end}}'
stallwache-agent-stallwache`. Dort `dashboard.token` ändern und den Agenten mit
`docker restart stallwache-agent-stallwache` neu starten. Wer den Token für das
Umstiegsskript mit `read -rs DASHBOARD_TOKEN` einliest, gibt die Befehle
einzeln ein: Mehrere eingefügte Zeilen auf einmal liest `read` sonst die
nächste Zeile als Token.

Ohne Modell (`modell.pfad` leer) startet der Agent im **Silent Mode** und
sammelt alle 2 Minuten ein Trainingsbild in `./aufnahmen` – genau das
Material, das für Phase „Datensammlung" gebraucht wird.

### Dauerbetrieb (systemd)

```ini
# /etc/systemd/system/stallblick-agent.service
[Unit]
Description=Stallblick Edge-Agent
After=network-online.target

[Service]
WorkingDirectory=/home/pi/Die_Stallwache/edge-agent
ExecStart=/home/pi/Die_Stallwache/edge-agent/venv/bin/python3 -u main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now stallblick-agent
```

---

## Telegram einrichten (2 Minuten)

1. In Telegram **@BotFather** öffnen → `/newbot` → Namen vergeben → **API-Token** kopieren.
2. **@userinfobot** öffnen → Start → numerische **Chat-ID** kopieren.
3. Beides in `config.yaml` unter `telegram:` eintragen.

### Kuh-Namen (Telegram `/kuh`)

Am Kasten im Livebild steht die Nummer der KI („Kuh #12“). Schreiben Sie dem
Bot im eingetragenen Chat `/kuh 12 Berta`, steht dort „Kuh #12 · Berta“, und
Alarme nennen „Kuh #12 (Berta)“. `/kuh 12 -` entfernt den Namen, `/kuehe`
zeigt alle. Regeln (`docs/kuh-namen-spezifikation.md`):

- nur für Nummern, die gerade im Bild sind (letzte 120 s), nur im Analyse-Modus;
- ein Name gehört höchstens einer Kuh – neu vergeben verschiebt ihn;
- nur im Arbeitsspeicher: Nach einem Neustart des Agenten oder wenn die Kuh
  länger als ~90 s aus dem Bild ist (neue Nummer), ist der Name weg. Eine
  gespeicherte Zuordnung hinge nach dem Neustart an einer anderen Kuh;
- braucht `telegram.feedback_buttons: true` (Standard); Nachrichten aus anderen
  Chats werden ignoriert.

---

## Kamerabild: kommt wirklich 2K an?

Welcher Stream gewählt ist, belegt nur das Bild selbst. Der Agent loggt beim
Verbinden genau einmal je Wechsel die Auflösung und nennt sie im
Tagesbericht; unter `stream.min_breite` (Standard 1280: erkennt den Unterstream) steht eine Warnung:

```bash
docker compose logs agent | grep "Bild von der Kamera"
# Bild von der Kamera: 2560x1440 (Livestream).          <- 2K, gut
# Bild von der Kamera nur 640x360 (Livestream) – …      <- Substream!
```

Direkt an der Quelle (Stall-Rechner, go2rtc-Restream):

```bash
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height \
  -of csv=p=0 rtsp://127.0.0.1:8554/stallwache      # Hauptstream (stream1)
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height \
  -of csv=p=0 rtsp://127.0.0.1:8554/stallwache_sd   # Substream (stream2)
```

- `stream.url` muss auf `…/stallwache` zeigen (go2rtc → `stream1`), nicht auf
  `…/stallwache_sd`.
- Liefert auch `stallwache` weniger als 2K, steht die Kamera selbst niedriger:
  Tapo-App → Kamera → Einstellungen → Videoqualität → 2K (Bezeichnung je
  nach Modell). Danach go2rtc neu verbinden lassen (`docker compose restart`
  in `bridge/`).
- Die Webapp bekommt über den Fernzugriff **bewusst** den SD-Stream
  (`FERN_QUELLE=stallwache_sd`, Datenvolumen am Handy). Das Livebild in der App
  ist also nicht das Bild, das der Agent analysiert.
- **Stichprobe 27.10.2026 (Stallwache, Bilder des alten kuhwatch):** Die
  Bilder haben 2560×1440; für den Edge-Agenten belegt das erst seine
  Logzeile. Schlechte
  Bildqualität hatte andere Ursachen: Ein weißer Kasten mit Kabel hängt vor
  der Linse und wird nachts vom IR-Licht grell angestrahlt, dazu
  Spinnweben; außerdem blockartige Bildfehler, vermutlich verlorene
  WLAN-Pakete zwischen Kamera und Bridge. Abhilfe: Gegenstand aus dem Bild,
  Linse reinigen, WLAN-Empfang der Kamera prüfen.
- 2K kostet Rechenzeit beim Dekodieren (alle Bilder des Streams, nicht nur
  1/s). Auf der A6-3650 nach dem Umstellen prüfen, ob „Bildgreifer … hinter
  dem Stream“ im Log erscheint (Bildfrische-Spezifikation, Kriterium 10).

## Brunst zuerst: das erste Modell kennt nur Kühe

Entscheidung des Betreibers (29.10.2026, `docs/brunst-zuerst-entscheidung.md`):
v1 erkennt nur `kuh` (Boxen) → scharf ist nur das **Aufsprungverhalten**.
Der Agent meldet beim Start und im Tagesbericht „NICHT scharf: Austreibung …,
Kalbeverdacht …“, die App sagt für die Kamera kein „OK“. Kurzfassung:

1. CVAT: Label `kuh` (Rechteck), jede Kuh einzeln – auch eng stehende und
   aufspringende. Export „Ultralytics YOLO Detection“.
2. `training/colab_training.py` mit `PHASE = "brunst"` (Datensatz
   `training/stall-brunst.yaml`).
3. `python3 training/abnahme.py best_v1.pt datensatz --phase brunst`
   (Gate K: Kuh-Recall, Gate Ü: beide Kühe in Aufsprung-Lage, Gate D:
   Doppelboxen; von Hand Gate E mit echten Aufsprung-Videos in 1 Bild/s).
4. `config.yaml`: `modell.pfad: best_v1.pt`, `modell.freigegeben: [brunst]`
   erst nach allen Gates (K, K-Nacht, Ü, D, E, 3b, 4), vorher `[]`;
   `modell.klassen` nicht kürzen. Dann `ANALYSE=1 docker compose up -d --build`.

Vorher die Kamera wählen: Laufbereich der besamungsfähigen Gruppe im Bild –
nicht die Stallwache, solange über ihr Livebild Kalbungen kontrolliert
werden –, nichts vor dem Objektiv (Abschnitt 2 und 9 der Entscheidung).

Der Abschnitt unten beschreibt den vollen Weg (Pose, Fruchtblase,
Kälberfüße) für die Kalbeüberwachung danach.

## Weg zum eigenen Modell (alles kostenlos)

Zyklus: **Sammeln → Sichten → Labeln → Split → Trainieren → Abnehmen →
Scharfschalten → Beobachten → wieder Sammeln.** Werkzeuge in `training/`.

1. **Silent Mode laufen lassen** (1–2 Wochen): sammelt alle 120 s ein Bild
   als `<kamera>_<JJJJMMTT-HHMMSS>.jpg`. Kamera und Zeit im Namen braucht
   der Split nach Tagen. Mindestens **ein Drittel IR-Nacht** (Beschluss B9,
   die Kalbung kommt nachts):

   ```bash
   python3 training/datensatz.py bilanz ./aufnahmen    # Exit 1 = zu wenig IR-Nacht
   ```
2. **Sichten:** nahezu identische Frames (leere Bucht, schlafende Herde)
   ausdünnen; Originale bleiben liegen. Faustzahl v1: 1.500–3.000 gelabelte
   Bilder. Danach die Bilanz auf der Auswahl wiederholen – nachts ändert
   sich wenig, das Ausdünnen trifft IR-Bilder am stärksten.

   ```bash
   python3 training/datensatz.py ausduennen ./aufnahmen ./auswahl
   ```
3. **Vorwissen beimischen:** Open-Source-Datensätze **CVB** (Cattle Visual
   Behaviors) und **CattleEyeView** (Top-Down) – nur Beimischung, nie
   Hauptquelle. Ohne Zeitstempel im Namen gehen sie automatisch nur ins
   Training, nie in die Abnahme.
4. **Labeln mit CVAT** (app.cvat.ai, kostenlos): Klasse `kuh` mit Box +
   genau 3 Keypoints `spine_end`, `tail_base`, `tail_tip`; Boxen für
   `amniotic_sac` (Fruchtblase) und `calf_legs` (Kälberfüße). Regeln:
   - Verdeckte Keypoints als **nicht sichtbar** markieren, nie raten –
     besonders `tail_tip`. Der Agent wertet nur sichtbare Keypoints
     (Konfidenz ≥ 0.5); geratene Labels lehren das Modell
     falsche Geometrie.
   - Erhobener Schwanz beim Koten ist normal `kuh`. Es gibt **keine Klasse
     „kalbt"** – das Verhalten entscheidet der Agent (30-min-Fenster).
   - Harte Negative (Kot/Urin, Reflexionen, Ketten) ungelabelt lassen.
   - Export: **„Ultralytics YOLO Pose"**.
5. **Split nach Stalltagen, nie zufällig nach Frames** (Nachbarframes sind
   fast identisch und schönen sonst die Val-Werte). Ein Stalltag läuft
   12–12 Uhr, jede Nacht bleibt ganz. Val = jüngste Tage, ≥ 15 %, plus
   ein Geburtstag, falls gelabelt:

   ```bash
   python3 training/datensatz.py split ./cvat-export ./datensatz [--val-tag 20261014]
   ```
6. **Training in Google Colab (Free-GPU):** Zellen in
   `training/colab_training.py` (Split, Training, Abnahme, Download).
   `training/stall.yaml` passt zu `config.yaml`.
7. **Abnahme-Gates** vor jedem Scharfschalten (`training/abnahme.py`):
   Austreibung Recall = 1.0 bei Konfidenz 0.80 für Fruchtblase **und**
   Kälberfüße, Schwanzwinkel-Abweichung
   < 10° (n ≥ 30) und Sichtbarkeit erhobener Schwänze ≥ 90 % (n ≥ 10)
   automatisch; Fehlalarm-Budget (24 h ereignisloses Material **mit 1 FPS**
   aufgenommen, `stream.url` auf die Datei als **lokaler Dateipfad**, nicht
   http/https – nur dann liest der Agent Bild für Bild: 0 Austreibung, ≤ 1
   Kalbeverdacht) und ≥ 1 FPS auf der Zielhardware von Hand:

   ```bash
   python3 training/abnahme.py best_v1.pt datensatz --bericht abnahme_v1.md
   python3 training/abnahme.py best_v1.pt datensatz --nur-fps   # auf dem Stall-Rechner
   ```

   Exit 2 = zu wenig Val-Material: ohne Geburt im Val-Set die
   Austreibungs-Logik nicht scharfschalten, ohne erhobene Schwänze erst
   mehr solche Bilder labeln.
8. **Versionieren:** `best_v1.pt`, `best_v2.pt`, … – nie überschreiben. Je
   Version eine Modellkarte aus `training/MODELLKARTE.vorlage.md`.
9. **Scharfschalten:** Datei auf den Stall-Rechner, Pfad in `config.yaml`
   unter `modell.pfad` → Agent wechselt in den Analyse-Modus. Danach
   `docs/metriken.md` mit Praxiswerten füllen.
10. **Nachtrainieren** bei > 2 Fehlalarmen/Woche desselben Typs, neuer
    Kamera/Umbau, Saisonwechsel oder der ersten aufgezeichneten Geburt.
    Fehlalarm-Bilder (Ein-Tipp-Feedback) zurück in CVAT als Negativ-
    Beispiele.

---

## Erkennungslogik (implementiert in `main.py`)

| Phase | Regel | Reaktion |
| --- | --- | --- |
| **Kalbeverdacht** | Schwanzwinkel > 45° (Vektoren `Spine_End→Tail_Base` und `Tail_Base→Tail_Tip`, `atan2`) in **> 20 %** der Frames eines rollierenden **30-Min-Fensters** (`collections.deque`). Nur Frames mit allen drei Keypoints sichtbar (Konfidenz ≥ 0.5, Sichtbarkeitsgrenze von Ultralytics) zählen – ein verdeckter Schwanz erzeugt keinen Winkel | Telegram + Dashboard |
| **Austreibung** | `amniotic_sac` oder `calf_legs` mit **≥ 0,80** Konfidenz (Vertrag: > 0,80; `≥` ist minimal empfindlicher, Richtung Recall) – gelesen **vor** dem Tracker, jede Einzelerkennung zählt | **Sofort-Alarm**, Zeitfilter übersprungen |
| **Eskalation** | Austreibung läuft, aber nach **60 min** (konfigurierbar) sind weiterhin Fruchtblase/Füße sichtbar → kein Geburtsfortschritt | **dringender Kontroll-Alarm** (Komplikationsverdacht, Lely-Zeta-Prinzip) |
| **Brunstverdacht** | Aufsprung: zwei Kuh-Boxen überlappen (IoU > 0.15), eine deutlich oberhalb, **≥ 4 s** anhaltend (filtert Spielverhalten) | Telegram + Dashboard |
| Anti-Spam | **15 Min Cooldown** pro Kuh-ID und Alarmtyp — nur Kalbe-/Brunstverdacht | – |
| Austreibungs-Takt | je **Episode** statt Cooldown: Sofort-Meldung bei Beginn, Erinnerung „läuft weiter seit N min" alle 15 min, solange sichtbar; nach „❌ Fehlalarm" meldet die nächste Erkennung nach ≥ 60 s Pause sofort neu (`docs/austreibung-episoden-spezifikation.md`) | eine laufende Geburt meldet sich, bis sie vorbei ist — nie verzögert durch einen pauschalen Cooldown |
| Bildserie | Jeder Alarm sendet die **letzten 4 Frames als Telegram-Album** (`bildserie_frames`) | Fehlalarm-Triage direkt am Handy |
| Wach-Modus | `logik.wach_modus: true` ~14 Tage vor Kalbetermin: halbierte Schwellen, frühere Verdachtsalarme | erhöhte Wachsamkeit nur, wenn bewusst scharfgeschaltet |
| MQTT (optional) | `mqtt.host` setzen → jedes Ereignis als JSON unter `stallblick/<kamera>/<typ>` | stiller Zusatzausgang für Home Assistant/Node-RED; Telegram bleibt primär |

Tracking über **ByteTrack** (in Ultralytics integriert) hält die Kuh-Identität
(„Kuh #42") über die Zeit stabil – Grundlage des Zeitfilters.

## Freeze-Watchdog (Kamera-Defekte)

`freeze_watchdog.py` erkennt zwei Fehler, die sonst niemand bemerkt: ein
**eingefrorenes Bild** (N Bilder in Folge praktisch identisch) und
**Streifen-Korruption** (senkrechte Farbstreifen). Je Kamera läuft ein
Watchdog (`stream.kamera`; die Futterwache als eigene Agent-Instanz mit eigener
`config.yaml`).

* **Eine** Meldung beim Eintritt in den Fehlerzustand (Telegram + Dashboard
  `info`), **eine** bei Erholung – kein Spam dazwischen.
* Solange die Kamera defekt ist: **keine Trainingsbilder, keine Analyse**
  (ein eingefrorenes Bild würde alte Befunde „weiterzählen"; im Datensatz wäre
  es Müll).
* Schwelle `watchdog.frames_bis_alarm`: leer = **Silent Mode 5** (geprüft wird
  jedes gespeicherte Trainingsbild, also 5 × `silent_mode.intervall_sekunden`)
  bzw. **Analyse-Modus 300** (jeder Frame bei ~1 FPS ≈ 5 min).
  `watchdog.aktiv: false` schaltet ihn ab.
* **Fail-open:** Ein Fehler im Watchdog oder beim Senden setzt die Analyse nie
  aus. Erkennungsschwellen (45°/20 %/30 min/0.80/IoU 0.15/4 s) und Cooldown
  bleiben unberührt.

## Logiktests

Die zeitkritischen Bausteine (Totmann-Meldung, Feedback-Schleife,
Tracker-Konfiguration, Referenz-Schwellenwerte, Freeze-Watchdog) haben eine
Offline-Testsuite (cv2/requests werden gestubbt; die Watchdog-Tests brauchen
echtes `numpy` aus `requirements.txt`):

```bash
python3 edge-agent/tests/alle_tests.py
```

## Robustheit

* **Immer das jüngste Bild:** Ein Bildgreifer-Thread liest den Livestream
  ständig mit und hält nur das neueste Bild. Vorher bekam die Analyse das
  nächste Bild im OpenCV-Puffer, nach wenigen Minuten also Minuten Altes
  (`docs/bildfrische-spezifikation.md`). Ohne frisches Bild (> 5 s) gibt es
  keines. Verbindungsaufbau und Reconnect laufen im Greifer mit
  exponentiellem Backoff (5 → 30 s). Die Analyseschleife wartet nie darauf.
  Meldet das Log „Bildgreifer … hinter dem Stream“, ist der Rechner zu
  langsam für den Stream: den Substream der Kamera bzw. von go2rtc
  eintragen. Eine Datei als `stream.url` wird weiter Bild für Bild gelesen.
* Nach 5 Abrufen ohne frisches Livebild Wechsel auf **Snapshot-Polling** über
  die go2rtc-API. Sobald der Livestream wieder frisch ist, gilt wieder er.
* **Ruhiges Log:** FFmpeg meldet nur noch „fatal“ (`OPENCV_FFMPEG_LOGLEVEL=8`).
  Manche Kameras hängen Zusatzdaten an jedes Bild, und der Decoder meldete
  dazu mehrmals pro Sekunde „SEI type … truncated“. Das verdrängte im
  rotierenden Docker-Log binnen Minuten die Meldungen des Agenten. Echte
  Ausfälle erkennt der Agent selbst (kein Bild → Reconnect, Totmann), den
  *Grund* nennt das Log dann aber nicht mehr.
  **Fehlersuche**, wenn das Log nur „Stream nicht erreichbar“ zeigt:
  `OPENCV_FFMPEG_LOGLEVEL=16 docker compose up -d` (weitere Kameras mit
  `KAMERA=…`/`-p …` wie beim Start). Der Grund steht dann als
  `[OPENCV:FFMPEG:16] method DESCRIBE failed: 401 Unauthorized` (falsche
  Zugangsdaten), `404 Not Found` (Streamname unbekannt; manche Server
  antworten dabei mit 400 ohne Logzeile) oder `Connection refused`
  (go2rtc/Kamera nicht erreichbar) im Log. Danach
  `docker compose up -d` ohne Variable, sonst kommt die Flut zurück. Liest der
  Agent den go2rtc-Restream, stehen Zugangsfehler zur Kamera im go2rtc-Log.
  Unter systemd: `Environment=OPENCV_FFMPEG_LOGLEVEL=16` in der Unit.
* Jede Iteration ist mit Exception-Handling abgesichert – der Prozess läuft
  24/7 weiter, `systemd` startet ihn zur Not neu.
* Telegram-/Dashboard-Ausfälle blockieren die Analyse nicht: Je Kanal ein
  eigener Versand-Thread, das Dashboard als Outbox (vor dem Senden auf die
  Platte gesichert, gepufferte Alarme gehen ohne neuen Alarm nach — ab 60 s,
  bei Dauerausfall mit Backoff bis 15 min, in Teilstapeln unter den
  Server-Grenzen, Austreibung zuerst). Feedback-Abruf ebenfalls entkoppelt
  (`docs/versand-entkopplung-spezifikation.md`).
* **Lebenszeichen** (`dashboard.lebenszeichen_minuten`, Default 5): Der
  Agent meldet der App im Hintergrund, dass er lebt, in welchem Modus er
  läuft und ob die Kamera ein Bild liefert. Ohne Lebenszeichen antwortet die
  Statusabfrage (`GET /api/stall-status`) mit „UNBEKANNT" statt „OK" —
  Schweigen heißt nie „alles ruhig". Eigener Thread, 10 s Timeout, blockiert
  die Analyse nicht (`docs/statusabfrage-spezifikation.md`).
