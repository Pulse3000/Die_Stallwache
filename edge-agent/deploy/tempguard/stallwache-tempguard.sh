#!/bin/sh
# Temperaturwaechter fuer den Stall-Rechner (aus kuhwatch, docs/ein-edge-agent-
# spezifikation.md U4). Grenzwerte unveraendert:
#   WARN 80 °C -> Telegram-Warnung
#   LIMIT 85 °C -> alle Agent-Container pausieren, Takt auf 1,6 GHz, Telegram
#   RESUME 75 °C -> Container fortsetzen, Takt zurueck, Entwarnung
# Konfiguration: /etc/stallwache/tempguard.env (Rechte 600)
#   TELEGRAM_BOT_TOKEN=...   TELEGRAM_CHAT_ID=...
#   CONTAINER_FILTER=stallwache-agent   (Teil des Containernamens)
WARN=80000; LIMIT=85000; RESUME=75000
EMERGENCY_FREQ=1600000; NORMAL_FREQ=2600000
ENVF=${TEMPGUARD_ENV:-/etc/stallwache/tempguard.env}
LOG=/var/log/stallwache-tempguard.log
wert() { grep "^$1=" "$ENVF" 2>/dev/null | head -1 | cut -d= -f2-; }
TOKEN=$(wert TELEGRAM_BOT_TOKEN)
CHAT=$(wert TELEGRAM_CHAT_ID)
FILTER=$(wert CONTAINER_FILTER); FILTER=${FILTER:-stallwache-agent}
log() { echo "$(date "+%F %T") $1" >> "$LOG"; }
notify() { [ -n "$TOKEN" ] && [ -n "$CHAT" ] && curl -s -m 10 "https://api.telegram.org/bot$TOKEN/sendMessage" --data-urlencode "chat_id=$CHAT" --data-urlencode "text=$1" >/dev/null 2>&1; }
pause_alle() { docker ps -q --filter "name=$FILTER" --filter status=running | xargs -r docker pause >/dev/null 2>&1; }
fortsetzen_alle() { docker ps -q --filter "name=$FILTER" --filter status=paused | xargs -r docker unpause >/dev/null 2>&1; }
log "tempguard gestartet (Limit ${LIMIT}mC, Container *$FILTER*)"
PAUSED=0; WARNED=0
while true; do
  T=""
  for d in /sys/class/hwmon/hwmon*; do
    [ "$(cat "$d/name" 2>/dev/null)" = "k10temp" ] && T=$(cat "$d/temp1_input" 2>/dev/null)
  done
  if [ -n "$T" ]; then
    C=$((T/1000))
    if [ "$T" -ge "$LIMIT" ] && [ "$PAUSED" -eq 0 ]; then
      for c in /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq; do echo $EMERGENCY_FREQ > "$c" 2>/dev/null; done
      pause_alle
      log "KRITISCH ${T}mC -> Agent pausiert, Takt 1.6GHz"
      notify "STALLWACHE KRITISCH: CPU bei $C°C. KI-Wache pausiert + Takt gedeckelt. Entwarnung folgt bei 75°C."
      PAUSED=1
    elif [ "$T" -le "$RESUME" ] && [ "$PAUSED" -eq 1 ]; then
      for c in /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq; do echo $NORMAL_FREQ > "$c" 2>/dev/null; done
      fortsetzen_alle
      log "ENTWARNUNG ${T}mC -> Agent laeuft wieder"
      notify "STALLWACHE OK: CPU auf $C°C abgekuehlt. KI-Wache laeuft wieder."
      PAUSED=0; WARNED=0
    elif [ "$T" -ge "$WARN" ] && [ "$WARNED" -eq 0 ] && [ "$PAUSED" -eq 0 ]; then
      log "WARNUNG ${T}mC"
      notify "STALLWACHE WARNUNG: CPU bei $C°C (Grenze 85°C)."
      WARNED=1
    elif [ "$T" -lt "$RESUME" ]; then
      WARNED=0
    fi
  fi
  sleep 15
done
