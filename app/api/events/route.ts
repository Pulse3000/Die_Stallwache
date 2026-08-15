import { NextRequest, NextResponse } from "next/server";
import {
  addEreignis,
  EREIGNIS_TYPEN,
  getGefilterteEreignisse,
  meldeKontakt,
  type EreignisTyp,
} from "@/lib/events";
import { sendeAlarmPush } from "@/lib/push";
import { veroeffentlicheEreignis } from "@/lib/pubsub";

export const dynamic = "force-dynamic";
// node:crypto (Service-Account-Signatur fuer FCM/Pub/Sub) braucht die Node-Runtime.
export const runtime = "nodejs";

/**
 * Dashboard liest die Ereignisliste (neueste zuerst).
 *
 * Filter (alle optional, kombinierbar):
 *   ?typ=austreibung,kalbeverdacht   nur diese Typen
 *   ?stunden=24                      nur die letzten N Stunden
 *   ?kuh=42                          Teiltreffer auf der Kuh-ID
 *   ?limit=50                        Obergrenze
 */
export async function GET(req: NextRequest) {
  const p = req.nextUrl.searchParams;

  const typen = (p.get("typ") ?? "")
    .split(",")
    .map((t) => t.trim())
    .filter((t): t is EreignisTyp => EREIGNIS_TYPEN.includes(t as EreignisTyp));

  const zahl = (name: string): number | undefined => {
    const roh = p.get(name);
    if (roh === null) return undefined;
    const n = Number(roh);
    return Number.isFinite(n) && n > 0 ? n : undefined;
  };

  const antwort = await getGefilterteEreignisse({
    typen: typen.length > 0 ? typen : undefined,
    stunden: zahl("stunden"),
    kuhId: p.get("kuh")?.trim() || undefined,
    limit: zahl("limit"),
  });

  return NextResponse.json(antwort, {
    headers: { "Cache-Control": "no-store" },
  });
}

/**
 * Ingest-Endpoint fuer den Edge-Agenten im Stall.
 *
 * Auth: Header  x-ingest-token  muss EDGE_INGEST_TOKEN (Vercel-Env) entsprechen.
 * Ohne gesetzte Env-Variable bleibt der Endpoint geschlossen (503), damit das
 * oeffentliche Dashboard nicht mit Fremd-Ereignissen geflutet werden kann.
 *
 * Nutzlast: ein einzelnes Ereignis ODER — fuer die Offline-Nachlieferung des
 * Agenten — ein Stapel:
 *   { "ereignisse": [ {...}, {...} ] }
 * Ein fehlerhafter Eintrag im Stapel verwirft nie den ganzen Stapel; die
 * Antwort meldet pro Eintrag Erfolg oder Grund.
 *
 * Optionale Felder je Ereignis:
 *   bild      Base64-JPEG (ohne data:-Praefix)  – Einzelbild
 *   bilder    Array von Base64-JPEGs            – Bildserie fuer das Replay
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

  // Stapel (Offline-Nachlieferung) oder Einzelereignis.
  const roh = body as Record<string, unknown>;
  const stapel = Array.isArray(roh?.ereignisse)
    ? (roh.ereignisse as unknown[])
    : Array.isArray(body)
      ? (body as unknown[])
      : null;

  if (stapel) {
    if (stapel.length === 0) {
      // Leerer Stapel ist ein gueltiges Lebenszeichen ("nichts nachzuliefern").
      await meldeKontakt();
      return NextResponse.json({ ok: true, angenommen: 0, ergebnisse: [] });
    }
    if (stapel.length > 100) {
      return NextResponse.json(
        { fehler: "Höchstens 100 Ereignisse pro Stapel." },
        { status: 400 },
      );
    }
    const ergebnisse = [];
    let angenommen = 0;
    for (const eintrag of stapel) {
      const r = await verarbeite(eintrag);
      if ("id" in r) angenommen++;
      ergebnisse.push(r);
    }
    // `ok` muss zum Status passen: Ein Stapel, in dem jeder Eintrag
    // abgelehnt wurde, ist nicht in Ordnung — auch wenn der eigene Agent
    // nur den Statuscode auswertet, ist alles andere eine Falle fuer
    // jeden weiteren Client.
    return NextResponse.json(
      { ok: angenommen > 0, angenommen, ergebnisse },
      { status: angenommen > 0 ? 201 : 400 },
    );
  }

  const ergebnis = await verarbeite(body);
  if ("fehler" in ergebnis) {
    return NextResponse.json(ergebnis, { status: 400 });
  }
  return NextResponse.json({ ok: true, ...ergebnis }, { status: 201 });
}

type Ergebnis =
  | { id: string; push: number; pubsub: boolean }
  | { fehler: string };

/** Validiert und speichert ein einzelnes Ereignis samt Folgewirkungen. */
async function verarbeite(eintrag: unknown): Promise<Ergebnis> {
  if (typeof eintrag !== "object" || eintrag === null) {
    return { fehler: "Ereignis ist kein Objekt." };
  }
  const b = eintrag as Record<string, unknown>;

  const typ = b.typ as EreignisTyp;
  if (!EREIGNIS_TYPEN.includes(typ)) {
    return { fehler: `Unbekannter typ – erlaubt: ${EREIGNIS_TYPEN.join(", ")}` };
  }
  const nachricht =
    typeof b.nachricht === "string" ? b.nachricht.slice(0, 500) : "";
  if (!nachricht) return { fehler: "nachricht fehlt." };

  // Einzelbild und Bildserie werden gleich behandelt; data:-Praefix abstreifen.
  const rohBilder: unknown[] = Array.isArray(b.bilder)
    ? b.bilder
    : typeof b.bild === "string"
      ? [b.bild]
      : [];
  const bilder = rohBilder
    .filter((x): x is string => typeof x === "string")
    .map((x) => x.replace(/^data:image\/[a-z+]+;base64,/i, "").trim())
    .filter((x) => x.length > 0);

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
    bilder,
  });

  // Push und Pub/Sub duerfen den Ingest nie scheitern lassen.
  const [push, pubsub] = await Promise.all([
    sendeAlarmPush(ereignis).catch((e) => {
      console.error("Push-Versand fehlgeschlagen:", e);
      return { zugestellt: 0, entfernt: 0, fehler: 0 };
    }),
    veroeffentlicheEreignis(ereignis),
  ]);

  return { id: ereignis.id, push: push.zugestellt, pubsub };
}
