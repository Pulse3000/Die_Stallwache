import { NextResponse } from "next/server";
import { quittiereEreignis } from "@/lib/events";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Quittiert einen Alarm ("gesehen").
 *
 * Zweck ist nicht Buchhaltung, sondern Ruhe: ein quittierter Alarm faellt in
 * der Liste zurueck und wiederholt sich nicht als roter Punkt. Der Aufruf ist
 * idempotent — die Offline-Warteschlange darf ihn gefahrlos wiederholen.
 *
 * Der Schutz laeuft ueber die Session (middleware.ts); der Ingest-Token des
 * Edge-Agenten gilt hier bewusst nicht.
 */
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const ereignis = await quittiereEreignis(id);
  if (!ereignis) {
    return NextResponse.json(
      { fehler: "Ereignis nicht gefunden (evtl. schon aus dem Puffer gefallen)." },
      { status: 404 },
    );
  }
  return NextResponse.json({ ok: true, ereignis });
}
