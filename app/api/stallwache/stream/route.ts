import { kameraStreamAntwort } from "@/lib/kamera-stream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Livebild der Stallwache aus der Tuya-Cloud.
 *
 * Die Stallwache ist die Hauptkamera im Abkalbebereich — die Quelle, auf der
 * der Edge-Agent Kalbe- und Brunstanzeichen erkennt. Ueber diesen Endpoint
 * laeuft die komplette KI-Wache auch auf einem Hof ganz ohne Bridge: Der
 * Agent (`CloudQuelle`, stream.quelle_api = /api/stallwache/stream) liest
 * dieselbe Quelle wie die App.
 *
 * Anders als bei den Zweitkameras ist Tuya hier **opt-in**
 * (NEXT_PUBLIC_STALLWACHE_TUYA=1), damit bestehende Bridge-Hoefe ihr
 * Verhalten unveraendert behalten — siehe lib/config.ts.
 */
export async function GET() {
  return kameraStreamAntwort("stallwache");
}
