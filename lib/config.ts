/**
 * Zentrale Konfiguration der Stallwache-Webapp.
 *
 * Die Tapo TCA72 liefert nur lokal einen RTSP-Stream (192.168.178.117).
 * Damit dieser 24/7 ueber das Internet erreichbar ist, laeuft im Stall-Netz
 * ein go2rtc-Bridge-Server (siehe /bridge), der via Cloudflare Tunnel oeffentlich
 * per HTTPS bereitgestellt wird. Diese App spricht ausschliesslich mit go2rtc –
 * niemals direkt mit der Kamera, und ohne Zugangsdaten im Frontend.
 *
 * Konfiguration erfolgt ueber Umgebungsvariablen (siehe .env.example):
 *   NEXT_PUBLIC_GO2RTC_URL   z.B. https://stallwache.example.com
 *   NEXT_PUBLIC_STREAM_NAME  Name des Streams in go2rtc.yaml (Default: "stallwache")
 */

export const STREAM_NAME =
  process.env.NEXT_PUBLIC_STREAM_NAME?.trim() || "stallwache";

/** Basis-URL des go2rtc-Servers (Cloudflare-Tunnel), ohne abschliessenden Slash. */
export const GO2RTC_URL = (process.env.NEXT_PUBLIC_GO2RTC_URL?.trim() || "")
  .replace(/\/+$/, "");

export const isConfigured = GO2RTC_URL.length > 0;

/** WebRTC-Signaling-Endpoint von go2rtc (niedrige Latenz, bevorzugt). */
export function webrtcUrl(): string {
  return `${GO2RTC_URL}/api/webrtc?src=${encodeURIComponent(STREAM_NAME)}`;
}

/** HLS-Playlist von go2rtc (robuster Fallback, etwas hoehere Latenz). */
export function hlsUrl(): string {
  return `${GO2RTC_URL}/api/stream.m3u8?src=${encodeURIComponent(STREAM_NAME)}`;
}

/** Einzelbild (Snapshot) der Kamera fuer Vorschau / Poster. */
export function snapshotUrl(): string {
  return `${GO2RTC_URL}/api/frame.jpeg?src=${encodeURIComponent(STREAM_NAME)}`;
}
