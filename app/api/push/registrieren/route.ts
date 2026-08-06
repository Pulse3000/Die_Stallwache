import { NextRequest, NextResponse } from "next/server";
import { EREIGNIS_TYPEN, type EreignisTyp } from "@/lib/events";
import { entferneAbo, registriereAbo } from "@/lib/push";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Meldet ein Geraet fuer Push-Benachrichtigungen an bzw. ab.
 *
 * POST   { token, typen?, geraet? }  – anmelden oder Auswahl aendern
 * DELETE ?token=...                  – abmelden (z.B. „Push aus" in den
 *                                      Einstellungen oder Token-Rotation)
 *
 * Die Route liegt hinter dem Session-Schutz (middleware.ts): nur wer sich am
 * Stallblick anmelden kann, darf Alarme dieses Hofes empfangen.
 */
export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ fehler: "Kein gültiges JSON." }, { status: 400 });
  }
  const b = body as Record<string, unknown>;

  const token = typeof b.token === "string" ? b.token.trim() : "";
  // FCM-Web-Tokens sind lange, undurchsichtige Strings – grob plausibilisieren.
  if (token.length < 20 || token.length > 4096) {
    return NextResponse.json({ fehler: "token fehlt oder ist ungültig." }, { status: 400 });
  }

  const typen = Array.isArray(b.typen)
    ? b.typen.filter((t): t is EreignisTyp =>
        EREIGNIS_TYPEN.includes(t as EreignisTyp),
      )
    : [];

  const abo = await registriereAbo({
    token,
    typen,
    geraet: typeof b.geraet === "string" ? b.geraet.slice(0, 60) : "Mobilgerät",
  });

  // Token nie zurueckspiegeln – er steht ohnehin im Browser, gehoert aber
  // nicht in Logs oder Netzwerk-Mitschnitte der Antwort.
  return NextResponse.json({
    ok: true,
    geraet: abo.geraet,
    typen: abo.typen,
    angelegt: abo.angelegt,
  });
}

export async function DELETE(req: NextRequest) {
  const token = req.nextUrl.searchParams.get("token")?.trim() || "";
  if (!token) {
    return NextResponse.json({ fehler: "token fehlt." }, { status: 400 });
  }
  await entferneAbo(token);
  return NextResponse.json({ ok: true });
}
