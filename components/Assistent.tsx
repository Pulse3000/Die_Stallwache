"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { StallEreignis } from "@/lib/ereignis-modell";
import { fmtZeit, TYP_BADGE, TYP_LABEL } from "@/lib/darstellung";

/**
 * Freitext- und Sprachanfragen an den Stall.
 *
 * Die Spracherkennung laeuft im Browser (Web Speech API) — kein Audio-Upload,
 * kein Warten im Funkloch. Wo sie fehlt (Firefox, aeltere iOS-Versionen),
 * verschwindet nur der Mikrofonknopf; das Textfeld bleibt.
 *
 * Serverseitig beantwortet lib/assistent.ts die Frage ueber Vertex AI bzw. die
 * Gemini-API und faellt auf eine lokale Auswertung des Protokolls zurueck,
 * wenn keine KI angebunden oder erreichbar ist.
 */

interface Antwort {
  antwort: string;
  quelle: "lokal" | "vertex-ai" | "gemini-api";
  ereignisse: StallEreignis[];
  hinweis?: string;
}

const BEISPIELE = [
  "Zeig mir alle Aktivitäten von Kuh #42",
  "Gab es heute Nacht Kalbealarme?",
  "Welche Brunstverdachte in den letzten 3 Tagen?",
];

/** Minimalprofil der Web-Speech-API (kein DOM-Typ in TypeScript enthalten). */
interface Spracherkennung {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((e: { results: { 0: { 0: { transcript: string } } } }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

type SpracherkennungKlasse = new () => Spracherkennung;

function spracherkennungKlasse(): SpracherkennungKlasse | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpracherkennungKlasse;
    webkitSpeechRecognition?: SpracherkennungKlasse;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Ob der Browser Spracherkennung kann, ist eine Eigenschaft der Umgebung und
 * aendert sich nie — daher ueber useSyncExternalStore statt ueber einen
 * Effekt. Auf dem Server lautet die Antwort „nein"; damit stimmen Server- und
 * Client-Render bis zur Hydrierung ueberein.
 */
const nieAendernd = () => () => {};

function useSpracheMoeglich(): boolean {
  return useSyncExternalStore(
    nieAendernd,
    () => spracherkennungKlasse() !== null,
    () => false,
  );
}

export default function Assistent() {
  const [frage, setFrage] = useState("");
  const [antwort, setAntwort] = useState<Antwort | null>(null);
  const [laeuft, setLaeuft] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);
  const [hoert, setHoert] = useState(false);
  const spracheMoeglich = useSpracheMoeglich();
  const erkennungRef = useRef<Spracherkennung | null>(null);

  // Laufende Aufnahme beenden, wenn die Seite verlassen wird.
  useEffect(() => () => erkennungRef.current?.stop(), []);

  const fragen = useCallback(async (text: string) => {
    const sauber = text.trim();
    if (!sauber) return;
    setLaeuft(true);
    setFehler(null);
    try {
      const res = await fetch("/api/assistent", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ frage: sauber }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.fehler ?? `HTTP ${res.status}`);
      setAntwort(json as Antwort);
    } catch (e) {
      setFehler(
        e instanceof Error && e.message
          ? e.message
          : "Anfrage fehlgeschlagen – ohne Verbindung kann die Frage nicht beantwortet werden.",
      );
    } finally {
      setLaeuft(false);
    }
  }, []);

  const zuhoeren = useCallback(() => {
    const Klasse = spracherkennungKlasse();
    if (!Klasse) return;
    if (hoert) {
      erkennungRef.current?.stop();
      return;
    }
    const erkennung = new Klasse();
    erkennung.lang = "de-DE";
    erkennung.interimResults = false;
    erkennung.maxAlternatives = 1;
    erkennung.continuous = false;
    erkennung.onresult = (e) => {
      const text = e.results[0][0].transcript;
      setFrage(text);
      // Direkt absenden: im Stall hat der Landwirt selten eine freie Hand.
      void fragen(text);
    };
    erkennung.onerror = () => setHoert(false);
    erkennung.onend = () => setHoert(false);
    erkennungRef.current = erkennung;
    setHoert(true);
    erkennung.start();
  }, [hoert, fragen]);

  return (
    <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void fragen(frage);
        }}
        className="flex gap-2"
      >
        <input
          value={frage}
          onChange={(e) => setFrage(e.target.value)}
          placeholder="Frage zum Stall …"
          aria-label="Frage zum Stall"
          enterKeyHint="search"
          className="min-w-0 flex-1 rounded-xl bg-black/30 px-3 py-2.5 text-sm outline-none ring-1 ring-white/10 placeholder:text-white/30 focus:ring-stall-accent/50"
        />
        {spracheMoeglich && (
          <button
            type="button"
            onClick={zuhoeren}
            aria-label={hoert ? "Aufnahme stoppen" : "Frage sprechen"}
            aria-pressed={hoert}
            className={`shrink-0 rounded-xl px-3 ring-1 ring-white/10 ${
              hoert ? "bg-red-500/30 text-red-200" : "bg-white/10"
            }`}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              aria-hidden
            >
              <rect x="9" y="3" width="6" height="11" rx="3" />
              <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
          </button>
        )}
        <button
          type="submit"
          disabled={laeuft || frage.trim().length === 0}
          className="shrink-0 rounded-xl bg-stall-accent/20 px-3.5 text-sm font-semibold text-stall-accent ring-1 ring-stall-accent/30 disabled:opacity-40"
        >
          {laeuft ? "…" : "Fragen"}
        </button>
      </form>

      {!antwort && !laeuft && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {BEISPIELE.map((b) => (
            <button
              key={b}
              onClick={() => {
                setFrage(b);
                void fragen(b);
              }}
              className="rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-white/50 ring-1 ring-white/10 active:bg-white/15"
            >
              {b}
            </button>
          ))}
        </div>
      )}

      {hoert && (
        <p role="status" className="mt-2 text-[11px] text-red-300/80">
          Ich höre zu … sprich jetzt.
        </p>
      )}
      {fehler && (
        <p role="alert" className="mt-2 rounded-lg bg-red-500/10 p-2.5 text-[11px] text-red-200/90">
          {fehler}
        </p>
      )}

      {antwort && (
        <div className="mt-3">
          <p className="whitespace-pre-wrap rounded-xl bg-black/25 p-3 text-xs leading-relaxed text-white/85">
            {antwort.antwort}
          </p>
          <p className="mt-1 text-[10px] text-white/30">
            {antwort.quelle === "lokal"
              ? "Aus dem Protokoll ausgewertet"
              : antwort.quelle === "vertex-ai"
                ? "Vertex AI (Gemini)"
                : "Gemini API"}
            {antwort.hinweis ? ` · ${antwort.hinweis}` : ""}
          </p>

          {antwort.ereignisse.length > 0 && (
            <ul className="mt-2 divide-y divide-white/5 rounded-xl bg-black/20">
              {antwort.ereignisse.slice(0, 8).map((e) => (
                <li key={e.id} className="flex items-center gap-2 px-2.5 py-2 text-[11px]">
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold ring-1 ${TYP_BADGE[e.typ]}`}
                  >
                    {TYP_LABEL[e.typ]}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-white/70">
                    {e.kuhId ? `${e.kuhId} · ` : ""}
                    {e.nachricht}
                  </span>
                  <span className="shrink-0 font-mono text-white/35">
                    {fmtZeit(e.zeit)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
