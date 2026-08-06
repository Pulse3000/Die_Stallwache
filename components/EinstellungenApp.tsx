"use client";

import { useEffect, useState } from "react";
import PushSchalter from "@/components/PushSchalter";
import { CAMERAS, type CameraId } from "@/lib/config";
import { useEinstellungen } from "@/lib/einstellungen";
import { warteschlangeLaenge, meldeSyncAn } from "@/lib/offline";

/**
 * Einstellungen: Benachrichtigungen, Datenverbrauch, Kameras, Diagnose.
 *
 * Reihenfolge nach Haeufigkeit der Nutzung — Push steht oben, weil das die
 * Einstellung ist, die ueber verpasste Kalbungen entscheidet.
 */
export default function EinstellungenApp() {
  const [werte, aendern] = useEinstellungen();
  const [wartend, setWartend] = useState(0);
  const [speicher, setSpeicher] = useState<string | null>(null);

  useEffect(() => {
    void warteschlangeLaenge().then(setWartend);
    // Wie viel legt die App auf dem Geraet ab? Ehrliche Zahl statt Vertrauen.
    navigator.storage?.estimate?.().then((s) => {
      if (typeof s.usage === "number") {
        setSpeicher(`${(s.usage / 1024 / 1024).toFixed(1)} MB`);
      }
    });
  }, []);

  return (
    <>
      <section aria-label="Benachrichtigungen">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          Benachrichtigungen
        </p>
        <PushSchalter />
      </section>

      <section aria-label="Datenverbrauch" className="mt-4">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          Datenverbrauch &amp; Akku
        </p>
        <div className="flex flex-col gap-2">
          <Schalterzeile
            titel="Livebild erst auf Tippen"
            erklaerung="Das Dashboard zeigt zuerst ein Standbild. Video startet erst, wenn du es startest – spart im Mobilfunk ein Vielfaches."
            an={werte.datensparen}
            umschalten={() => aendern({ datensparen: !werte.datensparen })}
          />
          <Schalterzeile
            titel="Alarmbilder erst auf Tippen"
            erklaerung="Die Alarmliste lädt nur Text. Bilder kommen, wenn du einen Alarm öffnest."
            an={werte.bilderNurAufTippen}
            umschalten={() => aendern({ bilderNurAufTippen: !werte.bilderNurAufTippen })}
          />
          <label className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
            <span className="flex items-baseline justify-between">
              <span className="text-sm font-semibold">Abruf der Ereignisse</span>
              <span className="font-mono text-xs text-white/50">
                alle {werte.abrufSekunden} s
              </span>
            </span>
            <input
              type="range"
              min={10}
              max={120}
              step={5}
              value={werte.abrufSekunden}
              onChange={(e) => aendern({ abrufSekunden: Number(e.target.value) })}
              className="mt-2 w-full accent-stall-accent"
            />
            <span className="mt-1 block text-[11px] leading-relaxed text-white/40">
              Längere Abstände schonen den Akku. Alarme kommen davon unabhängig
              sofort als Push-Benachrichtigung.
            </span>
          </label>
        </div>
      </section>

      <section aria-label="Kameras" className="mt-4">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          Kameras
        </p>
        <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
          <p className="mb-2 text-sm font-semibold">Startkamera</p>
          <div className="flex flex-wrap gap-1.5">
            {CAMERAS.map((c) => (
              <button
                key={c.id}
                onClick={() => aendern({ startKamera: c.id as CameraId })}
                aria-pressed={werte.startKamera === c.id}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ring-1 transition-colors ${
                  werte.startKamera === c.id
                    ? "bg-stall-accent/20 text-stall-accent ring-stall-accent/40"
                    : "bg-white/5 text-white/60 ring-white/10"
                }`}
              >
                {c.name}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-white/40">
            Diese Kamera zeigt das Dashboard groß. Die Zuordnung der Streams
            und die Tuya-Anbindung werden serverseitig konfiguriert
            (siehe .env.example).
          </p>
        </div>
      </section>

      <section aria-label="Gerät" className="mt-4">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          Gerät &amp; Diagnose
        </p>
        <div className="rounded-xl bg-stall-card p-3 text-xs ring-1 ring-white/10">
          <dl className="flex flex-col gap-1.5">
            <Zeile
              begriff="Nicht gesendete Aktionen"
              wert={wartend === 0 ? "keine" : String(wartend)}
            />
            <Zeile begriff="Lokal belegt" wert={speicher ?? "unbekannt"} />
          </dl>
          {wartend > 0 && (
            <button
              onClick={() => void meldeSyncAn().then(() => warteschlangeLaenge().then(setWartend))}
              className="mt-2 w-full rounded-xl bg-white/10 py-2 text-xs font-semibold ring-1 ring-white/10 active:bg-white/25"
            >
              Jetzt nachsenden
            </button>
          )}
          <p className="mt-2 text-[11px] leading-relaxed text-white/40">
            Die Bildanalyse läuft im Stall auf dem Edge-Agenten, nicht in der
            Cloud. Fällt die Verbindung aus, puffert der Agent die Ereignisse
            und liefert sie nach.
          </p>
        </div>
      </section>
    </>
  );
}

function Schalterzeile({
  titel,
  erklaerung,
  an,
  umschalten,
}: {
  titel: string;
  erklaerung: string;
  an: boolean;
  umschalten: () => void;
}) {
  return (
    <button
      onClick={umschalten}
      aria-pressed={an}
      className="flex items-start gap-3 rounded-xl bg-stall-card p-3 text-left ring-1 ring-white/10 active:bg-white/5"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{titel}</span>
        <span className="mt-0.5 block text-[11px] leading-relaxed text-white/45">
          {erklaerung}
        </span>
      </span>
      <span
        className={`mt-0.5 flex h-6 w-11 shrink-0 items-center rounded-full p-0.5 transition-colors ${
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

function Zeile({ begriff, wert }: { begriff: string; wert: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-white/45">{begriff}</dt>
      <dd className="font-mono text-white/80">{wert}</dd>
    </div>
  );
}
