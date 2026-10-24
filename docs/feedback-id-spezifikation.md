# Spezifikation: Feedback-IDs über Neustarts eindeutig

Härtung nach der Reifegrad-Regel. Der Fehler steckt seit der
Ein-Tipp-Feedback-Schleife (#35) im Edge-Agenten und wurde in einer
adversarialen Prüfung mit Reproduktion bestätigt. Entwurf und Übernahme:
Orchestrator (15.10.2026). **Status: umgesetzt, Abnahme am realen Agenten
offen.**

## 0. Befund

`FeedbackSchleife` vergibt die Feedback-ID (`fid`) als reinen Prozesszähler
ab 0. Der Zähler wird nirgends gesichert. Neustarts sind vorgesehen
(`Restart=always` in `edge-agent/setup.sh`, dazu Watchdog und Stromausfall).
Nach jedem Neustart beginnt die Zählung wieder bei 0:

1. **Falsche Hard Negatives.** Alarmnachrichten ohne Votum behalten ihre
   Buttons. Ein Tipp auf „❌ Fehlalarm“ unter einer *alten* Nachricht
   (`fb:0:fehlalarm`) trifft den *neuen* Alarm mit `fid` 0. Dessen Bilder
   landen als Negativbeispiele im Nachtraining, auch wenn der Alarm echt
   war. `bei_fehlalarm` erhält Typ und Episode des falschen Alarms. Für den
   Recall ist das unkritisch (`LogicEngine.fehlalarm_gemeldet` erlaubt nur
   eine frühere Neumeldung und unterdrückt nie), falsch ist es trotzdem.
   Denselben Weg kann ein Votum nehmen, das Telegram nach dem Neustart
   erneut zustellt. Der alte Prozess bestätigt den Offset erst beim nächsten
   Abruf; stirbt er vorher und ist im neuen Prozess schon ein Alarm
   registriert, trifft das Votum diesen ohne Zutun des Landwirts.
2. **Überschriebene Bilder.** Die Hard Negatives heißen `{typ}-{fid}-{i}.jpg`
   im Tagesordner und werden mit `write_bytes` ohne Existenzprüfung
   geschrieben. Ein Fehlalarm-Votum nach dem Neustart überschreibt die
   Hard Negatives desselben Tages; bei unterschiedlich langen Serien
   entstehen gemischte Serien. Mit `dashboard.archiv: false` (Standard)
   gibt es keine Cloud-Kopie, die Bilder sind verloren.

## 1. Grundsatz

1. **Jede `fid` ist über Neustarts hinweg eindeutig:**
   `fid = <Start-Token><laufende Nummer>`. Der Start-Token wird je Prozess
   einmal zufällig gezogen (8 Hex-Zeichen, 32 Bit, Modul `secrets`).
   Zufall statt Startzeit: Stallrechner ohne RTC-Batterie (Raspberry Pi,
   ausgemusterter Laptop) starten nach einem Stromausfall mit falscher Uhr,
   eine zeitbasierte ID könnte sich wiederholen.
2. **Ein Button aus einem früheren Prozess läuft ins Leere**, genau wie der
   Button eines abgelaufenen Alarms (älter als die letzten 20). Es werden
   keine Bilder gespeichert und `bei_fehlalarm` wird nicht aufgerufen.
   „❌ Fehlalarm“ antwortet „Danke – notiert (Bilder lagen nicht mehr
   vor).“, „✅ Treffer“ wie bisher „Danke!“. Der neue Alarm bleibt
   abstimmbar.
3. **Hard Negatives werden exklusiv angelegt** (`open(…, "xb")`): Eine
   vorhandene Datei wird nie überschrieben. Trifft das Schreiben doch auf
   eine vorhandene Datei, gilt es als gescheitert. Die Antwort meldet das
   mit dem vorhandenen Text „Bilder konnten NICHT gespeichert werden (Log
   prüfen)“, und die vorhandene Datei bleibt unverändert. Mit Grundsatz 1
   ist das praktisch unerreichbar, der Schutz hängt aber nicht am Zufall.

## 2. Grenzen

- **Telegram-Grenze:** `callback_data` höchstens 64 Bytes. `fb:` (3) +
  Token (8) + Nummer + `:fehlalarm` (10) ergibt 21 Bytes plus die Ziffern
  der Nummer. Überschritten wäre die Grenze erst bei einer 44-stelligen
  Nummer.
- **Zeichensatz:** Die `fid` besteht nur aus Hex-Zeichen und Ziffern. Sie
  enthält nie `:` (Trenner im `callback_data`) und nie `/` (Dateiname).
- **Unverändert:** Antworttexte, Zähler im Tagesbericht (ein Votum auf einen
  alten Button zählt einmal, wie bei abgelaufenen Alarmen; Doppel-Tipp-Regel
  in `versand-entkopplung-spezifikation.md` §7), Semantik von
  `bei_fehlalarm`, Austreibungs-Takt, alle Schwellenwerte, `MAX_OFFEN = 20`,
  Ablage im Tagesordner nach dem Muster `{typ}-{fid}-{i}.jpg`.
- **Bestehende Dateien bleiben unberührt:** keine Migration, keine
  Umbenennung. Alte Namen (`kalbeverdacht-0-1.jpg`) und neue
  (`kalbeverdacht-3f9a0c1e0-1.jpg`) liegen nebeneinander. Kein Code wertet
  die Dateinamen aus (geprüft: `edge-agent/`, Webapp, Skills).
- **Nicht Teil dieser Änderung:** Buttons alter Nachrichten bleiben sichtbar.
  Sie werden wie bisher nur beim ersten gültigen Votum entfernt.

## 3. Konfiguration

Keine neuen Schalter. Fest im Code: Start-Token mit 8 Hex-Zeichen.

## 4. Abnahmekriterien

Automatisiert (`edge-agent/tests/test_feedback.py`):

1. **Neustart:** Eine zweite `FeedbackSchleife` auf demselben Ordner vergibt
   andere IDs als die erste.
2. **Alter Button nach dem Neustart** („❌ Fehlalarm“ auf eine alte Nachricht
   ohne Votum) trifft keinen neuen Eintrag. Es werden keine Bilder
   geschrieben, `bei_fehlalarm` wird nicht aufgerufen, der neue Alarm
   bleibt abstimmbar, die Antwort lautet „Bilder lagen nicht mehr vor“.
3. **Kein Überschreiben:** Ein Fehlalarm-Votum nach dem Neustart lässt die
   Hard Negatives des Vorgänger-Prozesses vom selben Tag inhaltsgleich
   stehen, die neuen kommen hinzu.
4. **Exklusives Anlegen:** Eine vorhandene Datei mit dem Zielnamen bleibt
   unverändert, es gibt keine Erfolgsmeldung.
5. `callback_data` ist höchstens 64 Bytes lang, auch nach sehr vielen
   Alarmen (laufende Nummer 10¹⁵).
6. **Gegenprobe:** Die Kriterien 1–4 schlagen am alten Stand fehl.
7. `python3 edge-agent/tests/alle_tests.py` ist grün.

Am realen Agenten (Beweispflicht, offen):

8. Alarm auslösen (Testbild), die Nachricht **nicht** bewerten. Agent neu
   starten (`sudo systemctl restart stallblick-agent`). Neuen Alarm
   auslösen. Auf „❌ Fehlalarm“ der **alten** Nachricht tippen: Antwort
   „Bilder lagen nicht mehr vor“, im Tagesordner
   (`aufnahmen/fehlalarme/JJJJ-MM-TT/`) keine neue Datei.
9. Danach „❌ Fehlalarm“ der **neuen** Nachricht: neue Dateien mit anderem
   Präfix, vorhandene Dateien unverändert (`ls -l --time-style=full-iso`
   vorher und nachher vergleichen).

## 5. Risiken

1. **Gleicher Start-Token in zwei Prozessen:** Die Wahrscheinlichkeit liegt
   bei 1 : 2³² je Prozesspaar mit noch offenen Buttons. Selbst dann wird
   nichts überschrieben (Grundsatz 3); möglich wäre nur ein Fehltreffer
   eines alten Buttons.
2. **Erneut zugestellte Voten** (Offset vom alten Prozess nicht mehr
   bestätigt) zählen im Tagesbericht ein zweites Mal, weil `_abgestimmt`
   nach dem Neustart leer beginnt (`versand-entkopplung-spezifikation.md`
   §7.2). Bilder und `bei_fehlalarm` betrifft das nicht; die Zähler-Semantik
   bleibt bewusst unverändert.
3. **Längere Dateinamen** (+8 Zeichen): unkritisch.

## 6. Abnahme `qa-waechter` (15.10.2026, Delta ecde966..f7b20b4): FREIGABE

- Statik und Logiktests grün (`py_compile`, `alle_tests.py`, Feedback
  26/26).
- Spezifikationstreue grün. Der Token hat an 20 000 Ziehungen immer 8
  Zeichen aus `[0-9a-f]`. Die Byte-Rechnung der 64-Byte-Grenze stimmt
  (43 Ziffern = 64 Bytes, 44 Ziffern = 65 Bytes).
- Eigene Reproduktion grün (38/38 Checks): synchron und über den
  `Versandkanal`. Alte Buttons im neuen und im Vorversions-Format laufen ins
  Leere. Der Altbestand bleibt byte- und mtime-gleich, auch Dateien im
  alten Namensschema.
- Gegenprobe am alten Stand: 9 der neuen Checks rot (alle „Neustart“- und
  „Vorhandene Datei“-Checks). Der 64-Byte-Check ist eine reine Grenzprüfung
  und bleibt dort grün.

Befunde ohne Handlungsbedarf:

- **Kollision bei Bild i > 0** (setzt eine Token-Kollision voraus): Die
  Antwort lautet „NICHT gespeichert“, obwohl ein Teil der Serie auf der
  Platte liegt. Das ist pessimistisch, nie zu optimistisch. Das Archiv wird
  nicht befüllt.
- **Tagesgrenze im Test:** Läuft „Exklusives Anlegen“ genau über
  Mitternacht (Fenster im Mikrosekundenbereich), kann der Check fälschlich
  rot werden. Kein Produktfehler.
- Ungenaue Doku (Grundsatz 2 und Skill nannten nur die ❌-Antwort und
  „nie“ statt des Restrisikos): korrigiert.

**Folgepunkt außerhalb dieses Deltas:** Im Silent Mode heißen die
Trainingsbilder `%Y%m%d-%H%M%S.jpg` (`edge-agent/main.py`, Silent-Mode-Zweig
der Hauptschleife), und `cv2.imwrite` überschreibt ohne Prüfung. Startet ein
Raspberry Pi mit fake-hwclock nach einem Stromausfall mit zurückgestellter
Uhr, entstehen bis zur NTP-Synchronisierung wieder Namen der letzten Stunde
vor dem Ausfall. Vorhandene Trainingsbilder werden dann still
überschrieben. Eigener Schritt, gleiches Muster (eindeutiger Name oder
exklusives Anlegen).

## 7. Zusammenführung mit #77 (Doppel-Tipp zählt einmal)

#77 wurde parallel gemergt und führt `_abgestimmt` ein
(`versand-entkopplung-spezifikation.md` §7). Beim Zusammenführen:

- `registriere()` behält `_abgestimmt.pop(fid)` (dortige Grenze 6). Mit
  eindeutigen IDs greift das nur noch bei einer Token-Kollision; der
  Kommentar sagt das jetzt.
- Die Tests 28–30 und 33 aus #77 setzten numerische IDs (`"0"`, `"1"`,
  `"2"`) voraus. Sie lesen die ID jetzt aus dem Markup. Test 32 bildet die
  Alt-ID mit dem eigenen Token nach (Kollisionsfall), damit der Schutz in
  `registriere()` weiter geprüft wird.
- §7.4 Risiko 1 der Versand-Spezifikation (Kollision der IDs nach Neustart)
  ist damit behoben und dort vermerkt.
