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
#      Manifest, HTTPS am Geraet antwortet, Name ist oeffentlich aufloesbar,
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

# Fehler hier duerfen die Ausgabe von A/B/C nicht verschlucken (leerer Name
# wird unten gemeldet statt mit Python-Traceback abzubrechen).
DNS="$(tailscale status --json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"

# HTTPS am Geraet ueber den Tailscale-Namen (ohne Schluessel: 403 vom Proxy).
# Belegt Zertifikat und Serve-Konfiguration. NICHT den Weg von aussen: Mit
# MagicDNS (Linux-Standard) geht der Abruf direkt an die 100.x-Adresse statt
# ueber das Funnel-Relay. Den Weg von aussen belegt erst Kriterium 5
# (Mobilfunk ohne Tailscale) bzw. die App.
D="kein-Name"; D_RC=0
if [ -n "$DNS" ]; then
  D="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "https://$DNS:$FUNNEL_PORT/api/stream.m3u8")" || D_RC=$?
fi

# Oeffentlicher DNS-Eintrag: Tailscale legt ihn erst an, wenn der Funnel beim
# Kontrollserver registriert ist (Befund 19.10.: NXDOMAIN trotz "Funnel on").
# Nach dem ersten Einrichten kann das einige Minuten dauern -> nur Warnung.
E="?"
if [ -n "$DNS" ]; then
  E="$(curl -s --max-time 10 "https://dns.google/resolve?name=$DNS&type=A" \
    | python3 -c 'import sys,json; print("ja" if json.load(sys.stdin).get("Status") == 0 else "nein")' 2>/dev/null || echo "?")"
fi

echo "Selbsttest: ohne Schluessel=$A (soll 403) · go2rtc-API=$B (soll 404) · HLS=$C (soll 200) · HTTPS=$D (soll 403) · oeffentlicher Name=$E (soll ja)"
if [ "$C" = "200-leer" ]; then
  echo "go2rtc liefert kein Bild: TAPO_IP und Kamerakonto in bridge/.env pruefen (docker logs stallwache-go2rtc)." >&2
fi
if [ "$D" = "kein-Name" ]; then
  echo "Tailscale-Name nicht ermittelbar: 'tailscale status' pruefen (angemeldet, MagicDNS an?)." >&2
elif [ "$D" != 403 ]; then
  # curl-Fehlercode statt Raten: 6 = Name, 28 = Zeit, 35/60 = TLS/Zertifikat.
  case "$D_RC" in
    6)     echo "HTTPS: Name $DNS nicht aufloesbar (curl 6)." >&2 ;;
    28)    echo "HTTPS: Zeitueberschreitung (curl 28) – beim ersten Lauf holt Tailscale das Zertifikat erst; Skript in 1–2 min erneut ausfuehren." >&2 ;;
    35|60) echo "HTTPS: TLS scheitert (curl $D_RC) – in der Tailscale-Verwaltung DNS -> HTTPS Certificates einschalten, dann Skript erneut ausfuehren." >&2 ;;
    0)     echo "HTTPS: unerwartete Antwort $D (soll 403 vom Proxy)." >&2 ;;
    *)     echo "HTTPS scheitert (curl $D_RC)." >&2 ;;
  esac
fi
if [ "$E" = "nein" ]; then
  echo "Warnung: $DNS ist oeffentlich (noch) nicht aufloesbar – der Funnel ist beim Tailscale-Kontrollserver nicht registriert. Nach dem ersten Einrichten bis zu 10 min warten; bleibt es so: 'sudo tailscale funnel reset' und Skript erneut (docs/fernzugriff-spezifikation.md §5.2)." >&2
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
