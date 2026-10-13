#!/usr/bin/env bash
# Misst die Antwortzeit (TTFB) der Webapp: je N Abrufe, Median/Min/Max in ms,
# dazu die von Vercel gemeldete Edge->Function-Region (x-vercel-id).
#
#   COOKIE='stallblick_session=...' bash tests/messen-ttfb.sh [N] [BASIS]
#
# COOKIE (Session nach dem Login) ist noetig, damit /api/events die Function
# erreicht – ohne Login antwortet schon die Middleware am Rand mit 401 und
# misst die Region der Function nicht. Messpunkt zaehlt: Fuer Nutzer in
# Deutschland von einem Rechner in Deutschland messen (z. B. dem Stall-Rechner).
set -u
N="${1:-15}"
BASIS="${2:-https://stallwache.vercel.app}"
COOKIE="${COOKIE:-}"

median() { sort -n | awk '{a[NR]=$1} END{ if(NR==0){print "-"; exit} print (NR%2)?a[(NR+1)/2]:(a[NR/2]+a[NR/2+1])/2 }'; }

messen() {
  local pfad="$1" kopf=()
  [ -n "${2:-}" ] && kopf=(-H "Cookie: $2")
  local werte=() region=""
  for _ in $(seq "$N"); do
    local out
    out="$(curl -s -o /dev/null -D /tmp/ttfb.hdr -w '%{time_starttransfer}' "${kopf[@]}" "$BASIS$pfad")"
    werte+=("$(awk -v t="$out" 'BEGIN{printf "%d", t*1000}')")
    [ -z "$region" ] && region="$(grep -i '^x-vercel-id:' /tmp/ttfb.hdr | tr -d '\r' | awk '{print $2}' | cut -d- -f1)"
  done
  local med min max
  med="$(printf '%s\n' "${werte[@]}" | median)"
  min="$(printf '%s\n' "${werte[@]}" | sort -n | head -1)"
  max="$(printf '%s\n' "${werte[@]}" | sort -n | tail -1)"
  printf '%-24s Median %5s ms  (min %s, max %s)  Region %s\n' "$pfad" "$med" "$min" "$max" "$region"
}

echo "TTFB, $N Abrufe je Pfad, $BASIS"
messen /login
messen /manifest.webmanifest
if [ -n "$COOKIE" ]; then
  messen /api/events "$COOKIE"
else
  echo "(kein COOKIE gesetzt: /api/events uebersprungen)"
fi
