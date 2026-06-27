"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { hlsUrl, isConfigured, webrtcUrl } from "@/lib/config";

type Status = "idle" | "connecting" | "live" | "error" | "unconfigured";

const STATUS_LABEL: Record<Status, string> = {
  idle: "Bereit",
  connecting: "Verbinde…",
  live: "LIVE",
  error: "Keine Verbindung",
  unconfigured: "Nicht konfiguriert",
};

/**
 * Live-Player fuer den go2rtc-Stream.
 * Primaer WebRTC (niedrige Latenz, < 1 s), automatischer Fallback auf HLS.
 */
export default function LivePlayer() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const [status, setStatus] = useState<Status>(
    isConfigured ? "idle" : "unconfigured",
  );
  const [transport, setTransport] = useState<"WebRTC" | "HLS" | null>(null);
  const [muted, setMuted] = useState(true);

  const cleanup = useCallback(() => {
    pcRef.current?.close();
    pcRef.current = null;
    hlsRef.current?.destroy();
    hlsRef.current = null;
  }, []);

  const startHls = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    setTransport("HLS");
    const url = hlsUrl();

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      // Safari / iOS: natives HLS
      video.src = url;
      video.play().catch(() => {});
      setStatus("live");
      return;
    }
    if (Hls.isSupported()) {
      const hls = new Hls({ lowLatencyMode: true, liveSyncDuration: 2 });
      hlsRef.current = hls;
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        video.play().catch(() => {});
        setStatus("live");
      });
      hls.on(Hls.Events.ERROR, (_e, data) => {
        if (data.fatal) setStatus("error");
      });
    } else {
      setStatus("error");
    }
  }, []);

  const startWebrtc = useCallback(async () => {
    const video = videoRef.current;
    if (!video) return;
    setStatus("connecting");
    setTransport("WebRTC");

    try {
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      });
      pcRef.current = pc;
      pc.addTransceiver("video", { direction: "recvonly" });
      pc.addTransceiver("audio", { direction: "recvonly" });

      pc.ontrack = (ev) => {
        if (video.srcObject !== ev.streams[0]) {
          video.srcObject = ev.streams[0];
          video.play().catch(() => {});
        }
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "connected") setStatus("live");
        if (
          pc.connectionState === "failed" ||
          pc.connectionState === "disconnected"
        ) {
          // WebRTC fehlgeschlagen -> HLS-Fallback
          cleanup();
          startHls();
        }
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const res = await fetch(webrtcUrl(), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type: "offer", sdp: offer.sdp }),
      });
      if (!res.ok) throw new Error(`go2rtc HTTP ${res.status}`);
      const answer = await res.json();
      await pc.setRemoteDescription(answer);
    } catch (err) {
      console.warn("WebRTC fehlgeschlagen, Fallback auf HLS:", err);
      cleanup();
      startHls();
    }
  }, [cleanup, startHls]);

  const connect = useCallback(() => {
    if (!isConfigured) {
      setStatus("unconfigured");
      return;
    }
    cleanup();
    startWebrtc();
  }, [cleanup, startWebrtc]);

  useEffect(() => {
    connect();
    return cleanup;
  }, [connect, cleanup]);

  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMuted(v.muted);
  };

  const enterFullscreen = () => {
    const v = videoRef.current as
      | (HTMLVideoElement & { webkitEnterFullscreen?: () => void })
      | null;
    if (!v) return;
    if (v.requestFullscreen) v.requestFullscreen().catch(() => {});
    else if (v.webkitEnterFullscreen) v.webkitEnterFullscreen();
  };

  const isLive = status === "live";

  return (
    <div className="w-full">
      <div className="relative w-full overflow-hidden rounded-2xl bg-black shadow-xl ring-1 ring-white/10 aspect-video">
        <video
          ref={videoRef}
          className="h-full w-full object-contain"
          playsInline
          autoPlay
          muted={muted}
          controls={false}
        />

        {/* Status-Badge */}
        <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1 text-xs font-semibold backdrop-blur">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              isLive
                ? "animate-pulse bg-stall-accent"
                : status === "error" || status === "unconfigured"
                  ? "bg-red-500"
                  : "bg-amber-400"
            }`}
          />
          {STATUS_LABEL[status]}
          {transport && isLive ? (
            <span className="text-white/50">· {transport}</span>
          ) : null}
        </div>

        {/* Overlay bei Fehler / nicht konfiguriert */}
        {(status === "error" || status === "unconfigured") && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-black/70 p-6 text-center">
            <p className="text-sm text-white/80">
              {status === "unconfigured"
                ? "Es ist noch keine go2rtc-URL hinterlegt. Bitte NEXT_PUBLIC_GO2RTC_URL setzen (siehe README)."
                : "Stream nicht erreichbar. Laeuft die go2rtc-Bridge und der Cloudflare-Tunnel?"}
            </p>
            {status === "error" && (
              <button
                onClick={connect}
                className="rounded-lg bg-stall-accent px-4 py-2 text-sm font-semibold text-black active:scale-95"
              >
                Erneut verbinden
              </button>
            )}
          </div>
        )}
      </div>

      {/* Steuerung */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          onClick={connect}
          className="flex-1 rounded-xl bg-stall-card px-4 py-3 text-sm font-semibold ring-1 ring-white/10 active:scale-95 sm:flex-none"
        >
          ↻ Neu verbinden
        </button>
        <button
          onClick={toggleMute}
          className="flex-1 rounded-xl bg-stall-card px-4 py-3 text-sm font-semibold ring-1 ring-white/10 active:scale-95 sm:flex-none"
        >
          {muted ? "🔇 Ton an" : "🔊 Ton aus"}
        </button>
        <button
          onClick={enterFullscreen}
          className="flex-1 rounded-xl bg-stall-card px-4 py-3 text-sm font-semibold ring-1 ring-white/10 active:scale-95 sm:flex-none"
        >
          ⛶ Vollbild
        </button>
      </div>
    </div>
  );
}
