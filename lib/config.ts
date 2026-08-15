/**
 * Zentrale Konfiguration von Stallblick.
 *
 * Alle Kameras laufen ueber die **Tuya-Cloud**: Die Kamera schickt ihr Bild
 * selbst in Tuyas Cloud, und der Server holt sich pro Zugriff eine
 * kurzlebige HLS-URL (siehe lib/tuya.ts und app/api/<kamera>/stream). Damit
 * braucht es weder ein Geraet im Stall noch eine Portfreigabe – die frueher
 * noetige Bridge (go2rtc/MediaMTX) entfaellt vollstaendig; ihre Konfiguration
 * liegt nur noch als Legacy unter /_archiv.
 *
 * Zugangsdaten liegen ausschliesslich serverseitig (TUYA_*, siehe
 * .env.example) – im Browser landet nur die fertige, kurzlebige Stream-URL.
 * Ist eine Kamera nicht konfiguriert, antwortet ihr Endpoint mit 503 und die
 * Kachel bleibt beim Wartehinweis.
 */

export type CameraId = "stallwache" | "futterwache" | "stallbox";
 * Bridge-Wahl (siehe /bridge/README.md fuer die Entscheidungshilfe):
 *   go2rtc   (Default) – eigene JSON-API fuer WebRTC, integriertes
 *            Snapshot-Endpoint. Guter Default, viele Kameraprotokolle.
 *   mediamtx – Standard-WHEP/WHIP fuer WebRTC, ein einzelnes Binary, sehr
 *              aktiv gepflegte Community. Kein eingebautes JPEG-Snapshot –
 *              die Vorschau greift dafuer kurzzeitig auf HLS zurueck.
 *
 * Umgebungsvariablen (siehe .env.example):
 *   NEXT_PUBLIC_BRIDGE_URL     Basis-URL der Bridge, z.B. https://stallwache.example.com
 *   NEXT_PUBLIC_GO2RTC_URL     Alt-Name (Alias), falls schon gesetzt
 *   NEXT_PUBLIC_BRIDGE_TYPE    "go2rtc" (Default) | "mediamtx"
 *   NEXT_PUBLIC_STREAM_NAME    Stream/Pfad der Stallwache  (Default: "stallwache")
 *   NEXT_PUBLIC_STREAM_NAME_2  Stream/Pfad der Futterwache (Default: "futterwache")
 *   NEXT_PUBLIC_STREAM_NAME_3  Stream/Pfad der Abkalbebox  (Default: "abkalbebox")
 *   NEXT_PUBLIC_STREAM_NAME_4  Stream/Pfad der Weidewache  (Default: "weidewache")
 *   NEXT_PUBLIC_STALLWACHE_TUYA  "1" = Hauptkamera ueber die Tuya-Cloud
 *                                (Betrieb ganz ohne Bridge moeglich)
 *
 * Die Abkalbebox hiess frueher "Stallbox"; die alten Variablennamen
 * (NEXT_PUBLIC_STALLBOX_TUYA, TUYA_DEVICE_ID_STALLBOX) gelten weiter als
 * Alias, damit bestehende Deployments nicht beim Umbenennen ausfallen.
 */

export type BridgeType = "go2rtc" | "mediamtx";

export const BRIDGE_TYPE: BridgeType =
  process.env.NEXT_PUBLIC_BRIDGE_TYPE?.trim().toLowerCase() === "mediamtx"
    ? "mediamtx"
    : "go2rtc";

/** Basis-URL der Bridge (Cloudflare-Tunnel), ohne abschliessenden Slash. */
export const BRIDGE_URL = (
  process.env.NEXT_PUBLIC_BRIDGE_URL?.trim() ||
  process.env.NEXT_PUBLIC_GO2RTC_URL?.trim() ||
  ""
).replace(/\/+$/, "");

/** Rueckwaertskompatibler Alias – frueherer Name der Bridge-Basis-URL. */
export const GO2RTC_URL = BRIDGE_URL;

export const isConfigured = BRIDGE_URL.length > 0;

/** MediaMTX hat kein eingebautes JPEG-Snapshot-Endpoint. */
export const snapshotSupported = BRIDGE_TYPE === "go2rtc";

export type CameraId =
  | "stallwache"
  | "futterwache"
  | "abkalbebox"
  | "weidewache";

/** Kamera-State laut State-Modell: online | offline | laedt | instabil */
export type CameraState = "online" | "offline" | "laedt" | "instabil";

export interface CameraConfig {
  id: CameraId;
  /** Anzeigename in der UI. */
  name: string;
  /** Reduzierte Metadaten fuer die Vorschau-Karte. */
  ort: string;
  /** API-Route, die serverseitig eine kurzlebige Tuya-HLS-URL fuer diese Kamera allokiert. */
  tuyaEndpoint: string;
}

/**
 * Die drei LSC-Kameras haengen in der Tuya-Cloud und laufen standardmaessig
 * darueber (mit Bridge-Fallback). Zum Erzwingen der Bridge die jeweilige
 * Variable auf 0 setzen.
 */
const FUTTERWACHE_TUYA = process.env.NEXT_PUBLIC_FUTTERWACHE_TUYA?.trim() !== "0";
const ABKALBEBOX_TUYA =
  (process.env.NEXT_PUBLIC_ABKALBEBOX_TUYA ?? process.env.NEXT_PUBLIC_STALLBOX_TUYA)
    ?.trim() !== "0";
const WEIDEWACHE_TUYA = process.env.NEXT_PUBLIC_WEIDEWACHE_TUYA?.trim() !== "0";

/**
 * Die Stallwache ist die Hauptkamera im Abkalbebereich und lief historisch nur
 * ueber die Bridge. Tuya ist deshalb hier bewusst **opt-in**: Ein Hof mit
 * bestehender Bridge behaelt sein Verhalten unveraendert (kein zusaetzlicher
 * Tuya-Versuch beim Verbindungsaufbau), waehrend ein Hof mit Tuya-Kamera die
 * komplette Kalbeueberwachung ganz ohne Bridge betreiben kann.
 *
 * Aktivieren: NEXT_PUBLIC_STALLWACHE_TUYA=1 (plus TUYA_DEVICE_ID_STALLWACHE
 * serverseitig). Ist zusaetzlich eine Bridge gesetzt, dient sie als Fallback.
 */
const STALLWACHE_TUYA = process.env.NEXT_PUBLIC_STALLWACHE_TUYA?.trim() === "1";

/** Stallwache = Hauptkamera (Default), weitere Kameras als Zweitkameras. */
export const CAMERAS: readonly CameraConfig[] = [
  {
    id: "stallwache",
    name: "Stallwache",
    ort: "Abkalbebereich",
    tuyaFaehig: STALLWACHE_TUYA,
    tuyaEndpoint: "/api/stallwache/stream",
  },
  {
    id: "futterwache",
    name: "Futterwache",
    ort: "Futtertisch",
    tuyaEndpoint: "/api/futterwache/stream",
  },
  {
    id: "stallbox",
    name: "Stallbox",
    ort: "Stallbox",
    tuyaEndpoint: "/api/stallbox/stream",
    id: "abkalbebox",
    name: "Abkalbebox",
    streamName: process.env.NEXT_PUBLIC_STREAM_NAME_3?.trim() || "abkalbebox",
    ort: "Abkalbebucht",
    tuyaFaehig: ABKALBEBOX_TUYA,
    tuyaEndpoint: "/api/abkalbebox/stream",
  },
  {
    id: "weidewache",
    name: "Weidewache",
    streamName: process.env.NEXT_PUBLIC_STREAM_NAME_4?.trim() || "weidewache",
    ort: "Weide",
    tuyaFaehig: WEIDEWACHE_TUYA,
    tuyaEndpoint: "/api/weidewache/stream",
  },
];

export function cameraById(id: CameraId): CameraConfig {
  return CAMERAS.find((c) => c.id === id) ?? CAMERAS[0];
}
