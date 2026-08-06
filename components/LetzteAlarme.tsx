"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useEinstellungen } from "@/lib/einstellungen";
import type { EreignisTyp, StallEreignis } from "@/lib/ereignis-modell";
import { gepufferteEreignisse, merkeEreignisse } from "@/lib/offline";
import { fmtRelativ, TYP_BADGE, TYP_LABEL, TYP_RAND } from "@/lib/darstellung";

/**
 * Alarmuebersicht auf dem Dashboard: Zaehler der letzten 24 Stunden und die
 * drei juengsten Alarme.
 *
 * Bewusst knapp — das Dashboard beantwortet die Frage „muss ich raus?", die
 * ganze Liste steht unter Alarme. Ein laufender Austreibungsalarm faerbt die
 * Kachel rot, weil das die einzige Meldung ist, die keinen Aufschub duldet.
 */

interface ApiAntwort {
  ereignisse: StallEreignis[];
  letzterKontakt: string | null;
  quelle: "edge-agent" | "demo";
}

export default function LetzteAlarme() {
  const [einstellungen] = useEinstellungen();
  const [daten, setDaten] = useState<ApiAntwort | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let beendet = false;
    // Die Ladefunktion lebt im Effekt: sie gehoert zum Abonnement auf die
    // API und soll mit ihm zusammen aufgeraeumt werden.
    const laden = async () => {
      try {
        const res = await fetch("/api/events?stunden=24", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as ApiAntwort;
        if (beendet) return;
        setDaten(json);
        // Der Service Worker markiert Antworten aus seinem Cache.
        setOffline(res.headers.get("x-stallwache-offline") === "1");
        if (json.quelle === "edge-agent") void merkeEreignisse(json.ereignisse);
      } catch {
        const gepuffert = await gepufferteEreignisse();
        if (beendet) return;
        if (gepuffert.length > 0) {
          setDaten({ ereignisse: gepuffert, letzterKontakt: null, quelle: "edge-agent" });
        }
        setOffline(true);
      }
    };
    void laden();
    const t = setInterval(() => void laden(), einstellungen.abrufSekunden * 1000);
    return () => {
      beendet = true;
      clearInterval(t);
    };
  }, [einstellungen.abrufSekunden]);

  const ereignisse = daten?.ereignisse ?? [];
  const zaehle = (...typen: EreignisTyp[]) =>
    ereignisse.filter((e) => typen.includes(e.typ)).length;
  const alarme = ereignisse.filter((e) => e.typ !== "info");
  const dringend = alarme.some((e) => e.typ === "austreibung" && !e.quittiert);

  return (
    <section aria-label="Alarme" className="order-5">
      <div className="mb-1.5 flex items-baseline justify-between">
        <p className="text-[10px] uppercase tracking-wider text-white/40">
          KI-Wache · letzte 24 h
        </p>
        <Link href="/alarme" className="text-[11px] font-semibold text-stall-accent">
          alle ansehen →
        </Link>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Kachel
          label="Kalbung"
          wert={zaehle("kalbeverdacht", "austreibung")}
          warn={dringend}
        />
        <Kachel label="Brunst" wert={zaehle("brunstverdacht")} />
        <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
          <p className="text-[10px] uppercase tracking-wider text-white/40">Agent</p>
          <p className="mt-1 flex items-center gap-1.5 text-xs font-semibold">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${
                daten?.letzterKontakt ? "bg-stall-accent" : "bg-white/25"
              }`}
            />
            <span className="truncate">
              {offline
                ? "offline"
                : daten?.letzterKontakt
                  ? fmtRelativ(daten.letzterKontakt)
                  : "nicht verbunden"}
            </span>
          </p>
        </div>
      </div>

      {dringend && (
        <Link
          href="/alarme"
          className="mt-2 block rounded-xl bg-red-500/20 px-3 py-2.5 text-sm font-bold text-red-200 ring-1 ring-red-400/40"
        >
          Austreibung läuft – jetzt nachsehen →
        </Link>
      )}

      <ul className="mt-2 flex flex-col gap-1.5">
        {alarme.length === 0 ? (
          <li className="rounded-xl bg-stall-card px-3 py-2.5 text-xs text-white/40 ring-1 ring-white/10">
            Keine Alarme – die Herde ist ruhig.
          </li>
        ) : (
          alarme.slice(0, 3).map((e) => (
            <li key={e.id}>
              <Link
                href={`/alarme?id=${encodeURIComponent(e.id)}`}
                className={`flex items-center gap-2 rounded-xl border-l-4 bg-stall-card px-3 py-2 ring-1 ring-white/10 ${TYP_RAND[e.typ]} ${
                  e.quittiert ? "opacity-55" : ""
                }`}
              >
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ring-1 ${TYP_BADGE[e.typ]}`}
                >
                  {TYP_LABEL[e.typ]}
                </span>
                <span className="min-w-0 flex-1 truncate text-xs text-white/75">
                  {e.kuhId ? `${e.kuhId} · ` : ""}
                  {e.nachricht}
                </span>
                <span className="shrink-0 text-[11px] text-white/35">
                  {fmtRelativ(e.zeit)}
                </span>
              </Link>
            </li>
          ))
        )}
      </ul>
    </section>
  );
}

function Kachel({ label, wert, warn = false }: { label: string; wert: number; warn?: boolean }) {
  return (
    <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
      <p className="text-[10px] uppercase tracking-wider text-white/40">{label}</p>
      <p
        className={`mt-1 text-xl font-bold ${
          warn ? "text-red-400" : wert > 0 ? "text-amber-300" : ""
        }`}
      >
        {wert}
      </p>
    </div>
  );
}
