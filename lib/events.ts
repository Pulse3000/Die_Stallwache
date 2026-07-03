/**
 * Ereignis-Modell der KI-Wache (Brunst- & Kalbeerkennung).
 *
 * Die Bildanalyse laeuft NICHT auf Vercel, sondern lokal im Stall auf dem
 * Edge-Agenten (siehe /edge-agent). Der Agent meldet erkannte Ereignisse per
 * POST /api/events an dieses Dashboard. Solange noch kein Agent sendet,
 * liefert der Store gekennzeichnete Demo-Daten, damit UI und API end-to-end
 * funktionieren.
 *
 * Hinweis Persistenz: Der Store ist bewusst ein In-Memory-Ringpuffer pro
 * Serverless-Instanz (MVP). Fuer dauerhafte Historie spaeter Vercel KV /
 * Postgres anbinden – das API-Format bleibt gleich.
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

export function addEreignis(
  e: Omit<StallEreignis, "id" | "zeit"> & { zeit?: string },
): StallEreignis {
  const voll: StallEreignis = {
    ...e,
    id: crypto.randomUUID(),
    zeit: e.zeit ?? new Date().toISOString(),
  };
  store.ereignisse.unshift(voll);
  if (store.ereignisse.length > MAX_EREIGNISSE) {
    store.ereignisse.length = MAX_EREIGNISSE;
  }
  store.letzterKontakt = new Date().toISOString();
  return voll;
}

export function getEreignisse(): {
  ereignisse: StallEreignis[];
  letzterKontakt: string | null;
  quelle: "edge-agent" | "demo";
} {
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
