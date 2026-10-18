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
ExecStart=/home/pi/Die_Stallwache/edge-agent/venv/bin/python3 main.py
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

---

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
   aufgenommen, `stream.url` auf die Datei: 0 Austreibung, ≤ 1
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

* RTSP-Reconnect mit Wartezeit; nach 5 Fehlversuchen automatischer Wechsel auf
  **Snapshot-Polling** über die go2rtc-API (funktioniert selbst bei zickigem WLAN).
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
