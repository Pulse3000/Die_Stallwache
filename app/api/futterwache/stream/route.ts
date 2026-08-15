import { kameraStreamAntwort } from "@/lib/kamera-stream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Liefert dem Frontend eine kurzlebige HLS-URL der Futterwache aus der
 * Tuya-Cloud. Zugangsdaten bleiben serverseitig; ohne TUYA_*-Env-Vars
 * bleibt der Endpoint geschlossen (503) und die Kachel zeigt den
 * Wartehinweis – seit der Tuya-Umstellung gibt es keinen Bridge-Fallback
 * mehr.
 *
 * Die zurueckgegebene URL zeigt bewusst auf /api/futterwache/proxy statt
 * direkt auf Tuyas CDN: Tuya setzt dort keine CORS-Header, wodurch hls.js
 * im Browser die Antworten sonst nicht lesen koennte (schwarzes Bild ohne
 * sichtbaren Fehler). Der Proxy macht den Stream same-origin.
 */
/** Kurzlebige HLS-URL der Futterwache aus der Tuya-Cloud. */
export async function GET() {
  return kameraStreamAntwort("futterwache");
}
