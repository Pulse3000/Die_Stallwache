import { NextRequest, NextResponse } from "next/server";
import { getEreignisse, getLebenszeichen } from "@/lib/events";
import { baueStallStatus, STANDARD_FENSTER_STUNDEN } from "@/lib/stall-status";
import { tokenGleich } from "@/lib/token";

export const dynamic = "force-dynamic";
// node:crypto (zeitkonstanter Token-Vergleich) braucht die Node-Runtime.
export const runtime = "nodejs";

/**
 * Statusabfrage: ordnet die Befunde des Edge-Agenten je Kamera und Kuh in
 * OK / WARNUNG / KRITISCH / UNBEKANNT ein (docs/statusabfrage-spezifikation.md).
 * Reine Lese-Schnittstelle — loest nie eine Benachrichtigung aus.
 *
 * Parameter (alle optional):
 *   ?stunden=12          Auswertungsfenster, 1–72
 *   ?kamera=stallwache   nur diese Kamera
 *   ?kuh=42              nur diese Kuh (exakte Nummer)
 *
 * Auth, zwei Wege:
 *   - Header x-status-token = STATUS_READ_TOKEN — fuer externe Routinen
 *     (Tagesreport). Eigener Token, damit Lesen nie Einspeisen erlaubt.
 *   - ohne Header: App-Session wie jede andere Route (middleware.ts).
 */
export async function GET(req: NextRequest) {
  const gegeben = req.headers.get("x-status-token");
  if (gegeben !== null) {
    const soll = process.env.STATUS_READ_TOKEN?.trim();
    if (!soll) {
      return NextResponse.json(
        { fehler: "Statusabfrage per Token nicht konfiguriert – STATUS_READ_TOKEN setzen." },
        { status: 503 },
      );
    }
    if (!tokenGleich(gegeben, soll)) {
      return NextResponse.json({ fehler: "Ungültiger Token." }, { status: 401 });
    }
  }

  const p = req.nextUrl.searchParams;
  const zahl = (roh: string | undefined, standard: number) => {
    const n = Number(roh);
    return roh && Number.isFinite(n) && n > 0 ? n : standard;
  };

  const [alle, lebenszeichen] = await Promise.all([getEreignisse(), getLebenszeichen()]);
  const status = baueStallStatus(
    {
      ereignisse: alle.ereignisse,
      quelle: alle.quelle,
      letzterKontakt: alle.letzterKontakt,
      lebenszeichen,
    },
    {
      stunden: zahl(p.get("stunden") ?? undefined, STANDARD_FENSTER_STUNDEN),
      kamera: p.get("kamera")?.trim() || undefined,
      kuh: p.get("kuh")?.trim() || undefined,
      cooldownMinuten: zahl(process.env.STATUS_COOLDOWN_MINUTEN?.trim(), 15),
      lebenszeichenMaxMinuten: zahl(
        process.env.STATUS_LEBENSZEICHEN_MAX_MINUTEN?.trim(),
        15,
      ),
      zeitzone: process.env.ANALYTIK_ZEITZONE?.trim() || undefined,
    },
  );

  return NextResponse.json(status, { headers: { "Cache-Control": "no-store" } });
}
