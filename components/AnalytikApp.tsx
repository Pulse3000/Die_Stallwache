"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { AnalytikBericht, BrunstZyklus, TagesPunkt } from "@/lib/analytik";
import { ZEITRAEUME, ZYKLUS_NORMAL_MAX, ZYKLUS_NORMAL_MIN } from "@/lib/analytik";
import { fmtRelativ } from "@/lib/darstellung";

/**
 * Analytik: was die Herde ueber Wochen erzaehlt.
 *
 * Dashboard und Alarme beantworten „muss ich jetzt raus?". Diese Seite
 * beantwortet die Fragen, die man erst nach Wochen stellen kann: Wann in der
 * Nacht passiert es? Wird ruhiger oder unruhiger? Wann ist Kuh #17 wieder
 * brunstig? Reagiere ich eigentlich schnell genug?
 *
 * Die Diagramme sind bewusst reine CSS-Balken statt einer Chart-Bibliothek:
 * Jeder Balken ist ein echtes `<button>` — mit dem Daumen treffbar, per
 * Screenreader vorlesbar — und die Seite bleibt ohne ~100 kB Zusatz-Skript,
 * das im Stallfunk erst einmal geladen werden muesste.
 *
 * Gerechnet wird auf dem Server (`/api/analytik`): Der fertige Bericht ist
 * ein Bruchteil der Rohliste, und im Mobilfunk zaehlt jedes Kilobyte.
 */

/** Langzeitdaten aendern sich langsam — seltener abrufen spart Datenvolumen. */
const ABRUF_SEKUNDEN = 300;

export default function AnalytikApp() {
  const [tage, setTage] = useState<number>(ZEITRAEUME[0]);
  const [bericht, setBericht] = useState<AnalytikBericht | null>(null);
  const [offline, setOffline] = useState(false);
  const [fehler, setFehler] = useState(false);
  // Merkt sich, fuer welchen Zeitraum der angezeigte Stand gilt — sonst zeigt
  // die Seite beim Umschalten kurz die Zahlen des alten Zeitraums als neue.
  const [geladenFuer, setGeladenFuer] = useState<number | null>(null);

  useEffect(() => {
    let beendet = false;
    const laden = async () => {
      try {
        const res = await fetch(`/api/analytik?tage=${tage}`, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as AnalytikBericht;
        if (beendet) return;
        setBericht(json);
        setOffline(res.headers.get("x-stallwache-offline") === "1");
        setFehler(false);
      } catch {
        if (beendet) return;
        // Ohne Netz und ohne Cache-Treffer gibt es hier nichts zu zeigen:
        // Die Auswertung braucht die ganze Liste, der lokale Puffer haelt nur
        // die juengsten Alarme. Lieber ehrlich leer als falsch gerechnet.
        setFehler(true);
        setOffline(true);
      } finally {
        if (!beendet) setGeladenFuer(tage);
      }
    };
    void laden();
    const t = setInterval(() => void laden(), ABRUF_SEKUNDEN * 1000);
    return () => {
      beendet = true;
      clearInterval(t);
    };
  }, [tage]);

  const ladend = geladenFuer !== tage;

  return (
    <>
      {/* Zeitraum */}
      <div
        role="group"
        aria-label="Zeitraum"
        className="mb-3 flex gap-1.5 overflow-x-auto pb-0.5"
      >
        {ZEITRAEUME.map((z) => (
          <button
            key={z}
            type="button"
            onClick={() => setTage(z)}
            aria-pressed={tage === z}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ring-1 transition-colors ${
              tage === z
                ? "bg-stall-accent/20 text-stall-accent ring-stall-accent/40"
                : "bg-stall-card text-white/60 ring-white/10"
            }`}
          >
            {z} Tage
          </button>
        ))}
      </div>

      {bericht?.quelle === "demo" && (
        <p className="mb-3 rounded-xl border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-[11px] text-sky-100/90">
          <span className="font-semibold">Beispieldaten.</span> Der Edge-Agent
          hat noch nichts gemeldet — diese Auswertung beschreibt keine echte
          Herde.
        </p>
      )}

      {offline && !fehler && (
        <p className="mb-3 rounded-xl border border-white/15 bg-white/5 px-3 py-2 text-[11px] text-white/60">
          Kein Netz — die Auswertung zeigt den zuletzt geladenen Stand.
        </p>
      )}

      {fehler && (
        <p className="mb-3 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-[11px] text-red-100/90">
          Auswertung nicht abrufbar — nächster Versuch läuft automatisch.
        </p>
      )}

      {!bericht ? (
        <p className="rounded-xl bg-stall-card p-4 text-xs text-white/40 ring-1 ring-white/10">
          {fehler ? "Keine Daten verfügbar." : "Wird ausgewertet …"}
        </p>
      ) : (
        <div className={ladend ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <Kennzahlen bericht={bericht} />
          <Verlauf punkte={bericht.verlauf} />
          <Tagesgang bericht={bericht} />
          {/* Bezugszeit kommt aus dem Bericht, nicht aus Date.now(): So
              rechnen alle Restlaufzeiten gegen denselben, stabilen Zeitpunkt
              — und ein erneutes Rendern verschiebt keine Termine. */}
          <BrunstKalender
            zyklen={bericht.brunstZyklen}
            bezug={Date.parse(bericht.bis)}
          />
          <Kameras bericht={bericht} />
          <Datenbasis bericht={bericht} />
        </div>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Kennzahlen
// ---------------------------------------------------------------------------

function Kennzahlen({ bericht }: { bericht: AnalytikBericht }) {
  const { gesamt, reaktion, bestaetigung } = bericht;
  const kalbung = gesamt.kalbeverdacht + gesamt.austreibung;

  return (
    <section aria-label="Kennzahlen" className="mb-4 grid grid-cols-2 gap-2">
      <Kachel
        label={`Kalbung (${bericht.zeitraumTage} T)`}
        wert={String(kalbung)}
        fuss={
          gesamt.austreibung > 0
            ? `davon ${gesamt.austreibung} × Austreibung`
            : "keine Austreibung"
        }
        warn={gesamt.austreibung > 0}
      />
      <Kachel
        label={`Brunst (${bericht.zeitraumTage} T)`}
        wert={String(gesamt.brunstverdacht)}
        fuss={
          // Nur Kuehe mit erkanntem Rhythmus zaehlen: „21 Kühe im Rhythmus"
          // waere gelogen, wenn 20 davon erst eine einzige Brunst hatten.
          `${bericht.brunstZyklen.filter((z) => z.bewertung === "regelmaessig").length} mit erkanntem Zyklus`
        }
      />
      <Kachel
        label="Reaktionszeit"
        wert={
          reaktion.medianMinuten === null
            ? "–"
            : reaktion.medianMinuten < 60
              ? `${reaktion.medianMinuten} min`
              : `${(reaktion.medianMinuten / 60).toFixed(1)} h`
        }
        fuss={
          reaktion.alarme === 0
            ? "keine Alarme"
            : `${reaktion.offen} von ${reaktion.alarme} offen`
        }
        warn={reaktion.offen > 0 && reaktion.alarme > 0}
      />
      <Kachel
        label="Verdacht bestätigt"
        wert={
          bestaetigung.quote === null
            ? "–"
            : `${Math.round(bestaetigung.quote * 100)} %`
        }
        fuss={
          bestaetigung.verdachte === 0
            ? "kein Kalbeverdacht"
            : `${bestaetigung.bestaetigt} von ${bestaetigung.verdachte} → Austreibung`
        }
      />
    </section>
  );
}

function Kachel({
  label,
  wert,
  fuss,
  warn = false,
}: {
  label: string;
  wert: string;
  fuss: string;
  warn?: boolean;
}) {
  return (
    <div
      className={`rounded-xl p-3 ring-1 ${
        warn ? "bg-red-500/10 ring-red-400/30" : "bg-stall-card ring-white/10"
      }`}
    >
      <p className="text-[10px] uppercase tracking-wider text-white/40">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{wert}</p>
      <p className="mt-0.5 text-[10px] leading-tight text-white/40">{fuss}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Verlauf ueber Tage
// ---------------------------------------------------------------------------

function Verlauf({ punkte }: { punkte: TagesPunkt[] }) {
  const [gewaehlt, setGewaehlt] = useState<string | null>(null);
  const max = Math.max(1, ...punkte.map((p) => p.gesamt));
  const aktiv = punkte.find((p) => p.tag === gewaehlt) ?? null;
  const summe = punkte.reduce((s, p) => s + p.gesamt, 0);

  return (
    <Block
      titel="Verlauf"
      hinweis={
        aktiv
          ? `${aktiv.label} · ${aktiv.gesamt} ${aktiv.gesamt === 1 ? "Ereignis" : "Ereignisse"}`
          : `${summe} ${summe === 1 ? "Ereignis" : "Ereignisse"} · Balken antippen`
      }
    >
      <div className="flex h-28 items-end gap-[3px]">
        {punkte.map((p) => (
          <button
            key={p.tag}
            type="button"
            onClick={() => setGewaehlt(gewaehlt === p.tag ? null : p.tag)}
            aria-pressed={gewaehlt === p.tag}
            title={`${p.label}: ${p.gesamt}`}
            className={`flex h-full flex-1 flex-col justify-end rounded-t-sm transition-colors ${
              gewaehlt === p.tag ? "bg-white/15" : "hover:bg-white/5"
            }`}
          >
            {/* Reihenfolge von unten: Austreibung (dringend) ganz unten,
                darueber Kalbeverdacht, oben Brunst — dieselbe Farblogik wie
                im Alarmprotokoll (lib/darstellung.ts). */}
            <Segment anteil={p.brunstverdacht / max} farbe="bg-sky-400/80" />
            <Segment anteil={p.kalbeverdacht / max} farbe="bg-amber-400/85" />
            <Segment anteil={p.austreibung / max} farbe="bg-red-500" />
            <span className="sr-only">
              {p.label}: {p.gesamt} Ereignisse
            </span>
          </button>
        ))}
      </div>

      <div className="mt-1 flex justify-between text-[10px] text-white/35">
        <span>{punkte[0]?.label ?? ""}</span>
        <span>{punkte[punkte.length - 1]?.label ?? ""}</span>
      </div>

      {aktiv && (
        <p className="mt-2 text-[11px] text-white/60">
          {aktiv.austreibung > 0 && (
            <span className="text-red-300">{aktiv.austreibung} Austreibung · </span>
          )}
          {aktiv.kalbeverdacht} Kalbeverdacht · {aktiv.brunstverdacht} Brunst
        </p>
      )}

      <Legende />
    </Block>
  );
}

/** Ein Stapelsegment; sichtbar auch dann, wenn es nur ein Ereignis ist. */
function Segment({ anteil, farbe }: { anteil: number; farbe: string }) {
  if (anteil <= 0) return null;
  return (
    <span
      className={`block w-full ${farbe}`}
      style={{ height: `${Math.max(anteil * 100, 4)}%` }}
    />
  );
}

function Legende() {
  return (
    <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-white/45">
      {[
        ["bg-red-500", "Austreibung"],
        ["bg-amber-400/85", "Kalbeverdacht"],
        ["bg-sky-400/80", "Brunst"],
      ].map(([farbe, label]) => (
        <li key={label} className="flex items-center gap-1">
          <span className={`h-2 w-2 rounded-sm ${farbe}`} />
          {label}
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Tagesgang
// ---------------------------------------------------------------------------

/** Als „Nacht" hinterlegte Stunden — der Zeitraum, in dem niemand im Stall ist. */
const NACHT = (stunde: number) => stunde >= 22 || stunde < 6;

function Tagesgang({ bericht }: { bericht: AnalytikBericht }) {
  const [gewaehlt, setGewaehlt] = useState<number | null>(null);
  const punkte = bericht.tagesgang;
  const max = Math.max(1, ...punkte.map((p) => p.gesamt));
  const aktiv = punkte.find((p) => p.stunde === gewaehlt) ?? null;

  const nachts = punkte.filter((p) => NACHT(p.stunde)).reduce((s, p) => s + p.kalbung, 0);
  const kalbungGesamt = punkte.reduce((s, p) => s + p.kalbung, 0);

  return (
    <Block
      titel="Tagesgang"
      hinweis={
        aktiv
          ? `${String(aktiv.stunde).padStart(2, "0")}–${String((aktiv.stunde + 1) % 24).padStart(2, "0")} Uhr · ${aktiv.gesamt}`
          : "Wann passiert es? · Balken antippen"
      }
    >
      <div className="flex h-24 items-end gap-[2px]">
        {punkte.map((p) => (
          <button
            key={p.stunde}
            type="button"
            onClick={() => setGewaehlt(gewaehlt === p.stunde ? null : p.stunde)}
            aria-pressed={gewaehlt === p.stunde}
            title={`${String(p.stunde).padStart(2, "0")} Uhr: ${p.gesamt}`}
            className={`flex h-full flex-1 flex-col justify-end rounded-t-sm transition-colors ${
              gewaehlt === p.stunde
                ? "bg-white/15"
                : NACHT(p.stunde)
                  ? "bg-white/[0.06]"
                  : "hover:bg-white/5"
            }`}
          >
            <Segment anteil={p.brunst / max} farbe="bg-sky-400/80" />
            <Segment anteil={p.kalbung / max} farbe="bg-amber-400/85" />
            <span className="sr-only">
              {p.stunde} Uhr: {p.gesamt} Ereignisse
            </span>
          </button>
        ))}
      </div>

      <div className="mt-1 flex justify-between text-[10px] text-white/35">
        <span>00</span>
        <span>06</span>
        <span>12</span>
        <span>18</span>
        <span>24</span>
      </div>

      <p className="mt-2 text-[11px] leading-snug text-white/50">
        {kalbungGesamt === 0
          ? "Noch keine Kalbe-Ereignisse in diesem Zeitraum."
          : `${Math.round((nachts / kalbungGesamt) * 100)} % der Kalbe-Ereignisse fielen in die Nacht (22–06 Uhr) — die Stunden, in denen niemand im Stall steht.`}
      </p>
      <p className="mt-1 text-[10px] text-white/30">Ortszeit {bericht.zeitzone}</p>
    </Block>
  );
}

// ---------------------------------------------------------------------------
// Brunstkalender
// ---------------------------------------------------------------------------

/**
 * So viele Kuehe zeigt die Liste zunaechst.
 *
 * In einer 60er-Herde stehen sonst 60 Zeilen zwischen Tagesgang und
 * Kamera-Auswertung — und die Seite wird zu der Sorte Wand, an der man
 * aufhoert zu scrollen. Sortiert ist nach naechstem faelligem Termin, oben
 * steht also ohnehin das Dringende.
 */
const ZYKLEN_VORSCHAU = 6;

function BrunstKalender({
  zyklen,
  bezug,
}: {
  zyklen: BrunstZyklus[];
  bezug: number;
}) {
  const [alleZeigen, setAlleZeigen] = useState(false);
  const sichtbar = alleZeigen ? zyklen : zyklen.slice(0, ZYKLEN_VORSCHAU);

  return (
    <Block
      titel="Brunstrhythmus"
      hinweis={`Regelzyklus ${ZYKLUS_NORMAL_MIN}–${ZYKLUS_NORMAL_MAX} Tage`}
    >
      {zyklen.length === 0 ? (
        <p className="text-xs text-white/40">
          Noch keine Brunstmeldung mit Kuh-Zuordnung. Sobald die KI-Wache
          Aufsprünge einer getrackten Kuh meldet, entsteht hier ihr Rhythmus.
        </p>
      ) : (
        <>
          <ul className="divide-y divide-white/5">
            {sichtbar.map((z) => (
              <ZyklusZeile key={z.kuhId} zyklus={z} bezug={bezug} />
            ))}
          </ul>
          {zyklen.length > ZYKLEN_VORSCHAU && (
            <button
              type="button"
              onClick={() => setAlleZeigen((v) => !v)}
              aria-expanded={alleZeigen}
              className="mt-2 w-full rounded-lg bg-white/5 py-2 text-[11px] font-semibold text-white/70"
            >
              {alleZeigen
                ? "weniger anzeigen"
                : `alle ${zyklen.length} Kühe anzeigen`}
            </button>
          )}
        </>
      )}
      <p className="mt-2 text-[10px] leading-snug text-white/30">
        Errechnet aus dem Abstand der Brunstmeldungen — ein Hinweis für den
        Blick in den Stall, keine Trächtigkeitsdiagnose.
      </p>
    </Block>
  );
}

function ZyklusZeile({
  zyklus,
  bezug,
}: {
  zyklus: BrunstZyklus;
  bezug: number;
}) {
  const letzte = zyklus.brunsten[zyklus.brunsten.length - 1];
  const tageBis =
    zyklus.prognose === null
      ? null
      : Math.round((Date.parse(zyklus.prognose) - bezug) / 86_400_000);

  return (
    <li className="flex items-center gap-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold">{zyklus.kuhId}</p>
        <p className="text-[10px] text-white/40">
          {zyklus.brunsten.length}× erfasst · zuletzt {fmtRelativ(letzte, bezug)}
          {zyklus.medianTage !== null && ` · Ø ${zyklus.medianTage} Tage`}
        </p>
      </div>
      <div className="shrink-0 text-right">
        {zyklus.bewertung === "regelmaessig" && tageBis !== null ? (
          <>
            <p className="text-xs font-semibold text-stall-accent">
              {tageBis <= 0 ? "jetzt fällig" : `in ${tageBis} T`}
            </p>
            <p className="text-[10px] text-white/35">nächste Brunst</p>
          </>
        ) : zyklus.bewertung === "auffaellig" ? (
          <p className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold text-amber-300 ring-1 ring-amber-400/30">
            Abstand auffällig
          </p>
        ) : (
          <p className="text-[10px] text-white/35">erst eine Brunst</p>
        )}
      </div>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Kameras
// ---------------------------------------------------------------------------

function Kameras({ bericht }: { bericht: AnalytikBericht }) {
  const max = Math.max(1, ...bericht.kameras.map((k) => k.gesamt));
  return (
    <Block titel="Nach Kamera" hinweis="Woher kommen die Meldungen?">
      {bericht.kameras.length === 0 ? (
        <p className="text-xs text-white/40">
          Keine Ereignisse in diesem Zeitraum.
        </p>
      ) : (
        <ul className="space-y-2">
          {bericht.kameras.map((k) => (
            <li key={k.kamera}>
              <div className="flex items-baseline justify-between text-xs">
                <span className="font-semibold capitalize">{k.kamera}</span>
                <span className="tabular-nums text-white/45">{k.gesamt}</span>
              </div>
              <div className="mt-1 flex h-2 overflow-hidden rounded-full bg-white/5">
                <span
                  className="bg-amber-400/85"
                  style={{ width: `${(k.kalbung / max) * 100}%` }}
                />
                <span
                  className="bg-sky-400/80"
                  style={{ width: `${(k.brunst / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Block>
  );
}

// ---------------------------------------------------------------------------
// Datenbasis
// ---------------------------------------------------------------------------

function Datenbasis({ bericht }: { bericht: AnalytikBericht }) {
  const { datenbasis } = bericht;
  return (
    <section className="mt-4 rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
      <p className="text-[10px] uppercase tracking-wider text-white/40">
        Datenbasis
      </p>
      <p className="mt-1 text-[11px] leading-snug text-white/55">
        {datenbasis.ereignisse}{" "}
        {datenbasis.ereignisse === 1 ? "Ereignis" : "Ereignisse"} im gewählten
        Zeitraum
        {datenbasis.aeltestes &&
          ` · ältester Eintrag ${new Date(datenbasis.aeltestes).toLocaleDateString("de-DE")}`}
        .
      </p>
      {datenbasis.begrenzt && (
        <p className="mt-1.5 text-[11px] leading-snug text-amber-200/80">
          Der Ereignisspeicher reicht nicht über den ganzen Zeitraum zurück —
          die frühen Tage im Verlauf sind unvollständig.
        </p>
      )}
      <p className="mt-1.5 text-[10px] leading-snug text-white/30">
        Die Auswertung liest dieselben Ereignisse wie das{" "}
        <Link href="/alarme" className="underline decoration-white/20">
          Alarmprotokoll
        </Link>
        . Belastbare Erkennungsraten entstehen erst mit gelabelter Validierung
        (docs/metriken.md).
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Bausteine
// ---------------------------------------------------------------------------

function Block({
  titel,
  hinweis,
  children,
}: {
  titel: string;
  hinweis: string;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={titel} className="mt-4">
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <p className="text-[10px] uppercase tracking-wider text-white/40">
          {titel}
        </p>
        <p className="truncate text-[10px] text-white/35">{hinweis}</p>
      </div>
      <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
        {children}
      </div>
    </section>
  );
}
