#!/usr/bin/env bash
# Richtet den Fernzugriff auf die Stallwache (Tapo) ohne Tailscale-App ein.
# Auf dem Stall-Rechner (stallwache-lela) ausfuehren:
#
#     cd ~/Die_Stallwache/bridge && bash fern-einrichten.sh
#
# Was es tut:
#   1. erzeugt (einmalig) einen geheimen Schluessel,
#   2. startet bridge/fern-proxy.py als systemd-Dienst (nur 127.0.0.1:8089),
#   3. gibt NUR diesen Proxy per `tailscale funnel` auf Port 8443 frei –
#      go2rtc selbst bleibt im Tailnet,
#   4. prueft: ohne Schluessel 403, go2rtc-API 404, HLS liefert Daten,
#   5. gibt die drei Werte fuer Vercel aus.
#
# Voraussetzung: In der Tailscale-Verwaltung sind HTTPS-Zertifikate und
# Funnel fuer dieses Geraet erlaubt (Access controls -> nodeAttrs "funnel").
set -euo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVDATEI=/etc/stallwache-fern.env
DIENST=/etc/systemd/system/stallwache-fern.service
FERN_PORT=8089
FUNNEL_PORT=8443
ME="$(id -un)"

[ -f "$HIER/fern-proxy.py" ] || { echo "fern-proxy.py fehlt neben diesem Skript." >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 fehlt." >&2; exit 1; }
command -v tailscale >/dev/null || { echo "tailscale fehlt." >&2; exit 1; }

# 1 · Schluessel (bleibt bei erneutem Aufruf derselbe)
if ! sudo test -f "$ENVDATEI"; then
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  printf 'FERN_TOKEN=%s\nFERN_PORT=%s\n' "$TOKEN" "$FERN_PORT" | sudo tee "$ENVDATEI" >/dev/null
  sudo chmod 600 "$ENVDATEI"
fi
TOKEN="$(sudo grep '^FERN_TOKEN=' "$ENVDATEI" | cut -d= -f2-)"

# 2 · Dienst
sudo tee "$DIENST" >/dev/null <<EOF
[Unit]
Description=Stallwache Fernzugriff (Absicherung vor go2rtc)
After=network-online.target

[Service]
EnvironmentFile=$ENVDATEI
ExecStart=/usr/bin/env python3 $HIER/fern-proxy.py
Restart=always
RestartSec=5
User=$ME
NoNewPrivileges=yes
ProtectSystem=strict
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now stallwache-fern.service
sleep 2
systemctl is-active --quiet stallwache-fern.service || { sudo journalctl -u stallwache-fern -n 20 --no-pager; exit 1; }

# 3 · Funnel nur fuer den Proxy
sudo tailscale funnel --bg --https="$FUNNEL_PORT" "$FERN_PORT"

# 4 · Selbsttest (lokal)
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
A="$(code "http://127.0.0.1:$FERN_PORT/api/stream.m3u8")"
B="$(code -H "x-stallwache-token: $TOKEN" "http://127.0.0.1:$FERN_PORT/api/streams")"
C="$(code --max-time 20 -H "x-stallwache-token: $TOKEN" "http://127.0.0.1:$FERN_PORT/api/stream.m3u8")"
echo "Selbsttest: ohne Schluessel=$A (soll 403) · go2rtc-API=$B (soll 404) · HLS=$C (soll 200)"
[ "$A" = 403 ] && [ "$B" = 404 ] && [ "$C" = 200 ] || { echo "Selbsttest fehlgeschlagen." >&2; exit 1; }

DNS="$(tailscale status --json | python3 -c 'import sys,json; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
cat <<EOF

Fertig. Diese drei Werte in Vercel eintragen (Settings -> Environment
Variables, Production) und danach neu deployen:

  STALLWACHE_FERN_URL           https://$DNS:$FUNNEL_PORT
  STALLWACHE_FERN_TOKEN         $TOKEN
  NEXT_PUBLIC_STALLWACHE_FERN   1

Den Schluessel nicht weitergeben. Neuer Schluessel: sudo rm $ENVDATEI und
dieses Skript erneut ausfuehren, dann in Vercel ersetzen.
EOF
