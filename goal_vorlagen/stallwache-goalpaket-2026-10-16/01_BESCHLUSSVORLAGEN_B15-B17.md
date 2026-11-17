# Beschlussvorlagen B15–B17 — zur Entscheidung durch Landwirt + Dirigent

Stand 16.10.2026. Erst entscheiden, dann die Goals starten („Entscheidung vor Code").
Eintrag in `ENTSCHEIDUNGEN.md` nur durch den Dirigenten. Abweichende Entscheidung:
Default in `kuhwatch/erkennung/vertrag.py` (Klasse `Konfig`) anpassen — die Tests sind dort,
wo der Wert Beschlusssache ist, wertneutral.

---

## B15 · Ein Name für den Rücken-Keypoint

**Vorlage:** Überall `spine_end` — Label-Vertrag, CVAT, Datensatz-YAML, Edge, Telemetrie, Cockpit.
`back_mid` entfällt. Definition für Labeler: **Widerrist** (höchster Punkt über den Schulterblättern).
Prüfung am Pilot: sichtbar in ≥ 9 von 10 Bildern, sonst Definition vor dem Großlabeln anpassen.

**Begründung:** Der Code liest `back_mid`, der Label-Vertrag definiert `spine_end`. Ein Modell nach
Label-Vertrag liefert nie `back_mid` → Winkel immer `None` → Kalbeverdacht verstummt still.
Die Umbenennung kostet jetzt fast nichts: 0 Labels, PR #70 nicht deployt, keine Telemetrie in
Firestore. Nach 3.000 Labels oder Wochen an Telemetrie wird sie teuer. Die Ruhelage wird je Tier
kalibriert — der gewählte Punkt verschiebt nur den Rohwinkel-Offset; `RUHELAGE_FALLBACK` (94°)
wird nach dem Pilot neu bestimmt.

**Alternative:** intern `back_mid`, Abbildung nur im Adapter. Nachteil: zwei Namen für einen Punkt.

**Betroffen:** Wächter, Trainer, Bauleiter (Cockpit, Telemetrie), Chronist (Skills
`ki-wache-kern`, `training-pipeline`; LELA-Systemprompt §5.1 nennt `back_mid`).

## B16 · Messgröße und Anteil des Kalbeverdachts

**Vorlage:** Messgröße ist der **kalibrierte Ausschlag** (Rohwinkel − Ruhelage je Tier, README §2),
Schwelle 45° (im Kaltstart abgesenkt, nie angehoben). Die Skill-Formel „Rohwinkel per atan2 > 45°"
wird gestrichen. Dominanz-Anteil ist Konfigwert: **vorläufig 0,60**, Wach-Modus 0,30. Endgültig
erst nach dem Abnahme-Gate auf Realdaten (Geburts-Clips + 24 h ereignisloses Material).

**Begründung:**
- Die Skill-Formel ergibt für den hängenden Schwanz 90° (nachgerechnet) — die Regel wäre im
  Ruhezustand dauerhaft erfüllt. Kohärent ist nur die Code-Definition.
- 0,20 (Skill) und 0,60 (Code) gehören zu verschiedenen Messgrößen und sind nicht vergleichbar.
  Keiner der Werte ist an Realdaten belegt.
- Der Recall-Vertrag hängt nicht am Anteil: Die Austreibung ist schwellen- und kalibrierungsfrei.
  Deshalb startet der Kalbeverdacht auf der ruhigen Seite und wird mit Beleg abgesenkt —
  die B11-Kurve zeichnet den echten Verlauf bei der ersten aufgenommenen Geburt auf.

**Zielkonflikt Recall ↔ Ruhe → Entscheidung des Landwirts.**

**Betroffen:** Wächter (Konfig), Bauleiter (B11-Schwellenlinie = Konfigwert statt fest 20 %),
Chronist (`ki-wache-kern`, `stallblick-app-konventionen`).

## B17 · Ereignis-Schema: `typ: "eskalation"`

**Vorlage:** Das Schema erhält `typ: "eskalation"`. Ingest nimmt ihn an (201), das Dashboard hebt
ihn hervor (B3).

**Begründung:** B3 verlangt die prominente Erklärung der Eskalation. Ohne eigenen Typ müsste das
Dashboard Nachrichtentext parsen. Bis zur Umsetzung reist die Eskalation als `austreibung` mit
Präfix „ESKALATION" (V7, per Konfig umschaltbar) — kein Bruch auf beiden Seiten.

**Abnahme:** Wächter + Bauleiter (Schema ist Vertrag).

---

## Fachlicher Widerspruch (Textfrage, Landwirt entscheidet)

Der Codestand sendet bei der Fruchtblase „Sofort in den Stall." Störung im Stadium II kann den
Geburtsverlauf hemmen (Stress hemmt Oxytocin). Die Referenz nutzt den neutralen LELA-Standardtext
„SOFORT-ALARM: Fruchtblase bei Kuh #ID erkannt!" und gibt erst bei der Eskalation eine
Handlungsanweisung („Geburt kontrollieren").

## Roadmap

Nach Beschluss: B15–B17 in `docs/roadmap.md` (Die_Stallwache) unter „Entschieden" vermerken.
