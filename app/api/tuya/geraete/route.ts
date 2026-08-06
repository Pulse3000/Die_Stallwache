import { NextResponse } from "next/server";
import {
  geraeteKatalog,
  holeAlleGeraete,
  tuyaGrundkonfiguriert,
} from "@/lib/tuya";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Zustand aller freigegebenen Tuya-Geraete (Traenken, Licht, Sensoren, Kameras).
 *
 * Freigegeben heisst: in TUYA_GERAETE eingetragen (siehe lib/tuya.ts). Ein
 * Tuya-Konto umfasst oft mehr als den Stall – die App zeigt und steuert nur,
 * was der Betreiber ausdruecklich freigegeben hat.
 */
export async function GET() {
  if (!tuyaGrundkonfiguriert()) {
    return NextResponse.json(
      {
        fehler:
          "Tuya nicht konfiguriert – TUYA_ACCESS_ID und TUYA_ACCESS_SECRET setzen.",
        geraete: [],
      },
      { status: 503 },
    );
  }
  if (geraeteKatalog().length === 0) {
    return NextResponse.json(
      {
        geraete: [],
        hinweis:
          "Keine Geräte freigegeben – TUYA_GERAETE setzen (Format: id:Name:art, kommagetrennt).",
      },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  return NextResponse.json(
    { geraete: await holeAlleGeraete() },
    { headers: { "Cache-Control": "no-store" } },
  );
}
