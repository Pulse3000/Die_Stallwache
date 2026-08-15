import { NextResponse } from "next/server";
import type { StallEreignis } from "@/lib/events";
import { pushVersandMoeglich, sendeAlarmPush } from "@/lib/push";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Schickt eine Probe-Benachrichtigung an alle angemeldeten Geraete.
 *
 * Der Kalbealarm kommt nachts um drei — dann ist die falsche Zeit, um
 * herauszufinden, dass das Handy stumm geschaltet war. Diese Route macht die
 * Kette Server -> FCM -> Service Worker -> Sperrbildschirm einmal bewusst
 * pruefbar.
 *
 * Das Probe-Ereignis wird absichtlich NICHT gespeichert und nicht nach
 * Pub/Sub gespiegelt: es soll im Aktivitätsprotokoll keine Spur hinterlassen.
 */
export async function POST() {
  if (!pushVersandMoeglich()) {
    return NextResponse.json(
      {
        fehler:
          "Push-Versand nicht konfiguriert – GCP_SERVICE_ACCOUNT_JSON und Firebase-Projekt setzen.",
      },
      { status: 503 },
    );
  }

  const probe: StallEreignis = {
    id: `probe-${Date.now()}`,
    typ: "brunstverdacht",
    kuhId: "Probealarm",
    kamera: "stallwache",
    nachricht: "Testbenachrichtigung – die Alarmkette funktioniert.",
    konfidenz: null,
    zeit: new Date().toISOString(),
    bilder: 0,
    quittiert: null,
  };

  const ergebnis = await sendeAlarmPush(probe);
  return NextResponse.json({ ok: true, ...ergebnis });
}
