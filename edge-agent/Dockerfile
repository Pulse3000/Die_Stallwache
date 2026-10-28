# Edge-Agent als Container fuer den Stall-Rechner
# (docs/ein-edge-agent-spezifikation.md, U3).
#
#   Silent Mode:     docker compose up -d --build
#   Analyse-Modus:   ANALYSE=1 docker compose up -d --build
#
# Analyse-Rezept aus kuhwatch (stallwache-lela): torch/torchvision CPU,
# ultralytics 8.3.40, onnxruntime; Offline-Wheels aus wheels/ (z. B. torch
# ohne AVX) werden danach ohne Abhaengigkeiten darueber installiert.
FROM python:3.11-slim

ARG ANALYSE=0
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 \
    && if [ "$ANALYSE" = "1" ]; then apt-get install -y --no-install-recommends libgl1; fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-geraet.txt .
RUN pip install --no-cache-dir --timeout 120 --retries 10 -r requirements-geraet.txt

COPY wheels/ /tmp/wheels/
RUN if [ "$ANALYSE" = "1" ]; then \
      pip install --no-cache-dir --timeout 120 --retries 10 -c requirements-geraet.txt \
        torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
      && pip install --no-cache-dir --timeout 120 --retries 10 -c requirements-geraet.txt \
        ultralytics==8.3.40 opencv-python==4.10.0.84 "lapx>=0.5.5" onnxruntime \
      && if ls /tmp/wheels/*.whl >/dev/null 2>&1; then \
           pip install --no-cache-dir --no-deps /tmp/wheels/*.whl; \
         fi; \
    fi \
    && rm -rf /tmp/wheels

# Zonendateien fuer TZ=Europe/Berlin (docker-compose.yml). Ohne sie rechnet
# die C-Bibliothek still in UTC. Das slim-Image bringt tzdata heute mit; die
# Pruefung steht nach den Paket-Schichten, damit sie keinen Neubau von
# torch/ultralytics ausloest.
RUN test -f /usr/share/zoneinfo/Europe/Berlin || (apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*)

COPY main.py freeze_watchdog.py alte_cpu.py tracker-kuh.yaml config.example.yaml ./

# Ultralytics installiert fehlende Pakete sonst zur Laufzeit per pip nach –
# im Test zog das numpy 2.x nach und torch 2.1.2 brach ab („Numpy is not
# available“). Der gepinnte Stack fuer die alte CPU bleibt, wie er ist.
ENV YOLO_AUTOINSTALL=false

# Laufzeitdaten (config.yaml, aufnahmen/, Puffer) liegen im Volume /daten.
WORKDIR /daten
CMD ["python", "-u", "/app/main.py"]
