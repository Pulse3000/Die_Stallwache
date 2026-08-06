/**
 * Ereignis-Modell der KI-Wache (Brunst- & Kalbeerkennung).
 *
 * Die Bildanalyse laeuft NICHT auf Vercel, sondern lokal im Stall auf dem
 * Edge-Agenten (siehe /edge-agent). Der Agent meldet erkannte Ereignisse per
 * POST /api/events an dieses Dashboard. Solange noch kein Agent sendet,
 * liefert der Store gekennzeichnete Demo-Daten, damit UI und API end-to-end
 * funktionieren.
 *
 * Persistenz: Sobald ein Vercel-KV-/Upstash-Redis-Store verknuepft ist
 * (Env-Variablen KV_REST_API_URL + KV_REST_API_TOKEN vorhanden), schreibt und
 * liest der Store dauerhaft ueber die Upstash-REST-API — ohne zusaetzliche
 * Abhaengigkeit, das API-Format bleibt identisch. Ohne diese Variablen (oder
 * wenn KV nicht erreichbar ist) faellt alles auf den In-Memory-Ringpuffer
 * pro Serverless-Instanz zurueck; der Ausfall des Stores darf den Ingest nie
 * blockieren.
 *
 * Alarmbilder (komprimierte JPEGs) liegen bewusst NICHT in der Ereignisliste,
 * sondern unter eigenen Schluesseln mit TTL. So bleibt der Listenabruf klein
 * genug fuer Mobilfunk (Datensparen) und das Bild wird erst geladen, wenn der
 * Landwirt den Alarm oeffnet.
 */

// Typen und Konstanten leben in lib/ereignis-modell.ts (nebenwirkungsfrei,
// damit Client-Komponenten sie ohne diesen Serverspeicher importieren
// koennen); hier weitergereicht, damit Importe aus @/lib/events weiter gehen.
import {
  ALARM_TYPEN,
  EREIGNIS_TYPEN,
  type EreignisTyp,
  type StallEreignis,
} from "@/lib/ereignis-modell";

export { ALARM_TYPEN, EREIGNIS_TYPEN };
export type { EreignisTyp, StallEreignis };

const MAX_EREIGNISSE = 200;
/** Bildserie pro Alarm — der Agent schickt typischerweise 3. */
const MAX_BILDER = 6;
/** Groessengrenze je Bild (Base64-Zeichen, ~ 450 kB Rohbild). */
const MAX_BILD_BASE64 = 600_000;
/** Lebensdauer der Alarmbilder im Store (Sekunden) — 7 Tage. */
const BILD_TTL = 7 * 24 * 3600;
/** So viele Bilder haelt der In-Memory-Fallback maximal vor. */
const MAX_BILDER_SPEICHER = 60;

interface EventStore {
  ereignisse: StallEreignis[];
  letzterKontakt: string | null;
  /** Fallback-Bildspeicher: Schluessel "<ereignisId>:<index>" -> Base64-JPEG. */
  bilder: Map<string, string>;
}

// globalThis, damit der Puffer Hot-Reloads/Re-Imports derselben Instanz uebersteht.
const store: EventStore = ((globalThis as Record<string, unknown>).__kiwache ??= {
  ereignisse: [],
  letzterKontakt: null,
  bilder: new Map<string, string>(),
}) as EventStore;
// Aeltere Instanzen dieses Objekts kannten `bilder` noch nicht.
store.bilder ??= new Map<string, string>();

// ---------------------------------------------------------------------------
// Vercel KV / Upstash Redis ueber die REST-API (bewusst ohne Zusatzpaket).
// Aktiviert sich selbst, sobald der Betreiber einen KV-Store verknuepft.
// ---------------------------------------------------------------------------

const KV_URL = process.env.KV_REST_API_URL?.trim() || "";
const KV_TOKEN = process.env.KV_REST_API_TOKEN?.trim() || "";
const kvAktiv = Boolean(KV_URL && KV_TOKEN);
const KV_LISTE = "kiwache:ereignisse";
const KV_KONTAKT = "kiwache:kontakt";
const kvBildSchluessel = (id: string, index: number) =>
  `kiwache:bild:${id}:${index}`;

/** Fuehrt eine Upstash-Pipeline aus; null bei inaktivem/fehlerhaftem KV. */
async function kvPipeline(
  befehle: (string | number)[][],
): Promise<{ result: unknown }[] | null> {
  return kvSenden("pipeline", befehle);
}

/**
 * Wie `kvPipeline`, aber als Transaktion (MULTI/EXEC).
 *
 * Nur dort noetig, wo zwischen zwei Befehlen nichts dazwischenkommen darf —
 * beim Zurueckschreiben der Ereignisliste wuerde sonst ein Alarm, der genau
 * zwischen DEL und RPUSH eintrifft, verloren gehen. Genau den Alarm gibt es
 * nicht zweimal.
 */
async function kvTransaktion(
  befehle: (string | number)[][],
): Promise<{ result: unknown }[] | null> {
  return kvSenden("multi-exec", befehle);
}

async function kvSenden(
  endpunkt: "pipeline" | "multi-exec",
  befehle: (string | number)[][],
): Promise<{ result: unknown }[] | null> {
  if (!kvAktiv) return null;
  try {
    const res = await fetch(`${KV_URL}/${endpunkt}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${KV_TOKEN}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(befehle),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`KV antwortet mit HTTP ${res.status}`);
    return (await res.json()) as { result: unknown }[];
  } catch (e) {
    // Store-Ausfall darf Ingest/Dashboard nie blockieren -> In-Memory weiter.
    console.error("KV nicht erreichbar – nutze In-Memory-Fallback:", e);
    return null;
  }
}

/**
 * Legt ein Alarmbild ab (Base64-JPEG, ohne data:-Praefix).
 * Fallback-Speicher ist bewusst klein und verdraengt die aeltesten Eintraege.
 */
function merkeBild(id: string, index: number, base64: string): void {
  const schluessel = `${id}:${index}`;
  store.bilder.set(schluessel, base64);
  while (store.bilder.size > MAX_BILDER_SPEICHER) {
    const aeltester = store.bilder.keys().next();
    if (aeltester.done) break;
    store.bilder.delete(aeltester.value);
  }
}

export async function addEreignis(
  e: Omit<StallEreignis, "id" | "zeit" | "bilder" | "quittiert"> & {
    zeit?: string;
    /** Base64-JPEGs ohne data:-Praefix, neueste Aufnahme zuerst. */
    bilder?: string[];
  },
): Promise<StallEreignis> {
  const { bilder: rohBilder, ...rest } = e;
  const gueltige = (rohBilder ?? [])
    .filter((b) => typeof b === "string" && b.length > 0 && b.length <= MAX_BILD_BASE64)
    .slice(0, MAX_BILDER);

  const voll: StallEreignis = {
    ...rest,
    id: crypto.randomUUID(),
    zeit: e.zeit ?? new Date().toISOString(),
    bilder: gueltige.length,
    quittiert: null,
  };
  const jetzt = new Date().toISOString();

  // Immer auch in den Instanz-Puffer (Fallback + sofortige Lesbarkeit).
  store.ereignisse.unshift(voll);
  if (store.ereignisse.length > MAX_EREIGNISSE) {
    store.ereignisse.length = MAX_EREIGNISSE;
  }
  store.letzterKontakt = jetzt;
  gueltige.forEach((b, i) => merkeBild(voll.id, i, b));

  await kvPipeline([
    ["LPUSH", KV_LISTE, JSON.stringify(voll)],
    ["LTRIM", KV_LISTE, 0, MAX_EREIGNISSE - 1],
    ["SET", KV_KONTAKT, jetzt],
    ...gueltige.map((b, i) => [
      "SET",
      kvBildSchluessel(voll.id, i),
      b,
      "EX",
      BILD_TTL,
    ]),
  ]);
  return voll;
}

/** Meldet den Edge-Agenten als lebendig, ohne ein Ereignis zu erzeugen. */
export async function meldeKontakt(): Promise<void> {
  const jetzt = new Date().toISOString();
  store.letzterKontakt = jetzt;
  await kvPipeline([["SET", KV_KONTAKT, jetzt]]);
}

export interface EreignisAntwort {
  ereignisse: StallEreignis[];
  letzterKontakt: string | null;
  quelle: "edge-agent" | "demo";
}

export async function getEreignisse(): Promise<EreignisAntwort> {
  const kv = await kvPipeline([
    ["LRANGE", KV_LISTE, 0, MAX_EREIGNISSE - 1],
    ["GET", KV_KONTAKT],
  ]);
  if (kv) {
    const roh = Array.isArray(kv[0]?.result) ? (kv[0].result as string[]) : [];
    const ereignisse: StallEreignis[] = [];
    for (const s of roh) {
      try {
        ereignisse.push(normalisiere(JSON.parse(s) as StallEreignis));
      } catch {
        // korrupten Einzeleintrag ueberspringen statt Liste zu verwerfen
      }
    }
    if (ereignisse.length > 0) {
      return {
        ereignisse,
        letzterKontakt:
          typeof kv[1]?.result === "string" ? kv[1].result : null,
        quelle: "edge-agent",
      };
    }
  }

  if (store.ereignisse.length > 0) {
    return {
      ereignisse: store.ereignisse,
      letzterKontakt: store.letzterKontakt,
      quelle: "edge-agent",
    };
  }
  return { ereignisse: demoEreignisse(), letzterKontakt: null, quelle: "demo" };
}

/** Ergaenzt Felder, die aeltere (vor dem Bild-Update geschriebene) Eintraege nicht haben. */
function normalisiere(e: StallEreignis): StallEreignis {
  return {
    ...e,
    bilder: typeof e.bilder === "number" ? e.bilder : 0,
    quittiert: typeof e.quittiert === "string" ? e.quittiert : null,
  };
}

export interface EreignisFilter {
  /** Nur diese Typen zurueckgeben (leer/undefiniert = alle). */
  typen?: readonly EreignisTyp[];
  /** Nur Ereignisse der letzten N Stunden (Default im Aktivitaetsprotokoll: 24). */
  stunden?: number;
  /** Nur Ereignisse dieser Kuh. */
  kuhId?: string;
  /** Maximale Anzahl. */
  limit?: number;
}

/** Gefilterte Sicht auf die Ereignisliste — Grundlage des Aktivitaetsprotokolls. */
export async function getGefilterteEreignisse(
  filter: EreignisFilter,
): Promise<EreignisAntwort> {
  const alle = await getEreignisse();
  const grenze =
    filter.stunden && filter.stunden > 0
      ? Date.now() - filter.stunden * 3600_000
      : null;
  const kuh = filter.kuhId?.toLowerCase();

  let ereignisse = alle.ereignisse.filter((e) => {
    if (filter.typen?.length && !filter.typen.includes(e.typ)) return false;
    if (grenze !== null) {
      const t = Date.parse(e.zeit);
      // Unparsbare Zeit lieber behalten als still verschlucken.
      if (!Number.isNaN(t) && t < grenze) return false;
    }
    if (kuh && !(e.kuhId ?? "").toLowerCase().includes(kuh)) return false;
    return true;
  });
  if (filter.limit && filter.limit > 0) {
    ereignisse = ereignisse.slice(0, filter.limit);
  }
  return { ...alle, ereignisse };
}

/** Einzelnes Ereignis (fuer Detailansicht und Push-Deeplink). */
export async function getEreignis(id: string): Promise<StallEreignis | null> {
  const { ereignisse } = await getEreignisse();
  return ereignisse.find((e) => e.id === id) ?? null;
}

/**
 * Holt ein Alarmbild als Rohbytes.
 * Reihenfolge: KV (dauerhaft) -> Instanz-Puffer -> null.
 */
export async function getBild(
  id: string,
  index: number,
): Promise<Uint8Array | null> {
  let base64 = store.bilder.get(`${id}:${index}`) ?? null;
  if (!base64) {
    const kv = await kvPipeline([["GET", kvBildSchluessel(id, index)]]);
    const wert = kv?.[0]?.result;
    if (typeof wert === "string" && wert.length > 0) base64 = wert;
  }
  if (!base64) return null;
  try {
    return Uint8Array.from(Buffer.from(base64, "base64"));
  } catch {
    return null;
  }
}

/**
 * Quittiert einen Alarm ("gesehen"). Schreibt die ganze Liste zurueck, weil
 * Upstash kein In-Place-Update einzelner Listenelemente ueber die REST-API
 * anbietet; bei maximal 200 Eintraegen ist das unkritisch.
 */
export async function quittiereEreignis(
  id: string,
): Promise<StallEreignis | null> {
  const zeit = new Date().toISOString();
  let treffer: StallEreignis | null = null;

  const imPuffer = store.ereignisse.find((e) => e.id === id);
  if (imPuffer) {
    imPuffer.quittiert = zeit;
    treffer = imPuffer;
  }

  const kv = await kvPipeline([["LRANGE", KV_LISTE, 0, MAX_EREIGNISSE - 1]]);
  const roh = Array.isArray(kv?.[0]?.result) ? (kv[0].result as string[]) : [];
  if (roh.length > 0) {
    let gefunden = false;
    const neu = roh.map((s) => {
      try {
        const e = normalisiere(JSON.parse(s) as StallEreignis);
        if (e.id !== id) return s;
        gefunden = true;
        treffer = { ...e, quittiert: zeit };
        return JSON.stringify(treffer);
      } catch {
        return s;
      }
    });
    if (gefunden) {
      // Neu aufbauen statt einzeln patchen: DEL + ein RPUSH erhaelt die
      // Reihenfolge. Als Transaktion, damit ein zeitgleich eintreffender
      // Alarm nicht zwischen den beiden Befehlen verschwindet.
      await kvTransaktion([
        ["DEL", KV_LISTE],
        ["RPUSH", KV_LISTE, ...neu],
      ]);
    }
  }
  return treffer;
}

/** Plausible Beispieldaten, bis der Edge-Agent echte Ereignisse liefert. */
function demoEreignisse(): StallEreignis[] {
  const min = 60_000;
  const t = (vorMin: number) => new Date(Date.now() - vorMin * min).toISOString();
  const basis = { bilder: 0, quittiert: null };
  return [
    {
      ...basis,
      id: "demo-1",
      typ: "kalbeverdacht",
      kuhId: "Kuh #42",
      kamera: "stallwache",
      nachricht:
        "Schwanzwinkel > 45° in 26 % der Frames der letzten 30 Minuten",
      konfidenz: null,
      zeit: t(12),
    },
    {
      ...basis,
      id: "demo-2",
      typ: "brunstverdacht",
      kuhId: "Kuh #17",
      kamera: "futterwache",
      nachricht: "Aufsprungverhalten erkannt (Dauer 6 s)",
      konfidenz: 0.71,
      zeit: t(95),
    },
    {
      ...basis,
      id: "demo-3",
      typ: "info",
      kuhId: null,
      kamera: "stallwache",
      nachricht: "Edge-Agent gestartet (Silent Mode – Datensammlung)",
      konfidenz: null,
      zeit: t(240),
    },
  ];
}
