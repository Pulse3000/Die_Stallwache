#!/usr/bin/env bash
# ============================================================================
# Pub/Sub -> Firestore-Sink in einem Befehl einrichten und pruefen
# ============================================================================
# Laeuft in der Google Cloud Shell (gcloud ist dort angemeldet):
#
#   git clone https://github.com/Pulse3000/Die_Stallwache.git
#   bash Die_Stallwache/cloud-functions/pubsub-firestore-sink/einrichten.sh --trocken
#   bash Die_Stallwache/cloud-functions/pubsub-firestore-sink/einrichten.sh
#
# Optionen: --projekt <ID>        (Default: gcloud config get-value project)
#           --topic <Name>        (Default: stall-ereignisse = PUBSUB_TOPIC in Vercel)
#           --region <Region>     (Default: europe-west4)
#           --firestore-ort <Ort> (Default: eur3 = EU, nur beim Anlegen)
#           --trocken             nur zeigen, nichts aendern
#
# Idempotent: Vorhandenes (APIs, Datenbank, Topic, Konto, Rollen, Function)
# wird erkannt bzw. aktualisiert. Am Ende eine Probe: Testnachricht ins
# Topic, Dokument in Firestore abwarten, Testdokument wieder loeschen.
# README.md in diesem Ordner beschreibt die einzelnen Schritte.
# ============================================================================
set -euo pipefail
GRUEN='\033[0;32m'; GELB='\033[1;33m'; ROT='\033[0;31m'; AUS='\033[0m'
info()  { printf '%b==>%b %s\n' "$GRUEN" "$AUS" "$1"; }
warn()  { printf '%b!! %b %s\n' "$GELB" "$AUS" "$1"; }
fehler(){ printf '%bFEHLER:%b %s\n' "$ROT" "$AUS" "$1" >&2; exit 1; }

HIER="$(cd "$(dirname "$0")" && pwd)"
PROJEKT=""; TOPIC="stall-ereignisse"; REGION="europe-west4"; ORT="eur3"; TROCKEN=0
FUNKTION="pubsub-firestore-sink"; COLLECTION="stall_ereignisse"; KONTO_NAME="stall-firestore-sink"
FIRESTORE_API="${FIRESTORE_API:-https://firestore.googleapis.com/v1}"
WARTE_S="${WARTE_S:-10}"  # Pause zwischen Wiederholungen (IAM braucht etwas)
while [ $# -gt 0 ]; do
  case "$1" in
    --projekt|--topic|--region|--firestore-ort)
      [ $# -ge 2 ] || fehler "$1 braucht einen Wert."
      case "$1" in
        --projekt) PROJEKT="$2" ;; --topic) TOPIC="$2" ;;
        --region) REGION="$2" ;; --firestore-ort) ORT="$2" ;;
      esac
      shift ;;
    --trocken) TROCKEN=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) fehler "Unbekannte Option: $1" ;;
  esac
  shift
done

fuehre() {  # aendernde Befehle; im Trockenlauf nur zeigen
  if [ "$TROCKEN" = "1" ]; then printf '   [trocken] %s\n' "$*" >&2; else "$@"; fi
}

rolle() {  # rolle <Mitglied> <Rolle>; neue Konten sind erst nach Sekunden sichtbar
  local versuch
  for versuch in 1 2 3 4 5 6; do
    if fuehre gcloud projects add-iam-policy-binding "$PROJEKT" --member="$1" \
         --role="$2" --condition=None --quiet >/dev/null; then
      return 0
    fi
    [ "$versuch" -lt 6 ] && { warn "Rolle $2 noch nicht setzbar, neuer Versuch in ${WARTE_S} s …"; sleep "$WARTE_S"; }
  done
  fehler "Rolle $2 fuer $1 nicht setzbar (eigene Rechte: Projekt-IAM-Administrator?)."
}

command -v gcloud >/dev/null || fehler "gcloud fehlt – in der Google Cloud Shell ausfuehren."
KONTO=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1)
[ -n "$KONTO" ] || fehler "gcloud ist nicht angemeldet (gcloud auth login)."
[ -n "$PROJEKT" ] || PROJEKT=$(gcloud config get-value project 2>/dev/null || true)
[ -n "$PROJEKT" ] || fehler "Kein Projekt gesetzt: --projekt <ID> oder gcloud config set project <ID>."
PROJEKTNR=$(gcloud projects describe "$PROJEKT" --format='value(projectNumber)' 2>/dev/null) \
  || fehler "Projekt $PROJEKT nicht lesbar (Rechte? Projekt-ID?)."
[ -n "$PROJEKTNR" ] || fehler "Projekt $PROJEKT nicht lesbar (Rechte? Projekt-ID?)."
LAUFZEIT_SA="${KONTO_NAME}@${PROJEKT}.iam.gserviceaccount.com"
BUILD_SA="${PROJEKTNR}-compute@developer.gserviceaccount.com"
PUBSUB_AGENT="service-${PROJEKTNR}@gcp-sa-pubsub.iam.gserviceaccount.com"
info "Projekt $PROJEKT ($PROJEKTNR), Konto $KONTO, Topic $TOPIC, Region $REGION"
[ "$TROCKEN" = "1" ] && warn "Trockenlauf: Es wird nichts angelegt oder geaendert."

# --- 1. APIs -------------------------------------------------------------------
info "APIs aktivieren (Functions, Run, Eventarc, Pub/Sub, Firestore, Build, Registry, IAM) …"
fuehre gcloud services enable cloudfunctions.googleapis.com run.googleapis.com \
  eventarc.googleapis.com pubsub.googleapis.com firestore.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com iam.googleapis.com \
  --project="$PROJEKT"

# --- 2. Firestore-Datenbank -----------------------------------------------------
if gcloud firestore databases describe --database='(default)' --project="$PROJEKT" >/dev/null 2>&1; then
  info "Firestore-Datenbank (default) vorhanden."
else
  info "Lege Firestore (Native Mode, $ORT) an …"
  fuehre gcloud firestore databases create --database='(default)' --location="$ORT" \
    --type=firestore-native --project="$PROJEKT"
fi

# --- 3. Topic -------------------------------------------------------------------
if gcloud pubsub topics describe "$TOPIC" --project="$PROJEKT" >/dev/null 2>&1; then
  info "Topic $TOPIC vorhanden."
else
  warn "Topic $TOPIC fehlt – lege es an. In Vercel muss PUBSUB_TOPIC=$TOPIC stehen (Skill gcp-anbindung)."
  fuehre gcloud pubsub topics create "$TOPIC" --project="$PROJEKT"
fi

# --- 4. Konto und Rollen --------------------------------------------------------
# Eigenes Laufzeit-Konto mit nur den noetigen Rollen: in Firestore schreiben,
# Ereignisse vom Trigger empfangen. Das Compute-Default-Konto baut die
# Function (Cloud Build); der Pub/Sub-Dienstagent erzeugt die Tokens fuer den
# Push an die Function.
if gcloud iam service-accounts describe "$LAUFZEIT_SA" --project="$PROJEKT" >/dev/null 2>&1; then
  info "Laufzeit-Konto $LAUFZEIT_SA vorhanden."
else
  info "Lege Laufzeit-Konto $LAUFZEIT_SA an …"
  fuehre gcloud iam service-accounts create "$KONTO_NAME" --project="$PROJEKT" \
    --display-name="Stallwache Pub/Sub -> Firestore-Sink"
fi
info "Rollen setzen …"
for ROLLE in roles/datastore.user roles/run.invoker roles/eventarc.eventReceiver; do
  rolle "serviceAccount:$LAUFZEIT_SA" "$ROLLE"
done
rolle "serviceAccount:$BUILD_SA" roles/cloudbuild.builds.builder
rolle "serviceAccount:$PUBSUB_AGENT" roles/iam.serviceAccountTokenCreator

# --- 5. Function ----------------------------------------------------------------
info "Deploye $FUNKTION (dauert 2–4 min) …"
fuehre gcloud functions deploy "$FUNKTION" --gen2 --runtime=nodejs20 --region="$REGION" \
  --source="$HIER" --entry-point=pubsubFirestoreSink --trigger-topic="$TOPIC" \
  --service-account="$LAUFZEIT_SA" --trigger-service-account="$LAUFZEIT_SA" \
  --memory=256MB --timeout=30s --max-instances=5 --project="$PROJEKT" --quiet

if [ "$TROCKEN" = "1" ]; then
  info "Trockenlauf beendet. Ohne --trocken aufrufen, um einzurichten."
  exit 0
fi

# --- 6. Probe -------------------------------------------------------------------
ID="sink-probe-$(date +%s)"
info "Probe: Testnachricht $ID ins Topic, warte auf das Dokument in Firestore …"
gcloud pubsub topics publish "$TOPIC" --project="$PROJEKT" --attribute=typ=info \
  --message="{\"id\":\"$ID\",\"typ\":\"info\",\"nachricht\":\"Firestore-Sink-Probe\"}" >/dev/null
DOKUMENT="$FIRESTORE_API/projects/$PROJEKT/databases/(default)/documents/$COLLECTION/$ID"
TOKEN=$(gcloud auth print-access-token)
for _ in $(seq 1 18); do
  if curl -sf -o /dev/null -H "Authorization: Bearer $TOKEN" "$DOKUMENT"; then
    curl -sf -o /dev/null -X DELETE -H "Authorization: Bearer $TOKEN" "$DOKUMENT" || true
    info "Probe bestanden: Dokument $ID kam in $COLLECTION an (wieder geloescht)."
    info "Ab jetzt landet jedes Ereignis, das die Webapp nach Pub/Sub spiegelt, in Firestore."
    exit 0
  fi
  sleep 5
done
warn "Kein Dokument nach 90 s. Letzte Logs der Function:"
gcloud functions logs read "$FUNKTION" --region="$REGION" --project="$PROJEKT" --limit=20 || true
fehler "Probe fehlgeschlagen – meist fehlt eine Rolle oder das Topic stimmt nicht (README.md)."
