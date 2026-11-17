# Beschlüsse B18–B22 (Trainings-Pipeline und Edge-Laufzeit)

Entschieden am 01.11.2026 von Claude im Auftrag des Landwirts („you choose“). Grundlage: Messungen auf dem
Hof-Rechner und fünf Prüfrunden durch qa-waechter. Vor der Umsetzung im Agenten (B19–B21) muss der Landwirt
die Einträge in `ENTSCHEIDUNGEN.md` übernehmen und bestätigen – dort stehen die Regeln für Schwellenänderungen.

**Nummern vorläufig.** Das aktuelle `ENTSCHEIDUNGEN.md` im Repo (mit B13, B14 und den Vorlagen B15–B17)
konnte ich nicht lesen, der Repo-Zugriff wurde verweigert. B15–B17 bleiben unberührt. Beim Übertragen in
`ENTSCHEIDUNGEN.md` Nummern und Überschneidungen mit den Vorlagen prüfen.

| Nr | Datum | Beschluss | Begründung | Status |
| --- | --- | --- | --- | --- |
| B18 | 01.11.26 | **Labeln lokal mit dem Stall-Labeler** (`_training_v1/labeler/stall_labeler.html`). CVAT-1.1-XML bleibt das Austauschformat. app.cvat.ai ist verworfen. CVAT selbst gehostet nur als Option auf einem eigenen LAN-Rechner, nicht auf dem Edge-Rechner. Schafft keinen neuen Cloud-Pfad. Die Spannung aus B14 (Videotransport über die Tuya-Cloud) bleibt eigenständig dokumentiert. | B7 verbietet Frames dauerhaft in der Cloud. Der Gratis-Tarif von CVAT Online erlaubt nur 1 Projekt, 3 Aufgaben und 1 GB. CVAT selbst gehostet braucht Docker; der Edge-Rechner (A6-3650 ohne SSSE3/SSE4.x, 11 GB) trägt den 24/7-Agenten. Der Stall-Labeler läuft ohne Server und ohne Netz (B8: 0 €). Box und Keypoints gehören dort zu einem Objekt, Paarungsfehler entfallen. Nur als geprüft markierte Bilder gehen ins Training. | AKTIV |
| B19 | 01.11.26 | **Edge-Inferenz mit ONNX Runtime (CPU).** PyTorch/Ultralytics nur fürs Training. Die Dekodierung entspricht exakt `abnahme_gates.dekodiere_pose`: quadratische Letterbox 640, Austreibungsklassen mit Mehrfach-Label je Anker. ByteTrack verfolgt nur Klasse 0 (kuh). Fruchtblase und Kälberfüße gehen ungetrackt direkt in die Austreibungslogik. | Gemessen auf dem Hof-Rechner: PyTorch 2.14 bricht bei jeder Faltung ab („could not create a primitive“, oneDNN braucht SSE4.1). Ohne oneDNN schafft PyTorch 0,86 FPS (Gate D nicht bestanden). ONNX Runtime schafft 1,77–1,87 FPS reine Inferenz und 1,46 FPS Ende-zu-Ende (bestanden). Gemessen in der Cowork-VM mit 2 von 4 Kernen und Zufallsgewichten. Die Gates gelten nur bei identischer Dekodierung. Ultralytics-argmax fände weniger Austreibungs-Detektionen. Würden Mehrfach-Label-Boxen getrackt, entstünden Phantom-Kuh-IDs. | BESCHLOSSEN – Umsetzung offen |
| B20 | 01.11.26 | **Bildqualitäts-Gate im Agenten.** Defektbilder (`bildqualitaet.defekt_anteil` > 0.04) kommen nicht in die Schwanzwinkel-Statistik, und die Kalibrierung pausiert. Die Austreibungs-Erkennung läuft auf ihnen weiter (nie unterdrücken). Bei einer Defektquote > 50 % über 10 min: Info-Ereignis „Bildqualität degradiert“ an Dashboard und Tagesbericht, kein Push (B12). | 11,7 % der ausgewählten Silent-Mode-Bilder (302 von 2.586, fast nur nachts) zeigen Dekodier-Streifen nach Paketverlust. Verschmierte Bereiche erzeugen falsche Winkel. Ein Austreibungs-Treffer auf einem Defektbild darf trotzdem nie verloren gehen. Stille Degradation verlangt, die Einschränkung zu melden. | BESCHLOSSEN – Umsetzung offen |
| B21 | 01.11.26 | **Datensatz-Konventionen:** Silent-Mode-Dateiname `<kamera>_<YYYYmmdd-HHMMSS>.jpg` (UTC). Split nach Stalltag (12–12 Uhr Ortszeit). Label-Vertrag YOLO-seitig unverändert (kuh, amniotic_sac, calf_legs; spine_end, tail_base, tail_tip). Annotationsschema v2: Box `kuh` + Skelett `kuh_pose` mit gemeinsamer group_id, Tag `geprueft`. Modellabnahme verbindlich am ONNX-Modell, SHA-256 in der Modellkarte. | Die Kamera-Ansicht wechselt über die Tage, die Dateinamen tragen aber keinen Kameranamen. UTC-Kalendertage teilen jede Nacht auf beide Splits auf (Leck). CVATs YOLO-Pose-Export berechnet die Box aus 3 Punkten (unbrauchbar), deshalb echte Box + Skelett. | AKTIV (Training) / Kamerapräfix offen |
| B22 | 01.11.26 | **Colab-Training nur vorübergehend (Auslegung von B7).** `datensatz_v1.zip` liegt nur für den Lauf in Drive. Das Notebook löscht es nach einem erfolgreichen Lauf (danach Drive-Papierkorb leeren). Die Laufsicherung in Drive enthält keine Bilder (Mosaike ausgenommen). Dauerhaft bleiben nur Modelle, Gates, Modellkarte und Metriken. | B7 verbietet Frames *dauerhaft* in der Cloud. Training auf eigener GPU kostet Geld (B8), Colab ist kostenlos. Die vorübergehende Verarbeitung der kuratierten Stillbilder ist die einzige, eng begrenzte Nutzung. | AKTIV |

## Widerspruch (bewusst geprüft)

- **B18 gegen „CVAT steht in der Vision“:**
  - Der Stall-Labeler ist Eigenbau und hat weniger Funktionen: kein Mehrbenutzer, keine Interpolation.
  - Für einen Landwirt mit ~2.300 Bildern zählen Tempo und Datenhoheit mehr.
  - Die Pakete und XML bleiben CVAT-kompatibel, ein späterer Wechsel kostet nichts.
- **B19 gegen „ByteTrack kommt aus Ultralytics“:**
  - Der Import von Ultralytics bleibt möglich. Nur die Faltung scheitert.
  - Der Tracker braucht keine Faltung und läuft auf den ONNX-Detektionen.
- **B20 gegen „Defektbilder ganz verwerfen“:**
  - Das wäre einfacher, könnte aber eine Fruchtblase im intakten Bildteil verlieren. Das widerspricht dem Recall-Ziel.
  - Deshalb nur die Statistik schützen, die Austreibung nicht.
- **B21 gegen „Label-Vertrag unverändert“:**
  - YOLO-seitig bleibt alles gleich.
  - Der Konsistenztest „Label-Vertrag (CVAT, YAML, Edge-Konfig)“ in kuhwatch muss `kuh_pose` als CVAT-Hilfslabel zulassen.

- **B22 gegen „B7 hart“:**
  - Strenger wäre lokales Training. Auf dem A6-3650 ohne GPU dauert das Tage, und PyTorch-Faltung scheitert dort.
  - Deshalb: vorübergehend, gelöscht, ohne Bildkopien in der Sicherung.

## Folgeaufgaben

1. Diese Einträge in `ENTSCHEIDUNGEN.md` (Repo) übernehmen, Nummern prüfen, vom Landwirt bestätigen.
2. Danach B19–B21 im Agenten umsetzen: `UEBERGABE_AGENT_B19-B21.md` (Spezifikation + Goal-Vertrag für Claude Code im Repo).
3. Offene Vorlagen B15–B17 weiterhin durch den Landwirt.


## Ergänzungen bei der Umsetzung (10.11.2026)

Eingetragen in `ENTSCHEIDUNGEN.md` (Projekt), Zeilen B19 und B20. Begründung und Belege in
`docs/onnx-laufzeit-spezifikation.md` (§5).

- **B19, Schwellen:**
  - Die Logik nimmt Objekte ab 0.25.
  - ByteTrack nimmt Kühe ab 0.10, wie bisher Ultralytics-`track`. Die Logik-Objekte bleiben dabei identisch.
  - Ein Keypoint gilt ab 0.5 als sichtbar; das ist die bisherige Kappung von Ultralytics 8.3.40.
  - NMS 0.7.
  - Gate B rechnet nur mit sichtbaren Punkten. Gate B2 lässt zu, dass erhobene Schwänze höchstens 10 Prozentpunkte
    seltener messbar sind als anliegende (je n ≥ 30).
- **B20:**
  - Neue Texte. „Pausiert“ stimmte nicht, und gestreifte Bildteile sind nicht auswertbar.
  - Auf Defektbildern hält die Uhr der Austreibungs-Episode an, höchstens 2 Bildabstände je Bild.
  - Die Aufsprung-Lücke ist auf `brunst_min_dauer_s` begrenzt.
  - Weckregel (B12-Auslegung): „AUS“ und „BLIND“ wecken. „EINGESCHRÄNKT“ weckt nur im Wach-Modus. Entwarnungen gehen
    still und über denselben Kanal wie die Meldung.
- **Gate D** ist mit 1 Kern nicht bestanden; die Entscheidung ist offen (Spezifikation §6).
