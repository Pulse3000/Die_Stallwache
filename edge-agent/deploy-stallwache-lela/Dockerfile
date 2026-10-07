# Stallblick Edge-Agent fuer die Stallwache LELA (AMD A6, CPU-only).
# Basis ist das bereits vorhandene, auf die alte CPU abgestimmte Image
# (torch 2.14.1+cpu, ultralytics, lap, cv2). Es wird nur der Agent ergaenzt.
ARG BASIS=kuhwatch-stallwache:latest
FROM ${BASIS}
WORKDIR /agent
RUN pip install --no-cache-dir "paho-mqtt>=2,<3" "PyYAML>=6,<7" || true
COPY main.py tracker-kuh.yaml ./
COPY deploy-stallwache-lela/cpu_compat.py ./
CMD ["python", "-u", "-c", "import cpu_compat; cpu_compat.anwenden(); import runpy; runpy.run_path('main.py', run_name='__main__')"]
