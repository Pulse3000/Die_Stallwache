import { kameraStreamAntwort } from "@/lib/kamera-stream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
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
