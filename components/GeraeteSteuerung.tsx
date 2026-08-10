"use client";

import { useCallback, useEffect, useState } from "react";
import { aktion } from "@/lib/offline";
import type {
  Funktion,
  GeraeteArt,
  GeraeteZustand,
  MessSpezifikation,
  StatusPunkt,
} from "@/lib/tuya";

/**
 * Steuerung der Tuya-Geraete im Stall (Traenken, Licht, Sensoren, Kameras).
 *
 * Die App zeigt nur, was der Betreiber in TUYA_GERAETE freigegeben hat — ein
 * Tuya-Konto umfasst oft auch Privatgeraete. Welche Schalter ein Geraet hat,
 * meldet Tuya selbst; die Oberflaeche baut sich daraus auf, statt Geraetetypen
 * fest zu verdrahten.
 *
 * Schaltbefehle laufen ueber die Offline-Warteschlange: ausserhalb der
 * Funkzelle wird der Befehl vorgemerkt und beim naechsten Kontakt gesendet.
 * Angezeigt wird immer der von Tuya gemeldete Zustand, nie der gewuenschte —
 * ein Schalter, der behauptet, das Licht sei an, waere schlimmer als keiner.
 */

interface Antwort {
  geraete: GeraeteZustand[];
  fehler?: string;
  hinweis?: string;
}

const ART_SYMBOL: Record<GeraeteArt, string> = {
  traenke: "💧",
  licht: "💡",
  steckdose: "🔌",
  sensor: "📈",
  kamera: "🎥",
  sonstiges: "⚙️",
};

export default function GeraeteSteuerung() {
  const [antwort, setAntwort] = useState<Antwort | null>(null);
  const [schaltend, setSchaltend] = useState<string | null>(null);
  const [meldung, setMeldung] = useState<string | null>(null);
  /** Hochzaehlen erzwingt eine sofortige Neuabfrage (nach dem Schalten). */
  const [nachzaehlen, setNachzaehlen] = useState(0);

  useEffect(() => {
    let beendet = false;
    const laden = async () => {
      try {
        const res = await fetch("/api/tuya/geraete", { cache: "no-store" });
        const json = (await res.json()) as Antwort;
        if (!beendet) setAntwort(json);
      } catch {
        if (!beendet) {
          setAntwort({ geraete: [], fehler: "Geräte nicht erreichbar (offline?)." });
        }
      }
    };
    void laden();
    // Geraetezustaende aendern sich selten – ein ruhiges Intervall reicht und
    // schont Akku wie Tuya-Kontingent.
    const t = setInterval(() => void laden(), 60_000);
    return () => {
      beendet = true;
      clearInterval(t);
    };
  }, [nachzaehlen]);

  const schalten = useCallback(
    async (geraet: GeraeteZustand, code: string, value: string | number | boolean) => {
      setSchaltend(`${geraet.id}:${code}`);
      setMeldung(null);
      const ok = await aktion(
        `/api/tuya/geraete/${encodeURIComponent(geraet.id)}/befehl`,
        { code, value },
      );
      setMeldung(
        ok
          ? `${geraet.name}: geschaltet.`
          : `${geraet.name}: vorgemerkt – wird bei Verbindung gesendet.`,
      );
      setSchaltend(null);
      if (ok) setNachzaehlen((n) => n + 1);
    },
    [],
  );

  if (antwort === null) {
    return (
      <p className="rounded-xl bg-stall-card p-4 text-xs text-white/40 ring-1 ring-white/10">
        Geräte werden abgefragt …
      </p>
    );
  }

  if (antwort.fehler) {
    return (
      <p className="rounded-xl border border-white/10 bg-stall-card p-3 text-xs text-white/60">
        {antwort.fehler}
      </p>
    );
  }

  const geraete = antwort.geraete ?? [];

  return (
    <>
      {antwort.hinweis && (
        <p className="mb-3 rounded-xl border border-sky-500/30 bg-sky-500/10 p-3 text-[11px] text-sky-100/90">
          {antwort.hinweis}
        </p>
      )}
      {meldung && (
        <p role="status" className="mb-3 rounded-xl bg-white/10 p-2.5 text-[11px] text-white/80">
          {meldung}
        </p>
      )}

      {geraete.length === 0 ? (
        <p className="rounded-xl bg-stall-card p-4 text-xs text-white/40 ring-1 ring-white/10">
          Keine Geräte freigegeben.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {geraete.map((g) => (
            <li key={g.id} className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
              <div className="flex items-center gap-2">
                <span aria-hidden className="text-base">
                  {ART_SYMBOL[g.art]}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-semibold">
                  {g.name}
                </span>
                <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-white/50">
                  <span
                    className={`h-2 w-2 rounded-full ${
                      g.online ? "bg-stall-accent" : "bg-red-500"
                    }`}
                  />
                  {g.online ? "Online" : "Offline"}
                </span>
              </div>

              {g.fehler && (
                <p className="mt-2 text-[11px] text-red-300/80">{g.fehler}</p>
              )}

              <Messwerte
                status={g.status}
                funktionen={g.funktionen}
                messSpez={g.messSpez}
              />

              {g.funktionen.length > 0 && (
                <div className="mt-2 flex flex-col gap-2">
                  {g.funktionen.slice(0, 6).map((f) => (
                    <Schalter
                      key={f.code}
                      funktion={f}
                      status={g.status.find((s) => s.code === f.code)}
                      deaktiviert={!g.online || schaltend === `${g.id}:${f.code}`}
                      onSchalten={(wert) => void schalten(g, f.code, wert)}
                    />
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/**
 * Deutsche Beschriftungen fuer die haeufigsten Tuya-Statuscodes.
 * Unbekannte Codes behalten ihren Originalnamen — lieber technisch als falsch.
 */
const MESS_LABEL: Record<string, string> = {
  cur_power: "Leistung",
  cur_voltage: "Spannung",
  cur_current: "Strom",
  add_ele: "Energie",
  power_consumption: "Verbrauch",
  temp_current: "Temperatur",
  humidity_value: "Luftfeuchte",
  battery_percentage: "Batterie",
  countdown_1: "Countdown",
  relay_status: "Verhalten nach Stromausfall",
};

/**
 * Formatiert einen Messwert mit der Skalierung aus dem Geraetemodell.
 * Die Powerwache meldet 2301 fuer 230,1 V — ohne `scale` waere das Unsinn.
 */
function messwert(wert: StatusPunkt["value"], spez?: MessSpezifikation): string {
  if (typeof wert !== "number" || !spez) return String(wert);
  const skaliert = spez.scale ? wert / 10 ** spez.scale : wert;
  const text = skaliert.toLocaleString("de-DE", {
    maximumFractionDigits: spez.scale ?? 0,
  });
  return spez.unit ? `${text} ${spez.unit}` : text;
}

/** Statuspunkte ohne zugehoerigen Schalter — reine Messwerte (Sensoren, Zaehler). */
function Messwerte({
  status,
  funktionen,
  messSpez,
}: {
  status: StatusPunkt[];
  funktionen: Funktion[];
  messSpez: GeraeteZustand["messSpez"];
}) {
  const nurMessung = status.filter((s) => !funktionen.some((f) => f.code === s.code));
  if (nurMessung.length === 0) return null;
  return (
    <dl className="mt-2 grid grid-cols-2 gap-1.5">
      {nurMessung.slice(0, 6).map((s) => (
        <div key={s.code} className="rounded-lg bg-black/20 px-2 py-1.5">
          <dt className="truncate text-[10px] uppercase tracking-wider text-white/35">
            {MESS_LABEL[s.code] ?? s.code}
          </dt>
          <dd className="truncate text-xs font-semibold text-white/80">
            {messwert(s.value, messSpez?.[s.code])}
          </dd>
        </div>
      ))}
    </dl>
  );
}

interface Wertebereich {
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  range?: string[];
}

function bereich(f: Funktion): Wertebereich {
  try {
    return f.values ? (JSON.parse(f.values) as Wertebereich) : {};
  } catch {
    return {};
  }
}

/** Baut das passende Bedienelement zum gemeldeten Funktionstyp. */
function Schalter({
  funktion,
  status,
  deaktiviert,
  onSchalten,
}: {
  funktion: Funktion;
  status?: StatusPunkt;
  deaktiviert: boolean;
  onSchalten: (wert: string | number | boolean) => void;
}) {
  const label = funktion.name || funktion.code;
  const typ = funktion.type.toLowerCase();

  if (typ === "boolean") {
    const an = status?.value === true;
    return (
      <button
        onClick={() => onSchalten(!an)}
        disabled={deaktiviert}
        aria-pressed={an}
        className="flex items-center justify-between rounded-lg bg-black/20 px-3 py-2.5 text-xs font-semibold disabled:opacity-40"
      >
        <span className="truncate">{label}</span>
        <span
          className={`ml-3 flex h-6 w-11 shrink-0 items-center rounded-full p-0.5 transition-colors ${
            an ? "bg-stall-accent" : "bg-white/20"
          }`}
        >
          <span
            className={`h-5 w-5 rounded-full bg-white transition-transform ${
              an ? "translate-x-5" : ""
            }`}
          />
        </span>
      </button>
    );
  }

  if (typ === "enum") {
    const werte = bereich(funktion).range ?? [];
    if (werte.length === 0) return null;
    return (
      <div className="rounded-lg bg-black/20 px-3 py-2">
        <p className="mb-1.5 truncate text-[11px] font-semibold text-white/70">{label}</p>
        <div className="flex flex-wrap gap-1.5">
          {werte.map((w) => (
            <button
              key={w}
              onClick={() => onSchalten(w)}
              disabled={deaktiviert}
              aria-pressed={status?.value === w}
              className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ring-1 disabled:opacity-40 ${
                status?.value === w
                  ? "bg-stall-accent/20 text-stall-accent ring-stall-accent/40"
                  : "bg-white/5 text-white/60 ring-white/10"
              }`}
            >
              {w}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (typ === "integer" || typ === "value") {
    const b = bereich(funktion);
    const min = b.min ?? 0;
    const max = b.max ?? 100;
    const wert = typeof status?.value === "number" ? status.value : min;
    return (
      <label className="block rounded-lg bg-black/20 px-3 py-2">
        <span className="mb-1.5 flex items-baseline justify-between text-[11px] font-semibold text-white/70">
          <span className="truncate">{label}</span>
          <span className="font-mono text-white/50">
            {wert}
            {b.unit ?? ""}
          </span>
        </span>
        <input
          type="range"
          min={min}
          max={max}
          step={b.step && b.step > 0 ? b.step : 1}
          defaultValue={wert}
          disabled={deaktiviert}
          // Erst beim Loslassen senden – sonst ein Tuya-Aufruf je Pixel.
          onPointerUp={(e) => onSchalten(Number((e.target as HTMLInputElement).value))}
          onKeyUp={(e) => onSchalten(Number((e.target as HTMLInputElement).value))}
          className="w-full accent-stall-accent disabled:opacity-40"
        />
      </label>
    );
  }

  // Freitext-/JSON-Funktionen bekommen bewusst kein Bedienelement: raten waere
  // hier schlimmer als weglassen.
  return null;
}
