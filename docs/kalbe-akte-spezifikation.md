# Spezifikation: Automatische Kalbe-Akte

Implementierungsreife Regeln für Roadmap P3 („nach Abschluss einer Kalbung
EINE Zusammenfassung mit Phasen-Zeitstempeln + Belegbildern, kopierbar fürs
Stallbuch"; [`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md) Abschnitt 4b —
kein Wettbewerber dokumentiert Geburten automatisch, alle alarmieren nur
live). Entwurf: Orchestrator nach `ki-wache`-Mandat (Fachagent zweimal durch
API-Überlastung unterbrochen; Regeln folgen seinen etablierten Mustern aus
Festliege- und Brunst-Fusion-Spezifikation). **Status: spezifiziert; Teil-Akte
umsetzbar mit erstem Modell, Voll-Akte („Kalb steht") mit 2. Training.**

## 0. Grundsatz

Die Akte ist **Dokumentation und Entwarnung, kein Alarm**: Sie ersetzt keinen
der bestehenden Alarme, wird **still** zugestellt (`disable_notification` —
gute Nachrichten wecken nicht) und behauptet nichts über die Modell-Evidenz
hinaus: „abgeschlossen" heißt „30 min keine Geburtsanzeichen mehr", niemals
„erfolgreich" — bis eine Kalb-Klasse das Stehen wirklich sieht.

## 1. Episoden-Assemblierung — im Edge-Agenten

Die Akte lebt im **Edge-Agenten**, nicht serverseitig: Nur er hat die Frames
(Belegbilder), den Episoden-Zustand (`austreibung_start`,
`austreibung_zuletzt`, `eskaliert` existieren bereits) und die Datenhoheit
(Bilder verlassen den Hof nur als Telegram-Zustellung an den Landwirt selbst).
Bauform: eigenständige, offline testbare Klasse `KalbeAkte` mit injizierbarem
`jetzt` (Muster `TotmannWaechter`).

Phasen-Quellen (alles vorhandene Signale):

| Phase | Quelle | Regel |
| --- | --- | --- |
| **Unruhe-Beginn** | erster `kalbeverdacht`-Alarm derselben Kuh-ID im Rückblick von **12 h** vor Austreibungs-Start (Wehen-Vorlauf typisch 2–12 h) | fehlt er → Akte vermerkt „Unruhephase nicht erfasst" |
| **Austreibung ab** | `austreibung_start` (erste Fruchtblase/Füße > 0.80) | existiert |
| **Letzte Erkennung** | `austreibung_zuletzt` | existiert |
| **Abgeschlossen** | Episodenende (30 min ohne Erkennung, existiert) + **10 min Nachlauf** für das Abschluss-Belegbild | Auslöser der Akte |
| **Eskalation** | `eskaliert`-Flag | Vermerk in „Besonderheiten" |
| **Kalb sichtbar / Kalb steht** | erst mit neuen Klassen (Abschnitt 2) | Voll-Akte |

## 2. Ehrliche Erkennungsgrenzen

„Kalb sichtbar" und „Kalb steht" sind mit den heutigen Klassen
(`kuh`/`amniotic_sac`/`calf_legs`) **nicht erkennbar**. Entscheidung
(konsistent zum `kuh_seitenlage`-Vorgehen der Festliege-Spezifikation):
**zwei neue Klassen `kalb_liegend` und `kalb_stehend`** im 2. Training —
zwei Klassen statt „`kalb` + Geometrie", weil die Kalb-Größe jede
Aspekt-Heuristik unzuverlässig macht und das **Stehen** die eigentliche
Entwarnungs-Information ist (Kolostrum-Fenster).

- **Teil-Akte (ab erstem Modell, sofort):** Unruhe → Austreibung → letzte
  Erkennung → Abschluss + Eskalationsvermerk. Bereits stallbuchtauglich.
- **Voll-Akte (ab 2. Training):** zusätzlich „Kalb sichtbar seit HH:MM"
  (`kalb_liegend` ODER `kalb_stehend` ≥ 0.80) und als Abschluss-Trigger
  „**Kalb steht seit HH:MM**": `kalb_stehend` ≥ **0.80** in ≥ **70 %** der
  Frames eines **5-min-Fensters** — die erste Entwarnungs-Nachricht der
  Branche, statt des passiven 30-min-Timeouts.

## 3. Belegbilder

**3 Bilder, unannotiert** (die Akte ist Stallbuch-Dokument; eingezeichnete
Boxen gehören in die Alarm-Alben, und unannotierte Bilder bleiben als
Trainingsmaterial wiederverwendbar):

1. Austreibungs-Start (Frame des ersten Overrides),
2. letzte `amniotic_sac`/`calf_legs`-Erkennung (Geburtsmoment-Nähe),
3. Abschluss (Episodenende; in der Voll-Akte der erste stabile
   `kalb_stehend`-Frame).

Lokale Ablage: `./aufnahmen/kalbungen/JJJJ-MM-TT-kuh-N/` (Datenhoheit;
das Telegram-Album ist nur die Zustellung, nicht der Speicherort).

## 4. Auslöse- und Abschluss-Logik

- Genau **eine** Akte pro Austreibungs-Episode (Flag analog `eskaliert`);
  Episoden-Reset (30 min) startet die nächste Kalbung frisch.
- **Auslöser:** Episodenende + 10 min Nachlauf; in der Voll-Akte alternativ
  das bestätigte `kalb_stehend`-Fenster (was zuerst eintritt).
- **Eskalations-Episoden bekommen die Akte erst recht** — mit Vermerk
  „⚠️ Eskalations-Alarm war ausgelöst (kein Fortschritt über 60 min) —
  Verlauf und Nachgeburt kontrollieren."
- Austreibung ohne vorherigen Kalbeverdacht → Akte trotzdem (Vermerk).
  Kalbeverdacht ohne Austreibung → **keine** Akte (unbestätigter Verdacht
  ist kein dokumentationswürdiges Ereignis).
- **Zustellung still** (`disable_notification: true`), zusätzlich Eintrag im
  nächsten Tagesbericht („1 Kalbe-Akte erstellt").

## 5. Stallbuch-Format

Telegram-Nachricht (kopierbar, Album mit den 3 Belegbildern):

```
📔 Kalbe-Akte – Oberer Stollenhof
Datum: 17.07.2026 · Kamera: stallwache · Kuh #42
Unruhe erkannt:    01:12 Uhr (Schwanzwinkel-Fenster)
Austreibung ab:    03:47 Uhr (Fruchtblase, Konfidenz 91 %)
Letzte Erkennung:  04:19 Uhr
Abgeschlossen:     04:49 Uhr (30 min ohne Geburtsanzeichen)
Dauer Austreibung: 32 min · Gesamtverlauf ab Unruhe: 3 h 37 min
Besonderheiten:    keine (kein Eskalations-Alarm)
Belegbilder:       aufnahmen/kalbungen/2026-07-17-kuh-42/
```

Voll-Akte ergänzt: „Kalb sichtbar: 04:21 Uhr · **Kalb steht seit 04:32 Uhr**".

**Dashboard:** als `typ: "info"` mit `kuhId` — bewusst **kein** neuer
Ereignistyp: Die Akte ist Systemdokumentation, kein Alarm; das vermeidet die
Whitelist-Erweiterung der Ingest-Route (anders als beim Festliege-Alarm, der
als echter Alarmtyp `festliege` die Erweiterung braucht).

## 6. Konfig-Schema und Verifikation

```yaml
kalbe_akte:
  aktiv: true                 # Default AN: reine Dokumentation, weckt nicht,
                              #   null Fehlalarm-Risiko (nur nach echter Austreibungs-Episode)
  unruhe_rueckblick_h: 12     # Kalbeverdacht-Zuordnung vor Austreibungs-Start
  abschluss_nachlauf_min: 10  # Wartezeit nach Episodenende bis zur Zustellung
  belegbilder: 3
  ordner: ./aufnahmen/kalbungen
  # Voll-Akte, erst wenn best.pt kalb_liegend/kalb_stehend enthaelt:
  kalb_klassen: false
  kalb_steht_konfidenz: 0.80
  kalb_steht_fenster_min: 5
  kalb_steht_anteil: 0.70
```

Dazu in `modell.klassen` (2. Training): `kalb_liegend: 4`, `kalb_stehend: 5`.

**Offline (pytest, injiziertes `jetzt`):** (a) Kalbeverdacht 02:00 +
Austreibung 03:00–04:00 → genau 1 Akte, 3 Phasen, korrekte Dauern;
(b) Austreibung ohne Kalbeverdacht → Akte mit Vermerk; (c) Eskalations-
Episode → Besonderheiten-Vermerk; (d) zweite Episode nach Reset → zweite
Akte; (e) Kalbeverdacht ohne Austreibung → keine Akte; (f) Voll-Akte:
`kalb_stehend`-Fenster beendet vor dem Timeout.

**Praxis-Abnahme:** erste reale Kalbung → Akte vollständig, Zeitstempel
gegen Videoaufzeichnung ± 2 min, Belegbilder zeigen die richtigen Momente.

## Offene Risiken

1. **Episodenende ≠ Geburtserfolg:** 30 min ohne Anzeichen können auch
   Totgeburt oder verdeckte Lage bedeuten — die Teil-Akte formuliert deshalb
   neutral („abgeschlossen"), nie „erfolgreich"; erst `kalb_stehend` erlaubt
   die echte Entwarnung.
2. **Unruhe-Zuordnung über die Kuh-ID** bricht bei ByteTrack-ID-Wechseln —
   die Akte nimmt dann den jüngsten Kalbeverdacht der Bucht im
   Rückblick-Fenster und vermerkt „Zuordnung unsicher (ID-Wechsel)".
3. **Überlappende Kalbungen in derselben Bucht** vermischen Episoden
   (Austreibungs-Zustand ist heute buchtweit, nicht kuhweit) — selten, wird
   vermerkt („mehrere Tiere in Austreibungsphase — Akte buchtbasiert");
   buchtbasierte Ehrlichkeit wie im Rest des Systems.
