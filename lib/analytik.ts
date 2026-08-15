/**
 * Langzeitauswertung der KI-Wache — reine Rechenfunktionen, keine Nebenwirkungen.
 *
 * Bewusst frei von `process.env`, KV und `Buffer` (wie `ereignis-modell.ts`),
 * damit Server-Route und Client-Komponente dieselbe Logik teilen koennen, ohne
 * dass der Serverspeicher aus `lib/events.ts` ins Browser-Bundle wandert.
 *
 * Warum ueberhaupt aggregieren, statt im Frontend zu rechnen? Wegen Mobilfunk:
 * Bei gefuelltem Speicher (200 Ereignisse, 30 Tage) sind es gemessen ~48 kB
 * Rohliste gegen ~10 kB Bericht — gut ein Viertel. Bei wenigen Ereignissen
 * ist der Bericht sogar groesser als die Rohliste, aber dann geht es um ein
 * paar Kilobyte, die auf keiner Leitung wehtun.
 *
 * Zeitzone: Ein Tagesgang in UTC waere fuer einen Hof in Mitteleuropa im
 * Sommer um zwei Stunden verschoben — die naechtliche Kalbespitze landete am
 * Abend. Alle Tages- und Stundenraster entstehen deshalb ueber
 * `Intl.DateTimeFormat` in einer echten Zeitzone (Default Europe/Berlin), die
 * damit auch die Sommerzeit korrekt behandelt.
 */

import type { EreignisTyp, StallEreignis } from "@/lib/ereignis-modell";

export const STANDARD_ZEITZONE = "Europe/Berlin";

/** Auswaehlbare Betrachtungszeitraeume der Analytik-Seite. */
export const ZEITRAEUME = [7, 14, 30] as const;
export type ZeitraumTage = (typeof ZEITRAEUME)[number];

/**
 * Innerhalb dieser Frist gilt ein Kalbeverdacht als bestaetigt, wenn dieselbe
 * Kuh danach eine Austreibung zeigt. 12 h deckt auch eine lange, zaehe Geburt
 * ab, ohne den Verdacht von vorgestern noch dem Kalb von heute zuzurechnen.
 */
export const BESTAETIGUNG_STUNDEN = 12;

/**
 * Zwei Brunstmeldungen naeher als das beieinander gehoeren zur selben Brunst
 * (eine Brunst dauert Stunden und erzeugt mehrere Aufspruenge), zaehlen also
 * nicht als neuer Zyklus.
 */
const BRUNST_MINDESTABSTAND_STUNDEN = 36;

/** Regelzyklus des Rindes: 21 Tage, physiologisch normal sind 18–24. */
export const ZYKLUS_NORMAL_MIN = 18;
export const ZYKLUS_NORMAL_MAX = 24;

// ---------------------------------------------------------------------------
// Berichtsform
// ---------------------------------------------------------------------------

export interface TagesPunkt {
  /** Kalendertag als "YYYY-MM-DD" in der Auswertungszeitzone. */
  tag: string;
  /** Kurzform fuer die Achse, z.B. "Mo 04.08." */
  label: string;
  kalbeverdacht: number;
  austreibung: number;
  brunstverdacht: number;
  gesamt: number;
}

export interface StundenPunkt {
  /** 0..23 in der Auswertungszeitzone. */
  stunde: number;
  kalbung: number;
  brunst: number;
  gesamt: number;
}

export interface KameraPunkt {
  kamera: string;
  gesamt: number;
  kalbung: number;
  brunst: number;
}

export interface BrunstZyklus {
  kuhId: string;
  /** Zeitpunkte der als eigenstaendig gewerteten Brunsten (aufsteigend). */
  brunsten: string[];
  /** Median der Abstaende in Tagen; null bei nur einer Brunst. */
  medianTage: number | null;
  /** Erwarteter naechster Termin (ISO) — nur bei plausiblem Zyklus. */
  prognose: string | null;
  bewertung: "regelmaessig" | "auffaellig" | "zu_wenig_daten";
}

export interface AnalytikBericht {
  zeitraumTage: number;
  /** Untere Grenze des Auswertungsfensters (ISO). */
  von: string;
  bis: string;
  zeitzone: string;
  quelle: "edge-agent" | "demo";
  datenbasis: {
    /** Ereignisse im Fenster. */
    ereignisse: number;
    /** Aeltestes bekanntes Ereignis ueberhaupt (ISO) oder null. */
    aeltestes: string | null;
    /**
     * true, wenn der Ringpuffer (nicht der gewaehlte Zeitraum) die Grenze
     * setzt — dann ist der Verlauf am linken Rand unvollstaendig und die
     * Seite sagt das auch.
     */
    begrenzt: boolean;
  };
  gesamt: Record<EreignisTyp, number>;
  verlauf: TagesPunkt[];
  tagesgang: StundenPunkt[];
  kameras: KameraPunkt[];
  brunstZyklen: BrunstZyklus[];
  reaktion: {
    alarme: number;
    quittiert: number;
    offen: number;
    /** Median der Zeit bis „Gesehen" in Minuten; null ohne Quittierung. */
    medianMinuten: number | null;
  };
  bestaetigung: {
    verdachte: number;
    bestaetigt: number;
    /** Anteil 0..1; null, wenn es keinen Verdacht im Fenster gab. */
    quote: number | null;
  };
}

// ---------------------------------------------------------------------------
// Zeitzonen-Raster
// ---------------------------------------------------------------------------

interface Zeitteile {
  tag: string; // YYYY-MM-DD
  stunde: number; // 0..23
}

/**
 * Zerlegt einen Zeitstempel in Kalendertag und Stunde **der Zielzeitzone**.
 * `Intl` ist der einzige Weg, der ohne Zusatzpaket auch Sommerzeit kennt.
 */
function zerlege(iso: string, formatierer: Intl.DateTimeFormat): Zeitteile | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const teile = formatierer.formatToParts(new Date(t));
  const feld = (typ: string) => teile.find((p) => p.type === typ)?.value ?? "";
  const jahr = feld("year");
  const monat = feld("month");
  const tag = feld("day");
  // "24" statt "00" liefern manche Laufzeiten fuer Mitternacht (hourCycle h23
  // ist erst ab neueren Versionen verlaesslich) — auf 0 normalisieren.
  const stunde = Number(feld("hour")) % 24;
  if (!jahr || !monat || !tag || Number.isNaN(stunde)) return null;
  return { tag: `${jahr}-${monat}-${tag}`, stunde };
}

function baueFormatierer(zeitzone: string): Intl.DateTimeFormat {
  try {
    return new Intl.DateTimeFormat("de-DE", {
      timeZone: zeitzone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      hour12: false,
    });
  } catch {
    // Unbekannte Zeitzone darf die Analytik nicht sprengen.
    return new Intl.DateTimeFormat("de-DE", {
      timeZone: "UTC",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      hour12: false,
    });
  }
}

/** "2026-08-04" -> "Mo 04.08." (Achsenbeschriftung, ohne erneutes Parsen der Zeitzone). */
function tagesLabel(tag: string): string {
  const [j, m, t] = tag.split("-").map(Number);
  if (!j || !m || !t) return tag;
  // Mittag als Bezug: haelt das Label auch bei Zeitumstellung auf dem Tag.
  const d = new Date(Date.UTC(j, m - 1, t, 12));
  const wt = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"][d.getUTCDay()];
  return `${wt} ${String(t).padStart(2, "0")}.${String(m).padStart(2, "0")}.`;
}

// ---------------------------------------------------------------------------
// Hauptauswertung
// ---------------------------------------------------------------------------

const LEER_GESAMT = (): Record<EreignisTyp, number> => ({
  kalbeverdacht: 0,
  austreibung: 0,
  brunstverdacht: 0,
  info: 0,
});

const istKalbung = (t: EreignisTyp) => t === "kalbeverdacht" || t === "austreibung";

/**
 * Rechnet die Ereignisliste zum Bericht.
 *
 * `jetzt` ist injizierbar, damit die Auswertung testbar bleibt und Server und
 * Client denselben Fensterrand benutzen koennen.
 */
export function baueBericht(
  alle: readonly StallEreignis[],
  optionen: {
    zeitraumTage: number;
    zeitzone?: string;
    quelle?: "edge-agent" | "demo";
    jetzt?: number;
  },
): AnalytikBericht {
  const zeitzone = optionen.zeitzone?.trim() || STANDARD_ZEITZONE;
  const formatierer = baueFormatierer(zeitzone);
  const jetzt = optionen.jetzt ?? Date.now();
  const tage = Math.max(1, Math.round(optionen.zeitraumTage));
  const von = jetzt - tage * 86_400_000;

  const imFenster = alle.filter((e) => {
    const t = Date.parse(e.zeit);
    // Unparsbare Zeit lieber behalten als still verschlucken (wie im Protokoll).
    return Number.isNaN(t) || t >= von;
  });

  // Aeltestes Ereignis der **ganzen** Liste: zeigt, wie weit der Speicher reicht.
  let aeltesteZeit = Number.POSITIVE_INFINITY;
  for (const e of alle) {
    const t = Date.parse(e.zeit);
    if (!Number.isNaN(t) && t < aeltesteZeit) aeltesteZeit = t;
  }
  const hatAeltestes = Number.isFinite(aeltesteZeit);

  const gesamt = LEER_GESAMT();
  for (const e of imFenster) {
    if (e.typ in gesamt) gesamt[e.typ] += 1;
  }

  return {
    zeitraumTage: tage,
    von: new Date(von).toISOString(),
    bis: new Date(jetzt).toISOString(),
    zeitzone,
    quelle: optionen.quelle ?? "edge-agent",
    datenbasis: {
      ereignisse: imFenster.length,
      aeltestes: hatAeltestes ? new Date(aeltesteZeit).toISOString() : null,
      // Der Puffer begrenzt, wenn sein aeltester Eintrag juenger ist als der
      // gewuenschte Fensterrand: dann fehlen Tage, die es mal gab.
      begrenzt: hatAeltestes && aeltesteZeit > von,
    },
    gesamt,
    verlauf: baueVerlauf(imFenster, tage, jetzt, formatierer),
    tagesgang: baueTagesgang(imFenster, formatierer),
    kameras: baueKameras(imFenster),
    brunstZyklen: baueBrunstZyklen(alle, jetzt),
    reaktion: baueReaktion(imFenster),
    bestaetigung: baueBestaetigung(alle, imFenster),
  };
}

/** Ein Balken pro Kalendertag — auch fuer Tage ohne Ereignis (Luecken sind Information). */
function baueVerlauf(
  ereignisse: readonly StallEreignis[],
  tage: number,
  jetzt: number,
  formatierer: Intl.DateTimeFormat,
): TagesPunkt[] {
  const punkte = new Map<string, TagesPunkt>();
  // Rueckwaerts vom heutigen Tag, damit auch leere Tage eine Saeule bekommen.
  for (let i = tage - 1; i >= 0; i--) {
    const teile = zerlege(new Date(jetzt - i * 86_400_000).toISOString(), formatierer);
    if (!teile) continue;
    punkte.set(teile.tag, {
      tag: teile.tag,
      label: tagesLabel(teile.tag),
      kalbeverdacht: 0,
      austreibung: 0,
      brunstverdacht: 0,
      gesamt: 0,
    });
  }

  for (const e of ereignisse) {
    if (e.typ === "info") continue; // Systemmeldungen verzerren den Verlauf.
    const teile = zerlege(e.zeit, formatierer);
    const punkt = teile && punkte.get(teile.tag);
    if (!punkt) continue;
    if (e.typ === "kalbeverdacht") punkt.kalbeverdacht += 1;
    else if (e.typ === "austreibung") punkt.austreibung += 1;
    else punkt.brunstverdacht += 1;
    punkt.gesamt += 1;
  }
  return [...punkte.values()];
}

/**
 * Tagesgang ueber 24 Stunden.
 *
 * Die eigentliche Frage dahinter: „Wann muss ich wach sein?" Kalbungen haeufen
 * sich nachts, Brunst zeigt sich eher in den ruhigen Stunden nach dem Melken —
 * beides sieht man erst, wenn man ueber Wochen uebereinanderlegt.
 */
function baueTagesgang(
  ereignisse: readonly StallEreignis[],
  formatierer: Intl.DateTimeFormat,
): StundenPunkt[] {
  const punkte: StundenPunkt[] = Array.from({ length: 24 }, (_, stunde) => ({
    stunde,
    kalbung: 0,
    brunst: 0,
    gesamt: 0,
  }));
  for (const e of ereignisse) {
    if (e.typ === "info") continue;
    const teile = zerlege(e.zeit, formatierer);
    if (!teile) continue;
    const p = punkte[teile.stunde];
    if (!p) continue;
    if (istKalbung(e.typ)) p.kalbung += 1;
    else p.brunst += 1;
    p.gesamt += 1;
  }
  return punkte;
}

/** Welche Kamera liefert was — zeigt tote Winkel und ueberaktive Buchten. */
function baueKameras(ereignisse: readonly StallEreignis[]): KameraPunkt[] {
  const nach = new Map<string, KameraPunkt>();
  for (const e of ereignisse) {
    if (e.typ === "info") continue;
    const kamera = e.kamera || "unbekannt";
    const p = nach.get(kamera) ?? { kamera, gesamt: 0, kalbung: 0, brunst: 0 };
    p.gesamt += 1;
    if (istKalbung(e.typ)) p.kalbung += 1;
    else p.brunst += 1;
    nach.set(kamera, p);
  }
  return [...nach.values()].sort((a, b) => b.gesamt - a.gesamt);
}

/**
 * Brunstrhythmus je Kuh — der eigentliche Langzeitnutzen.
 *
 * Das Rind zeigt alle ~21 Tage Brunst. Wer den letzten Termin und den
 * persoenlichen Abstand einer Kuh kennt, weiss, wann er das naechste Mal
 * hinschauen muss — und sieht an einem auffaelligen Abstand (< 18 oder > 24
 * Tage) einen moeglichen Zyklusfehler, bevor die Zwischenkalbezeit leidet.
 *
 * Bewusst ueber die **ganze** Liste statt nur ueber das Fenster: Ein
 * 21-Tage-Zyklus ist in 7 Tagen nicht sichtbar.
 */
function baueBrunstZyklen(
  alle: readonly StallEreignis[],
  jetzt: number,
): BrunstZyklus[] {
  const nachKuh = new Map<string, number[]>();
  for (const e of alle) {
    if (e.typ !== "brunstverdacht" || !e.kuhId) continue;
    const t = Date.parse(e.zeit);
    if (Number.isNaN(t)) continue;
    const liste = nachKuh.get(e.kuhId) ?? [];
    liste.push(t);
    nachKuh.set(e.kuhId, liste);
  }

  const zyklen: BrunstZyklus[] = [];
  for (const [kuhId, roh] of nachKuh) {
    roh.sort((a, b) => a - b);
    // Meldungen derselben Brunst zusammenfassen: nur der erste Aufsprung
    // markiert den Zyklusbeginn, die folgenden gehoeren dazu.
    const brunsten: number[] = [];
    for (const t of roh) {
      const letzte = brunsten[brunsten.length - 1];
      if (letzte === undefined || t - letzte >= BRUNST_MINDESTABSTAND_STUNDEN * 3600_000) {
        brunsten.push(t);
      }
    }

    const abstaendeTage: number[] = [];
    for (let i = 1; i < brunsten.length; i++) {
      abstaendeTage.push((brunsten[i] - brunsten[i - 1]) / 86_400_000);
    }
    const median = abstaendeTage.length > 0 ? medianVon(abstaendeTage) : null;
    const letzte = brunsten[brunsten.length - 1];

    let bewertung: BrunstZyklus["bewertung"] = "zu_wenig_daten";
    let prognose: string | null = null;
    if (median !== null) {
      const plausibel = median >= ZYKLUS_NORMAL_MIN && median <= ZYKLUS_NORMAL_MAX;
      bewertung = plausibel ? "regelmaessig" : "auffaellig";
      // Prognose nur auf plausibler Grundlage — ein Termin aus einem
      // 4-Tage-„Zyklus" waere eine Falschaussage mit Datumsangabe.
      if (plausibel) {
        prognose = new Date(letzte + median * 86_400_000).toISOString();
      }
    }

    zyklen.push({
      kuhId,
      brunsten: brunsten.map((t) => new Date(t).toISOString()),
      medianTage: median === null ? null : Math.round(median * 10) / 10,
      prognose,
      bewertung,
    });
  }

  // Naechster faelliger Termin zuerst; Kuehe ohne Prognose ans Ende.
  return zyklen.sort((a, b) => {
    const ta = a.prognose ? Date.parse(a.prognose) : Number.POSITIVE_INFINITY;
    const tb = b.prognose ? Date.parse(b.prognose) : Number.POSITIVE_INFINITY;
    if (ta !== tb) return ta - tb;
    return Date.parse(b.brunsten[b.brunsten.length - 1] ?? "0") - jetzt;
  });
}

function medianVon(werte: number[]): number {
  const s = [...werte].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 === 1 ? s[m] : (s[m - 1] + s[m]) / 2;
}

/**
 * Wie schnell wird reagiert?
 *
 * Median statt Mittelwert: Eine einzige Nacht, in der das Handy stumm im
 * Haus lag, wuerde den Mittelwert unbrauchbar machen. Der Median beschreibt
 * den normalen Fall — und genau der ist die Frage.
 */
function baueReaktion(ereignisse: readonly StallEreignis[]): AnalytikBericht["reaktion"] {
  const alarme = ereignisse.filter((e) => e.typ !== "info");
  const dauern: number[] = [];
  let quittiert = 0;
  for (const e of alarme) {
    if (!e.quittiert) continue;
    quittiert += 1;
    const auf = Date.parse(e.zeit);
    const ab = Date.parse(e.quittiert);
    if (Number.isNaN(auf) || Number.isNaN(ab) || ab < auf) continue;
    dauern.push((ab - auf) / 60_000);
  }
  return {
    alarme: alarme.length,
    quittiert,
    offen: alarme.length - quittiert,
    medianMinuten: dauern.length > 0 ? Math.round(medianVon(dauern)) : null,
  };
}

/**
 * Bestaetigungsquote: Wie viele Kalbeverdachte muendeten in eine Austreibung?
 *
 * Das ist die ehrlichste Kennzahl, die die App ohne Handeingabe hat — eine
 * Naeherung der Treffergenauigkeit aus den eigenen Daten. Sie ersetzt keine
 * gelabelte Validierung (`docs/metriken.md`), zeigt aber sofort, wenn das
 * Modell anfaengt, ins Leere zu alarmieren.
 *
 * Gesucht wird in der **ganzen** Liste, damit eine Austreibung kurz nach dem
 * Fensterrand den Verdacht im Fenster noch bestaetigen kann.
 */
function baueBestaetigung(
  alle: readonly StallEreignis[],
  imFenster: readonly StallEreignis[],
): AnalytikBericht["bestaetigung"] {
  const austreibungen = new Map<string, number[]>();
  for (const e of alle) {
    if (e.typ !== "austreibung" || !e.kuhId) continue;
    const t = Date.parse(e.zeit);
    if (Number.isNaN(t)) continue;
    const liste = austreibungen.get(e.kuhId) ?? [];
    liste.push(t);
    austreibungen.set(e.kuhId, liste);
  }

  const frist = BESTAETIGUNG_STUNDEN * 3600_000;
  let verdachte = 0;
  let bestaetigt = 0;
  for (const e of imFenster) {
    if (e.typ !== "kalbeverdacht" || !e.kuhId) continue;
    const t = Date.parse(e.zeit);
    if (Number.isNaN(t)) continue;
    verdachte += 1;
    const treffer = (austreibungen.get(e.kuhId) ?? []).some(
      (a) => a >= t && a - t <= frist,
    );
    if (treffer) bestaetigt += 1;
  }
  return {
    verdachte,
    bestaetigt,
    quote: verdachte > 0 ? bestaetigt / verdachte : null,
  };
}
