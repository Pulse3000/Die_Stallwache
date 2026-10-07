# Edge-Agent auf der Stallwache LELA (AMD A6, CPU-only)

Docker-Deployment fuer den ausgemusterten Stall-PC (AMD A6-3650, 2011, **kein AVX**).

## Was ist anders als im Standard-Setup?
- **`cpu_compat.py`**: ersetzt `torchvision.ops.nms` durch eine NumPy-Variante.
  Der kompilierte Operator fuehrt auf CPUs ohne AVX eine illegale Instruktion
  aus (SIGILL). Getestet: 0 Abweichungen in 200 Zufallsfaellen gegen die Referenz.
  Wird erst relevant, wenn ein Modell (`modell.pfad`) gesetzt ist.
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

## Bekannte Einschraenkung: Feedback-Buttons
`telegram.feedback_buttons` nutzt `getUpdates`. Ist am selben Bot ein Webhook
gesetzt, antwortet Telegram mit **409 Conflict**; dann `feedback_buttons: false`
setzen oder einen eigenen Bot fuer den Agent verwenden.

## Hinweis Logs
Die `requests`-Fehlermeldung enthaelt die Telegram-URL samt Bot-Token. Logs
nicht teilen; bei Weitergabe Token neu ausstellen (@BotFather `/revoke`).
