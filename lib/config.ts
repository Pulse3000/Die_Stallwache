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

/** Stallwache = Hauptkamera (Default), weitere Kameras als Zweitkameras. */
export const CAMERAS: readonly CameraConfig[] = [
  {
    id: "stallwache",
    name: "Stallwache",
    ort: "Abkalbebereich",
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
  },
];

export function cameraById(id: CameraId): CameraConfig {
  return CAMERAS.find((c) => c.id === id) ?? CAMERAS[0];
}
