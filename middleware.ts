import { NextRequest, NextResponse } from "next/server";
import { authAktiv, pruefeToken, SESSION_COOKIE } from "@/lib/auth";

/**
 * Schuetzt die gesamte App mit dem gemeinsamen Passwort (siehe lib/auth.ts).
 *
 * Ausnahmen (auch ohne Session erreichbar):
 *   - /login, /api/login, /api/logout  (Anmeldeweg selbst)
 *   - POST /api/events                  (Edge-Agent-Ingest, eigene Token-Auth)
 *   - POST /api/datensatz               (Edge-Agent-Bildarchiv, eigene Token-Auth)
 *   - statische Assets                  (ueber matcher unten ausgeschlossen)
 */
export async function middleware(req: NextRequest) {
  if (!authAktiv()) return NextResponse.next();

  const { pathname } = req.nextUrl;

  if (
    pathname === "/login" ||
    pathname === "/api/login" ||
    pathname === "/api/logout"
  ) {
    return NextResponse.next();
  }

  // Edge-Agent meldet Ereignisse und archiviert Trainingsbilder mit eigenem
  // x-ingest-token (kein Session-Cookie). Die Routen pruefen ihn selbst.
  if (
    (pathname === "/api/events" || pathname === "/api/datensatz") &&
    req.method === "POST"
  ) {
    return NextResponse.next();
  }

  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (await pruefeToken(token)) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ fehler: "Nicht angemeldet" }, { status: 401 });
  }

  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.searchParams.set("weiter", pathname + req.nextUrl.search);
  return NextResponse.redirect(url);
}

export const config = {
  // Alles ausser Next-internen und statischen Dateien.
  //
  // sw.js muss ausgenommen bleiben: Ein Redirect auf /login liefert HTML
  // statt JavaScript, und der Browser verweigert die Registrierung des
  // Service Workers – die PWA waere damit weder offlinefaehig noch
  // push-faehig. Das Skript enthaelt keine Daten, nur Ablauflogik.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|manifest.webmanifest|sw.js|.*\\.(?:svg|png|jpg|jpeg|webp|gif|ico)$).*)",
  ],
};
