# Lagebericht-Vertrag v1 — `GET /api/lagebericht` — Stand 16.10.2026

**Zweck:** Tagesreport-Punkte 2 (Brunst-/Kalbeüberwachung) und 3 (Sonstige Auffälligkeiten)
aus gelesenen Daten statt „Keine Angaben möglich". Nur lesend, aggregiert, ohne Bilder.

**Grundsatz:** Null heißt *gelesen und leer* — nie *nicht gelesen*. Kein 200 mit Nullen,
wenn die Persistenz nicht gelesen werden konnte.

## Anfrage

```
GET /api/lagebericht?stunden=12        (Ganzzahl 1–72, Standard 12)
x-report-token: <REPORT_READ_TOKEN>
```

Eigener Lese-Token. Der Ingest-Token (`EDGE_INGEST_TOKEN`) darf schreiben und öffnet den
Lagebericht nicht. Vergleich in konstanter Zeit (`crypto.timingSafeEqual`) — dasselbe für den
bestehenden Ingest-Token, falls noch nicht umgesetzt.

## Antworten

| Code | Wann |
|---|---|
| 200 | Persistenz gelesen |
| 400 | `stunden` nicht ganzzahlig oder außerhalb 1–72 |
| 401 | Token fehlt oder falsch |
| 503 | `REPORT_READ_TOKEN` nicht gesetzt **oder** Persistenz nicht lesbar — Body nennt, welches |

Alle Antworten: `Cache-Control: no-store`.

## 200-Body

```json
{
  "erzeugt": "2026-10-16T06:00:00Z",
  "zeitraum": { "von": "2026-10-15T18:00:00Z", "bis": "2026-10-16T06:00:00Z", "stunden": 12 },
  "quelle": { "name": "<Persistenz, in die /api/events schreibt>" },
  "zaehler": { "kalbeverdacht": 0, "austreibung": 0, "brunstverdacht": 0, "info": 0 },
  "je_kamera": { "stallwache": { "kalbeverdacht": 0, "austreibung": 0, "brunstverdacht": 0, "info": 0 } },
  "letzte_ereignisse": [
    { "zeit": "…", "typ": "info", "kuhId": null, "kamera": "stallwache", "nachricht": "…", "konfidenz": null }
  ],
  "letztes_lebenszeichen": { "stallwache": "2026-10-16T05:58:00Z", "futterwache": null, "stallbox": null }
}
```

- `letzte_ereignisse`: höchstens 20, neueste zuerst, genau diese sechs Felder.
- `letztes_lebenszeichen`: jüngstes Ereignis beliebigen Typs je Kamera, **unabhängig vom
  Zeitraum**; `null` = nie. Immer enthalten: `stallwache`, `futterwache`, `stallbox` (B14),
  dazu jede weitere gesehene Kamera.
- Eskalation: bis B17 im Zähler `austreibung` (Nachricht mit Präfix „ESKALATION");
  nach B17 eigener Zähler `eskalation`.
- Datenschutz: nur Ereignisse, die den Hof ohnehin verlassen dürfen (B7). Keine Bilder,
  keine Keypoints, keine Rohdaten.

## Zuordnung im Tagesreport

| Report-Punkt | Quelle im Lagebericht |
|---|---|
| 2 Brunst- und Kalbeüberwachung | `zaehler.kalbeverdacht/austreibung/brunstverdacht` + passende `letzte_ereignisse` |
| 3 Sonstige Auffälligkeiten | `info`-Ereignisse (Kamera offline/online, Tempguard, Modus, Fähigkeitsprüfung) und Lücken in `letztes_lebenszeichen` |
| Quelle nicht lesbar | 503-Body wörtlich berichten — keine Nullen erfinden |

## Abhängigkeiten (nicht Teil des Bauleiter-Goals)

- **Edge:** Punkt 3 bleibt leer, bis kuhwatch `info`-Ereignisse sendet (Folgeauftrag Wächter #2:
  Tempguard, Kamera offline/online, Modus beim Start, Fähigkeitsprüfung V0, Tagesbilanz B12).
  Leer ist dann aber belegt leer.
- **Betreiber:** `REPORT_READ_TOKEN` in Vercel (Production) setzen und als Secret der Report-Routine
  hinterlegen; Routine-Prompt ergänzen (Text in `00_LIESMICH.md`).
- **PR #70** (Pub/Sub → Firestore) ist hierfür nur relevant, wenn `/api/events` nach Firestore
  schreibt. Ein zweiter Datenweg entsteht nicht ohne Beschluss.

## Prüfung

`scripts/smoke-lagebericht.sh` gegen `npm run dev`. Das Skript schreibt nichts (Ingest nur mit
Payloads, die abgelehnt werden müssen) und verweigert Ziele außer localhost. Gegen eine
vertragstreue Attrappe grün, gegen eine vertragsbrüchige rot (fehlendes `no-store`,
Zusatzfeld mit Bilddaten).

## Umsetzung

*(vom Bauleiter nach dem Goal-Lauf zu füllen)*
