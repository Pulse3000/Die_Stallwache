/**
 * Tuya-Cloud-Anbindung fuer die Futterwache (serverseitig!).
 *
 * Die Futterwache ist eine Tuya-/Smart-Life-Kamera. Die Tuya-OpenAPI liefert
 * auf Anfrage eine kurzlebige HLS-Stream-URL, die ans Frontend durchgereicht
 * werden kann. Alle Zugangsdaten bleiben in Server-Env-Vars – nie im Browser.
 *
 * Benoetigte Umgebungsvariablen (Vercel -> Settings -> Environment Variables):
 *   TUYA_ACCESS_ID      Access ID / Client ID  (iot.tuya.com -> Cloud -> Projekt)
 *   TUYA_ACCESS_SECRET  Access Secret          (ebenda)
 *   TUYA_DEVICE_ID      Device ID der Futterwache (Projekt -> Devices)
 *   TUYA_API_BASE       optional, Default EU: https://openapi.tuyaeu.com
 *
 * Signierung gemaess Tuya-Doku: HMAC-SHA256 ueber
 *   client_id [+ access_token] + t + stringToSign
 * mit stringToSign = METHOD \n sha256(body) \n \n pfad
 */

import { createHash, createHmac } from "node:crypto";

const BASE = (process.env.TUYA_API_BASE?.trim() || "https://openapi.tuyaeu.com")
  .replace(/\/+$/, "");
const ACCESS_ID = process.env.TUYA_ACCESS_ID?.trim() || "";
const ACCESS_SECRET = process.env.TUYA_ACCESS_SECRET?.trim() || "";
const DEVICE_ID = process.env.TUYA_DEVICE_ID?.trim() || "";

export const tuyaKonfiguriert =
  ACCESS_ID.length > 0 && ACCESS_SECRET.length > 0 && DEVICE_ID.length > 0;

function sha256Hex(s: string): string {
  return createHash("sha256").update(s).digest("hex");
}

function hmacUpper(s: string): string {
  return createHmac("sha256", ACCESS_SECRET).update(s).digest("hex").toUpperCase();
}

interface TuyaAntwort<T> {
  success: boolean;
  code?: number;
  msg?: string;
  result: T;
}

async function tuyaRequest<T>(
  method: "GET" | "POST",
  pfad: string,
  body?: string,
  accessToken?: string,
): Promise<T> {
  const t = Date.now().toString();
  const stringToSign = [method, sha256Hex(body ?? ""), "", pfad].join("\n");
  const signatur = hmacUpper(ACCESS_ID + (accessToken ?? "") + t + stringToSign);

  const res = await fetch(`${BASE}${pfad}`, {
    method,
    headers: {
      client_id: ACCESS_ID,
      t,
      sign_method: "HMAC-SHA256",
      sign: signatur,
      ...(accessToken ? { access_token: accessToken } : {}),
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body,
    cache: "no-store",
  });
  const json = (await res.json()) as TuyaAntwort<T>;
  if (!json.success) {
    throw new Error(`Tuya-API-Fehler ${json.code ?? res.status}: ${json.msg ?? "unbekannt"}`);
  }
  return json.result;
}

// Token pro Serverless-Instanz cachen (Tuya-Tokens gelten ~2 h).
let tokenCache: { token: string; ablauf: number } | null = null;

async function holeToken(): Promise<string> {
  if (tokenCache && Date.now() < tokenCache.ablauf) return tokenCache.token;
  const r = await tuyaRequest<{ access_token: string; expire_time: number }>(
    "GET",
    "/v1.0/token?grant_type=1",
  );
  tokenCache = {
    token: r.access_token,
    ablauf: Date.now() + Math.max(60, r.expire_time - 60) * 1000,
  };
  return tokenCache.token;
}

/** Fordert bei Tuya eine kurzlebige Stream-URL der Futterwache an. */
export async function holeFutterwacheStream(
  typ: "hls" | "rtsp" = "hls",
): Promise<{ url: string; typ: string }> {
  const token = await holeToken();
  const r = await tuyaRequest<{ url: string }>(
    "POST",
    `/v1.0/devices/${encodeURIComponent(DEVICE_ID)}/stream/actions/allocate`,
    JSON.stringify({ type: typ }),
    token,
  );
  return { url: r.url, typ };
}
