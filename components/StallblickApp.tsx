"use client";

import { useCallback, useEffect, useState } from "react";
import LivePlayer from "@/components/LivePlayer";
import PreviewPlayer from "@/components/PreviewPlayer";
import StatusBlock from "@/components/StatusBlock";
import QuickActions from "@/components/QuickActions";
import EventList from "@/components/EventList";
import {
  CAMERAS,
  DEFAULT_MAIN_CAMERA,
  isConfigured,
  otherCamera,
  snapshotUrl,
  type CameraId,
} from "@/lib/config";
import {
  CAMERA_STATE_LABEL,
  DEFAULT_FEATURES,
  type CameraState,
  type FeatureState,
  type FeaturesByCamera,
} from "@/lib/state";

/**
 * Stallblick-Startscreen. Modulreihenfolge (fix):
 * Header -> Hauptkamera (Stallwache) -> Zweitkamera (Futterwache)
 * -> Statusblock -> Schnellaktionen -> Letzte Ereignisse.
 *
 * Rollenwechsel bindet nur die Kamera-Container neu (key={streamName}),
 * die Seite selbst wird nicht neu aufgebaut. Vollbild ist reines CSS auf
 * dem bestehenden Karten-Container – der Stream laeuft ununterbrochen
 * weiter, und beim Zurueckkehren bleibt der Zustand erhalten.
 */
export default function StallblickApp() {
  const [mainCamera, setMainCamera] = useState<CameraId>(DEFAULT_MAIN_CAMERA);
  const [vollbild, setVollbild] = useState(false);
  const [cameraStates, setCameraStates] = useState<
    Record<CameraId, CameraState>
  >({
    stallwache: isConfigured ? "laedt" : "offline",
    futterwache: isConfigured ? "laedt" : "offline",
  });
  const [features, setFeatures] = useState<FeaturesByCamera>({
    stallwache: DEFAULT_FEATURES,
    futterwache: DEFAULT_FEATURES,
  });

  const previewCamera = otherCamera(mainCamera);
  const main = CAMERAS[mainCamera];
  const preview = CAMERAS[previewCamera];
  const mainFeatures = features[mainCamera];

  const handleMainState = useCallback(
    (s: CameraState) =>
      setCameraStates((prev) =>
        prev[mainCamera] === s ? prev : { ...prev, [mainCamera]: s },
      ),
    [mainCamera],
  );
  const handlePreviewState = useCallback(
    (s: CameraState) =>
      setCameraStates((prev) =>
        prev[previewCamera] === s ? prev : { ...prev, [previewCamera]: s },
      ),
    [previewCamera],
  );

  const swapCameras = useCallback(
    () => setMainCamera((prev) => otherCamera(prev)),
    [],
  );

  const toggleFeature = useCallback(
    (key: keyof FeatureState) =>
      setFeatures((prev) => ({
        ...prev,
        [mainCamera]: { ...prev[mainCamera], [key]: !prev[mainCamera][key] },
      })),
    [mainCamera],
  );

  const takeSnapshot = useCallback(() => {
    if (!isConfigured) return;
    window.open(snapshotUrl(CAMERAS[mainCamera].streamName), "_blank");
  }, [mainCamera]);

  // Vollbild: Scroll sperren + per Escape verlassen.
  useEffect(() => {
    if (!vollbild) return;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setVollbild(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [vollbild]);

  const onlineCount = Object.values(cameraStates).filter(
    (s) => s === "online",
  ).length;

  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col gap-5 px-4 pb-10 pt-5">
      {/* 1 · Header – nur Orientierung, kompakt */}
      <header className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold tracking-tight sm:text-2xl">
            Stallblick
          </h1>
          <p className="truncate text-xs text-white/50 sm:text-sm">
            {onlineCount === 2
              ? "2 Kameras online"
              : onlineCount === 1
                ? "1 Kamera online"
                : "Kameras verbinden…"}
          </p>
        </div>
        <span
          aria-label="Systemstatus"
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${
            onlineCount === 2
              ? "bg-stall-accent"
              : onlineCount === 1
                ? "bg-amber-400"
                : "bg-white/30"
          }`}
        />
      </header>

      {/* 2 · Hauptkamera-Karte (Standard: Stallwache) */}
      <section aria-label={`Hauptkamera ${main.label}`}>
        <div
          className={
            vollbild
              ? "fixed inset-0 z-50 bg-black"
              : "relative aspect-video w-full cursor-pointer overflow-hidden rounded-2xl bg-black shadow-2xl ring-1 ring-white/10"
          }
          onClick={vollbild ? undefined : () => setVollbild(true)}
        >
          {/* Player bleibt beim Vollbild-Wechsel gemountet -> Stream laeuft weiter */}
          <LivePlayer
            key={main.streamName}
            streamName={main.streamName}
            onStateChange={handleMainState}
          />

          {mainFeatures.privatsphaere && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/90">
              <p className="text-sm font-semibold text-white/70">
                Privatsphäre aktiv
              </p>
            </div>
          )}

          {/* Kamera-Name + optionale Statushinweise */}
          <div className="pointer-events-none absolute bottom-3 left-3 z-20 flex flex-wrap items-center gap-1.5">
            <span className="rounded-full bg-black/70 px-3 py-1 text-xs font-semibold">
              {main.label}
            </span>
            {mainFeatures.nachtsicht && <Hint>Nachtsicht</Hint>}
            {mainFeatures.bewegung && <Hint>Bewegung</Hint>}
            {mainFeatures.privatsphaere && <Hint>Privatsphäre</Hint>}
          </div>

          {/* Vollbild-Overlay: Zurueck + reduzierte Schnellaktionen */}
          {vollbild && (
            <>
              <button
                onClick={() => setVollbild(false)}
                className="absolute left-3 top-14 z-30 rounded-full bg-black/70 px-4 py-2 text-sm font-semibold ring-1 ring-white/15 transition active:scale-95"
              >
                ‹ Zurück
              </button>
              <div className="absolute inset-x-0 bottom-0 z-30 bg-gradient-to-t from-black/90 to-transparent px-4 pb-4 pt-10">
                <QuickActions
                  compact
                  cameraLabel={main.label}
                  features={mainFeatures}
                  onToggle={toggleFeature}
                  onSnapshot={takeSnapshot}
                />
              </div>
            </>
          )}
        </div>

        {!vollbild && (
          <div className="mt-2 grid grid-cols-3 gap-2">
            <CardButton onClick={() => setVollbild(true)}>Vollbild</CardButton>
            <CardButton onClick={swapCameras}>Tauschen</CardButton>
            <CardButton onClick={takeSnapshot}>Snapshot</CardButton>
          </div>
        )}
      </section>

      {/* 3 · Zweitkamera-Karte (Standard: Futterwache) – leichter gewichtet */}
      <section
        aria-label={`Zweitkamera ${preview.label}`}
        className="flex items-stretch gap-3"
      >
        <div
          className="relative aspect-video w-2/5 shrink-0 cursor-pointer overflow-hidden rounded-xl bg-black ring-1 ring-white/10"
          onClick={swapCameras}
        >
          <PreviewPlayer
            key={preview.streamName}
            streamName={preview.streamName}
            onStateChange={handlePreviewState}
          />
          <span className="absolute left-2 top-2 rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-semibold text-white/80">
            Vorschau
          </span>
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-between py-0.5">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{preview.label}</p>
            <p className="flex items-center gap-1.5 text-xs text-white/50">
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${
                  cameraStates[previewCamera] === "online"
                    ? "bg-stall-accent"
                    : cameraStates[previewCamera] === "laedt"
                      ? "bg-amber-400"
                      : cameraStates[previewCamera] === "instabil"
                        ? "bg-red-400"
                        : "bg-white/30"
                }`}
              />
              {CAMERA_STATE_LABEL[cameraStates[previewCamera]]}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <CardButton
              small
              onClick={() => {
                swapCameras();
                setVollbild(true);
              }}
            >
              Öffnen
            </CardButton>
            <CardButton small onClick={swapCameras}>
              Als Hauptbild
            </CardButton>
          </div>
        </div>
      </section>

      {/* 4 · Statusblock – rendert unabhaengig vom Videostream */}
      <StatusBlock
        bewegung={mainFeatures.bewegung ? "Aktiv" : "Aus"}
        geraeusch="Ruhig"
        letzterEvent="vor 2 Min"
        speicher={mainFeatures.aufnahme ? "Aufnahme an" : "Aufnahme aus"}
      />

      {/* 5 · Schnellaktionen – immer bezogen auf die aktuell grosse Kamera */}
      <QuickActions
        cameraLabel={main.label}
        features={mainFeatures}
        onToggle={toggleFeature}
        onSnapshot={takeSnapshot}
      />

      {/* 6 · Letzte Ereignisse – nachgelagert geladen */}
      <EventList />
    </main>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-black/70 px-2 py-0.5 text-[10px] font-medium text-stall-accent">
      {children}
    </span>
  );
}

function CardButton({
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
      className={`rounded-xl bg-stall-card font-semibold ring-1 ring-white/10 transition active:scale-95 ${
        small ? "px-2 py-2.5 text-xs" : "px-3 py-3 text-sm"
      }`}
    >
      {children}
    </button>
  );
}
