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
#   4. prueft: ohne Schluessel 403, go2rtc-API 404, HLS liefert ein
#      Manifest, HTTPS ueber den Tailscale-Namen antwortet,
#   5. gibt die drei Werte fuer Vercel aus.
#
# Voraussetzung: In der Tailscale-Verwaltung sind HTTPS-Zertifikate (DNS ->
# HTTPS Certificates) und Funnel fuer dieses Geraet erlaubt (Access controls
# -> nodeAttrs "funnel").
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
  # Erst leer mit 600 anlegen, dann schreiben — nie kurz fuer alle lesbar.
  sudo install -m 600 /dev/null "$ENVDATEI"
  printf 'FERN_TOKEN=%s\nFERN_PORT=%s\n' "$TOKEN" "$FERN_PORT" | sudo tee "$ENVDATEI" >/dev/null
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
sudo systemctl enable stallwache-fern.service
# restart statt `enable --now`: Ein schon laufender Proxy liest einen neuen
# Schluessel aus $ENVDATEI sonst erst beim naechsten Neustart (Selbsttest 403).
sudo systemctl restart stallwache-fern.service
sleep 2
systemctl is-active --quiet stallwache-fern.service || { sudo journalctl -u stallwache-fern -n 20 --no-pager; exit 1; }

# 3 · Funnel nur fuer den Proxy
sudo tailscale funnel --bg --https="$FUNNEL_PORT" "$FERN_PORT"

# 4 · Selbsttest
# `|| true`: Bei Zeitueberschreitung oder TLS-Fehler endet curl mit Fehlercode;
# unter `set -e` brach das Skript dann ohne Selbsttest-Zeile ab. So bleibt
# der Status "000" und die Auswertung unten greift.
code() { curl -s -o /dev/null -w '%{http_code}' "$@" || true; }
A="$(code "http://127.0.0.1:$FERN_PORT/api/stream.m3u8")"
B="$(code -H "x-stallwache-token: $TOKEN" "http://127.0.0.1:$FERN_PORT/api/streams")"
# go2rtc antwortet auch dann mit 200, wenn es die Kamera nicht erreicht –
# nur mit leerem Manifest. Deshalb zaehlt erst ein Manifest (#EXTM3U).
MANIFEST="$(mktemp)"
trap 'rm -f "$MANIFEST"' EXIT
C="$(curl -s -o "$MANIFEST" -w '%{http_code}' --max-time 20 -H "x-stallwache-token: $TOKEN" "http://127.0.0.1:$FERN_PORT/api/stream.m3u8" || true)"
if [ "$C" = 200 ] && ! head -c 7 "$MANIFEST" | grep -q '#EXTM3U'; then C="200-leer"; fi

DNS="$(tailscale status --json | python3 -c 'import sys,json; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))')"
# HTTPS ueber den Tailscale-Namen, wie die Webapp ihn ruft (ohne Schluessel:
# 403 vom Proxy). "000" = TLS scheitert, meist HTTPS-Zertifikate nicht erlaubt.
D="$(code --max-time 30 "https://$DNS:$FUNNEL_PORT/api/stream.m3u8")"

echo "Selbsttest: ohne Schluessel=$A (soll 403) · go2rtc-API=$B (soll 404) · HLS=$C (soll 200) · HTTPS=$D (soll 403)"
if [ "$C" = "200-leer" ]; then
  echo "go2rtc liefert kein Bild: TAPO_IP und Kamerakonto in bridge/.env pruefen (docker logs stallwache-go2rtc)." >&2
fi
if [ "$D" = 000 ]; then
  echo "HTTPS scheitert: in der Tailscale-Verwaltung DNS -> HTTPS Certificates einschalten, dann 'sudo tailscale cert $DNS'." >&2
fi
[ "$A" = 403 ] && [ "$B" = 404 ] && [ "$C" = 200 ] && [ "$D" = 403 ] || { echo "Selbsttest fehlgeschlagen." >&2; exit 1; }
cat <<EOF

Fertig. Diese drei Werte in Vercel eintragen (Settings -> Environment
Variables, Production) und danach neu deployen:

  STALLWACHE_FERN_URL           https://$DNS:$FUNNEL_PORT
  STALLWACHE_FERN_TOKEN         $TOKEN
  NEXT_PUBLIC_STALLWACHE_FERN   1

Die URL genau so, MIT :$FUNNEL_PORT – ohne Port landet die Anfrage auf 443
und bricht ab. Den Schluessel nicht weitergeben, auch nicht in Chats. Neuer Schluessel: sudo rm $ENVDATEI und
dieses Skript erneut ausfuehren, dann in Vercel ersetzen.
EOF
