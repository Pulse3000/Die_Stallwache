/**
 * GET /api/lagebericht — Aggregierte Lage für den Tagesreport.
 *
 * Liefert Punkte 2 (Brunst-/Kalbeüberwachung) und 3 (Sonstige Auffälligkeiten)
 * als strukturierte Daten, die die Tagesreport-Routine maschinell auswerten kann.
 *
 * Spezifikation: docs/lagebericht-vertrag.md
 * Eigener Token: REPORT_READ_TOKEN (≠ EDGE_INGEST_TOKEN)
 */

import { NextRequest, NextResponse } from "next/server";
import { getEreignisse, getLebenszeichen } from "@/lib/events";
import { tokenGleich } from "@/lib/token";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const BEKANNTE_KAMERAS = ["stallwache", "futterwache", "stallbox"] as const;

const antwort503 = (fehler: string) =>
  NextResponse.json({ fehler }, { status: 503, headers: { "Cache-Control": "no-store" } });

export async function GET(req: NextRequest) {
  // --- Token ---
  const token = process.env.REPORT_READ_TOKEN?.trim();
  if (!token) {
    return antwort503("Lagebericht nicht konfiguriert – REPORT_READ_TOKEN setzen.");
  }
  if (!tokenGleich(req.headers.get("x-report-token"), token)) {
    return NextResponse.json(
      { fehler: "Ungültiger Token." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  // --- Parameter ---
  const stundenRoh = req.nextUrl.searchParams.get("stunden");
  const stunden = stundenRoh !== null ? Number(stundenRoh) : 12;
  if (stundenRoh !== null && (!Number.isInteger(stunden) || stunden < 1 || stunden > 72)) {
    return NextResponse.json(
      { fehler: "stunden muss eine Ganzzahl zwischen 1 und 72 sein." },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  // --- Persistenz lesen ---
  const [alle, lebenszeichenRoh] = await Promise.all([
    getEreignisse(),
    getLebenszeichen(),
  ]);

  // 503 wenn KV konfiguriert aber nicht erreichbar (speicher: "instanz" statt "kv")
  const kvKonfiguriert = Boolean(
    process.env.KV_REST_API_URL?.trim() && process.env.KV_REST_API_TOKEN?.trim(),
  );
  if (kvKonfiguriert && alle.speicher === "instanz") {
    return antwort503("Persistenz nicht lesbar – KV-Store antwortet nicht.");
  }

  // --- Zeitraum ---
  const jetzt = Date.now();
  const grenze = jetzt - stunden * 3_600_000;
  const von = new Date(grenze).toISOString();
  const bis = new Date(jetzt).toISOString();

  // --- Filtern ---
  const imZeitraum = alle.ereignisse.filter((e) => {
    const t = Date.parse(e.zeit);
    return !Number.isNaN(t) && t >= grenze;
  });

  // --- Zähler ---
  const zaehler = { kalbeverdacht: 0, austreibung: 0, brunstverdacht: 0, info: 0 };
  const jeKamera: Record<string, typeof zaehler> = {};

  for (const e of imZeitraum) {
    if (e.typ in zaehler) (zaehler as Record<string, number>)[e.typ]++;
    if (!jeKamera[e.kamera]) {
      jeKamera[e.kamera] = { kalbeverdacht: 0, austreibung: 0, brunstverdacht: 0, info: 0 };
    }
    if (e.typ in jeKamera[e.kamera]) (jeKamera[e.kamera] as Record<string, number>)[e.typ]++;
  }

  // --- letzte_ereignisse (max 20, neueste zuerst, genau 6 Felder) ---
  const letzte_ereignisse = imZeitraum.slice(0, 20).map((e) => ({
    zeit: e.zeit,
    typ: e.typ,
    kuhId: e.kuhId,
    kamera: e.kamera,
    nachricht: e.nachricht,
    konfidenz: e.konfidenz,
  }));

  // --- letztes_lebenszeichen (alle bekannten + gesehenen Kameras) ---
  const letztes_lebenszeichen: Record<string, string | null> = {};
  const alleKameras = new Set<string>([
    ...BEKANNTE_KAMERAS,
    ...Object.keys(lebenszeichenRoh),
    ...alle.ereignisse.map((e) => e.kamera),
  ]);
  for (const kamera of alleKameras) {
    letztes_lebenszeichen[kamera] = lebenszeichenRoh[kamera]?.zeit ?? null;
  }

  return NextResponse.json(
    {
      erzeugt: new Date().toISOString(),
      zeitraum: { von, bis, stunden },
      quelle: {
        name: alle.speicher === "kv" ? "Upstash KV" : "In-Memory-Ringpuffer",
      },
      zaehler,
      je_kamera: jeKamera,
      letzte_ereignisse,
      letztes_lebenszeichen,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
}
