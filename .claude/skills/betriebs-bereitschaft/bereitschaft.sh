#!/usr/bin/env bash
# Bereitschafts-Check der Stallwache: Welche Bausteine sind scharf?
#
# Gehoert zum Skill `betriebs-bereitschaft`. Fragt ausschliesslich oeffentlich
# beobachtbare Endpunkte ab — keine Secrets noetig, nichts wird veraendert.
#
#   bash .claude/skills/betriebs-bereitschaft/bereitschaft.sh [BASIS-URL] [COOKIE-DATEI]
#
# Ohne Argumente wird die Produktion geprueft. Bei aktivem Passwortschutz
# vorher anmelden und die Cookie-Datei mitgeben:
#   curl -c kekse -X POST "$B/api/login" -H 'content-type: application/json' \
#        -d '{"passwort":"..."}'

set -uo pipefail

BASIS="${1:-https://stallwache.vercel.app}"
KEKSE="${2:-}"
CURL=(curl -s --max-time 25)
[ -n "$KEKSE" ] && CURL+=(-b "$KEKSE")

hole() { "${CURL[@]}" "$BASIS$1"; }
code() { "${CURL[@]}" -o /dev/null -w '%{http_code}' "$BASIS$1"; }

zeile() { printf '  %-22s %-10s %s\n' "$1" "$2" "$3"; }

echo "Bereitschaft: $BASIS"
echo

# --- 1. Erreichbarkeit & Anmeldung -----------------------------------------
START=$(code /)
if [ "$START" = "307" ] || [ "$START" = "302" ]; then
  echo "  Passwortschutz ist aktiv und es liegt keine Anmeldung vor."
  echo "  Ohne Cookie-Datei sind nur die offenen Pfade pruefbar."
  echo
fi

# --- 2. Service Worker (stille Falle) --------------------------------------
SW_TYP=$("${CURL[@]}" -o /dev/null -w '%{content_type}' "$BASIS/sw.js")
SW_CODE=$(code /sw.js)
if [ "$SW_CODE" = "200" ] && [[ "$SW_TYP" == *javascript* ]]; then
  zeile "Service Worker" "SCHARF" "als JavaScript ausgeliefert"
else
  zeile "Service Worker" "DEFEKT" "HTTP $SW_CODE, Typ $SW_TYP — PWA verliert Offline UND Push"
fi

# --- 3. Ereigniskette -------------------------------------------------------
EV=$(hole /api/events)
if echo "$EV" | grep -q '"quelle"'; then
  QUELLE=$(echo "$EV" | python3 -c 'import sys,json;print(json.load(sys.stdin)["quelle"])' 2>/dev/null)
  KONTAKT=$(echo "$EV" | python3 -c 'import sys,json;print(json.load(sys.stdin)["letzterKontakt"] or "nie")' 2>/dev/null)
  if [ "$QUELLE" = "demo" ]; then
    zeile "Edge-Agent" "SCHLAEFT" "nur Demo-Daten — noch kein Ereignis gemeldet"
  else
    zeile "Edge-Agent" "SCHARF" "letzter Kontakt: $KONTAKT"
  fi
else
  zeile "Edge-Agent" "UNKLAR" "Ereignisliste nicht lesbar (Anmeldung noetig?)"
fi

# --- 4. Push ----------------------------------------------------------------
PK=$(hole /api/push/konfig)
if echo "$PK" | grep -q '"aktiv":true'; then
  zeile "Push (FCM)" "SCHARF" "Versand und Browser-Anmeldung moeglich"
elif echo "$PK" | grep -q '"versandBereit":true'; then
  zeile "Push (FCM)" "HALB" "Server sendet, aber FIREBASE_*-Web-Konfig fehlt"
elif echo "$PK" | grep -q '"aktiv"'; then
  zeile "Push (FCM)" "SCHLAEFT" "nicht eingerichtet — Skill push-live-schalten"
else
  zeile "Push (FCM)" "UNKLAR" "Konfig-Endpunkt nicht lesbar"
fi

# --- 5. Assistent -----------------------------------------------------------
AS=$(hole /api/assistent)
if echo "$AS" | grep -q '"ki":true'; then
  zeile "Assistent" "SCHARF" "Vertex AI bzw. Gemini angebunden"
elif echo "$AS" | grep -q '"ki"'; then
  zeile "Assistent" "LOKAL" "antwortet aus dem Protokoll (voll nutzbar)"
else
  zeile "Assistent" "UNKLAR" "Endpunkt nicht lesbar"
fi

# --- 6. Tuya-Geraete --------------------------------------------------------
TG=$(hole /api/tuya/geraete)
if echo "$TG" | grep -q '"geraete"'; then
  python3 - "$TG" <<'PY' 2>/dev/null || zeile "Tuya-Geraete" "UNKLAR" "Antwort nicht lesbar"
import sys, json
d = json.loads(sys.argv[1])
g = d.get("geraete", [])
if d.get("fehler"):
    print("  %-22s %-10s %s" % ("Tuya-Geraete", "SCHLAEFT", d["fehler"][:60]))
elif not g:
    print("  %-22s %-10s %s" % ("Tuya-Geraete", "SCHLAEFT", d.get("hinweis", "keine freigegeben")[:60]))
else:
    online = [x for x in g if x.get("online")]
    fehler = {x.get("fehler", "")[:45] for x in g if x.get("fehler")}
    zustand = "SCHARF" if len(online) == len(g) else ("HALB" if online else "DEFEKT")
    detail = "%d von %d online" % (len(online), len(g))
    if fehler:
        detail += " — " + "; ".join(sorted(fehler))
    print("  %-22s %-10s %s" % ("Tuya-Geraete", zustand, detail))
PY
else
  zeile "Tuya-Geraete" "UNKLAR" "Endpunkt nicht lesbar (Anmeldung noetig?)"
fi

# --- 7. Kameras -------------------------------------------------------------
for k in futterwache abkalbebox weidewache; do
  C=$(code "/api/$k/stream")
  A=$(hole "/api/$k/stream")
  if [ "$C" = "404" ]; then
    # Route existiert im Deployment nicht — meist ein aelterer Stand.
    zeile "Kamera $k" "FEHLT" "Route nicht deployt (alter Stand?)"
  elif echo "$A" | grep -q '"url"'; then
    zeile "Kamera $k" "SCHARF" "Stream-URL erhalten"
  elif echo "$A" | grep -q 'nicht konfiguriert'; then
    zeile "Kamera $k" "SCHLAEFT" "Geraete-ID fehlt"
  elif echo "$A" | grep -q 'fehler'; then
    zeile "Kamera $k" "DEFEKT" "$(echo "$A" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("fehler","?")[:60])' 2>/dev/null || echo 'unlesbar')"
  else
    zeile "Kamera $k" "UNKLAR" "HTTP $C, keine verwertbare Antwort"
  fi
done

# --- 8. Bridge (Stallwache) -------------------------------------------------
if hole / | grep -q "NEXT_PUBLIC_BRIDGE_URL"; then
  zeile "Bridge (Stallwache)" "SCHLAEFT" "Platzhalter sichtbar — Tunnel-Hostname fehlt"
elif [ "$START" = "200" ]; then
  zeile "Bridge (Stallwache)" "GESETZT" "Livebild erst am Geraet pruefbar"
else
  zeile "Bridge (Stallwache)" "UNKLAR" "Startseite nicht lesbar"
fi

echo
echo "Lesart: SCHARF = in Betrieb · SCHLAEFT = gebaut, nicht konfiguriert"
echo "        HALB/DEFEKT = konfiguriert, aber nicht funktionsfaehig"
echo "        FEHLT  = Route im Deployment nicht vorhanden"
echo "        UNKLAR = von aussen nicht pruefbar (meist fehlende Anmeldung)"
