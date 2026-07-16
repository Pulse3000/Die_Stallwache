# Roadmap & Entscheidungs-Backlog

Konsolidierte Sicht aller Produktentscheidungen aus
[`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md) mit ehrlichem Status.
Dies ist die **Single Source of Truth** für „was ist gebaut, was kommt".
Reihenfolge: erledigt → als Nächstes → wartet auf Voraussetzung.

Legende: ✅ erledigt · 🔄 teilweise · ⏳ offen · 🔒 blockiert (Voraussetzung fehlt)

## Erledigt

| Prio | Entscheidung | Wo umgesetzt |
| --- | --- | --- |
| ✅ P1 | Eskalations-Alarm (Austreibung ohne Fortschritt → Kontroll-Alarm) | `edge-agent/main.py` (`logik.eskalation_minuten`) |
| ✅ P1 | Positionierung „Verhaltens-Schicht, kein NVR" | `README.md` |
| ✅ P2 | Bildserie am Alarm (Telegram-Album) | `edge-agent/main.py` (`telegram.bildserie_frames`) |
| ✅ P2 | Täglicher Telegram-Digest | `edge-agent/main.py` (`telegram.digest_uhrzeit`) |
| ✅ P2 | Wach-Modus pro Bucht (gesenkte Schwellen vor Termin) | `edge-agent/main.py` (`logik.wach_modus`) |
| ✅ P2 | Optionale MQTT-Event-Ausgabe (Home Assistant) | `edge-agent/main.py` (`mqtt.host`) |
| ✅ P2 | Tuya-Futterwache-Frontend (HLS + Bridge-Fallback) | `components/CameraStream.tsx`, `lib/tuya.ts`; nur noch `TUYA_*`-Env setzen |
| ✅ Infra | **MediaMTX als Bridge-Alternative** zu go2rtc (WHEP-Standard statt proprietärer API) | `lib/config.ts` (`NEXT_PUBLIC_BRIDGE_TYPE`), `components/CameraStream.tsx`, `bridge/mediamtx/`; Entscheidungshilfe `bridge/README.md` |
| ✅ Infra | **CORS-Proxy für Tuya-Livestream** (behebt schwarzes Bild – Tuyas CDN setzt keine CORS-Header) | `app/api/futterwache/proxy/route.ts`; schreibt HLS-Manifest same-origin um |
| ✅ Infra | **Bridge auf Android/Termux** (Workaround ohne dedizierte Hardware, für Betriebe mit nur einem Mobilgerät) | `bridge/termux/`; iOS nicht möglich (Apple-Beschränkung) |
| ✅ Infra | **Ein-Befehl-Installation der Termux-Bridge** (Architektur-Erkennung, Binaries, interaktive Konfiguration, Autostart) | `bridge/termux/install.sh` — ein `curl \| bash` statt Einzelschritte |
| 🔄 Infra | **Edge-Agent auf Android/Termux** (Silent Mode/Datensammlung ohne Zusatz-Hardware) | `edge-agent/termux/`; Analyse-Modus (YOLO-Inferenz) dort bewusst **nicht** gebaut – `ultralytics`/`torch` haben keine Android-Wheels, erst nach erstem Modell und ONNX/NCNN-Prüfung relevant |
| ✅ Infra | **Passwortschutz (Login)** – ein gemeinsames Passwort schützt die ganze App, HMAC-signiertes Session-Cookie, keine Datenbank | `middleware.ts`, `lib/auth.ts`, `app/login/`; aktiv via `STALLBLICK_PASSWORT` |
| ✅ P2 | **Stream-Totmann-Meldung** („Das dritte Auge ist blind" — genau 1 Telegram-Nachricht bei Stream-Ausfall > Schwelle, genau 1 Entwarnung bei Rückkehr; Alleinstellung, kein Wettbewerber meldet Ausfälle aktiv) | `edge-agent/main.py` (`TotmannWaechter`, `stream.totmann_minuten`, Default 5 min); modellunabhängig, läuft schon im Silent Mode |
| ✅ Infra | **ByteTrack-Kuh-Tuning** (stabile Kuh-IDs = Fundament aller zeitbasierten Regeln; `track_buffer` 90 statt 30, weil Frames bei 1 FPS Sekunden sind) | `edge-agent/tracker-kuh.yaml` + `modell.tracker`-Option; Verifikations-/Tuning-Prozedur: Skill `bytetrack-tuning` |
| ✅ P2 | **Ein-Tipp-Feedback-Schleife** (Inline-Buttons ✅ Treffer / ❌ Fehlalarm unter jedem Alarm → unannotierte Bildserie automatisch als Hard Negatives; Alleinstellung, niemand lässt den Landwirt das Modell verbessern) | `edge-agent/main.py` (`FeedbackSchleife`, `telegram.feedback_buttons` + `fehlalarm_ordner`); Triage-Prozedur: Skill `fehlalarm-triage`; Bilanz im Tagesbericht |
| ✅ P3 | **Ein-Befehl-Setup** (geführtes Install-Skript: venv, Pakete gestuft nach Silent/Analyse, Telegram-Bot-Assistent, Config-Erzeugung mit 600er-Rechten, optional systemd) — matcht CowCatcherAI-Onboarding | `edge-agent/setup.sh`; README-Schnellstart |
| 🔄 P3 | Öffentliche Erkennungs-Metriken | Methodik steht (`docs/metriken.md`); Werte nach 1. Training |

## Als Nächstes (kein Blocker)

| Prio | Entscheidung | Nächster Schritt |
| --- | --- | --- |
| ⏳ P1 | **Ereignis-Persistenz** (Vercel KV/Postgres statt In-Memory) | Betreiber legt Vercel-KV-Store an; `lib/events.ts` von In-Memory auf KV umstellen (API-Format bleibt) |

## Blockiert (wartet auf Voraussetzung)

| Prio | Entscheidung | Blocker |
| --- | --- | --- |
| 🔒 P1 | **Festliege-Wächter** (Downer-Cow-Alarm: Seitenlage bzw. zu lange liegend, bes. nach Kalbung/Milchfieber-Fenster) — Alleinstellung, kein Kamera-Produkt hat das | erstes trainiertes Modell (Pose-Keypoints nötig) |
| 🔒 P2 | Zwei-Kamera-Brunst-Fusion | erstes trainiertes Modell + beide Kameras sehen dieselbe Bucht |
| 🔒 P3 | **Automatische Kalbe-Akte** (eine Abschluss-Nachricht mit Phasen-Zeitstempeln + Belegbildern, „Kalb steht seit 04:32" als erste Entwarnungs-Nachricht der Branche) | setzt Ereignis-Persistenz (P1) voraus |
| 🔒 P3 | 7-Tage-Aktivitäts-Trend je Bucht | setzt Ereignis-Persistenz (P1) voraus |
| 🔒 P3 | Lahmheits-Frühwarnung (Rückenlinien-Winkel) | eigene Validierung nötig; erst nach stabilem Kalbe-/Brunst-Betrieb |

## Bewusst NICHT auf der Roadmap

Aus [`vision.md`](./vision.md) — schützt den Differenzierer: keine
BCS-/Gewichtsschätzung (braucht 3D-Kameras), keine tierindividuelle ID (braucht
Zusatz-Hardware), keine Cloud-Videoanalyse, kein Abo, kein Hardware-Verkauf.

## Nächster natürlicher Meilenstein

**Modell-Erstinbetriebnahme** (geführte Prozedur: Skill `modell-training`,
Details `edge-agent/README.md`): Silent Mode →
CVAT-Labeling → Colab-Training → `best.pt` → Analyse-Modus. Erst danach werden
die Metriken (`metriken.md`) gefüllt und die modellabhängigen Features (Brunst-
Fusion, Lahmheit) sinnvoll — deshalb ist alles Modellabhängige bewusst blockiert
statt halb gebaut.
