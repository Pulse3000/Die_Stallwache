#!/usr/bin/env python3
"""Erzeugt die config.yaml des Edge-Agenten aus der .env von kuhwatch.

Teil des Umstiegs (umstieg-von-kuhwatch.sh, docs/ein-edge-agent-
spezifikation.md U5). Laeuft im Agent-Image (PyYAML vorhanden):

  kuhwatch_env_nach_config.py <kuhwatch/.env> <config.example.yaml> <ziel/config.yaml>

Uebernommen: erste Kamera aus RTSP_URLS (als ``stallwache``), Telegram-Bot.
Silent Mode (modell.pfad leer), bis ein eigenes Modell die Abnahme besteht.
Optional DASHBOARD_TOKEN aus der Umgebung (= EDGE_INGEST_TOKEN in Vercel).
Zugangsdaten erscheinen nie in der Ausgabe; die Datei bekommt Rechte 600.
"""

import os
import sys
import urllib.parse

import yaml


def lies_env(pfad: str) -> dict:
    werte = {}
    with open(pfad, encoding="utf-8") as f:
        for zeile in f:
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            schluessel, wert = zeile.split("=", 1)
            werte[schluessel.strip()] = wert.strip().strip('"').strip("'")
    return werte


def ohne_zugangsdaten(url: str) -> str:
    teile = urllib.parse.urlsplit(url)
    if teile.username is None:
        return url
    host = teile.hostname or ""
    if teile.port:
        host = f"{host}:{teile.port}"
    return urllib.parse.urlunsplit((teile.scheme, host, teile.path, teile.query, teile.fragment))


def main() -> int:
    env_pfad, vorlage, ziel = sys.argv[1:4]
    werte = lies_env(env_pfad)
    urls = [u.strip() for u in werte.get("RTSP_URLS", "").split(",") if u.strip()]
    if not urls:
        print("FEHLER: RTSP_URLS in der kuhwatch-.env ist leer.", file=sys.stderr)
        return 1
    with open(vorlage, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["stream"]["url"] = urls[0]           # dieselbe Quelle wie kuhwatch (U6)
    cfg["stream"]["fallback_snapshot_url"] = ""
    cfg["stream"]["kamera"] = "stallwache"
    cfg["modell"]["pfad"] = ""               # Silent Mode bis zur Modell-Abnahme
    cfg["modell"]["tracker"] = "/app/tracker-kuh.yaml"  # Pfad im Image
    cfg["telegram"]["token"] = werte.get("TELEGRAM_BOT_TOKEN", "")
    cfg["telegram"]["chat_id"] = werte.get("TELEGRAM_CHAT_ID", "")
    cfg["dashboard"]["token"] = os.environ.get("DASHBOARD_TOKEN", "")
    os.umask(0o077)
    with open(ziel, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    os.chmod(ziel, 0o600)

    telegram = bool(cfg["telegram"]["token"] and cfg["telegram"]["chat_id"])
    print(f"  Kamera stallwache: {ohne_zugangsdaten(urls[0])}")
    print("  Modus:             Silent Mode (Trainingsbilder alle "
          f"{cfg['silent_mode']['intervall_sekunden']} s)")
    print(f"  Telegram:          {'uebernommen' if telegram else 'nicht gesetzt (nur Log)'}")
    print(f"  Dashboard:         {'Token gesetzt' if cfg['dashboard']['token'] else 'aus (DASHBOARD_TOKEN fehlt)'}")
    if werte.get("POSE_MODEL_PATH"):
        print(f"  Nicht uebernommen: POSE_MODEL_PATH={werte['POSE_MODEL_PATH']} "
              "(allgemeines Modell, kein Befund – Silent Mode bis zum eigenen Modell)")
    for nr, url in enumerate(urls[1:], start=2):
        print(f"  Weitere Kamera {nr} NICHT eingerichtet: {ohne_zugangsdaten(url)} "
              "(eigene Instanz: KAMERA=<name> docker compose -p <name> up -d, Skill neue-kamera)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
