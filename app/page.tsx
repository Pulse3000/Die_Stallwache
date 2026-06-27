import Link from "next/link";
import LivePlayer from "@/components/LivePlayer";
import LiveClock from "@/components/LiveClock";
import { GO2RTC_URL, isConfigured, STREAM_NAME } from "@/lib/config";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col px-4 pb-10 pt-6">
      <header className="mb-5 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/logo-mark.svg"
            alt="Oberer Stollenhof"
            className="h-11 w-11 shrink-0 rounded-lg bg-white/95 p-1 ring-1 ring-white/10"
          />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-bold tracking-tight sm:text-2xl">
              Die Stallwache
            </h1>
            <p className="truncate text-xs text-white/50 sm:text-sm">
              KI-basierte Brunst- &amp; Kalbüberwachung · Tapo TCA72
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 rounded-full bg-stall-card px-3 py-1.5 text-sm ring-1 ring-white/10">
          <span className="h-2 w-2 animate-pulse rounded-full bg-stall-accent" />
          <LiveClock />
        </div>
      </header>

      <LivePlayer />

      <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <InfoCard label="Kamera" value="Tapo TCA72" />
        <InfoCard label="Stream" value={STREAM_NAME} />
        <InfoCard label="Transport" value="WebRTC / HLS" />
        <InfoCard label="Bridge" value={isConfigured ? "konfiguriert" : "—"} />
      </section>

      <Link
        href="/stall3d"
        className="mt-3 flex items-center justify-between rounded-xl bg-stall-card px-4 py-3.5 ring-1 ring-white/10 transition active:scale-[0.99]"
      >
        <span className="flex items-center gap-3">
          <span className="text-xl">🧊</span>
          <span>
            <span className="block text-sm font-semibold">3D-Stall begehen</span>
            <span className="block text-xs text-white/50">
              Interaktiver Rundgang durch die Reihe
            </span>
          </span>
        </span>
        <span className="text-white/40">→</span>
      </Link>

      {!isConfigured && (
        <div className="mt-6 rounded-xl border border-sky-500/30 bg-sky-500/10 p-4 text-sm text-sky-100">
          <p className="font-semibold">Letzter Schritt: Bridge verbinden</p>
          <p className="mt-1 text-sky-100/80">
            Die Webapp ist live. Setze die Umgebungsvariable{" "}
            <code className="rounded bg-black/40 px-1">
              NEXT_PUBLIC_GO2RTC_URL
            </code>{" "}
            auf die öffentliche Cloudflare-Tunnel-Adresse deiner go2rtc-Bridge –
            danach erscheint das Live-Bild automatisch. Anleitung im README und
            im Ordner <code className="rounded bg-black/40 px-1">/bridge</code>.
          </p>
        </div>
      )}

      <footer className="mt-auto flex flex-col items-center gap-3 pt-10">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/logo.svg"
          alt="Oberer Stollenhof – seit 1497"
          className="h-28 w-28 rounded-xl bg-white/95 p-2 ring-1 ring-white/10"
        />
        <p className="text-center text-[11px] text-white/30">
          {GO2RTC_URL ? (
            <>Quelle: {safeHost(GO2RTC_URL)}</>
          ) : (
            "Oberer Stollenhof · seit 1497"
          )}
        </p>
      </footer>
    </main>
  );
}

function safeHost(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
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
