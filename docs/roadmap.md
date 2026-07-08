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
| 🔄 P3 | Öffentliche Erkennungs-Metriken | Methodik steht (`docs/metriken.md`); Werte nach 1. Training |

## Als Nächstes (kein Blocker)

| Prio | Entscheidung | Nächster Schritt |
| --- | --- | --- |
| ⏳ P1 | **Ereignis-Persistenz** (Vercel KV/Postgres statt In-Memory) | Betreiber legt Vercel-KV-Store an; `lib/events.ts` von In-Memory auf KV umstellen (API-Format bleibt) |
| ⏳ P3 | **Ein-Befehl-Setup** (geführtes Install-Skript + Telegram-Bot-Assistent) | `edge-agent/setup.sh`: venv, pip, config-Assistent, systemd-Unit — matcht CowCatcherAI-Onboarding |

## Blockiert (wartet auf Voraussetzung)

| Prio | Entscheidung | Blocker |
| --- | --- | --- |
| 🔒 P2 | Zwei-Kamera-Brunst-Fusion | erstes trainiertes Modell + beide Kameras sehen dieselbe Bucht |
| 🔒 P3 | 7-Tage-Aktivitäts-Trend je Bucht | setzt Ereignis-Persistenz (P1) voraus |
| 🔒 P3 | Lahmheits-Frühwarnung (Rückenlinien-Winkel) | eigene Validierung nötig; erst nach stabilem Kalbe-/Brunst-Betrieb |

## Bewusst NICHT auf der Roadmap

Aus [`vision.md`](./vision.md) — schützt den Differenzierer: keine
BCS-/Gewichtsschätzung (braucht 3D-Kameras), keine tierindividuelle ID (braucht
Zusatz-Hardware), keine Cloud-Videoanalyse, kein Abo, kein Hardware-Verkauf.

## Nächster natürlicher Meilenstein

**Modell-Erstinbetriebnahme** (siehe `edge-agent/README.md`): Silent Mode →
CVAT-Labeling → Colab-Training → `best.pt` → Analyse-Modus. Erst danach werden
die Metriken (`metriken.md`) gefüllt und die modellabhängigen Features (Brunst-
Fusion, Lahmheit) sinnvoll — deshalb ist alles Modellabhängige bewusst blockiert
statt halb gebaut.
