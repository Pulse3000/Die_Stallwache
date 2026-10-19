# Edge-Agent auf stallwache-lela: Silent Mode statt kuhwatch

Runbook für den Betreiber. Hintergrund, Grenzen und Abnahme:
[`docs/lela-datensammlung-spezifikation.md`](../../docs/lela-datensammlung-spezifikation.md).

Der Agent sammelt Trainingsbilder der Stallwache (alle 120 s ein Bild).
**Während der Sammelphase gibt es auf LELA keine automatische Kalbe- oder
Brunsterkennung.** Die Bilder bleiben auf dem Rechner. Es gibt keinen
Cloud-Upload.

## Was hier liegt

| Datei | Zweck |
| --- | --- |
| `Dockerfile` | baut auf dem vorhandenen Image `kuhwatch-stallwache:latest` auf (numpy < 2, läuft auf der A6 ohne AVX/X86_V2, offline) |
| `docker-compose.yml` | Container `stallblick-agent`: Host-Netz, 1 CPU, 2 GB RAM, Ortszeit vom Host, Volumes für `config.yaml`, `aufnahmen/`, `daten/` |
| `config.silent-lela.yaml` | Profil: Silent Mode, nur Einzelbilder von go2rtc über 127.0.0.1, kein Archiv, keine Feedback-Buttons |
| `cpu_compat.py` | NMS ohne AVX, erst mit Modell relevant |

## 0. Vorher prüfen (2 min)

```bash
docker ps --format '{{.Names}} {{.Status}}'      # kuhwatch-stallwache und stallwache-go2rtc laufen
docker images kuhwatch-stallwache                 # Image vorhanden (Basis des Agenten)
curl -s -o /tmp/probe.jpg -w '%{http_code}\n' 'http://127.0.0.1:1984/api/frame.jpeg?src=stallwache'   # 200
df -h ~                                           # freier Platz: ~ 0,2–0,8 GB pro Tag einplanen
timedatectl | grep 'Time zone'                    # Europe/Berlin
systemctl is-active kuhwatch-tempguard            # active
```

Liefert der `curl`-Aufruf nicht 200, läuft go2rtc nicht oder kennt den Stream
`stallwache` nicht. Dann zuerst go2rtc reparieren (`bridge/`). Die
Bildquelle des Agenten ist genau diese Adresse.

## 1. Tempguard auf den Agenten erweitern

Aus dem kuhwatch-Repo (ab dem Stand mit `TEMPGUARD_CONTAINER`):

```bash
cd ~/kuhwatch && git pull
sudo cp deploy/kuhwatch-tempguard.sh /usr/local/bin/kuhwatch-tempguard.sh
sudo systemctl restart kuhwatch-tempguard
tail -3 /var/log/kuhwatch-tempguard.log           # nennt Sensor und beide Container
```

## 2. Umstellen

```bash
# kuhwatch-Inferenz stoppen (Image und .env bleiben: Rückweg und Tempguard)
cd ~/kuhwatch && docker compose stop stallwache

# Agent einrichten
cd ~/Die_Stallwache && git pull
cd edge-agent
cp deploy-stallwache-lela/config.silent-lela.yaml config.yaml && chmod 600 config.yaml
nano config.yaml      # telegram.token/chat_id wie in ~/kuhwatch/.env, dashboard.token = EDGE_INGEST_TOKEN
mkdir -p aufnahmen daten modelle
docker compose -f deploy-stallwache-lela/docker-compose.yml up -d --build
docker logs -f stallblick-agent                   # Strg-C beendet nur die Anzeige
```

Erwartet im Log:
`Nur Einzelbilder: http://127.0.0.1:1984/api/frame.jpeg`,
`Edge-Agent gestartet (Silent Mode – Datensammlung)`,
danach alle 2 min `Trainingsbild gespeichert: aufnahmen/stallwache_JJJJMMTT-HHMMSS.jpg`.

Der Build braucht kein Internet. Scheitert er bei der Import-Probe
(`RUN python -c "import cv2, numpy …"`), fehlt im Basis-Image ein Paket.
Den Fehler dann vollständig an den Orchestrator geben.

## 3. Abnahme

Die Prüfliste steht in der Spezifikation, §6. Kurz:

- nach 10 min: 5–6 Bilder in `aufnahmen/`, die Uhrzeit im Bild passt zum Dateinamen
- 20:00: Tagesbericht mit „Trainingsbilder seit dem letzten Bericht: N · frei: X GB“
- nach 24 h: ca. 720 Bilder, mindestens eine IR-Nachtaufnahme
- nach 1–2 Wochen: `docker exec stallblick-agent python training/datensatz.py bilanz aufnahmen` → Exit 0

## 4. Bilder sichern (wöchentlich)

Die Bilder liegen nur auf diesem Rechner. Sie bleiben auf dem Hof
(Entscheidung des Landwirts, 19.10.2026). Gesichert wird deshalb lokal:

```bash
rsync -a ~/Die_Stallwache/edge-agent/aufnahmen/ /media/<usb-platte>/stallwache-aufnahmen/
```

Die Dateien gehören root (der Container schreibt sie). Zum Löschen nach dem
Sichern deshalb `sudo` verwenden. Fällt der freie Platz unter 2 GB, speichert
der Agent keine Bilder mehr und meldet das einmal per Telegram.

## 5. Rückweg zu kuhwatch

```bash
cd ~/Die_Stallwache/edge-agent && docker compose -f deploy-stallwache-lela/docker-compose.yml stop
cd ~/kuhwatch && docker compose start stallwache
docker logs --tail 20 kuhwatch-stallwache
```

Nie `docker compose down --rmi`, `docker image prune -a` oder die
kuhwatch-`.env` löschen. Das kuhwatch-Image lässt sich ohne die lokalen
`wheels/` und `models/` nicht neu bauen, und der Agent baut auf ihm auf.

## Später: Analyse-Modus

Nach bestandener Abnahme eines Modells (`training/abnahme.py`): `best_vN.pt`
nach `modelle/`, in `config.yaml` `modell.pfad: modelle/best_vN.pt`,
`stream.url: rtsp://127.0.0.1:8554/stallwache` und `stream.ziel_fps: 1.0`.
Für die Analyse braucht das Basis-Image torch/ultralytics; das echte
kuhwatch-Image hat beides.
