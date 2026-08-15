"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Replay der Alarm-Bildserie.
 *
 * Der Edge-Agent schickt zum Alarm mehrere komprimierte Einzelbilder aus den
 * Sekunden davor und danach. Nacheinander abgespielt zeigen sie die Bewegung
 * — das ist der Unterschied zwischen „irgendwas war da" und „die Fruchtblase
 * ist draussen". Ein Video waere schoener, kostet aber ein Vielfaches an
 * Daten; die Serie kommt auch durch schmale Mobilfunkverbindungen.
 *
 * Geladen wird erst auf Tippen (`sofortLaden = false`), damit die Alarmliste
 * im Funkloch nicht an Bildern haengt.
 */
export default function AlarmBilder({
  ereignisId,
  anzahl,
  sofortLaden = false,
}: {
  ereignisId: string;
  anzahl: number;
  sofortLaden?: boolean;
}) {
  const [geladen, setGeladen] = useState(sofortLaden);
  const [index, setIndex] = useState(0);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stoppen = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setLaeuft(false);
  }, []);

  useEffect(() => stoppen, [stoppen]);

  const abspielen = useCallback(() => {
    if (anzahl < 2) return;
    stoppen();
    setIndex(0);
    setLaeuft(true);
    timer.current = setInterval(() => {
      setIndex((i) => {
        if (i + 1 >= anzahl) {
          // Am Ende stehenbleiben statt zu schleifen: das letzte Bild ist das
          // aussagekraeftigste und soll betrachtbar sein.
          if (timer.current) clearInterval(timer.current);
          timer.current = null;
          setLaeuft(false);
          return i;
        }
        return i + 1;
      });
    }, 700);
  }, [anzahl, stoppen]);

  if (anzahl <= 0) return null;

  if (!geladen) {
    return (
      <button
        onClick={() => setGeladen(true)}
        className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-white/15 py-3 text-xs font-semibold text-white/60 active:bg-white/10"
      >
        {anzahl} Alarmbild{anzahl === 1 ? "" : "er"} laden
      </button>
    );
  }

  return (
    <div className="mt-2">
      <div className="relative overflow-hidden rounded-xl bg-black ring-1 ring-white/10">
        {/* Kein next/image: die Bilder kommen aus einer API-Route mit eigenem
            Cache-Header, den der Service Worker fuer das Offline-Replay nutzt. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/events/${encodeURIComponent(ereignisId)}/bild/${index}`}
          alt={`Alarmbild ${index + 1} von ${anzahl}`}
          className="aspect-video w-full object-contain"
          onError={() => setFehler(true)}
        />
        {fehler && (
          <p className="absolute inset-0 flex items-center justify-center bg-black/70 p-4 text-center text-xs text-white/60">
            Bild nicht mehr verfügbar (Alarmbilder werden nach 7 Tagen
            gelöscht).
          </p>
        )}
        {anzahl > 1 && (
          <span className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-0.5 font-mono text-[11px] text-white/70">
            {index + 1}/{anzahl}
          </span>
        )}
      </div>

      {anzahl > 1 && (
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={laeuft ? stoppen : abspielen}
            className="rounded-lg bg-white/10 px-3 py-1.5 text-xs font-semibold ring-1 ring-white/10 active:bg-white/25"
          >
            {laeuft ? "Pause" : "Abspielen"}
          </button>
          <div className="flex flex-1 gap-1">
            {Array.from({ length: anzahl }, (_, i) => (
              <button
                key={i}
                aria-label={`Bild ${i + 1}`}
                onClick={() => {
                  stoppen();
                  setIndex(i);
                }}
                className={`h-1.5 flex-1 rounded-full transition-colors ${
                  i === index ? "bg-stall-accent" : "bg-white/15"
                }`}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
