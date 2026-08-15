#!/data/data/com.termux/files/usr/bin/bash
# Startet die Stallblick-Bridge (go2rtc + Cloudflare Tunnel) unter Termux.
#
# Erwartete Ablage: dieses Skript liegt in Die_Stallwache/bridge/termux/,
# die Binaries (go2rtc, cloudflared) werden in denselben Ordner geladen
# (siehe README.md), die go2rtc-Konfiguration wird aus bridge/go2rtc.yaml
# im selben Repo verwendet - keine zweite Kopie noetig.
#
# Manueller Start:  bash start-bridge.sh
# Autostart:         nach ~/.termux/boot/ kopieren (siehe README.md)

set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Fehler: .env fehlt. cp .env.example .env und Werte eintragen." >&2
  exit 1
fi
set -a
source .env
set +a

if [ ! -x ./go2rtc ] || [ ! -x ./cloudflared ]; then
  echo "Fehler: go2rtc und/oder cloudflared fehlen oder sind nicht ausfuehrbar." >&2
  echo "Siehe README.md, Schritt 3 (Binaries herunterladen)." >&2
  exit 1
fi

# Verhindert, dass Android den Prozess im Ruhezustand (Doze) einfriert.
termux-wake-lock || echo "Hinweis: termux-wake-lock nicht verfuegbar (pkg install termux-tools)."

mkdir -p logs

echo "Starte go2rtc …"
nohup ./go2rtc -config ../go2rtc.yaml > logs/go2rtc.log 2>&1 &
disown
echo "go2rtc laeuft (PID $!) – Log: logs/go2rtc.log"

echo "Starte Cloudflare Tunnel …"
nohup ./cloudflared tunnel --no-autoupdate run --token "$CLOUDFLARE_TUNNEL_TOKEN" > logs/cloudflared.log 2>&1 &
disown
echo "cloudflared laeuft (PID $!) – Log: logs/cloudflared.log"

echo ""
echo "Fertig. Pruefen mit: tail -f logs/go2rtc.log logs/cloudflared.log"
