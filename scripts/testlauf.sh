#!/bin/bash
# Testlauf: alle 10 Min ein Bild mit Analyse (bis 17:30 Uhr)
LOG="/home/stallwache/Die_Stallwache/logs/testlauf.log"

ENDE=$(date -d "today 17:30" +%s)
echo "$(date "+%H:%M:%S") TESTLAUF gestartet (bis 17:30)" >> "$LOG"
while [ $(date +%s) -lt $ENDE ]; do
  NEWEST=$(ls -t ~/Die_Stallwache/edge-agent/aufnahmen/*.jpg 2>/dev/null | head -1)
  [ -z "$NEWEST" ] && { echo "$(date "+%H:%M:%S") Kein Bild gefunden" >> "$LOG"; sleep 600; continue; }
  docker cp "$NEWEST" kuhwatch-stallwache:/tmp/test.jpg >/dev/null 2>&1
  RES=$(docker exec kuhwatch-stallwache python -c "
from ultralytics import YOLO
m = YOLO(\"/kuhwatch/models/yolov8n.onnx\", task=\"detect\")
r = m.predict(\"/tmp/test.jpg\", imgsz=640, conf=0.25, classes=[0,5,6,17,18,19], verbose=False)[0]
d={}
for v,c in zip(r.boxes.conf, r.boxes.cls):
    n=m.names[int(c)]; d[n]=d.get(n,0)+1
print(\", \".join(f\"{k}: {v}\" for k,v in d.items()) or \"keine Objekte\")
" 2>/dev/null | grep -vE "Warning|WARNING|Loading|Preferring")
  echo "$(date "+%H:%M:%S") | $(basename $NEWEST .jpg) | $RES" >> "$LOG"
  REST=$((ENDE-$(date +%s)))
  [ $REST -le 0 ] && break
  sleep $(( REST<600 ? REST : 600 ))
done
echo "$(date "+%H:%M:%S") TESTLAUF beendet" >> "$LOG"
