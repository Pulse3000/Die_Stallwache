# Stallblick Edge-Agent fuer den Stall-Rechner stallwache-lela (AMD A6-3650,
# 2011, kein AVX, kein X86_V2, ohne GPU).
#
# Basis ist das vorhandene kuhwatch-Image: Es laeuft nachweislich auf der
# alten CPU (numpy < 2, opencv-python-headless 4.10, torch/onnxruntime aus
# Offline-Wheels) und braucht beim Bauen kein Internet. Ein frisches venv
# zoege numpy >= 2.4 und stuerzte schon beim Import ab.
# Spezifikation: docs/lela-datensammlung-spezifikation.md
ARG BASIS=kuhwatch-stallwache:latest
FROM ${BASIS}
WORKDIR /agent

# PyYAML kommt mit ultralytics, requests mit kuhwatch. Nur nachinstallieren,
# wenn es fehlt – sonst bleibt der Bau offline.
RUN python -c "import yaml" 2>/dev/null || pip install --no-cache-dir "PyYAML>=6,<7"

COPY main.py freeze_watchdog.py tracker-kuh.yaml ./
COPY training/ ./training/
COPY deploy-stallwache-lela/cpu_compat.py ./

# Beweis schon beim Bauen: Fehlt ein Modul oder passt numpy nicht zur CPU,
# scheitert der Build – nicht erst der Dauerbetrieb im Neustart-Loop.
RUN python -c "import cv2, numpy, requests, yaml, freeze_watchdog; \
print('numpy', numpy.__version__, '| cv2', cv2.__version__)"

CMD ["python", "-u", "-c", "import cpu_compat; cpu_compat.anwenden(); import runpy; runpy.run_path('main.py', run_name='__main__')"]
