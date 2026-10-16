# Modellkarte best_vN.pt

Kopie je Modellversion als `MODELLKARTE_vN.md` neben der Modelldatei.
Ein Modell ohne Modellkarte wird nicht scharfgeschaltet.

## Kenndaten

| Feld | Wert |
| --- | --- |
| Datei | `best_vN.pt` |
| Basis | `yolov8n-pose.pt` |
| Trainingsdatum | JJJJ-MM-TT |
| Datenzeitraum (Stalltage) | JJJJMMTT – JJJJMMTT |
| Kameras | stallwache, … |
| Split | `split.json`: Val-Tage …, Geburtstage … |

## Datensatz

| Klasse / Licht | Tag | Dämmerung | IR-Nacht | Summe |
| --- | --- | --- | --- | --- |
| Bilder gesamt | | | | |
| `kuh` (Instanzen) | | | | |
| `amniotic_sac` | | | | |
| `calf_legs` | | | | |

IR-Anteil (Ziel ≥ 1/3, `datensatz.py bilanz`): …
Beimischung offener Datensätze (nur train): …

## Abnahme (`abnahme.py`-Bericht hier einfügen)

| Gate | Kriterium | Ergebnis | Status |
| --- | --- | --- | --- |
| 1 Austreibung | Recall = 1.0 bei Konfidenz ≥ 0.80 | | |
| 2 Keypoints | mittl. Winkelabweichung < 10° (n ≥ 30) | | |
| 3 Fehlalarm-Budget | 24 h ereignislos: 0 Austreibung, ≤ 1 Kalbeverdacht | | |
| 4 Laufzeit | ≥ 1 FPS auf der Zielhardware | | |

## Bekannte Schwächen

- …

## Scharfgeschaltet

| Datum | Kamera | Austreibungs-Logik | Bemerkung |
| --- | --- | --- | --- |
| | | an / aus (Gate 1) | |
