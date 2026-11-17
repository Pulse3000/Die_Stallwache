# Erkennungsvertrag v1 (Edge) — Stand 16.10.2026

**Status:** Spezifikation für den Wächter-Goal. Erst Spezifikation und Tests, dann Code.
**Vertragstests:** `tests/test_erkennungsvertrag.py` (58) · `tests/test_vertrag_konsistenz.py` (3)
**Referenz:** `erkennung/` — reine Logik, nur Standardbibliothek, besteht alle Vertragstests.
**Beschlüsse:** B1, B3, B4, B7, B8 (AKTIV) · B15–B17 (Vorlage, siehe `01_BESCHLUSSVORLAGEN_B15-B17.md`)

Werte, die Beschlusssache sind, prüfen die Tests relativ zur Konfig. Aktive Werte
(0.80 · 30 min · 60 min) sind festgenagelt.

---

## Anlass: Befunde im Codestand (`Die_Stallwache/funktionen`, Projekt-Snapshot)

| # | Befund | Fundstelle | Folge | Punkt |
|---|---|---|---|---|
| E1 | `calf_legs` hat keinen Alarmpfad | `pipeline.py:54`, `wache.py:152` | Recall-Lücke, wenn Blase gerissen/verdeckt | V1 |
| E2 | Austreibung hängt an einer erkannten Kuh (`sac_conf` ist Feld der Kuh-Erkennung) | `pipeline.py:54/170` | Blase ohne Kuh-Box (liegend, IR, verdeckt) geht verloren | V1 |
| E3 | Austreibung feuert in jedem Frame; ein Test kodiert das | `wache.py:152–164`, `test_stallwache.py` | 1 fps → 3.600 Meldungen/h | V2 |
| E4 | Eskalation (B3, AKTIV) fehlt | – | Pflichtfeature fehlt | V2 |
| E5 | Code liest `back_mid`, Label-Vertrag definiert `spine_end` | `kalibrierung.py:44–75`, `pipeline.py:147`, `wache.py:144`, `main.py:84/173` | Kalbeverdacht verstummt still, sobald das Modell nach Label-Vertrag trainiert ist | V0, V4 |
| E6 | Kein Keypoint-Konfidenzfilter im Alarmpfad (nur im Kalibrierpfad) | `wache.py:143` vs. `pipeline.py:145` | verdeckte Schwanzspitze verfälscht das Fenster | V4 |
| E7 | Mindestbelegung fest 300 Frames | `wache.py:33` | unter ~0,17 fps (Snapshot-Pfad) nie eine Entscheidung | V5 |
| E8 | Sperre nur je Tier, nicht je (Tier, Typ) | `wache.py:124–130` | Brunstalarm sperrt Kalbeverdacht derselben Kuh | V6 |
| E9 | Eskalation hat keinen Schema-`typ` | Ereignis-Schema | Dashboard kann B3 nicht hervorheben | V7 |

Gegenprobe: 12 Fehlerbilder (darunter E1, E2, E3, E5, E6, E7) als Mutation in die Referenz
eingebaut — die Vertragstests werden in allen 12 Fällen rot. Die Tests fangen also genau
die Fehler des Codestands.

---

## V0 — Fähigkeitsprüfung beim Start

Je Kamera beim Prozessstart: Klassen des geladenen Modells (über `klassen_alias`
normalisiert, z. B. COCO `cow → kuh`) und deklarierte Keypoints gegen den Vertrag
prüfen. Jede fehlende Fähigkeit = genau ein `info`-Ereignis. Leere Liste = Vertrag erfüllt.
Stand laut Tagesreport (generisches `yolov8n.onnx`): zwei Meldungen —
Austreibung nicht verfügbar, Kalbeverdacht nicht verfügbar.

## V1 — Austreibung (Prio 1), frame-weit

- Auslöser: beliebiges Objekt im Frame mit Klasse ∈ {`amniotic_sac`, `calf_legs`} und Konfidenz **> 0.80** (strikt).
- Unabhängig von Kuh-Erkennung, Identität, Keypoints, Kalibrierung, Fenster und Sperre.
- Gemeldet im selben Aufruf, der den Treffer verarbeitet — keine Verzögerung.
- Das Ereignis trägt `belege` (auslösende Detektionen) für das annotierte Beweisbild (B1).
- Konfidenz = Maximum der Belege.
- Text: `SOFORT-ALARM: <Fruchtblase | Kälberfüße | Fruchtblase und Kälberfüße> bei <Kuh-ID | nicht zugeordneter Kuh> erkannt! (Kamera <k>)`

## V2 — Episoden und Eskalation

- Episode je (Kamera, Kuh-ID oder None). Erster Treffer → genau ein `austreibung`.
- Folgetreffer verlängern die Episode, erzeugen keinen neuen Alarm.
- Ende: mehr als 1.800 s ohne Treffer. Der nächste Treffer eröffnet eine neue Episode.
- Eskalation: erster Treffer mit ≥ 3.600 s seit Episodenbeginn → genau ein `eskalation` je Episode, nie gesperrt.
  Text: `ESKALATION: … seit <n> Min. sichtbar – Geburt kontrollieren. (Kamera <k>)`
- `episode_aktiv(kamera, kuh_id, jetzt)` steht der Integration zur Verfügung (I3).

## V3 — Kuh-Zuordnung (Anreicherung, nie Bedingung)

- Zugeordnet wird die Kuh, deren um 15 % erweiterte Box den Mittelpunkt der Detektion
  enthält (Fruchtblasen treten hinter der Kuh-Box aus). Mehrere Kandidaten: größte Überlappung.
  Kein Kandidat: Kuh-ID None — der Alarm geht trotzdem raus.
- Die Kuh-ID liefert ein injizierter Auflöser. In der Integration: `identitaet.py`
  (stabile IDs), nicht die flüchtige Track-ID.

## V4 — Keypoint-Eingang (Kalbeverdacht)

- Modellausgabe 3 × (x, y, Konfidenz) → Namen in Vertragsreihenfolge
  (`Konfig.keypoint_namen` = CVAT-Skelett = `training/stallwache-pose.yaml`).
  Abweichende Form → `ValueError` beim Laden, nie stilles Vertauschen.
- Winkel nur, wenn alle drei Keypoints Konfidenz ≥ 0,5 haben. Sonst `None` = **Lücke**,
  nicht „unter Schwelle" — der Frame kommt nicht ins Fenster.
- Formel identisch zu `kalibrierung.rohwinkel`: u = Rücken − Basis, v = Spitze − Basis, arccos.

## V5 — Konfiguration

- Alle Schwellen aus `Konfig` bzw. der Konfigdatei. Unbekannte Schlüssel brechen den Start ab.
- `dominanz_effektiv`: Anteil, im Wach-Modus halbiert. Wert selbst: B16.
- `min_frames_entscheidung(fps)` = ⌈Fenster × fps × 1/6⌉ → 1 fps: 300 (Codestand), 0,1 fps: 30.
  Wach-Modus halbiert. Die Integration übergibt die **gemessene** Frame-Rate.

## V6 — Sperre

- Je (Kuh-ID, Typ), 900 s. `austreibung` und `eskalation` sind nicht sperrbar —
  der Versuch wirft `ValueError`.

## V7 — Abbildung auf `POST /api/events`

- Genau die fünf Vertragsfelder: `typ`, `kuhId`, `kamera`, `nachricht`, `konfidenz`.
- Eskalation: bis B17 als `typ: austreibung` mit Präfix „ESKALATION"; nach B17 per
  `eskalation_api_typ: eskalation` umschaltbar.
- Unbekannter typ, leere Nachricht, Konfidenz außerhalb [0, 1] → `ValueError`
  (im Versandpfad gefangen, nie in der Auswertung).
- Kamera wird nicht gefiltert (`stallbox`, B14).

---

## Integrationspflichten — vom Wächter als Tests gegen den integrierten Pfad zu schreiben

| ID | Pflicht |
|---|---|
| I0 | End-to-End-Probe: synthetische Modellausgabe (3 Keypoints in Vertragsreihenfolge) → Pipeline → Schwanzfenster wächst. Fängt E5. |
| I1 | Frame mit Fruchtblase > 0.80 und ohne jede Kuh-Erkennung → genau ein Ereignis im Versandpuffer. |
| I2 | Frames mit Winkel `None` verändern das Schwanzfenster nicht. |
| I3 | Kalbeverdacht für Kuh X ist unterdrückt, solange eine Austreibungs-Episode für X aktiv ist. |
| I4 | Der Alarmwächter liest `dominanz_effektiv` und `min_frames_entscheidung(fps_gemessen)` aus der Konfig. |
| I5 | Versandfehler (Telegram down, Dashboard 401/503) blockieren die Auswertung nicht; Austreibung wird gepuffert und wiederholt, nie verworfen. |
| I6 | V0-Meldungen werden einmal je Prozessstart versendet. |

## Betriebsmodi (Soll — im Plan-Modus mit dem Ist von `SILENT_MODE` abgleichen)

| Modell | `SILENT_MODE` | Verhalten |
|---|---|---|
| keines | – | Silent: 1 Bild/120 s, keine Inferenz |
| generisch (COCO) | 1 | Silent + V0 meldet „nicht verfügbar" |
| eigenes, Abnahme-Gates offen | 1 | Schattenbetrieb: Ereignisse nur lokal protokollieren |
| eigenes, Abnahme-Gates bestanden | 0 | scharf |

## Bekannte Grenzen (bewusst, dokumentiert)

- Zwei gleichzeitige, beide unzugeordnete Austreibungen in einer Kamera bilden eine Episode.
- Zuordnungswechsel None ↔ Kuh X erzeugt höchstens einen zweiten Alarm je Geburt (Recall vor Ruhe).
- Verdeckung über 30 min beendet die Episode; die Eskalation zählt ab dem nächsten Treffer neu.
- Der Rohwinkel ist vorzeichenlos. Bei Ruhelage 94° fällt ein Schwanz, der mehr als
  ~41° über die Waagrechte gehoben ist, unter die 45°-Schwelle (Ausschlag = 86° − Hebung).
  README §3e nimmt „nicht über die Waagrechte" an — Prüfung im Keypoint-Gate an
  Realbildern, Literatur über Späher-Frage F1.

## Umsetzung

*(vom Wächter nach dem Goal-Lauf zu füllen: Ort der Module, Adapter, ersetzte Stellen, Testnamen I0–I6)*
