# Übergabe: B19–B21 im Edge-Agenten umsetzen

**Vorbedingung:** B18–B22 sind in `ENTSCHEIDUNGEN.md` übernommen und vom Landwirt bestätigt
(B20 bringt neue Schwellen; Schwellenänderungen am Agenten ohne Eintrag sind verboten).

Für eine Claude-Code-Sitzung im Repo `Die_Stallwache` (Ort des Inferenzpfads: `edge-agent/` oder
`kuhwatch/erkennung/` – im Plan-Modus klären). Ablauf wie im Goal-Paket vom 16.10.: Plan-Modus → Plan
freigeben → `/goal` → Diff-Review + qa-waechter → Merge.

Bausteine liegen schon vor und sind getestet:
- `aufnahmen/_training_v1/werkzeuge/abnahme_gates.py`: `OnnxModell`, `dekodiere_pose`
- `aufnahmen/_training_v1/werkzeuge/bildqualitaet.py`: `defekt_anteil`

Diese Funktionen übernehmen, nicht neu erfinden: Die Abnahme-Gates gelten nur bei identischer Dekodierung.

## B19 – ONNX-Runtime-Inferenz

| Punkt | Festlegung |
|---|---|
| Grundsatz | Das Modell läuft als ONNX mit `onnxruntime` (CPU). Kein Faltungsaufruf über PyTorch im Laufzeitpfad. |
| Grenzen | Austreibung und Eskalation nie hinter Sperre, Fenster oder Kuh-Erkennung. Kein Frame-Upload (B7). Einzige neue Abhängigkeit: `onnxruntime`. |
| Schwellen | Kandidaten ab Konfidenz 0.25, NMS-IoU 0.7 je Klasse. Austreibung > 0.80 aus der Konfig (unverändert). Klassen 1/2 mit Mehrfach-Label je Anker. |
| Config | `modell.pfad` zeigt auf `best_vN.onnx`. `modell.threads` (Standard: alle Kerne). Bildgröße aus dem ONNX-Eingang. |
| Tracking | ByteTrack bekommt **nur Klasse 0 (kuh)** (Pixel, xyxy, conf), Keypoints hängen am Track. Klassen 1/2 (Fruchtblase, Kälberfüße) gehen ungetrackt direkt in die Austreibungslogik. Mehrfach-Label-Boxen würden sonst Phantom-IDs oder Klassenwechsel erzeugen. |
| Abnahme | (1) Unit-Test: Adapter liefert für eine feste Rohausgabe dieselben Objekte wie `dekodiere_pose`. (2) Auf dem Hof-Rechner: `abnahme_gates.py laufzeit` ≥ 1 FPS Ende-zu-Ende (vorläufig mit `modelle/laufzeittest_yolov8n-pose_3kpt_640.onnx`, später mit `best_v1.onnx`). (3) Auf 20 Val-Bildern identische Austreibungs-Detektionen wie `abnahme_gates.py val`. |
| Risiken | Abweichende Vorverarbeitung (Letterbox, BGR/RGB) verfälscht die Gate-Gültigkeit. Zu viele Threads verdrängen andere Dienste. |

## B20 – Bildqualitäts-Gate

| Punkt | Festlegung |
|---|---|
| Grundsatz | Jedes Bild bekommt vor der Auswertung `defekt_anteil`. Defektbilder zählen nicht für Schwanzwinkel-Fenster und Kalibrierung. |
| Grenzen | Die Austreibungs-Erkennung läuft auf Defektbildern weiter. Kein Bild wird für Austreibung verworfen. |
| Schwellen | `defekt_anteil` > 0.04 = Defektbild. Degradiert, wenn > 50 % Defektbilder in 10 min. Meldung 1× je Episode; Ende nach 10 min unter der Schwelle. |
| Config | `qualitaet.schwelle_defekt: 0.04`, `qualitaet.degradiert_anteil: 0.5`, `qualitaet.fenster_min: 10` |
| UI-Text | „Bildqualität degradiert (stallwache): 63 % der Bilder der letzten 10 min mit Dekodier-Streifen. Austreibungs-Erkennung läuft weiter, Schwanzwinkel-Auswertung pausiert.“ — Info-Ereignis (`typ: info`) fürs Dashboard + Zeile im Tagesbericht, kein Telegram-Push (B12). |
| Abnahme | Tests: Defektbild verändert das 30-min-Fenster nicht. Austreibung > 0.80 auf Defektbild → Sofort-Alarm. Degradations-Info genau 1× je Episode. Zähler im Tagesbericht. |
| Risiken | Fehlalarm des Defektfilters an Gittern → Schwanzwinkel-Pause. Die Schwelle 0.04 ist an 36 Stichproben kalibriert; Quote im Tagesbericht beobachten. |

## B21 – Kamerapräfix im Silent Mode

| Punkt | Festlegung |
|---|---|
| Grundsatz | Silent-Mode-Bilder heißen `<kamera>_<YYYYmmdd-HHMMSS>.jpg` (UTC), z. B. `stallwache_20261102-031500.jpg`. |
| Grenzen | Bestehende Dateien nicht umbenennen. Die Werkzeuge lesen Datum/Uhrzeit mit und ohne Präfix. |
| Abnahme | Test auf das Namensmuster. `datensatz_inventur.py` und `cvat_zu_yolo_pose.py` erkennen beide Formen. |
| Label-Vertrag | Konsistenztest „Label-Vertrag (CVAT, YAML, Edge-Konfig)“: CVAT-Seite = Schema v2 (`kuh` Box, `kuh_pose` Skelett mit spine_end, tail_base, tail_tip; `amniotic_sac`, `calf_legs`). YAML/Edge-Klassen unverändert. |

## Plan-Modus-Prompt

```
Plan-Modus, keine Logik. Lies ENTSCHEIDUNGEN.md (B7, B12, B18–B22), edge-agent/aufnahmen/_training_v1/UEBERGABE_AGENT_B19-B21.md,
edge-agent/aufnahmen/_training_v1/werkzeuge/{abnahme_gates.py,bildqualitaet.py} und den heutigen Inferenzpfad
(Modell laden, Vorverarbeitung, Tracking, Silent Mode). Beantworte mit Pfaden: Wo wird das Modell geladen? Wo
entstehen Kuh-ID und Schwanzwinkel? Wo wird das Silent-Mode-Bild gespeichert? Welche Tests decken das ab?
Schlage die Änderungen je Beschluss und die Tests vor. Warte auf Freigabe.
```

## Goal-Vertrag

```
**Objective:** Der Edge-Agent setzt B19–B21 um: ONNX-Runtime-Inferenz mit derselben Dekodierung wie die Abnahme-Gates, Bildqualitäts-Gate, Kamerapräfix im Silent Mode – gemäß freigegebenem Plan.
**Read first:** UEBERGABE_AGENT_B19-B21.md, ENTSCHEIDUNGEN.md (B18–B22 müssen eingetragen sein, sonst anhalten), werkzeuge/abnahme_gates.py, werkzeuge/bildqualitaet.py, Inferenzpfad und Tests laut Plan
**Constraints:** Schwellen nur aus der Konfig; Austreibung und Eskalation nie hinter Sperre, Fenster, Qualitätsfilter oder Kuh-Erkennung; kein Video- oder Frame-Upload (B7); keine laufenden Kosten (B8); einzige neue Abhängigkeit onnxruntime; Dekodierung aus abnahme_gates übernehmen statt neu schreiben; ENTSCHEIDUNGEN.md nicht anfassen; keine Tests löschen, überspringen oder abschwächen; nur im Plan genannte Dateien ändern
**Validate:** `pytest -q` nach jeder Änderung; am Ende auf dem Hof-Rechner `python3 edge-agent/aufnahmen/_training_v1/werkzeuge/abnahme_gates.py laufzeit --modell <onnx> --bilder-ordner edge-agent/aufnahmen --stalltag 2026-10-18 --anzahl 30`
**Document:** Dokumentiere jede Änderung knapp und gezielt — neue .md-Dateien anlegen oder bestehende Doku aktualisieren (Abschnitt „Umsetzung“ in dieser Übergabe); am Ende 1–3 Zeilen „Grenzen dieser Session“ an CLAUDE.md anhängen.
**Checkpoints:** B19 Adapter + Unit-Test → B19 Laufzeit auf dem Hof-Rechner → B20 Gate + Tests → B21 Dateiname + Konsistenztest; Fortschritt kurz loggen
**Stop when:** gesamte Suite grün, Laufzeit ≥ 1 FPS auf dem Hof-Rechner gemessen und PR mit Prüfbericht offen (Merge erst nach qa-waechter), ODER der Inferenzpfad ist nicht eindeutig auffindbar bzw. liegt in zwei Repos – dann anhalten und fragen
```


## Umsetzung (05.–10.11.2026)

Umgesetzt von Claude (Cowork) im Repo `Die_Stallwache`, Ort `edge-agent/main.py` (Begründung:
`docs/onnx-laufzeit-spezifikation.md` §0). Maßgeblich ist jetzt `docs/onnx-laufzeit-spezifikation.md` mit Messungen (§3),
Abweichungen von diesem Entwurf (§5) und offenen Entscheidungen (§6).

- **B19:** ONNX-Adapter mit wörtlich übernommenem `OnnxModell` und `dekodiere_pose`; ein Wächtertest vergleicht Quelltext
  und Ergebnisse mit `abnahme_gates.py`.
  - ByteTrack bekommt nur Kühe ab 0.10, die Logik nimmt Objekte ab 0.25.
  - Die Thread-Zahl folgt der cgroup-Quote.
  - Beim Laden läuft eine Probe-Inferenz; Ausfall-Wächter melden per Telegram.
- **B20:** `BildQualitaet` mit wörtlich übernommenem `defekt_anteil`.
  - Defektbilder bleiben aus dem Fenster und aus dem Tracker heraus.
  - Auf Defektbildern hält die Austreibungs-Uhr an, höchstens 2 Bildabstände je Bild.
  - Die Brunst-Lücke ist begrenzt.
  - Neu: Bildstörungs-Info, Blind-Wächter, Weckregel.
- **B21:** Silent-Mode-Dateien heißen `<kamera>_<UTC>.jpg`; die Werkzeuge lesen beide Formen. `datensatz_inventur`
  rechnet den Stalltag in Ortszeit. Dazu der Label-Vertrag-Test und `cvat_labels_stallwache_v2.json` im Repo.
- **Training:** Gate B rechnet wie der Agent nur mit sichtbaren Punkten. Neues Gate B2 prüft die Messbarkeit bei
  erhobenem Schwanz.
- **Prüfung:** `python3 edge-agent/tests/alle_tests.py` ist grün.
  - Hof-VM: 16 Dateien, 1 übersprungen (ByteTrack, Ultralytics fehlt in der VM).
  - Cloud: mit Ultralytics 8.3.40 (image-nah: Python 3.11, numpy 1.26, OpenCV 4.10, ONNX Runtime 1.31) und 8.4.197.
  - training_v1: 70 Tests, Smoke 14/14, Labeler 5.
- **Review:** qa-waechter Freigabe, ki-wache einverstanden (10.11.2026, drei Runden).
- **Nicht erfüllt:** Abnahme (2), Gate D mit 1 Kern (0,94–0,99 FPS; mit 2 Kernen 1,64 FPS).
- **Vor dem Scharfschalten offen:** Spezifikation §6. Der 15-min-Cooldown auf der Austreibung ist eine Sperre.
