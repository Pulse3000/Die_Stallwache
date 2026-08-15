import { NextRequest, NextResponse } from "next/server";
import { getEreignisse } from "@/lib/events";
import { baueBericht, STANDARD_ZEITZONE, ZEITRAEUME } from "@/lib/analytik";

export const dynamic = "force-dynamic";

/**
 * Langzeitauswertung fuer die Analytik-Seite.
 *
 * Aggregiert wird **serverseitig**: Bei gefuelltem Speicher stehen gemessen
 * ~48 kB Rohliste ~10 kB Bericht gegenueber. Ueber Mobilfunk im Stall ist das
 * die Sorte Unterschied, die man beim Laden merkt.
 *
 * Query:
 *   ?tage=7|14|30   Betrachtungszeitraum (Default 7)
 *
 * Zeitzone der Tages-/Stundenraster ueber ANALYTIK_ZEITZONE (Default
 * Europe/Berlin) — Vercel laeuft in UTC, ein Tagesgang waere sonst verschoben.
 *
 * Die Route liest nur, veraendert nichts und braucht deshalb keinen eigenen
 * Token: Vor ihr liegt bereits der App-weite Login (`middleware.ts`).
 */
export async function GET(req: NextRequest) {
  const roh = Number(req.nextUrl.searchParams.get("tage"));
  // Nur die angebotenen Zeitraeume zulassen — sonst laesst sich der Server
  // ueber ?tage=100000 zu sinnlos grossen Verlaufsarrays ueberreden.
  const zeitraumTage = (ZEITRAEUME as readonly number[]).includes(roh)
    ? roh
    : ZEITRAEUME[0];

  const { ereignisse, quelle } = await getEreignisse();

  const bericht = baueBericht(ereignisse, {
    zeitraumTage,
    zeitzone: process.env.ANALYTIK_ZEITZONE?.trim() || STANDARD_ZEITZONE,
    quelle,
  });

  return NextResponse.json(bericht, {
    headers: { "Cache-Control": "no-store" },
  });
}
