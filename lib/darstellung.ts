/**
 * Gemeinsame Darstellung der Ereignistypen.
 *
 * Farbe und Wortwahl eines Alarms muessen ueberall gleich sein — auf dem
 * Dashboard, in der Alarmliste, in der Benachrichtigung. Wer nachts um drei
 * auf ein rotes Feld schaut, soll ohne Nachdenken wissen, was es bedeutet.
 */

import type { EreignisTyp } from "@/lib/ereignis-modell";

export const TYP_LABEL: Record<EreignisTyp, string> = {
  kalbeverdacht: "Kalbeverdacht",
  austreibung: "Austreibung",
  brunstverdacht: "Brunstverdacht",
  info: "Info",
};

/** Kurzerklaerung fuer Filterknoepfe und Einstellungen. */
export const TYP_ERKLAERUNG: Record<EreignisTyp, string> = {
  kalbeverdacht: "Schwanzwinkel über längere Zeit erhöht",
  austreibung: "Fruchtblase oder Kälberfüße sichtbar – sofort nachsehen",
  brunstverdacht: "Aufsprung- oder Duldungsverhalten",
  info: "Statusmeldungen des Edge-Agenten",
};

export const TYP_BADGE: Record<EreignisTyp, string> = {
  kalbeverdacht: "bg-amber-500/20 text-amber-300 ring-amber-400/30",
  austreibung: "bg-red-500/25 text-red-300 ring-red-400/40",
  brunstverdacht: "bg-sky-500/20 text-sky-300 ring-sky-400/30",
  info: "bg-white/10 text-white/60 ring-white/15",
};

/** Randfarbe der Alarmkarte – traegt die Dringlichkeit ohne Text. */
export const TYP_RAND: Record<EreignisTyp, string> = {
  kalbeverdacht: "border-l-amber-400",
  austreibung: "border-l-red-500",
  brunstverdacht: "border-l-sky-400",
  info: "border-l-white/20",
};

/** Uhrzeit heute, sonst Datum + Uhrzeit. */
export function fmtZeit(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const heute = new Date().toDateString() === d.toDateString();
  const uhr = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  return heute
    ? uhr
    : `${d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })} ${uhr}`;
}

/** „vor 12 min" – im Stall die wichtigere Angabe als die Uhrzeit. */
export function fmtRelativ(iso: string, bezug = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const min = Math.round((bezug - t) / 60_000);
  if (min < 1) return "gerade eben";
  if (min < 60) return `vor ${min} min`;
  const std = Math.round(min / 60);
  if (std < 24) return `vor ${std} h`;
  return `vor ${Math.round(std / 24)} Tagen`;
}
