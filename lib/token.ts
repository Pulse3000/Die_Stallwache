/**
 * Zeitkonstanter Vergleich von Zugangs-Tokens (Ingest, Statusabfrage).
 *
 * `a !== b` bricht beim ersten abweichenden Zeichen ab — die Antwortzeit
 * verraet dann, wie viele Zeichen am Anfang stimmen. Beide Seiten werden
 * deshalb erst gehasht (gleiche Laenge) und dann mit `timingSafeEqual`
 * verglichen. Nur fuer die Node-Runtime (node:crypto); die Middleware auf
 * dem Edge-Runtime hat ihren eigenen Vergleich in lib/auth.ts.
 */

import { createHash, timingSafeEqual } from "node:crypto";

const hash = (s: string) => createHash("sha256").update(s, "utf8").digest();

/** true, wenn `gegeben` exakt dem konfigurierten `soll` entspricht. */
export function tokenGleich(gegeben: string | null | undefined, soll: string): boolean {
  if (!soll || typeof gegeben !== "string") return false;
  return timingSafeEqual(hash(gegeben), hash(soll));
}
