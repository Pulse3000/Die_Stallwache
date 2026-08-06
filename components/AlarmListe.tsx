"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import AlarmBilder from "@/components/AlarmBilder";
import { useEinstellungen } from "@/lib/einstellungen";
import type { EreignisTyp, StallEreignis } from "@/lib/ereignis-modell";
import { gepufferteEreignisse, aktion, merkeEreignisse } from "@/lib/offline";
import { fmtRelativ, fmtZeit, TYP_BADGE, TYP_LABEL, TYP_RAND } from "@/lib/darstellung";

/**
 * Aktivitaetsprotokoll: alle Ereignisse eines Zeitraums, filterbar, mit
 * Bild-Replay und Quittierung.
 *
 * Grundeinstellung sind die letzten 24 Stunden — das ist der Zeitraum, den
 * ein Landwirt morgens durchsieht. Der Filter arbeitet serverseitig, damit
 * ueber Mobilfunk nur das wandert, was auch angezeigt wird.
 *
 * Offline zeigt die Liste den gepufferten Stand aus IndexedDB, ergaenzt um
 * Alarme, die der Service Worker per Push empfangen hat.
 */

type FilterId = "alle" | "kalbung" | "brunst" | "system";

const FILTER: { id: FilterId; label: string; typen: EreignisTyp[] }[] = [
  { id: "alle", label: "Alle", typen: [] },
  { id: "kalbung", label: "Kalbung", typen: ["kalbeverdacht", "austreibung"] },
  { id: "brunst", label: "Brunst", typen: ["brunstverdacht"] },
  { id: "system", label: "System", typen: ["info"] },
];

const ZEITRAEUME = [
  { stunden: 24, label: "24 h" },
  { stunden: 72, label: "3 Tage" },
  { stunden: 168, label: "7 Tage" },
];

interface ApiAntwort {
  ereignisse: StallEreignis[];
  letzterKontakt: string | null;
  quelle: "edge-agent" | "demo";
}

export default function AlarmListe() {
  const suche = useSearchParams();
  const [einstellungen] = useEinstellungen();

  const [filter, setFilter] = useState<FilterId>("alle");
  const [stunden, setStunden] = useState(24);
  const [daten, setDaten] = useState<ApiAntwort | null>(null);
  const [offline, setOffline] = useState(false);
  const [quittiert, setQuittiert] = useState<Set<string>>(new Set());

  const typen = useMemo(
    () => FILTER.find((f) => f.id === filter)?.typen ?? [],
    [filter],
  );
  // Ein Textschluessel je Abfrage: taugt als Effekt-Abhaengigkeit (anders als
  // das Array) und zugleich als Marke fuer „dieser Stand ist schon geladen".
  const abfrage = `${stunden}|${typen.join(",")}`;
  const [geladenFuer, setGeladenFuer] = useState<string | null>(null);
  const ladend = geladenFuer !== abfrage;

  // Deeplink aus der Benachrichtigung: den gemeinten Alarm gleich aufklappen.
  // Abgeleitet statt im Effekt gesetzt — `undefined` heisst „noch nichts
  // angetippt", danach gilt die Wahl des Landwirts.
  const zielId = suche.get("id");
  const [angetippt, setAngetippt] = useState<string | null | undefined>(undefined);
  const offen = angetippt === undefined ? zielId : angetippt;

  const zielRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    if (zielId && zielRef.current) {
      zielRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [zielId, daten]);

  useEffect(() => {
    let beendet = false;
    const laden = async () => {
      const p = new URLSearchParams({ stunden: String(stunden) });
      if (typen.length > 0) p.set("typ", typen.join(","));
      try {
        const res = await fetch(`/api/events?${p}`, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as ApiAntwort;
        if (beendet) return;
        setDaten(json);
        // Der Service Worker markiert Antworten aus seinem Cache.
        setOffline(res.headers.get("x-stallwache-offline") === "1");
        if (json.quelle === "edge-agent") void merkeEreignisse(json.ereignisse);
      } catch {
        // Kein Netz und kein Cache-Treffer: eigener Puffer.
        const gepuffert = await gepufferteEreignisse();
        if (beendet) return;
        setDaten({
          ereignisse: gepuffert,
          letzterKontakt: null,
          quelle: "edge-agent",
        });
        setOffline(true);
      } finally {
        if (!beendet) setGeladenFuer(abfrage);
      }
    };
    void laden();
    const t = setInterval(() => void laden(), einstellungen.abrufSekunden * 1000);
    return () => {
      beendet = true;
      clearInterval(t);
    };
    // `typen` haengt eindeutig an `abfrage` – daher reicht der Schluessel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [abfrage, einstellungen.abrufSekunden]);

  const quittieren = useCallback(async (id: string) => {
    // Sofort ausblenden – die Nachlieferung erledigt notfalls die
    // Warteschlange, der Landwirt soll nicht auf das Netz warten.
    setQuittiert((v) => new Set(v).add(id));
    await aktion(`/api/events/${encodeURIComponent(id)}/quittieren`);
  }, []);

  const ereignisse = (daten?.ereignisse ?? []).filter(
    (e) => typen.length === 0 || typen.includes(e.typ),
  );
  const istDemo = daten?.quelle === "demo";

  return (
    <>
      {/* Filter: Art */}
      <div
        role="group"
        aria-label="Nach Art filtern"
        className="flex gap-1.5 overflow-x-auto pb-1"
      >
        {FILTER.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            aria-pressed={filter === f.id}
            className={`shrink-0 rounded-full px-3.5 py-1.5 text-xs font-semibold ring-1 transition-colors ${
              filter === f.id
                ? "bg-stall-accent/20 text-stall-accent ring-stall-accent/40"
                : "bg-stall-card text-white/60 ring-white/10"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Filter: Zeitraum */}
      <div
        role="group"
        aria-label="Zeitraum wählen"
        className="mt-2 flex gap-1.5"
      >
        {ZEITRAEUME.map((z) => (
          <button
            key={z.stunden}
            onClick={() => setStunden(z.stunden)}
            aria-pressed={stunden === z.stunden}
            className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold ring-1 transition-colors ${
              stunden === z.stunden
                ? "bg-white/15 text-white ring-white/20"
                : "bg-transparent text-white/45 ring-white/10"
            }`}
          >
            {z.label}
          </button>
        ))}
      </div>

      {offline && (
        <p className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-2.5 text-[11px] text-amber-100/90">
          Offline – angezeigt wird der zuletzt gespeicherte Stand.
        </p>
      )}
      {istDemo && (
        <p className="mt-3 rounded-xl border border-sky-500/30 bg-sky-500/10 p-2.5 text-[11px] text-sky-100/90">
          <span className="font-semibold">Demo-Daten.</span> Sobald der
          Edge-Agent Ereignisse meldet, stehen hier echte Alarme.
        </p>
      )}

      <ul className="mt-3 flex flex-col gap-2">
        {ladend && ereignisse.length === 0 && (
          <li className="rounded-xl bg-stall-card p-4 text-xs text-white/40 ring-1 ring-white/10">
            Wird geladen …
          </li>
        )}
        {!ladend && ereignisse.length === 0 && (
          <li className="rounded-xl bg-stall-card p-4 text-xs text-white/40 ring-1 ring-white/10">
            Keine Einträge im gewählten Zeitraum.
          </li>
        )}

        {ereignisse.map((e) => {
          const istOffen = offen === e.id;
          const istQuittiert = Boolean(e.quittiert) || quittiert.has(e.id);
          return (
            <li
              key={e.id}
              ref={e.id === zielId ? zielRef : undefined}
              className={`rounded-xl border-l-4 bg-stall-card ring-1 ring-white/10 ${TYP_RAND[e.typ]} ${
                istQuittiert ? "opacity-55" : ""
              }`}
            >
              <button
                onClick={() => setAngetippt(istOffen ? null : e.id)}
                aria-expanded={istOffen}
                className="w-full px-3 py-2.5 text-left"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-bold ring-1 ${TYP_BADGE[e.typ]}`}
                  >
                    {TYP_LABEL[e.typ]}
                  </span>
                  {e.kuhId && (
                    <span className="truncate text-xs font-semibold">{e.kuhId}</span>
                  )}
                  <span className="ml-auto shrink-0 text-[11px] text-white/40">
                    {fmtRelativ(e.zeit)}
                  </span>
                </div>
                <p className="mt-1 text-xs text-white/75">{e.nachricht}</p>
                <p className="mt-0.5 text-[10px] text-white/40">
                  {fmtZeit(e.zeit)} · Kamera {e.kamera}
                  {e.konfidenz !== null &&
                    ` · Konfidenz ${Math.round(e.konfidenz * 100)} %`}
                  {e.bilder > 0 && ` · ${e.bilder} Bild${e.bilder === 1 ? "" : "er"}`}
                  {istQuittiert && " · gesehen"}
                </p>
              </button>

              {istOffen && (
                <div className="px-3 pb-3">
                  {e.bilder > 0 ? (
                    <AlarmBilder
                      ereignisId={e.id}
                      anzahl={e.bilder}
                      sofortLaden={!einstellungen.bilderNurAufTippen}
                    />
                  ) : (
                    <p className="rounded-lg bg-black/20 p-2.5 text-[11px] text-white/40">
                      Kein Alarmbild übermittelt — der Agent lief zu diesem
                      Zeitpunkt ohne Bildversand.
                    </p>
                  )}
                  {e.typ !== "info" && !istQuittiert && (
                    <button
                      onClick={() => void quittieren(e.id)}
                      className="mt-2 w-full rounded-xl bg-white/10 py-2.5 text-xs font-semibold ring-1 ring-white/10 active:bg-white/25"
                    >
                      Gesehen
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
