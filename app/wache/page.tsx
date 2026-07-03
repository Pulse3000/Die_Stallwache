import Link from "next/link";
import WacheDashboard from "@/components/WacheDashboard";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "KI-Wache – Stallblick",
  description:
    "Alarm-Dashboard der KI-basierten Brunst- und Kalbeerkennung im Stall.",
};

export default function WachePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-8 pt-5">
      <header className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold tracking-tight">KI-Wache</h1>
          <p className="truncate text-xs text-white/50">
            Brunst- &amp; Kalbeerkennung
          </p>
        </div>
        <Link
          href="/"
          className="shrink-0 rounded-xl bg-white/10 px-3 py-2 text-xs font-semibold ring-1 ring-white/10 transition-colors active:bg-white/25"
        >
          ← Stallblick
        </Link>
      </header>

      <WacheDashboard />

      <footer className="mt-auto pt-8">
        <p className="text-center text-[11px] text-white/30">
          Analyse läuft lokal im Stall · Dashboard zeigt gemeldete Ereignisse
        </p>
      </footer>
    </main>
  );
}
