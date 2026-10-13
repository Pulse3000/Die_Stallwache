import { NextRequest, NextResponse } from "next/server";
import { authAktiv } from "@/lib/auth";
import { fernAbruf, schreibeManifestUm } from "@/lib/fern";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Reicht das Stallwache-HLS vom Stall-Rechner durch (siehe lib/fern.ts).
 *
 * Liegt hinter dem App-Login (middleware.ts). Zusaetzlich verweigert die
 * Route selbst den Dienst, solange der Login nicht aktiv ist (fail-closed):
 * Das Stallbild darf nie ohne Anmeldung erreichbar sein, auch nicht durch
 * eine vergessene Umgebungsvariable. Erlaubt sind nur die HLS-Pfade der
 * Stallwache, alles andere ist 404.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ pfad: string[] }> },
) {
  if (!authAktiv()) {
    return NextResponse.json(
      { fehler: "Fernzugriff gesperrt – App-Login (STALLBLICK_PASSWORT) ist nicht aktiv." },
      { status: 503 },
    );
  }
  const { pfad } = await params;
  const teil = pfad.join("/");
  const r = await fernAbruf(teil, req.nextUrl.searchParams);
  if (!r.ok) return NextResponse.json({ fehler: r.fehler }, { status: r.status });

  const typ = r.antwort.headers.get("content-type") ?? "application/octet-stream";
  const headers = { "Content-Type": typ, "Cache-Control": "no-store" };

  if (teil.endsWith(".m3u8")) {
    const text = await r.antwort.text();
    return new NextResponse(schreibeManifestUm(text, r.antwort.url || `http://stall/api/${teil}`), {
      status: 200,
      headers,
    });
  }
  return new NextResponse(r.antwort.body, { status: 200, headers });
}
