import { NextResponse } from "next/server";
import { getBild } from "@/lib/events";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Liefert ein einzelnes Alarmbild (komprimiertes JPEG) des Ereignisses.
 *
 * Bewusst als eigener Endpoint statt eingebettet in die Ereignisliste: so
 * bleibt der Listenabruf im Mobilfunk klein und das Bild wandert erst ueber
 * die Leitung, wenn der Landwirt den Alarm oeffnet ("Datensparen").
 *
 * Der Inhalt eines Bildes aendert sich nie — daher `immutable`. Der Service
 * Worker legt es damit dauerhaft ab und das Replay funktioniert offline.
 */
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string; index: string }> },
) {
  const { id, index } = await params;
  const nr = Number(index);
  if (!Number.isInteger(nr) || nr < 0 || nr > 9) {
    return NextResponse.json({ fehler: "Ungültiger Bildindex." }, { status: 400 });
  }

  const bild = await getBild(id, nr);
  if (!bild) {
    return NextResponse.json({ fehler: "Bild nicht gefunden." }, { status: 404 });
  }

  return new NextResponse(bild as unknown as BodyInit, {
    headers: {
      "Content-Type": "image/jpeg",
      "Content-Length": String(bild.byteLength),
      "Cache-Control": "private, max-age=604800, immutable",
    },
  });
}
