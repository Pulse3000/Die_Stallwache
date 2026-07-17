#!/usr/bin/env bash
# ============================================================================
# Stallblick Edge-Agent – Ein-Befehl-Setup fuer den Stall-Rechner
# ============================================================================
# Uebernimmt alle manuellen Schritte aus dem README: venv, Pakete,
# gefuehrte Konfiguration (Bridge, Telegram-Bot, Dashboard-Token) und
# optional den systemd-Dauerbetrieb.
#
# Aufruf auf dem Stall-Rechner (Linux, Python 3.10+):
#   git clone https://github.com/Pulse3000/Die_Stallwache.git
#   bash Die_Stallwache/edge-agent/setup.sh
#
# Idempotent: vorhandenes venv/config.yaml wird erkannt und beibehalten.
# ============================================================================

set -euo pipefail
GRUEN='\033[0;32m'; GELB='\033[1;33m'; ROT='\033[0;31m'; AUS='\033[0m'
info()  { printf "${GRUEN}==>${AUS} %s\n" "$1"; }
warn()  { printf "${GELB}!! ${AUS} %s\n" "$1"; }
fehler(){ printf "${ROT}FEHLER:${AUS} %s\n" "$1" >&2; exit 1; }

HIER="$(cd "$(dirname "$0")" && pwd)"
cd "$HIER"

# --- 1. Python pruefen -------------------------------------------------------
command -v python3 >/dev/null || fehler "python3 fehlt (Debian/Ubuntu: sudo apt install python3 python3-venv)"
python3 - <<'EOF' || fehler "Python 3.10 oder neuer noetig."
import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)
EOF

# --- 2. venv + Pakete --------------------------------------------------------
# STALLBLICK_SETUP_OHNE_INSTALL=1 ueberspringt diesen Block (nur fuer Tests).
if [ "${STALLBLICK_SETUP_OHNE_INSTALL:-0}" != "1" ]; then
  if [ ! -d venv ]; then
    info "Virtuelle Umgebung anlegen …"
    python3 -m venv venv || fehler "venv fehlgeschlagen (sudo apt install python3-venv)"
  fi
  # shellcheck disable=SC1091
  . venv/bin/activate
  pip install --quiet --upgrade pip
  info "Basis-Pakete installieren (Silent Mode: sammeln von Trainingsbildern) …"
  pip install --quiet "opencv-python>=4.9,<5" "numpy>=1.26,<3" "requests>=2.31,<3" "PyYAML>=6.0,<7"
  echo
  warn "Der Analyse-Modus (YOLO) braucht zusaetzlich ultralytics/torch (mehrere GB)."
  warn "Er wird erst nach dem Modell-Training relevant (Skill modell-training)."
  read -r -p "  Analyse-Pakete jetzt mitinstallieren? [j/N]: " ANALYSE
  if [ "${ANALYSE:-n}" = "j" ] || [ "${ANALYSE:-n}" = "J" ]; then
    info "Installiere vollstaendige requirements.txt (dauert) …"
    pip install -r requirements.txt
  else
    info "Uebersprungen – spaeter nachholbar mit:  venv/bin/pip install -r requirements.txt"
  fi
fi

# --- 3. Gefuehrte Konfiguration ----------------------------------------------
if [ -f config.yaml ]; then
  info "config.yaml existiert bereits – Werte werden beibehalten."
else
  info "Jetzt die Konfiguration (Enter uebernimmt den [Vorschlag])."
  warn "Videoquelle: 1 = Cloud ohne Bridge (Kamera haengt in der Tuya-Cloud,"
  warn "z. B. Futterwache — sofort startklar) | 2 = Bridge im Stall-LAN (RTSP)"
  read -r -p "  Quelle [1]: " QUELLE
  QUELLE="${QUELLE:-1}"
  if [ "$QUELLE" = "1" ]; then
    read -r -p "  Webapp-Adresse [https://die-stallwache.vercel.app]: " APP_URL
    APP_URL="${APP_URL:-https://die-stallwache.vercel.app}"
    read -r -p "  Kamera-Name (futterwache|stallbox) [futterwache]: " KAMERA
    KAMERA="${KAMERA:-futterwache}"
    read -r -s -p "  Webapp-Passwort (STALLBLICK_PASSWORT): " APP_PASS; echo
    BRIDGE_IP=""
  else
    read -r -p "  IP des Bridge-Rechners im Stall-LAN [192.168.178.50]: " BRIDGE_IP
    BRIDGE_IP="${BRIDGE_IP:-192.168.178.50}"
    read -r -p "  Kamera-Name (stallwache|futterwache) [stallwache]: " KAMERA
    KAMERA="${KAMERA:-stallwache}"
    APP_URL=""; APP_PASS=""
  fi
  echo
  warn "Telegram-Bot: in Telegram @BotFather oeffnen -> /newbot -> Token kopieren;"
  warn "danach @userinfobot oeffnen -> Start -> numerische Chat-ID kopieren."
  warn "Beides leer lassen = vorerst ohne Telegram (nur Dashboard/Logs)."
  read -r -p "  Telegram-Bot-Token: " TG_TOKEN
  read -r -p "  Telegram-Chat-ID: " TG_CHAT
  echo
  warn "Dashboard-Token = EDGE_INGEST_TOKEN aus Vercel (leer = kein Dashboard)."
  read -r -p "  Dashboard-Token: " DB_TOKEN

  umask 077
  BRIDGE_IP="$BRIDGE_IP" KAMERA="$KAMERA" APP_URL="${APP_URL:-}" \
  APP_PASS="${APP_PASS:-}" TG_TOKEN="$TG_TOKEN" \
  TG_CHAT="$TG_CHAT" DB_TOKEN="$DB_TOKEN" python3 - <<'EOF'
import os, yaml
with open("config.example.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
ip, kamera = os.environ["BRIDGE_IP"], os.environ["KAMERA"]
app_url = os.environ["APP_URL"]
if app_url:
    # Cloud-Quelle ohne Bridge: Agent holt die HLS-URL selbst.
    cfg["stream"]["url"] = ""
    cfg["stream"]["fallback_snapshot_url"] = ""
    cfg["stream"]["app_url"] = app_url
    cfg["stream"]["quelle_api"] = f"/api/{kamera}/stream"
    cfg["stream"]["app_passwort"] = os.environ["APP_PASS"]
else:
    cfg["stream"]["url"] = f"rtsp://{ip}:8554/{kamera}"
    cfg["stream"]["fallback_snapshot_url"] = f"http://{ip}:1984/api/frame.jpeg?src={kamera}"
cfg["stream"]["kamera"] = kamera
cfg["telegram"]["token"] = os.environ["TG_TOKEN"]
cfg["telegram"]["chat_id"] = os.environ["TG_CHAT"]
cfg["dashboard"]["token"] = os.environ["DB_TOKEN"]
with open("config.yaml", "w", encoding="utf-8") as f:
    yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
print("config.yaml geschrieben (nur fuer dich lesbar).")
EOF
fi

# --- 4. Dauerbetrieb via systemd (optional) -----------------------------------
if command -v systemctl >/dev/null && [ "${STALLBLICK_SETUP_OHNE_INSTALL:-0}" != "1" ]; then
  read -r -p "  Dauerbetrieb einrichten (systemd, startet nach Reboot neu)? [j/N]: " SYSD
  if [ "${SYSD:-n}" = "j" ] || [ "${SYSD:-n}" = "J" ]; then
    UNIT="/etc/systemd/system/stallblick-agent.service"
    sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=Stallblick Edge-Agent
After=network-online.target

[Service]
WorkingDirectory=$HIER
ExecStart=$HIER/venv/bin/python3 $HIER/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable --now stallblick-agent
    info "systemd-Dienst laeuft:  sudo systemctl status stallblick-agent"
  fi
fi

# --- 5. Fertig -----------------------------------------------------------------
echo
info "Setup fertig. Manuell starten mit:"
echo "    cd $HIER && venv/bin/python3 main.py"
echo
info "Ohne Modell laeuft der Agent im Silent Mode und sammelt alle 2 Minuten"
info "ein Trainingsbild nach ./aufnahmen – genau richtig fuer den Start"
info "(weiter geht es mit dem Skill modell-training)."
