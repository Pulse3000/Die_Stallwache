# Roadmap & Entscheidungs-Backlog

Konsolidierte Sicht aller Produktentscheidungen aus
[`wettbewerbsanalyse.md`](./wettbewerbsanalyse.md) mit ehrlichem Status.
Dies ist die **Single Source of Truth** für „was ist gebaut, was kommt".
Reihenfolge: erledigt → als Nächstes → wartet auf Voraussetzung.

Legende: ✅ erledigt · 🔄 teilweise · ⏳ offen · 🔒 blockiert (Voraussetzung fehlt)

## Erledigt

| Prio | Entscheidung | Wo umgesetzt |
| --- | --- | --- |
| ✅ P1 | **Inhaltliche** Eskalation (Austreibung ohne Fortschritt → Kontroll-Alarm; „geht es der Kuh schlecht?"). Nicht zu verwechseln mit der **Reaktions**-Eskalation weiter unten („hat es jemand gesehen?") | `edge-agent/main.py` (`logik.eskalation_minuten`) |
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
| ✅ Infra | **Cloud-Quelle ohne Bridge**: Edge-Agent liest Tuya-Kameras (Futterwache/Abkalbebox/Weidewache) direkt über die Webapp-API — Login, kurzlebige HLS-URL, CDN-Direktzugriff, automatische URL-Erneuerung beim Reconnect. **Silent Mode startet damit ohne Bridge-Hardware** | `edge-agent/main.py` (`CloudQuelle`, `stream.app_url`/`quelle_api`/`app_passwort`); Bridge bleibt der Weg für die Stallwache (RTSP, latenzarm) |
| ✅ P1 | **Push-Benachrichtigungen (FCM)** — Austreibung als dringender Alarm (schließt sich nicht selbst, stärkere Vibration), Quittieren direkt aus der Meldung, Probealarm zum Prüfen der Kette | `lib/push.ts` (HTTP v1 über Service-Account-JWT, ohne SDK im Server), `public/sw.js`, `components/PushSchalter.tsx`; Env: `GCP_SERVICE_ACCOUNT_JSON` + `FIREBASE_*` |
| ✅ P1 | **Alarmbilder in der App** — der Edge-Agent schickt die Bildserie mit, das Aktivitätsprotokoll spielt sie ab | `edge-agent/main.py` (`dashboard.bilder`), `app/api/events/[id]/bild/[index]/`, `components/AlarmBilder.tsx` |
| ✅ P1 | **Offline-Fähigkeit beidseitig** — App: Shell/Ereignisse/Bilder im Cache, Quittierungen & Schaltbefehle in einer Warteschlange (Background Sync). Agent: Puffer auf der Platte, überlebt Neustart, liefert mit dem **ursprünglichen** Zeitstempel nach | `public/sw.js`, `lib/offline.ts`, `edge-agent/main.py` (`dashboard.puffer_datei`); Tests: `edge-agent/tests/test_offlinepuffer.py` |
| ✅ P2 | **Fünf-Bereiche-PWA** (Dashboard/Alarme/Steuerung/Analytik/Einstellungen), installierbar auf Android & iOS, Tab-Leiste mit Safe-Area und Zähler offener Alarme | `app/layout.tsx`, `components/TabLeiste.tsx`, `public/manifest.webmanifest` |
| ✅ P3 | **Analytik-Bereich** — Verlauf (7/14/30 T), Tagesgang in Ortszeit, Reaktionszeit (Median) und Bestätigungsquote Kalbeverdacht → Austreibung. Serverseitig aggregiert (~10 kB statt ~48 kB), Diagramme als antippbare CSS-Balken statt Chart-Bibliothek | `lib/analytik.ts`, `app/api/analytik/`, `components/AnalytikApp.tsx`; Tests: `tests/analytik.test.ts` (24 Checks) |
| ✅ P3 | **Brunstrhythmus je Kuh** — persönlicher Zyklus aus den Abständen der Brunstmeldungen, Prognose des nächsten Termins nur bei plausiblen 18–24 Tagen, auffällige Abstände als Hinweis. Meldungen derselben Brunst (< 36 h) zählen als eine | `lib/analytik.ts` (`baueBrunstZyklen`) |
| ✅ P2 | **Datensparen als Vorgabe** — Livebild und Alarmbilder erst auf Tippen, Abrufintervall einstellbar; im Mobilfunk der Unterschied zwischen ein paar kB und ein paar MB | `lib/einstellungen.ts`, `components/StallblickApp.tsx`, `components/EinstellungenApp.tsx` |
| ✅ P2 | **Tuya-Gerätesteuerung** (Tränken, Licht, Sensoren) — Bedienelemente entstehen aus dem gemeldeten Gerätemodell; `TUYA_GERAETE` ist zugleich Allowlist, damit kein Fremdgerät des Tuya-Kontos schaltbar ist | `lib/tuya.ts`, `app/api/tuya/geraete/` |
| ✅ P2 | **Freitext-/Sprachanfragen** („Zeig mir alle Aktivitäten von Kuh #42") — Vertex AI bzw. Gemini-API, mit lokaler Auswertung des Protokolls als Rückfallebene, die auch ohne Cloud antwortet | `lib/assistent.ts`, `app/api/assistent/`, `components/Assistent.tsx` (Web Speech API) |
| ✅ Infra | **Pub/Sub-Spiegelung** jedes Ereignisses in die bestehende GCP-Architektur (Cloud Functions, YOLO-Nachanalyse); fire-and-forget, blockiert den Alarmweg nie | `lib/pubsub.ts`, `lib/gcp.ts`; Env: `PUBSUB_TOPIC` |
| 🔄 P3 | Öffentliche Erkennungs-Metriken | Methodik steht (`docs/metriken.md`); Werte nach 1. Training |

## Als Nächstes (kein Blocker)

| Prio | Entscheidung | Nächster Schritt |
| --- | --- | --- |
| 🔄 P1 | **Ereignis-Persistenz** — KV-Adapter fertig implementiert (Upstash-REST ohne Zusatzpaket, In-Memory-Fallback, Store-Ausfall blockiert Ingest nie); **aktiviert sich selbst**, sobald der Betreiber einen Vercel-KV-/Upstash-Store verknüpft (`KV_REST_API_URL`/`KV_REST_API_TOKEN` erscheinen dann automatisch) | `lib/events.ts`; letzter Schritt: Betreiber legt den Store im Vercel-Dashboard an (Storage → Create → Upstash Redis, Projekt verknüpfen) |
| 🔄 P1 | **Quittierungs-getriebene Nacht-Eskalation mit lokalem Weckkanal** — bleibt ein dringender Alarm N Minuten unquittiert: Push wiederholen (+5) → zweiter Empfänger (+10) → **lokaler Weckton per MQTT (+15), Gerät im Wohnhaus**. Marktbefund August 2026: *niemand* eskaliert auf ausbleibende Reaktion; der Autodialer mit Funk-Summer ist der ehrlichste Vergleichsmaßstab für den Nacht-Alarm | **Implementierungsreif spezifiziert** in [`eskalationskette-spezifikation.md`](./eskalationskette-spezifikation.md) (Stufenzeiten aus dem geburtshilflichen Zeitbudget, MQTT-Vertrag mit vier Ausschaltwegen, Neustart-Sicherheit, 21 Abnahmekriterien; Entwurf: Agent `ki-wache`, Stufenlogik in 27 Simulationen belegt). **Reihenfolge: KV-Store verknüpfen → Stufen 1–2 scharf → 7 Nächte Fehlalarmrate messen → Weckton scharf.** Ohne Ereignis-Persistenz (Zeile darüber) meldet eine andere Serverless-Instanz „ID unbekannt" und die Kette eskaliert trotz Quittierung — deshalb bleibt `weckruf.aktiv: false`, bis der Store steht |
| ⏳ P1 | **Weckkanal-Einkaufsliste in die README** — Zwischenstecker mit geräteseitiger Abschaltzeit (Shelly Gen2 `toggle_after`, ab 17,79 €) + **tieffrequentes** Weckgerät oder Vibrationskissen (6–30 €) + lokaler Quittierungs-Taster (~18 €), zusammen ~66 € einmalig | Zwei Befunde aus der Weckkanal-Recherche machen das zur P1: Ein 3100-Hz-Piepser weckt viele Menschen **selbst bei 95 dB(A) am Kopfkissen nicht** (520 Hz ist 4–12× wirksamer), und ein Weckton ohne physischen Stopp-Taster wird beim ersten Fehlalarm abgeklemmt. Ohne die Festlegung ist die Weckton-Stufe ein Versprechen an Hardware, die vielleicht nicht weckt. Begründung: `wettbewerbsanalyse.md` §1d |
| ⏳ P2 | **Notstrom-Lücke schließen bzw. aussprechen** — USV (~40 €) an Rechner, Router und Broker; bis dahin die Lücke in README und Tagesbericht benennen | Bei Stromausfall ist die ganze Kette tot, und der Totmann-Wächter kann es nicht melden, weil der Uplink mit ausfällt — der stille Ausfall aus Vision-Prinzip 6 eine Ebene tiefer. Die Nachbarkategorie hat das gelöst: Fachliteratur fordert ≥ 2 h, das Agrar-Wählgerät liefert 30 h, der Sigloo-Empfänger 36–48 h. Risiko 13 der Eskalations-Spezifikation |
| ⏳ P2 | **Migration `middleware.ts` → `proxy.ts`** — Next 16 meldet die Konvention als veraltet. An dieser einen Datei hängen **beide** Schutzmechanismen: der Session-Schutz der ganzen App *und* die Ausnahme für `/sw.js`. Fällt die Konvention in einem künftigen Major weg, verschwinden beide gleichzeitig und lautlos | Umbenennen, Build prüfen, danach zwingend die Auth-Kette **und** `/sw.js` mit gesetztem `STALLBLICK_PASSWORT` gegenprüfen (Agent `qa-waechter`, Punkte 2 und 6) |
| ⏳ P2 | **Alarmweg-TÜV** — Zustandsanzeige *gesendet → zugestellt → quittiert* je Alarm, dazu ein wöchentlicher automatischer Probealarm über die ganze Kette | Der manuelle Probealarm existiert (`POST /api/push/test`); es fehlen Zeitplan und Statusfeld. Setzt Push-Go-Live voraus (Skill `push-live-schalten`) |

## Blockiert (wartet auf Voraussetzung)

| Prio | Entscheidung | Blocker |
| --- | --- | --- |
| 🔒 P1 | **Festliege-Wächter** (Downer-Cow-Alarm) — Alleinstellung, kein Kamera-Produkt hat das; **implementierungsreif spezifiziert** in [`festliege-spezifikation.md`](./festliege-spezifikation.md) (Regeln, Config, Alarmtexte, Abnahmekriterien; Entwurf: Agent `ki-wache`) | erstes trainiertes Modell; Seitenlage-Alarm zusätzlich Klasse `kuh_seitenlage` im 2. Training |
| 🔒 P2 | Zwei-Kamera-Brunst-Fusion — **implementierungsreif spezifiziert** in [`brunst-fusion-spezifikation.md`](./brunst-fusion-spezifikation.md) (MQTT-Peer-Topologie, Zeit-Koinzidenz 30 s, annotieren/plausibilisieren-Modi mit Recall-Ventil; Entwurf: Agent `ki-wache`) | erstes trainiertes Modell + beide Kameras sehen dieselbe Bucht + Mosquitto-Broker |
| 🔒 P3 | **Automatische Kalbe-Akte** — **implementierungsreif spezifiziert** in [`kalbe-akte-spezifikation.md`](./kalbe-akte-spezifikation.md) (Teil-Akte ab erstem Modell, Voll-Akte „Kalb steht seit 04:32" mit Klassen `kalb_liegend`/`kalb_stehend` im 2. Training; stille Zustellung, Stallbuch-Format) | erstes trainiertes Modell (Teil-Akte); 2. Training (Voll-Akte) |
| 🔄 P3 | 7-Tage-Aktivitäts-Trend je Bucht | **Gebaut** im Analytik-Bereich (Verlauf + Auswertung nach Kamera). Die *Tiefe* hängt weiter an der Ereignis-Persistenz (P1): Ohne KV-Store reicht der Instanz-Ringpuffer nicht über 30 Tage, und ein Instanzwechsel setzt ihn zurück. Die Seite weist das unter „Datenbasis" selbst aus, statt einen lückenhaften Verlauf als vollständig zu zeigen |
| 🔒 P3 | **Nacht-Ruhefenster + veröffentlichte Alarmqualität** — „weckt" gegen „kann warten" als explizite Klassen; Fehlalarme pro Nacht sichtbar in App und `metriken.md`. Kein Hersteller veröffentlicht diese Zahl, CowManagers Snooze ist der einzige Anti-Müdigkeits-Mechanismus am Markt | Die Dringlichkeitsklassen bestehen bereits (Austreibung vs. Rest); die **Kennzahl** setzt das erste Modell und laufende Fehlalarm-Triage voraus |
| 🔒 P3 | Lahmheits-Frühwarnung (Rückenlinien-Winkel) — **implementierungsreif spezifiziert** in [`lahmheit-spezifikation.md`](./lahmheit-spezifikation.md) (Hinweis statt Alarm, Tages-Median 170°/174°-Hysterese, Kalbe-Sperre, Kamera-Kalibrierprobe; Entwurf: Agent `ki-wache`) | Keypoint `spine_mid` im 2. Training; eigene Validierung (≥ 3 bestätigte Fälle); stabiler Kalbe-/Brunst-Betrieb |

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
