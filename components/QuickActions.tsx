"use client";

import { memo } from "react";
import type { FeatureState } from "@/lib/state";

type ToggleKey = keyof FeatureState;

type Props = {
  /** Name der aktuell grossen Kamera – Aktionen beziehen sich immer darauf. */
  cameraLabel: string;
  features: FeatureState;
  onToggle: (key: ToggleKey) => void;
  onSnapshot: () => void;
  /** Reduzierte Darstellung in der Vollbild-Ansicht. */
  compact?: boolean;
};

const TOGGLES: { key: ToggleKey; label: string }[] = [
  { key: "privatsphaere", label: "Privatsphäre" },
  { key: "nachtsicht", label: "Nachtsicht" },
  { key: "bewegung", label: "Bewegung" },
  { key: "sirene", label: "Sirene" },
  { key: "aufnahme", label: "Aufnahme" },
];

/** Reduzierter Satz fuer die Vollbild-Ansicht. */
const COMPACT_KEYS: ToggleKey[] = ["privatsphaere", "nachtsicht", "sirene"];

/**
 * Schnellaktionen fuer die aktuell grosse Kamera. Immer mit Textlabel
 * (nie icon-only), grosse Touch-Flaechen, klarer Aktiv-/Inaktiv-Zustand.
 * Der UI-State ist vom Device-State entkoppelt (siehe lib/state.ts).
 */
function QuickActions({
  cameraLabel,
  features,
  onToggle,
  onSnapshot,
  compact = false,
}: Props) {
  const toggles = compact
    ? TOGGLES.filter((t) => COMPACT_KEYS.includes(t.key))
    : TOGGLES;

  return (
    <section aria-label="Schnellaktionen">
      {!compact && (
        <h2 className="mb-2 text-sm font-semibold text-white/70">
          Schnellaktionen{" "}
          <span className="font-normal text-white/40">· {cameraLabel}</span>
        </h2>
      )}
      <div
        className={`grid gap-2 ${compact ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-3"}`}
      >
        {toggles.map(({ key, label }) => {
          const active = features[key];
          return (
            <button
              key={key}
              onClick={() => onToggle(key)}
              aria-pressed={active}
              className={`min-h-12 rounded-xl px-2 py-3 text-sm font-semibold ring-1 transition active:scale-95 ${
                active
                  ? "bg-stall-accent/15 text-stall-accent ring-stall-accent/60"
                  : "bg-stall-card text-white/80 ring-white/10"
              }`}
            >
              {label}
              <span
                className={`mt-0.5 block text-[10px] font-normal ${
                  active ? "text-stall-accent/80" : "text-white/35"
                }`}
              >
                {active ? "An" : "Aus"}
              </span>
            </button>
          );
        })}
        <button
          onClick={onSnapshot}
          className="min-h-12 rounded-xl bg-stall-card px-2 py-3 text-sm font-semibold text-white/80 ring-1 ring-white/10 transition active:scale-95"
        >
          Snapshot
          <span className="mt-0.5 block text-[10px] font-normal text-white/35">
            Einzelbild
          </span>
        </button>
      </div>
    </section>
  );
}

export default memo(QuickActions);
