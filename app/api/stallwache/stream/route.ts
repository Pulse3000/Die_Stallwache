import { NextResponse } from "next/server";
import { holeTuyaStream, tuyaKonfiguriert } from "@/lib/tuya";

export const dynamic = "force-dynamic";

/**
 * Liefert dem Frontend eine kurzlebige HLS-URL der Stallwache aus der
 * Tuya-Cloud. Zugangsdaten bleiben serverseitig; ohne TUYA_*-Env-Vars
 * bleibt der Endpoint geschlossen (503) und die Stallwache laeuft weiter
 * ueber die Bridge.
 *
 * Die Stallwache ist die Hauptkamera im Abkalbebereich — die Quelle, auf der
 * der Edge-Agent Kalbe- und Brunstanzeichen erkennt. Ueber diesen Endpoint
 * laeuft die komplette KI-Wache auch auf einem Hof ganz ohne Bridge: Der
 * Agent (`CloudQuelle`, stream.quelle_api = /api/stallwache/stream) liest
 * dieselbe Quelle wie die App.
 *
 * Nutzt denselben CORS-Proxy wie die Futterwache (/api/futterwache/proxy
 * ist generisch: er validiert nur, dass die Ziel-URL zu einem Tuya-Host
 * gehoert, unabhaengig davon, welche Kamera sie angefordert hat).
 */
export async function GET() {
  if (!tuyaKonfiguriert("stallwache")) {
    return NextResponse.json(
      {
        fehler:
          "Tuya nicht konfiguriert – TUYA_ACCESS_ID, TUYA_ACCESS_SECRET und TUYA_DEVICE_ID_STALLWACHE setzen.",
      },
      { status: 503 },
    );
  }
  try {
    const stream = await holeTuyaStream("stallwache", "hls");
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
