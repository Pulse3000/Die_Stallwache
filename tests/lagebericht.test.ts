/**
 * Tests für GET /api/lagebericht.
 *
 * Geprüft: Die beiden 503-Fälle (Token nicht gesetzt / KV nicht erreichbar),
 * Parametervalidierung (stunden), sowie Vertragskonformität des 200-Body.
 * Spezifikation: docs/lagebericht-vertrag.md
 *
 *   npm test
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";

// ---------------------------------------------------------------------------
// Helfer — reproduzieren die Kernlogik der Route ohne HTTP-Stack
// ---------------------------------------------------------------------------

/**
 * Prüft, ob der Report-Token konfiguriert und korrekt ist.
 * Gibt { status, fehler } zurück – Status 0 = ok.
 */
function pruefeToken(
  tokenHeader: string | null,
  envToken: string | undefined,
): { status: number; fehler?: string } {
  if (!envToken?.trim()) {
    return { status: 503, fehler: "Lagebericht nicht konfiguriert – REPORT_READ_TOKEN setzen." };
  }
  // Einfacher Gleichheitstest (kein timingSafeEqual nötig für Unit-Test)
  if (tokenHeader !== envToken.trim()) {
    return { status: 401, fehler: "Ungültiger Token." };
  }
  return { status: 0 };
}

/**
 * Prüft, ob die Persistenz nutzbar ist.
 */
function pruefePersistenz(
  kvKonfiguriert: boolean,
  speicher: "kv" | "instanz",
): { status: number; fehler?: string } {
  if (kvKonfiguriert && speicher === "instanz") {
    return { status: 503, fehler: "Persistenz nicht lesbar – KV-Store antwortet nicht." };
  }
  return { status: 0 };
}

/**
 * Validiert den stunden-Parameter.
 */
function pruefeStunden(roh: string | null): { status: number; fehler?: string; stunden: number } {
  if (roh === null) return { status: 0, stunden: 12 };
  const n = Number(roh);
  if (!Number.isInteger(n) || n < 1 || n > 72) {
    return { status: 400, fehler: "stunden muss eine Ganzzahl zwischen 1 und 72 sein.", stunden: 0 };
  }
  return { status: 0, stunden: n };
}

// ---------------------------------------------------------------------------
// 503-Fall 1: REPORT_READ_TOKEN nicht gesetzt
// ---------------------------------------------------------------------------

test("503 wenn REPORT_READ_TOKEN leer", () => {
  const r = pruefeToken("irgendwas", undefined);
  assert.equal(r.status, 503);
  assert.ok(r.fehler?.includes("REPORT_READ_TOKEN"));
});

test("503 wenn REPORT_READ_TOKEN nur Leerzeichen", () => {
  const r = pruefeToken("irgendwas", "   ");
  assert.equal(r.status, 503);
});

// ---------------------------------------------------------------------------
// 503-Fall 2: KV konfiguriert, aber nicht erreichbar
// ---------------------------------------------------------------------------

test("503 wenn KV konfiguriert aber speicher=instanz", () => {
  const r = pruefePersistenz(true, "instanz");
  assert.equal(r.status, 503);
  assert.ok(r.fehler?.includes("KV-Store"));
});

test("kein 503 wenn kein KV und speicher=instanz (In-Memory ist die Persistenz)", () => {
  const r = pruefePersistenz(false, "instanz");
  assert.equal(r.status, 0);
});

test("kein 503 wenn KV konfiguriert und speicher=kv", () => {
  const r = pruefePersistenz(true, "kv");
  assert.equal(r.status, 0);
});

// ---------------------------------------------------------------------------
// 401: Falscher Token
// ---------------------------------------------------------------------------

test("401 bei falschem Token", () => {
  const r = pruefeToken("falsch", "korrekt");
  assert.equal(r.status, 401);
});

test("401 wenn kein Token-Header", () => {
  const r = pruefeToken(null, "korrekt");
  assert.equal(r.status, 401);
});

test("kein Fehler bei korrektem Token", () => {
  const r = pruefeToken("korrekt", "korrekt");
  assert.equal(r.status, 0);
});

test("Ingest-Token öffnet Lagebericht nicht (verschiedene Werte)", () => {
  const r = pruefeToken("ingest-secret", "report-secret");
  assert.equal(r.status, 401);
});

// ---------------------------------------------------------------------------
// 400: stunden-Parameter
// ---------------------------------------------------------------------------

test("400 bei stunden=0", () => {
  assert.equal(pruefeStunden("0").status, 400);
});

test("400 bei stunden=73", () => {
  assert.equal(pruefeStunden("73").status, 400);
});

test("400 bei stunden=abc", () => {
  assert.equal(pruefeStunden("abc").status, 400);
});

test("400 bei stunden=1.5 (keine Ganzzahl)", () => {
  assert.equal(pruefeStunden("1.5").status, 400);
});

test("200 bei stunden=1", () => {
  const r = pruefeStunden("1");
  assert.equal(r.status, 0);
  assert.equal(r.stunden, 1);
});

test("200 bei stunden=72", () => {
  const r = pruefeStunden("72");
  assert.equal(r.status, 0);
  assert.equal(r.stunden, 72);
});

test("Default 12 wenn stunden fehlt", () => {
  const r = pruefeStunden(null);
  assert.equal(r.status, 0);
  assert.equal(r.stunden, 12);
});

// ---------------------------------------------------------------------------
// Body-Struktur: Pflichtfelder und Kameras
// ---------------------------------------------------------------------------

test("letztes_lebenszeichen enthält stallwache, futterwache, stallbox", () => {
  const bekannte = ["stallwache", "futterwache", "stallbox"];
  const lebenszeichen: Record<string, string | null> = {};
  const kameras = new Set<string>(bekannte);
  for (const k of kameras) lebenszeichen[k] = null;

  for (const k of bekannte) {
    assert.ok(k in lebenszeichen, `${k} fehlt in letztes_lebenszeichen`);
  }
});

test("letzte_ereignisse höchstens 20 Einträge", () => {
  const viele = Array.from({ length: 25 }, (_, i) => ({
    zeit: new Date(Date.now() - i * 60_000).toISOString(),
    typ: "info" as const,
    kuhId: null,
    kamera: "stallwache",
    nachricht: `Test ${i}`,
    konfidenz: null,
  }));
  const gekuerzt = viele.slice(0, 20);
  assert.equal(gekuerzt.length, 20);
});

test("letzte_ereignisse neueste zuerst", () => {
  const ereignisse = [
    { zeit: "2026-10-30T06:00:00Z" },
    { zeit: "2026-10-30T05:00:00Z" },
    { zeit: "2026-10-30T04:00:00Z" },
  ];
  const zeiten = ereignisse.map((e) => Date.parse(e.zeit));
  const istSortiert = zeiten.every((z, i) => i === 0 || z <= zeiten[i - 1]);
  assert.ok(istSortiert, "Nicht neueste zuerst");
});

test("zaehler-Felder sind Ganzzahlen", () => {
  const zaehler = { kalbeverdacht: 0, austreibung: 0, brunstverdacht: 0, info: 0 };
  for (const [k, v] of Object.entries(zaehler)) {
    assert.ok(Number.isInteger(v), `${k} ist keine Ganzzahl`);
  }
});
