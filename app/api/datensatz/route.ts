import { NextRequest, NextResponse } from "next/server";
import {
  gcsBucket,
  gcsKonfiguriert,
  ladeNachGcs,
  saubererPfadteil,
} from "@/lib/gcs";

export const dynamic = "force-dynamic";
// node:crypto (Service-Account-Signatur) braucht die Node-Runtime.
export const runtime = "nodejs";

/**
 * Archiv-Endpoint fuer Trainings- und Fehlalarmbilder des Edge-Agenten.
 *
 * Warum ueber die Webapp statt direkt aus dem Stall nach GCS: Der Agent laeuft
 * auf einem Rechner im Stall, an den mehrere Leute herankommen. Ein
 * GCP-Service-Account-Schluessel hat dort nichts verloren. Der Agent besitzt
 * ohnehin schon den EDGE_INGEST_TOKEN fuer /api/events – dieselbe
 * Vertrauensgrenze wird hier wiederverwendet, die GCP-Zugangsdaten bleiben
 * ausschliesslich in Vercel.
 *
 * Auth: Header  x-ingest-token  muss EDGE_INGEST_TOKEN entsprechen.
 *
 * Nutzlast:
 *   {
 *     "art":    "silent" | "fehlalarm",   // Datensammlung oder Hard Negative
 *     "kamera": "stallwache",             // optional, nur fuer den Objektnamen
 *     "bild":   "<base64-JPEG>",          // Einzelbild
 *     "bilder": ["<base64>", ...]         // oder Serie (max. 8)
 *   }
 *
 * Antworten: 201 (abgelegt) · 400 (Nutzlast) · 401 (Token) ·
 *            503 (Archiv nicht konfiguriert) · 502 (GCS-Fehler)
 *
 * Der Agent behaelt seine lokale Kopie unabhaengig vom Ergebnis – dieses
 * Archiv ist eine zweite Kopie, nie die einzige.
 */

/** Erlaubte Ablagearten – zugleich das oberste Pfad-Praefix im Bucket. */
const ARTEN = ["silent", "fehlalarm"] as const;
type Art = (typeof ARTEN)[number];

/** Obergrenze je Bild (Base64-Zeichen, ~450 kB Rohbild) – wie bei /api/events. */
const MAX_BILD_BASE64 = 600_000;
/** Eine Fehlalarm-Bildserie umfasst typischerweise 4 Frames. */
const MAX_BILDER = 8;

/** JPEG beginnt immer mit FF D8 FF – schuetzt das Archiv vor Fremdinhalten. */
function istJpeg(daten: Uint8Array): boolean {
  return (
    daten.length > 3 &&
    daten[0] === 0xff &&
    daten[1] === 0xd8 &&
    daten[2] === 0xff
  );
}

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
  if (!gcsKonfiguriert()) {
    return NextResponse.json(
      {
        fehler:
          "Datensatz-Archiv nicht konfiguriert – GCS_BUCKET und GCP_SERVICE_ACCOUNT_JSON setzen.",
      },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ fehler: "Kein gültiges JSON." }, { status: 400 });
  }
  const b = (body ?? {}) as Record<string, unknown>;

  const art = b.art as Art;
  if (!ARTEN.includes(art)) {
    return NextResponse.json(
      { fehler: `Unbekannte art – erlaubt: ${ARTEN.join(", ")}` },
      { status: 400 },
    );
  }

  const rohBilder: unknown[] = Array.isArray(b.bilder)
    ? b.bilder
    : typeof b.bild === "string"
      ? [b.bild]
      : [];
  const base64Bilder = rohBilder
    .filter((x): x is string => typeof x === "string")
    .map((x) => x.replace(/^data:image\/[a-z+]+;base64,/i, "").trim())
    .filter((x) => x.length > 0);

  if (base64Bilder.length === 0) {
    return NextResponse.json({ fehler: "bild fehlt." }, { status: 400 });
  }
  if (base64Bilder.length > MAX_BILDER) {
    return NextResponse.json(
      { fehler: `Höchstens ${MAX_BILDER} Bilder pro Anfrage.` },
      { status: 400 },
    );
  }
  if (base64Bilder.some((x) => x.length > MAX_BILD_BASE64)) {
    return NextResponse.json({ fehler: "Bild zu groß." }, { status: 400 });
  }

  const kamera = saubererPfadteil(
    typeof b.kamera === "string" ? b.kamera : "stallwache",
    "stallwache",
  );
  const tag = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const stempel = new Date().toISOString().replace(/[:.]/g, "-");

  const abgelegt: string[] = [];
  for (const [i, roh] of base64Bilder.entries()) {
    const daten = Buffer.from(roh, "base64");
    if (daten.byteLength === 0) {
      return NextResponse.json(
        { fehler: "Bild ist kein gültiges Base64." },
        { status: 400 },
      );
    }
    if (!istJpeg(daten)) {
      return NextResponse.json(
        { fehler: "Nur JPEG wird archiviert." },
        { status: 400 },
      );
    }
    // Zufallssuffix: zwei Agenten (Haupt-/Zweitkamera) duerfen sich in
    // derselben Sekunde nicht gegenseitig ueberschreiben.
    const zufall = Math.random().toString(36).slice(2, 8);
    const name = `${art}/${tag}/${kamera}-${stempel}-${i}-${zufall}.jpg`;
    try {
      await ladeNachGcs(name, new Uint8Array(daten));
      abgelegt.push(name);
    } catch (e) {
      console.error("GCS-Upload fehlgeschlagen:", e);
      return NextResponse.json(
        {
          fehler: e instanceof Error ? e.message : "GCS-Upload fehlgeschlagen",
          // Der gescheiterte Objektname hilft beim Nachsehen im Bucket und
          // zeigt zugleich, welcher Pfad tatsaechlich angesteuert wurde.
          objekt: name,
          abgelegt,
        },
        { status: 502 },
      );
    }
  }

  return NextResponse.json(
    { ok: true, bucket: gcsBucket(), abgelegt },
    { status: 201 },
  );
}
