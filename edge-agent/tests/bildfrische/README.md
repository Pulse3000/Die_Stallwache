# Teststrecke Bildfrische

Misst das Alter jedes analysierten Bilds an einem echten RTSP-Stream
(`docs/bildfrische-spezifikation.md`). Die Testquelle brennt ihre Sendezeit
als Binärcode in jedes Bild; der Leser decodiert sie.

Voraussetzungen: `ffmpeg`, [MediaMTX](https://github.com/bluenviron/mediamtx)
(einzelne Datei, getestet mit v1.9.3), Python mit `opencv-python-headless`,
`numpy`, `requests`, `PyYAML`. Nicht Teil von `alle_tests.py` (die laufen ohne
Installation); die Logik prüft `../test_bildgreifer.py`.

```bash
./mediamtx &                                         # RTSP auf :8554
python3 sender.py rtsp://127.0.0.1:8554/stall 25 &   # 720p25 mit Sendezeit
python3 messung.py agent  --sekunden 240             # StreamHandler aus main.py
python3 messung.py puffer --sekunden 240             # früheres Lesemuster zum Vergleich
python3 messung.py agent  --sekunden 150 --bremse 0.06   # zu langsamer Rechner
```

kuhwatch misst mit derselben Quelle: `python3 tests/messe_bildalter.py`
im kuhwatch-Repo.

Erwartung (Kriterien 1–2): `agent` hält das Bildalter unter 1 s, und
aufeinanderfolgende Bilder liegen im Video etwa `1/ziel_fps` auseinander.
`puffer` zeigt den Befund: Das Alter wächst mit der Laufzeit, der Abstand
liegt bei 1/Kamera-fps (40 ms).

Ausfall (Kriterium 4): MediaMTX während der Messung beenden und neu
starten. Ab dem Ende der Verbindung kommt „kein Bild“. Nach der Rückkehr ist
das Bild spätestens nach Backoff-Deckel + 5 s wieder frisch.

Am Gerät (Kriterium 9) gibt es keine eingebrannte Sendezeit. Dort vergleicht
man die Uhr im Kamerabild (OSD) mit der Uhrzeit im Dateinamen eines
Silent-Mode-Trainingsbilds.
