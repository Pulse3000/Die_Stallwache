# Stallblick Edge-Agent auf einem Android-Handy (Termux)

Workaround für Betriebe **ohne** ausgemusterten Laptop/Mini-PC/Raspberry Pi:
Der Edge-Agent ist reines Python (OpenCV, NumPy, Requests, PyYAML) und läuft
im **Silent Mode** (Trainingsbilder sammeln) deshalb auch unter **Termux** —
demselben Linux-Terminal für Android, das schon die
[Stallblick-Bridge](../../bridge/termux/README.md) nutzt.

> **iPhone/iOS geht nicht.** Aus demselben Grund wie bei der Bridge: Apple
> erlaubt keine dauerhaften Hintergrundprozesse für Drittanbieter-Apps.

## Wichtig: zwei Betriebsmodi, unterschiedlich gut geeignet

| Modus | Auf Termux? | Warum |
| --- | --- | --- |
| **Silent Mode** (kein Modell, sammelt nur Bilder) | ✅ funktioniert | Braucht nur `opencv-python`, `numpy`, `requests`, `PyYAML` — alles unter Termux installierbar. |
| **Analyse-Modus** (YOLO-Pose-Inferenz mit `best.pt`) | ⚠️ **noch nicht unterstützt** | `ultralytics`/`torch` haben **keine offiziellen Android/Termux-Wheels** (Termux linkt gegen Bionic-libc, nicht glibc — die PyPI-`manylinux`-Wheels passen nicht). Es gäbe experimentelle Auswege (z. B. Modell nach ONNX/NCNN exportieren und mit einer mobil-tauglichen Inferenz-Engine statt Ultralytics laufen lassen), das ist aber unerprobt und bewusst **nicht** halb eingebaut. |

**Empfohlener Weg:** Handy läuft im Silent Mode und sammelt Trainingsbilder,
bis ein Modell trainiert ist (siehe [`../README.md`](../README.md), Abschnitt
„Weg zum eigenen Modell"). Für den anschließenden Analyse-Modus entweder
- das Handy gegen einen Bridge-Rechner/alten Laptop/Raspberry Pi tauschen
  (`best.pt` einfach in dessen `config.yaml` eintragen), oder
- sag Bescheid, sobald ein Modell vorliegt — dann prüfen wir gemeinsam den
  ONNX/NCNN-Weg für dieses konkrete Handy.

## Einschränkungen (bitte vorher lesen)

- Gilt alles, was auch für die [Bridge unter Termux](../../bridge/termux/README.md#einschränkungen-bitte-vorher-lesen)
  gilt: Akku-Optimierung aus, WLAN im Ruhezustand aktiv, Termux nicht aus
  „Kürzlich verwendet" wischen, kein offizieller Support seitens der
  Bibliotheken für Android.
- Das Handy muss **dauerhaft an Strom + WLAN** bleiben.
- 1 Bild alle paar Minuten reicht (siehe `config.yaml`) — das ist unkritisch
  für älteres/schwächeres Hardware.

## 1. Termux installieren

Falls die Bridge bereits auf diesem (oder einem anderen) Handy läuft, ist
Termux schon vorhanden — sonst:

- [Termux via F-Droid](https://f-droid.org/packages/com.termux/) installieren
  (**nicht** aus dem Play Store, veraltete Version)
- **Termux:Boot** (gleicher Store) für Autostart nach Neustart

## 2. Android vorbereiten

- *Einstellungen → Apps → Termux → Akku* → **„Uneingeschränkt"**
- WLAN: „WLAN im Ruhezustand aktiv lassen" aktivieren
- Handy dauerhaft ans Ladegerät anschließen

## 3. Python-Umgebung einrichten

```bash
pkg update && pkg install python git termux-tools -y

git clone https://github.com/Pulse3000/Die_Stallwache.git ~/Die_Stallwache
cd ~/Die_Stallwache/edge-agent

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

# Silent Mode braucht nur diese vier Pakete (kein ultralytics/torch nötig):
pip install "opencv-python-headless>=4.9,<5" "numpy>=1.26,<3" "requests>=2.31,<3" "PyYAML>=6.0,<7"
```

> **Falls `opencv-python-headless` beim Bauen scheitert:** Termux hat kein
> `manylinux`, d. h. es wird ggf. aus dem Quellcode kompiliert (dauert lange,
> braucht `pkg install cmake clang pkg-config`). Vorher testen:
> `python3 -c "import cv2; print(cv2.__version__)"` — erst wenn das
> durchläuft, mit der Konfiguration weitermachen.

## 4. Konfiguration eintragen

```bash
cp config.example.yaml config.yaml
nano config.yaml
```

Wichtig für den Android-Betrieb:

- `stream.url` / `stream.fallback_snapshot_url`: IP der bestehenden Bridge
  im Stall-WLAN (go2rtc, egal ob die Bridge selbst auf Termux, Docker oder
  einem NAS läuft).
- `modell.pfad`: **leer lassen** → Silent Mode.
- `telegram.token` / `telegram.chat_id`: siehe [`../README.md`](../README.md#telegram-einrichten-2-minuten).
- `dashboard.token`: `EDGE_INGEST_TOKEN` aus Vercel.

## 5. Starten

```bash
cd ~/Die_Stallwache/edge-agent/termux
bash start-agent.sh
```

Logs prüfen:

```bash
tail -f logs/agent.log
```

## 6. Autostart nach Neustart (mit Termux:Boot)

```bash
mkdir -p ~/.termux/boot
cp start-agent.sh ~/.termux/boot/stallblick-agent-boot.sh
```

Termux:Boot einmalig öffnen und die angeforderte Berechtigung erteilen.

## Fehlersuche

| Problem | Ursache / Lösung |
| --- | --- |
| `import cv2` schlägt fehl | Kein passendes Wheel für dieses Android/Termux — Schritt 3 erneut prüfen, ggf. `pkg install clang cmake` für den Build aus Quellcode |
| Agent fällt nach einiger Zeit aus | Akku-Optimierung doch aktiv, oder Termux aus „Kürzlich verwendet" entfernt — Schritt 2 erneut prüfen |
| `termux-wake-lock: command not found` | `pkg install termux-tools` (Skript läuft trotzdem weiter, nur ohne Wake-Lock) |
| Nach Handy-Neustart offline | Termux:Boot-Berechtigung fehlt oder Schritt 6 nicht ausgeführt |
| Modell soll jetzt aktiviert werden | Auf Termux nicht vorgesehen (siehe oben) — Handy gegen Laptop/RPi tauschen oder ONNX/NCNN-Weg gemeinsam prüfen |
