/**
 * Das Ereignis-Modell der KI-Wache — reine Typen und Konstanten.
 *
 * Bewusst getrennt von `lib/events.ts`: Der Speicher dort spricht mit KV,
 * liest `process.env` und nutzt `Buffer`. Weil er beim Import Nebenwirkungen
 * hat (Instanz-Puffer an `globalThis`), laesst er sich nicht wegoptimieren —
 * eine Client-Komponente, die nur `ALARM_TYPEN` braucht, wuerde sonst den
 * ganzen Serverspeicher ins Browser-Bundle ziehen.
 *
 * Alles hier ist frei von Nebenwirkungen und darf von beiden Seiten importiert
 * werden. `lib/events.ts` reicht die Namen weiter, damit bestehende Importe
 * unveraendert funktionieren.
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
  /** Quellkamera: stallwache | futterwache | abkalbebox | weidewache */
  kamera: string;
  nachricht: string;
  /** Modell-Konfidenz 0..1, null bei regelbasierten/System-Ereignissen. */
  konfidenz: number | null;
  /** ISO-8601-Zeitstempel (vom Agenten geliefert oder Eingangszeit). */
  zeit: string;
  /**
   * Anzahl mitgelieferter Alarmbilder (Bildserie fuer das Replay).
   * Abruf einzeln ueber /api/events/<id>/bild/<index>.
   */
  bilder: number;
  /** Vom Landwirt quittiert (ISO-Zeitstempel) oder null. */
  quittiert: string | null;
}

export const EREIGNIS_TYPEN: readonly EreignisTyp[] = [
  "kalbeverdacht",
  "austreibung",
  "brunstverdacht",
  "info",
];

/** Alarmtypen = alles ausser Systemmeldungen (Grundlage der Push-Regeln). */
export const ALARM_TYPEN: readonly EreignisTyp[] = [
  "kalbeverdacht",
  "austreibung",
  "brunstverdacht",
];

/**
 * Zaehler fuer den roten Punkt an „Alarme": unquittierte Alarme aus der
 * Antwort von GET /api/events. Gezaehlt wird nur, was der Edge-Agent
 * tatsaechlich gemeldet hat — Beispieldaten („demo") ergeben 0. Der Punkt
 * steht auf jeder Seite ohne den Hinweis „Beispieldaten" und behauptet sonst
 * offene Alarme, die es nicht gibt.
 */
export function zaehleOffeneAlarme(antwort: {
  ereignisse: readonly Pick<StallEreignis, "quittiert">[];
  quelle?: string;
}): number {
  if (antwort.quelle !== "edge-agent") return 0;
  return antwort.ereignisse.filter((e) => !e.quittiert).length;
}

/**
 * Kuerzt eine Ereignisliste (neueste zuerst) auf `max` Eintraege und opfert
 * dabei zuerst die aeltesten Systemmeldungen (`info`). Ein Alarm faellt erst
 * heraus, wenn die Liste nur noch aus Alarmen besteht. Grund: Ein flackernder
 * Stream erzeugt viele Meldungen; draengten sie einen Alarm aus der Liste,
 * saehe die Statusabfrage `OK` statt `WARNUNG`/`KRITISCH`
 * (docs/statusabfrage-spezifikation.md §9.8).
 */
export function kuerzeEreignisse<T extends { typ: EreignisTyp }>(
  liste: T[],
  max: number,
): T[] {
  if (liste.length <= max) return liste;
  const aus = liste.slice();
  for (let i = aus.length - 1; i >= 0 && aus.length > max; i--) {
    if (aus[i].typ === "info") aus.splice(i, 1);
  }
  if (aus.length > max) aus.length = max;
  return aus;
}

/**
 * Fuehrt getrennt gespeicherte Alarme und Systemmeldungen zu einer Liste
 * zusammen: neueste zuerst, jede ID nur einmal. Eintraege ohne lesbare Zeit
 * stehen vorn (lieber sichtbar als verschluckt).
 */
export function fuehreEreignisseZusammen<T extends { id: string; zeit: string }>(
  ...listen: T[][]
): T[] {
  const gesehen = new Set<string>();
  const alle: T[] = [];
  for (const liste of listen) {
    for (const e of liste) {
      if (gesehen.has(e.id)) continue;
      gesehen.add(e.id);
      alle.push(e);
    }
  }
  const t = (e: T) => {
    const z = Date.parse(e.zeit);
    return Number.isNaN(z) ? Number.POSITIVE_INFINITY : z;
  };
  // Array.prototype.sort ist stabil: gleiche Zeit behaelt die Eingangsfolge.
  return alle.sort((a, b) => t(b) - t(a));
}
