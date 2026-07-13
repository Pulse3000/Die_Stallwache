# Wettbewerbsanalyse: KI als „Drittes Auge" im Stall

Stand: Juli 2026 · Kontext: Stallblick/KI-Wache (dieses Repo) — kamerabasierte
Brunst- & Kalbeerkennung als 0-€-DIY-Stack (vorhandene Kameras, alter Rechner,
Colab-Training, Telegram, Vercel-Dashboard).

## 1. Wettbewerber im Überblick

| System | Ansatz | Fokus | Kosten (Größenordnung) |
| --- | --- | --- | --- |
| **Lely Zeta** (AI Calving) | Deckenmodul: Kamera + LED + Mini-Computer | Kalbung: Wehen-Score, Phasen, Komplikations-Alarm | Weiter Pilotphase (8 Testbetriebe NL); UK-Launch Kalbemodul für 2026 erwartet; Gerät + Abo, Preis weiter offen |
| **GEA CattleEye** | Kamera über Treibgang, Cloud-SaaS (seit 2024 zu GEA) | Lahmheit, BCS; Liverpool-Studie 07/2026 belegt Reduktion schwerer Lahmheit; >250.000 Kühe | Einstieg ab ~300–400 $ Hardware + SaaS-Abo |
| **Ever.Ag Maternity Warden** | Kameras + Edge-Nodes in Abkalbebucht; Alarm bei 3 Ereignissen in 20 min, 30-s-Clip | Kalbe-Alarme (Schwanzheben, Wehen, Fruchtteile), >95 % Genauigkeit, >100.000 Kühe | ~5.000 $ System + 0,50 $/Kuh/Monat |
| **Cattle Care OmniCalf** | Kameras Abkalbe-/Kälberbereich, Echtzeit auch bei Iglus | Kalbeverlust-Prävention + Arbeitsprotokoll-Kontrolle (Tubing, Nabeldesinfektion, Handling) | SaaS |
| **smaXtec** | Pansen-Bolus (invasiv) | Brunst, Gesundheit, Kalbung (Körpertemperatur) | ~2.450 € Infrastruktur + ~36 €/Kuh/Jahr Basis |
| **SenseHub (Allflex)** | Ohrmarke/Halsband | Brunst, Gesundheit | 19–28 €/Kuh/Jahr |
| **Moocall** | Schwanz-Sensor (angeklemmt) | Kalbung (Schwanzbewegung), Alarm 1–2 h vorher | ~166 € inkl. 1 Jahr Daten, danach ~162 €/Jahr Abo; 1 Sensor für 40–50 Kühe/Jahr |
| **Dilepix** (FR) | Feste Stall-Kameras (auch Thermal) + KI-Videoanalyse als Dienst | Brunst-Erkennung 24/7 mit Sofort-Alarm, separates Kalbe-Modul | SaaS, Preis auf Anfrage |
| **Kuhtracking** (Mechatronik Austria + Cognify, AT) | Rein kamerabasiert, Einzeltier-Tracking per KI, App-Alarm | Kalbung, Brunst, Krankheit/Verletzung; Zielgruppe Nebenerwerbsbetriebe | FFG-Forschungsprojekt (1 Mio. € gefördert), 10 Pilotbetriebe Pinzgau, noch kein Marktprodukt |
| **MyAnIML** (US) | Kamera aufs Flotzmaul (Muzzle-Analyse) | Krankheits-Vorhersage Tage vor Symptomen (Beef-Fokus) | Kommerziell, Preis auf Anfrage |
| **dsp-Agrosoft COW-AI** | Kamera über Laufgang (4,5–6 m) + Ohrmarken-Kamera zur Tier-ID | Lahmheit (automatisch, im Laufbereich) | Abo-Modell, Preis auf Anfrage |
| **DeLaval BCS-Kamera** | 3D-Kamera über Selektionstor/VMS-Ausgang | Body Condition Score (täglich, automatisch) | Gerätekauf + DelPro-Bindung, Preis über Händler |
| **CowManager** | Ohrsensor (Temperatur, Wiederkauen, Aktivität) | Brunst, Gesundheit (1–2 Tage Vorlauf), Transition | ~30 €/Sensor + Abo pro Kuh/Monat je Modul |
| **Nedap CowControl** | Hals-/Fußband-SmartTag + Ortungs-Infrastruktur | Brunst inkl. Besamungszeitpunkt, Gesundheit, Kuh-Ortung | ~118 €/Tier (Tag) + Infrastruktur |
| **HerdVision** | Stereo-3D-Kamera am Melkstand-Ausgang, EID-Tag-ID | BCS + Mobility-Score; DairyComp-Integration angekündigt | ~£5.900 + Abo (1. Jahr frei) |
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
| **CowCatcherAI (+ CalvingCatcher AI)** | YOLO/ONNX-Tool (Exe/Docker) + RTSP + Telegram-Fotoalarm; Modell V16 (01/2025), AGPL-3.0; NEU: CalvingCatcher erkennt Kalbe-Stadien (Wasserblase, Beine, Kopf, Kalb) | Direktester DIY-Konkurrent zieht bei Kalbung nach — jetzt mit Stadien-Erkennung, aber weiterhin ohne Eskalation, Wach-Modus, Dashboard, Persistenz | Kostenlos |
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
Lely-Zeta-Marktstart und Kuhtracking-Kommerzialisierung).

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
