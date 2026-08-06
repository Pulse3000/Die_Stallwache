/**
 * Tuya-Cloud-Anbindung fuer Kameras und IoT-Geraete (serverseitig!).
 *
 * Mehrere Geraete koennen ueber dasselbe Tuya-Cloud-Projekt laufen (ein
 * Access ID/Secret-Paar), aber jedes mit seiner eigenen Geraete-ID. Die
 * Tuya-OpenAPI liefert auf Anfrage eine kurzlebige HLS-Stream-URL (Kameras)
 * bzw. Status und Steuerbefehle (Traenken, Licht, Sensoren). Alle
 * Zugangsdaten bleiben in Server-Env-Vars – nie im Browser.
 *
 * Benoetigte Umgebungsvariablen (Vercel -> Settings -> Environment Variables):
 *   TUYA_ACCESS_ID              Access ID / Client ID  (iot.tuya.com -> Cloud -> Projekt)
 *   TUYA_ACCESS_SECRET          Access Secret          (ebenda)
 *   TUYA_DEVICE_ID_FUTTERWACHE  Geraete-ID der Futterwache (Projekt -> Devices)
 *   TUYA_DEVICE_ID_STALLBOX     Geraete-ID der Stallbox    (Projekt -> Devices)
 *   TUYA_GERAETE                steuerbare Geraete, siehe `geraeteKatalog()`
 *   TUYA_API_BASE               optional, Default EU: https://openapi.tuyaeu.com
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

export type TuyaKameraId = "futterwache" | "stallbox";

const DEVICE_IDS: Record<TuyaKameraId, string> = {
  futterwache: process.env.TUYA_DEVICE_ID_FUTTERWACHE?.trim() || "",
  stallbox: process.env.TUYA_DEVICE_ID_STALLBOX?.trim() || "",
};

export function tuyaKonfiguriert(kamera: TuyaKameraId): boolean {
  return ACCESS_ID.length > 0 && ACCESS_SECRET.length > 0 && DEVICE_IDS[kamera].length > 0;
}

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

// Token pro Serverless-Instanz cachen (Tuya-Tokens gelten ~2 h). Gilt
// projektweit (nicht pro Geraet), daher ein gemeinsamer Cache.
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

/** Fordert bei Tuya eine kurzlebige Stream-URL fuer die angegebene Kamera an. */
export async function holeTuyaStream(
  kamera: TuyaKameraId,
  typ: "hls" | "rtsp" = "hls",
): Promise<{ url: string; typ: string }> {
  const token = await holeToken();
  const r = await tuyaRequest<{ url: string }>(
    "POST",
    `/v1.0/devices/${encodeURIComponent(DEVICE_IDS[kamera])}/stream/actions/allocate`,
    JSON.stringify({ type: typ }),
    token,
  );
  return { url: r.url, typ };
}

// ---------------------------------------------------------------------------
// Steuerbare Tuya-Geraete (Traenken, Licht, Sensoren)
// ---------------------------------------------------------------------------

export type GeraeteArt = "traenke" | "licht" | "sensor" | "kamera" | "sonstiges";

export interface TuyaGeraet {
  /** Tuya-Geraete-ID. */
  id: string;
  /** Anzeigename in der Steuerung. */
  name: string;
  art: GeraeteArt;
}

const ARTEN: readonly GeraeteArt[] = [
  "traenke",
  "licht",
  "sensor",
  "kamera",
  "sonstiges",
];

/**
 * Katalog der steuerbaren Geraete – zugleich die **Allowlist**.
 *
 * Ein Tuya-Cloud-Projekt enthaelt oft mehr als den Stall (Privatgeraete des
 * Betriebsleiters, Nachbarhof im selben Konto). Die App steuert deshalb
 * ausschliesslich, was hier ausdruecklich eingetragen ist; eine beliebige
 * Geraete-ID aus dem Request wird nie durchgereicht.
 *
 * Format von TUYA_GERAETE (kommagetrennt, Felder mit Doppelpunkt):
 *   <geraete-id>:<Anzeigename>:<art>
 * Beispiel:
 *   TUYA_GERAETE=bf1a..:Tränke Bucht 1:traenke,bf2b..:Stalllicht:licht
 * Die Art ist optional (Default "sonstiges") und steuert nur das Symbol.
 */
export function geraeteKatalog(): TuyaGeraet[] {
  const roh = process.env.TUYA_GERAETE?.trim() || "";
  const geraete: TuyaGeraet[] = [];

  for (const eintrag of roh.split(",")) {
    const teile = eintrag.split(":").map((t) => t.trim());
    const id = teile[0] ?? "";
    if (!id) continue;
    const art = (teile[2] ?? "").toLowerCase() as GeraeteArt;
    geraete.push({
      id,
      name: teile[1] || id,
      art: ARTEN.includes(art) ? art : "sonstiges",
    });
  }

  // Die Kameras sind ohnehin schon konfiguriert – ihr Online-Status gehoert
  // mit in die Steuerungsuebersicht, damit der Landwirt einen Ort hat.
  for (const [kamera, name] of [
    ["futterwache", "Futterwache"],
    ["stallbox", "Stallbox"],
  ] as const) {
    const id = DEVICE_IDS[kamera];
    if (id && !geraete.some((g) => g.id === id)) {
      geraete.push({ id, name, art: "kamera" });
    }
  }
  return geraete;
}

/** Grundzugang zur Tuya-Cloud vorhanden (unabhaengig von einzelnen Geraeten)? */
export function tuyaGrundkonfiguriert(): boolean {
  return ACCESS_ID.length > 0 && ACCESS_SECRET.length > 0;
}

/** Findet ein Geraet in der Allowlist; null wenn nicht freigegeben. */
export function geraetAusKatalog(id: string): TuyaGeraet | null {
  return geraeteKatalog().find((g) => g.id === id) ?? null;
}

/** Ein Statuspunkt („data point") eines Geraets. */
export interface StatusPunkt {
  code: string;
  value: string | number | boolean;
}

/** Eine steuerbare Funktion laut Tuya-Geraetemodell. */
export interface Funktion {
  code: string;
  name?: string;
  type: string;
  /** JSON-String mit Wertebereich, z.B. {"min":0,"max":100}. */
  values?: string;
}

export interface GeraeteZustand {
  id: string;
  name: string;
  art: GeraeteArt;
  online: boolean;
  status: StatusPunkt[];
  funktionen: Funktion[];
  /** Gesetzt, wenn Tuya fuer dieses Geraet nicht antworten konnte. */
  fehler?: string;
}

/**
 * Liest Online-Zustand, Statuspunkte und steuerbare Funktionen eines Geraets.
 *
 * Ein Ausfall einzelner Geraete (Funkloch im Stall, Geraet abgesteckt) darf
 * die Uebersicht nicht leeren – deshalb wird der Fehler am Geraet vermerkt
 * statt geworfen.
 */
export async function holeGeraeteZustand(
  geraet: TuyaGeraet,
): Promise<GeraeteZustand> {
  const basis = { id: geraet.id, name: geraet.name, art: geraet.art };
  try {
    const token = await holeToken();
    const pfad = `/v1.0/iot-03/devices/${encodeURIComponent(geraet.id)}`;
    const [info, funktionen] = await Promise.all([
      tuyaRequest<{ online: boolean; name?: string; status?: StatusPunkt[] }>(
        "GET",
        pfad,
        undefined,
        token,
      ),
      // Sensoren haben keine steuerbaren Funktionen -> leere Liste statt Fehler.
      tuyaRequest<{ functions?: Funktion[] }>(
        "GET",
        `${pfad}/functions`,
        undefined,
        token,
      ).catch(() => ({ functions: [] as Funktion[] })),
    ]);
    return {
      ...basis,
      online: Boolean(info.online),
      status: info.status ?? [],
      funktionen: funktionen.functions ?? [],
    };
  } catch (e) {
    return {
      ...basis,
      online: false,
      status: [],
      funktionen: [],
      fehler: e instanceof Error ? e.message : "Tuya-Anfrage fehlgeschlagen",
    };
  }
}

/** Zustand aller freigegebenen Geraete (parallel, fehlertolerant). */
export async function holeAlleGeraete(): Promise<GeraeteZustand[]> {
  return Promise.all(geraeteKatalog().map(holeGeraeteZustand));
}

/**
 * Schickt einen Steuerbefehl an ein Geraet.
 *
 * Der Aufrufer muss die Geraete-ID vorher gegen `geraetAusKatalog()` geprueft
 * haben; `code` wird zusaetzlich gegen die vom Geraet gemeldeten Funktionen
 * validiert, damit kein beliebiger Datenpunkt beschrieben werden kann.
 */
export async function sendeBefehl(
  geraeteId: string,
  code: string,
  value: string | number | boolean,
): Promise<void> {
  const token = await holeToken();
  await tuyaRequest<boolean>(
    "POST",
    `/v1.0/iot-03/devices/${encodeURIComponent(geraeteId)}/commands`,
    JSON.stringify({ commands: [{ code, value }] }),
    token,
  );
}
