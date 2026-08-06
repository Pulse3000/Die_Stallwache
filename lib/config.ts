/**
 * Zentrale Konfiguration von Stallblick.
 *
 * Kameras liefern lokal RTSP-Streams. Im Stall-Netz laeuft eine Bridge
 * (go2rtc ODER MediaMTX, siehe /bridge), die via Cloudflare Tunnel
 * oeffentlich per HTTPS erreichbar ist. Die App spricht ausschliesslich mit
 * der Bridge – niemals direkt mit den Kameras, ohne Zugangsdaten im Frontend.
 * Tuya-faehige Kameras (siehe CameraConfig.tuyaFaehig) laufen stattdessen
 * primaer ueber die Tuya-Cloud, mit der Bridge nur als Fallback.
 *
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
  /** Name des Streams (go2rtc) bzw. Pfads (MediaMTX). */
  streamName: string;
  /** Reduzierte Metadaten fuer die Vorschau-Karte. */
  ort: string;
  /**
   * Kann diese Kamera als Hauptbild ueber die Tuya-Cloud laufen?
   * Wenn true, holt der Player zuerst eine HLS-URL von `tuyaEndpoint`
   * und faellt bei 503/Fehler automatisch auf die Bridge zurueck.
   */
  tuyaFaehig: boolean;
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

/** Stallwache = Hauptkamera (Default), weitere Kameras als Zweitkameras. */
export const CAMERAS: readonly CameraConfig[] = [
  {
    id: "stallwache",
    name: "Stallwache",
    streamName: process.env.NEXT_PUBLIC_STREAM_NAME?.trim() || "stallwache",
    ort: "Abkalbebereich",
    tuyaFaehig: false,
    tuyaEndpoint: "",
  },
  {
    id: "futterwache",
    name: "Futterwache",
    streamName: process.env.NEXT_PUBLIC_STREAM_NAME_2?.trim() || "futterwache",
    ort: "Futtertisch",
    tuyaFaehig: FUTTERWACHE_TUYA,
    tuyaEndpoint: "/api/futterwache/stream",
  },
  {
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

/**
 * WebRTC-Signaling-Endpoint der Bridge (niedrige Latenz, nur Hauptkamera).
 * go2rtc:   eigene JSON-API (POST { type, sdp } -> { type, sdp })
 * MediaMTX: WHEP-Standard (POST rohes SDP -> rohes SDP, Content-Type application/sdp)
 */
export function webrtcUrl(streamName: string): string {
  return BRIDGE_TYPE === "mediamtx"
    ? `${BRIDGE_URL}/${encodeURIComponent(streamName)}/whep`
    : `${BRIDGE_URL}/api/webrtc?src=${encodeURIComponent(streamName)}`;
}

/** HLS-Playlist der Bridge (robuster Fallback fuer die Hauptkamera). */
export function hlsUrl(streamName: string): string {
  return BRIDGE_TYPE === "mediamtx"
    ? `${BRIDGE_URL}/${encodeURIComponent(streamName)}/index.m3u8`
    : `${BRIDGE_URL}/api/stream.m3u8?src=${encodeURIComponent(streamName)}`;
}

/**
 * Einzelbild (Snapshot) – Grundlage der ressourcenschonenden Vorschau.
 * Nur bei go2rtc verfuegbar; bei MediaMTX siehe `snapshotSupported`.
 */
export function snapshotUrl(streamName: string): string {
  return `${BRIDGE_URL}/api/frame.jpeg?src=${encodeURIComponent(streamName)}`;
}
