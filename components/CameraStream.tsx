"use client";

import { useEffect, useRef, useState } from "react";
import type Hls from "hls.js";
import {
  BRIDGE_TYPE,
  type CameraConfig,
  type CameraState,
  hlsUrl,
  isConfigured,
  snapshotSupported,
  snapshotUrl,
  webrtcUrl,
} from "@/lib/config";
import { PING_OK_MS, bewertePing, wartezeitBisPing } from "@/lib/kamera-status";

export type CameraRole = "haupt" | "vorschau";

interface Props {
  camera: CameraConfig;
  role: CameraRole;
  /**
   * Kachel nicht im Bild / Tab verborgen (lib/pausiert.ts): keine Verbindung
   * halten, kein Snapshot-Polling – spart Daten, Akku und Tuya-Aufrufe.
   */
  pausiert?: boolean;
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
 * Quelle Tuya-Cloud (camera.tuyaFaehig, z.B. Futterwache/Abkalbebox):
 *   Rolle "haupt"    → HLS-URL von camera.tuyaEndpoint; bei 503/Fehler
 *                      automatischer Fallback auf die Bridge. Tuya-URLs
 *                      laufen ab → bei fatalem HLS-Fehler wird eine frische
 *                      URL geholt.
 *   Rolle "vorschau" → wie Bridge-Vorschau oben (go2rtc-Snapshot wenn
 *                      verfuegbar). Ohne Bridge: ruhiger Platzhalter, Zustand
 *                      "ungeprueft" (kein Bildbeweis) plus sparsamer
 *                      Status-Ping an camera.tuyaEndpoint
 *                      (docs/vorschau-status-spezifikation.md).
 *
 * Der Rollenwechsel bindet nur die Medienquelle im selben Container um;
 * die Komponente bleibt gemountet, es gibt keinen Seiten-Neuaufbau.
 */
export default function CameraStream({ camera, role, pausiert = false, onState }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const whepResourceUrlRef = useRef<string | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptsRef = useRef(0);
  const wasLiveRef = useRef(false);
  const webrtcWatchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const disposedRef = useRef(false);
  // Tuya fehlgeschlagen -> fuer diese Haupt-Session auf die Bridge bleiben.
  const tuyaAufgegebenRef = useRef(false);
  // Status-Ping der Vorschau ohne Bridge: Fehlschlaege in Folge und absolute
  // Faelligkeit (ueberdauert Rollenwechsel und Pause – hoechstens ein Ping
  // pro Intervall, lib/kamera-status.ts).
  const pingFehlschlaegeRef = useRef(0);
  const pingFaelligRef = useRef(0);

  const istTuya = camera.tuyaFaehig;

  const [videoLive, setVideoLive] = useState(false);
  const [snapSrc, setSnapSrc] = useState<string | null>(null);
  const [snapVisible, setSnapVisible] = useState(false);

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

    // Muss VOR teardownLive stehen: teardownLive meldet den Listener ab und
    // laeuft schon in den Zweigen „pausiert" und „vorschau" — eine spaeter
    // deklarierte const waere dort noch nicht initialisiert (TDZ ->
    // ReferenceError, das ganze Dashboard faellt aus).
    const markLive = () => {
      attemptsRef.current = 0;
      wasLiveRef.current = true;
      // Ein Livebild ist der staerkste Beweis: der naechste Vorschau-Ping
      // ist erst nach dem normalen Takt faellig.
      pingFehlschlaegeRef.current = 0;
      pingFaelligRef.current = Date.now() + PING_OK_MS;
      setVideoLive(true);
      report("online");
    };

    const teardownLive = () => {
      clearTimer();
      if (webrtcWatchdogRef.current) clearTimeout(webrtcWatchdogRef.current);
      webrtcWatchdogRef.current = null;
      pcRef.current?.close();
      pcRef.current = null;
      teardownWhep();
      hlsRef.current?.destroy();
      hlsRef.current = null;
      const video = videoRef.current;
      if (video) {
        video.removeEventListener("playing", markLive);
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

    if (pausiert) {
      // Nicht sichtbar: Verbindung schliessen und nichts nachladen. Beim
      // Fortsetzen verbindet sich die Kachel frisch („laedt", nicht „instabil").
      teardownLive();
      wasLiveRef.current = false;
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
        // Kein uebernommenes „online": das erste Einzelbild entscheidet.
        // „offline" bleibt bis dahin stehen (nicht ohne Beweis zuruecknehmen).
        if (stateRef.current !== "offline") report("laedt");
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
        // Ohne Einzelbild gibt es keinen Bildbeweis: „ungeprueft" statt eines
        // uebernommenen „online" oder eines ewigen „laedt". „offline" bleibt,
        // bis eine Pruefung etwas anderes zeigt.
        if (stateRef.current !== "offline") report("ungeprueft");
        // Sparsamer Status-Ping: Erfolg ist kein Bildbeweis (bleibt
        // „ungeprueft"), zwei Fehlschlaege in Folge sind eine Stoerung.
        let aktiv = true; // nur dieser Effektlauf darf melden
        const abbruch = new AbortController();
        const pingen = async () => {
          let ok = false;
          try {
            const res = await fetch(camera.tuyaEndpoint, {
              cache: "no-store",
              signal: abbruch.signal,
            });
            ok = res.ok;
            res.body?.cancel().catch(() => {}); // nur der Status zaehlt
          } catch {
            ok = false;
          }
          if (!aktiv) return;
          const e = bewertePing(pingFehlschlaegeRef.current, ok);
          pingFehlschlaegeRef.current = e.fehlschlaege;
          pingFaelligRef.current = Date.now() + e.warteMs;
          if (e.zustand) report(e.zustand);
          timerRef.current = setTimeout(pingen, e.warteMs);
        };
        timerRef.current = setTimeout(
          pingen,
          wartezeitBisPing(pingFaelligRef.current, Date.now()),
        );
        return () => {
          aktiv = false;
          abbruch.abort();
          disposedRef.current = true;
          clearTimer();
        };
      }
      return () => {
        disposedRef.current = true;
        clearTimer();
      };
    }

    // ---- Haupt-Modus: Live-Stream mit hoechster Prioritaet ----
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
        // "online" erst beim echten "playing"-Event – play() aufgeloest
        // heisst nur "Wiedergabe gestartet", nicht "Bild da".
        video.addEventListener("playing", markLive, { once: true });
        video.play().catch(() => {});
        return;
      }
      // hls.js (~250 KB) erst laden, wenn er wirklich gebraucht wird:
      // Safari/iOS spielt nativ, WebRTC-Pfade brauchen ihn nie.
      import("hls.js")
        .then(({ default: HlsJs }) => {
          if (disposedRef.current) return;
          startHlsJs(HlsJs, video, url, onFatal);
        })
        .catch(onFatal);
    };

    const startHlsJs = (
      HlsJs: typeof Hls,
      video: HTMLVideoElement,
      url: string,
      onFatal: () => void,
    ) => {
      if (HlsJs.isSupported()) {
        // Live-Bild: kurzer Puffer, kein Rueckpuffer (vier Player gleichzeitig).
        const hls = new HlsJs({
          lowLatencyMode: true,
          liveSyncDuration: 2,
          maxBufferLength: 8,
          maxMaxBufferLength: 12,
          backBufferLength: 0,
        });
        hlsRef.current = hls;
        hls.loadSource(url);
        hls.attachMedia(video);
        hls.on(HlsJs.Events.MANIFEST_PARSED, () => {
          // "online" erst beim echten "playing"-Event – ein geparstes
          // Manifest heisst nur "Playlist gueltig", nicht "Bild da".
          video.addEventListener("playing", markLive, { once: true });
          video.play().catch(() => {});
        });
        hls.on(HlsJs.Events.ERROR, (_e, data) => {
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

      // Pro Verbindungsversuch eigenes Flag: wasLiveRef bleibt ueber
      // Reconnects hinweg true, sobald die Kamera einmal online war, und
      // taugt deshalb nicht zur Erkennung "dieser Versuch liefert kein Bild".
      let bildDa = false;
      const onPlaying = () => {
        bildDa = true;
        markLive();
      };
      video.addEventListener("playing", onPlaying, { once: true });

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
          if (pc.connectionState === "connected") {
            // ICE/DTLS steht – das heisst noch nicht, dass auch ein
            // Videotrack ankommt (z.B. RTSP-Quelle an der Bridge offline).
            // "online" meldet erst das "playing"-Event oben; kommt bis
            // dahin kein Bild, auf HLS zurueckfallen statt den Nutzer vor
            // einem endlosen Lade-Spinner haengen zu lassen.
            if (webrtcWatchdogRef.current) clearTimeout(webrtcWatchdogRef.current);
            webrtcWatchdogRef.current = setTimeout(() => {
              if (pcRef.current === pc && !disposedRef.current && !bildDa) {
                video.removeEventListener("playing", onPlaying);
                pc.close();
                if (pcRef.current === pc) pcRef.current = null;
                startHls();
              }
            }, 8000);
          }
          if (
            pc.connectionState === "failed" ||
            pc.connectionState === "disconnected"
          ) {
            if (webrtcWatchdogRef.current) clearTimeout(webrtcWatchdogRef.current);
            webrtcWatchdogRef.current = null;
            video.removeEventListener("playing", onPlaying);
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
        if (webrtcWatchdogRef.current) clearTimeout(webrtcWatchdogRef.current);
        webrtcWatchdogRef.current = null;
        video.removeEventListener("playing", onPlaying);
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
        const res = await fetch(camera.tuyaEndpoint, { cache: "no-store" });
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
    // camera.id/.streamName sind konstant pro Instanz – nur Rolle/Pause wechseln.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, pausiert]);

  const onSnapLoad = () => {
    setSnapVisible(true);
    if (role === "vorschau" && !pausiert && !disposedRef.current) {
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
    if (role === "vorschau" && !pausiert && !disposedRef.current) {
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
