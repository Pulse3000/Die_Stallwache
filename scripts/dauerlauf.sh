#!/bin/bash
# Stallwache Dauerlauf v2 - 60s Zyklus, SQLite-Aufzeichnung
# Pfade: scripts/, logs/, data/ unter ~/Die_Stallwache/
SCRIPT_DIR="/home/stallwache/Die_Stallwache/scripts"
LOG="/home/stallwache/Die_Stallwache/logs/dauerlauf.log"
DB="/home/stallwache/Die_Stallwache/data/dauerlauf.db"
PID_FILE="/home/stallwache/Die_Stallwache/logs/dauerlauf.pid"

echo $$ > "$PID_FILE"
echo "$(date "+%F %H:%M:%S") DAUERLAUF v2 gestartet (60 s Zyklus, SQLite-Aufzeichnung)" >> "$LOG"
while true; do
  Z=$(date +%s)
  NEWEST=$(ls -t ~/Die_Stallwache/edge-agent/aufnahmen/*.jpg 2>/dev/null | head -1)
  if [ -z "$NEWEST" ]; then
    echo "$(date "+%H:%M:%S") | KEIN BILD" >> "$LOG"
  else
    docker cp "$NEWEST" kuhwatch-stallwache:/tmp/test.jpg >/dev/null 2>&1
    docker cp /tmp/nacht_analyse.py kuhwatch-stallwache:/tmp/nacht_analyse.py >/dev/null 2>&1
    RES=$(docker exec kuhwatch-stallwache python /tmp/nacht_analyse.py 2>/dev/null | tail -1)
    LINE=$(echo "$RES" | python3 "$SCRIPT_DIR/dauerlauf_db.py" "$(basename $NEWEST .jpg)" 2>/dev/null)
    echo "${LINE:-$(date "+%H:%M:%S") | ANALYSE_FEHLGESCHLAGEN}" >> "$LOG"
  fi
  V=$((60-$(date +%s)+Z)); [ $V -lt 5 ] && V=5
  [ $(wc -l < "$LOG") -gt 20000 ] && mv "$LOG" "${LOG}.1"
  sleep $V
done
