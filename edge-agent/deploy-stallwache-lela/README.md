# Edge-Agent auf der Stallwache LELA (AMD A6, CPU-only)

Docker-Deployment fuer den ausgemusterten Stall-PC (AMD A6-3650, 2011, **kein AVX**).

## Was ist anders als im Standard-Setup?
- **Inferenz mit ONNX Runtime (B19):** `modell.pfad: modelle/best_v1.onnx`
  (Ordner `modelle/` ist schreibgeschuetzt eingebunden). PyTorch bricht auf
  dieser CPU bei jeder Faltung ab; Ultralytics wird nur noch fuer ByteTrack
  importiert. `modell.threads: 0` nimmt so viele Threads, wie die
  Docker-Quote erlaubt (`cpus: 1` -> 1).
- **Gate D (>= 1 FPS):** mit 1 Kern 0,94-0,99 FPS (nicht bestanden), mit 2
  Kernen 1,64 FPS (gemessen 05.11.2026, `docs/onnx-laufzeit-spezifikation.md`).
  Bei `ziel_fps: 1.0` ist die mittlere Last mit `cpus: 2` gleich (je Bild
  ~1 Kern-Sekunde), nur die Spitze ist kuerzer. Entscheidung offen.
- **`cpu_compat.py`**: ersetzt `torchvision.ops.nms` durch eine NumPy-Variante.
  Der kompilierte Operator fuehrt auf CPUs ohne AVX eine illegale Instruktion
  aus (SIGILL). Getestet: 0 Abweichungen in 200 Zufallsfaellen gegen die Referenz.
  Seit B19 nicht mehr im Laufzeitpfad (NMS laeuft ueber OpenCV), bleibt als
  Schutz fuer Ultralytics-Importe.
- **`cpus: 1`** im Compose-File: konstante, flache Last. Auf der alten APU hat
  Dauer-Volllast zu thermischen Abstuerzen gefuehrt.
- Aufbau auf einem vorhandenen CPU-tauglichen Image (`BASIS=...`), kein
  erneuter Download von torch/CUDA.

## Start
```bash
cd edge-agent
cp config.example.yaml config.yaml        # Stream, Telegram eintragen (nicht committen!)
mkdir -p aufnahmen modelle
docker compose -f deploy-stallwache-lela/docker-compose.yml up -d --build
docker logs -f stallblick-agent
```

## Pruefen im Container
```bash
# Tracker-Test mit der Ultralytics-Version des Images (8.3.40):
docker run --rm -v "$PWD":/pruef -w /pruef kuhwatch-stallwache:latest \
    python tests/test_bytetrack_echt.py
docker run --rm -v "$PWD":/pruef -w /pruef kuhwatch-stallwache:latest \
    python tests/alle_tests.py
```

## Bekannte Einschraenkung: Feedback-Buttons
`telegram.feedback_buttons` nutzt `getUpdates`. Ist am selben Bot ein Webhook
gesetzt, antwortet Telegram mit **409 Conflict**; dann `feedback_buttons: false`
setzen oder einen eigenen Bot fuer den Agent verwenden.

## Hinweis Logs
Die `requests`-Fehlermeldung enthaelt die Telegram-URL samt Bot-Token. Logs
nicht teilen; bei Weitergabe Token neu ausstellen (@BotFather `/revoke`).
