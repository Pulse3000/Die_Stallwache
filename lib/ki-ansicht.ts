/**
 * Zustand der KI-Ansicht an der Stallwache-Kachel
 * (docs/ki-ansicht-spezifikation.md §5).
 *
 * Die Kachel holt je Sekunde (bei Datensparen alle 5 s) das letzte
 * Analysebild des Edge-Agenten ueber den Fernzugriff. Ob das Bild aktuell
 * ist, entscheidet die Kachel daran, ob sich die Bildzeit (X-Bild-Zeit)
 * weiterbewegt – gemessen mit der Uhr des Handys. So stoert eine falsch
 * gehende Uhr am Stall-Rechner nicht, und ein haengengebliebenes Bild wird
 * nie als aktuell gezeigt. Der Proxy am Stall prueft zusaetzlich selbst.
 *
 * Reine Funktionen ohne Framework-Importe, damit `npm test` sie ohne Build
 * pruefen kann.
 */

/** Pfad in dieser App (lib/fern.ts: FERN_PRAEFIX + KI_ANSICHT_PFAD). */
export const KI_ANSICHT_URL = "/api/stallwache/fern/ki-ansicht.jpg";

/** Bildzeit steht laenger still -> „nicht aktuell". */
export const KI_FRISCH_MS = 10_000;

/** Abruftakt: wie die Analyse, bei Datensparen sparsamer. */
export function kiTaktMs(datensparen: boolean): number {
  return datensparen ? 5_000 : 1_000;
}

export type KiZustand = "laedt" | "bild" | "alt" | "aus" | "anmelden" | "gestoert";

export interface KiStand {
  zustand: KiZustand;
  /** Unix-Sekunden des zuletzt gezeigten Bilds (vom Stall-Rechner). */
  bildZeit: number | null;
  /** Handy-Zeit (ms), zu der sich die Bildzeit zuletzt bewegt hat. */
  seit: number | null;
}

export const KI_START: KiStand = { zustand: "laedt", bildZeit: null, seit: null };

/**
 * Naechster Zustand nach einem Abruf. `status` null = Netzfehler.
 * 404 heisst am Stall „kein aktuelles Bild": Gab es schon eines, ist es
 * jetzt „nicht aktuell", sonst analysiert der Agent nicht.
 */
export function naechsterKiStand(
  alt: KiStand,
  status: number | null,
  bildZeit: number | null,
  jetzt: number,
): KiStand {
  if (status === 200 && bildZeit !== null) {
    const seit = bildZeit !== alt.bildZeit || alt.seit === null ? jetzt : alt.seit;
    return { zustand: jetzt - seit > KI_FRISCH_MS ? "alt" : "bild", bildZeit, seit };
  }
  if (status === 404) return { ...alt, zustand: alt.bildZeit === null ? "aus" : "alt" };
  if (status === 401) return { ...alt, zustand: "anmelden" };
  return { ...alt, zustand: "gestoert" };
}

/** Text der Fusszeile; `uhr` formatiert Unix-Sekunden als Uhrzeit. */
export function kiText(stand: KiStand, uhr: (sekunden: number) => string): string {
  const zeit = stand.bildZeit !== null ? uhr(stand.bildZeit) : null;
  switch (stand.zustand) {
    case "laedt":
      return "KI-Ansicht lädt …";
    case "bild":
      return `KI-Ansicht · Stand ${zeit ?? "–"} · Nummern vom Tracker, keine Ohrmarken`;
    case "alt":
      return `KI-Ansicht nicht aktuell – letztes Bild von ${zeit ?? "–"}.`;
    case "aus":
      return "Keine KI-Ansicht – der Edge-Agent analysiert gerade nicht (Silent Mode ohne Modell oder Agent aus).";
    case "anmelden":
      return "KI-Ansicht nicht erreichbar – bitte neu anmelden.";
    case "gestoert":
      return "KI-Ansicht nicht erreichbar – Fernzugriff zum Stall gestört.";
  }
}

/** Bildzeit aus dem Kopf X-Bild-Zeit; nur Ganzzahlen. */
export function leseBildZeit(wert: string | null): number | null {
  return wert && /^\d{1,12}$/.test(wert) ? Number(wert) : null;
}
