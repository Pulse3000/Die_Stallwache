/**
 * Statusabfrage der KI-Wache („Status in der Stallwache?", „Auffälligkeiten
 * bei Kuh #12?").
 *
 * Ordnet die Befunde des Edge-Agenten je Kamera und je Kuh in
 * OK / WARNUNG / KRITISCH / UNBEKANNT ein. Spezifikation mit Regeln, Grenzen
 * und Abnahmekriterien: docs/statusabfrage-spezifikation.md.
 *
 * Zwei Grundsaetze, die man dem Code nicht ansieht:
 *
 *   - **Schweigen ist kein „OK".** OK gibt es nur mit aktuellem Lebenszeichen
 *     der Kamera, im Analyse-Modus und mit Bild. Sonst UNBEKANNT mit Grund.
 *   - **Keine zweite Alarmlogik.** Hier wird nur eingeordnet, was der
 *     Edge-Agent gemeldet hat — keine Neubewertung, keine Benachrichtigung.
 *
 * Rein funktional (kein Env, kein Speicher), damit direkt testbar:
 * tests/stall-status.test.ts.
 */

import type { EreignisTyp, StallEreignis } from "@/lib/ereignis-modell";

export type Stufe = "OK" | "WARNUNG" | "KRITISCH" | "UNBEKANNT";
export type AgentModus = "analyse" | "silent";

/** Letztes Lebenszeichen einer Kamera (vom Edge-Agenten gemeldet). */
export interface Lebenszeichen {
  zeit: string;
  /** null = Agent hat keinen gueltigen Modus gemeldet. */
  modus: AgentModus | null;
  /** Stream liefert verwertbare Frames; null = unbekannt. */
  bild: boolean | null;
}

export interface StatusEingabe {
  ereignisse: StallEreignis[];
  quelle: "edge-agent" | "demo";
  /** Globaler Kontakt (jedes Ereignis, jeder Stapel) — Rueckfall fuer alte Agenten. */
  letzterKontakt: string | null;
  /** Lebenszeichen je Kamera. */
  lebenszeichen: Record<string, Lebenszeichen>;
  /**
   * "kv" = Ereignisliste aus dem dauerhaften Store; "instanz" = nur der
   * Puffer dieser Serverless-Instanz (kein KV oder Lesefehler). Dann koennen
   * Alarme fehlen — es gibt hoechstens UNBEKANNT, nie OK.
   */
  speicher: "kv" | "instanz";
}

export interface StatusOptionen {
  jetzt?: number;
  /** Auswertungsfenster in Stunden (Default 12). */
  stunden?: number;
  kamera?: string;
  kuh?: string;
  /** Spiegel von telegram.cooldown_minuten des Agenten (Default 15). */
  cooldownMinuten?: number;
  /** Ab diesem Alter gilt eine Kamera als ohne Lebenszeichen (Default 15). */
  lebenszeichenMaxMinuten?: number;
  zeitzone?: string;
}

export type Evidenz = "modellbasiert" | "regelbasiert";

export interface StatusAlarm {
  id: string;
  typ: EreignisTyp;
  zeit: string;
  nachricht: string;
  konfidenz: number | null;
  evidenz: Evidenz;
  quittiert: string | null;
  /** Kontroll-Alarm „kein Geburtsfortschritt". */
  eskalation: boolean;
}

export interface Cooldown {
  typ: EreignisTyp;
  /** Bis dahin buendelt der Agent Folgemeldungen gleicher Art (ISO). */
  bis: string;
}

export interface KuhStatus {
  kuhId: string;
  stufe: Stufe;
  alarme: StatusAlarm[];
  cooldown: Cooldown[];
  text: string;
}

export interface Datenlage {
  aktuell: boolean;
  /** Woher die Aussage zum Kamerazustand stammt. */
  quelle: "kamera" | "global" | "keine";
  lebenszeichen: Lebenszeichen | null;
  /** Klartext-Grund, wenn nicht aktuell. */
  grund: string | null;
}

export interface KameraStatus {
  kamera: string;
  stufe: Stufe;
  datenlage: Datenlage;
  /** Ereignisse ohne Kuh-Bezug (Austreibung, Eskalation). */
  kameraAlarme: StatusAlarm[];
  cooldown: Cooldown[];
  kuehe: KuhStatus[];
  text: string;
}

export interface StallStatus {
  stand: string;
  fensterStunden: number;
  stufe: Stufe;
  quelle: "edge-agent" | "demo";
  speicher: "kv" | "instanz";
  kameras: KameraStatus[];
  text: string;
}

export const STANDARD_FENSTER_STUNDEN = 12;
export const MAX_FENSTER_STUNDEN = 72;
const ALARM_TYPEN: readonly EreignisTyp[] = [
  "kalbeverdacht",
  "austreibung",
  "brunstverdacht",
];
/** Markierung, mit der der Agent den Eskalations-Alarm meldet (kein Tier). */
const ESKALATION_KENNUNG = "Eskalation";
const RANG: Record<Stufe, number> = { OK: 0, UNBEKANNT: 1, WARNUNG: 2, KRITISCH: 3 };
const TYP_NAME: Record<EreignisTyp, string> = {
  kalbeverdacht: "Kalbeverdacht",
  austreibung: "Austreibung",
  brunstverdacht: "Brunstverdacht",
  info: "Systemmeldung",
};

function hoechste(stufen: Stufe[]): Stufe {
  return stufen.reduce<Stufe>((a, b) => (RANG[b] > RANG[a] ? b : a), "OK");
}

/** "42" aus "Kuh #42", "kuh 42", "#42" — null, wenn keine Nummer drinsteht. */
function kuhNummer(text: string): string | null {
  const m = text.match(/(\d{1,6})/);
  return m ? String(Number(m[1])) : null;
}

function istKameraEreignis(e: StallEreignis): boolean {
  return e.typ === "austreibung" || !e.kuhId || e.kuhId === ESKALATION_KENNUNG;
}

function zuAlarm(e: StallEreignis): StatusAlarm {
  return {
    id: e.id,
    typ: e.typ,
    zeit: e.zeit,
    nachricht: e.nachricht,
    konfidenz: e.konfidenz,
    // Nur die Austreibung stuetzt sich auf eine Objekterkennung; Kalbe- und
    // Brunstverdacht sind Regeln ueber Keypoints bzw. Boxen (Verdacht).
    evidenz: e.typ === "austreibung" ? "modellbasiert" : "regelbasiert",
    quittiert: e.quittiert,
    eskalation: e.kuhId === ESKALATION_KENNUNG,
  };
}

function stufeAusAlarmen(alarme: StatusAlarm[]): Stufe | null {
  const offen = alarme.filter((a) => !a.quittiert);
  if (offen.some((a) => a.typ === "austreibung")) return "KRITISCH";
  if (offen.length > 0) return "WARNUNG";
  return null;
}

export function baueStallStatus(
  eingabe: StatusEingabe,
  optionen: StatusOptionen = {},
): StallStatus {
  const jetzt = optionen.jetzt ?? Date.now();
  const stunden = Math.min(
    MAX_FENSTER_STUNDEN,
    Math.max(1, optionen.stunden ?? STANDARD_FENSTER_STUNDEN),
  );
  const cooldownMs = Math.max(0, optionen.cooldownMinuten ?? 15) * 60_000;
  const maxAlterMs = Math.max(1, optionen.lebenszeichenMaxMinuten ?? 15) * 60_000;
  const uhr = uhrzeitFormat(optionen.zeitzone, jetzt);
  const stand = new Date(jetzt).toISOString();

  // Demo-Daten sind kein Stallzustand: lieber gar nichts einordnen als eine
  // erfundene WARNUNG ausgeben. Hat sich aber schon ein Agent per
  // Lebenszeichen gemeldet, ist der Stall nur noch ohne Ereignisse — dann
  // gilt die leere Liste, nicht die Demo.
  if (eingabe.quelle === "demo" && Object.keys(eingabe.lebenszeichen).length > 0) {
    eingabe = { ...eingabe, ereignisse: [], quelle: "edge-agent" };
  }
  if (eingabe.quelle === "demo") {
    return {
      stand,
      fensterStunden: stunden,
      stufe: "UNBEKANNT",
      quelle: "demo",
      speicher: eingabe.speicher,
      kameras: [],
      text:
        "Noch kein Edge-Agent verbunden – angezeigt werden Demo-Daten, kein Stallzustand.",
    };
  }

  const grenze = jetzt - stunden * 3_600_000;
  const imFenster = eingabe.ereignisse.filter((e) => {
    const t = Date.parse(e.zeit);
    // Unparsbare Zeit lieber zeigen als still verschlucken.
    return Number.isNaN(t) || t >= grenze;
  });

  const kameraFilter = optionen.kamera?.trim().toLowerCase() || null;
  const kuhFilter = optionen.kuh?.trim() || null;
  const kuhFilterNummer = kuhFilter ? kuhNummer(kuhFilter) : null;
  const passtKuh = (kuhId: string) =>
    !kuhFilter ||
    (kuhFilterNummer !== null
      ? kuhNummer(kuhId) === kuhFilterNummer
      : kuhId.toLowerCase() === kuhFilter.toLowerCase());

  // Kameras: alles, was sich im Fenster gemeldet hat oder ein Lebenszeichen hat.
  const namen = new Set<string>(Object.keys(eingabe.lebenszeichen));
  for (const e of imFenster) if (e.kamera) namen.add(e.kamera);
  if (kameraFilter) {
    for (const n of [...namen]) if (n.toLowerCase() !== kameraFilter) namen.delete(n);
    if (namen.size === 0) namen.add(optionen.kamera!.trim());
  }

  const kameras: KameraStatus[] = [...namen].sort().map((kamera) => {
    const datenlage = bewerteDatenlage(
      eingabe.lebenszeichen[kamera] ?? null,
      eingabe.letzterKontakt,
      eingabe.speicher,
      jetzt,
      maxAlterMs,
      uhr,
    );
    const basis: Stufe = datenlage.aktuell ? "OK" : "UNBEKANNT";
    const alarme = imFenster
      .filter((e) => e.kamera === kamera && ALARM_TYPEN.includes(e.typ))
      .map((e) => ({ e, a: zuAlarm(e) }));

    const kameraAlarme = alarme.filter(({ e }) => istKameraEreignis(e)).map(({ a }) => a);
    const jeKuh = new Map<string, StatusAlarm[]>();
    for (const { e, a } of alarme) {
      if (istKameraEreignis(e) || !passtKuh(e.kuhId!)) continue;
      const liste = jeKuh.get(e.kuhId!) ?? [];
      liste.push(a);
      jeKuh.set(e.kuhId!, liste);
    }

    const kuehe: KuhStatus[] = [...jeKuh.entries()]
      .sort(([a], [b]) => a.localeCompare(b, "de", { numeric: true }))
      .map(([kuhId, liste]) => {
        const stufe = stufeAusAlarmen(liste) ?? basis;
        const cooldown = berechneCooldown(liste, jetzt, cooldownMs);
        return {
          kuhId,
          stufe,
          alarme: liste,
          cooldown,
          text: kuhText(kuhId, stufe, liste, cooldown, uhr),
        };
      });

    const stufe = hoechste([
      basis,
      stufeAusAlarmen(kameraAlarme) ?? "OK",
      ...kuehe.map((k) => k.stufe),
    ]);
    const cooldown = berechneCooldown(
      kameraAlarme.filter((a) => !a.eskalation),
      jetzt,
      cooldownMs,
    );
    return {
      kamera,
      stufe,
      datenlage,
      kameraAlarme,
      cooldown,
      kuehe,
      text: kameraText(kamera, stufe, datenlage, kameraAlarme, kuehe, stunden, uhr),
    };
  });

  const zeilen: string[] = [];
  if (kuhFilter && !kameras.some((k) => k.kuehe.length > 0)) {
    const name = kuhFilterNummer !== null ? `Kuh #${kuhFilterNummer}` : kuhFilter;
    zeilen.push(`${name}: keine Alarme in den letzten ${stunden} h.`);
  }
  if (kameras.length === 0) {
    zeilen.push(
      "Kein Edge-Agent hat sich gemeldet – keine Aussage über den Stall möglich.",
    );
  }
  for (const k of kameras) {
    zeilen.push(k.text);
    for (const kuh of k.kuehe) zeilen.push(kuh.text);
  }

  return {
    stand,
    fensterStunden: stunden,
    stufe: kameras.length > 0 ? hoechste(kameras.map((k) => k.stufe)) : "UNBEKANNT",
    quelle: eingabe.quelle,
    speicher: eingabe.speicher,
    kameras,
    text: zeilen.join("\n"),
  };
}

function bewerteDatenlage(
  lz: Lebenszeichen | null,
  letzterKontakt: string | null,
  speicher: "kv" | "instanz",
  jetzt: number,
  maxAlterMs: number,
  uhr: (iso: string) => string,
): Datenlage {
  if (!lz) {
    // Alter Agent ohne Kamera-Lebenszeichen: Kontakt sagt nichts ueber
    // Modus und Bild — also hoechstens UNBEKANNT.
    return {
      aktuell: false,
      quelle: letzterKontakt ? "global" : "keine",
      lebenszeichen: null,
      grund: letzterKontakt
        ? `kein Kamera-Lebenszeichen (Agent-Update nötig), letzter Kontakt ${uhr(letzterKontakt)}`
        : "kein Lebenszeichen vom Edge-Agenten",
    };
  }
  const t = Date.parse(lz.zeit);
  const alterMs = Number.isNaN(t) ? Infinity : jetzt - t;
  let grund: string | null = null;
  if (alterMs > maxAlterMs) {
    grund = Number.isFinite(alterMs)
      ? `letztes Lebenszeichen ${uhr(lz.zeit)} (vor ${Math.round(alterMs / 60_000)} min)`
      : "Lebenszeichen ohne gültige Zeit";
  } else if (lz.modus === "silent") {
    grund = "Silent Mode (Datensammlung), Tiere werden noch nicht analysiert";
  } else if (lz.modus !== "analyse") {
    grund = "Betriebsmodus des Agenten unbekannt";
  } else if (lz.bild === false) {
    grund = "Kamera liefert kein Bild";
  } else if (lz.bild !== true) {
    grund = "Bildzustand der Kamera unbekannt";
  } else if (speicher !== "kv") {
    // Ohne dauerhaften Store sieht diese Instanz nur ihre eigenen
    // Ereignisse: Ein Alarm, der auf einer anderen Instanz oder vor einem
    // Redeploy eingegangen ist, fehlt hier — „OK" waere dann gelogen.
    grund =
      "keine dauerhafte Ereignisablage (KV-Store fehlt oder nicht erreichbar) – Alarme anderer App-Instanzen oder von vor einem Neustart wären hier nicht sichtbar";
  }
  return { aktuell: grund === null, quelle: "kamera", lebenszeichen: lz, grund };
}

/** Juengster Alarm je Typ + Cooldown, solange er noch laeuft. */
function berechneCooldown(
  alarme: StatusAlarm[],
  jetzt: number,
  cooldownMs: number,
): Cooldown[] {
  if (cooldownMs <= 0) return [];
  const zuletzt = new Map<EreignisTyp, number>();
  for (const a of alarme) {
    const t = Date.parse(a.zeit);
    if (Number.isNaN(t)) continue;
    if (t > (zuletzt.get(a.typ) ?? -Infinity)) zuletzt.set(a.typ, t);
  }
  return [...zuletzt.entries()]
    .filter(([, t]) => t + cooldownMs > jetzt)
    .map(([typ, t]) => ({ typ, bis: new Date(t + cooldownMs).toISOString() }));
}

function alarmZeile(a: StatusAlarm, uhr: (iso: string) => string): string {
  const name = a.eskalation ? "Kein Geburtsfortschritt" : TYP_NAME[a.typ];
  const evidenz =
    a.evidenz === "modellbasiert"
      ? `modellbasiert${a.konfidenz !== null ? `, Konfidenz ${Math.round(a.konfidenz * 100)} %` : ""}`
      : "regelbasiert, Verdacht ohne Objekt-Evidenz";
  const zustand = a.quittiert ? `gesehen ${uhr(a.quittiert)}` : "offen";
  return `${name} ${uhr(a.zeit)}, ${zustand} (${evidenz})`;
}

/** Juengster offener Alarm, sonst juengster ueberhaupt. */
function massgeblich(alarme: StatusAlarm[]): StatusAlarm | null {
  const nachZeit = [...alarme].sort((a, b) => Date.parse(b.zeit) - Date.parse(a.zeit));
  const offen = nachZeit.filter((a) => !a.quittiert);
  // Bei offener Austreibung zaehlt die Eskalation bzw. Austreibung zuerst.
  return (
    offen.find((a) => a.eskalation) ??
    offen.find((a) => a.typ === "austreibung") ??
    offen[0] ??
    nachZeit[0] ??
    null
  );
}

function kuhText(
  kuhId: string,
  stufe: Stufe,
  alarme: StatusAlarm[],
  cooldown: Cooldown[],
  uhr: (iso: string) => string,
): string {
  const a = massgeblich(alarme);
  let text = `${kuhId}: ${stufe}`;
  if (a) text += ` – ${alarmZeile(a, uhr)}.`;
  const weitere = alarme.filter((x) => !x.quittiert).length - (a && !a.quittiert ? 1 : 0);
  if (weitere > 0) text += ` ${weitere} weitere offene Meldung(en).`;
  for (const c of cooldown) {
    text += ` Folgemeldungen ${TYP_NAME[c.typ]} gebündelt bis ${uhr(c.bis)}.`;
  }
  return text;
}

function kameraText(
  kamera: string,
  stufe: Stufe,
  datenlage: Datenlage,
  kameraAlarme: StatusAlarm[],
  kuehe: KuhStatus[],
  stunden: number,
  uhr: (iso: string) => string,
): string {
  const name = kamera.charAt(0).toUpperCase() + kamera.slice(1);
  const teile: string[] = [];
  const offeneKamera = kameraAlarme.filter((a) => !a.quittiert);
  const offeneKuehe = kuehe.filter((k) => k.stufe === "WARNUNG" || k.stufe === "KRITISCH");

  if (offeneKamera.length > 0) {
    teile.push(`${alarmZeile(massgeblich(kameraAlarme)!, uhr)}.`);
    if (offeneKamera.length > 1) teile.push(`${offeneKamera.length} offene Meldungen ohne Kuh-Bezug.`);
  }
  if (offeneKuehe.length > 0) {
    teile.push(
      `Offene Verdachtsmeldungen: ${offeneKuehe.map((k) => k.kuhId).join(", ")}.`,
    );
  }
  if (teile.length === 0) {
    if (datenlage.aktuell) {
      teile.push(
        `keine offenen Alarme in den letzten ${stunden} h. Analyse läuft, letztes Lebenszeichen ${uhr(datenlage.lebenszeichen!.zeit)}.`,
      );
    } else {
      teile.push(`${datenlage.grund}. Keine Aussage über die Tiere möglich.`);
    }
    // Bereits gesehene Austreibung trotzdem nennen — sie ist der Kontext.
    const gesehen = massgeblich(kameraAlarme);
    if (gesehen) teile.push(`Zuletzt: ${alarmZeile(gesehen, uhr)}.`);
  } else if (!datenlage.aktuell) {
    teile.push(`Achtung: ${datenlage.grund}.`);
  }
  return `${name}: ${stufe} – ${teile.join(" ")}`;
}

/** "HH:MM" in Ortszeit, aeltere Tage mit Datum davor ("13.10. 22:14"). */
function uhrzeitFormat(
  zeitzone: string | undefined,
  jetzt: number,
): (iso: string) => string {
  const zone = zeitzone?.trim() || "Europe/Berlin";
  const formatierer = (() => {
    const opts: Intl.DateTimeFormatOptions = {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    };
    try {
      return new Intl.DateTimeFormat("de-DE", { ...opts, timeZone: zone });
    } catch {
      // Unbekannte Zeitzone darf die Statusabfrage nicht sprengen.
      return new Intl.DateTimeFormat("de-DE", { ...opts, timeZone: "UTC" });
    }
  })();
  const teile = (t: number) => {
    const p = formatierer.formatToParts(new Date(t));
    const f = (typ: string) => p.find((x) => x.type === typ)?.value ?? "";
    return { tag: `${f("day")}.${f("month")}.`, zeit: `${f("hour").padStart(2, "0").replace(/^24/, "00")}:${f("minute")}` };
  };
  const heute = teile(jetzt).tag;
  return (iso: string) => {
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "unbekannt";
    const { tag, zeit } = teile(t);
    return tag === heute ? zeit : `${tag} ${zeit}`;
  };
}
