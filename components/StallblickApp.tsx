"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import CameraStream from "@/components/CameraStream";
import {
  CAMERAS,
  type CameraId,
  type CameraState,
  cameraById,
  isConfigured,
  snapshotSupported,
  snapshotUrl,
} from "@/lib/config";

const STATE_LABEL: Record<CameraState, string> = {
  online: "Online",
  offline: "Offline",
  laedt: "Lädt",
  instabil: "Instabil",
};

const STATE_DOT: Record<CameraState, string> = {
  online: "bg-stall-accent",
  offline: "bg-red-500",
  laedt: "bg-amber-400",
  instabil: "bg-orange-400",
};

interface Ereignis {
  zeit: string;
  text: string;
}

function jetzt(): string {
  return new Date().toLocaleTimeString("de-DE", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Stallblick-Hauptscreen.
 *
 * Beide CameraStream-Instanzen bleiben dauerhaft an derselben Stelle im
 * React-Baum gemountet; Rollenwechsel und Vollbild aendern nur Props bzw.
 * CSS-Klassen (order / fixed) – kein Seiten-Neuaufbau, kein Re-Mount der
 * Videocontainer. Status und Ereignisse rendern unabhaengig vom Stream.
 */
export default function StallblickApp() {
  // View-State: hauptkamera = Stallwache (Default) | Futterwache
  const [hauptkamera, setHauptkamera] = useState<CameraId>("stallwache");
  const [vollbild, setVollbild] = useState(false);

  const [camStates, setCamStates] = useState<Record<CameraId, CameraState>>({
    stallwache: isConfigured ? "laedt" : "offline",
    futterwache: isConfigured ? "laedt" : "offline",
  });

  // Ereignisliste laedt nachgelagert – blockiert den ersten Bildaufbau nicht.
  const [ereignisse, setEreignisse] = useState<Ereignis[]>([]);
  const [ereignisseSichtbar, setEreignisseSichtbar] = useState(false);
  const pendingRef = useRef<Ereignis[]>([]);

  const addEreignis = useCallback((text: string) => {
    const e = { zeit: jetzt(), text };
    pendingRef.current = [e, ...pendingRef.current].slice(0, 6);
    setEreignisse(pendingRef.current);
  }, []);

  useEffect(() => {
    const t = setTimeout(() => setEreignisseSichtbar(true), 900);
    return () => clearTimeout(t);
  }, []);

  const onCamState = useCallback(
    (id: CameraId, state: CameraState) => {
      setCamStates((prev) => {
        if (prev[id] === state) return prev;
        return { ...prev, [id]: state };
      });
      if (state === "online" || state === "offline") {
        addEreignis(`${cameraById(id).name} ist ${STATE_LABEL[state].toLowerCase()}`);
      }
    },
    [addEreignis],
  );

  const zweitkamera: CameraId =
    hauptkamera === "stallwache" ? "futterwache" : "stallwache";

  const tauschen = useCallback(() => {
    setHauptkamera((prev) => {
      const next: CameraId = prev === "stallwache" ? "futterwache" : "stallwache";
      addEreignis(`${cameraById(next).name} ist jetzt Hauptbild`);
      return next;
    });
  }, [addEreignis]);

  const oeffnen = useCallback(
    (id: CameraId) => {
      setHauptkamera((prev) => {
        if (prev !== id) addEreignis(`${cameraById(id).name} ist jetzt Hauptbild`);
        return id;
      });
      setVollbild(true);
    },
    [addEreignis],
  );

  // Scroll-Lock im Vollbild; Zurueck erhaelt den Zustand ohne Neuaufbau.
  useEffect(() => {
    document.body.style.overflow = vollbild ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [vollbild]);

  const snapshot = useCallback(async () => {
    const cam = cameraById(hauptkamera);
    if (!isConfigured) {
      addEreignis(`Snapshot nicht möglich – Bridge nicht verbunden`);
      return;
    }
    if (!snapshotSupported) {
      addEreignis(
        `Snapshot nicht verfügbar – MediaMTX hat kein Einzelbild-Endpoint`,
      );
      return;
    }
    try {
      const res = await fetch(`${snapshotUrl(cam.streamName)}&t=${Date.now()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `stallblick-${cam.id}-${Date.now()}.jpg`;
      a.click();
      URL.revokeObjectURL(url);
      addEreignis(`Snapshot von ${cam.name} gespeichert`);
    } catch {
      addEreignis(`Snapshot von ${cam.name} fehlgeschlagen`);
    }
  }, [hauptkamera, addEreignis]);

  const onlineCount = CAMERAS.filter((c) => camStates[c.id] === "online").length;
  const systemOk = onlineCount === CAMERAS.length;

  return (
    <>
      {/* 1 · Header – nur Orientierung, kompakt */}
      <header className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold tracking-tight">
            Stallblick
          </h1>
          <p className="truncate text-xs text-white/50">
            {systemOk
              ? "2 Kameras online"
              : `${onlineCount} von 2 Kameras online`}
          </p>
        </div>
        <div
          className="flex shrink-0 items-center gap-2 rounded-full bg-stall-card px-3 py-1.5 text-xs ring-1 ring-white/10"
          aria-label="Systemstatus"
        >
          <span
            className={`h-2 w-2 rounded-full ${
              systemOk ? "bg-stall-accent" : onlineCount > 0 ? "bg-amber-400" : "bg-red-500"
            }`}
          />
          <span className="text-white/70">System</span>
        </div>
      </header>

      {/* 2+3 · Kamera-Karten: DOM-Reihenfolge stabil, Rollen nur per Props/CSS */}
      <section className="flex flex-col gap-3">
        {CAMERAS.map((cam) => {
          const istHaupt = cam.id === hauptkamera;
          const state = camStates[cam.id];
          const rolle = istHaupt ? "haupt" : "vorschau";

          return (
            <article
              key={cam.id}
              className={
                vollbild && istHaupt
                  ? "fixed inset-0 z-50 flex flex-col bg-black"
                  : `rounded-2xl bg-stall-card ring-1 ring-white/10 ${
                      istHaupt ? "order-1" : "order-2"
                    }`
              }
            >
              {/* Video-Container – wird beim Rollenwechsel nur umgebunden */}
              <div
                role={istHaupt && !vollbild ? "button" : undefined}
                tabIndex={istHaupt && !vollbild ? 0 : undefined}
                aria-label={istHaupt && !vollbild ? "Vollbild öffnen" : undefined}
                onClick={istHaupt && !vollbild ? () => setVollbild(true) : undefined}
                onKeyDown={
                  istHaupt && !vollbild
                    ? (e) => e.key === "Enter" && setVollbild(true)
                    : undefined
                }
                className={
                  vollbild && istHaupt
                    ? "relative min-h-0 flex-1"
                    : `relative overflow-hidden ${
                        istHaupt
                          ? "aspect-video cursor-pointer rounded-t-2xl"
                          : "aspect-[21/9] rounded-t-2xl"
                      }`
                }
              >
                <CameraStream camera={cam} role={rolle} onState={onCamState} />

                {/* Statuszeile ueber dem Bild */}
                <div className="pointer-events-none absolute left-2.5 top-2.5 flex items-center gap-2">
                  {istHaupt && state === "online" && (
                    <span className="rounded bg-red-600 px-2 py-0.5 text-[11px] font-bold tracking-wide text-white">
                      LIVE
                    </span>
                  )}
                  <span className="flex items-center gap-1.5 rounded bg-black/70 px-2 py-0.5 text-[11px] font-semibold">
                    <span className={`h-1.5 w-1.5 rounded-full ${STATE_DOT[state]}`} />
                    {cam.name} · {STATE_LABEL[state]}
                  </span>
                  {!istHaupt && (
                    <span className="rounded bg-black/70 px-2 py-0.5 text-[11px] text-white/60">
                      Vorschau
                    </span>
                  )}
                </div>
              </div>

              {vollbild && istHaupt ? (
                /* Vollbild: reduzierte Schnellaktionen */
                <div className="grid shrink-0 grid-cols-3 gap-2 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
                  <ActionButton onClick={() => setVollbild(false)}>
                    ← Zurück
                  </ActionButton>
                  <ActionButton onClick={tauschen}>Tauschen</ActionButton>
                  <ActionButton onClick={snapshot}>Snapshot</ActionButton>
                </div>
              ) : istHaupt ? (
                <div className="grid grid-cols-3 gap-2 p-2.5">
                  <ActionButton onClick={() => setVollbild(true)}>
                    Vollbild
                  </ActionButton>
                  <ActionButton onClick={tauschen}>Tauschen</ActionButton>
                  <ActionButton onClick={snapshot}>Snapshot</ActionButton>
                </div>
              ) : (
                <div className="flex items-center gap-2 p-2.5">
                  <p className="min-w-0 flex-1 truncate text-xs text-white/50">
                    {cam.ort}
                  </p>
                  <ActionButton small onClick={() => oeffnen(cam.id)}>
                    Öffnen
                  </ActionButton>
                  <ActionButton small onClick={tauschen}>
                    Als Hauptbild
                  </ActionButton>
                </div>
              )}
            </article>
          );
        })}

        {/* 4 · Statusblock – kompakt, unabhaengig vom Videostream */}
        <section
          aria-label="Status"
          className="order-3 grid grid-cols-2 gap-2"
        >
          {CAMERAS.map((cam) => (
            <div
              key={cam.id}
              className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10"
            >
              <p className="text-[10px] uppercase tracking-wider text-white/40">
                {cam.name} · {cam.id === hauptkamera ? "Hauptbild" : "Vorschau"}
              </p>
              <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
                <span
                  className={`h-2 w-2 rounded-full ${STATE_DOT[camStates[cam.id]]}`}
                />
                {STATE_LABEL[camStates[cam.id]]}
              </p>
            </div>
          ))}
        </section>

        {/* 5 · Schnellaktionen – beziehen sich auf die aktuell grosse Kamera */}
        <section aria-label="Schnellaktionen" className="order-4">
          <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
            Schnellaktionen · {cameraById(hauptkamera).name}
          </p>
          <div className="grid grid-cols-3 gap-2">
            <ActionButton onClick={() => setVollbild(true)}>Vollbild</ActionButton>
            <ActionButton onClick={tauschen}>Tauschen</ActionButton>
            <ActionButton onClick={snapshot}>Snapshot</ActionButton>
          </div>
        </section>

        {/* KI-Wache: Brunst- & Kalbeerkennung (eigene Seite, laedt nichts vor) */}
        <a
          href="/wache"
          className="order-5 flex items-center justify-between rounded-xl bg-stall-card px-3 py-3 text-sm font-semibold ring-1 ring-white/10 transition-colors active:bg-white/10"
        >
          <span>
            KI-Wache
            <span className="ml-2 text-xs font-normal text-white/50">
              Brunst- &amp; Kalbeerkennung
            </span>
          </span>
          <span className="text-white/40">→</span>
        </a>

        {/* 6 · Letzte Ereignisse – nachgelagert geladen */}
        <section aria-label="Letzte Ereignisse" className="order-6">
          <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
            Letzte Ereignisse
          </p>
          <div className="rounded-xl bg-stall-card ring-1 ring-white/10">
            {!ereignisseSichtbar ? (
              <p className="p-3 text-xs text-white/40">Wird geladen …</p>
            ) : ereignisse.length === 0 ? (
              <p className="p-3 text-xs text-white/40">
                Noch keine Ereignisse.
              </p>
            ) : (
              <ul className="divide-y divide-white/5">
                {ereignisse.map((e, i) => (
                  <li
                    key={`${e.zeit}-${i}`}
                    className="flex items-baseline gap-3 px-3 py-2 text-xs"
                  >
                    <span className="shrink-0 font-mono text-white/40">
                      {e.zeit}
                    </span>
                    <span className="text-white/80">{e.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </section>
    </>
  );
}

function ActionButton({
  children,
  onClick,
  small = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  small?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-xl bg-white/10 font-semibold ring-1 ring-white/10 transition-colors active:bg-white/25 ${
        small ? "px-3 py-2 text-xs" : "px-3 py-3 text-sm"
      }`}
    >
      {children}
    </button>
  );
}
