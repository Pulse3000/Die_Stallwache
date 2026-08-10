"use client";

/**
 * Nutzereinstellungen der PWA — bewusst nur lokal im Geraet (localStorage).
 *
 * Der Schwerpunkt liegt auf Datenverbrauch und Akku: Ein Livebild kostet im
 * Mobilfunk ein Vielfaches einer Ereignisliste, und der Landwirt hat das Handy
 * den ganzen Tag im Stall dabei. Deshalb ist „Datensparen" der Default —
 * Video laeuft erst, wenn er es ausdruecklich startet.
 */

import { useCallback, useSyncExternalStore } from "react";
import { ALARM_TYPEN, type EreignisTyp } from "@/lib/ereignis-modell";
import { CAMERAS, type CameraId } from "@/lib/config";

export interface Einstellungen {
  /** Livebild erst auf Tippen starten statt beim Oeffnen der App. */
  datensparen: boolean;
  /** Alarmbilder erst laden, wenn der Alarm geoeffnet wird. */
  bilderNurAufTippen: boolean;
  /** Welche Kamera das Dashboard gross zeigt. */
  startKamera: CameraId;
  /** Fuer welche Alarmarten dieses Geraet Push bekommt (leer = alle). */
  pushTypen: EreignisTyp[];
  /** Abrufintervall der Ereignisliste in Sekunden. */
  abrufSekunden: number;
}

export const STANDARD: Einstellungen = {
  datensparen: true,
  bilderNurAufTippen: true,
  startKamera: "stallwache",
  pushTypen: [...ALARM_TYPEN],
  abrufSekunden: 20,
};

const SCHLUESSEL = "stallwache:einstellungen";

/** Liest die Einstellungen; unbekannte/kaputte Werte fallen auf STANDARD zurueck. */
export function ladeEinstellungen(): Einstellungen {
  if (typeof localStorage === "undefined") return STANDARD;
  try {
    const roh = localStorage.getItem(SCHLUESSEL);
    if (!roh) return STANDARD;
    const g = JSON.parse(roh) as Partial<Einstellungen>;
    return {
      datensparen: typeof g.datensparen === "boolean" ? g.datensparen : STANDARD.datensparen,
      bilderNurAufTippen:
        typeof g.bilderNurAufTippen === "boolean"
          ? g.bilderNurAufTippen
          : STANDARD.bilderNurAufTippen,
      startKamera: CAMERAS.some((c) => c.id === g.startKamera)
        ? (g.startKamera as CameraId)
        : STANDARD.startKamera,
      pushTypen: Array.isArray(g.pushTypen)
        ? g.pushTypen.filter((t): t is EreignisTyp =>
            (ALARM_TYPEN as readonly string[]).includes(t),
          )
        : STANDARD.pushTypen,
      abrufSekunden:
        typeof g.abrufSekunden === "number" && g.abrufSekunden >= 10 && g.abrufSekunden <= 300
          ? g.abrufSekunden
          : STANDARD.abrufSekunden,
    };
  } catch {
    return STANDARD;
  }
}

/** Ereignisname, mit dem sich mehrere Komponenten im selben Tab synchron halten. */
const GEAENDERT = "stallwache:einstellungen-geaendert";

export function speichereEinstellungen(e: Einstellungen): void {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(SCHLUESSEL, JSON.stringify(e));
  window.dispatchEvent(new CustomEvent(GEAENDERT));
}

// ---------------------------------------------------------------------------
// Anbindung an React ueber useSyncExternalStore.
//
// localStorage ist ein externer Speicher, kein React-State — genau der Fall,
// fuer den useSyncExternalStore gemacht ist. Wichtig ist, dass der
// Schnappschuss referenzstabil bleibt: React vergleicht ihn per Identitaet und
// wuerde bei jedem Aufruf eines frisch geparsten Objekts endlos neu rendern.
// Deshalb wird das geparste Objekt gecacht und nur neu gebaut, wenn sich der
// Rohtext im Speicher geaendert hat.
// ---------------------------------------------------------------------------

let cacheRoh: string | null = null;
let cacheWert: Einstellungen = STANDARD;

function schnappschuss(): Einstellungen {
  const roh = typeof localStorage === "undefined" ? null : localStorage.getItem(SCHLUESSEL);
  if (roh !== cacheRoh) {
    cacheRoh = roh;
    cacheWert = ladeEinstellungen();
  }
  return cacheWert;
}

/** Server kennt den Geraetespeicher nicht – dort gelten die Vorgaben. */
function serverSchnappschuss(): Einstellungen {
  return STANDARD;
}

function abonniere(melden: () => void): () => void {
  window.addEventListener(GEAENDERT, melden);
  window.addEventListener("storage", melden); // anderes Tab
  return () => {
    window.removeEventListener(GEAENDERT, melden);
    window.removeEventListener("storage", melden);
  };
}

/** Einstellungen als React-State, inklusive Aenderungsfunktion. */
export function useEinstellungen(): [Einstellungen, (aenderung: Partial<Einstellungen>) => void] {
  const werte = useSyncExternalStore(abonniere, schnappschuss, serverSchnappschuss);

  const aendern = useCallback((aenderung: Partial<Einstellungen>) => {
    // Aus dem Speicher lesen statt aus `werte`: so gewinnt nicht ein
    // veralteter Render-Schnappschuss, wenn zwei Schalter schnell nacheinander
    // umgelegt werden.
    speichereEinstellungen({ ...schnappschuss(), ...aenderung });
  }, []);

  return [werte, aendern];
}
