# Offline-Wheels fuer den Analyse-Build (optional)

Liegen hier `*.whl`-Dateien, installiert `docker compose build` mit
`ANALYSE=1` sie nach den oeffentlichen Paketen ohne Abhaengigkeiten darueber.
Gedacht fuer stallwache-lela (AMD A6-3650 ohne AVX): torch, torchvision und
onnxruntime in Builds, die dort laufen, dazu was offline gebraucht wird
(kuhwatch-Rezept, `docs/ein-edge-agent-spezifikation.md` U3).

Die Wheels werden nicht eingecheckt (`.gitignore`). Auf dem Geraet liegen
sie bisher unter `~/kuhwatch/wheels/`.
