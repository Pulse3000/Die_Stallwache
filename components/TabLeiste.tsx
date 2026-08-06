"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Untere Navigationsleiste der PWA.
 *
 * Vier Ziele, weil vier die Grenze dessen sind, was am Handy mit dem Daumen
 * sicher getroffen wird — die Reihenfolge folgt der Dringlichkeit im Stall:
 * erst sehen, dann pruefen, dann schalten, dann einstellen.
 *
 * Die Leiste sitzt fest am unteren Rand inklusive `safe-area-inset-bottom`,
 * damit sie auf iPhones nicht unter der Home-Indicator-Leiste klebt.
 */

interface Tab {
  href: string;
  label: string;
  /** Wird auch bei Unterseiten markiert (z.B. /alarme?id=…). */
  praefix?: string;
  symbol: React.ReactNode;
}

const TABS: Tab[] = [
  { href: "/", label: "Dashboard", symbol: <SymbolStall /> },
  { href: "/alarme", label: "Alarme", symbol: <SymbolGlocke /> },
  { href: "/steuerung", label: "Steuerung", symbol: <SymbolSchalter /> },
  { href: "/einstellungen", label: "Einstellungen", symbol: <SymbolZahnrad /> },
];

/** Seiten, auf denen die Leiste stoert statt hilft. */
const OHNE_LEISTE = ["/login", "/offline"];

export default function TabLeiste() {
  const pfad = usePathname();
  const [offeneAlarme, setOffeneAlarme] = useState(0);
  const versteckt = OHNE_LEISTE.includes(pfad);

  // Zaehler fuer den roten Punkt an „Alarme": unquittierte Alarme der letzten
  // 24 h. Bewusst sparsam abgefragt – die Alarmseite selbst pollt haeufiger.
  useEffect(() => {
    if (versteckt) return;
    let beendet = false;
    const laden = async () => {
      try {
        const res = await fetch(
          "/api/events?stunden=24&typ=kalbeverdacht,austreibung,brunstverdacht",
          { cache: "no-store" },
        );
        if (!res.ok) return;
        const json = (await res.json()) as {
          ereignisse: { quittiert: string | null }[];
        };
        if (!beendet) {
          setOffeneAlarme(json.ereignisse.filter((e) => !e.quittiert).length);
        }
      } catch {
        // Offline: der zuletzt bekannte Zaehler bleibt stehen.
      }
    };
    void laden();
    const t = setInterval(laden, 60_000);
    return () => {
      beendet = true;
      clearInterval(t);
    };
  }, [pfad, versteckt]);

  if (versteckt) return null;

  return (
    <nav
      aria-label="Hauptnavigation"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-white/10 bg-stall-bg/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="mx-auto flex max-w-2xl">
        {TABS.map((tab) => {
          const aktiv =
            tab.href === "/" ? pfad === "/" : pfad.startsWith(tab.href);
          return (
            <li key={tab.href} className="flex-1">
              <Link
                href={tab.href}
                aria-current={aktiv ? "page" : undefined}
                className={`flex flex-col items-center gap-0.5 py-2 text-[10px] font-semibold transition-colors ${
                  aktiv ? "text-stall-accent" : "text-white/45"
                }`}
              >
                <span className="relative">
                  {tab.symbol}
                  {tab.href === "/alarme" && offeneAlarme > 0 && (
                    <span
                      className="absolute -right-2 -top-1 min-w-[16px] rounded-full bg-red-500 px-1 text-[9px] font-bold leading-4 text-white"
                      aria-label={`${offeneAlarme} offene Alarme`}
                    >
                      {offeneAlarme > 9 ? "9+" : offeneAlarme}
                    </span>
                  )}
                </span>
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/* Symbole als Inline-SVG: keine Icon-Bibliothek, kein zusaetzlicher Download. */

const svgProps = {
  width: 22,
  height: 22,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function SymbolStall() {
  return (
    <svg {...svgProps}>
      <path d="M3 10.5 12 4l9 6.5" />
      <path d="M5 10v9h14v-9" />
      <circle cx="12" cy="14.5" r="2.2" />
    </svg>
  );
}

function SymbolGlocke() {
  return (
    <svg {...svgProps}>
      <path d="M18 15V10a6 6 0 1 0-12 0v5l-1.5 2.5h15L18 15Z" />
      <path d="M10 20a2 2 0 0 0 4 0" />
    </svg>
  );
}

function SymbolSchalter() {
  return (
    <svg {...svgProps}>
      <rect x="3" y="7" width="18" height="10" rx="5" />
      <circle cx="8.5" cy="12" r="2.6" />
    </svg>
  );
}

function SymbolZahnrad() {
  return (
    <svg {...svgProps}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.5v2.2M12 19.3v2.2M21.5 12h-2.2M4.7 12H2.5M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6M18.7 18.7l-1.6-1.6M6.9 6.9 5.3 5.3" />
    </svg>
  );
}
