"use client";

import { useEffect, useRef, useState } from "react";
import {
  KI_ANSICHT_URL,
  KI_START,
  type KiStand,
  kiTaktMs,
  kiText,
  leseBildZeit,
  naechsterKiStand,
} from "@/lib/ki-ansicht";
import { sichtbaresIntervall } from "@/lib/sichtbares-intervall";

const uhr = (sekunden: number) =>
  new Date(sekunden * 1000).toLocaleTimeString("de-DE", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

/**
 * KI-Ansicht der Stallwache: das letzte Bild, das der Edge-Agent analysiert
 * hat, mit Kaesten und „Kuh #ID" (docs/ki-ansicht-spezifikation.md). Liegt
 * ueber dem Video der Kachel. Abrufe nur bei sichtbarem Tab, nie zwei
 * gleichzeitig; ein altes Bild bleibt abgeblendet stehen, bis ein neues kommt.
 */
export default function KiAnsicht({ datensparen }: { datensparen: boolean }) {
  const [stand, setStand] = useState<KiStand>(KI_START);
  const [src, setSrc] = useState<string | null>(null);
  const standRef = useRef<KiStand>(KI_START);
  const srcRef = useRef<string | null>(null);

  useEffect(() => {
    let aus = false;
    let laeuft = false;
    const ctrl = new AbortController();

    const setze = (neu: KiStand) => {
      standRef.current = neu;
      setStand(neu);
    };

    const laden = async () => {
      if (laeuft || aus) return;
      laeuft = true;
      try {
        const res = await fetch(`${KI_ANSICHT_URL}?t=${Date.now()}`, {
          cache: "no-store",
          signal: ctrl.signal,
        });
        const bildZeit = leseBildZeit(res.headers.get("x-bild-zeit"));
        const neu = naechsterKiStand(standRef.current, res.status, bildZeit, Date.now());
        if (res.status === 200 && bildZeit !== null && bildZeit !== standRef.current.bildZeit) {
          const url = URL.createObjectURL(await res.blob());
          if (aus) {
            URL.revokeObjectURL(url);
            return;
          }
          if (srcRef.current) URL.revokeObjectURL(srcRef.current);
          srcRef.current = url;
          setSrc(url);
        } else {
          void res.body?.cancel(); // gleiches Bild oder Fehlertext: nicht laden
        }
        if (!aus) setze(neu);
      } catch {
        if (!aus) setze(naechsterKiStand(standRef.current, null, null, Date.now()));
      } finally {
        laeuft = false;
      }
    };

    void laden();
    const ende = sichtbaresIntervall(() => void laden(), kiTaktMs(datensparen));
    return () => {
      aus = true;
      ctrl.abort();
      ende();
    };
  }, [datensparen]);

  // Blob-URL beim Ausblenden freigeben
  useEffect(
    () => () => {
      if (srcRef.current) URL.revokeObjectURL(srcRef.current);
    },
    [],
  );

  return (
    <div className="absolute inset-0 bg-black" data-ki-zustand={stand.zustand}>
      {src && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt="KI-Ansicht der Stallwache mit erkannten Kühen"
          className={`absolute inset-0 h-full w-full object-contain ${
            stand.zustand === "bild" ? "" : "opacity-40"
          }`}
        />
      )}
      <p className="absolute inset-x-0 bottom-0 bg-black/75 px-2.5 py-1.5 text-[11px] leading-snug text-white/85">
        {kiText(stand, uhr)}
      </p>
    </div>
  );
}
