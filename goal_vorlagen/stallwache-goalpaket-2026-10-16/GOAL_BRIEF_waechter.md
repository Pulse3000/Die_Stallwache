# AUFTRAG an Wächter — Erkennungsvertrag v1 in kuhwatch

**Ziel:** Die Edge-Erkennung in kuhwatch erfüllt `docs/erkennungsvertrag.md`;
Vertragstests und Integrationstests I0–I6 sind grün.

**Kontext (zuerst lesen):** `docs/erkennungsvertrag.md` · `erkennung/` (Referenz, besteht alle
Vertragstests) · `tests/test_erkennungsvertrag.py` · `tests/test_vertrag_konsistenz.py` ·
`training/` · Skill `ki-wache-kern` · `ENTSCHEIDUNGEN.md` (B1–B17) · Frame-Schleife in kuhwatch ·
falls vorhanden `Die_Stallwache/funktionen/` (`wache.py`, `pipeline.py`, `kalibrierung.py`)

**Vorgehen (agentic build loop):** 1. Plan-Modus → Freigabe durch den Betreiber.
2. Goal-Lauf gegen die Tests. 3. Diff-Review durch Betreiber + qa-waechter. 4. Grenzen in `CLAUDE.md`.

## Plan-Fragen (mit Dateipfaden und Belegen beantworten, keine Annahmen)

1. Wo läuft die Frame-Schleife? Welches Ausgabeformat liefert das Modell (Tensor-Layout, Quelle der Klassennamen)?
2. Ist die Alarmlogik (`wache.py`/`pipeline.py`/`kalibrierung.py`) in kuhwatch vorhanden und eingebunden? Wenn nein: Vorschlag zur Anbindung von `erkennung/`. **Kein Code wird ohne Freigabe zwischen Repos verschoben.**
3. Reale Frame-Rate je Kamera im Tuya-Pfad (B14) — gemessen, nicht angenommen.
4. Was bewirkt `SILENT_MODE=1` heute genau (Inferenz ja/nein, Versand ja/nein)?
5. Wo und wie werden Ereignisse versendet (Telegram, `POST /api/events`), wie wird bei Fehlern gepuffert?
6. Modulstruktur: Ort von `erkennung/`, Ort des Adapters Modellausgabe → `Frame`, ersetzte Stellen, Ort der Integrationstests.

## Definition of Done

- [ ] `pytest -q` gesamt grün (Vertrags-, Konsistenz- und Bestandstests)
- [ ] I0–I6 als Tests gegen den integrierten Pfad vorhanden und grün
- [ ] Werte aus B15–B17 in der Konfig; wo ein Beschluss fehlt: Default + Vermerk „B-Nr. offen" im Prüfbericht
- [ ] Kein Schwellenwert ohne B-Nr. geändert; kein Video-/Frame-Upload eingeführt (B7)
- [ ] `docs/erkennungsvertrag.md` Abschnitt „Umsetzung" gefüllt; 1–3 Zeilen „Grenzen dieser Session" in `CLAUDE.md`
- [ ] PR offen mit Prüfbericht (je DoD-Punkt der Beleg: Testname bzw. Ausgabe); Merge erst nach qa-waechter

## Verbote

- Vertragstests ändern — einzige Ausnahme: die Import-Zeile laut freigegebenem Plan
- Schwellen, Cooldowns oder Ereignis-Schema ohne Beschluss-Nr. ändern; `ENTSCHEIDUNGEN.md` bearbeiten
- Austreibung oder Eskalation hinter Sperre, Fenster oder Kuh-Erkennung legen
- neue Abhängigkeiten; Refactoring außerhalb der im Plan genannten Dateien

**Iterationsgrenze:** Derselbe Test drei Läufe in Folge rot → anhalten und die Spezifikation melden.
Nicht den Test anpassen.

**Rückgabe:** PR-Link, Prüfbericht, Liste offener Punkte.

## Nicht in diesem Auftrag (Folgeaufträge)

- Wächter #2: `info`-Ereignisse für Tempguard (warn/pause/entwarnung), Kamera offline/online,
  Modus beim Start, Tagesbilanz 1×/Tag (B12) → füllt Tagesreport-Punkt 3.
- Wächter #3: 4-Frame-Serie je Alarm (B1) über Ringpuffer; Brunst-Aufsprung (B4) zunächst im
  Schattenbetrieb mit dem generischen Modell (nur protokollieren, keine Alarme).
