"use client";

import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import { hlsUrl, isConfigured, webrtcUrl } from "@/lib/config";

type Status = "idle" | "connecting" | "live" | "error" | "unconfigured";

const STATUS_LABEL: Record<Status, string> = {
  idle: "Bereit",
  connecting: "Verbinde…",
  live: "LIVE",
  error: "Keine Verbindung",
  unconfigured: "Warte auf Bridge",
};

function fmtUptime(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

/**
 * Live-Player fuer den go2rtc-Stream.
 * Primaer WebRTC (niedrige Latenz, < 1 s), automatischer Fallback auf HLS,
 * automatischer Reconnect mit Backoff und Uptime-Anzeige.
 *
 * Die gesamte Verbindungslogik laeuft ueber Refs, damit der Effekt nur einmal
 * startet und ein Transportwechsel (WebRTC -> HLS) keinen Neustart ausloest.
 */
export default function LivePlayer() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptsRef = useRef(0);
  const liveSinceRef = useRef<number | null>(null);
  const transportRef = useRef<"WebRTC" | "HLS" | null>(null);
  const disposedRef = useRef(false);

  const [status, setStatus] = useState<Status>(
    isConfigured ? "idle" : "unconfigured",
  );
  const [transport, setTransport] = useState<"WebRTC" | "HLS" | null>(null);
  const [muted, setMuted] = useState(true);
  const [uptime, setUptime] = useState(0);

  // Alle Routinen liegen in Refs -> stabile Identitaet, keine Render-Loops.
  const fns = useRef({
    teardown: () => {},
    connect: () => {},
    markLive: () => {},
    startHls: () => {},
    startWebrtc: async () => {},
    scheduleReconnect: () => {},
  });

  useEffect(() => {
    const setTransportBoth = (t: "WebRTC" | "HLS" | null) => {
      transportRef.current = t;
      setTransport(t);
    };

    fns.current.teardown = () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      pcRef.current?.close();
      pcRef.current = null;
      hlsRef.current?.destroy();
      hlsRef.current = null;
    };

    fns.current.markLive = () => {
      attemptsRef.current = 0;
      liveSinceRef.current = liveSinceRef.current ?? Date.now();
      setStatus("live");
    };

    fns.current.scheduleReconnect = () => {
      if (disposedRef.current) return;
      liveSinceRef.current = null;
      setUptime(0);
      const delay = Math.min(30000, 2000 * 2 ** attemptsRef.current);
      attemptsRef.current += 1;
      if (retryRef.current) clearTimeout(retryRef.current);
      retryRef.current = setTimeout(() => fns.current.connect(), delay);
    };

    fns.current.startHls = () => {
      const video = videoRef.current;
      if (!video) return;
      setTransportBoth("HLS");
      const url = hlsUrl();

      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = url; // Safari / iOS: natives HLS
        video.play().catch(() => {});
        fns.current.markLive();
        return;
      }
      if (Hls.isSupported()) {
        const hls = new Hls({ lowLatencyMode: true, liveSyncDuration: 2 });
        hlsRef.current = hls;
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          video.play().catch(() => {});
          fns.current.markLive();
        });
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (data.fatal) {
            setStatus("error");
            fns.current.scheduleReconnect();
          }
        });
      } else {
        setStatus("error");
        fns.current.scheduleReconnect();
      }
    };

    fns.current.startWebrtc = async () => {
      const video = videoRef.current;
      if (!video) return;
      setStatus((s) => (s === "live" ? s : "connecting"));
      setTransportBoth("WebRTC");

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
          if (pc.connectionState === "connected") fns.current.markLive();
          if (
            pc.connectionState === "failed" ||
            pc.connectionState === "disconnected"
          ) {
            pc.close();
            if (transportRef.current === "WebRTC") fns.current.startHls();
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
        console.warn("WebRTC nicht verfuegbar, nutze HLS:", err);
        pcRef.current?.close();
        pcRef.current = null;
        fns.current.startHls();
      }
    };

    fns.current.connect = () => {
      if (!isConfigured) {
        setStatus("unconfigured");
        return;
      }
      fns.current.teardown();
      void fns.current.startWebrtc();
    };

    // Einmaliger Start beim Mount.
    disposedRef.current = false;
    fns.current.connect();

    const ticker = setInterval(() => {
      if (liveSinceRef.current) {
        setUptime(Math.floor((Date.now() - liveSinceRef.current) / 1000));
      }
    }, 1000);

    return () => {
      disposedRef.current = true;
      clearInterval(ticker);
      fns.current.teardown();
    };
  }, []);

  const manualRetry = () => {
    attemptsRef.current = 0;
    fns.current.connect();
  };

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
  const waiting = status === "error" || status === "unconfigured";

  return (
    <div className="w-full">
      <div className="relative w-full overflow-hidden rounded-2xl bg-black shadow-2xl ring-1 ring-white/10 aspect-video">
        <video
          ref={videoRef}
          className="h-full w-full object-contain"
          playsInline
          autoPlay
          muted={muted}
          controls={false}
        />

        {waiting && <WaitingScene />}

        <div className="pointer-events-none absolute left-3 top-3 flex items-center gap-2 rounded-full bg-black/60 px-3 py-1 text-xs font-semibold backdrop-blur">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              isLive
                ? "animate-pulse bg-stall-accent shadow-[0_0_8px] shadow-stall-accent"
                : status === "error"
                  ? "bg-red-500"
                  : status === "unconfigured"
                    ? "bg-sky-400"
                    : "animate-pulse bg-amber-400"
            }`}
          />
          {STATUS_LABEL[status]}
          {transport && isLive ? (
            <span className="text-white/50">· {transport}</span>
          ) : null}
        </div>

        {isLive && (
          <div className="pointer-events-none absolute right-3 top-3 rounded-full bg-black/60 px-3 py-1 font-mono text-xs text-white/70 backdrop-blur">
            {fmtUptime(uptime)}
          </div>
        )}

        {waiting && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
            <p className="max-w-sm text-sm text-white/80">
              {status === "unconfigured"
                ? "Die Webapp läuft. Sobald die go2rtc-Bridge im Stall verbunden ist, erscheint hier automatisch das Live-Bild."
                : "Stream nicht erreichbar – versuche automatisch erneut zu verbinden. Läuft die Bridge & der Cloudflare-Tunnel?"}
            </p>
            <button
              onClick={manualRetry}
              className="rounded-lg bg-stall-accent px-4 py-2 text-sm font-semibold text-black transition active:scale-95"
            >
              Jetzt verbinden
            </button>
          </div>
        )}
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <button
          onClick={manualRetry}
          className="rounded-xl bg-stall-card px-3 py-3 text-sm font-semibold ring-1 ring-white/10 transition active:scale-95"
        >
          ↻ Verbinden
        </button>
        <button
          onClick={toggleMute}
          className="rounded-xl bg-stall-card px-3 py-3 text-sm font-semibold ring-1 ring-white/10 transition active:scale-95"
        >
          {muted ? "🔇 Ton an" : "🔊 Ton aus"}
        </button>
        <button
          onClick={enterFullscreen}
          className="rounded-xl bg-stall-card px-3 py-3 text-sm font-semibold ring-1 ring-white/10 transition active:scale-95"
        >
          ⛶ Vollbild
        </button>
      </div>
    </div>
  );
}

/** Dezent animierte „Stall"-Szene als Platzhalter, solange kein Live-Bild da ist. */
function WaitingScene() {
  return (
    <div className="absolute inset-0 overflow-hidden bg-gradient-to-b from-slate-800 via-slate-900 to-black">
      <div className="absolute inset-0 opacity-30 [background-image:radial-gradient(circle_at_1px_1px,rgba(255,255,255,0.15)_1px,transparent_0)] [background-size:22px_22px]" />
      <div className="absolute left-1/2 top-1/2 h-40 w-40 -translate-x-1/2 -translate-y-1/2 rounded-full border border-stall-accent/40 [animation:ping_2.4s_cubic-bezier(0,0,0.2,1)_infinite]" />
      <div className="absolute left-1/2 top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-stall-accent/80" />
    </div>
  );
}
