"use client";

import { memo } from "react";

type Props = {
  bewegung: string;
  geraeusch: string;
  letzterEvent: string;
  speicher: string;
};

/**
 * "Status auf einen Blick": vier kompakte Kacheln mit kurzen Zustaenden,
 * keine Rohdaten. Rendert unabhaengig vom Videostream (memoisiert, keine
 * Abhaengigkeit zum Player).
 */
function StatusBlock({ bewegung, geraeusch, letzterEvent, speicher }: Props) {
  return (
    <section aria-label="Status auf einen Blick">
      <h2 className="mb-2 text-sm font-semibold text-white/70">
        Status auf einen Blick
      </h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatusCard label="Bewegung" value={bewegung} />
        <StatusCard label="Geräusch" value={geraeusch} />
        <StatusCard label="Letzter Event" value={letzterEvent} />
        <StatusCard label="Speicher" value={speicher} />
      </div>
    </section>
  );
}

function StatusCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
      <p className="text-[10px] uppercase tracking-wider text-white/40">
        {label}
      </p>
      <p className="mt-0.5 truncate text-sm font-semibold">{value}</p>
    </div>
  );
}

export default memo(StatusBlock);
