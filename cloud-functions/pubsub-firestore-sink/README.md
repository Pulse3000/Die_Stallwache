# Pub/Sub → Firestore-Sink

Ergänzt die Pub/Sub-Spiegelung aus `lib/pubsub.ts`/`lib/gcp.ts` (Skill
`gcp-anbindung`) um einen **dauerhaft abfragbaren Lese-Speicher**. Ohne
diesen Sink landen Ereignisse zwar im Topic, aber es gibt keinen Ort, an dem
eine Status-Routine (z. B. der zweimal tägliche KuhWatch-Tagesreport) sie
nachträglich lesen kann.

Diese Function ist ein **zusätzliches** Abo am bestehenden Topic — sie
ersetzt keine vorhandene Archiv-/BigQuery-Nachanalyse, mehrere Abonnenten an
einem Pub/Sub-Topic sind der Normalfall.

## Voraussetzung

- Die GCP-Anbindung aus Skill `gcp-anbindung` ist scharf (Service Account +
  `PUBSUB_TOPIC` gesetzt, Topic existiert, `/api/events` liefert
  `"pubsub": true`).
- Firestore (Native Mode) ist im selben GCP-Projekt angelegt (Firestore →
  Datenbank erstellen, falls noch nicht vorhanden; Region frei wählbar, EU
  empfohlen).

## Deploy (Betreiber, einmalig)

```bash
cd cloud-functions/pubsub-firestore-sink

gcloud functions deploy pubsub-firestore-sink \
  --gen2 \
  --runtime=nodejs20 \
  --region=europe-west4 \
  --source=. \
  --entry-point=pubsubFirestoreSink \
  --trigger-topic=stall-ereignisse \
  --memory=256MB \
  --timeout=30s \
  --max-instances=5
```

`--trigger-topic` auf den tatsächlichen `PUBSUB_TOPIC`-Namen anpassen, falls
abweichend von `stall-ereignisse`. Das Service-Konto, unter dem die Function
läuft (Standard: `<PROJECT_ID>@appspot.gserviceaccount.com` bzw. das
Compute-Default-SA), braucht die Rolle `roles/datastore.user` auf
Firestore — in der GCP-Konsole unter IAM nachtragen, falls das Schreiben mit
`PERMISSION_DENIED` fehlschlägt.

Optional: `FIRESTORE_COLLECTION` als Env-Variable der Function setzen, wenn
nicht `stall_ereignisse` heißen soll
(`--set-env-vars=FIRESTORE_COLLECTION=...`).

## Verifizieren

1. Testereignis wie in `gcp-anbindung` Schritt 2 einspeisen:
   `POST /api/events` mit `x-ingest-token` und
   `{"typ":"info","nachricht":"Firestore-Sink-Test"}`.
2. In der Firestore-Konsole (oder `gcloud firestore documents list`): Die
   Collection `stall_ereignisse` enthält ein neues Dokument mit `typ: "info"`
   und gesetztem `empfangenAm`.
3. Cloud-Functions-Logs prüfen (`gcloud functions logs read
   pubsub-firestore-sink --region=europe-west4 --limit=20`), falls kein
   Dokument erscheint — meist fehlende `datastore.user`-Rolle oder falscher
   Topic-Name.

## Rollback

`gcloud functions delete pubsub-firestore-sink --region=europe-west4
--gen2`. Die Pub/Sub-Spiegelung selbst (und alle anderen Abonnenten des
Topics) laufen unverändert weiter — der Sink ist ein reiner Lese-Baustein,
kein Teil des Alarmwegs.

## Anschluss an den Tagesreport

Der Sink macht die Daten lediglich **speicherbar**. Damit die
KuhWatch-Tagesreport-Routine sie auch lesen kann, fehlt noch ein
Abfrageweg aus der Cloud-Session heraus — z. B. ein schlanker, token-
geschützter Lese-Endpunkt in der Webapp (`GET /api/stall-status?stunden=12`),
den die Routine per HTTPS abruft. Das ist bewusst nicht Teil dieser
Function und folgt als eigener Schritt, sobald der Sink produktiv Daten
sammelt.
