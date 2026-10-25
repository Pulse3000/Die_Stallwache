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
  `PUBSUB_TOPIC` in Vercel gesetzt, `/api/events` liefert `"pubsub": true`).
  Ohne sie kommt im Topic nichts an — der Sink läuft dann, bleibt aber leer.
- Abrechnung (Billing) ist im GCP-Projekt aktiv; Cloud Functions gen2 lässt
  sich sonst nicht deployen. Bei einigen hundert Ereignissen pro Tag liegt
  der Betrieb in den kostenlosen Kontingenten von Cloud Functions und
  Firestore; das Build-Image in Artifact Registry kann wenige Cent im Monat
  kosten.

## Einrichten in einem Befehl (Betreiber, einmalig)

In der [Google Cloud Shell](https://shell.cloud.google.com) (gcloud ist
dort bereits angemeldet):

```bash
git clone https://github.com/Pulse3000/Die_Stallwache.git
bash Die_Stallwache/cloud-functions/pubsub-firestore-sink/einrichten.sh --trocken   # nur zeigen
bash Die_Stallwache/cloud-functions/pubsub-firestore-sink/einrichten.sh             # einrichten
```

`einrichten.sh` ist idempotent und erledigt der Reihe nach:

1. APIs aktivieren (Functions, Run, Eventarc, Pub/Sub, Firestore, Build,
   Artifact Registry, IAM).
2. Firestore (Native Mode, `eur3`) anlegen, falls noch keine
   `(default)`-Datenbank existiert.
3. Topic `stall-ereignisse` anlegen, falls es fehlt (muss gleich
   `PUBSUB_TOPIC` in Vercel sein).
4. Eigenes Laufzeit-Konto `stall-firestore-sink@<PROJEKT>.iam.gserviceaccount.com`
   mit nur `roles/datastore.user`, `roles/run.invoker`,
   `roles/eventarc.eventReceiver`; Compute-Default-Konto bekommt
   `roles/cloudbuild.builds.builder` (baut die Function), der
   Pub/Sub-Dienstagent `roles/iam.serviceAccountTokenCreator`.
5. Function deployen (gen2, Node 22, `europe-west4`; Node 20 ist seit
   April 2026 ohne Node-Support).
6. **Probe:** Testnachricht ins Topic, wartet bis 90 s auf das Dokument in
   `stall_ereignisse`, löscht es wieder. Ohne Dokument: letzte Logs der
   Function und Abbruch mit Fehler.

Optionen: `--projekt <ID>`, `--topic <Name>`, `--region <Region>`,
`--firestore-ort <Ort>`. Ihre Rolle im Projekt muss IAM-Rollen vergeben
dürfen (Inhaber oder Projekt-IAM-Administrator).

## Einzelschritte von Hand (Alternative)

```bash
cd cloud-functions/pubsub-firestore-sink

gcloud functions deploy pubsub-firestore-sink \
  --gen2 \
  --runtime=nodejs22 \
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
läuft (ohne `--service-account` das Compute-Default-Konto), braucht die
Rolle `roles/datastore.user` auf Firestore — in der GCP-Konsole unter IAM
nachtragen, falls das Schreiben mit `PERMISSION_DENIED` fehlschlägt.

Optional: `FIRESTORE_COLLECTION` als Env-Variable der Function setzen, wenn
nicht `stall_ereignisse` heißen soll
(`--set-env-vars=FIRESTORE_COLLECTION=...`; `einrichten.sh` prüft dann die
falsche Collection — in dem Fall von Hand verifizieren).

## Verifizieren

`einrichten.sh` prüft den Weg Topic → Function → Firestore selbst. Den
ganzen Weg ab der Webapp prüft man so:

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

Der Sink macht die Daten lediglich **speicherbar**. Für den Tagesreport
gibt es inzwischen den token-geschützten Lese-Endpunkt der Webapp:

```bash
curl -s -H "x-status-token: $STATUS_READ_TOKEN" \
  "https://<app>/api/stall-status?stunden=12"
```

Er liefert je Kamera und Kuh `OK`/`WARNUNG`/`KRITISCH`/`UNBEKANNT` samt
Klartext und liest aus dem Ereignisspeicher der Webapp (KV), nicht aus
Firestore — die Statusabfrage funktioniert damit auch ohne GCP. Regeln und
Grenzen: [`docs/statusabfrage-spezifikation.md`](../../docs/statusabfrage-spezifikation.md).
