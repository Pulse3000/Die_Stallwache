import { NextResponse } from "next/server";
import { authAktiv } from "@/lib/auth";
import { fernAbruf, fernKonfiguriert, FERN_PRAEFIX } from "@/lib/fern";
import { kameraStreamAntwort } from "@/lib/kamera-stream";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Livebild der Stallwache – ueber den Fernzugriff zum Stall-Rechner
 * (Tapo via go2rtc, lib/fern.ts) oder aus der Tuya-Cloud.
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
  // Fernzugriff ueber den Stall-Rechner (Tapo/go2rtc, lib/fern.ts): nur mit
  // aktivem App-Login. Antwortet der Stall-Rechner nicht, geht es mit 502
  // weiter – die Kachel faellt dann auf die Bridge zurueck (Tailscale).
  if (fernKonfiguriert()) {
    if (!authAktiv()) {
      return NextResponse.json(
        { fehler: "Fernzugriff gesperrt – App-Login (STALLBLICK_PASSWORT) ist nicht aktiv." },
        { status: 503 },
      );
    }
    const probe = await fernAbruf("stream.m3u8", new URLSearchParams(), 6_000);
    if (!probe.ok) {
      return NextResponse.json({ fehler: probe.fehler }, { status: probe.status });
    }
    await probe.antwort.body?.cancel();
    return NextResponse.json(
      { url: `${FERN_PRAEFIX}/stream.m3u8`, typ: "hls" },
      { headers: { "Cache-Control": "no-store" } },
    );
  }
  return kameraStreamAntwort("stallwache");
}
