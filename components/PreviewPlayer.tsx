"use client";

import { memo, useEffect, useRef, useState } from "react";
import { isConfigured, snapshotUrl } from "@/lib/config";
import type { CameraState } from "@/lib/state";

const REFRESH_MS = 5000;

type Props = {
  /** Name des go2rtc-Streams fuer die Vorschau. */
  streamName: string;
  onStateChange?: (state: CameraState) => void;
};

/**
 * Vorschau der Zweitkamera: bewusst KEIN zweiter Live-Stream auf dem
 * Startscreen, sondern ein alle 5 s aktualisiertes Einzelbild (frame.jpeg
 * von go2rtc). Das haelt die volle Stream-Prioritaet bei der Hauptkamera
 * und die Vorschau trotzdem aktuell.
 */
function PreviewPlayer({ streamName, onStateChange }: Props) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const hadFrameRef = useRef(false);
  const onStateChangeRef = useRef(onStateChange);
  onStateChangeRef.current = onStateChange;

  useEffect(() => {
    hadFrameRef.current = false;
    setSrc(null);
    setFailed(false);

    if (!isConfigured) {
      onStateChangeRef.current?.("offline");
      return;
    }
    onStateChangeRef.current?.("laedt");

    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    // Bild vorab laden und erst nach Erfolg anzeigen -> kein Flackern.
    const refresh = () => {
      const img = new Image();
      img.onload = () => {
        if (disposed) return;
        hadFrameRef.current = true;
        setFailed(false);
        setSrc(img.src);
        onStateChangeRef.current?.("online");
        timer = setTimeout(refresh, REFRESH_MS);
      };
      img.onerror = () => {
        if (disposed) return;
        setFailed(true);
        onStateChangeRef.current?.(hadFrameRef.current ? "instabil" : "offline");
        timer = setTimeout(refresh, REFRESH_MS * 2);
      };
      img.src = `${snapshotUrl(streamName)}&t=${Date.now()}`;
    };
    refresh();

    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
    };
  }, [streamName]);

  return (
    <div className="absolute inset-0 bg-gradient-to-b from-slate-800 via-slate-900 to-black">
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          className="h-full w-full object-cover"
          draggable={false}
        />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs text-white/40">
            {!isConfigured
              ? "Warte auf Bridge"
              : failed
                ? "Keine Verbindung"
                : "Lädt…"}
          </span>
        </div>
      )}
    </div>
  );
}

export default memo(PreviewPlayer);
