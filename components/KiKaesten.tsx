"use client";

import { useEffect, useRef, useState } from "react";
import {
  KI_KAESTEN_URL,
  KI_START,
  KI_TAKT_MS,
  type KiArt,
  type KiBild,
  type KiStand,
  kaesten,
  kiText,
  leseKiBild,
  naechsterKiStand,
  puffere,
  seitenAbweichung,
  videoRechteck,
  videoVersatzS,
  waehleBild,
  wirksamerVersatzS,
} from "@/lib/ki-ansicht";
import { sichtbaresIntervall } from "@/lib/sichtbares-intervall";

const uhr = (sekunden: number) =>
  new Date(sekunden * 1000).toLocaleTimeString("de-DE", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

/** Neu berechnen (Videozeit, Groesse) – ohne Netz, nur bei sichtbarem Tab. */
const ANZEIGE_MS = 250;
/** Oben in der Kachel liegen LIVE, Status und Schalter: Beschriftungen von
 *  Kaesten, die dort beginnen, wandern an die Unterkante des Kastens. */
const LEISTE_OBEN_PX = 34;

const RAHMEN: Record<KiArt, string> = {
  kuh: "border-2 border-stall-accent",
  // Alarm liegt immer oben: keine andere Beschriftung darf ihn verdecken.
  alarm: "z-10 border-[3px] border-red-500",
  unter: "border-2 border-dashed border-amber-300",
};
const MARKE: Record<KiArt, string> = {
  kuh: "bg-stall-accent text-black",
  alarm: "bg-red-600 text-white",
  unter: "bg-amber-300 text-black",
};

interface Anzeige {
  stand: KiStand;
  bild: KiBild | null;
  versatzS: number;
  videoLaeuft: boolean;
  schief: boolean;
  /** Sichtbarer Videobereich in der Kachel (object-contain), Pixel. */
  rechteck: { x: number; y: number; w: number; h: number } | null;
}

/**
 * KI-Kaesten der Stallwache ueber dem laufenden Livebild
 * (docs/ki-ansicht-spezifikation.md): Kuh-Kaesten mit „Kuh #ID", Fruchtblase
 * und Kaelberfuesse, jeweils die Erkennung, die zum gerade gezeigten
 * Videobild passt. Fragt jede Sekunde den Stall-Rechner (wenige hundert
 * Bytes), nur bei sichtbarem Tab und nie zwei Abrufe gleichzeitig. Nimmt
 * keine Klicks an – Vollbild und Knoepfe der Kachel bleiben bedienbar.
 */
export default function KiKaesten({ video }: { video: HTMLVideoElement | null }) {
  const flaecheRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef(video);
  const pufferRef = useRef<KiBild[]>([]);
  const standRef = useRef<KiStand>(KI_START);
  const [anzeige, setAnzeige] = useState<Anzeige>({
    stand: KI_START,
    bild: null,
    versatzS: 0,
    videoLaeuft: false,
    schief: false,
    rechteck: null,
  });

  const aktualisiereRef = useRef(() => {});
  useEffect(() => {
    videoRef.current = video;
    aktualisiereRef.current = () => {
      const v = videoRef.current;
      const flaeche = flaecheRef.current;
      const stand = standRef.current;
      const videoLaeuft = !!v && !v.paused && v.readyState >= 2 && v.videoWidth > 0;
      const ende = v && v.seekable.length ? v.seekable.end(v.seekable.length - 1) : null;
      const versatzS = videoVersatzS(ende, v ? v.currentTime : 0);
      const bild =
        stand.zustand === "bild"
          ? waehleBild(pufferRef.current, wirksamerVersatzS(versatzS, stand.seit, Date.now()))
          : null;
      setAnzeige({
        stand,
        bild,
        versatzS,
        videoLaeuft,
        schief: !!bild && !!v && seitenAbweichung(bild, v.videoWidth, v.videoHeight),
        rechteck:
          v && flaeche
            ? videoRechteck(flaeche.clientWidth, flaeche.clientHeight, v.videoWidth, v.videoHeight)
            : null,
      });
    };
    aktualisiereRef.current();
  }, [video]);

  // Abruf der Erkennungen
  useEffect(() => {
    let aus = false;
    let laeuft = false;
    const ctrl = new AbortController();

    const laden = async () => {
      if (laeuft || aus) return;
      laeuft = true;
      let status: number | null = null;
      let bild: KiBild | null = null;
      try {
        const res = await fetch(KI_KAESTEN_URL, { cache: "no-store", signal: ctrl.signal });
        status = res.status;
        if (res.ok) bild = leseKiBild(await res.json().catch(() => null));
        else void res.body?.cancel();
      } catch {
        status = null;
      } finally {
        laeuft = false;
      }
      if (aus) return;
      if (bild) pufferRef.current = puffere(pufferRef.current, bild);
      standRef.current = naechsterKiStand(standRef.current, status, bild?.zeit ?? null, Date.now());
      aktualisiereRef.current();
    };

    void laden();
    const ende = sichtbaresIntervall(() => void laden(), KI_TAKT_MS);
    return () => {
      aus = true;
      ctrl.abort();
      ende();
    };
  }, []);

  // Videozeit und Kachelgroesse verfolgen
  useEffect(() => {
    const ende = sichtbaresIntervall(() => aktualisiereRef.current(), ANZEIGE_MS);
    const flaeche = flaecheRef.current;
    const beob =
      flaeche && typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => aktualisiereRef.current())
        : null;
    if (flaeche) beob?.observe(flaeche);
    return () => {
      ende();
      beob?.disconnect();
    };
  }, []);

  const { stand, bild, rechteck, videoLaeuft, schief } = anzeige;
  const zeigen = !!bild && !!rechteck && videoLaeuft && !schief;
  const liste = zeigen ? kaesten(bild) : [];

  return (
    <div
      ref={flaecheRef}
      className="pointer-events-none absolute inset-0 isolate"
      data-ki-zustand={stand.zustand}
      data-ki-kaesten={liste.length}
    >
      {zeigen &&
        liste.map((k, i) => {
          const [x1, y1, x2, y2] = k.box;
          const links = rechteck.x + x1 * rechteck.w;
          const oben = rechteck.y + y1 * rechteck.h;
          const breite = (x2 - x1) * rechteck.w;
          // Beschriftung linksbuendig, nur am rechten Rand rechtsbuendig, und
          // auf den Platz bis zum Bildrand begrenzt: Sie bricht um, statt
          // abgeschnitten zu werden oder weit ueber andere Kaesten zu ragen.
          const rechtsBuendig = x1 > 0.6;
          const platz = rechtsBuendig ? links + breite : rechteck.w + 2 * rechteck.x - links;
          return (
            <div
              key={`${k.art}-${k.text}-${i}`}
              data-ki-art={k.art}
              className={`absolute rounded-sm ${RAHMEN[k.art]}`}
              style={{
                left: links,
                top: oben,
                width: breite,
                height: (y2 - y1) * rechteck.h,
              }}
            >
              <span
                className={`absolute w-max rounded-sm px-1 text-[11px] font-semibold leading-4 ${
                  MARKE[k.art]
                } ${oben < LEISTE_OBEN_PX ? "bottom-0" : "bottom-full mb-px"} ${
                  rechtsBuendig ? "right-0" : "left-0"
                }`}
                style={{ maxWidth: Math.max(64, platz - 2) }}
              >
                {k.text}
              </span>
            </div>
          );
        })}
      <p className="absolute inset-x-0 bottom-0 bg-black/75 px-2.5 py-1.5 text-[11px] leading-snug text-white/85">
        {kiText(stand, uhr, {
          videoLaeuft,
          kuehe: bild ? bild.kuehe.length : 0,
          versatzS: anzeige.versatzS,
          passend: !!bild,
          schief,
        })}
      </p>
    </div>
  );
}
