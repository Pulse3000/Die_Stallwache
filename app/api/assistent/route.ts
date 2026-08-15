import { NextRequest, NextResponse } from "next/server";
import { beantworteFrage, kiKonfiguriert } from "@/lib/assistent";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** Meldet, ob eine KI angebunden ist (die Oberflaeche beschriftet sich danach). */
export async function GET() {
  return NextResponse.json(
    { ki: kiKonfiguriert() },
    { headers: { "Cache-Control": "no-store" } },
  );
}

/**
 * Beantwortet eine Freitext- oder Sprachanfrage des Landwirts.
 *
 * Nutzlast: { "frage": "Zeig mir alle Aktivitäten von Kuh #42" }
 *
 * Die Spracherkennung laeuft im Browser (Web Speech API) – hier kommt bereits
 * fertiger Text an. Das spart Audio-Upload im Funkloch und haelt die Antwort
 * schnell.
 */
export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ fehler: "Kein gültiges JSON." }, { status: 400 });
  }

  const roh = (body as Record<string, unknown>).frage;
  const frage = typeof roh === "string" ? roh.trim().slice(0, 500) : "";
  if (!frage) {
    return NextResponse.json({ fehler: "frage fehlt." }, { status: 400 });
  }

  try {
    return NextResponse.json(await beantworteFrage(frage), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (e) {
    return NextResponse.json(
      { fehler: e instanceof Error ? e.message : "Anfrage fehlgeschlagen." },
      { status: 502 },
    );
  }
}
