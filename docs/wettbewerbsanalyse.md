# Wettbewerbsanalyse: KI als „Drittes Auge" im Stall

Stand: Juli 2026 · Kontext: Stallblick/KI-Wache (dieses Repo) — kamerabasierte
Brunst- & Kalbeerkennung als 0-€-DIY-Stack (vorhandene Kameras, alter Rechner,
Colab-Training, Telegram, Vercel-Dashboard).

## 1. Wettbewerber im Überblick

| System | Ansatz | Fokus | Kosten (Größenordnung) |
| --- | --- | --- | --- |
| **Lely Zeta** (AI Calving) | Deckenmodul: Kamera + LED + Mini-Computer, Analyse **in der Lely-Cloud** (Anbindung per Datenkabel/WLAN), 1 Leuchte ≈ 10 Tiere | Kalbung: Wehen-Score, Phasen, Komplikations-Alarm; „Full-Moon"-Nachtmodus | Weiter 8 Testbetriebe NL; UK-Launch Kalbemodul 2026, **breite kommerzielle Verfügbarkeit erst ~2027 erwartet**; Gerät + Abo, Preis weiter offen |
| **GEA CattleEye** | Kamera über Treibgang, Cloud-SaaS (seit 2024 zu GEA); Ausgabe als **Tagesbericht/Dashboard, nicht als Nachtalarm** | Lahmheit, BCS; Liverpool-Studie 07/2026 belegt Reduktion schwerer Lahmheit; >250.000 Kühe | Einstieg ab ~300–400 $ Hardware + SaaS-Abo |
| **Ever.Ag Maternity Warden** | Kameras + Edge-Nodes in Abkalbebucht, **Videoverarbeitung nachweislich lokal** („footage remains onsite"); Alarm bei 3 Ereignissen in 20 min, 30-s-Clip über die Vault-App | Kalbe-Alarme (Schwanzheben, Wehen, Fruchtteile), >95 % Genauigkeit, >100.000 Kühe | ~5.000 $ System + 0,50 $/Kuh/Monat |
| **Cattle Care OmniCalf** | Kameras Abkalbe-/Kälberbereich, **Analyse auf Cattle-Care-Servern (Cloud)**, Rohvideo bleibt lokal; dringende Fälle per **SMS mit Videolink** | Kalbeverlust-Prävention + Arbeitsprotokoll-Kontrolle (Tubing, Nabeldesinfektion, Handling) | SaaS, Preis nur nach Gespräch |
| **smaXtec** | Pansen-Bolus (invasiv), Base Station → Cloud (Upload ~alle 30 min) | Brunst, Gesundheit, Kalbung (Körpertemperatur), Alarm bis ~15 h vorher | ~2.450 € Infrastruktur + ~36 €/Kuh/Jahr Basis; UK-Praxisbeleg 2026: ~14.500 £ Einrichtung + 2,50–3,00 £/Bolus/Monat |
| **SenseHub (Allflex)** | Ohrmarke/Halsband | Brunst, Gesundheit | 19–28 €/Kuh/Jahr |
| **Moocall** | Schwanz-Sensor (angeklemmt) mit **eigener Vodafone-Roaming-SIM** | Kalbung (Schwanzbewegung), 2-stufiger Alarm 1–2 h vorher | ~166 € inkl. 1 Jahr Daten, danach ~162 €/Jahr Abo; UK-Preispunkt 2026: 239 £ Gerät + 120 £/Gerät/Jahr |
| **Dilepix** (FR) | Feste Stall-Kameras (auch Thermal) + KI-Videoanalyse als Dienst | Brunst-Erkennung 24/7 mit Sofort-Alarm, separates Kalbe-Modul | SaaS, Preis auf Anfrage |
| **Kuhtracking** (Mechatronik Austria + Cognify, AT) | Rein kamerabasiert, Einzeltier-Tracking per KI, App-Alarm | Kalbung, Brunst, Krankheit/Verletzung; Zielgruppe Nebenerwerbsbetriebe | FFG-Forschungsprojekt (1 Mio. € gefördert), 10 Pilotbetriebe Pinzgau, noch kein Marktprodukt |
| **MyAnIML** (US) | Kamera aufs Flotzmaul (Muzzle-Analyse) | Krankheits-Vorhersage Tage vor Symptomen (Beef-Fokus) | Kommerziell, Preis auf Anfrage |
| **dsp-Agrosoft COW-AI** | Kamera über Laufgang (4,5–6 m) + Ohrmarken-Kamera zur Tier-ID | Lahmheit (automatisch, im Laufbereich) | Abo-Modell, Preis auf Anfrage |
| **DeLaval BCS-Kamera** | 3D-Kamera über Selektionstor/VMS-Ausgang | Body Condition Score (täglich, automatisch) | Gerätekauf + DelPro-Bindung, Preis über Händler |
| **CowManager** | Ohrsensor (Temperatur, Wiederkauen, Aktivität) | Brunst, Gesundheit (1–2 Tage Vorlauf), Transition | ~30 €/Sensor + Abo pro Kuh/Monat je Modul |
| **Nedap CowControl** | Hals-/Fußband-SmartTag + Ortungs-Infrastruktur | Brunst inkl. Besamungszeitpunkt, Gesundheit, Kuh-Ortung | ~118 €/Tier (Tag) + Infrastruktur |
| **HerdVision** | Stereo-3D-Kamera am Melkstand-Ausgang, EID-Tag-ID | BCS + Mobility-Score; DairyComp-Integration angekündigt | ~£5.900 + Abo (1. Jahr frei) |
| **Mozaë** (FR) | Schwanzsensor bzw. Halsband + Basisstation (Reichweite bis ~700 ha) | Kalbung (2 Alarme: Geburtsbeginn, Schwergeburt), danach Brunst-Modus | SMS + Push, Preis auf Anfrage |
| **VikingGenetics CowFIT** | 3D-Kamera + Deep Learning, berührungslose Waage | Tiergewicht täglich (Energiebilanz) | Kommerzielles System, Preis auf Anfrage |

Kommerzielle Kamera-Komplettsysteme liegen laut Wissenspaket bei **45.000–75.000 €**
Investition; Sensor-Systeme kosten laufend pro Kuh. Der DIY-Ansatz (dieses Repo)
liegt bei **0–2.000 €** einmalig und **0 €/Kuh/Jahr** — bei ~370–400 € Mehrwert
pro Kuh und Jahr amortisiert er sich sofort.

## 1b. Open-Source-/DIY-Schiene (der eigentliche Vergleichsmaßstab)

Was ein technikaffiner Landwirt heute selbst aufsetzen könnte — recherchiert
durch den Subagenten `markt-analyst`:

| System | Ansatz | Fürs Kalbe-/Brunst-Szenario | Kosten |
| --- | --- | --- | --- |
| **Frigate NVR (+ Frigate+)** | Open-Source-NVR, lokale Objekterkennung (COCO inkl. „cow"), Zonen, MQTT/Home Assistant | „Kuh anwesend", nicht „Kuh kalbt" — keine Pose/Verhaltenslogik | Kostenlos; Fine-Tuning nur via Frigate+-Abo 50 $/Jahr (ohne Nutztier-Labels) |
| **Viseron** | Self-hosted NVR (MIT), YOLOv3–v7/Coral, natives Telegram + MQTT | Generische Objekterkennung, kein Tierverhalten | Kostenlos |
| **Home Assistant + Kamera** | Smart-Home-Plattform als Alarmweg, Eigenbau-Automatisierungen | Keine Stall-Blueprints — Status quo bleibt „Stream aufs Handy + selber gucken" | Kostenlos, hoher Pflegeaufwand |
| **CowCatcherAI (+ CalvingCatcher AI)** | YOLO/ONNX-Tool (Exe/Docker) + RTSP + Telegram-Fotoalarm; V16 (01/2025) weiterhin **letztes GitHub-Release**, AGPL-3.0. CalvingCatcher erkennt Kalbe-Stadien, hat aber **kein eigenes Repo und kein Release** — Auslieferung über Modell/Config, Support per Telegram-Gruppe | Direktester DIY-Konkurrent bleibt auf der Erkennungsebene stehen: ein Kanal, ein Foto, keine Eskalation, keine Quittierung, kein Puffer, keine App | Kostenlos |
| **Forschungs-Repos** (YOLO-TransT, IPCLab-NEAU, CattleSense, CalvingDetection) | Paper-Begleitcode: Brunst-Tracking, Mounting-Detektion, Pose-Verhalten | Methodik-Beleg für den Pose-Ansatz, aber kein Produkt (kein Alarmweg, keine Wartung) | Kostenlos (Research) |

**Kernbefunde:**
- Es existiert **kein produktionsreifes Open-Source-Projekt für kamerabasierte
  Kalbeerkennung** — genau diese Lücke füllt Stallblick.
- NVRs erkennen *Objekte*, Stallblick erkennt *Verhaltensphasen* — Stallblick
  ist kein NVR-Konkurrent, sondern die Schicht darüber (läuft parallel auf
  denselben RTSP-Streams).
- Der reale Gegner des Zielkunden ist das **nächtliche Selber-Gucken**
  (Streaming-Barncams ohne KI).
- Selbst im Open-Source-Lager wird Modellpflege zum Abo (Frigate+ 50 $/Jahr);
  die DIY-KI-Kette hat brüchige Glieder (CodeProject.AI verwaist) — Stallblicks
  schlanker, reproduzierbarer Eigen-Stack ist ein Robustheits-Argument.
- **Update Juli 2026:** CalvingCatcher AI (CowCatcherAI-Familie) erkennt jetzt
  ebenfalls Geburtsstadien — der Vorsprung „wir haben Phasen, die nur Boxen"
  schrumpft. Stallblicks Differenzierung verlagert sich auf die
  **Logik-Schicht** (Eskalation, Wach-Modus, Digest, Persistenz, Metriken) und
  auf Features, die niemand hat (Abschnitt 4b).

## 1c. Alarmweg & App-Ebene (Stand August 2026)

Die landwirt-zugewandte Schicht — bis August 2026 blinder Fleck dieser Datei,
recherchiert durch den Subagenten `markt-analyst`. **„Keine öffentliche
Aussage gefunden"** heißt: Der Hersteller kommuniziert es nicht öffentlich.
Das ist kein Beleg für Abwesenheit des Features — aber es ist ein Beleg
dafür, dass er es nicht für verkaufsrelevant hält.

| System | Alarmweg | Beleg am Alarm | Offline-Verhalten |
| --- | --- | --- | --- |
| **Lely Zeta** | Push über Lely Horizon; zweistufig: Meldung bei Kalbebeginn, **Alarm bei Komplikation**. Pro Alarmtyp einstellbar, **wer** ihn **wann** bekommt (Nutzer + Zeitplan) — die ausgereifteste Empfänger-Rota am Markt. Quittierung: keine öffentliche Aussage | **Live-Feed** aufs Smartphone + Wehen-Score; LED mit „Full-Moon"-Nachtmodus. Kein Bild-/Clip-Anhang dokumentiert | KI läuft **in der Lely-Cloud**, nicht am Edge. Netzausfall: keine öffentliche Aussage |
| **Ever.Ag Maternity Warden** | „alarmiert unmittelbar das zuständige Personal" über die Vault-App. Kanal, Eskalation, Quittierung: keine öffentliche Aussage | **30-s-Videoclip** + benanntes Verhalten + Position in der Bucht; Auslöser 3 Anzeichen in 20 min | **Videoverarbeitung explizit lokal** („footage remains onsite"). Ob **Alarme** bei Internetausfall zugestellt werden: keine öffentliche Aussage |
| **Cattle Care OmniCalf** | **SMS mit Direktlink** zum Videobericht bei dringenden Verstößen; Regelbetrieb ist ein Dashboard-Bericht, kein Weckruf | **Videoclip** des Vorfalls, teilbar (auch als Mitarbeiter-Nachweis) | Analyse **auf Cattle-Care-Servern**; Rohvideo bleibt lokal. Bandbreite/Netzausfall: keine öffentliche Aussage |
| **Dilepix** | „Alarm in Echtzeit" — Kanal nicht benannt | keine öffentliche Aussage | keine öffentliche Aussage (weder Edge- noch Cloud-Architektur dokumentiert) |
| **Moocall** | **SMS an bis zu 2 Nummern** + App-Push + E-Mail. **Zweistufig** nach Wehenstadium, nicht nach Reaktion | Kein Bild — reiner Text | **Eigene Roaming-SIM (GSM)**, unabhängig vom Hof-WLAN — die einzige echte Kanal-Redundanz am Markt. Ohne Mobilfunk kein Alarm; Zwischenspeicherung: keine öffentliche Aussage |
| **smaXtec** | Push **oder** E-Mail, pro Meldungstyp wählbar; Kalbealarm bis ~15 h vorher | Kein Bild — Temperaturkurve in der App | Bolus puffert 6 Tage intern, Base Station sendet ~alle 30 min. Die App erfasst offline **Dateneingaben**, nicht Alarmzustellung |
| **SenseHub (Allflex/MSD)** | Feinstes Routing am Markt: E-Mail, SMS **oder** Push pro Alarmtyp; eigene „Distress Alerts" mit **einstellbarer Empfindlichkeit** | Kein Bild (Ohrmarke) | **Einzige explizite Offline-Zusage der Branche**: App 8.3.3 (04/2025) verspricht Alarme „regardless of Internet Connectivity" + Konnektivitätsbericht |
| **CowManager** | Push + Web; seit 07/2025 auch Kalbe-Benachrichtigungen. **Snooze/Entfernen von Alarmen** — der einzige dokumentierte Anti-Alarmmüdigkeits-Mechanismus am Markt | Kein Bild (Ohrsensor) | App meldet Verbindungsverlust und **wiederholt automatisch**, zeigt gecachte Seiten. Sensor-Router bei Netzausfall: keine öffentliche Aussage |
| **Nedap CowControl** | Push + priorisierte Tages-„Attention Lists" | Kein Bild | „on-premise reliability + Cloud-Skalierung"; Push bei Internetausfall: keine öffentliche Aussage |
| **GEA CattleEye** | **Tagesberichte im Dashboard** — Berichtsrhythmus, ausdrücklich kein Nachtwecker | Widgets, kein Clip am Alarm | Cloud-Plattform; keine öffentliche Aussage |
| **CowCatcherAI / CalvingCatcher** (DIY) | **Telegram-Foto**, genau ein Kanal, keine Stufen. Keine Eskalation, keine Quittierung, **keine App** | Annotiertes **Einzelfoto** | Analyse vollständig lokal — aber die **Zustellung** hängt an Telegram: kein Puffer, keine Nachlieferung, kein Offline-UI |
| **Stall-Autodialer** (Sensaphone, FarmAlarm, Agralarm, SmartBarn) — Nachbarkategorie ohne KI | **Automatischer Telefonanruf** an mehrere Nummern nacheinander, bis jemand abnimmt, dazu SMS/E-Mail | Kein Bild (Klima-/Strom-/Füllstandsalarme) | **Lokaler Funk-Summer (bis ~450 m), der auch schrillt, wenn das Telefonnetz tot ist** — der Referenzstandard für „wer weckt nachts zuverlässig" |

### Der eigentliche Befund: Die Branche verkauft Erkennung, nicht Zustellung

Fünf Fragen, fünf Antworten — und in der Summe eine Lücke, die größer ist als
jedes einzelne Feature:

1. **Niemand eskaliert, weil niemand reagiert hat.** Lely eskaliert
   *inhaltlich* (Komplikation erkannt), Moocall *nach Stadium*. Eine
   Eskalation, die auf **ausbleibende Quittierung** reagiert, gibt es bei
   keinem recherchierten System — und eine Quittierung überhaupt ist bei
   keinem öffentlich dokumentiert. Der Alarm gilt als zugestellt, sobald er
   abgeschickt ist.
2. **Belege am Alarm sind selten.** Nur Ever.Ag (30-s-Clip), Cattle Care
   (SMS-Link) und Lely (Live-Feed) liefern Bildmaterial. Lelys Live-Feed ist
   im Funkloch wertlos — er muss beim Öffnen streamen. Alle Sensorsysteme
   senden reinen Text.
3. **Offline ist der blinde Fleck der Kamera-Systeme.** Genau zwei explizite
   Offline-Zusagen existieren am ganzen Markt (SenseHub, CowManager) — beide
   aus dem *Sensor*-Lager, beide nur auf App-Ebene. Bei **keinem** der
   kamerabasierten KI-Systeme findet sich eine Aussage zum Netzausfall im
   Stall. Ever.Ag ist der aufschlussreichste Fall: lokale Verarbeitung wird
   beworben, über die Zustellung schweigt der Hersteller. **Ein Anbieter, der
   Ereignisse puffert und mit Original-Zeitstempel nachliefert, ist in der
   öffentlichen Kommunikation nicht auffindbar.**
4. **Kein Hersteller veröffentlicht Fehlalarme pro Nacht.** Die einzige Zahl
   am Markt ist Ever.Ags „>95 % Genauigkeit" — und das ist keine
   Fehlalarmrate. Die Literatur liefert derweil harte Zahlen: im Mittel
   2,7 Alarme pro Kuh vor Stadium II, Falsch-Positiv-Raten von 6–50 % bei
   Schwanzsensoren, in einer Studie ein positiver Vorhersagewert von 3–4 %.
   Abgeschaltet wird Technik laut Praxisliteratur nicht wegen der Hardware,
   sondern weil der Prozess fehlt: *jeder Alarm braucht einen Besitzer und
   einen nächsten Schritt.*
5. **Keine PWA im Segment.** Durchweg native Apps (iOS/Android); reine
   Weboberflächen bei CattleEye und Cattle Care; gar keine App bei
   CowCatcherAI. Kehrseite: **kein Wettbewerber beansprucht iOS „Critical
   Alerts"** — dass Web-Push diese Stufe nicht erreicht und auf iOS die
   Installation voraussetzt, ist Plattformwissen, keine Wettbewerber-Schwäche.

**Schlussfolgerung für Stallblick.** Die gesamte Branche investiert in die
Frage *„erkennen wir es?"* und fast niemand in *„kommt die Nachricht an?"*.
Das ist keine Nachlässigkeit, sondern eine Folge der Geschäftsmodelle:
Erkennungsqualität lässt sich in einer Broschüre versprechen, Zustellung
zeigt sich erst um drei Uhr früh beim Kunden. Genau dort liegt unsere fünfte
Vision-Ebene **„Durchhalten"** — und genau deshalb ist der ehrlichste
Vergleichsmaßstab für den Nacht-Alarm nicht Lely oder Ever.Ag, sondern der
**Autodialer mit Funk-Summer**: ein Gerät ohne jede KI, das die eine Aufgabe
erfüllt, an der die KI-Systeme schweigen — jemanden wecken, auch wenn das
Netz tot ist.

## 2. Was die Konkurrenz besser macht (und was wir davon übernehmen)

1. **Lely Zeta: Komplikations-Alarm** („Alarm, wenn der Geburtsvorgang zu lange
   dauert"). Das ist der wertvollste Einzelmechanismus am Markt: nicht nur
   *erkennen*, sondern *eskalieren*, wenn nach Austreibungsbeginn kein
   Fortschritt sichtbar ist. → **übernehmen (P1)**.
2. **Ever.Ag: Beweisbilder beim Alarm** (zeitgestempelte Clips). Wir senden
   bereits ein annotiertes Foto per Telegram; eine kurze Bildserie
   (3–5 Frames) macht Fehlalarme sofort am Handy erkennbar. → **übernehmen (P2)**.
3. **CattleEye: Lahmheit aus Rückenlinie**. Unsere Pose-Keypoints (Rückenlinie)
   liefern die Datengrundlage dafür fast gratis mit (Cobb-Winkel < 170° als
   Frühindikator). → **Roadmap (P3)**, kein MVP-Thema.
4. **Forschung Brunsterkennung: Zwei-Kamera-Fusion** (Ensemble zweier
   Blickwinkel steigert die Duldungs-Erkennung deutlich). Wir *haben* zwei
   Kameras (Stallwache + Futterwache). → **übernehmen (P2)**.
5. **CowManager: Transition-Monitor** (erhöhte Wachsamkeit um den
   Geburtstermin). Stallblick-Übersetzung: manueller **„Wach-Modus"** pro
   Bucht — Landwirt schaltet die Abkalbebucht ~14 Tage vor Termin scharf,
   niedrigere Schwellen nur dort. → **übernehmen (P2)**.
6. **HerdVision: Trends statt Momentaufnahmen** (wöchentliche Score-Verläufe).
   Ein 7-Tage-Aktivitäts-Trend je Bucht aus persistierten Events ist fast
   gratis ableitbar. → **Roadmap (P3, setzt Persistenz voraus)**.
7. **CowFIT/CattleEye: Peer-Review als Vertrauensargument.** Der
   Open-Source-Gegenzug: eigene Precision/Recall-Werte auf annotierten
   Stall-Clips transparent im Repo dokumentieren. → **übernehmen (P3)**.
8. **Nedap: Ortung als Verkaufsschlager.** Stallblick markiert die Position
   bereits per Bounding-Box im Alarmbild — gehört in die Kommunikation,
   nicht in neue Features.
9. **Stall-Autodialer: der lokale Weckton.** Der ehrlichste Vergleichsmaßstab
   für den Nacht-Alarm ist kein KI-System, sondern ein Gerät ohne jede
   Intelligenz: der Autodialer mit Funk-Summer, der auch schrillt, wenn das
   Telefonnetz tot ist. Er erfüllt die eine Aufgabe, an der alle
   KI-Wettbewerber schweigen. → **übernehmen (P1, siehe Abschnitt 4)**.
10. **SenseHub/CowManager: Ehrlichkeit über die eigene Verbindung.**
    Konnektivitätsbericht und automatische Zustellwiederholung sind die
    einzigen Offline-Zusagen am Markt — beide aus dem Sensorlager. Für ein
    Kamera-System wäre das ein Alleinstellungsmerkmal.
    → **übernehmen (P2, Alarmweg-TÜV)**.

## 3. Was wir bewusst NICHT machen

- **Keine invasiven Sensoren** (Bolus/Ohrmarke): Kostenlawine pro Kuh/Jahr,
  Batterie-/Tierwohl-Themen — unser Differenzierer ist kamerabasiert + kostenlos.
- **Kein Abo-Modell / keine Cloud-Videoanalyse**: Edge-First bleibt gesetzt
  (Datenhoheit, kein Uplink-Problem, 0 € Laufkosten).
- **Keine Hardware-Verkäufe**: Anleitung statt Gerät („bring your own Rechner").
- **Kein Feature-Zoo im Dashboard**: Stallblick-Prinzip „Ruhe vor Fülle" gilt
  auch für die KI-Wache — Alarme müssen in 3 Sekunden erfassbar sein.
- **Keine BCS-/Gewichtsschätzung**: braucht 3D-Kameras bzw. kalibrierte
  Messpunkte — verletzt „vorhandene Hardware" (DeLaval/HerdVision/CowFIT-Terrain).
- **Keine tierindividuelle ID**: dsp-Agrosoft löst das mit einer zweiten
  Ohrmarken-Kamera; Stallblick bleibt ehrlich **buchtbasiert** in der Alarmierung.

## 4. Produktentscheidungen (priorisiert)

> Konsolidierter Umsetzungsstatus aller Entscheidungen:
> [`docs/roadmap.md`](./roadmap.md).

| Prio | Entscheidung | Begründung / Wettbewerbsbezug |
| --- | --- | --- |
| **P1** | **Eskalations-Alarm**: Austreibung erkannt, aber nach konfigurierbarer Zeit (Default 60 min) kein Kalb → zweiter, dringlicherer Alarm („Kontrolle nötig") | Lely Zeta; größter Nutzen pro Codezeile, rettet Kälber |
| **P1** | **Ereignis-Persistenz** im Dashboard (Vercel KV/Postgres statt In-Memory) | Alle SaaS-Wettbewerber haben Historie; ohne sie ist das Dashboard nur Momentaufnahme |
| **P2** | **Bildserie am Alarm** (3–5 Frames per Telegram-Album) | Ever.Ag; Fehlalarm-Triage am Handy |
| **P2** | **Zwei-Kamera-Brunst-Fusion**: Aufsprung nur melden, wenn von der Zweitkamera plausibilisiert (falls beide dieselbe Bucht sehen) | Forschungsstand; halbiert Fehlalarme |
| **P2** | **Täglicher Telegram-Digest** (1 Nachricht: Ereignisse, Agent-Uptime, Bildkontingent) | smaXtec/SenseHub-Apps; Vertrauen durch Routine |
| **P2** | **Wach-Modus pro Bucht**: manuell scharfschalten ~14 Tage vor Kalbetermin → gesenkte Schwellen/dichtere Frames nur dort | CowManager Transition-Monitor; nur ein Config-Flag, konform mit „Ruhe vor Fülle" |
| **P3** | **7-Tage-Aktivitäts-Trend je Bucht** (Sparkline aus persistierten Events) | HerdVision „Trends statt Momentaufnahmen"; setzt P1-Persistenz voraus |
| **P3** | **Öffentliche Erkennungs-Metriken** (Precision/Recall auf annotierten Stall-Clips im Repo) → Methodik & Vorlage: [`docs/metriken.md`](./metriken.md) | Peer-Review-Argument von CowFIT/CattleEye als Open-Source-Version; stärkstes Vertrauens-Feature gegen Blackbox-Abos |
| **P1** | **Positionierung „Verhaltens-Schicht, kein NVR"** prominent im README (Stallblick läuft neben Frigate auf denselben Streams) | Fängt technikaffine Landwirte ab, die zuerst Frigate googeln |
| **P2** | **Optionale MQTT-Event-Ausgabe** (ein Topic je Ereignis; Telegram bleibt der primäre Alarmweg) | Erschließt die Home-Assistant-Community als Multiplikator, Edge-konform, 0 € |
| **P3** | **Ein-Befehl-Setup** (geführtes Install-Skript inkl. Telegram-Bot-Assistent) | CowCatcherAI setzt die Onboarding-Messlatte („Exe + JSON") — bei gleichem Preis muss Stallblick im Aufwand vorn bleiben |
| **P3** | **Lahmheits-Frühwarnung** aus Rückenlinien-Winkel | CattleEye; Keypoints vorhanden, braucht aber eigene Validierung |
| **P3** | **BCS-Schätzung** (Body Condition) | DeLaval/CattleEye; erst nach stabilem Kalbe-/Brunst-Betrieb |


### Entscheidungen aus der Alarmweg-Analyse (August 2026)

Aus Abschnitt 1c abgeleitet — sie zielen alle auf dieselbe Marktlücke: Die
Branche verkauft Erkennung, niemand verkauft Zustellung.

| Prio | Entscheidung | Begründung / Wettbewerbsbezug |
| --- | --- | --- |
| **P1** | **Quittierungs-getriebene Nacht-Eskalation mit lokalem Weckkanal**: Bleibt ein dringender Alarm (Austreibung, Komplikation, Festliegen) N Minuten unquittiert → Push wiederholen, dann zweiter Empfänger, dann **lokaler Weckton per MQTT** (Funkgong/Summer **im Wohnhaus**, geschaltet über den Broker im Stall-LAN — nicht im Stall, siehe Architektur-Entscheidung) | Lely eskaliert inhaltlich, Moocall nach Stadium — **niemand eskaliert, weil niemand reagiert hat**. Die Autodialer-Nachbarkategorie beweist mit ihrem Funk-Summer, dass Landwirte genau für den Kanal zahlen, der bei totem Netz noch funktioniert. Quittierung und MQTT sind gebaut; es fehlt die Kette dazwischen |
| **P2** | **Alarmweg-TÜV**: pro Alarm sichtbarer Zustand *gesendet → zugestellt → quittiert*, dazu ein automatischer Probealarm pro Woche zur festen Uhrzeit, der die ganze Kette Agent → Push → Gerät durchläuft | SenseHub ist der Einzige, der Zustellprobleme überhaupt thematisiert (Konnektivitätsbericht). Wer Nachtwache verspricht, muss beweisen, dass Stille „alles ruhig" heißt und nicht „Kette tot". Setzt Vision-Nordstern „die Kette ist jederzeit beweisbar" um; der manuelle Probealarm existiert bereits |
| **P3** | **Nacht-Ruhefenster + veröffentlichte Alarmqualität**: „weckt" gegen „kann warten" als explizite Klassen, stille Sammlung außerhalb der Dringlichkeit, und die aus der Feedback-Schleife ohnehin anfallende Kennzahl *Fehlalarme pro Nacht* sichtbar in App und `metriken.md` | **Kein Hersteller veröffentlicht Fehlalarme pro Nacht**; CowManagers Snooze ist der einzige Anti-Müdigkeits-Mechanismus am Markt. Die Literatur (2,7 Alarme/Kuh, Falsch-Positiv-Raten bis 50 %, PPV teils 3–4 %) macht „Ruhe vor Fülle" vom Designprinzip zum messbaren Verkaufsargument |

**Architektur-Entscheidung zur Eskalation (P1): Sie gehört an den Edge, nicht
in die Cloud.** Das ist nicht offensichtlich — die Quittierung passiert in der
App, also läge die Eskalationslogik dort scheinbar näher. Sie wäre dort aber
genau dann wirkungslos, wenn sie gebraucht wird: Fällt die Leitung aus, kann
die Cloud weder feststellen, ob der Landwirt geweckt wurde, noch eine Sirene
im Stall auslösen. Deshalb:

- Der **Edge-Agent** hält den Eskalationstimer und fragt die App, ob der Alarm
  quittiert wurde (er spricht ohnehin mit ihr).
- **Erreicht er die App nicht, gilt der Alarm als unquittiert** und die
  Eskalation läuft. Der Fehlerfall führt zum Wecken, nicht zum Schweigen —
  ein Weckton zu viel ist verzeihlich, eine verpasste Kalbung nicht.
- Der lokale Weckkanal läuft über **MQTT im Stall-LAN**, nicht über Tuya:
  Tuya ist cloudgebunden und fällt mit derselben Leitung aus wie alles andere.
  Die Tuya-Steckdose bleibt der Komfortweg für den Normalfall.
- **Das Weckgerät hängt im Wohnhaus, nicht im Stall.** Diese Korrektur kam aus
  der Fachprüfung durch den Agenten `ki-wache` und war nicht offensichtlich:
  Stress im Stadium II hemmt die Oxytocin-Ausschüttung — eine Sirene über der
  kalbenden Kuh kann die Austreibung verzögern und damit genau das Kalb
  gefährden, das der Alarm retten soll. Dazu Vision-Prinzip 4 („Tierwohl ohne
  Eingriff"). Der Autodialer als Vergleichsmaßstab macht es genauso: Sein
  Funk-Summer hängt in der Wohnung. Steht ausnahmsweise nur ein Gerät im Stall
  zur Verfügung: **Lampe statt Ton.**

Damit ist die Eskalation der erste Baustein, der **vollständig ohne Internet**
funktioniert — Kamera, Erkennung, Entscheidung und Weckruf liegen alle auf dem
Hof. Das ist die konsequente Fortsetzung von Vision-Ebene „Durchhalten".

Implementierungsreife Ausarbeitung (Stufenzeiten aus dem geburtshilflichen
Zeitbudget, MQTT-Vertrag mit vier Ausschaltwegen, Neustart-Sicherheit,
21 Abnahmekriterien, 12 Risiken):
[`eskalationskette-spezifikation.md`](./eskalationskette-spezifikation.md).

## 4b. Alleinstellungs-Features (Juli 2026): Was NIEMAND bietet

Ergebnis der gezielten Lückensuche durch den `markt-analyst` — drei Features,
die kein Wettbewerber (kommerziell oder DIY) hat und die mit unserer
Architektur zum Nulltarif machbar sind:

| Prio | Feature | Aufwand | Warum es niemand hat / Prinzipien-Fit |
| --- | --- | --- | --- |
| **P1** | **Festliege-Wächter (Downer-Cow-Alarm)**: Kuh in Seitenlage oder länger als konfigurierbare Zeit ohne Aufstehen (v. a. nach erkannter Kalbung → Milchfieber-Fenster) → dringlicher Alarm | M | Kein Kamera-Produkt adressiert Festliegen explizit; Sensorik (smaXtec/Nedap) erkennt es nur indirekt, Lely Zeta nur den Geburtsprozess. Unsere Pose-Keypoints unterscheiden Brust- von Seitenlage fast gratis — ein Alarm, der Kühe rettet |
| **P2** | **Ein-Tipp-Feedback-Schleife**: Inline-Buttons „Treffer/Fehlalarm" unter jedem Telegram-Alarm; Fehlalarm-Frames landen automatisch als Hard Negatives im Trainingsordner fürs nächste Colab-Retraining | S | Kein Wettbewerber lässt den Landwirt das Modell verbessern — SaaS trainiert zentral (Blackbox), CowCatcherAI hat keinen Feedback-Kanal. Nur Stallblick besitzt die offene Kette Kamera→Modell→Training; zahlt direkt auf „<1 Fehlalarm/Nacht" ein (Prozedur: Skill `fehlalarm-triage`) |
| **P2** | **Stream-Totmann-Meldung**: genau eine Telegram-Nachricht, wenn ein Kamerastream >5 min ausfällt („Das dritte Auge ist blind") | S | Kein Kalbe-Wettbewerber kommuniziert Ausfälle aktiv; für ein Nachtwach-Versprechen ist das ein Vertrauens-Feature — Schweigen darf nicht fälschlich „alles ruhig" bedeuten. Modellunabhängig, läuft schon im Silent Mode |
| **P3** | **Automatische Kalbe-Akte**: nach Abschluss einer Kalbung EINE Telegram-Zusammenfassung mit Zeitstempeln aller Phasen (Unruhe → Austreibung → Kalb sichtbar → Kalb steht) + 3 Belegbildern, kopierbar fürs Stallbuch | S–M | Alle Wettbewerber alarmieren nur *live*; automatische Geburts-Dokumentation bietet niemand. „Kalb steht seit 04:32" ist die erste *Entwarnungs*-Nachricht der Branche. Setzt Ereignis-Persistenz voraus |

**Termin-Hinweis:** EuroTier 10.–13.11.2026 (Leitthema „Intelligence in Animal
Farming"); dort werden 3D-Kamera-Systeme zur Kalbe-Vorhersage erwartet —
**Wettbewerbs-Check im November/Dezember 2026 wiederholen** (vermutlich
Lely-Zeta-Marktstart und Kuhtracking-Kommerzialisierung; zusätzlich
Nachbarmarkt Pferd live verifizieren, s. u.).

## 4c. Nachbarmarkt Abfohlen (Ausblick, Stand ~01/2026 — nicht live verifiziert)

Analyse Juli 2026 (`markt-analyst`; Web-Tools am Limit, Zahlen aus der
Wissensbasis — beim Nov-Check verifizieren). Der Pferde-Abfohlmarkt ist
sensor-dominiert und teuer, ein offenes Edge-Kamera-KI-Produkt fehlt:

| System | Ansatz | Fokus | Kosten (Größenordnung) |
| --- | --- | --- | --- |
| **Foalert** (US) | An Vulvalippen genähter Magnetkontakt (invasiv, Tierarzt) + Funk | Alarm exakt bei Geburtsbeginn | ~1.000–1.500 $ |
| **Birth Alarm** (NL) | Obergurt-Lagesensor (Seitenlage = Wehen) + GSM | Vorzeichen-Alarm; Fehlalarme durch Wälzen | ~500–700 € |
| **Magic AI** (UK) | KI-Stallkamera, Cloud + Abo | Verhalten/Kolik; Gegenmodell zu Edge-First | Abo |
| **Abfohlkameras (Gattung)** | IP-Kamera + Mensch am Monitor | Status quo, keine KI | 100–300 € |

**Produktentscheidung** (Details und Begründung: [`vision.md`](./vision.md)):
Pferde-Abfohlen = dokumentierte **Zweitmarkt-Option nach Modell v1**
(Logik-Schicht tierartagnostisch, Festliege-Seitenlage ≈ Birth-Alarm-Signal);
Schaf/Ziege = **Nicht-Ziel**. Kein Code jetzt — „Ruhe vor Fülle" gilt auch
für die Roadmap.

**Positionierung in einem Satz:** *Stallblick ist das kostenlose, offene
„Dritte Auge" für kleine Betriebe — dieselben Kalbe- und Brunst-Alarme wie die
45.000-€-Systeme, auf der Hardware, die schon im Stall liegt.*

## 5. Quellen

- [Elite Magazin: Intelligente Kameras – Überwachung ohne Kuhkontakt](https://www.elite-magazin.de/herdenmanagement/intelligente-kameras-uberwachung-ohne-kuhkontakt-31140.html)
- [Lely Zeta – AI Calving & Barn Monitor](https://www.lely.com/solutions/latest-innovations/zeta/)
- [Farmers Weekly: AI calving monitor debuts at Dairy Day](https://www.fwi.co.uk/livestock/dairy/artificial-intelligence-calving-monitor-debuts-at-dairy-day)
- [Dairy Herd: The Rise of AI-Powered Smart Cameras in Dairy Farming](https://www.dairyherd.com/news/dairy-production/rise-ai-powered-smart-cameras-dairy-farming)
- [Cattle Care (OmniCalf)](https://www.cattle-care.com/)
- [Studie: Estrus-Erkennung durch Ensemble-Fusion zweier Kamerablickwinkel](https://pmc.ncbi.nlm.nih.gov/articles/PMC12810773/)
- [agrarheute: Brunsterkennung beim Rind – 11 Systeme im Überblick](https://www.agrarheute.com/tier/rind/brunsterkennung-beim-rind-11-systeme-ueberblick-575155)
- [smaXtec – Früherkennung mit Bolus-Technologie](https://www.smaxtec.com/de/)
- [Elite Magazin: Elf Sensoren unter der Lupe](https://www.elite-magazin.de/tiergesundheit/elf-sensoren-unter-der-lupe-23262.html)
- [dsp-Agrosoft COW-AI](https://www.dsp-agrosoft.de/produkte/cowai/)
- [DeLaval BCS-Kamera](https://www.delaval.com/de/unsere-losungen/farmmanagement/delaval-delpro/delaval-body-condition-scoring-kamera-bcs/)
- [CowManager: System & Preise](https://www.cowmanager.com/cow-management/pricing-options/)
- [Nedap CowControl](https://nedap-livestockmanagement.com/de/losungen/nedap-cowcontrol/)
- [LK NÖ: Wenn die Technik die Brunsterkennung übernimmt (Praxistest)](https://noe.lko.at/wenn-die-technik-die-brunsterkennung-%C3%BCbernimmt+2400+3425060)
- [HerdVision (AgSenze)](https://herd.vision/)
- [VikingGenetics CowFIT](https://www.vikinggenetics.com/products-solutions/cowfit)
- [DLG: EuroTier 2024 – Trends in der Tierhaltungstechnik](https://www.dlg.org/detail/eurotier-2024-trends-in-der-tierhaltungstechnik)
- [Frigate NVR](https://github.com/blakeblackshear/frigate) · [Frigate+](https://frigate.video/plus/)
- [Viseron](https://github.com/roflcoopter/viseron)
- [CowCatcherAI](https://github.com/CowCatcherAI/CowCatcherAI)
- [CattleSense (YOLOv8-Pose-Verhaltensanalyse)](https://github.com/mohitksahu/CattleSense)
- [Scientific Reports: Lightweight cow mounting recognition (YOLOv5s)](https://www.nature.com/articles/s41598-023-40757-7)
- [Ever.Ag Maternity Warden](https://ever.ag/dairy/on-farm-dairy-operations/maternity-warden) · [Ag Proud: Computer vision tracks calvings](https://www.agproud.com/articles/59645-computer-vision-tracks-calvings-for-just-in-time-management)
- [Dilepix: Heat/Calving detection](https://www.dilepix.com/en/heat-detection)
- [FFG: Kuhtracking – KI im Kuhstall](https://www.ffg.at/success-stories/kuhtracking-die-ki-im-kuhstall) · [SN.at: Kuhtracking im Pinzgau](https://www.sn.at/panorama/wissen/kuhtracking-mit-ki-im-pinzgau-app-alarmiert-landwirt-bei-notfaellen-art-551766)
- [MyAnIML: AI camera predicts cattle disease](https://americancattlemen.com/myaniml-launches-ai-camera-system-that-predicts-cattle-disease/)
- [RealAgriculture 04/2026: CattleEye Lahmheit/BCS](https://www.realagriculture.com/2026/04/tracking-lameness-and-body-score-with-ai-powered-cattleeye)
- [Moocall: Calving Aids in 2026](https://www.moocall.com/calving-aids-in-2026-what-works-on-real-farms/)
- [EuroTier 2026](https://www.eurotier.com/de/) · [top agrar: EuroTier 2026 & KI](https://www.topagrar.com/rind/news/eurotier-2026-beschaftigt-sich-mit-ki-in-der-tierhaltungsbranche-20027042.html)

### Alarmweg- & App-Recherche (August 2026)

- [Lely Zeta AI Calving](https://www.lely.com/solutions/latest-innovations/zeta/ai-calving/) · [Lely Horizon: Empfänger/Zeitpläne](https://community.lely.com/horizon/a/horizon-documentation/HD12/learn-how-to-edit-your-people-in-lely-horizon) · [profi: Zeta AI Barn Monitor im Test](https://www.profi.co.uk/test-centre/livestock-equipment/lely-juno-max-discovery-collector-c1-c2-and-zeta-ai-barn-monitor-pushing-flushing-spying/)
- [Ever.Ag Maternity Warden](https://ever.ag/dairy/on-farm-dairy-operations/maternity-warden) · [Ever.Ag: Story behind Maternity Warden](https://www.ever.ag/empowering-dairy-farmers-the-story-behind-maternity-warden/) · [PR Newswire: Introducing Maternity Warden](https://www.prnewswire.com/news-releases/introducing-maternity-warden-constant-care-for-calving-cows-301940509.html)
- [Cattle Care FAQ](https://www.cattle-care.com/faq) · [Cattle Care OmniCalf](https://www.cattle-care.com/omni-calf)
- [Dilepix: Kalbeerkennung](https://www.dilepix.com/en/calving-detection)
- [Moocall Help Center: Was zeigt die App](http://help.moocall.com/en/articles/1566875-what-does-the-moocall-app-tell-me-about-my-moocall-calving-sensor) · [Moocall: Sensor testen](http://help.moocall.com/en/articles/13994979-how-do-i-test-my-moocall-calving-sensor) · [Farmers Weekly: Calving detection technology – 3 options compared](https://www.fwi.co.uk/livestock/calving-detection-technology-3-options-compared)
- [smaXtec System im Detail](https://www.smaxtec.com/en/smaXtec-system-in-detail/) · [smaXtec Messenger](https://www.smaxtec.com/us/software/)
- [SenseHub App (Release Notes 8.3.3 — Offline-Zusage)](https://apps.apple.com/us/app/allflex-sensehub/id1178919853)
- [CowManager: Snooze und Alarme entfernen](https://support.cowmanager.com/s/article/Web-application-snooze-and-remove-alerts?language=en_US) · [CowManager App (Release Notes)](https://apps.apple.com/us/app/cowmanager-app/id6596747980)
- [Nedap Now](https://nedap-livestockmanagement.com/solutions/nedap-cowcontrol/nedap-now/)
- [CowCatcherAI: Releases](https://github.com/CowCatcherAI/CowCatcherAI/releases) · [config.json](https://github.com/CowCatcherAI/CowCatcherAI/blob/main/config.json) · [CalvingCatcher-Website](https://jacobsfarm.github.io/website/)
- [Mozaë: Kalbe-Alarme](https://www.mozae-monitoring.fr/en/monitoring-platform/calving-alerts/)
- Autodialer-Nachbarkategorie: [Sensaphone Livestock](https://sensaphone.com/industries/livestock/) · [FarmAlarm](https://farmalarm.com/farmalarm-system) · [Agralarm](https://agralarm.com/) · [Smart Barn](https://smartbarn.io/benefits)
- Fehlalarm-Literatur: [PMC: Automated tail movement sensor to predict calving time](https://pmc.ncbi.nlm.nih.gov/articles/PMC11365211/) · [MDPI: Automated Systems for Estrous and Calving Detection](https://www.mdpi.com/2624-7402/4/2/31) · [PMC: How to Predict Parturition in Cattle](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8833683/)
- [EuroTier 2026 Innovation Award](https://www.eurotier.com/de/awards/innovation-award) — Anmeldeschluss war der 31.07.2026; die Liste der angemeldeten Neuheiten erscheint erfahrungsgemäß im September/Oktober. **Nächster konkreter Prüfpunkt vor der Messe (10.–13.11.2026).**
