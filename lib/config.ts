/**
 * Zentrale Konfiguration von Stallblick.
 *
 * Beide Kameras liefern nur lokal RTSP-Streams. Im Stall-Netz laeuft eine
 * go2rtc-Bridge (siehe /bridge), die via Cloudflare Tunnel oeffentlich per
 * HTTPS erreichbar ist. Die App spricht ausschliesslich mit go2rtc –
 * niemals direkt mit den Kameras, ohne Zugangsdaten im Frontend.
 *
 * Umgebungsvariablen (siehe .env.example):
 *   NEXT_PUBLIC_GO2RTC_URL     z.B. https://stallwache.example.com
 *   NEXT_PUBLIC_STREAM_NAME    go2rtc-Stream der Stallwache  (Default: "stallwache")
 *   NEXT_PUBLIC_STREAM_NAME_2  go2rtc-Stream der Futterwache (Default: "futterwache")
 */

/** Basis-URL des go2rtc-Servers (Cloudflare-Tunnel), ohne abschliessenden Slash. */
export const GO2RTC_URL = (process.env.NEXT_PUBLIC_GO2RTC_URL?.trim() || "")
  .replace(/\/+$/, "");

export const isConfigured = GO2RTC_URL.length > 0;

export type CameraId = "stallwache" | "futterwache";

/** Kamera-State laut State-Modell: online | offline | laedt | instabil */
export type CameraState = "online" | "offline" | "laedt" | "instabil";

export interface CameraConfig {
  id: CameraId;
  /** Anzeigename in der UI. */
  name: string;
  /** Name der Quelle in go2rtc.yaml. */
  streamName: string;
  /** Reduzierte Metadaten fuer die Vorschau-Karte. */
  ort: string;
}

/** Stallwache = Hauptkamera (Default), Futterwache = Zweitkamera. */
export const CAMERAS: readonly [CameraConfig, CameraConfig] = [
  {
    id: "stallwache",
    name: "Stallwache",
    streamName: process.env.NEXT_PUBLIC_STREAM_NAME?.trim() || "stallwache",
    ort: "Abkalbebereich",
  },
  {
    id: "futterwache",
    name: "Futterwache",
    streamName: process.env.NEXT_PUBLIC_STREAM_NAME_2?.trim() || "futterwache",
    ort: "Futtertisch",
  },
];

export function cameraById(id: CameraId): CameraConfig {
  return CAMERAS.find((c) => c.id === id) ?? CAMERAS[0];
}

/** WebRTC-Signaling-Endpoint von go2rtc (niedrige Latenz, nur Hauptkamera). */
export function webrtcUrl(streamName: string): string {
  return `${GO2RTC_URL}/api/webrtc?src=${encodeURIComponent(streamName)}`;
}

/** HLS-Playlist von go2rtc (robuster Fallback fuer die Hauptkamera). */
export function hlsUrl(streamName: string): string {
  return `${GO2RTC_URL}/api/stream.m3u8?src=${encodeURIComponent(streamName)}`;
}

/** Einzelbild (Snapshot) – Grundlage der ressourcenschonenden Vorschau. */
export function snapshotUrl(streamName: string): string {
  return `${GO2RTC_URL}/api/frame.jpeg?src=${encodeURIComponent(streamName)}`;
}
