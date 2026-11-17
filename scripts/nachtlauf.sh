#!/bin/bash
# Ueber-Nacht-Silent-Lauf: alle 2 Min Bild + Analyse (conf 0.15), bis 07:00 Uhr
LOG="/home/stallwache/Die_Stallwache/logs/nachtlauf.log"
PID_FILE="/home/stallwache/Die_Stallwache/logs/nachtlauf.pid"

ENDE=$(date -d "tomorrow 07:00" +%s)
echo $$ > "$PID_FILE"
echo "$(date "+%F %H:%M:%S") NACHTLAUF gestartet (Schwelle 0.15, alle 2 Min, bis morgen 07:00)" >> "$LOG"
while [ $(date +%s) -lt $ENDE ]; do
  NEWEST=$(ls -t ~/Die_Stallwache/edge-agent/aufnahmen/*.jpg 2>/dev/null | head -1)
  if [ -z "$NEWEST" ]; then
    echo "$(date "+%H:%M:%S") | KEIN BILD" >> "$LOG"
  else
    docker cp "$NEWEST" kuhwatch-stallwache:/tmp/test.jpg >/dev/null 2>&1
    docker cp /tmp/nacht_analyse.py kuhwatch-stallwache:/tmp/nacht_analyse.py >/dev/null 2>&1
    RES=$(docker exec kuhwatch-stallwache python /tmp/nacht_analyse.py 2>/dev/null | grep -vE "Warning|WARNING|Loading|Preferring")
    echo "$(date "+%H:%M:%S") | $(basename $NEWEST .jpg) | ${RES:-ANALYSE_FEHLGESCHLAGEN}" >> "$LOG"
  fi
  REST=$((ENDE-$(date +%s)))
  [ $REST -le 0 ] && break
  sleep $(( REST<120 ? REST : 120 ))
done
echo "$(date "+%F %H:%M:%S") NACHTLAUF beendet" >> "$LOG"
