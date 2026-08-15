import { NextRequest, NextResponse } from "next/server";
import {
  geraetAusKatalog,
  holeGeraeteZustand,
  sendeBefehl,
  tuyaGrundkonfiguriert,
} from "@/lib/tuya";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Schaltet einen Datenpunkt eines freigegebenen Tuya-Geraets.
 *
 * Nutzlast: { "code": "switch_1", "value": true }
 *
 * Zwei Sicherungen, weil hier echte Technik im Stall geschaltet wird:
 *   1. Die Geraete-ID aus der URL muss in der Allowlist (TUYA_GERAETE) stehen —
 *      sonst laesst sich ueber diese Route kein anderes Geraet des
 *      Tuya-Kontos ansprechen.
 *   2. Der `code` muss eine Funktion sein, die das Geraet selbst meldet, und
 *      der Werttyp muss zum Geraetemodell passen. Damit kann ein
 *      manipulierter Request keine unbekannten Datenpunkte beschreiben.
 */
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> },
) {
  if (!tuyaGrundkonfiguriert()) {
    return NextResponse.json(
      { fehler: "Tuya nicht konfiguriert." },
      { status: 503 },
    );
  }

  const { id } = await params;
  const geraet = geraetAusKatalog(id);
  if (!geraet) {
    return NextResponse.json(
      { fehler: "Gerät nicht freigegeben." },
      { status: 404 },
    );
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ fehler: "Kein gültiges JSON." }, { status: 400 });
  }
  const b = body as Record<string, unknown>;
  const code = typeof b.code === "string" ? b.code : "";
  const value = b.value;
  if (!code) {
    return NextResponse.json({ fehler: "code fehlt." }, { status: 400 });
  }
  if (
    typeof value !== "boolean" &&
    typeof value !== "number" &&
    typeof value !== "string"
  ) {
    return NextResponse.json(
      { fehler: "value muss boolean, number oder string sein." },
      { status: 400 },
    );
  }

  const zustand = await holeGeraeteZustand(geraet);
  if (zustand.fehler) {
    return NextResponse.json({ fehler: zustand.fehler }, { status: 502 });
  }
  const funktion = zustand.funktionen.find((f) => f.code === code);
  if (!funktion) {
    return NextResponse.json(
      { fehler: `Funktion "${code}" gibt es an diesem Gerät nicht.` },
      { status: 400 },
    );
  }
  if (!typPasst(funktion.type, value)) {
    return NextResponse.json(
      { fehler: `Wert passt nicht zum Typ ${funktion.type}.` },
      { status: 400 },
    );
  }

  try {
    await sendeBefehl(geraet.id, code, value);
  } catch (e) {
    return NextResponse.json(
      { fehler: e instanceof Error ? e.message : "Befehl fehlgeschlagen." },
      { status: 502 },
    );
  }

  // Frischen Zustand mitliefern, damit die UI nicht raten muss. Tuya
  // uebernimmt den Wert nicht immer sofort – die Steuerung zeigt daher den
  // gemeldeten Wert, nicht den gewuenschten.
  return NextResponse.json({
    ok: true,
    zustand: await holeGeraeteZustand(geraet),
  });
}

/** Prueft den Werttyp gegen den Typ aus dem Tuya-Geraetemodell. */
function typPasst(typ: string, value: unknown): boolean {
  switch (typ.toLowerCase()) {
    case "boolean":
      return typeof value === "boolean";
    case "integer":
    case "value":
      return typeof value === "number" && Number.isFinite(value);
    case "enum":
    case "string":
      return typeof value === "string";
    case "json":
      return typeof value === "string" || typeof value === "number";
    default:
      // Unbekannte Typen laesst Tuya selbst pruefen und lehnt sie sonst ab.
      return true;
  }
}
