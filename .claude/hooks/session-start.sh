#!/bin/bash
# SessionStart-Hook fuer Claude Code im Web: installiert die npm-Abhaengigkeiten,
# damit `npm run pruefen` (Typecheck, Lint, Tests, Geruest, Build) und der
# Playwright-Smoke-Test (Skill ki-wache-smoketest) sofort laufen.
#
# Registriert in .claude/settings.json (hooks.SessionStart). Ohne diesen
# Eintrag laeuft das Skript nie – dann startet jede Sitzung ohne node_modules.
#
# Bewusst NICHT installiert: edge-agent/requirements.txt (ultralytics/torch,
# mehrere GB) — der Edge-Agent laeuft im Stall, nicht in der Web-Session;
# seine Logiktests sind pures Python und brauchen keine Pakete.
set -euo pipefail

# Nur in der Remote-Umgebung (Claude Code on the web) noetig.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Chromium ist im Web-Container vorinstalliert — Playwright darf keinen
# eigenen Browser nachladen (Smoke-Test nutzt /opt/pw-browsers/chromium).
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Der Hook laeuft bei jedem Start, Fortsetzen und Verdichten einer Sitzung.
# Installiert wird nur, wenn sich seit der letzten erfolgreichen Installation
# etwas geaendert hat, das die Pakete bestimmt. Die Pruefsummen liegen in
# node_modules: Verschwinden die Pakete, verschwindet die Datei mit.
hashes=node_modules/.session-start.sha256
if ! sha256sum --check --status "$hashes" 2>/dev/null; then
  # Alte Pruefsummen zuerst loeschen: Eine gescheiterte Installation laeuft
  # beim naechsten Start erneut.
  rm -f "$hashes"

  # npm install statt npm ci: nutzt den gecachten Container-Zustand.
  npm install --prefer-offline --no-audit --no-fund

  sha256sum .claude/hooks/session-start.sh package.json package-lock.json \
    > "$hashes" || rm -f "$hashes"
  echo "SessionStart-Hook: npm-Abhaengigkeiten installiert."
else
  echo "SessionStart-Hook: npm-Abhaengigkeiten aktuell, nichts zu tun."
fi
