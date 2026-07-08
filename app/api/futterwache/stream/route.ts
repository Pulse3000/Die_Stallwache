import { NextResponse } from "next/server";
import { holeFutterwacheStream, tuyaKonfiguriert } from "@/lib/tuya";

export const dynamic = "force-dynamic";

/**
 * Liefert dem Frontend eine kurzlebige HLS-URL der Futterwache aus der
 * Tuya-Cloud. Zugangsdaten bleiben serverseitig; ohne TUYA_*-Env-Vars
 * bleibt der Endpoint geschlossen (503) und die Futterwache laeuft weiter
 * ueber die Bridge.
 *
 * Die zurueckgegebene URL zeigt bewusst auf /api/futterwache/proxy statt
 * direkt auf Tuyas CDN: Tuya setzt dort keine CORS-Header, wodurch hls.js
 * im Browser die Antworten sonst nicht lesen koennte (schwarzes Bild ohne
 * sichtbaren Fehler). Der Proxy macht den Stream same-origin.
 */
export async function GET() {
  if (!tuyaKonfiguriert) {
    return NextResponse.json(
      {
        fehler:
          "Tuya nicht konfiguriert – TUYA_ACCESS_ID, TUYA_ACCESS_SECRET und TUYA_DEVICE_ID setzen.",
      },
      { status: 503 },
    );
  }
  try {
    const stream = await holeFutterwacheStream("hls");
    const proxied = {
      ...stream,
      url: `/api/futterwache/proxy?url=${encodeURIComponent(stream.url)}`,
    };
    return NextResponse.json(proxied, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (e) {
    return NextResponse.json(
      { fehler: e instanceof Error ? e.message : "Tuya-Anfrage fehlgeschlagen" },
      { status: 502 },
    );
  }
}
