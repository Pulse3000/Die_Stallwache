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

1. **Silent Mode laufen lassen** (1–2 Wochen): sammelt Bilder bei Tag,
   Dämmerung und IR-Nacht aus dem eigenen Stall.
2. **Vorwissen holen:** Open-Source-Datensätze **CVB** (Cattle Visual
   Behaviors) und **CattleEyeView** (Top-Down) herunterladen.
3. **Labeln mit CVAT** (app.cvat.ai, kostenlos): pro Kuh Bounding-Box +
   Keypoints `Spine_End`, `Tail_Base`, `Tail_Tip`; zusätzlich Boxen für
   `amniotic_sac` (Fruchtblase) und `calf_legs` (Kälberfüße). Export im
   YOLO-Format.
4. **Training in Google Colab (Free-GPU):**

   ```python
   !pip install ultralytics
   from ultralytics import YOLO
   modell = YOLO("yolov8n-pose.pt")          # vortrainiert, klein & CPU-tauglich
   modell.train(data="stall.yaml", epochs=100, imgsz=640)
   # Ergebnis: runs/pose/train/weights/best.pt herunterladen
   ```

5. **`best.pt` auf den Stall-Rechner kopieren** und in `config.yaml` unter
   `modell.pfad` eintragen → Agent wechselt automatisch in den Analyse-Modus.
6. **Fehlalarme nachtrainieren:** falsch erkannte Bilder zurück in CVAT als
   Negativ-Beispiele („Background") labeln und erneut trainieren.

---

## Erkennungslogik (implementiert in `main.py`)

| Phase | Regel | Reaktion |
| --- | --- | --- |
| **Kalbeverdacht** | Schwanzwinkel > 45° (Vektoren `Spine_End→Tail_Base` und `Tail_Base→Tail_Tip`, `atan2`) in **> 20 %** der Frames eines rollierenden **30-Min-Fensters** (`collections.deque`) | Telegram + Dashboard |
| **Austreibung** | `amniotic_sac` oder `calf_legs` mit **> 80 %** Konfidenz | **Sofort-Alarm**, Zeitfilter übersprungen |
| **Eskalation** | Austreibung läuft, aber nach **60 min** (konfigurierbar) sind weiterhin Fruchtblase/Füße sichtbar → kein Geburtsfortschritt | **dringender Kontroll-Alarm** (Komplikationsverdacht, Lely-Zeta-Prinzip) |
| **Brunstverdacht** | Aufsprung: zwei Kuh-Boxen überlappen (IoU > 0.15), eine deutlich oberhalb, **≥ 4 s** anhaltend (filtert Spielverhalten) | Telegram + Dashboard |
| Anti-Spam | **15 Min Cooldown** pro Kuh-ID und Alarmtyp | – |
| Bildserie | Jeder Alarm sendet die **letzten 4 Frames als Telegram-Album** (`bildserie_frames`) | Fehlalarm-Triage direkt am Handy |
| Wach-Modus | `logik.wach_modus: true` ~14 Tage vor Kalbetermin: halbierte Schwellen, frühere Verdachtsalarme | erhöhte Wachsamkeit nur, wenn bewusst scharfgeschaltet |
| MQTT (optional) | `mqtt.host` setzen → jedes Ereignis als JSON unter `stallblick/<kamera>/<typ>` | stiller Zusatzausgang für Home Assistant/Node-RED; Telegram bleibt primär |

Tracking über **ByteTrack** (in Ultralytics integriert) hält die Kuh-Identität
(„Kuh #42") über die Zeit stabil – Grundlage des Zeitfilters.

## Robustheit

* RTSP-Reconnect mit Wartezeit; nach 5 Fehlversuchen automatischer Wechsel auf
  **Snapshot-Polling** über die go2rtc-API (funktioniert selbst bei zickigem WLAN).
* Jede Iteration ist mit Exception-Handling abgesichert – der Prozess läuft
  24/7 weiter, `systemd` startet ihn zur Not neu.
* Telegram-/Dashboard-Ausfälle blockieren die Analyse nicht.
