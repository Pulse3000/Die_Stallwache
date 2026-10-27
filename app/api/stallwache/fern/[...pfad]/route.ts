import { NextRequest, NextResponse } from "next/server";
import { authAktiv } from "@/lib/auth";
import { bildZeitKopf, fernAbruf, KI_ANSICHT_PFAD, schreibeManifestUm } from "@/lib/fern";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Reicht das Stallwache-HLS vom Stall-Rechner durch (siehe lib/fern.ts).
 *
 * Liegt hinter dem App-Login (middleware.ts). Zusaetzlich verweigert die
 * Route selbst den Dienst, solange der Login nicht aktiv ist (fail-closed):
 * Das Stallbild darf nie ohne Anmeldung erreichbar sein, auch nicht durch
 * eine vergessene Umgebungsvariable. Erlaubt sind nur die HLS-Pfade der
 * Stallwache und die KI-Ansicht, alles andere ist 404.
 *
 * KI-Ansicht: 404 vom Stall-Rechner heisst „der Agent analysiert gerade
 * nicht" und bleibt 404 (die Kachel zeigt dann den Hinweis statt
 * „Fernzugriff gestoert"); die Bildzeit geht nur als Ganzzahl durch.
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
  if (!r.ok) {
    const keinBild = teil === KI_ANSICHT_PFAD && r.upstream === 404;
    return NextResponse.json(
      { fehler: keinBild ? "Keine aktuelle KI-Ansicht" : r.fehler },
      { status: keinBild ? 404 : r.status },
    );
  }

  const typ = r.antwort.headers.get("content-type") ?? "application/octet-stream";
  const headers: Record<string, string> = { "Content-Type": typ, "Cache-Control": "no-store" };
  const bildZeit = bildZeitKopf(r.antwort.headers.get("x-bild-zeit"));
  if (teil === KI_ANSICHT_PFAD && bildZeit) headers["X-Bild-Zeit"] = bildZeit;

  if (teil.endsWith(".m3u8")) {
    const text = await r.antwort.text();
    return new NextResponse(schreibeManifestUm(text, r.antwort.url || `http://stall/api/${teil}`), {
      status: 200,
      headers,
    });
  }
  return new NextResponse(r.antwort.body, { status: 200, headers });
}
