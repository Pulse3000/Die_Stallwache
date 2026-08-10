---
name: tuya-diagnose
description: Grenzt Tuya-Cloud-Störungen von außen ein, ohne Zugriff auf die Secrets — unterscheidet falsches Access Secret, falsches Rechenzentrum, nicht verknüpftes Gerät und fehlende Env-Variable anhand des Tuya-Fehlercodes. Nutzen bei "sign invalid", "clientId is invalid", "Kamera zeigt Fehler", "Tuya geht nicht", schwarzem Livebild oder Fehlern in der Gerätesteuerung.
---

# Tuya-Störung eingrenzen (ohne die Secrets zu sehen)

Tuya-Fehler sehen alle gleich aus („geht nicht"), haben aber vier klar
unterscheidbare Ursachen. Der **Fehlercode** trennt sie zuverlässig — man
muss ihn nur lesen, statt am Access Secret herumzuraten.

Wichtig für die Erwartungshaltung: Die Werte der Env-Variablen sind von hier
aus **nicht lesbar** (Vercel gibt Secrets nicht heraus, und der Schreibzugriff
auf den Store ist gesperrt). Diese Prozedur arbeitet ausschließlich mit dem,
was die API von außen verrät. Das reicht — man muss ein Secret nicht sehen,
um zu beweisen, dass es falsch ist.

## Schritt 1 — Fehlercode holen

```
GET /api/tuya/geraete          # Gerätesteuerung, Fehler steht je Gerät
GET /api/<kamera>/stream       # futterwache | abkalbebox | weidewache
```

Der aussagekräftige Teil ist `Tuya-API-Fehler <code>: <msg>`.

## Schritt 2 — Code deuten

| Code | Bedeutung | Ursache | Fix |
| --- | --- | --- | --- |
| **2009** `clientId is invalid` | Das Rechenzentrum kennt diese Access ID nicht | falsches Data Center **oder** vertippte/falsche `TUYA_ACCESS_ID` | `TUYA_API_BASE` auf das richtige DC setzen (Schritt 3) bzw. ID korrigieren |
| **1004** `sign invalid` | Die ID ist hier bekannt, aber die Signatur passt nicht | **`TUYA_ACCESS_SECRET` gehört nicht zu dieser ID** (rotiert, oder aus einem anderen Projekt) | Secret im Portal frisch kopieren, in Vercel ersetzen, Redeploy |
| **1106** `permission deny` | Zugang gültig, aber das Gerät gehört nicht zu diesem Projekt | Gerät nicht verknüpft | Tuya-Portal → Cloud → Projekt → Devices → *Link App Account* |
| **HTTP 503** „Tuya nicht konfiguriert" | Gar kein Aufruf erfolgt | Env-Variable fehlt — die Meldung nennt sie beim Namen | Variable setzen, Redeploy |
| **HTTP 502**, sonstiger Text | Netz/Timeout zur Tuya-Cloud | meist vorübergehend | wiederholen, dann Tuya-Status prüfen |

**Der entscheidende Kniff:** 2009 und 1004 sehen für den Betreiber gleich aus,
zeigen aber in völlig verschiedene Richtungen. 1004 heißt, dass die ID *echt*
und *am richtigen Ort* ist — dann ist das Rechenzentrum korrekt und nur das
Secret falsch. Wer bei 1004 die Region umstellt, sucht am falschen Ende.

## Schritt 3 — Verdacht beweisen (Skript)

`pruefe.mjs` in diesem Skill-Ordner probiert dieselbe Signatur, die
`lib/tuya.ts` baut, gegen **alle** Tuya-Rechenzentren durch und sagt, welches
antwortet. Es gibt weder ID noch Secret aus.

```bash
TUYA_ACCESS_ID=… TUYA_ACCESS_SECRET=… \
  node .claude/skills/tuya-diagnose/pruefe.mjs
```

Optional mit Geräteprüfung:

```bash
TUYA_ACCESS_ID=… TUYA_ACCESS_SECRET=… TUYA_DEVICE_ID_FUTTERWACHE=… \
  node .claude/skills/tuya-diagnose/pruefe.mjs
```

Lesart des Ergebnisses:

- **Ein DC meldet „TOKEN OK"** → Schlüssel sind gültig. Ist es nicht
  `openapi.tuyaeu.com`, gehört `TUYA_API_BASE` auf diesen Host.
- **Überall 2009** → die Access ID existiert nirgends. Tippfehler oder
  falsches Projekt.
- **Überall 1004** → die ID ist bekannt, das Secret passt nicht. Kein
  Regionsproblem.
- **Skript sagt OK, Produktion nicht** → der Wert in Vercel weicht vom
  getesteten ab: Leerzeichen, Zeilenumbruch, oder nur für *Preview* statt
  *Production* gesetzt.

Zugangsdaten **immer** über die Umgebung übergeben, nie als Argument —
Argumente landen in der Shell-History und in der Prozessliste.

## Schritt 4 — Nach dem Fix verifizieren

1. Env-Variable in Vercel ändern → **Redeploy** (Werte greifen erst dann).
2. `GET /api/tuya/geraete` → jedes freigegebene Gerät hat `online: true`
   und kein `fehler`-Feld.
3. `GET /api/<kamera>/stream` → 200 mit `url` auf `/api/futterwache/proxy?…`.
4. Livebild der betroffenen Kamera im Dashboard öffnen.

## Was kein Tuya-Problem ist

Nicht jede schwarze Kachel liegt an der Cloud — vor der Fehlersuche
ausschließen:

- **Bridge nicht verbunden** → die Kamera zeigt „Warte auf Bridge". Das ist
  `NEXT_PUBLIC_BRIDGE_URL`, nicht Tuya. Siehe Skill `stallwache-live-schalten`.
- **Datensparen aktiv** → das Hauptbild läuft absichtlich als Standbild, bis
  „Live starten" getippt wird. Kein Fehler, eine Einstellung.
- **Schwarzes Bild trotz 200** → CORS. Die Stream-URL muss über
  `/api/futterwache/proxy` laufen (tut sie standardmäßig); zeigt sie direkt
  auf Tuyas CDN, kann `hls.js` die Antwort nicht lesen.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Schritte 1, 2, 4 | Orchestrator (dieser Skill) |
| Schritt 3 mit den echten Schlüsseln | Betreiber (nur er hat sie) |
| Env-Variablen ändern | Betreiber (Secret-Store gesperrt) |

## Verwandt

- `tuya-futterwache` — Erstanbindung einer Kamera
- `stallwache-live-schalten` — Bridge-Weg statt Cloud-Weg
