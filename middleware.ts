import { NextRequest, NextResponse } from "next/server";
import { authAktiv, pruefeToken, SESSION_COOKIE } from "@/lib/auth";

/**
 * Schuetzt die gesamte App mit dem gemeinsamen Passwort (siehe lib/auth.ts).
 *
 * Ausnahmen (auch ohne Session erreichbar):
 *   - /login, /api/login, /api/logout  (Anmeldeweg selbst)
 *   - POST /api/events                  (Edge-Agent-Ingest, eigene Token-Auth)
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

  // Edge-Agent meldet Ereignisse mit eigenem x-ingest-token (kein Session-Cookie).
  if (pathname === "/api/events" && req.method === "POST") {
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
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|manifest.webmanifest|.*\\.(?:svg|png|jpg|jpeg|webp|gif|ico)$).*)",
  ],
};
