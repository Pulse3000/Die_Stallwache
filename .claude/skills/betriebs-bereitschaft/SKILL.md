---
name: betriebs-bereitschaft
description: Beantwortet in einem Blick, welche Bausteine der Stallwache scharf sind und was der eine nächste Schritt ist — Service Worker, Edge-Agent, Push, Assistent, Tuya-Geräte, Kameras, Bridge. Nutzen bei "läuft das System?", "was fehlt noch?", "ist die Nachtwache scharf?", nach jedem Deploy und vor jeder Übergabe.
---

# Bereitschaft: Ist die Nachtwache wirklich scharf?

Stallblick besteht aus Bausteinen, die **einzeln schlafen können**, ohne dass
die App etwas davon zeigt. Ohne Firebase läuft alles weiter — nur meldet sich
nichts mehr. Ohne Bridge kommt kein Livebild, aber die Alarme funktionieren.
Ohne Modell erkennt der Agent nichts, sendet aber Lebenszeichen.

Das ist im Betrieb richtig (ein fehlender Baustein darf nicht das Ganze
mitreißen) und in der Kommunikation gefährlich: Der Landwirt sieht eine
funktionierende App und schließt daraus auf eine funktionierende Nachtwache.
Dieser Skill schließt genau diese Lücke — er sagt, **was gerade wirklich
wacht**, und benennt den einen nächsten Schritt.

## Ausführen

```bash
bash .claude/skills/betriebs-bereitschaft/bereitschaft.sh [BASIS-URL] [COOKIE-DATEI]
```

Ohne Argumente wird die Produktion geprüft. Bei aktivem Passwortschutz vorher
anmelden, sonst sind nur die offenen Pfade sichtbar:

```bash
curl -c kekse -X POST "$B/api/login" \
  -H 'content-type: application/json' -d '{"passwort":"…"}'
bash .claude/skills/betriebs-bereitschaft/bereitschaft.sh "$B" kekse
```

Das Skript ist rein lesend, braucht keine Secrets und verändert nichts.

## Zustände lesen

| Zustand | Bedeutung | Handlung |
| --- | --- | --- |
| **SCHARF** | in Betrieb | nichts |
| **SCHLAEFT** | gebaut, aber nicht konfiguriert | zugehörigen Scharfschalt-Skill fahren |
| **HALB** | teilweise konfiguriert | fehlendes Stück ergänzen |
| **DEFEKT** | konfiguriert, aber funktionsunfähig | **Vorrang vor allem anderen** — hier lügt das System |
| **FEHLT** | Route im Deployment nicht vorhanden | veralteter Stand → deployen |
| **UNKLAR** | von außen nicht prüfbar | meist fehlende Anmeldung |

**DEFEKT ist schlimmer als SCHLAEFT.** Ein schlafender Baustein ist ehrlich —
die App sagt „nicht eingerichtet". Ein defekter Baustein sieht konfiguriert
aus und tut nichts; das ist genau der stille Ausfall aus Vision-Prinzip 6.

## Die Rangfolge des nächsten Schritts

Nicht alles ist gleich dringend. Wenn mehrere Bausteine schlafen, gilt diese
Reihenfolge — sie folgt der Frage „was nützt dem Landwirt heute Nacht am
meisten?":

1. **Service Worker DEFEKT** → sofort. Ohne ihn verliert die PWA Offline
   *und* Push, und zwar lautlos. Prüfen, ob `/sw.js` vom Passwortschutz
   eingefangen wurde (`middleware.ts`).
2. **Edge-Agent SCHLAEFT** → Skill `modell-training` bzw. Agent starten. Ohne
   ihn gibt es überhaupt nichts zu melden; alle anderen Bausteine sind dann
   Infrastruktur ohne Inhalt.
3. **Push SCHLAEFT** → Skill `push-live-schalten`. Der Agent meldet, aber
   niemand wird geweckt. Das ist der Baustein, der aus einem Dashboard eine
   Nachtwache macht.
4. **Kameras/Tuya DEFEKT** → Skill `tuya-diagnose`. Betrifft das Livebild,
   nicht den Alarmweg — deshalb nach Push.
5. **Bridge SCHLAEFT** → Skill `stallwache-live-schalten`. Die Hauptkamera
   ist die für den Abkalbebereich; wichtig, aber der Agent kann übergangsweise
   über die Cloud-Quelle laufen.
6. **Assistent LOKAL** → Skill `gcp-anbindung`, niedrigste Priorität. Die
   Funktion ist ohne KI voll nutzbar; im Funkloch ist die lokale Auswertung
   sogar die einzige, die antwortet.

## Was der Check nicht beantwortet

Er prüft die **Serverseite**. Ob der Alarm tatsächlich auf dem gesperrten
Bildschirm ankommt, ob die App installiert ist, ob „Nicht stören" ihn
verschluckt — all das steht in `push-live-schalten` (Schritt 6) und
`pwa-abnahme` (Teil B) und lässt sich nur am echten Gerät klären.

Ein Bericht, der nur diesen Check zitiert, darf deshalb nie „die Nachtwache
läuft" behaupten. Er darf sagen: „Serverseitig ist alles scharf; die
Zustellung am Gerät ist zuletzt am <Datum> bewiesen worden."

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Check ausführen und deuten | Orchestrator (dieser Skill) |
| Nächsten Schritt benennen (genau einen) | Orchestrator |
| Env-Variablen setzen, Geräte-Prüfung | Betreiber |
