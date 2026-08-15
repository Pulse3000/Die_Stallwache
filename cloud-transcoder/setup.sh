#!/usr/bin/env bash
# Ein-Klick-Setup fuer den Cloud-Transcoder auf einem frischen Ubuntu-VPS.
# Installiert Docker, oeffnet die noetigen Ports und startet go2rtc + Caddy.
#
#   ssh root@DEIN_VPS
#   git clone <dieses-repo> && cd Die_Stallwache/cloud-transcoder
#   cp .env.example .env && nano .env      # Werte eintragen
#   sudo bash setup.sh
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "FEHLER: .env fehlt. Erst:  cp .env.example .env  und ausfuellen."
  exit 1
fi

echo "==> Docker installieren (falls noetig)…"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

echo "==> Firewall: 80/443 (HTTPS) und 8555 (WebRTC) freigeben…"
if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp   || true
  ufw allow 443/tcp  || true
  ufw allow 8555/tcp || true
  ufw allow 8555/udp || true
fi

echo "==> Container starten…"
docker compose up -d
sleep 3
docker compose ps

cat <<'EOF'

============================================================
Fertig. Naechste Schritte:

1) DNS: A-Record von STREAM_DOMAIN auf die VPS-IP zeigen lassen
   (falls noch nicht geschehen). Caddy holt dann automatisch HTTPS.

2) Router (zu Hause): Portfreigabe
   externer Port CAM_RTSP_PORT  ->  192.168.178.117 : 554 (TCP)
   Sicherheit: Quelle moeglichst auf die VPS-IP einschraenken!

3) Test:  https://STREAM_DOMAIN/  -> go2rtc-Weboberflaeche,
   Stream "stallwache" muss ein Bild zeigen.

4) Webapp (Vercel): Env-Variable setzen
   NEXT_PUBLIC_GO2RTC_URL = https://STREAM_DOMAIN
   -> danach laeuft der Livestream auf die-stallwache.vercel.app
============================================================
EOF
