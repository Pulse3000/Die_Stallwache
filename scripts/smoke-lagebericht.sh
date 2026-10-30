#!/usr/bin/env bash
# Smoke-Test: Lagebericht-Vertrag (neu) + Ingest-Vertrag (unverändert).
# Schreibt KEINE Ereignisse: Ingest wird nur mit Payloads geprüft, die abgelehnt werden müssen.
#
#   npm run dev                      # Terminal 1
#   REPORT_READ_TOKEN=... EDGE_INGEST_TOKEN=... bash scripts/smoke-lagebericht.sh   # Terminal 2
#
# Spezifikation: docs/lagebericht-vertrag.md
set -uo pipefail

BASIS_URL="${BASIS_URL:-http://localhost:3000}"
case "$BASIS_URL" in
  http://localhost*|http://127.0.0.1*) ;;
  *) if [ "${ERLAUBE_EXTERN:-0}" != "1" ]; then
       echo "Abbruch: nur gegen localhost. ERLAUBE_EXTERN=1 übersteuert (Skript schreibt nichts)."; exit 2
     fi ;;
esac
if [ -z "${REPORT_READ_TOKEN:-}" ]; then echo "Abbruch: REPORT_READ_TOKEN setzen"; exit 2; fi
command -v node >/dev/null || { echo "Abbruch: node fehlt"; exit 2; }

KOERPER="$(mktemp)"; KOPF="$(mktemp)"; trap 'rm -f "$KOERPER" "$KOPF"' EXIT
fehler=0

status() {   # status <erwartet> <beschreibung> <curl-argumente…>
  local erwartet="$1" text="$2"; shift 2
  local ist
  ist=$(curl -s -o "$KOERPER" -D "$KOPF" -w '%{http_code}' "$@")
  if [ "$ist" = "$erwartet" ]; then echo "ok   $text ($ist)"
  else echo "FEHL $text: erwartet $erwartet, erhalten $ist"; fehler=$((fehler + 1)); fi
}

L="$BASIS_URL/api/lagebericht"
status 401 "Lagebericht ohne Token"            "$L"
status 401 "Lagebericht mit falschem Token"    -H "x-report-token: falsch" "$L"
status 401 "Ingest-Token öffnet Lagebericht nicht" -H "x-report-token: ${EDGE_INGEST_TOKEN:-ingest}" "$L"
status 400 "stunden=0"                         -H "x-report-token: $REPORT_READ_TOKEN" "$L?stunden=0"
status 400 "stunden=73"                        -H "x-report-token: $REPORT_READ_TOKEN" "$L?stunden=73"
status 400 "stunden=abc"                       -H "x-report-token: $REPORT_READ_TOKEN" "$L?stunden=abc"
status 200 "Lagebericht 12 h"                  -H "x-report-token: $REPORT_READ_TOKEN" "$L?stunden=12"

if grep -qi '^cache-control:.*no-store' "$KOPF"; then echo "ok   Cache-Control: no-store"
else echo "FEHL Cache-Control: no-store fehlt"; fehler=$((fehler + 1)); fi

node - "$KOERPER" <<'JS' || fehler=$((fehler + 1))
const fs = require('fs');
const b = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const raus = (m) => { console.log('FEHL ' + m); process.exit(1); };
const pflicht = ['erzeugt', 'zeitraum', 'quelle', 'zaehler', 'je_kamera', 'letzte_ereignisse', 'letztes_lebenszeichen'];
const fehlt = pflicht.filter((k) => !(k in b));
if (fehlt.length) raus('fehlende Felder: ' + fehlt.join(', '));
if (b.zeitraum.stunden !== 12) raus('zeitraum.stunden != 12');
if (typeof b.quelle.name !== 'string' || !b.quelle.name) raus('quelle.name fehlt');
for (const t of ['kalbeverdacht', 'austreibung', 'brunstverdacht', 'info'])
  if (!Number.isInteger(b.zaehler[t])) raus('zaehler.' + t + ' ist keine Ganzzahl');
for (const k of ['stallwache', 'futterwache', 'stallbox'])
  if (!(k in b.letztes_lebenszeichen)) raus('letztes_lebenszeichen.' + k + ' fehlt');
if (!Array.isArray(b.letzte_ereignisse) || b.letzte_ereignisse.length > 20) raus('letzte_ereignisse fehlt oder > 20');
const erlaubt = ['zeit', 'typ', 'kuhId', 'kamera', 'nachricht', 'konfidenz'];
for (const e of b.letzte_ereignisse) {
  const extra = Object.keys(e).filter((k) => !erlaubt.includes(k));
  if (extra.length) raus('Zusatzfelder in letzte_ereignisse: ' + extra.join(', '));
}
const zeiten = b.letzte_ereignisse.map((e) => Date.parse(e.zeit));
if (zeiten.some((z, i) => i > 0 && z > zeiten[i - 1])) raus('letzte_ereignisse nicht neueste zuerst');
if (/"[^"]{2001,}"/.test(JSON.stringify(b))) raus('Zeichenkette > 2000 Zeichen (Bild-/Rohdaten?)');
console.log('ok   JSON-Form des Lageberichts');
JS

E="$BASIS_URL/api/events"
status 401 "Ingest mit falschem Token" -X POST -H "content-type: application/json" \
  -H "x-ingest-token: falsch" -d '{"typ":"info","kamera":"stallwache","nachricht":"smoke"}' "$E"
if [ -n "${EDGE_INGEST_TOKEN:-}" ]; then
  status 400 "Ingest unbekannter typ" -X POST -H "content-type: application/json" \
    -H "x-ingest-token: $EDGE_INGEST_TOKEN" -d '{"typ":"lahmheit","kamera":"stallwache","nachricht":"smoke"}' "$E"
  status 400 "Ingest ohne nachricht" -X POST -H "content-type: application/json" \
    -H "x-ingest-token: $EDGE_INGEST_TOKEN" -d '{"typ":"info","kamera":"stallwache"}' "$E"
else
  echo "hinweis Ingest-400-Prüfungen übersprungen (EDGE_INGEST_TOKEN nicht gesetzt)"
fi

echo "----"
if [ "$fehler" -eq 0 ]; then echo "SMOKE GRÜN"; exit 0; else echo "SMOKE ROT: $fehler Befund(e)"; exit 1; fi
