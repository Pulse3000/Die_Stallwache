/**
 * Zentrale Konfiguration der Stallblick-Webapp.
 *
 * Die Tapo-Kameras liefern nur lokal RTSP-Streams. Damit diese 24/7 ueber das
 * Internet erreichbar sind, laeuft im Stall-Netz ein go2rtc-Bridge-Server
 * (siehe /bridge), der via Cloudflare Tunnel oeffentlich per HTTPS
 * bereitgestellt wird. Diese App spricht ausschliesslich mit go2rtc –
 * niemals direkt mit einer Kamera, und ohne Zugangsdaten im Frontend.
 *
 * Konfiguration ueber Umgebungsvariablen (siehe .env.example):
 *   NEXT_PUBLIC_GO2RTC_URL              z.B. https://stallwache.example.com
 *   NEXT_PUBLIC_STREAM_NAME             Stream der Stallwache  (Default: "stallwache")
 *   NEXT_PUBLIC_STREAM_NAME_FUTTERWACHE Stream der Futterwache (Default: "futterwache")
 */

export type CameraId = "stallwache" | "futterwache";

export type CameraDef = {
  id: CameraId;
  /** Anzeigename in der UI. */
  label: string;
  /** Stream-Name in go2rtc (bridge/go2rtc.yaml). */
  streamName: string;
};

/** Stallwache = Hauptkamera, Futterwache = Zweitkamera (Standardzuordnung). */
export const CAMERAS: Record<CameraId, CameraDef> = {
  stallwache: {
    id: "stallwache",
    label: "Stallwache",
    streamName: process.env.NEXT_PUBLIC_STREAM_NAME?.trim() || "stallwache",
  },
  futterwache: {
    id: "futterwache",
    label: "Futterwache",
    streamName:
      process.env.NEXT_PUBLIC_STREAM_NAME_FUTTERWACHE?.trim() || "futterwache",
  },
};

/** Standard-Hauptkamera beim ersten Laden. */
export const DEFAULT_MAIN_CAMERA: CameraId = "stallwache";

export function otherCamera(id: CameraId): CameraId {
  return id === "stallwache" ? "futterwache" : "stallwache";
}

/** Basis-URL des go2rtc-Servers (Cloudflare-Tunnel), ohne abschliessenden Slash. */
export const GO2RTC_URL = (process.env.NEXT_PUBLIC_GO2RTC_URL?.trim() || "")
  .replace(/\/+$/, "");

export const isConfigured = GO2RTC_URL.length > 0;

/** WebRTC-Signaling-Endpoint von go2rtc (niedrige Latenz, bevorzugt). */
export function webrtcUrl(streamName: string): string {
  return `${GO2RTC_URL}/api/webrtc?src=${encodeURIComponent(streamName)}`;
}

/** HLS-Playlist von go2rtc (robuster Fallback, etwas hoehere Latenz). */
export function hlsUrl(streamName: string): string {
  return `${GO2RTC_URL}/api/stream.m3u8?src=${encodeURIComponent(streamName)}`;
}

/** Einzelbild (Snapshot) einer Kamera fuer Vorschau / Poster. */
export function snapshotUrl(streamName: string): string {
  return `${GO2RTC_URL}/api/frame.jpeg?src=${encodeURIComponent(streamName)}`;
}
