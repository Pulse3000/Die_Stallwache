"use client";

import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import {
  BRIDGE_TYPE,
  type CameraConfig,
  type CameraState,
  hlsUrl,
  isConfigured,
  snapshotSupported,
  snapshotUrl,
  TUYA_STREAM_ENDPOINT,
  webrtcUrl,
} from "@/lib/config";

export type CameraRole = "haupt" | "vorschau";

interface Props {
  camera: CameraConfig;
  role: CameraRole;
  /** Meldet Statuswechsel nach oben (Header, Statusblock, Ereignisse). */
  onState: (id: CameraConfig["id"], state: CameraState) => void;
}

/** Vorschau: Einzelbilder statt Live-Stream – reduzierte Stream-Prioritaet. */
const PREVIEW_INTERVAL_OK = 5000;
const PREVIEW_INTERVAL_ERR = 15000;
/** Kopfstart der Hauptkamera: Vorschau beginnt erst kurz danach. */
const PREVIEW_INITIAL_DELAY = 600;

/**
 * Ein Kamera-Container fuer Stallblick.
 *
 * Quelle Bridge (go2rtc ODER MediaMTX, siehe lib/config.ts BRIDGE_TYPE):
 *   Rolle "haupt"    → WebRTC (go2rtc-JSON oder MediaMTX-WHEP, niedrige
 *                      Latenz) mit automatischem HLS-Fallback + Reconnect.
 *   Rolle "vorschau" → go2rtc: Snapshot-Polling per <img> (leichtgewichtig).
 *                      MediaMTX: kein JPEG-Snapshot vorhanden – daher nur
 *                      ein leichtes HEAD-Status-Polling (kein Videodecode)
 *                      plus ruhiger Platzhalter statt Thumbnail.
 *
 * Quelle Tuya-Cloud (Futterwache, camera.tuyaFaehig):
 *   Rolle "haupt"    → HLS-URL von /api/futterwache/stream; bei 503/Fehler
 *                      automatischer Fallback auf die Bridge. Tuya-URLs
 *                      laufen ab → bei fatalem HLS-Fehler wird eine frische
 *                      URL geholt.
 *   Rolle "vorschau" → wie Bridge-Vorschau oben (go2rtc-Snapshot wenn
 *                      verfuegbar, sonst ruhiger Platzhalter).
 *
 * Der Rollenwechsel bindet nur die Medienquelle im selben Container um;
 * die Komponente bleibt gemountet, es gibt keinen Seiten-Neuaufbau.
 */
export default function CameraStream({ camera, role, onState }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const whepResourceUrlRef = useRef<string | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptsRef = useRef(0);
  const wasLiveRef = useRef(false);
  const disposedRef = useRef(false);
  // Tuya fehlgeschlagen -> fuer diese Haupt-Session auf die Bridge bleiben.
  const tuyaAufgegebenRef = useRef(false);

  const istTuya = camera.tuyaFaehig;

  const [videoLive, setVideoLive] = useState(false);
  const [snapSrc, setSnapSrc] = useState<string | null>(null);
  const [snapVisible, setSnapVisible] = useState(false);

  // Stabile Referenz auf den Callback, damit der Effekt nur auf `role` reagiert.
  const onStateRef = useRef(onState);
  onStateRef.current = onState;
  const stateRef = useRef<CameraState | null>(null);

  useEffect(() => {
    disposedRef.current = false;
    tuyaAufgegebenRef.current = false;
    const report = (s: CameraState) => {
      if (disposedRef.current || stateRef.current === s) return;
      stateRef.current = s;
      onStateRef.current(camera.id, s);
    };

    const clearTimer = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
    };

    /** Beendet eine laufende MediaMTX-WHEP-Session (WHEP-Standard: DELETE auf die Resource-URL). */
    const teardownWhep = () => {
      const url = whepResourceUrlRef.current;
      whepResourceUrlRef.current = null;
      if (url) fetch(url, { method: "DELETE" }).catch(() => {});
    };

    const teardownLive = () => {
      clearTimer();
      pcRef.current?.close();
      pcRef.current = null;
      teardownWhep();
      hlsRef.current?.destroy();
      hlsRef.current = null;
      const video = videoRef.current;
      if (video) {
        video.srcObject = null;
        video.removeAttribute("src");
      }
      setVideoLive(false);
    };

    // Kamera ist bedienbar, wenn Bridge konfiguriert ODER Tuya moeglich ist.
    if (!isConfigured && !istTuya) {
      report("offline");
      return () => {
        disposedRef.current = true;
      };
    }

    if (role === "vorschau") {
      teardownLive();
      if (isConfigured && snapshotSupported) {
        // ---- Vorschau via go2rtc-Snapshot ----
        const poll = () => {
          if (disposedRef.current) return;
          setSnapSrc(`${snapshotUrl(camera.streamName)}&t=${Date.now()}`);
        };
        report(wasLiveRef.current ? "online" : "laedt");
        timerRef.current = setTimeout(poll, PREVIEW_INITIAL_DELAY);
      } else if (isConfigured) {
        // ---- MediaMTX: kein Snapshot-Endpoint – leichtes HEAD-Polling ----
        // Kein Videodecode fuer die Vorschau, nur ein Status-Ping.
        const pingen = async () => {
          if (disposedRef.current) return;
          try {
            const res = await fetch(hlsUrl(camera.streamName), {
              method: "HEAD",
              cache: "no-store",
            });
            report(res.ok ? "online" : "offline");
          } catch {
            report("offline");
          } finally {
            if (!disposedRef.current) {
              timerRef.current = setTimeout(
                pingen,
                stateRef.current === "online"
                  ? PREVIEW_INTERVAL_OK
                  : PREVIEW_INTERVAL_ERR,
              );
            }
          }
        };
        void pingen();
      } else {
        // ---- Tuya-only: ruhiger Platzhalter, kein zweiter Live-Stream ----
        report(wasLiveRef.current ? "online" : "laedt");
      }
      return () => {
        disposedRef.current = true;
        clearTimer();
      };
    }

    // ---- Haupt-Modus: Live-Stream mit hoechster Prioritaet ----
    const markLive = () => {
      attemptsRef.current = 0;
      wasLiveRef.current = true;
      setVideoLive(true);
      report("online");
    };

    const scheduleReconnect = () => {
      if (disposedRef.current) return;
      setVideoLive(false);
      report(attemptsRef.current >= 2 ? "offline" : "instabil");
      const delay = Math.min(30000, 2000 * 2 ** attemptsRef.current);
      attemptsRef.current += 1;
      clearTimer();
      timerRef.current = setTimeout(connect, delay);
    };

    /** Spielt eine HLS-URL ab (nativ oder via hls.js); onFatal bei Abbruch. */
    const playHlsUrl = (url: string, onFatal: () => void) => {
      const video = videoRef.current;
      if (!video || disposedRef.current) return;

      if (video.canPlayType("application/vnd.apple.mpegurl")) {
        video.src = url; // Safari / iOS: natives HLS
        video.play().then(markLive).catch(() => {});
        return;
      }
      if (Hls.isSupported()) {
        const hls = new Hls({ lowLatencyMode: true, liveSyncDuration: 2 });
        hlsRef.current = hls;
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(Hls.Events.MANIFEST_PARSED, () => {
          video.play().catch(() => {});
          markLive();
        });
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (data.fatal) onFatal();
        });
      } else {
        onFatal();
      }
    };

    const startHls = () => playHlsUrl(hlsUrl(camera.streamName), scheduleReconnect);

    /** WebRTC-Verbindungsaufbau ueber die konfigurierte Bridge (go2rtc oder MediaMTX/WHEP). */
    const startBridgeWebrtc = async () => {
      const video = videoRef.current;
      if (!video || disposedRef.current) return;

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
          if (pc.connectionState === "connected") markLive();
          if (
            pc.connectionState === "failed" ||
            pc.connectionState === "disconnected"
          ) {
            pc.close();
            if (pcRef.current === pc && !disposedRef.current) {
              pcRef.current = null;
              startHls();
            }
          }
        };

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        if (BRIDGE_TYPE === "mediamtx") {
          // WHEP-Standard: rohes SDP rein, rohes SDP raus (kein JSON).
          const res = await fetch(webrtcUrl(camera.streamName), {
            method: "POST",
            headers: { "Content-Type": "application/sdp" },
            body: offer.sdp,
          });
          if (!res.ok) throw new Error(`WHEP HTTP ${res.status}`);
          const location = res.headers.get("Location");
          if (location) {
            whepResourceUrlRef.current = new URL(location, webrtcUrl(camera.streamName)).toString();
          }
          const answerSdp = await res.text();
          await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
        } else {
          // go2rtc-JSON-API.
          const res = await fetch(webrtcUrl(camera.streamName), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ type: "offer", sdp: offer.sdp }),
          });
          if (!res.ok) throw new Error(`go2rtc HTTP ${res.status}`);
          const answer = await res.json();
          await pc.setRemoteDescription(answer);
        }
      } catch {
        pcRef.current?.close();
        pcRef.current = null;
        teardownWhep();
        if (!disposedRef.current) startHls();
      }
    };

    /** Holt eine frische Tuya-HLS-URL und spielt sie; Fallback auf die Bridge. */
    const startTuya = async () => {
      const video = videoRef.current;
      if (!video || disposedRef.current) return;
      try {
        const res = await fetch(TUYA_STREAM_ENDPOINT, { cache: "no-store" });
        if (!res.ok) throw new Error(`Tuya HTTP ${res.status}`);
        const data = (await res.json()) as { url?: string };
        if (disposedRef.current) return;
        if (!data.url) throw new Error("Tuya ohne URL");
        // Bei fatalem Fehler frische URL holen (Tuya-URLs laufen ab).
        playHlsUrl(data.url, scheduleReconnect);
      } catch {
        if (disposedRef.current) return;
        if (isConfigured) {
          // Tuya nicht verfuegbar → fuer diese Session auf die Bridge umschalten.
          tuyaAufgegebenRef.current = true;
          void startBridgeWebrtc();
        } else {
          scheduleReconnect();
        }
      }
    };

    function connect() {
      teardownLive();
      report(wasLiveRef.current ? "instabil" : "laedt");
      if (istTuya && !tuyaAufgegebenRef.current) void startTuya();
      else void startBridgeWebrtc();
    }

    connect();

    return () => {
      disposedRef.current = true;
      teardownLive();
    };
    // camera.id/.streamName sind konstant pro Instanz – nur die Rolle wechselt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  const onSnapLoad = () => {
    setSnapVisible(true);
    if (role === "vorschau" && !disposedRef.current) {
      if (stateRef.current !== "online") {
        stateRef.current = "online";
        onStateRef.current(camera.id, "online");
      }
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(
        () => setSnapSrc(`${snapshotUrl(camera.streamName)}&t=${Date.now()}`),
        PREVIEW_INTERVAL_OK,
      );
    }
  };

  const onSnapError = () => {
    if (role === "vorschau" && !disposedRef.current) {
      if (stateRef.current !== "offline") {
        stateRef.current = "offline";
        onStateRef.current(camera.id, "offline");
      }
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(
        () => setSnapSrc(`${snapshotUrl(camera.streamName)}&t=${Date.now()}`),
        PREVIEW_INTERVAL_ERR,
      );
    }
  };

  const zeigeVorschauPlatzhalter =
    role === "vorschau" && isConfigured && !snapshotSupported;

  return (
    <div className="absolute inset-0 bg-black">
      {/* Letztes Standbild bleibt als ruhiger Hintergrund erhalten. */}
      {snapSrc && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={snapSrc}
          alt={`${camera.name} – Vorschau`}
          onLoad={onSnapLoad}
          onError={onSnapError}
          className={`absolute inset-0 h-full w-full object-contain transition-opacity ${
            snapVisible && !videoLive ? "opacity-100" : "opacity-0"
          }`}
        />
      )}
      <video
        ref={videoRef}
        playsInline
        autoPlay
        muted
        controls={false}
        className={`absolute inset-0 h-full w-full object-contain ${
          role === "haupt" && videoLive ? "opacity-100" : "opacity-0"
        }`}
      />
      {/* Bridge nicht konfiguriert (nur fuer reine Bridge-Kameras) */}
      {!isConfigured && !istTuya && (
        <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-slate-800 to-slate-950 p-4">
          <p className="max-w-xs text-center text-xs text-white/60">
            Warte auf Bridge – sobald{" "}
            <code className="rounded bg-black/40 px-1">
              NEXT_PUBLIC_BRIDGE_URL
            </code>{" "}
            gesetzt ist, erscheint hier das Bild der {camera.name}.
          </p>
        </div>
      )}
      {/* MediaMTX-Vorschau: kein Snapshot-Endpoint -> ruhiger Platzhalter statt Thumbnail */}
      {zeigeVorschauPlatzhalter && (
        <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-slate-800 to-slate-950 p-4">
          <p className="max-w-xs text-center text-xs text-white/60">
            {camera.name} · Vorschau
          </p>
        </div>
      )}
      {/* Tuya-Kamera ohne Bridge: ruhiger Hinweis, solange kein Livebild steht */}
      {istTuya && !isConfigured && !videoLive && !snapVisible && (
        <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-b from-slate-800 to-slate-950 p-4">
          <p className="max-w-xs text-center text-xs text-white/60">
            {role === "haupt"
              ? `${camera.name} über Tuya-Cloud – verbinde…`
              : `${camera.name} · Vorschau`}
          </p>
        </div>
      )}
    </div>
  );
}
