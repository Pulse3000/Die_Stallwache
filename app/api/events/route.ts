import { NextRequest, NextResponse } from "next/server";
import {
  addEreignis,
  EREIGNIS_TYPEN,
  getEreignisse,
  type EreignisTyp,
} from "@/lib/events";

export const dynamic = "force-dynamic";

/** Dashboard liest die Ereignisliste (neueste zuerst). */
export async function GET() {
  return NextResponse.json(await getEreignisse(), {
    headers: { "Cache-Control": "no-store" },
  });
}

/**
 * Ingest-Endpoint fuer den Edge-Agenten im Stall.
 *
 * Auth: Header  x-ingest-token  muss EDGE_INGEST_TOKEN (Vercel-Env) entsprechen.
 * Ohne gesetzte Env-Variable bleibt der Endpoint geschlossen (503), damit das
 * oeffentliche Dashboard nicht mit Fremd-Ereignissen geflutet werden kann.
 */
export async function POST(req: NextRequest) {
  const token = process.env.EDGE_INGEST_TOKEN?.trim();
  if (!token) {
    return NextResponse.json(
      { fehler: "Ingest nicht konfiguriert – EDGE_INGEST_TOKEN setzen." },
      { status: 503 },
    );
  }
  if (req.headers.get("x-ingest-token") !== token) {
    return NextResponse.json({ fehler: "Ungültiger Token." }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ fehler: "Kein gültiges JSON." }, { status: 400 });
  }

  const b = body as Record<string, unknown>;
  const typ = b.typ as EreignisTyp;
  if (!EREIGNIS_TYPEN.includes(typ)) {
    return NextResponse.json(
      { fehler: `Unbekannter typ – erlaubt: ${EREIGNIS_TYPEN.join(", ")}` },
      { status: 400 },
    );
  }
  const nachricht = typeof b.nachricht === "string" ? b.nachricht.slice(0, 500) : "";
  if (!nachricht) {
    return NextResponse.json({ fehler: "nachricht fehlt." }, { status: 400 });
  }

  const ereignis = await addEreignis({
    typ,
    nachricht,
    kuhId: typeof b.kuhId === "string" ? b.kuhId.slice(0, 50) : null,
    kamera: typeof b.kamera === "string" ? b.kamera.slice(0, 50) : "stallwache",
    konfidenz:
      typeof b.konfidenz === "number" && b.konfidenz >= 0 && b.konfidenz <= 1
        ? b.konfidenz
        : null,
    zeit:
      typeof b.zeit === "string" && !Number.isNaN(Date.parse(b.zeit))
        ? b.zeit
        : undefined,
  });

  return NextResponse.json({ ok: true, id: ereignis.id }, { status: 201 });
}
