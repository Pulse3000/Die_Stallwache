#!/usr/bin/env python3
"""Strukturtests fuer den Einsatz auf stallwache-lela (deploy-stallwache-lela/).

Am Geraet testen koennen wir nicht; geprueft wird, was sich im Repo belegen
laesst:
1. Das Profil hat dieselben Schluessel wie config.example.yaml – der Agent
   verlangt sie auch im Silent Mode (KeyError sonst erst am Geraet).
2. Profilwerte: Silent Mode, nur Einzelbilder ueber 127.0.0.1, keine
   Geheimnisse im Repo, kein Archiv („Bilder bleiben auf dem Hof").
3. Das Dockerfile kopiert jedes lokale Modul, das main.py importiert
   (der alte Deploy-Zweig vergass freeze_watchdog.py -> ImportError).
4. Compose und Profil passen zusammen (Host-Netz, Volumes, Ortszeit).
Ohne PyYAML: Die Schluessel liest ein kleiner Einrueckungs-Parser.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main  # noqa: E402

AGENT = Path(__file__).resolve().parent.parent
DEPLOY = AGENT / "deploy-stallwache-lela"
p = Pruefer("LELA-Profil")


def schluessel(text: str) -> dict[str, str]:
    """Pfad -> roher Wert (ohne Kommentar) fuer einfache YAML-Dateien."""
    pfade: dict[str, str] = {}
    stapel: list[tuple[int, str]] = []
    for zeile in text.splitlines():
        if not zeile.strip() or zeile.lstrip().startswith("#"):
            continue
        t = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):(.*)$", zeile)
        if not t:
            continue
        tiefe, name, rest = len(t.group(1)), t.group(2), t.group(3)
        while stapel and stapel[-1][0] >= tiefe:
            stapel.pop()
        pfad = ".".join([n for _, n in stapel] + [name])
        wert = re.sub(r"\s+#.*$", "", rest).strip()
        pfade[pfad] = wert.strip('"')
        stapel.append((tiefe, name))
    return pfade


beispiel = schluessel((AGENT / "config.example.yaml").read_text(encoding="utf-8"))
profil_text = (DEPLOY / "config.silent-lela.yaml").read_text(encoding="utf-8")
profil = schluessel(profil_text)

# --- 1. gleiche Schluessel ----------------------------------------------------
fehlen = sorted(set(beispiel) - set(profil))
zuviel = sorted(set(profil) - set(beispiel))
p.check(f"1: keine Schluessel fehlen ({fehlen})", not fehlen)
p.check(f"1: keine unbekannten Schluessel ({zuviel})", not zuviel)
p.check(f"1: Parser hat Schluessel gefunden ({len(beispiel)})", len(beispiel) > 40)

# --- 2. Werte ---------------------------------------------------------------------
p.check("2: Silent Mode (modell.pfad leer)", profil.get("modell.pfad") == "")
p.check("2: kein RTSP-Strom (stream.url leer)", profil.get("stream.url") == "")
snap = profil.get("stream.fallback_snapshot_url", "")
p.check("2: Einzelbilder von go2rtc auf 127.0.0.1",
        snap.startswith("http://127.0.0.1:1984/api/frame.jpeg?src=stallwache"))
p.check("2: keine Zugangsdaten in der Snapshot-URL", "@" not in snap)
p.check("2: ein Einzelbild alle 10 s", profil.get("stream.ziel_fps") == "0.1")
p.check("2: Speichern alle 120 s", profil.get("silent_mode.intervall_sekunden") == "120")
p.check("2: Archiv aus (Bilder bleiben auf dem Hof)", profil.get("dashboard.archiv") == "false")
p.check("2: keine Alarmbilder an die App", profil.get("dashboard.bilder") == "0")
p.check("2: Feedback-Buttons aus", profil.get("telegram.feedback_buttons") == "false")
for k in ("telegram.token", "telegram.chat_id", "dashboard.token", "stream.app_passwort", "mqtt.password"):
    p.check(f"2: kein Geheimnis im Repo ({k})", profil.get(k) == "")
p.check("2: Offline-Puffer im daten-Volume", profil.get("dashboard.puffer_datei", "").startswith("daten/"))

# --- 2b. Profil laeuft durch den echten StreamHandler -------------------------
try:
    import yaml  # noqa: F401
    echt_yaml = hasattr(yaml, "safe_load")
except ImportError:
    echt_yaml = False
if echt_yaml:
    cfg = yaml.safe_load(profil_text)
    m, _ = lade_main(mit_requests_stub=True)
    sh = m.StreamHandler(cfg)
    p.check("2b: StreamHandler startet im Einzelbild-Modus", sh.nutze_fallback and not sh.url)
    p.check("2b: 10 s zwischen zwei Einzelbildern", abs(sh.frame_intervall - 10.0) < 1e-9)
    p.check("2b: Totmann 5 min", m.TotmannWaechter(cfg).schwelle_s == 300)
else:
    print("HINWEIS 2b uebersprungen: PyYAML fehlt")

# --- 3. Dockerfile kopiert jedes lokale Modul ------------------------------------
docker = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
kopiert = " ".join(z for z in docker.splitlines() if z.startswith("COPY "))
main_py = (AGENT / "main.py").read_text(encoding="utf-8")
lokal = sorted({n for n in re.findall(r"^(?:from|import)\s+([A-Za-z_]\w*)", main_py, re.M)
                if (AGENT / f"{n}.py").exists()})
p.check(f"3: lokale Module gefunden ({lokal})", "freeze_watchdog" in lokal)
for n in lokal + ["main"]:
    p.check(f"3: Dockerfile kopiert {n}.py", re.search(rf"\b{n}\.py\b", kopiert))
p.check("3: tracker-kuh.yaml kopiert (Analyse-Modus spaeter)", "tracker-kuh.yaml" in kopiert)
p.check("3: training/ kopiert (datensatz.py bilanz im Container)", "training/" in kopiert)
p.check("3: Basis ist das kuhwatch-Image (numpy < 2, offline)", "kuhwatch-stallwache:latest" in docker)
p.check("3: Import-Probe beim Bauen", re.search(r"RUN python -c \"import cv2, numpy", docker))
p.check("3: cpu_compat liegt bei", (DEPLOY / "cpu_compat.py").exists())

# --- 4. Compose passt zum Profil ----------------------------------------------------
compose = (DEPLOY / "docker-compose.yml").read_text(encoding="utf-8")
p.check("4: Host-Netz (go2rtc ueber 127.0.0.1)", re.search(r"^\s+network_mode:\s*host\s*$", compose, re.M))
p.check("4: Containername wie im Tempguard", re.search(r"^\s+container_name:\s*stallblick-agent\s*$", compose, re.M))
p.check("4: 1 CPU", re.search(r"^\s+cpus:\s*1\b", compose, re.M))
p.check("4: Arbeitsverzeichnis /agent", re.search(r"^\s+working_dir:\s*/agent\s*$", compose, re.M))
for quelle, ziel in (("../config.yaml", "/agent/config.yaml:ro"), ("../aufnahmen", "/agent/aufnahmen"),
                     ("../daten", "/agent/daten"), ("/etc/localtime", "/etc/localtime:ro")):
    p.check(f"4: Volume {quelle} -> {ziel}", f"- {quelle}:{ziel}" in compose)
p.check("4: Profil-Ordner ./aufnahmen liegt im Volume", profil.get("silent_mode.ordner") == "./aufnahmen")
p.check("4: Dockerfile-Pfad passt zum Build-Kontext",
        "dockerfile: deploy-stallwache-lela/Dockerfile" in compose and "context: .." in compose)
p.check("4: Log-Groesse begrenzt", "max-size" in compose and "max-file" in compose)

# --- 5. nichts davon landet im Repo -----------------------------------------------
ignore = (AGENT.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
for eintrag in ("edge-agent/config.yaml", "edge-agent/aufnahmen/", "edge-agent/daten/", "edge-agent/modelle/"):
    p.check(f"5: .gitignore enthaelt {eintrag}", eintrag in ignore)

sys.exit(p.bericht())
