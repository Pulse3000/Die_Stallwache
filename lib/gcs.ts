/**
 * Google Cloud Storage – Archiv fuer Trainings- und Alarmbilder.
 *
 * Warum das noetig ist: Der Edge-Agent sammelt im Silent Mode ueber Wochen
 * Trainingsbilder und legt per Ein-Tipp-Feedback Fehlalarm-Bilder als Hard
 * Negatives ab – bisher ausschliesslich auf der Platte des Stallrechners.
 * Genau dort ist es am unsichersten: ein alter Laptop im Stall, ohne RAID,
 * ohne Backup. Geht die Platte kaputt, ist die gesamte Datengrundlage des
 * eigenen Modells verloren.
 *
 * Dieses Modul spiegelt einzelne, bereits komprimierte JPEGs nach GCS. Es
 * bleibt damit im Rahmen der Datenhoheit: Es verlaesst NIE ein Videostream
 * den Hof, nur einzelne Standbilder, die der Betrieb ohnehin fuers Training
 * seines eigenen Modells braucht.
 *
 * Umgebungsvariablen (nur serverseitig):
 *   GCS_BUCKET                Name des Buckets, z.B. "stallwache-datensatz".
 *                             Leer/ungesetzt = Archiv aus (Route antwortet 503).
 *   GCP_SERVICE_ACCOUNT_JSON  siehe lib/gcp.ts, braucht roles/storage.objectCreator
 */

import { gcpAccessToken, gcpKonfiguriert } from "@/lib/gcp";

const BUCKET = process.env.GCS_BUCKET?.trim() || "";

/** Schreibrecht auf Objekte – bewusst enger als cloud-platform. */
export const SCOPE_STORAGE_RW =
  "https://www.googleapis.com/auth/devstorage.read_write";

export function gcsKonfiguriert(): boolean {
  return BUCKET.length > 0 && gcpKonfiguriert();
}

export function gcsBucket(): string {
  return BUCKET;
}

/**
 * Baut einen sicheren Objektnamen.
 *
 * Der Edge-Agent liefert Bestandteile (Art, Kamera, Dateiname) an. Die duerfen
 * niemals ungeprueft in den Pfad wandern: „../" oder fuehrende Slashes wuerden
 * sonst aus dem vorgesehenen Praefix ausbrechen und fremde Objekte des Buckets
 * ueberschreiben. Deshalb hart auf eine Zeichen-Allowlist reduzieren.
 */
export function saubererPfadteil(roh: string, ersatz = "x"): string {
  const s = roh
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9._-]/g, "-")
    .replace(/^[.-]+/, "")
    .slice(0, 80);
  return s.length > 0 ? s : ersatz;
}

/**
 * Legt ein Objekt im Bucket ab (einfacher Media-Upload der JSON-API).
 *
 * Wirft bei Fehlern – die aufrufende Route uebersetzt das in einen Statuscode.
 * Der Agent behaelt seine lokale Kopie in jedem Fall, das Archiv ist ein
 * Zusatz und niemals der einzige Ablageort.
 */
export async function ladeNachGcs(
  objektName: string,
  daten: Uint8Array,
  contentType = "image/jpeg",
): Promise<{ bucket: string; name: string; groesse: number }> {
  if (!gcsKonfiguriert()) {
    throw new Error("GCS nicht konfiguriert (GCS_BUCKET fehlt)");
  }
  const token = await gcpAccessToken(SCOPE_STORAGE_RW);
  const url =
    `https://storage.googleapis.com/upload/storage/v1/b/${encodeURIComponent(BUCKET)}/o` +
    `?uploadType=media&name=${encodeURIComponent(objektName)}`;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": contentType,
      "Content-Length": String(daten.byteLength),
    },
    // Uint8Array ist ein gueltiger BodyInit; Buffer waere Node-spezifisch.
    body: daten as unknown as BodyInit,
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(
      `GCS-Upload fehlgeschlagen (HTTP ${res.status}): ${(await res.text()).slice(0, 300)}`,
    );
  }
  return { bucket: BUCKET, name: objektName, groesse: daten.byteLength };
}
