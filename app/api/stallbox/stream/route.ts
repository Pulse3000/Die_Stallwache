import { NextResponse } from "next/server";
import { holeTuyaStream, tuyaKonfiguriert } from "@/lib/tuya";

export const dynamic = "force-dynamic";

/**
 * Liefert dem Frontend eine kurzlebige HLS-URL der Stallbox aus der
 * Tuya-Cloud. Zugangsdaten bleiben serverseitig; ohne TUYA_*-Env-Vars
 * bleibt der Endpoint geschlossen (503) und die Stallbox laeuft weiter
 * ueber die Bridge.
 *
 * Nutzt denselben CORS-Proxy wie die Futterwache (/api/futterwache/proxy
 * ist generisch: er validiert nur, dass die Ziel-URL zu einem Tuya-Host
 * gehoert, unabhaengig davon, welche Kamera sie angefordert hat).
 */
export async function GET() {
  if (!tuyaKonfiguriert("stallbox")) {
    return NextResponse.json(
      {
        fehler:
          "Tuya nicht konfiguriert – TUYA_ACCESS_ID, TUYA_ACCESS_SECRET und TUYA_DEVICE_ID_STALLBOX setzen.",
      },
      { status: 503 },
    );
  }
  try {
    const stream = await holeTuyaStream("stallbox", "hls");
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
