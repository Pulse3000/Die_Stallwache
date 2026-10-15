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

/** Geschuetztes Leerzeichen (U+00A0). */
const NBSP = "\u00a0";

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

  // Begriffe = Kachel-Labels (kurz: der Kopf hat am 360-px-Handy ~187 px).
  // Zahl und Wort mit geschuetztem Leerzeichen: bricht der Kopf um, steht
  // nie „· 1" am Zeilenende und „pausiert" allein darunter.
  const zusatz: string[] = [];
  if (laedt > 0) zusatz.push(`${laedt}${NBSP}${laedt === 1 ? "lädt" : "laden"}`);
  if (ungeprueft > 0) zusatz.push(`${ungeprueft}${NBSP}ungeprüft`);
  if (pausiert > 0) zusatz.push(`${pausiert}${NBSP}pausiert`);

  if (gezaehlt === 0) {
    return { text: zusatz.length > 0 ? zusatz.join(" · ") : "Keine Kameras", ton };
  }
  const anteil = online === gezaehlt ? `${online}` : `${online}${NBSP}von${NBSP}${gezaehlt}`;
  if (zusatz.length === 0) {
    return { text: `${anteil} ${gezaehlt === 1 ? "Kamera" : "Kameras"} online`, ton };
  }
  return { text: [`${anteil}${NBSP}online`, ...zusatz].join(" · "), ton };
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

/** Frist je Ping; eine haengende Anfrage haelt den Takt nicht an. */
export const PING_TIMEOUT_MS = 20_000;
/**
 * Zwei Fehlschlaege gelten nur „in Folge", wenn hoechstens so viel Zeit
 * dazwischen liegt (Offline-Takt plus Frist). Ein alter Fehlschlag vor einer
 * Pause von Stunden macht den naechsten nicht zum zweiten.
 */
export const PING_FOLGE_MAX_MS = 3 * 60_000;

/**
 * Was eine Ping-Antwort belegt:
 *   ok       – 2xx: Quelle erreichbar (kein Bildbeweis).
 *   stoerung – HTTP >= 500: Server erreicht, Quelle gestoert (Tuya, Funnel,
 *              nicht konfiguriert).
 *   unklar   – kein Netz, Frist abgelaufen oder ein anderer Status (z. B.
 *              401, Login abgelaufen): sagt nichts ueber die Kamera.
 */
export type PingAntwort = "ok" | "stoerung" | "unklar";

/** Ordnet einen HTTP-Status ein; `null` = Netzfehler oder Frist abgelaufen. */
export function pingAntwort(status: number | null): PingAntwort {
  if (status === null) return "unklar";
  if (status >= 200 && status < 300) return "ok";
  return status >= 500 ? "stoerung" : "unklar";
}

/**
 * Ping-Stand einer Kamera. Er gehoert der Kamera, nicht der Kachel-Instanz:
 * Er ueberdauert Rollenwechsel, Pause und Navigation (Remount) – sonst ginge
 * ein belegtes „offline" beim Tabwechsel verloren, und jede Rueckkehr loeste
 * einen neuen Ping aus.
 */
export interface PingStand {
  /** Stoerungen in Folge. */
  fehlschlaege: number;
  /** Zeitpunkt der letzten Stoerung (ms), 0 = keine. */
  letzterFehlschlag: number;
  /** Ab wann der naechste Ping faellig ist (ms, absolut). */
  faellig: number;
  /** Letzter Beleg war „offline" (Ping oder Live-Versuch). */
  belegtOffline: boolean;
}

export const LEERER_PING_STAND: PingStand = {
  fehlschlaege: 0,
  letzterFehlschlag: 0,
  faellig: 0,
  belegtOffline: false,
};

export interface PingErgebnis {
  stand: PingStand;
  /** Neuer Zustand der Kachel; `null` = unveraendert lassen. */
  zustand: "ungeprueft" | "offline" | null;
  /** Abstand bis zum naechsten Ping. */
  warteMs: number;
}

/**
 * Bewertet einen Status-Ping. Ein erfolgreicher Ping ist kein Bildbeweis
 * (Tuya teilt nur eine URL zu) und fuehrt deshalb nie zu „online"; zwei
 * Stoerungen in Folge sind ein Beleg fuer einen Ausfall. Eine unklare
 * Antwort aendert nichts und zaehlt nicht.
 */
export function bewertePing(stand: PingStand, antwort: PingAntwort, jetzt: number): PingErgebnis {
  if (antwort === "ok") {
    return {
      stand: { fehlschlaege: 0, letzterFehlschlag: 0, faellig: jetzt + PING_OK_MS, belegtOffline: false },
      zustand: "ungeprueft",
      warteMs: PING_OK_MS,
    };
  }
  if (antwort === "unklar") {
    return {
      stand: { ...stand, faellig: jetzt + PING_OFFLINE_MS },
      zustand: null,
      warteMs: PING_OFFLINE_MS,
    };
  }
  const inFolge = stand.fehlschlaege > 0 && jetzt - stand.letzterFehlschlag <= PING_FOLGE_MAX_MS;
  const fehlschlaege = (inFolge ? stand.fehlschlaege : 0) + 1;
  if (fehlschlaege >= PING_FEHLSCHLAEGE_OFFLINE) {
    return {
      stand: { fehlschlaege, letzterFehlschlag: jetzt, faellig: jetzt + PING_OFFLINE_MS, belegtOffline: true },
      zustand: "offline",
      warteMs: PING_OFFLINE_MS,
    };
  }
  return {
    stand: { ...stand, fehlschlaege, letzterFehlschlag: jetzt, faellig: jetzt + PING_BESTAETIGUNG_MS },
    zustand: null,
    warteMs: PING_BESTAETIGUNG_MS,
  };
}

/** Ein Livebild (`playing`) ist der staerkste Beweis: Stand zuruecksetzen. */
export function nachLivebild(jetzt: number): PingStand {
  return { fehlschlaege: 0, letzterFehlschlag: 0, faellig: jetzt + PING_OK_MS, belegtOffline: false };
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
