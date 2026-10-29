# Entscheidung: Brunst zuerst, Kalbeüberwachung danach

Stand: 29.10.2026 · Entscheidung des Betreibers: „Zuerst fangen wir mit der
Brunsterkennung an und dem Aufsprungverhalten der Kühe, die
Kalb-Überwachung und Kalb-Erkennung kommt erst danach.“
**Status: umgesetzt im Repo (Trainingsweg, Abnahme, ehrliche Statusmeldung).
Am Gerät offen, bis das erste Modell läuft.**

## 1. Grundsatz

1. **Das erste eigene Modell (v1) kennt nur Kühe.** Eine Klasse `kuh`, nur
   Boxen (YOLOv8n-Detection), getrackt mit ByteTrack. Daraus erkennt der
   Agent das **Aufsprungverhalten** mit der bestehenden, unveränderten Regel
   (`LogicEngine._brunst`): Zwei getrackte Kuh-Boxen überlappen (IoU ≥ 0,15),
   die obere setzt mindestens 20 % der Boxhöhe höher an, und das hält
   ≥ `logik.brunst_min_dauer_s` (4 s) an. Gemeldet wird „Aufsprungverhalten
   erkannt (Kuh #A auf Kuh #B …)“, mit Bild und Kuh-Nummer.
2. **Was v1 nicht kann, wird nicht behauptet.** Austreibung (Fruchtblase,
   Kälberfüße) und Kalbeverdacht (Schwanzwinkel) brauchen Klassen bzw.
   Keypoints, die v1 nicht hat. Der Agent erkennt das selbst
   (`nicht_scharf()` in `edge-agent/main.py`) und meldet es:
   - in der Startmeldung und im Tagesbericht: „Scharf: Brunst (Aufsprung) ·
     NICHT scharf: Austreibung (Fruchtblase/Kälberfüße), Kalbeverdacht
     (Schwanzwinkel)“;
   - im Lebenszeichen als `nicht_scharf`. Die Statusabfrage sagt für diese
     Kamera dann **nie „OK“**, sondern `UNBEKANNT` mit Grund. Offene
     Brunstverdachte bleiben `WARNUNG`.
3. **Freigabe ist ausdrücklich.** `modell.freigegeben` in `config.yaml`
   überträgt das Abnahmeergebnis: In der Brunst-Phase `[brunst]`. Der Eintrag
   meldet nur, er unterdrückt keine Erkennung.
4. **Ein Modell ehrlich durch Konstruktion.** Der Datensatz der Brunst-Phase
   (`edge-agent/training/stall-brunst.yaml`) enthält nur `kuh`. Ein Modell,
   das die Namen `amniotic_sac`/`calf_legs` trägt, ohne sie gelernt zu haben,
   sähe sonst wie eine scharfe Kalbeüberwachung aus.

## 2. Fachlicher Widerspruch (Widerspruchspflicht)

- **Kalbung ist der Notfall, Brunst ist planbar.** Das Besamungsfenster ist
  8–18 h breit; eine verpasste Austreibung kann Kalb und Kuh kosten. Mit
  „Brunst zuerst“ überwacht die KI in dieser Phase **keine Geburt**. Die
  Entscheidung trägt nur, wenn
  1. die bisherige menschliche Kalbeüberwachung unverändert weiterläuft, und
  2. die App das unmissverständlich zeigt. Das ist jetzt technisch
     sichergestellt (Grundsatz 2).
- **Empfehlung, die nichts kostet:** Beim Labeln der Brunst-Bilder jede
  eindeutig sichtbare Fruchtblase/Kälberfüße trotzdem markieren und die
  Geburtsbilder (`aufnahmen/kalbungen/`) aufheben. Das spart in Phase 2 einen
  ganzen Durchgang, ändert v1 aber nicht (die Klassen kommen erst mit
  `stall.yaml`).
- **Die Aufsprung-Regel ist auf Seitenansicht gebaut.** „Oben“ heißt höher
  im Bild. Bei einer Kamera senkrecht von oben überdecken sich die Boxen fast
  vollständig, und „höher im Bild“ heißt „weiter hinten“. Ob die Regel an der
  Stallwache-Position trägt, entscheidet erst der Goldstandard (Abnahme A1).
- **Non-Maximum-Suppression:** Beim Aufsprung überlappen zwei Kühe stark.
  Liegt die Überlappung über der NMS-Grenze von Ultralytics (IoU 0,7), bleibt
  nur eine Box übrig: kein Paar, kein Brunstverdacht, und die
  Kuh-Erkennung sieht trotzdem gut aus. Deshalb das eigene Abnahme-Gate Ü.

## 3. Grenzen

- Brunst nur über Aufsprung. Duldung ohne Aufsprung, Unruhe und Schwanz-
  wedeln sind nicht Teil von v1 (Brunst-Verhaltensschicht v0.1 mit
  Schwanzwinkel braucht Keypoints → Phase 2).
- Kuh-Nummern sind Tracker-Nummern, keine Ohrmarken. Namen vergibt der
  Landwirt per Telegram (`/kuh 12 Berta`, `docs/kuh-namen-spezifikation.md`).
- Ein Kalb kann als „Kuh“ erkannt werden und an einem Paar beteiligt sein
  (Kalb an der Kuh ist kein Aufsprung). Die 20-%-Höhenregel filtert das
  nicht sicher; der 24-h-Test (3b) zeigt, wie oft das passiert.

## 4. Schwellenwerte

| Wert | Größe | Herkunft |
| --- | --- | --- |
| Aufsprung IoU | ≥ 0,15 | `LogicEngine._brunst`, unverändert |
| Höhenversatz | ≥ 20 % der Boxhöhe | ebenda |
| Mindestdauer | `logik.brunst_min_dauer_s` = 4 s | Referenzwert |
| Paar stumm nach Meldung | 1 h | ebenda |
| Gate K Kuh-Recall | ≥ 90 % bei Konfidenz ≥ 0,5 (n ≥ 30) | Vorschlag; 0,5 = `new_track_thresh` |
| Gate Ü beide Kühe bei Überlappung | ≥ 80 % (n ≥ 5 Paare) | Vorschlag |

Die Gate-Werte K und Ü sind ein Vorschlag des Orchestrators. Der Betreiber
entscheidet; bis dahin gelten sie.

## 5. Konfiguration (Stall-Rechner, Brunst-Phase)

```yaml
modell:
  pfad: best_v1.pt
  klassen:
    kuh: 0
  tier_klassen: [kuh]
  freigegeben: [brunst]
```

## 6. Ablauf für den Betreiber: Silent Mode beenden, Training beginnen

Der Silent Mode endet nur auf eine Art: Ein abgenommenes Modell steht in
`modell.pfad`. Bis dahin sammelt der Agent weiter, und das ist gut so.

1. **Bestand prüfen** (Stall-Rechner):
   `python3 edge-agent/training/datensatz.py bilanz ./aufnahmen`
   (≥ 1/3 IR-Nacht, Beschluss B9). Die App zeigt die Bildzahl in der
   Statusabfrage.
2. **Ausdünnen:**
   `python3 edge-agent/training/datensatz.py ausduennen ./aufnahmen ./auswahl`.
3. **Labeln in CVAT** (app.cvat.ai, kostenlos): Label `kuh` als Rechteck.
   Jede Kuh einzeln umranden, auch eng stehende und aufspringende. Gezielt
   Bilder mit Kühen dicht beieinander aufnehmen, denn sie sind selten in
   zufälligen 120-s-Bildern und entscheiden Gate Ü. Export „Ultralytics YOLO
   Detection“.
4. **Teilen nach Stalltagen:**
   `python3 edge-agent/training/datensatz.py split ./cvat-export ./datensatz`.
5. **Colab** (`edge-agent/training/colab_training.py`, `PHASE = "brunst"`):
   trainiert YOLOv8n (COCO-vortrainiert, kennt „cow“) auf `stall-brunst.yaml`.
6. **Abnahme:** `python3 abnahme.py best_v1.pt datensatz --phase brunst`.
   Gate K und Ü automatisch, Goldstandard A1, 24-h-Test 3b und Laufzeit
   (`--nur-fps` am Stall-Rechner) von Hand.
7. **Scharfschalten:** Konfiguration aus Abschnitt 5, dann
   `ANALYSE=1 docker compose up -d --build`. Startmeldung prüfen: „Scharf:
   Brunst (Aufsprung) · NICHT scharf: Austreibung …, Kalbeverdacht …“.

## 7. Abnahmekriterien (dieser Entscheidung)

Automatisch (vor dem Merge):
1. `edge-agent/tests/test_aufloesung_umfang.py`: Brunst-Modell → Austreibung
   und Kalbeverdacht nicht scharf; COCO-Modell (Index 1/2 = bicycle/car) →
   Austreibung nicht scharf; `freigegeben` schränkt ein, macht aber nichts
   scharf, was das Modell nicht kann; Lebenszeichen meldet `nicht_scharf`.
2. `tests/stall-status.test.ts` 24–24e: mit `nicht_scharf` nie „OK“;
   Brunstverdacht bleibt `WARNUNG`; Parser verwirft Unbekanntes.
3. `edge-agent/tests/test_training.py`: Gates K und Ü, Exit-Codes, Bericht.

Am Gerät (Beweispflicht, erst mit v1):
4. Startmeldung und Tagesbericht nennen den Umfang wie oben.
5. Statusabfrage für die Stallwache: `UNBEKANNT – Austreibung …,
   Kalbeverdacht … nicht scharf`, nie `OK`.
6. Goldstandard A1 (Brunst-Spezifikation §6) im Replay: Aufsprung erkannt.
7. 24 h Live: ≤ 1 falscher Brunstverdacht.

## 8. Risiken

1. **Falsches Sicherheitsgefühl bei der Kalbung.** Gegenmittel:
   Grundsatz 2. Restrisiko: Wer nur Telegram liest und nie die
   Statusabfrage, sieht den Hinweis einmal am Tag im Tagesbericht.
2. **Aufsprung-Regel passt nicht zur Kameraposition** (Draufsicht).
   Gegenmittel: A1 entscheidet vor dem Scharfschalten.
3. **NMS schluckt die zweite Kuh.** Gegenmittel: Gate Ü; bei „verfehlt“
   mehr Überlappungs-Bilder labeln. Ein Absenken der NMS-Grenze wäre ein
   neuer Regler und braucht eine eigene Entscheidung.
4. **Wenige Aufsprung-Szenen im Datensatz.** Das Modell muss Kühe erkennen,
   nicht Aufsprünge. Für Gate Ü genügen eng stehende Kühe.
