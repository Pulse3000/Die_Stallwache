/**
 * Kachel-Status ohne Bridge: Kopfzeile und Status-Ping der Vorschau.
 *
 * Spezifikation mit Regeln, Grenzen und Abnahmekriterien:
 * docs/vorschau-status-spezifikation.md.
 *
 * Zwei Grundsaetze, die man dem Code nicht ansieht:
 *
 *   - **„Online" nur mit aktuellem Bildbeweis** (playing-Ereignis, geladenes
 *     Einzelbild). Eine Vorschau ohne Bridge hat kein Einzelbild und ist
 *     deshalb „ungeprueft" – nie „online", und auch nicht „laedt".
 *   - **Rot nur bei echtem Ausfall.** Laden, Ungeprueft und Pausiert faerben
 *     den System-Punkt nie rot.
 *
 * Rein funktional (kein React, kein DOM), damit direkt testbar:
 * tests/kamera-status.test.ts. Die Tailwind-Klassen bleiben in den
 * Komponenten (tailwind.config.ts scannt lib/ nicht).
 */

import type { CameraState } from "@/lib/config";

/** Anzeige-Zustand einer Kachel: Kamerazustand plus „pausiert" (nicht im Bild). */
export type Anzeige = CameraState | "pausiert";

/** Farbe des System-Punkts: gruen, gelb, rot, grau. */
export type KopfTon = "ok" | "hinweis" | "stoerung" | "neutral";

export interface KopfStatus {
  text: string;
  ton: KopfTon;
}

/**
 * Kopfzeile aus den Anzeige-Zustaenden aller Kacheln – dieselben Zustaende,
 * die die Statuszeilen zeigen. Gezaehlt (Beweis oder Versuch mit Ergebnis)
 * sind online, offline und instabil; „laedt", „ungeprueft" und „pausiert"
 * stehen als eigene Teile daneben.
 */
export function kopfStatus(anzeigen: readonly Anzeige[]): KopfStatus {
  const anzahl = (z: Anzeige) => anzeigen.filter((a) => a === z).length;
  const online = anzahl("online");
  const offline = anzahl("offline");
  const instabil = anzahl("instabil");
  const laedt = anzahl("laedt");
  const ungeprueft = anzahl("ungeprueft");
  const pausiert = anzahl("pausiert");
  const gezaehlt = online + offline + instabil;

  const ton: KopfTon =
    offline > 0 && online === 0
      ? "stoerung"
      : offline + instabil + laedt > 0
        ? "hinweis"
        : online > 0
          ? "ok"
          : "neutral";

  if (anzeigen.length > 0 && online === anzeigen.length) {
    return { text: `${online} ${online === 1 ? "Kamera" : "Kameras"} online`, ton };
  }
  if (anzeigen.length > 0 && pausiert === anzeigen.length) {
    return { text: "Livebilder pausiert", ton };
  }

  const zusatz: string[] = [];
  // Begriffe = Kachel-Labels (kurz: der Kopf hat am 360-px-Handy ~187 px).
  if (laedt > 0) zusatz.push(`${laedt} ${laedt === 1 ? "lädt" : "laden"}`);
  if (ungeprueft > 0) zusatz.push(`${ungeprueft} ungeprüft`);
  if (pausiert > 0) zusatz.push(`${pausiert} pausiert`);

  if (gezaehlt === 0) {
    return { text: zusatz.length > 0 ? zusatz.join(" · ") : "Keine Kameras", ton };
  }
  const anteil = online === gezaehlt ? `${online}` : `${online} von ${gezaehlt}`;
  if (zusatz.length === 0) {
    return { text: `${anteil} ${gezaehlt === 1 ? "Kamera" : "Kameras"} online`, ton };
  }
  return { text: [`${anteil} online`, ...zusatz].join(" · "), ton };
}

// ---- Status-Ping der Vorschau ohne Bridge (docs/vorschau-status-spezifikation.md §3) ----

/** Fruehester Ping nach dem Eintritt in die Vorschau – das Hauptbild verbindet sich zuerst. */
export const PING_START_MS = 3_000;
/** Takt nach erfolgreichem Ping oder nach einem Livebild. */
export const PING_OK_MS = 5 * 60_000;
/** Nach dem ersten Fehlschlag: Bestaetigung, ein einzelner Fehlschlag faerbt nichts rot. */
export const PING_BESTAETIGUNG_MS = 60_000;
/** Takt, solange die Kachel offline ist. */
export const PING_OFFLINE_MS = 2 * 60_000;
/** Fehlschlaege in Folge bis „offline". */
export const PING_FEHLSCHLAEGE_OFFLINE = 2;

export interface PingErgebnis {
  /** Fehlschlaege in Folge nach diesem Ping. */
  fehlschlaege: number;
  /** Neuer Zustand der Kachel; `null` = unveraendert lassen. */
  zustand: "ungeprueft" | "offline" | null;
  /** Abstand bis zum naechsten Ping. */
  warteMs: number;
}

/**
 * Bewertet einen Status-Ping. Ein erfolgreicher Ping ist kein Bildbeweis
 * (Tuya teilt nur eine URL zu) und fuehrt deshalb nie zu „online"; ein
 * bestaetigter Fehlschlag ist dagegen ein Beleg fuer eine Stoerung.
 */
export function bewertePing(fehlschlaegeBisher: number, ok: boolean): PingErgebnis {
  if (ok) return { fehlschlaege: 0, zustand: "ungeprueft", warteMs: PING_OK_MS };
  const fehlschlaege = fehlschlaegeBisher + 1;
  return fehlschlaege >= PING_FEHLSCHLAEGE_OFFLINE
    ? { fehlschlaege, zustand: "offline", warteMs: PING_OFFLINE_MS }
    : { fehlschlaege, zustand: null, warteMs: PING_BESTAETIGUNG_MS };
}

/**
 * Wartezeit bis zum ersten Ping nach dem Eintritt in die Vorschau. Die
 * Faelligkeit ist absolut: Rollenwechsel, Pause und Rueckkehr setzen sie
 * nicht zurueck – hoechstens ein Ping pro Intervall und Kachel.
 */
export function wartezeitBisPing(faelligAb: number, jetzt: number): number {
  return Math.max(PING_START_MS, faelligAb - jetzt);
}

/**
 * Soll die Ereignisliste einen Statuswechsel melden? Nur wenn sich der
 * belegte Zustand zwischen online und offline aendert; Zwischenzustaende
 * (ungeprueft, laedt, instabil) erzeugen keinen Eintrag und setzen nichts
 * zurueck – ein Rollenwechsel wiederholt also nicht „X ist online".
 */
export function belegterWechsel(
  zuletztGemeldet: "online" | "offline" | undefined,
  neu: CameraState,
): neu is "online" | "offline" {
  return (neu === "online" || neu === "offline") && neu !== zuletztGemeldet;
}
