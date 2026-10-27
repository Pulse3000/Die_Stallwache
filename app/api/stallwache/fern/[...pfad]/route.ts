import { NextRequest, NextResponse } from "next/server";
import { authAktiv, pruefeToken, SESSION_COOKIE } from "@/lib/auth";
import { fernAbruf, KI_ANSICHT_PFAD, schreibeManifestUm } from "@/lib/fern";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Reicht das Stallwache-HLS vom Stall-Rechner durch (siehe lib/fern.ts).
 *
 * Liegt hinter dem App-Login (middleware.ts). Zusaetzlich verweigert die
 * Route selbst den Dienst, solange der Login nicht aktiv ist (fail-closed),
 * und prueft die Sitzung selbst: Das Stallbild darf nie ohne Anmeldung
 * erreichbar sein, auch nicht durch eine vergessene Umgebungsvariable oder
 * einen Pfad, den der Matcher der Middleware auslaesst (statische Bilder). Erlaubt sind nur die HLS-Pfade der
 * Stallwache und die KI-Kaesten, alles andere ist 404.
 *
 * KI-Kaesten: 404 vom Stall-Rechner heisst „keine aktuellen Erkennungen"
 * und bleibt 404 (die Kachel zeigt dann den Hinweis statt „Fernzugriff
 * gestoert").
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
  if (!(await pruefeToken(req.cookies.get(SESSION_COOKIE)?.value))) {
    return NextResponse.json({ fehler: "Nicht angemeldet" }, { status: 401 });
  }
  const { pfad } = await params;
  const teil = pfad.join("/");
  const r = await fernAbruf(teil, req.nextUrl.searchParams);
  if (!r.ok) {
    const keinBild = teil === KI_ANSICHT_PFAD && r.upstream === 404;
    return NextResponse.json(
      { fehler: keinBild ? "Keine aktuellen KI-Kästen" : r.fehler },
      { status: keinBild ? 404 : r.status },
    );
  }

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
