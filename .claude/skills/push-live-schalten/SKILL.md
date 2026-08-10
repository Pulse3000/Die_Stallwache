---
name: push-live-schalten
description: Go-Live der Push-Benachrichtigungen (Firebase Cloud Messaging) — Firebase-Projekt und Service Account eintragen, Anmeldung am Gerät, Probealarm, Zustellung bei gesperrtem Bildschirm verifizieren. Nutzen bei "Push aktivieren", "Firebase eingerichtet", "Alarme aufs Handy", "Benachrichtigungen kommen nicht an" oder wenn die Einstellungsseite "Push ist noch nicht eingerichtet" zeigt.
---

# Push live schalten (FCM → Sperrbildschirm)

Die gesamte Push-Kette ist gebaut (`lib/push.ts`, `public/sw.js`,
`components/PushSchalter.tsx`) und **degradiert bewusst still**: Ohne
Konfiguration bleibt die App voll nutzbar, meldet sich aber nicht von selbst.
Genau das ist die gefährlichste Halbwahrheit im ganzen Produkt — der Landwirt
glaubt, er sei gewarnt.

Diese Prozedur macht die Kette scharf und **beweist sie am Gerät**.

## Was am Ende bewiesen sein muss

Nicht „die Variablen sind gesetzt", sondern: **Ein Alarm erreicht das Handy
mit gesperrtem Bildschirm.** Alles darunter ist kein Go-Live.

## Voraussetzung (vom Betreiber, Firebase-Konsole)

1. Firebase-Projekt anlegen (oder vorhandenes GCP-Projekt nutzen — dann ist
   die Projekt-ID dieselbe).
2. **Web-App** im Projekt registrieren → liefert `apiKey`,
   `messagingSenderId`, `appId`.
3. **Cloud Messaging → Web Push certificates → Schlüsselpaar erzeugen** →
   liefert den VAPID-Schlüssel.
4. **Projekteinstellungen → Dienstkonten → neuen privaten Schlüssel
   generieren** → JSON-Datei. Rolle: FCM-Versand
   (`roles/firebasemessaging.admin` oder
   `cloudmessaging.messages.create`).

## Schritt 1 — Env-Variablen in Vercel setzen

Alle serverseitig, Environment **Production** (und Preview, wenn dort
getestet werden soll):

| Variable | Quelle |
| --- | --- |
| `GCP_SERVICE_ACCOUNT_JSON` | JSON aus Schritt 4 — als Text **oder** Base64 (einzeilig, in Vercel angenehmer: `base64 -w0 schluessel.json`) |
| `FIREBASE_API_KEY` | Web-App-Konfiguration |
| `FIREBASE_MESSAGING_SENDER_ID` | Web-App-Konfiguration |
| `FIREBASE_APP_ID` | Web-App-Konfiguration |
| `FIREBASE_VAPID_KEY` | Web-Push-Zertifikat |
| `FIREBASE_PROJECT_ID` | nur nötig, wenn abweichend von `GCP_PROJECT_ID` |
| `PUSH_MAX_ALTER_MINUTEN` | optional, Default 30 (siehe Schritt 5) |

Danach **Redeploy** — Env-Variablen greifen erst mit dem nächsten Deployment.

## Schritt 2 — Serverseite bestätigen

```
GET /api/push/konfig
```

Erwartet: `{"aktiv":true,"versandBereit":true,"konfig":{…}}`

- `versandBereit:false` → Service Account fehlt oder ist ungültig
  (`GCP_SERVICE_ACCOUNT_JSON`).
- `konfig:null` → mindestens eine der vier Web-App-Variablen fehlt.
- Die Route nennt in der Einstellungsseite den fehlenden Baustein im
  Klartext — dort nachsehen statt raten.

## Schritt 3 — Gerät anmelden

Einstellungen → **Alarme einschalten**. Die Fallstricke der Reihe nach:

- **iOS**: Web-Push gibt es ausschließlich in der **installierten** PWA.
  Safari → Teilen → *Zum Home-Bildschirm* → App von dort öffnen. Im Tab
  bleibt der Knopf mit Hinweis stehen, das ist kein Fehler.
- **Android/Chrome**: funktioniert im Tab, aber die installierte PWA ist
  zuverlässiger (Hintergrundzustellung).
- Berechtigung abgelehnt? Der Browser fragt **nicht erneut**. Seiten-
  Einstellungen → Benachrichtigungen → zurücksetzen.
- Erfolg ist der grüne Punkt plus „Alarme auf diesem Gerät".

## Schritt 4 — Probealarm (der eigentliche Test)

Einstellungen → **Probealarm senden** (oder `POST /api/push/test`).

Prüfen — und zwar am Gerät, nicht in der Antwort:

1. Meldung erscheint bei **gesperrtem Bildschirm**.
2. Tippen öffnet die App auf `/alarme`.
3. Die Aktion **„Gesehen"** in der Meldung quittiert den Alarm.
4. Antwort meldet `zugestellt ≥ 1`. Steht dort `entfernt ≥ 1`, war das
   Token tot und wurde ausgetragen — Schritt 3 wiederholen.

Der Probealarm wird **nicht** gespeichert und nicht nach Pub/Sub gespiegelt;
er hinterlässt im Aktivitätsprotokoll bewusst keine Spur.

## Schritt 5 — Dringlichkeit und Nachlieferung verstehen

Zwei eingebaute Verhaltensweisen, die der Betreiber kennen muss, bevor er
sich wundert:

- **Austreibung** wird als dringender Alarm zugestellt: schließt sich nicht
  von selbst (`requireInteraction`), stärkeres Vibrationsmuster, hohe
  Urgency. Kalbeverdacht und Brunstverdacht kommen als normale Meldung.
  Das ist Absicht — wenn alles dringend ist, ist nichts dringend.
- **Nachgelieferte Ereignisse wecken nicht.** Kommt der Edge-Agent nach
  einem Funkloch zurück und liefert seinen Puffer nach, wandern Ereignisse
  älter als `PUSH_MAX_ALTER_MINUTEN` (Default 30) still ins Protokoll. Sie
  sind vollständig da — sie klingeln nur nicht vierzigmal. Wer das anders
  will, setzt den Wert hoch; wer nachts nie geweckt werden will, niedrig.

## Schritt 6 — Nachtprobe (einmalig, unbedingt)

Der Alarm, auf den es ankommt, kommt um drei Uhr früh. Einmal bewusst
prüfen, ob er dann auch durchkommt:

- Handy im **Nachtmodus / Nicht stören**: Kommt die Meldung durch? Falls
  nicht, in den Systemeinstellungen die App als *zeitkritisch* bzw. von „Nicht
  stören" ausgenommen markieren. Das kann die App nicht für sich selbst
  erledigen.
- **Android-Akkuoptimierung**: App auf „nicht optimieren" setzen, sonst
  verzögert das System die Zustellung.
- Ergebnis dem Betreiber ausdrücklich mitteilen — inklusive der
  Systemeinstellungen, die er selbst gesetzt hat.

## Schritt 7 — Aufräumen

- `docs/roadmap.md`: Push-Zeile bleibt ✅, aber Vermerk „scharf seit
  <Datum>, Nachtprobe bestanden" ergänzen.
- Mehrere Geräte: Schritte 3–4 je Gerät. Die Registrierung ist pro Gerät;
  die Auswahl der Alarmarten ebenfalls.
- Betreiber informieren, welche Alarmarten je Gerät aktiv sind.

## Fehlerbilder

| Symptom | Ursache |
| --- | --- |
| „Push ist noch nicht eingerichtet" | eine der vier `FIREBASE_*`-Variablen fehlt |
| „Der Server kann noch nicht senden" | `GCP_SERVICE_ACCOUNT_JSON` fehlt/ungültig |
| Anmeldung bricht mit SDK-Fehler ab | VAPID-Schlüssel gehört nicht zu diesem Projekt |
| `zugestellt:0` trotz Anmeldung | Token im falschen Firebase-Projekt registriert |
| Meldung kommt nur bei offener App | Service Worker nicht registriert → `/sw.js` muss 200 mit `application/javascript` liefern (bei aktivem Passwortschutz ist der Pfad in `middleware.ts` ausgenommen — nicht wieder einfangen!) |
| Auf iOS gar nichts | App läuft im Safari-Tab statt installiert |

## Rollback

`GCP_SERVICE_ACCOUNT_JSON` entfernen + Redeploy → Versand aus, App
unverändert nutzbar. Einzelne Geräte melden sich über den Schalter ab
(`DELETE /api/push/registrieren`). Keine Code-Änderung nötig.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Firebase-Projekt, Web-App, VAPID, Dienstkonto | Betreiber |
| Env-Variablen setzen (Secret-Store ist gesperrt) | Betreiber |
| Schritte 2, 5, 7 | Orchestrator (dieser Skill) |
| Schritte 3, 4, 6 — am echten Gerät | Betreiber, angeleitet |
