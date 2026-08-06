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
  /** Quellkamera: stallwache | futterwache | stallbox */
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
