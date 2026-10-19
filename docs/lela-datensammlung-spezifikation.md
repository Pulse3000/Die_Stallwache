# Datensammlung auf stallwache-lela: Edge-Agent im Silent Mode statt kuhwatch

Stand: 19.10.2026 · Entscheidungen des Landwirts:
„stallwache-lela: Soll dort statt kuhwatch der Edge-Agent im Silent Mode
laufen, damit Trainingsbilder gesammelt werden? – ja" und
„Bilder bleiben auf dem Hof".

Das Dokument legt fest, wie der Stall-Rechner stallwache-lela umgestellt wird,
was der Agent dort tut und was nicht, und wie die Umstellung am Gerät
abgenommen und notfalls zurückgenommen wird. Die Umstellung macht der
Betreiber am Gerät. Agenten haben keinen Zugriff auf LELA.

## 1. Grundsatz

1. **Zweck ist die Datensammlung für Modell v1.** kuhwatch speichert keine
   Bilder. Ohne eigene Stall-Bilder gibt es kein trainiertes Pose-Modell und
   damit keine Kalbe- oder Brunsterkennung (Meilenstein der Roadmap).
2. **Bilder bleiben auf dem Hof.** Trainingsbilder liegen nur auf LELA und auf
   lokalen Sicherungen (USB-Platte, Hof-NAS). Es gibt keinen automatischen
   Upload: `dashboard.archiv` bleibt `false`. Ein Einschalten des Archivs
   braucht eine neue Entscheidung des Landwirts.
3. **Nach außen gehen nur strukturierte Meldungen:** Lebenszeichen an die App
   (Modus „silent", Kamera liefert Bild ja/nein, kein Bild), Tagesbericht und
   Störungsmeldungen per Telegram (Text, kein Bild).
4. **Ein Analyseprozess, flache Last.** Der Rechner (AMD A6-3650, 2011, kein
   AVX, ohne GPU) hatte unter Dauerlast schon Hitze-Abstürze. kuhwatch wird
   gestoppt, nicht parallel betrieben.
5. **Der Hitzeschutz bleibt.** Der Tempguard aus kuhwatch läuft weiter und
   pausiert ab 85 °C auch den Agenten.

## 2. Grenzen (was die Umstellung bewusst nicht leistet)

1. **Während der Sammelphase gibt es auf LELA keine automatische Kalbe- oder
   Brunsterkennung.** Der Silent Mode analysiert nicht. Der bisherige
   kuhwatch-Bewegungsalarm fällt weg. Er war fachlich schwach (Box-Bewegung
   über alle Klassen einschließlich Menschen) und mit `SILENT_MODE=1` in
   kuhwatch ohnehin nur geloggt. Steht eine Kalbung an, gilt die gewohnte
   Kontrolle durch Menschen.
2. **Austreibungsbilder entstehen so nicht.** Fruchtblase und Kälberfüße
   brauchen eine Videoaufzeichnung echter Geburten (1 Bild alle 2–5 s,
   `training-pipeline`). Die 120-s-Bilder liefern Tag, Dämmerung, IR-Nacht und
   Schwanzhaltung, nicht die Austreibung.
3. **Eine Kamera.** Gesammelt wird die Stallwache (Tapo, lokal über go2rtc).
   Die Tuya-Kameras (Abkalbebox, Futterwache, Weidewache) wären je eine eigene
   Agent-Instanz und sind nicht Teil dieser Umstellung.
4. **Labeln und Training** (CVAT, Colab) sind nicht Teil dieser Umstellung. Ob
   „Bilder bleiben auf dem Hof" auch dafür gilt, ist offen (Abschnitt 8).

## 3. Aufbau

| Teil | Wo | Was |
| --- | --- | --- |
| Agent | Docker-Container `stallblick-agent` | `edge-agent/deploy-stallwache-lela/`; baut auf dem vorhandenen Image `kuhwatch-stallwache:latest` auf (numpy < 2, OpenCV headless, offline gebaut, läuft nachweislich auf der A6). `network_mode: host`, 1 CPU, 2 GB RAM, Ortszeit vom Host |
| Bildquelle | go2rtc auf LELA | Nur Einzelbilder: `http://127.0.0.1:1984/api/frame.jpeg?src=stallwache`, alle 10 s abgeholt (`stream.ziel_fps: 0.1`), alle 120 s eins gespeichert. Von 127.0.0.1 braucht go2rtc keinen Login (`local_auth` aus), also stehen keine Kamera-Zugangsdaten in der Konfiguration |
| Ablage | `edge-agent/aufnahmen/` auf dem Host | `<kamera>_<JJJJMMTT-HHMMSS>.jpg` in Ortszeit (Split nach Stalltagen 12–12 Uhr) |
| Puffer | `edge-agent/daten/` auf dem Host | Offline-Puffer des Dashboard-Versands, überlebt einen Neuaufbau des Containers |
| Hitzeschutz | systemd `kuhwatch-tempguard` | pausiert `kuhwatch-stallwache` **und** `stallblick-agent` ab 85 °C, Takt 1,6 GHz, Entwarnung ab 75 °C |
| kuhwatch | Container `kuhwatch-stallwache` | gestoppt (`docker compose stop`), Image und `.env` bleiben für den Rückweg und den Tempguard |

**Warum Einzelbilder statt RTSP:** Der Silent Mode braucht alle 120 s ein
Bild. Ein offener RTSP-Strom wird dauernd dekodiert. Liest OpenCV ihn nur mit
1 Bild/s, staut sich der Strom auf, und gespeicherte Bilder können
zeitlich hinterherhinken oder verschmiert sein. Ein Einzelbild von go2rtc ist
immer aktuell und kostet die alte CPU nur einen kurzen Dekodierschritt alle
10 s. Für den späteren Analyse-Modus (1 Bild/s) wird auf RTSP umgestellt.

**Warum Docker statt venv:** Ein frisches venv zieht numpy ≥ 2.4. Das setzt
den Befehlssatz X86_V2 (SSSE3, SSE4.1/4.2) voraus, den die A6-3650 nicht hat:
Der Agent würde schon beim Import abstürzen. Das kuhwatch-Image bringt die
passenden Pakete mit und braucht kein Internet.

## 4. Werte (keine neuen Regler)

Es gibt keine neuen Schwellen in der Erkennungslogik. Neu sind nur feste
Betriebsgrenzen als Konstanten im Code:

| Wert | Wo | Begründung |
| --- | --- | --- |
| Platzreserve 2 GiB | `main.py`, `AblageWaechter.RESERVE_BYTES` | Darunter speichert der Agent keine Bilder mehr. Betriebssystem, Docker und Logs liegen auf derselben Platte und dürfen nicht volllaufen |
| Wiederaufnahme ab 2,5 GiB (Hysterese 512 MiB) | `main.py`, `AblageWaechter.WIEDER_AB_BYTES` | verhindert, dass die Meldung flackert, wenn Logs den freien Platz um die Reserve schwanken lassen |
| `ziel_fps: 0.1` | LELA-Profil `config.silent-lela.yaml` | ein Einzelbild alle 10 s: Lebenszeichen „Bild da" (< 120 s) und Totmann (5 min) bleiben gültig, Bildabstand 120–131 s (Mittel ca. 126 s). Nur für den Silent Mode: Startet der Agent mit Modell und weniger als 1 Bild/s, meldet er das einmal |
| `feedback_buttons: false` | LELA-Profil | im Silent Mode gibt es keine Alarme, und `getUpdates` kollidiert mit einem Webhook am selben Bot (409) |
| `archiv: false` | LELA-Profil | Entscheidung „Bilder bleiben auf dem Hof" |

Unverändert: Silent-Intervall 120 s, Freeze-Watchdog (5 gespeicherte Bilder
= ca. 10 min), Totmann 5 min, Tagesbericht 20:00, Tempguard 80/85/75 °C.

## 5. Meldetexte

| Anlass | Kanal | Text |
| --- | --- | --- |
| Start | Dashboard, MQTT | „Edge-Agent gestartet (Silent Mode – Datensammlung)" (unverändert) |
| Tagesbericht 20:00 | Telegram | „Modus: Datensammlung (Silent Mode) – keine Kalbe- und Brunsterkennung. Bitte den Abkalbebereich wie gewohnt selbst kontrollieren." / „Trainingsbilder seit dem letzten Bericht: N · frei: X GB" (erster Bericht nach einem Neustart: „seit dem Start um HH:MM") / „Agent läuft seit … · Kamera: stallwache". Keine Zähler „Kalbeverdacht/Austreibung: 0": Es wird nichts analysiert |
| Ablage gestört (Platz unter Reserve) | Telegram, Dashboard (einmal je Störung) | „Trainingsbilder pausiert: nur noch 1,9 GB frei, das System braucht 2 GB Reserve. Bitte die Bilder sichern (z. B. USB-Platte) und danach im Ordner aufnahmen löschen. Ab 2,5 GB frei läuft die Sammlung von selbst weiter." (freier Platz abgerundet) |
| Ablage gestört (Schreibfehler) | Telegram, Dashboard (einmal je Störung) | „Trainingsbild konnte nicht gespeichert werden (<Ordner>). Bitte Ordner und Rechte prüfen. Wurde der Ordner verschoben oder gelöscht, den Agenten neu starten." |
| Ablage wieder in Ordnung | Telegram, Dashboard | „Trainingsbilder werden wieder gespeichert." |
| Kamerabild eingefroren/gestört | Telegram, Dashboard (Freeze-Watchdog, einmal je Störung) | „Kamera stallwache: Bild eingefroren seit … Es werden vorerst keine Trainingsbilder gespeichert – bitte Kamera und Bildquelle (go2rtc/Bridge) prüfen." Ein gleichmäßiges Band (dunkle Decke nachts, überstrahlte Wand) gilt nicht als Streifen-Defekt. Ein sehr rauscharmes Nachtband mit Helligkeitsverlauf oder Lichtkante kann noch als Streifen gelten (§8). Entwarnung „Bild wieder in Ordnung" erst nach 5 sauberen Bildern in Folge; Rückfälle dazwischen ohne neue Meldung |
| Analyse mit zu wenigen Bildern | Telegram, Dashboard (einmal beim Start) | „Analyse läuft mit nur einem Bild alle 10 s – kurze Aufsprünge werden so übersehen. Bitte stream.ziel_fps auf 1.0 stellen (und stream.url auf RTSP)." |
| Hitze ≥ 85 °C | Telegram (Tempguard) | „STALLWACHE KRITISCH: CPU bei N°C. Pausiert: <Container>. Takt gedeckelt. Entwarnung folgt bei 75°C." |
| Hitze ≤ 75 °C | Telegram (Tempguard) | „STALLWACHE OK: CPU auf N°C abgekuehlt. Laeuft wieder: <Container>." |
| Kein Temperatursensor | Telegram, Log (Tempguard, einmal) | „STALLWACHE WARNUNG: Kein k10temp-Sensor gefunden – Hitzeschutz ohne Messwert." |
| Tempguard-Fehlschläge | Telegram (Tempguard) | Gescheitertes Pausieren/Fortsetzen, nicht erreichbares Docker, fehlendes cpufreq und ein in der Hitze wieder angelaufener Container werden ausdrücklich gemeldet; vollständige Texte in kuhwatch `deploy/README.md` |

## 6. Abnahme am Gerät (Beweispflicht, Betreiber)

Die Umstellung gilt erst als vollzogen, wenn der Betreiber diese Punkte am
Gerät belegt hat. Was wir aus der Ferne sehen, steht in der letzten Spalte.

| # | Prüfung | erwartet | aus der Ferne sichtbar |
| --- | --- | --- | --- |
| 1 | `docker ps -a` | `kuhwatch-stallwache` „Exited", `stallblick-agent` „Up" | – |
| 2 | `docker logs stallblick-agent` | „Edge-Agent gestartet (Silent Mode – Datensammlung)", danach „Trainingsbild gespeichert" | Startmeldung im Aktivitätsprotokoll der App (mit `dashboard.token`) |
| 3 | `ls -l edge-agent/aufnahmen` nach 10 min | 5–6 Bilder, Name mit Ortszeit, Uhrzeit im Kamerabild passt zum Namen (± 15 s) | – |
| 4 | ein Bild öffnen | volle Auflösung, scharf, keine Schlieren | – |
| 5 | `systemctl status kuhwatch-tempguard` | aktiv, Log nennt den Sensor und beide Container | – |
| 6 | `GET /api/stall-status` (Tagesreport) | Stallwache „UNBEKANNT – Silent Mode (Datensammlung)" | ja |
| 7 | Tagesbericht 20:00 | „Datensammlung (Silent Mode) – keine Kalbe- und Brunsterkennung …" und „Trainingsbilder seit …: N" | ja (Telegram) |
| 8 | nach der ersten Nacht und nach 24 h | `docker exec stallblick-agent python training/datensatz.py bilanz aufnahmen` zeigt IR-Nacht-Bilder aus der ganzen Nacht (etwa 1/3 bis 1/2 aller Bilder); in der Nacht kam keine Meldung „Bild gestört" oder „Bild eingefroren"; nach 24 h ca. 690 Bilder (660–720) | Tagesbericht |
| 9 | nach 1–2 Wochen | `docker exec stallblick-agent python training/datensatz.py bilanz aufnahmen` endet mit Exit 0 (IR-Nacht ≥ 1/3, B9) | – |

## 7. Rückweg

Zurück zu kuhwatch, wenn der Agent im Neustart-Loop hängt, die CPU dauerhaft
über 80 °C liegt oder der Landwirt den Bewegungsalarm zurückwill:

```bash
cd ~/Die_Stallwache/edge-agent
docker compose -f deploy-stallwache-lela/docker-compose.yml stop
cd ~/kuhwatch && docker compose start stallwache
docker logs --tail 20 kuhwatch-stallwache
```

Die gesammelten Bilder in `edge-agent/aufnahmen/` bleiben liegen. Nie
`docker compose down --rmi`, `docker image prune -a` oder die kuhwatch-`.env`
löschen: Das kuhwatch-Image lässt sich ohne die lokalen `wheels/` und
`models/` nicht neu bauen, und der Agent baut auf ihm auf.

## 8. Risiken und offene Punkte

| Risiko | Gegenmaßnahme |
| --- | --- |
| Bilder liegen nur auf einer alten Platte | wöchentlich auf USB-Platte oder Hof-NAS kopieren (Landwirt/Betreiber); kein Cloud-Upload (Grundsatz 2) |
| go2rtc läuft nicht oder liefert kein Bild | Totmann-Meldung nach 5 min; Lebenszeichen „kein Bild"; dann go2rtc prüfen oder `stream.fallback_snapshot_url` auf die Kamera direkt setzen. Erreicht go2rtc die Kamera nicht, antwortet es mit 200 ohne Inhalt – auch das zählt als „kein Bild" (früher fiel dabei der Totmann aus) |
| Zugangsdaten und Tokens im Log | Jede Logzeile wird geschwärzt (`OhneGeheimnisse`): Benutzer/Passwort in URLs, Telegram-Bot-Token, die Tokens und Passwörter aus `config.yaml` – auch in Tracebacks |
| `archiv: "false"` (in Anführungszeichen) schaltete das Archiv ein | Nur ein echtes `true` schaltet es ein, alles andere bleibt aus und wird gewarnt |
| Streifen-Fehlalarm bei sehr rauscharmen Nachtbildern mit Helligkeitsverlauf/Lichtkante (Altbestand) | Abnahme §6 #8 zeigt es in der ersten Nacht. Dann `docker exec stallblick-agent python freeze_watchdog.py diagnose aufnahmen` (nur Kennzahlen, kein Bild) an den Orchestrator. Über ein anderes Streifen-Kriterium wird mit diesen Zahlen entschieden – der naheliegende Ersatz (Sprung von Spalte zu Spalte) übersähe Verschmieren in glatten Nachtbildern |
| Platte läuft voll | Platzreserve 2 GiB, einmalige Meldung, Tagesbericht nennt freien Platz |
| Ordner `aufnahmen/` beim Sichern verschoben oder gelöscht | Bind-Mount: der Agent schreibt in den alten Ordner weiter bzw. meldet einen Schreibfehler. Runbook: nur Bilder löschen, nie den Ordner; sonst Container neu starten |
| Hitze | Tempguard pausiert den Agenten; Container auf 1 CPU begrenzt |
| Personen im Bild | Bilder bleiben auf dem Hof; vor dem Labeln Bilder mit Personen aussortieren |
| **Offen (Landwirt):** Gilt „Bilder bleiben auf dem Hof" auch fürs Labeln (app.cvat.ai) und fürs Training (Colab)? | Bis zur Entscheidung keine Bilder hochladen; Alternative wäre ein lokales CVAT auf einem Hof-PC |
| **Offen (Landwirt):** zweite Instanz für die Abkalbebox (Tuya-Cloud) | eigene Entscheidung, eigene Instanz |
| **Offen (Landwirt):** Gilt „Bilder bleiben auf dem Hof" auch für die Alarmbilder im späteren Analyse-Modus (Telegram-Bildserie, Bilder in der App)? | Bis zur Entscheidung bleibt der Analyse-Modus auf LELA aus |
