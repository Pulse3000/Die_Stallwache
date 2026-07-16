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
 */

export type EreignisTyp =
  | "kalbeverdacht" // Schwanzwinkel-Statistik ueber Schwelle (Zeit-Filter)
  | "austreibung" // Fruchtblase/Kaelberfuesse erkannt -> Sofort-Alarm
  | "brunstverdacht" // Aufsprung/Duldung erkannt
  | "info"; // Statusmeldungen des Agenten (Start, Silent Mode, ...)

export interface StallEreignis {
  id: string;
  typ: EreignisTyp;
  /** Tracking-ID der Kuh (z.B. "Kuh #42"), null bei Systemmeldungen. */
  kuhId: string | null;
  /** Quellkamera: stallwache | futterwache */
  kamera: string;
  nachricht: string;
  /** Modell-Konfidenz 0..1, null bei regelbasierten/System-Ereignissen. */
  konfidenz: number | null;
  /** ISO-8601-Zeitstempel (vom Agenten geliefert oder Eingangszeit). */
  zeit: string;
}

export const EREIGNIS_TYPEN: readonly EreignisTyp[] = [
  "kalbeverdacht",
  "austreibung",
  "brunstverdacht",
  "info",
];

const MAX_EREIGNISSE = 200;

interface EventStore {
  ereignisse: StallEreignis[];
  letzterKontakt: string | null;
}

// globalThis, damit der Puffer Hot-Reloads/Re-Imports derselben Instanz uebersteht.
const store: EventStore = ((globalThis as Record<string, unknown>).__kiwache ??= {
  ereignisse: [],
  letzterKontakt: null,
}) as EventStore;

// ---------------------------------------------------------------------------
// Vercel KV / Upstash Redis ueber die REST-API (bewusst ohne Zusatzpaket).
// Aktiviert sich selbst, sobald der Betreiber einen KV-Store verknuepft.
// ---------------------------------------------------------------------------

const KV_URL = process.env.KV_REST_API_URL?.trim() || "";
const KV_TOKEN = process.env.KV_REST_API_TOKEN?.trim() || "";
const kvAktiv = Boolean(KV_URL && KV_TOKEN);
const KV_LISTE = "kiwache:ereignisse";
const KV_KONTAKT = "kiwache:kontakt";

/** Fuehrt eine Upstash-Pipeline aus; null bei inaktivem/fehlerhaftem KV. */
async function kvPipeline(
  befehle: (string | number)[][],
): Promise<{ result: unknown }[] | null> {
  if (!kvAktiv) return null;
  try {
    const res = await fetch(`${KV_URL}/pipeline`, {
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

export async function addEreignis(
  e: Omit<StallEreignis, "id" | "zeit"> & { zeit?: string },
): Promise<StallEreignis> {
  const voll: StallEreignis = {
    ...e,
    id: crypto.randomUUID(),
    zeit: e.zeit ?? new Date().toISOString(),
  };
  const jetzt = new Date().toISOString();

  // Immer auch in den Instanz-Puffer (Fallback + sofortige Lesbarkeit).
  store.ereignisse.unshift(voll);
  if (store.ereignisse.length > MAX_EREIGNISSE) {
    store.ereignisse.length = MAX_EREIGNISSE;
  }
  store.letzterKontakt = jetzt;

  await kvPipeline([
    ["LPUSH", KV_LISTE, JSON.stringify(voll)],
    ["LTRIM", KV_LISTE, 0, MAX_EREIGNISSE - 1],
    ["SET", KV_KONTAKT, jetzt],
  ]);
  return voll;
}

export async function getEreignisse(): Promise<{
  ereignisse: StallEreignis[];
  letzterKontakt: string | null;
  quelle: "edge-agent" | "demo";
}> {
  const kv = await kvPipeline([
    ["LRANGE", KV_LISTE, 0, MAX_EREIGNISSE - 1],
    ["GET", KV_KONTAKT],
  ]);
  if (kv) {
    const roh = Array.isArray(kv[0]?.result) ? (kv[0].result as string[]) : [];
    const ereignisse: StallEreignis[] = [];
    for (const s of roh) {
      try {
        ereignisse.push(JSON.parse(s) as StallEreignis);
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

/** Plausible Beispieldaten, bis der Edge-Agent echte Ereignisse liefert. */
function demoEreignisse(): StallEreignis[] {
  const min = 60_000;
  const t = (vorMin: number) => new Date(Date.now() - vorMin * min).toISOString();
  return [
    {
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
      id: "demo-2",
      typ: "brunstverdacht",
      kuhId: "Kuh #17",
      kamera: "futterwache",
      nachricht: "Aufsprungverhalten erkannt (Dauer 6 s)",
      konfidenz: 0.71,
      zeit: t(95),
    },
    {
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
