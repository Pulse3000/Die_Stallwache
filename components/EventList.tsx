"use client";

import { memo, useEffect, useState } from "react";
import { CAMERAS } from "@/lib/config";
import type { StallEvent } from "@/lib/state";

/**
 * Demo-Ereignisse, bis die KI-Erkennung (Roadmap Stufe 2) echte Events
 * liefert. Chronologisch absteigend.
 */
const DEMO_EVENTS: StallEvent[] = [
  { id: "e1", title: "Bewegung erkannt", camera: "stallwache", when: "vor 2 Min", kind: "bewegung" },
  { id: "e2", title: "Aufnahme gestartet", camera: "stallwache", when: "vor 2 Min", kind: "aufnahme" },
  { id: "e3", title: "Geräusch erkannt", camera: "futterwache", when: "vor 14 Min", kind: "geraeusch" },
  { id: "e4", title: "Bewegung erkannt", camera: "futterwache", when: "vor 31 Min", kind: "bewegung" },
  { id: "e5", title: "Bridge wieder verbunden", camera: "stallwache", when: "vor 1 Std", kind: "warnung" },
];

const KIND_DOT: Record<StallEvent["kind"], string> = {
  bewegung: "bg-stall-accent",
  geraeusch: "bg-sky-400",
  warnung: "bg-amber-400",
  aufnahme: "bg-white/50",
};

const PREVIEW_COUNT = 3;

/**
 * "Letzte Ereignisse": ergaenzt den Ueberblick, dominiert ihn nicht.
 * Wird nachgelagert geladen (erst nach dem Mount, wenn der Browser Luft
 * hat) und blockiert damit den initialen Screenaufbau nie.
 */
function EventList() {
  const [events, setEvents] = useState<StallEvent[] | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const w = window as Window & {
      requestIdleCallback?: (cb: () => void) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    if (w.requestIdleCallback) {
      const id = w.requestIdleCallback(() => setEvents(DEMO_EVENTS));
      return () => w.cancelIdleCallback?.(id);
    }
    const t = setTimeout(() => setEvents(DEMO_EVENTS), 300);
    return () => clearTimeout(t);
  }, []);

  const visible = events
    ? expanded
      ? events
      : events.slice(0, PREVIEW_COUNT)
    : [];

  return (
    <section aria-label="Letzte Ereignisse">
      <h2 className="mb-2 text-sm font-semibold text-white/70">
        Letzte Ereignisse
      </h2>
      <div className="overflow-hidden rounded-xl bg-stall-card ring-1 ring-white/10">
        {events === null ? (
          <p className="px-4 py-3.5 text-sm text-white/35">Lädt…</p>
        ) : (
          <>
            <ul className="divide-y divide-white/5">
              {visible.map((ev) => (
                <li key={ev.id} className="flex items-center gap-3 px-4 py-3">
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${KIND_DOT[ev.kind]}`}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">
                      {ev.title}
                    </span>
                    <span className="block text-xs text-white/40">
                      {CAMERAS[ev.camera].label}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-white/40">
                    {ev.when}
                  </span>
                </li>
              ))}
            </ul>
            {!expanded && events.length > PREVIEW_COUNT && (
              <button
                onClick={() => setExpanded(true)}
                className="block w-full border-t border-white/5 px-4 py-3 text-center text-sm font-semibold text-stall-accent transition active:bg-white/5"
              >
                Mehr anzeigen
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}

export default memo(EventList);
