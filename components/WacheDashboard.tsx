"use client";

import { useCallback, useEffect, useState } from "react";
import type { EreignisTyp, StallEreignis } from "@/lib/events";

interface ApiAntwort {
  ereignisse: StallEreignis[];
  letzterKontakt: string | null;
  quelle: "edge-agent" | "demo";
}

const TYP_LABEL: Record<EreignisTyp, string> = {
  kalbeverdacht: "Kalbeverdacht",
  austreibung: "Austreibung",
  brunstverdacht: "Brunstverdacht",
  info: "Info",
};

const TYP_BADGE: Record<EreignisTyp, string> = {
  kalbeverdacht: "bg-amber-500/20 text-amber-300 ring-amber-400/30",
  austreibung: "bg-red-500/25 text-red-300 ring-red-400/40",
  brunstverdacht: "bg-sky-500/20 text-sky-300 ring-sky-400/30",
  info: "bg-white/10 text-white/60 ring-white/15",
};

const POLL_INTERVALL = 15_000;

function fmtZeit(iso: string): string {
  const d = new Date(iso);
  const heute = new Date().toDateString() === d.toDateString();
  const uhr = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  return heute
    ? uhr
    : `${d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })} ${uhr}`;
}

/**
 * KI-Wache: Alarm-Dashboard fuer Brunst- & Kalbeerkennung.
 *
 * Die Analyse laeuft lokal im Stall (Edge-Agent, siehe /edge-agent im Repo);
 * dieses Dashboard zeigt nur die gemeldeten Ereignisse. Sanftes Polling,
 * kein Einfluss auf die Kamera-Streams der Startseite.
 */
export default function WacheDashboard() {
  const [daten, setDaten] = useState<ApiAntwort | null>(null);
  const [fehler, setFehler] = useState(false);

  const laden = useCallback(async () => {
    try {
      const res = await fetch("/api/events", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setDaten((await res.json()) as ApiAntwort);
      setFehler(false);
    } catch {
      setFehler(true);
    }
  }, []);

  useEffect(() => {
    void laden();
    const t = setInterval(() => void laden(), POLL_INTERVALL);
    return () => clearInterval(t);
  }, [laden]);

  const ereignisse = daten?.ereignisse ?? [];
  const istDemo = daten?.quelle === "demo";
  const h24 = Date.now() - 24 * 3600 * 1000;
  const zaehle = (typ: EreignisTyp) =>
    ereignisse.filter((e) => e.typ === typ && Date.parse(e.zeit) >= h24).length;

  const alarme = ereignisse.filter((e) => e.typ !== "info");
  const meldungen = ereignisse.filter((e) => e.typ === "info");

  return (
    <>
      {istDemo && (
        <div className="mb-3 rounded-xl border border-sky-500/30 bg-sky-500/10 p-3 text-xs text-sky-100/90">
          <span className="font-semibold">Demo-Daten.</span> Sobald der
          Edge-Agent im Stall Ereignisse meldet (POST /api/events), erscheinen
          hier echte Alarme. Einrichtung: Ordner{" "}
          <code className="rounded bg-black/40 px-1">edge-agent/</code> im Repo.
        </div>
      )}
      {fehler && (
        <div className="mb-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-100/90">
          Ereignisse konnten nicht geladen werden – nächster Versuch läuft
          automatisch.
        </div>
      )}

      {/* Statuskacheln */}
      <section aria-label="Status" className="grid grid-cols-3 gap-2">
        <StatusKachel
          label="Kalbung (24 h)"
          wert={zaehle("kalbeverdacht") + zaehle("austreibung")}
          warn={zaehle("austreibung") > 0}
        />
        <StatusKachel label="Brunst (24 h)" wert={zaehle("brunstverdacht")} />
        <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
          <p className="text-[10px] uppercase tracking-wider text-white/40">
            Edge-Agent
          </p>
          <p className="mt-1 flex items-center gap-1.5 text-sm font-semibold">
            <span
              className={`h-2 w-2 rounded-full ${
                daten?.letzterKontakt ? "bg-stall-accent" : "bg-white/25"
              }`}
            />
            {daten?.letzterKontakt
              ? `zuletzt ${fmtZeit(daten.letzterKontakt)}`
              : "nicht verbunden"}
          </p>
        </div>
      </section>

      {/* Alarme */}
      <section aria-label="Alarme" className="mt-4">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          Alarme &amp; Verdachtsfälle
        </p>
        <div className="rounded-xl bg-stall-card ring-1 ring-white/10">
          {alarme.length === 0 ? (
            <p className="p-3 text-xs text-white/40">
              Keine Alarme – die Herde ist ruhig.
            </p>
          ) : (
            <ul className="divide-y divide-white/5">
              {alarme.map((e) => (
                <li key={e.id} className="px-3 py-2.5">
                  <div className="flex items-center gap-2">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-bold ring-1 ${TYP_BADGE[e.typ]}`}
                    >
                      {TYP_LABEL[e.typ]}
                    </span>
                    {e.kuhId && (
                      <span className="text-xs font-semibold">{e.kuhId}</span>
                    )}
                    <span className="ml-auto shrink-0 font-mono text-[11px] text-white/40">
                      {fmtZeit(e.zeit)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-white/75">{e.nachricht}</p>
                  <p className="mt-0.5 text-[10px] text-white/40">
                    Kamera: {e.kamera}
                    {e.konfidenz !== null &&
                      ` · Konfidenz ${(e.konfidenz * 100).toFixed(0)} %`}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* Systemmeldungen */}
      <section aria-label="Systemmeldungen" className="mt-4">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          Systemmeldungen
        </p>
        <div className="rounded-xl bg-stall-card ring-1 ring-white/10">
          {meldungen.length === 0 ? (
            <p className="p-3 text-xs text-white/40">Keine Meldungen.</p>
          ) : (
            <ul className="divide-y divide-white/5">
              {meldungen.map((e) => (
                <li
                  key={e.id}
                  className="flex items-baseline gap-3 px-3 py-2 text-xs"
                >
                  <span className="shrink-0 font-mono text-white/40">
                    {fmtZeit(e.zeit)}
                  </span>
                  <span className="text-white/70">{e.nachricht}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* Erkennnungslogik – kompakte Erklaerung */}
      <section aria-label="Erkennungslogik" className="mt-4">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          So erkennt die KI
        </p>
        <div className="rounded-xl bg-stall-card p-3 text-xs leading-relaxed text-white/60 ring-1 ring-white/10">
          <p>
            <span className="font-semibold text-white/80">Kalbeverdacht:</span>{" "}
            Schwanzwinkel &gt; 45° in mehr als 20 % der Frames eines
            30-Minuten-Fensters (filtert Koten/Fliegenabwehr heraus).
          </p>
          <p className="mt-1.5">
            <span className="font-semibold text-white/80">Austreibung:</span>{" "}
            Fruchtblase oder Kälberfüße mit &gt; 80 % Konfidenz – sofortiger
            Alarm, Zeitfilter wird übersprungen.
          </p>
          <p className="mt-1.5">
            <span className="font-semibold text-white/80">Brunstverdacht:</span>{" "}
            Aufsprung-/Duldungsverhalten über mehrere Sekunden.
          </p>
        </div>
      </section>
    </>
  );
}

function StatusKachel({
  label,
  wert,
  warn = false,
}: {
  label: string;
  wert: number;
  warn?: boolean;
}) {
  return (
    <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
      <p className="text-[10px] uppercase tracking-wider text-white/40">
        {label}
      </p>
      <p
        className={`mt-1 text-xl font-bold ${warn ? "text-red-400" : wert > 0 ? "text-amber-300" : ""}`}
      >
        {wert}
      </p>
    </div>
  );
}
