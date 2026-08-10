import { kameraStreamAntwort } from "@/lib/kamera-stream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Kurzlebige HLS-URL der Abkalbebox aus der Tuya-Cloud. */
export async function GET() {
  return kameraStreamAntwort("abkalbebox");
}
