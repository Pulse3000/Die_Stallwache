/**
 * Passwortschutz fuer Stallblick (ein gemeinsames Passwort, keine Datenbank).
 *
 * Aktiv nur, wenn STALLBLICK_PASSWORT gesetzt ist – ohne die Variable bleibt
 * die App offen (kein Aussperren bestehender Deployments). Setzen des
 * Passworts in Vercel aktiviert den Schutz.
 *
 * Nach erfolgreicher Anmeldung wird ein HMAC-signiertes Session-Cookie
 * gesetzt (kein Passwort im Cookie, nur Ablaufzeit + Signatur). Verifikation
 * laeuft in der Middleware auf dem Edge-Runtime, daher Web Crypto statt
 * node:crypto.
 *
 * Umgebungsvariablen (nur serverseitig, NIE NEXT_PUBLIC_*):
 *   STALLBLICK_PASSWORT      aktiviert den Schutz; das gemeinsame Passwort
 *   STALLBLICK_AUTH_SECRET   optionaler Signaturschluessel (Default: Passwort)
 */

export const SESSION_COOKIE = "stallblick_session";
/** Gueltigkeitsdauer eines Logins in Sekunden (7 Tage). */
export const SESSION_MAX_AGE = 7 * 24 * 60 * 60;

function passwort(): string {
  return process.env.STALLBLICK_PASSWORT?.trim() || "";
}

/** Schutz ist aktiv, sobald ein Passwort konfiguriert ist. */
export function authAktiv(): boolean {
  return passwort().length > 0;
}

function signaturSchluessel(): string {
  return process.env.STALLBLICK_AUTH_SECRET?.trim() || passwort();
}

function base64url(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmac(nachricht: string): Promise<string> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(signaturSchluessel()),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(nachricht));
  return base64url(new Uint8Array(sig));
}

/** Laengensicherer, zeitkonstanter Stringvergleich. */
function sicherGleich(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

/** Prueft die Passworteingabe gegen das konfigurierte Passwort. */
export function pruefePasswort(eingabe: string): boolean {
  const soll = passwort();
  return soll.length > 0 && sicherGleich(eingabe, soll);
}

/** Erstellt ein signiertes Session-Token: "<ablauf>.<signatur>". */
export async function erstelleToken(): Promise<string> {
  const ablauf = Math.floor(Date.now() / 1000) + SESSION_MAX_AGE;
  const sig = await hmac(String(ablauf));
  return `${ablauf}.${sig}`;
}

/** Verifiziert Signatur und Ablaufzeit eines Session-Tokens. */
export async function pruefeToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const punkt = token.indexOf(".");
  if (punkt <= 0) return false;
  const ablaufStr = token.slice(0, punkt);
  const sig = token.slice(punkt + 1);
  const ablauf = Number(ablaufStr);
  if (!Number.isInteger(ablauf) || ablauf < Math.floor(Date.now() / 1000)) {
    return false;
  }
  const erwartet = await hmac(ablaufStr);
  return sicherGleich(sig, erwartet);
}
