# Wettbewerbsanalyse: KI als „Drittes Auge" im Stall

Stand: Juli 2026 · Kontext: Stallblick/KI-Wache (dieses Repo) — kamerabasierte
Brunst- & Kalbeerkennung als 0-€-DIY-Stack (vorhandene Kameras, alter Rechner,
Colab-Training, Telegram, Vercel-Dashboard).

## 1. Wettbewerber im Überblick

| System | Ansatz | Fokus | Kosten (Größenordnung) |
| --- | --- | --- | --- |
| **Lely Zeta** (AI Calving) | Deckenmodul: Kamera + LED + Mini-Computer | Kalbung: Wehen-Score, Phasen, Komplikations-Alarm | Gerät + Abo, Launch ~2026, Preis offen |
| **GEA CattleEye** | Kamera über Treibgang, Cloud-SaaS | Lahmheit, Body Condition Score | SaaS-Abo; peer-reviewed validiert |
| **Ever.Ag Maternity** | Kameras in Abkalbebucht | Kalbe-Alarme + zeitgestempelte Videoclips aufs Handy | SaaS; >100.000 Kühe im Einsatz |
| **Cattle Care OmniCalf** | Kameras Abkalbe-/Kälberbereich | Kalbeverlust-Prävention, kritische Ereignisse | SaaS |
| **smaXtec** | Pansen-Bolus (invasiv) | Brunst, Gesundheit, Kalbung (Körpertemperatur) | ~1.200–2.000 € einmalig + ~43 €/Kuh/Jahr |
| **SenseHub (Allflex)** | Ohrmarke/Halsband | Brunst, Gesundheit | 19–28 €/Kuh/Jahr |
| **Moocall** | Schwanz-Sensor (angeklemmt) | Kalbung (Schwanzbewegung) | ~300 €/Sensor + Datentarif |

Kommerzielle Kamera-Komplettsysteme liegen laut Wissenspaket bei **45.000–75.000 €**
Investition; Sensor-Systeme kosten laufend pro Kuh. Der DIY-Ansatz (dieses Repo)
liegt bei **0–2.000 €** einmalig und **0 €/Kuh/Jahr** — bei ~370–400 € Mehrwert
pro Kuh und Jahr amortisiert er sich sofort.

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

## 3. Was wir bewusst NICHT machen

- **Keine invasiven Sensoren** (Bolus/Ohrmarke): Kostenlawine pro Kuh/Jahr,
  Batterie-/Tierwohl-Themen — unser Differenzierer ist kamerabasiert + kostenlos.
- **Kein Abo-Modell / keine Cloud-Videoanalyse**: Edge-First bleibt gesetzt
  (Datenhoheit, kein Uplink-Problem, 0 € Laufkosten).
- **Keine Hardware-Verkäufe**: Anleitung statt Gerät („bring your own Rechner").
- **Kein Feature-Zoo im Dashboard**: Stallblick-Prinzip „Ruhe vor Fülle" gilt
  auch für die KI-Wache — Alarme müssen in 3 Sekunden erfassbar sein.

## 4. Produktentscheidungen (priorisiert)

| Prio | Entscheidung | Begründung / Wettbewerbsbezug |
| --- | --- | --- |
| **P1** | **Eskalations-Alarm**: Austreibung erkannt, aber nach konfigurierbarer Zeit (Default 60 min) kein Kalb → zweiter, dringlicherer Alarm („Kontrolle nötig") | Lely Zeta; größter Nutzen pro Codezeile, rettet Kälber |
| **P1** | **Ereignis-Persistenz** im Dashboard (Vercel KV/Postgres statt In-Memory) | Alle SaaS-Wettbewerber haben Historie; ohne sie ist das Dashboard nur Momentaufnahme |
| **P2** | **Bildserie am Alarm** (3–5 Frames per Telegram-Album) | Ever.Ag; Fehlalarm-Triage am Handy |
| **P2** | **Zwei-Kamera-Brunst-Fusion**: Aufsprung nur melden, wenn von der Zweitkamera plausibilisiert (falls beide dieselbe Bucht sehen) | Forschungsstand; halbiert Fehlalarme |
| **P2** | **Täglicher Telegram-Digest** (1 Nachricht: Ereignisse, Agent-Uptime, Bildkontingent) | smaXtec/SenseHub-Apps; Vertrauen durch Routine |
| **P3** | **Lahmheits-Frühwarnung** aus Rückenlinien-Winkel | CattleEye; Keypoints vorhanden, braucht aber eigene Validierung |
| **P3** | **BCS-Schätzung** (Body Condition) | DeLaval/CattleEye; erst nach stabilem Kalbe-/Brunst-Betrieb |

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
