#!/data/data/com.termux/files/usr/bin/bash
# Startet den Stallblick-Edge-Agent unter Termux (Silent Mode oder Analyse-
# Modus, je nach config.yaml).
#
# Erwartete Ablage: dieses Skript liegt in edge-agent/termux/, config.yaml
# und die venv liegen eine Ebene hoeher in edge-agent/ (siehe README.md).
#
# Manueller Start:  bash start-agent.sh
# Autostart:         nach ~/.termux/boot/ kopieren (siehe README.md)

set -e
cd "$(dirname "$0")/.."

if [ ! -f config.yaml ]; then
  echo "Fehler: config.yaml fehlt. cp config.example.yaml config.yaml und Werte eintragen." >&2
  exit 1
fi

if [ ! -x venv/bin/python3 ]; then
  echo "Fehler: venv fehlt. Siehe termux/README.md, Schritt 3 (Python-Umgebung einrichten)." >&2
  exit 1
fi

# Verhindert, dass Android den Prozess im Ruhezustand (Doze) einfriert.
termux-wake-lock || echo "Hinweis: termux-wake-lock nicht verfuegbar (pkg install termux-tools)."

mkdir -p termux/logs

echo "Starte Edge-Agent …"
nohup ./venv/bin/python3 main.py > termux/logs/agent.log 2>&1 &
disown
echo "Edge-Agent laeuft (PID $!) – Log: termux/logs/agent.log"
