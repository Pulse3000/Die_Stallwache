/**
 * Gemeinsamer Handler der Tuya-Kamera-Stream-Endpunkte.
 *
 * Jede Tuya-Kamera hat ihre eigene Route (/api/<kamera>/stream), weil der
 * Edge-Agent und die Android-App die Pfade fest verdrahtet haben. Der Inhalt
 * ist aber fuer alle identisch — mit drei Kameras waere dreifaches Copy-Paste
 * daraus geworden, und genau dort schleichen sich Abweichungen ein.
 */

import { NextResponse } from "next/server";
import {
  holeTuyaStream,
  KAMERA_ENV,
  KAMERA_NAMEN,
  tuyaKonfiguriert,
  type TuyaKameraId,
} from "@/lib/tuya";

/**
 * Liefert dem Frontend eine kurzlebige HLS-URL der Kamera aus der Tuya-Cloud.
 * Zugangsdaten bleiben serverseitig; ohne TUYA_*-Env-Vars bleibt der Endpoint
 * geschlossen (503) und die Kamera laeuft weiter ueber die Bridge.
 *
 * Die zurueckgegebene URL zeigt bewusst auf /api/futterwache/proxy statt
 * direkt auf Tuyas CDN: Tuya setzt dort keine CORS-Header, wodurch hls.js im
 * Browser die Antworten sonst nicht lesen koennte (schwarzes Bild ohne
 * sichtbaren Fehler). Der Proxy ist generisch — er prueft nur, ob die
 * Ziel-URL zu einem Tuya-Host gehoert, unabhaengig von der Kamera.
 */
export async function kameraStreamAntwort(
  kamera: TuyaKameraId,
): Promise<NextResponse> {
  if (!tuyaKonfiguriert(kamera)) {
    return NextResponse.json(
      {
        fehler:
          `Tuya nicht konfiguriert – TUYA_ACCESS_ID, TUYA_ACCESS_SECRET und ` +
          `${KAMERA_ENV[kamera]} setzen (${KAMERA_NAMEN[kamera]}).`,
      },
      { status: 503 },
    );
  }
  try {
    const stream = await holeTuyaStream(kamera, "hls");
    return NextResponse.json(
      {
        ...stream,
        url: `/api/futterwache/proxy?url=${encodeURIComponent(stream.url)}`,
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (e) {
    return NextResponse.json(
      { fehler: e instanceof Error ? e.message : "Tuya-Anfrage fehlgeschlagen" },
      { status: 502 },
    );
  }
}
