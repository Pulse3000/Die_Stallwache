import { NextRequest, NextResponse } from "next/server";
import {
  authAktiv,
  erstelleToken,
  pruefePasswort,
  SESSION_COOKIE,
  SESSION_MAX_AGE,
} from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!authAktiv()) {
    // Kein Passwort konfiguriert -> Login nicht noetig.
    return NextResponse.json({ ok: true, hinweis: "Kein Schutz aktiv" });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ fehler: "Kein gültiges JSON." }, { status: 400 });
  }
  const passwort = (body as Record<string, unknown>).passwort;
  if (typeof passwort !== "string" || !pruefePasswort(passwort)) {
    return NextResponse.json({ fehler: "Falsches Passwort." }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(SESSION_COOKIE, await erstelleToken(), {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });
  return res;
}
