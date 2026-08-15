/**
 * Weitergabe erkannter Ereignisse an die bestehende GCP-Architektur.
 *
 * Der Ingest-Endpoint (/api/events) spiegelt jedes Ereignis in ein
 * Pub/Sub-Topic. Daran haengen die vorhandenen Cloud Functions (Archiv,
 * BigQuery, Compute-Engine-Nachanalyse der YOLO-Ergebnisse) — die App ist
 * damit nur eine weitere Quelle im bestehenden Datenfluss, kein Silo.
 *
 * Wichtig: Der Publish laeuft „fire and forget". Ein Ausfall von Pub/Sub darf
 * den Alarmweg zum Landwirt (Dashboard + Push) niemals blockieren; Fehler
 * landen im Log, nicht in der Antwort an den Edge-Agenten.
 *
 * Umgebungsvariablen:
 *   GCP_SERVICE_ACCOUNT_JSON  siehe lib/gcp.ts (roles/pubsub.publisher)
 *   PUBSUB_TOPIC              Topic-Name, z.B. "stall-ereignisse".
 *                             Leer/ungesetzt = Spiegelung aus.
 *   GCP_PROJECT_ID            optional; sonst aus der Schluesseldatei.
 */

import { gcpAccessToken, gcpKonfiguriert, gcpProjekt, SCOPE_PUBSUB } from "@/lib/gcp";
import type { StallEreignis } from "@/lib/events";

const TOPIC = process.env.PUBSUB_TOPIC?.trim() || "";

export function pubsubAktiv(): boolean {
  return Boolean(TOPIC) && gcpKonfiguriert() && Boolean(gcpProjekt());
}

/**
 * Spiegelt ein Ereignis nach Pub/Sub. Antwortet nie mit einem Fehler —
 * das Ergebnis ist rein informativ (z.B. fuer die Diagnose-Anzeige).
 */
export async function veroeffentlicheEreignis(
  ereignis: StallEreignis,
): Promise<boolean> {
  if (!pubsubAktiv()) return false;
  try {
    const token = await gcpAccessToken(SCOPE_PUBSUB);
    const url = `https://pubsub.googleapis.com/v1/projects/${gcpProjekt()}/topics/${encodeURIComponent(TOPIC)}:publish`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        messages: [
          {
            // Attribute erlauben Pub/Sub-Filter, ohne die Nutzlast zu parsen.
            attributes: {
              typ: ereignis.typ,
              kamera: ereignis.kamera,
              ...(ereignis.kuhId ? { kuhId: ereignis.kuhId } : {}),
            },
            data: Buffer.from(JSON.stringify(ereignis), "utf8").toString("base64"),
          },
        ],
      }),
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    }
    return true;
  } catch (e) {
    console.error("Pub/Sub-Publish fehlgeschlagen (Ingest laeuft weiter):", e);
    return false;
  }
}
