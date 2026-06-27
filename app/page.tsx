import LivePlayer from "@/components/LivePlayer";
import { GO2RTC_URL, isConfigured, STREAM_NAME } from "@/lib/config";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col px-4 pb-10 pt-6">
      <header className="mb-5 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight sm:text-2xl">
            🐄 Die Stallwache
          </h1>
          <p className="text-xs text-white/50 sm:text-sm">
            KI-basierte Brunst- &amp; Kalbueberwachung · Tapo TCA72
          </p>
        </div>
        <span className="rounded-full bg-stall-card px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-white/60 ring-1 ring-white/10">
          Live
        </span>
      </header>

      <LivePlayer />

      <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <InfoCard label="Kamera" value="Tapo TCA72" />
        <InfoCard label="Stream" value={STREAM_NAME} />
        <InfoCard
          label="Bridge"
          value={isConfigured ? "verbunden" : "—"}
        />
      </section>

      {!isConfigured && (
        <div className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-200">
          <p className="font-semibold">Einrichtung erforderlich</p>
          <p className="mt-1 text-amber-200/80">
            Setze die Umgebungsvariable{" "}
            <code className="rounded bg-black/40 px-1">
              NEXT_PUBLIC_GO2RTC_URL
            </code>{" "}
            auf die oeffentliche Cloudflare-Tunnel-Adresse deiner go2rtc-Bridge.
            Die komplette Anleitung steht im README sowie im Ordner{" "}
            <code className="rounded bg-black/40 px-1">/bridge</code>.
          </p>
        </div>
      )}

      <footer className="mt-auto pt-8 text-center text-[11px] text-white/30">
        {GO2RTC_URL ? <>Quelle: {new URL(GO2RTC_URL).host}</> : "Demeter Stollenhof"}
      </footer>
    </main>
  );
}

function InfoCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-stall-card p-3 ring-1 ring-white/10">
      <p className="text-[10px] uppercase tracking-wider text-white/40">
        {label}
      </p>
      <p className="mt-0.5 truncate text-sm font-semibold">{value}</p>
    </div>
  );
}
