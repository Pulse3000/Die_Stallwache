import { kameraStreamAntwort } from "@/lib/kamera-stream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Liefert dem Frontend eine kurzlebige HLS-URL der Stallbox aus der
 * Tuya-Cloud. Zugangsdaten bleiben serverseitig; ohne TUYA_*-Env-Vars
 * bleibt der Endpoint geschlossen (503) und die Kachel zeigt den
 * Wartehinweis – seit der Tuya-Umstellung gibt es keinen Bridge-Fallback
 * mehr.
 * Alt-Pfad der Abkalbebox (hiess frueher "Stallbox").
 *
 * Bleibt bestehen, weil die Android-App (Der-Stallblick) und moeglicherweise
 * laufende Edge-Agenten diesen Pfad in ihrer Konfiguration stehen haben
 * (`stream.quelle_api`). Ein 404 nach der Umbenennung haette dort still das
 * Livebild abgeschaltet — die Kamera, die genau dann zaehlt, wenn eine Kuh
 * kalbt. Neue Konfigurationen nutzen /api/abkalbebox/stream.
 */
export async function GET() {
  return kameraStreamAntwort("abkalbebox");
}
