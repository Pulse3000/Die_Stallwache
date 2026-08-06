import { NextResponse } from "next/server";
import { firebaseWebKonfig, pushVersandMoeglich } from "@/lib/push";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Liefert dem Browser die Firebase-Web-Konfiguration fuer die Token-Anfrage.
 *
 * Diese Werte sind nach Firebase-Design oeffentlich (sie stehen bei jeder
 * Firebase-Web-App im Bundle) — der eigentliche Schutz ist der VAPID-Schlüssel
 * plus die serverseitige Absenderberechtigung. Sie liegen hier trotzdem in
 * Server-Env-Variablen statt in NEXT_PUBLIC_*, damit ein Projektwechsel kein
 * neues Deployment braucht.
 *
 * `aktiv` heisst: Browser-Anmeldung UND Serverversand sind moeglich. Fehlt
 * eines von beidem, zeigt die Einstellungsseite den konkreten fehlenden
 * Baustein statt eines stummen Knopfes.
 */
export async function GET() {
  const konfig = firebaseWebKonfig();
  return NextResponse.json(
    {
      aktiv: Boolean(konfig) && pushVersandMoeglich(),
      versandBereit: pushVersandMoeglich(),
      konfig,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
