#!/bin/bash
# SessionStart-Hook fuer Claude Code im Web: installiert die npm-Abhaengigkeiten,
# damit Build (npm run build), Lint (npm run lint), Typecheck (npm run typecheck)
# und der Playwright-Smoke-Test (Skill ki-wache-smoketest) sofort laufen.
#
# Bewusst NICHT installiert: edge-agent/requirements.txt (ultralytics/torch,
# mehrere GB) — der Edge-Agent laeuft im Stall, nicht in der Web-Session;
# seine Logik laesst sich mit Bordmitteln (python3) simulieren.
set -euo pipefail

# Nur in der Remote-Umgebung (Claude Code on the web) noetig.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Chromium ist im Web-Container vorinstalliert — Playwright darf keinen
# eigenen Browser nachladen (Smoke-Test nutzt /opt/pw-browsers/chromium).
export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# npm install statt npm ci: nutzt den gecachten Container-Zustand und ist
# idempotent (zweiter Lauf ist in Sekunden fertig).
npm install --prefer-offline --no-audit --no-fund

echo "SessionStart-Hook fertig: npm-Abhaengigkeiten installiert."
