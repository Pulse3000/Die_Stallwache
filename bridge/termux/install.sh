#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
# Stallblick-Bridge – Ein-Befehl-Installation fuer Android/Termux
# ============================================================================
# Uebernimmt alle manuellen Schritte: Pakete, Architektur-Erkennung, Binaries
# (go2rtc + cloudflared), interaktive Konfiguration, Autostart.
#
# Aufruf in Termux (nach `pkg install git`):
#   git clone https://github.com/Pulse3000/Die_Stallwache.git ~/Die_Stallwache
#   bash ~/Die_Stallwache/bridge/termux/install.sh
#
# Oder komplett ohne vorheriges clone:
#   pkg install -y curl && \
#   bash <(curl -fsSL https://raw.githubusercontent.com/Pulse3000/Die_Stallwache/main/bridge/termux/install.sh)
# ============================================================================

set -e
GRUEN='\033[0;32m'; GELB='\033[1;33m'; ROT='\033[0;31m'; AUS='\033[0m'
info()  { printf "${GRUEN}==>${AUS} %s\n" "$1"; }
warn()  { printf "${GELB}!! ${AUS} %s\n" "$1"; }
fehler(){ printf "${ROT}FEHLER:${AUS} %s\n" "$1" >&2; exit 1; }

# --- 0. Termux-Umgebung pruefen ---------------------------------------------
[ -n "$PREFIX" ] && [ -d "$PREFIX" ] || fehler "Das laeuft nur in Termux (kein \$PREFIX gefunden)."

# --- 1. Repo sicherstellen ---------------------------------------------------
REPO="$HOME/Die_Stallwache"
info "Pakete installieren (git, wget, termux-tools) …"
pkg install -y git wget termux-tools >/dev/null 2>&1 || pkg install -y git wget termux-tools

if [ ! -d "$REPO/.git" ]; then
  info "Repository klonen nach $REPO …"
  git clone --depth 1 https://github.com/Pulse3000/Die_Stallwache.git "$REPO"
else
  info "Repository vorhanden – aktualisieren …"
  git -C "$REPO" pull --ff-only || warn "git pull uebersprungen (lokale Aenderungen?)"
fi

TDIR="$REPO/bridge/termux"
cd "$TDIR"

# --- 2. Architektur erkennen -------------------------------------------------
ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|arm64) GO2RTC_ARCH="arm64"; CF_ARCH="arm64" ;;
  armv7l|armv8l|arm) GO2RTC_ARCH="arm";  CF_ARCH="arm"   ;;
  x86_64|amd64) GO2RTC_ARCH="amd64"; CF_ARCH="amd64" ;;
  *) fehler "Unbekannte CPU-Architektur: $ARCH (erwartet aarch64/armv7l/x86_64)" ;;
esac
info "Architektur erkannt: $ARCH  ->  go2rtc=$GO2RTC_ARCH, cloudflared=$CF_ARCH"

# --- 3. Binaries laden -------------------------------------------------------
lade() { # $1=url  $2=zieldatei
  info "Lade $(basename "$2") …"
  wget -q --show-progress -O "$2" "$1" || fehler "Download fehlgeschlagen: $1"
  chmod +x "$2"
}
[ -x ./go2rtc ]     || lade "https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_${GO2RTC_ARCH}" ./go2rtc
[ -x ./cloudflared ]|| lade "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" ./cloudflared

# --- 4. Konfiguration (.env) interaktiv --------------------------------------
if [ -f .env ]; then
  info ".env existiert bereits – Werte werden beibehalten."
else
  info "Jetzt die Zugangsdaten eingeben (Enter uebernimmt den [Vorschlag])."
  read -r -p "  IP-Adresse der Stallwache-Kamera im WLAN: " TAPO_IP
  [ -n "$TAPO_IP" ] || fehler "Ohne Kamera-IP geht es nicht."
  read -r -p "  Kamera-Benutzer [Stallwache]: " TAPO_USER; TAPO_USER="${TAPO_USER:-Stallwache}"
  read -r -s -p "  Kamera-Passwort: " TAPO_PASS; echo
  [ -n "$TAPO_PASS" ] || fehler "Ohne Kamera-Passwort geht es nicht."
  echo
  warn "Cloudflare-Tunnel-Token aus dem Zero-Trust-Dashboard "
  warn "(Networks -> Tunnels -> Create -> Cloudflared). Public Hostname"
  warn "spaeter auf  http://localhost:1984  zeigen lassen."
  read -r -p "  Cloudflare Tunnel Token (eyJ...): " CF_TOKEN
  [ -n "$CF_TOKEN" ] || fehler "Ohne Tunnel-Token ist die Kamera nicht von aussen erreichbar."

  umask 077
  cat > .env <<EOF
TAPO_IP=$TAPO_IP
TAPO_USER=$TAPO_USER
TAPO_PASS=$TAPO_PASS
CLOUDFLARE_TUNNEL_TOKEN=$CF_TOKEN
EOF
  info ".env geschrieben (nur fuer dich lesbar)."
fi

# --- 5. Autostart via Termux:Boot -------------------------------------------
BOOT="$HOME/.termux/boot"
mkdir -p "$BOOT"
ln -sf "$TDIR/start-bridge.sh" "$BOOT/stallblick-bridge.sh"
chmod +x "$BOOT/stallblick-bridge.sh" 2>/dev/null || true
info "Autostart eingerichtet (Termux:Boot-App einmal oeffnen und Berechtigung erteilen)."

# --- 6. Direkt starten -------------------------------------------------------
info "Bridge starten …"
bash "$TDIR/start-bridge.sh"

echo
info "Fertig. Pruefen mit:"
echo "    tail -f $TDIR/logs/go2rtc.log $TDIR/logs/cloudflared.log"
echo
warn "Letzter Schritt im Cloudflare-Dashboard: Public Hostname auf"
warn "http://localhost:1984 zeigen lassen. Danach die Tunnel-Adresse an"
warn "die Webapp melden (NEXT_PUBLIC_BRIDGE_URL in Vercel)."
