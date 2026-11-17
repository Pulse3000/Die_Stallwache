# AUFTRAG an Trainer — Tagesreport-Punkt 4 messbar machen

**Ziel:** `tools/datensatz_inventur.py` läuft gegen die echten Silent-Mode-Aufnahmen und liefert
den Abschnitt „Datensatz (Silent Mode)" für `docs/metriken.md` (Repo Die_Stallwache). Label-Vertrag
(CVAT-Skelett + Datensatz-YAML) liegt konsistent zur Edge-Konfig im Repo.

**Kontext (zuerst lesen):** `tools/datensatz_inventur.py` · `tests/test_datensatz_inventur.py` ·
`tests/test_vertrag_konsistenz.py` · `training/stallwache-pose.yaml` · `training/cvat-labels.json` ·
Skill `training-pipeline` · `.env.example`

Warum zuerst die Inventur: Ohne Modell bleiben die Erkennungsmetriken „tbd". Messbar ist heute
schon der Datensatz — Bildzahl, einzigartige Bilder, IR-Anteil gegen B9, Stall-Tage, Split.
Damit wird aus „unverändert" im Tagesreport ein Fortschrittswert.

## Plan-Fragen (mit Pfaden beantworten)

1. Wohin schreibt kuhwatch im Silent Mode (Pfad im Container, Volume auf dem Host)?
2. Exaktes Dateinamensmuster — drei echte Dateinamen.
3. Ist der Ordner aus dieser Session lesbar (lokal, SSH, Tailscale)?
4. Welche Bildbibliothek ist im Repo vorhanden (Pillow / OpenCV)?
5. Wird `./aufnahmen/crops/` (B6) bereits befüllt?

## Definition of Done

- [ ] Testfall mit dem echten Dateinamensmuster **ergänzt** (nicht ersetzt); alle Tests grün
- [ ] Inventur auf echten Aufnahmen gelaufen: `metriken-datensatz.md` und `inventur.json` erzeugt
- [ ] Lichtphasen-Schwellen an je 10 echten Bildern je Phase stichprobenartig bestätigt (Dateinamen im Prüfbericht); Schwellenänderung nur mit diesem Beleg
- [ ] Prüfbericht nennt: einzigartige Bilder, IR-Anteil und B9-Status, Stall-Tage, Split-Vorschlag
- [ ] Doku aktualisiert; 1–3 Zeilen „Grenzen dieser Session" in `CLAUDE.md`
- [ ] PR offen; Merge nach qa-waechter

## Verbote

- Bilder verschieben, löschen, umbenennen oder hochladen — die Inventur liest nur
- Label-Vertrag ändern (Namen, Indexreihenfolge, Klassen; keine Klasse „kalbt")
- Split nach Frames statt nach Stall-Tagen
- neue Abhängigkeiten außer numpy + vorhandener Bildbibliothek; Tests abschwächen

**Rückgabe:** PR-Link, `metriken-datensatz.md`, Prüfbericht.

## Menschliche Schritte danach (nicht Teil des Goals)

1. CVAT-Projekt aus `training/cvat-labels.json` anlegen. Das Raw-Format folgt der CVAT-Skelett-Doku,
   ist aber nicht gegen eure CVAT-Version geprüft. Lehnt CVAT es ab: im Skelett-Konstruktor
   nachbauen — 3 Punkte, 2 Kanten, Reihenfolge exakt wie in der YAML.
2. **Pilot vor dem Großlabeln:** 10 Bilder labeln → Export „Ultralytics YOLO Pose" →
   `yolo val data=training/stallwache-pose.yaml` läuft fehlerfrei. Dabei prüfen:
   - Box der Klasse `kuh` umfasst das ganze Tier, nicht nur die drei Punkte (`haltung.py` braucht die Ganzkörper-Box).
   - `amniotic_sac`/`calf_legs` tragen im Export Null-Keypoints mit Sichtbarkeit 0.
   - `spine_end` ist in mindestens 9 von 10 Bildern sichtbar — sonst Definition (B15) vor dem Großlabeln anpassen.
3. Danach `RUHELAGE_FALLBACK` (94°, aus Skelettgeometrie) an den Pilot-Labels neu bestimmen.

## Folgeauftrag

Vorauswahl zum Labeln mit dem vorhandenen `yolov8n.onnx` (COCO `cow`): leere Buchtbilder
aussortieren, Kuh-Boxen als CVAT-Vorannotation importieren (Keypoints bleiben Handarbeit).
