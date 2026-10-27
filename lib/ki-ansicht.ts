/**
 * KI-Kaesten auf dem Livebild der Stallwache
 * (docs/ki-ansicht-spezifikation.md).
 *
 * Der Edge-Agent schreibt je Analyse (etwa 1/s) die Kaesten als kleine
 * JSON-Datei; die Kachel holt sie ueber den Fernzugriff und legt sie ueber
 * das laufende Video. Das Video (HLS) laeuft einige Sekunden hinter der
 * Wirklichkeit her, die Analyse fast nicht. Deshalb puffert die Kachel die
 * letzten Erkennungen und zeigt die, deren Zeit zum gerade gezeigten
 * Videobild passt: neueste Zeit minus Versatz des Videos. Gerechnet wird
 * nur mit Zeiten des Stall-Rechners untereinander, eine falsch gehende Uhr
 * am Handy stoert also nicht.
 *
 * Ob die Erkennungen aktuell sind, entscheidet die Kachel daran, ob sich
 * die neueste Zeit weiterbewegt (Handy-Uhr). Der Proxy am Stall prueft
 * zusaetzlich selbst (Dateizeit, 10 s).
 *
 * Reine Funktionen ohne Framework-Importe, damit `npm test` sie ohne Build
 * pruefen kann.
 */

/** Pfad in dieser App (lib/fern.ts: FERN_PRAEFIX + KI_ANSICHT_PFAD). */
export const KI_KAESTEN_URL = "/api/stallwache/fern/ki-kaesten";

/** Abruftakt: wie die Analyse. Eine Antwort hat wenige hundert Bytes. */
export const KI_TAKT_MS = 1_000;
/** Neueste Zeit steht laenger still -> „nicht aktuell". */
export const KI_FRISCH_MS = 10_000;
/** So viele Sekunden Erkennungen haelt der Puffer (deckt den HLS-Versatz). */
export const KI_PUFFER_S = 30;
/** Weg vom Ende der HLS-Playlist bis zur Wirklichkeit (Segment, go2rtc,
 *  Proxy). Schaetzwert, am Geraet zu pruefen (Spezifikation §6). */
export const KI_ZUSCHLAG_S = 1.5;
/** Hoechstens so viele Sekunden darf eine Erkennung vor dem gezeigten
 *  Moment liegen (Analyse alle 1–3 s, Kuehe in der Box bewegen sich kaum). */
export const KI_LUECKE_S = 3;

export interface KiKuh {
  id: number;
  box: [number, number, number, number];
  winkel: number | null;
}

export interface KiObjekt {
  klasse: string;
  box: [number, number, number, number];
  prozent: number;
  alarm: boolean;
}

export interface KiBild {
  zeit: number;
  breite: number;
  hoehe: number;
  alarmAb: number;
  kuehe: KiKuh[];
  objekte: KiObjekt[];
}

const istZahl = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);

function leseBox(x: unknown): [number, number, number, number] | null {
  if (!Array.isArray(x) || x.length !== 4 || !x.every((v) => istZahl(v) && v >= 0 && v <= 1)) {
    return null;
  }
  const [x1, y1, x2, y2] = x as number[];
  return x2 >= x1 && y2 >= y1 ? [x1, y1, x2, y2] : null;
}

/**
 * Prueft die Antwort des Stall-Rechners streng; null bei allem, was nicht
 * passt. Die Daten kommen aus dem Stall-LAN und landen im DOM – Text wird
 * nie aus ihnen uebernommen, nur Zahlen und bekannte Klassen.
 */
export function leseKiBild(json: unknown): KiBild | null {
  if (!json || typeof json !== "object") return null;
  const d = json as Record<string, unknown>;
  if (d.v !== 1 || !istZahl(d.zeit) || !istZahl(d.breite) || !istZahl(d.hoehe)) return null;
  if (d.breite <= 0 || d.hoehe <= 0 || !istZahl(d.alarm_ab)) return null;
  if (!Array.isArray(d.kuehe) || !Array.isArray(d.objekte)) return null;
  if (d.kuehe.length > 200 || d.objekte.length > 200) return null;
  const kuehe: KiKuh[] = [];
  for (const k of d.kuehe) {
    const kk = k as Record<string, unknown>;
    const box = leseBox(kk?.box);
    if (!box || !Number.isInteger(kk.id) || (kk.id as number) < 0) return null;
    if (kk.winkel !== null && !istZahl(kk.winkel)) return null;
    kuehe.push({ id: kk.id as number, box, winkel: kk.winkel as number | null });
  }
  const objekte: KiObjekt[] = [];
  for (const o of d.objekte) {
    const oo = o as Record<string, unknown>;
    const box = leseBox(oo?.box);
    if (!box || !(oo.klasse === "amniotic_sac" || oo.klasse === "calf_legs")) return null;
    if (!Number.isInteger(oo.prozent) || typeof oo.alarm !== "boolean") return null;
    objekte.push({ klasse: oo.klasse, box, prozent: oo.prozent as number, alarm: oo.alarm });
  }
  return { zeit: d.zeit, breite: d.breite, hoehe: d.hoehe, alarmAb: d.alarm_ab, kuehe, objekte };
}

/** Fuegt ein Bild in den Puffer ein (nach Zeit sortiert, ohne Doppel) und
 *  wirft alles weg, was mehr als KI_PUFFER_S hinter dem neuesten liegt. */
export function puffere(puffer: KiBild[], bild: KiBild): KiBild[] {
  if (puffer.some((b) => b.zeit === bild.zeit)) return puffer;
  const neu = [...puffer, bild].sort((a, b) => a.zeit - b.zeit);
  const grenze = neu[neu.length - 1].zeit - KI_PUFFER_S;
  return neu.filter((b) => b.zeit >= grenze);
}

/**
 * Das Bild, das zum gerade gezeigten Videobild passt: das juengste mit
 * zeit <= neueste Zeit − Versatz. null, wenn der Puffer nicht so weit
 * zurueckreicht (dann lieber keine Kaesten als falsche).
 */
export function waehleBild(puffer: KiBild[], versatzS: number): KiBild | null {
  if (!puffer.length) return null;
  const ziel = puffer[puffer.length - 1].zeit - Math.max(0, versatzS);
  let wahl: KiBild | null = null;
  for (const b of puffer) if (b.zeit <= ziel + 0.05) wahl = b;
  // Mehr als KI_LUECKE_S vor dem Ziel: Der Agent hat in der Zeit nichts
  // geliefert (Luecke im Puffer) – kein passendes Bild.
  return wahl && ziel - wahl.zeit <= KI_LUECKE_S ? wahl : null;
}

/**
 * Versatz des Videos in Sekunden: Abstand der Wiedergabe zum Ende der
 * HLS-Playlist plus Zuschlag. `seekableEnde` null = unbekannt.
 */
export function videoVersatzS(seekableEnde: number | null, aktuell: number): number {
  const rueckstand =
    seekableEnde !== null && Number.isFinite(seekableEnde) ? Math.max(0, seekableEnde - aktuell) : 0;
  return rueckstand + KI_ZUSCHLAG_S;
}

/**
 * Versatz fuer waehleBild zwischen zwei Abrufen: Seit die neueste
 * Erkennung ankam (`seit`, Handy-Uhr), ist die Zeit am Stall weitergelaufen,
 * das gezeigte Videobild also naeher an die neueste Erkennung gerueckt.
 */
export function wirksamerVersatzS(versatzS: number, seit: number | null, jetzt: number): number {
  const vergangen = seit === null ? 0 : Math.max(0, (jetzt - seit) / 1000);
  return Math.max(0, versatzS - vergangen);
}

/** Sichtbarer Bildbereich eines Videos mit object-fit: contain. */
export function videoRechteck(
  cw: number,
  ch: number,
  vw: number,
  vh: number,
): { x: number; y: number; w: number; h: number } | null {
  if (cw <= 0 || ch <= 0 || vw <= 0 || vh <= 0) return null;
  const f = Math.min(cw / vw, ch / vh);
  const w = vw * f;
  const h = vh * f;
  return { x: (cw - w) / 2, y: (ch - h) / 2, w, h };
}

/** Weichen Seitenverhaeltnis der Analyse und des Livebilds ab (> 3 %)? */
export function seitenAbweichung(bild: KiBild, vw: number, vh: number): boolean {
  if (vw <= 0 || vh <= 0) return false;
  return Math.abs(bild.breite / bild.hoehe / (vw / vh) - 1) > 0.03;
}

export type KiArt = "kuh" | "alarm" | "unter";

export interface KiKasten {
  art: KiArt;
  text: string;
  box: [number, number, number, number];
}

const NAMEN: Record<string, string> = { amniotic_sac: "Fruchtblase", calf_legs: "Kälberfüße" };

/** Kaesten mit Beschriftung (Befund ki-wache: rot nur mit Alarm). */
export function kaesten(bild: KiBild): KiKasten[] {
  const out: KiKasten[] = bild.kuehe.map((k) => ({
    art: "kuh",
    text: `Kuh #${k.id}${k.winkel !== null ? ` · ${Math.round(k.winkel)}°` : ""}`,
    box: k.box,
  }));
  for (const o of bild.objekte) {
    const name = NAMEN[o.klasse];
    out.push(
      o.alarm
        ? { art: "alarm", text: `${name} ${o.prozent} % ALARM`, box: o.box }
        : {
            art: "unter",
            text: `${name}? ${o.prozent} % (Alarm ab ${Math.round(bild.alarmAb * 100)} %)`,
            box: o.box,
          },
    );
  }
  return out;
}

export type KiZustand = "laedt" | "bild" | "alt" | "aus" | "anmelden" | "gestoert";

export interface KiStand {
  zustand: KiZustand;
  /** Neueste Zeit (Stall-Rechner) im Puffer. */
  neueste: number | null;
  /** Handy-Zeit (ms), zu der sich die neueste Zeit zuletzt bewegt hat. */
  seit: number | null;
}

export const KI_START: KiStand = { zustand: "laedt", neueste: null, seit: null };

/**
 * Naechster Zustand nach einem Abruf. `status` null = Netzfehler; `zeit`
 * null bei 200 = Antwort unbrauchbar. 404 heisst am Stall „keine aktuellen
 * Erkennungen": Gab es schon welche, sind sie jetzt „nicht aktuell".
 */
export function naechsterKiStand(
  alt: KiStand,
  status: number | null,
  zeit: number | null,
  jetzt: number,
): KiStand {
  if (status === 200 && zeit !== null) {
    const neu = alt.neueste === null || zeit > alt.neueste;
    const neueste = neu ? zeit : alt.neueste;
    const seit = neu || alt.seit === null ? jetzt : alt.seit;
    return { zustand: jetzt - seit > KI_FRISCH_MS ? "alt" : "bild", neueste, seit };
  }
  if (status === 404) return { ...alt, zustand: alt.neueste === null ? "aus" : "alt" };
  if (status === 401) return { ...alt, zustand: "anmelden" };
  return { ...alt, zustand: "gestoert" };
}

/** Text der Statuszeile; `uhr` formatiert Unix-Sekunden als Uhrzeit. */
export function kiText(
  stand: KiStand,
  uhr: (sekunden: number) => string,
  info: { videoLaeuft: boolean; kuehe: number; versatzS: number; passend: boolean; schief: boolean },
): string {
  switch (stand.zustand) {
    case "laedt":
      return "KI-Kästen laden …";
    case "bild":
      if (!info.videoLaeuft) return "KI-Kästen erscheinen, sobald das Livebild läuft.";
      if (!info.passend) return "KI-Kästen: keine Erkennung zum gezeigten Moment.";
      if (info.schief) {
        return "KI-Kästen ausgeblendet – Analysebild und Livebild haben verschiedene Seitenverhältnisse.";
      }
      // Kurz (eine Zeile am Handy): Die Leiste liegt ueber dem Bild.
      return `KI · ${info.kuehe} ${info.kuehe === 1 ? "Kuh" : "Kühe"} · Versatz ≈ ${Math.round(
        info.versatzS,
      )} s · Nr. von der KI, nicht Ohrmarke`;
    case "alt":
      return `KI-Kästen nicht aktuell – letzte Erkennung ${
        stand.neueste !== null ? uhr(stand.neueste) : "–"
      }.`;
    case "aus":
      return (
        "Keine KI-Kästen – vom Stall-Rechner kommen gerade keine Erkennungen " +
        "(z. B. noch kein Modell, Agent aus, Kamera ohne Bild oder dort nicht eingerichtet)."
      );
    case "anmelden":
      return "KI-Kästen nicht erreichbar – bitte neu anmelden.";
    case "gestoert":
      return "KI-Kästen nicht erreichbar – Fernzugriff zum Stall gestört.";
  }
}
