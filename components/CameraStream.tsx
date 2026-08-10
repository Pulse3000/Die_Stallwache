"use client";

import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";
import type { CameraConfig, CameraState } from "@/lib/config";

export type CameraRole = "haupt" | "vorschau";

interface Props {
  camera: CameraConfig;
  role: CameraRole;
  /** Meldet Statuswechsel nach oben (Header, Statusblock, Ereignisse). */
  onState: (id: CameraConfig["id"], state: CameraState) => void;
}

/**
 * Ein Kamera-Container fuer Stallblick – Quelle ist ausschliesslich die
 * Tuya-Cloud.
 *
 *   Rolle "haupt"    → holt eine kurzlebige HLS-URL von camera.tuyaEndpoint
 *                      und spielt sie per hls.js (bzw. nativ auf Safari/iOS).
 *                      Tuya-URLs laufen ab, deshalb holt jeder Reconnect eine
 *                      frische URL; Wartezeit mit exponentiellem Backoff
 *                      (max. 30 s).
 *   Rolle "vorschau" → ruhiger Platzhalter, bewusst **kein** zweiter
 *                      Dauerstream: jede Tuya-Allokation kostet ein
 *                      Cloud-Kontingent, und ein Einzelbild-Endpoint (wie
 *                      frueher go2rtcs frame.jpeg) existiert dort nicht.
 *
 * Der Rollenwechsel bindet nur die Medienquelle im selben Container um;
 * die Komponente bleibt gemountet, es gibt keinen Seiten-Neuaufbau.
 */
export default function CameraStream({ camera, role, onState }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptsRef = useRef(0);
  const wasLiveRef = useRef(false);
  const disposedRef = useRef(false);

  const [videoLive, setVideoLive] = useState(false);

  // Stabile Referenz auf den Callback, damit der Effekt nur auf `role` reagiert.
  // Aktualisierung im Effekt (nicht im Render) haelt das Rendern pur; dieser
  // Effekt steht vor dem Haupt-Effekt und laeuft daher pro Commit zuerst.
  const onStateRef = useRef(onState);
  useEffect(() => {
    onStateRef.current = onState;
  });
  const stateRef = useRef<CameraState | null>(null);

  useEffect(() => {
    disposedRef.current = false;
    const report = (s: CameraState) => {
      if (disposedRef.current || stateRef.current === s) return;
      stateRef.current = s;
      onStateRef.current(camera.id, s);
    };

    const clearTimer = () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = null;
    };

    const teardownLive = () => {
      clearTimer();
      hlsRef.current?.destroy();
      hlsRef.current = null;
      videoRef.current?.removeAttribute("src");
      setVideoLive(false);
    };

    if (role === "vorschau") {
      // ---- Vorschau: ruhiger Platzhalter, kein zweiter Live-Stream ----
      teardownLive();
      report(wasLiveRef.current ? "online" : "laedt");
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

    /** Holt eine frische Tuya-HLS-URL und spielt sie ab. */
    async function connect() {
      teardownLive();
      report(wasLiveRef.current ? "instabil" : "laedt");
      try {
        const res = await fetch(camera.tuyaEndpoint, { cache: "no-store" });
        if (!res.ok) throw new Error(`Tuya HTTP ${res.status}`);
        const data = (await res.json()) as { url?: string };
        if (disposedRef.current) return;
        if (!data.url) throw new Error("Tuya ohne URL");
        // Bei fatalem Fehler frische URL holen (Tuya-URLs laufen ab).
        playHlsUrl(data.url, scheduleReconnect);
      } catch {
        scheduleReconnect();
      }
    }

    void connect();

    return () => {
      disposedRef.current = true;
      teardownLive();
    };
    // camera.id/.tuyaEndpoint sind konstant pro Instanz – nur die Rolle wechselt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role]);

  return (
    <div className="absolute inset-0 bg-black">
      <video
        ref={videoRef}
        // Der Schnappschuss in StallblickApp greift ueber dieses Attribut auf
        // das gerade aktive Hauptbild zu (beide Instanzen bleiben gemountet).
        data-rolle={role}
        playsInline
        autoPlay
        muted
        controls={false}
        className={`absolute inset-0 h-full w-full object-contain ${
          role === "haupt" && videoLive ? "opacity-100" : "opacity-0"
        }`}
      />
      {/* Ruhiger Hinweis, solange kein Livebild steht */}
      {!(role === "haupt" && videoLive) && (
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
