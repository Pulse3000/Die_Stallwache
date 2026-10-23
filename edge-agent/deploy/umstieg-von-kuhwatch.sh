#!/usr/bin/env bash
# ============================================================================
# Umstieg stallwache-lela: kuhwatch -> Edge-Agent (ein Agent statt zwei)
# docs/ein-edge-agent-spezifikation.md, U5
# ============================================================================
#   bash Die_Stallwache/edge-agent/deploy/umstieg-von-kuhwatch.sh            # umsteigen
#   bash Die_Stallwache/edge-agent/deploy/umstieg-von-kuhwatch.sh --trocken  # nur zeigen
#   Optionen: --kuhwatch <Pfad> (Default ~/kuhwatch bzw. /home/stallwache/kuhwatch)
#             --ohne-tempguard (Temperaturwaechter nicht anfassen)
#   Optional: DASHBOARD_TOKEN=<EDGE_INGEST_TOKEN> vor den Aufruf setzen.
#
# Was passiert:
#   1. Agent-Image bauen (Silent Mode)
#   2. config.yaml aus kuhwatch/.env erzeugen (erste Kamera, Telegram; 600)
#   3. kuhwatch-Container stoppen, NICHT loeschen (restart=no)
#   4. Edge-Agent starten (docker compose)
#   5. Temperaturwaechter auf den neuen Container umstellen (sudo)
# Der Rueckweg steht am Ende der Ausgabe.
# ============================================================================
set -euo pipefail
GRUEN='\033[0;32m'; GELB='\033[1;33m'; ROT='\033[0;31m'; AUS='\033[0m'
info()  { printf "${GRUEN}==>${AUS} %s\n" "$1"; }
warn()  { printf "${GELB}!! ${AUS} %s\n" "$1"; }
fehler(){ printf "${ROT}FEHLER:${AUS} %s\n" "$1" >&2; exit 1; }

HIER="$(cd "$(dirname "$0")/.." && pwd)"          # edge-agent/
KUHWATCH=""
TROCKEN=0
TEMPGUARD=1
KW_CONTAINER=kuhwatch-stallwache
while [ $# -gt 0 ]; do
  case "$1" in
    --trocken) TROCKEN=1 ;;
    --ohne-tempguard) TEMPGUARD=0 ;;
    --kuhwatch) KUHWATCH="$2"; shift ;;
    *) fehler "Unbekannte Option: $1" ;;
  esac
  shift
done
if [ -z "$KUHWATCH" ]; then
  for k in "$HOME/kuhwatch" /home/stallwache/kuhwatch; do
    [ -f "$k/.env" ] && KUHWATCH="$k" && break
  done
fi
[ -n "$KUHWATCH" ] && [ -f "$KUHWATCH/.env" ] || fehler "kuhwatch/.env nicht gefunden (--kuhwatch <Pfad>)."
command -v docker >/dev/null || fehler "docker fehlt."

env_wert() {  # Wert aus kuhwatch/.env wie kuhwatch_env_nach_config.py: ohne CR,
              # Leerraum und umschliessende Anfuehrungszeichen (Befund qa-waechter)
  grep "^$1=" "$KUHWATCH/.env" | head -1 | cut -d= -f2- | tr -d '\r' \
    | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/"
}
fuehre() {  # Befehl ausfuehren oder im Trockenlauf nur zeigen
  if [ "$TROCKEN" = "1" ]; then printf "   [trocken] %s\n" "$*"; else "$@"; fi
}
[ "$TROCKEN" = "1" ] && warn "Trockenlauf: Es wird nichts gestoppt, gestartet oder installiert."

# --- 1. Image -----------------------------------------------------------------
info "Baue das Agent-Image (Silent Mode) …"
docker compose -f "$HIER/docker-compose.yml" build --quiet

# --- 2. config.yaml -----------------------------------------------------------
DATEN="$HIER/daten/stallwache"
if [ "$TROCKEN" = "1" ]; then
  ZIEL="$(mktemp -d)"
  trap 'rm -rf "$ZIEL"' EXIT
else
  ZIEL="$DATEN"
  mkdir -p "$ZIEL"
fi
if [ "$TROCKEN" = "0" ] && [ -f "$ZIEL/config.yaml" ]; then
  info "daten/stallwache/config.yaml existiert bereits – bleibt unveraendert."
else
  info "Erzeuge config.yaml aus $KUHWATCH/.env:"
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e DASHBOARD_TOKEN \
    -v "$KUHWATCH/.env:/kuhwatch.env:ro" \
    -v "$HIER/deploy/kuhwatch_env_nach_config.py:/umstieg.py:ro" \
    -v "$ZIEL:/ziel" \
    stallwache-agent:0 python /umstieg.py /kuhwatch.env /app/config.example.yaml /ziel/config.yaml
  [ "$TROCKEN" = "1" ] && info "Trockenlauf: config.yaml geprueft ($(stat -c %a "$ZIEL/config.yaml")), nicht abgelegt."
fi

# --- 3. kuhwatch stoppen (nicht loeschen) ------------------------------------
if docker ps -a --format '{{.Names}}' | grep -qx "$KW_CONTAINER"; then
  info "Stoppe $KW_CONTAINER (bleibt fuer den Rueckweg erhalten) …"
  fuehre docker update --restart=no "$KW_CONTAINER"
  fuehre docker stop "$KW_CONTAINER"
else
  warn "Container $KW_CONTAINER nicht gefunden – nichts zu stoppen."
fi

# --- 4. Edge-Agent starten ----------------------------------------------------
info "Starte den Edge-Agenten …"
fuehre docker compose -f "$HIER/docker-compose.yml" up -d

# --- 5. Temperaturwaechter ----------------------------------------------------
if [ "$TEMPGUARD" = "0" ]; then
  warn "Temperaturwaechter nicht angefasst (--ohne-tempguard)."
elif command -v systemctl >/dev/null; then
  info "Stelle den Temperaturwaechter um (sudo) …"
  TG_TOKEN=$(env_wert TELEGRAM_BOT_TOKEN)
  TG_CHAT=$(env_wert TELEGRAM_CHAT_ID)
  fuehre sudo install -m 755 "$HIER/deploy/tempguard/stallwache-tempguard.sh" /usr/local/bin/
  fuehre sudo install -m 644 "$HIER/deploy/tempguard/stallwache-tempguard.service" /etc/systemd/system/
  fuehre sudo install -d -m 700 /etc/stallwache
  if [ "$TROCKEN" = "1" ]; then
    printf "   [trocken] /etc/stallwache/tempguard.env schreiben (Telegram aus kuhwatch/.env, 600)\n"
  else
    printf 'TELEGRAM_BOT_TOKEN=%s\nTELEGRAM_CHAT_ID=%s\nCONTAINER_FILTER=stallwache-agent\n' \
      "$TG_TOKEN" "$TG_CHAT" | sudo install -m 600 /dev/stdin /etc/stallwache/tempguard.env
  fi
  if systemctl cat kuhwatch-tempguard.service >/dev/null 2>&1; then
    fuehre sudo systemctl disable --now kuhwatch-tempguard.service
  fi
  fuehre sudo systemctl daemon-reload
  fuehre sudo systemctl enable --now stallwache-tempguard.service
else
  warn "Kein systemd – Temperaturwaechter bitte von Hand einrichten (deploy/tempguard/)."
fi

echo
if [ "$TROCKEN" = "1" ]; then
  info "Trockenlauf beendet. Ohne --trocken aufrufen, um umzusteigen."
  exit 0
fi
info "Fertig. Pruefen:  docker logs -f stallwache-agent-stallwache"
info "Trainingsbilder:  $DATEN/aufnahmen/"
echo
warn "Rueckweg zu kuhwatch:"
echo "   docker compose -f $HIER/docker-compose.yml down"
echo "   docker update --restart=unless-stopped $KW_CONTAINER && docker start $KW_CONTAINER"
echo "   sudo systemctl disable --now stallwache-tempguard.service"
echo "   sudo systemctl enable --now kuhwatch-tempguard.service"
