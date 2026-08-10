---
name: gcp-anbindung
description: Verbindet die App mit der bestehenden GCP-Architektur — ein Service Account für alles (Pub/Sub-Spiegelung der Ereignisse, Vertex AI für Freitext-/Sprachanfragen, FCM-Versand), Rechte prüfen, Spiegelung und Assistent end-to-end verifizieren. Nutzen bei "Pub/Sub", "Cloud Function bekommt nichts", "Vertex AI", "Gemini", "Assistent antwortet nur lokal" oder beim Anlegen des Dienstkontos.
---

# GCP-Anbindung scharfschalten (ein Schlüssel, drei Dienste)

Drei Bausteine hängen an **derselben** Service-Account-Datei
(`GCP_SERVICE_ACCOUNT_JSON`), brauchen aber verschiedene Rechte und fallen
unabhängig voneinander aus:

| Baustein | Zweck | Rolle | Fehlt er, dann … |
| --- | --- | --- | --- |
| **FCM** | Push aufs Handy | `roles/firebasemessaging.admin` | keine Benachrichtigungen (Skill `push-live-schalten`) |
| **Pub/Sub** | Ereignisse in die bestehende Architektur spiegeln | `roles/pubsub.publisher` | Cloud Functions und YOLO-Nachanalyse bekommen nichts |
| **Vertex AI** | Freitext-/Sprachanfragen | `roles/aiplatform.user` | Assistent antwortet nur aus dem Protokoll (lokal) |

Bewusst **ohne** `google-auth-library`: Ein Service-Account-Token ist ein
selbst signiertes RS256-JWT, das gegen ein OAuth2-Token getauscht wird
(`lib/gcp.ts`, ~40 Zeilen `node:crypto`). Das hält den Cold Start auf Vercel
klein und den Abhängigkeitsbaum überschaubar.

## Schritt 1 — Dienstkonto anlegen (Betreiber)

Google Cloud Console → IAM & Verwaltung → Dienstkonten → erstellen →
**alle drei Rollen** zuweisen (auch die, die noch nicht gebraucht werden —
Nachrüsten kostet ein Redeploy) → Schlüssel → JSON.

In Vercel als `GCP_SERVICE_ACCOUNT_JSON` hinterlegen, entweder als JSON-Text
oder Base64 (`base64 -w0 schluessel.json`; einzeilig, in der Vercel-Oberfläche
deutlich angenehmer). `GCP_PROJECT_ID` nur setzen, wenn es von der
Projekt-ID in der Schlüsseldatei abweicht.

**Redeploy** nicht vergessen.

## Schritt 2 — Pub/Sub-Spiegelung

Topic in GCP anlegen (z. B. `stall-ereignisse`), dann in Vercel
`PUBSUB_TOPIC=stall-ereignisse`. Leer/ungesetzt = Spiegelung aus.

Verifizieren:

1. Ereignis einspeisen:
   `POST /api/events` mit gültigem `x-ingest-token`, Nutzlast
   `{"typ":"info","nachricht":"Pub/Sub-Go-Live-Test"}`.
2. Die Antwort enthält `"pubsub": true` → der Publish hat geklappt.
   Steht dort `false`, ist entweder das Topic leer, der Service Account
   fehlt, oder die Rolle stimmt nicht — der Grund steht in den
   Vercel-Runtime-Logs (`get_runtime_logs`, Fenster klein halten, die
   Retention ist knapp).
3. Auf GCP-Seite: Abo am Topic ziehen (`gcloud pubsub subscriptions pull`)
   → die Nachricht trägt die Attribute `typ`, `kamera` und ggf. `kuhId`, die
   Nutzlast ist das Ereignis als JSON.

**Die Attribute sind kein Beiwerk:** Sie erlauben Pub/Sub-Filter, ohne die
Nutzlast zu parsen — eine Cloud Function kann `typ=austreibung` abonnieren
und alles andere ignorieren.

Wichtig zu wissen: Der Publish ist **fire and forget**. Ein Ausfall von
Pub/Sub darf den Alarmweg zum Landwirt nie blockieren; Fehler landen im Log,
nicht in der Antwort an den Edge-Agenten. Wer hier eine Zustellgarantie
braucht, baut sie in die Cloud Function, nicht in den Ingest.

## Schritt 3 — Assistent (Vertex AI oder Gemini-Schlüssel)

Zwei Wege, die App nimmt automatisch den ersten verfügbaren:

- **Vertex AI** über den Service Account oben. Optional
  `VERTEX_LOCATION` (Default `europe-west4`) und `VERTEX_MODEL`
  (Default `gemini-2.5-flash`). Bei Datenschutz-Anspruch die EU-Region
  behalten.
- **Gemini-API** mit `GEMINI_API_KEY` — der schnellere Weg zum Ausprobieren,
  ohne Dienstkonto.

Verifizieren:

1. `GET /api/assistent` → `{"ki":true}`.
2. `POST /api/assistent` mit `{"frage":"Gab es heute Nacht Kalbealarme?"}`
   → Antwort mit `"quelle":"vertex-ai"` bzw. `"gemini-api"`.
3. Gegenprobe der Rückfallebene: Steht dort `"quelle":"lokal"` mit einem
   `hinweis`, war der Dienst nicht erreichbar — die App hat dann trotzdem
   geantwortet, aus dem Protokoll. Das ist gewolltes Verhalten, aber ein
   Signal, dass die Konfiguration klemmt.

**Ohne jede KI bleibt die Funktion nutzbar**: Fragen nach Tier, Art und
Zeitraum („Zeig mir alle Aktivitäten von Kuh #42") beantwortet die App selbst
aus dem Ereignisspeicher. Die KI ist der Komfort, nicht die Grundlage — und
in einem Funkloch ist die lokale Auswertung die *einzige*, die antwortet.

## Schritt 4 — Kosten und Datenfluss ehrlich benennen

Diese Anbindung ist die einzige Stelle, an der Stallblick laufende Kosten
verursachen kann. Dem Betreiber sagen, was tatsächlich fließt:

- **Pub/Sub:** eine Nachricht je Ereignis (wenige pro Tag) — praktisch im
  Gratis-Kontingent.
- **Vertex/Gemini:** eine Anfrage je gestellter Frage, mit bis zu 60
  Ereignissen als Kontext. Kein Hintergrundverkehr, keine Analyse auf Vorrat.
- **Video geht nie in die Cloud.** Auch hier nicht. Es wandern Ereignisse und
  Fragen, nichts sonst — Prinzip 2 der Vision bleibt unangetastet.

## Rollback

Einzeln abschaltbar, ohne Code-Änderung: `PUBSUB_TOPIC` leeren (Spiegelung
aus), `GEMINI_API_KEY` und Vertex-Rechte entziehen (Assistent fällt auf lokal
zurück), `GCP_SERVICE_ACCOUNT_JSON` entfernen (alle drei aus, Push
inklusive). Jeweils Redeploy.

## Rollenverteilung

| Schritt | Wer |
| --- | --- |
| Dienstkonto, Rollen, Topic, Env-Variablen | Betreiber |
| Schritte 2–3 verifizieren | Orchestrator (dieser Skill) |
| Schritt 4 kommunizieren | Orchestrator |

## Verwandt

- `push-live-schalten` — der dritte Dienst am selben Schlüssel
- `ki-wache-smoketest` — Ereigniskette Agent → API → Dashboard
