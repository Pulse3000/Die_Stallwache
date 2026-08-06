import { Suspense } from "react";
import AlarmListe from "@/components/AlarmListe";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Alarme – Stallwache",
  description:
    "Aktivitätsprotokoll der KI-Wache: Brunst- und Kalbealarme mit Bild-Replay, filterbar nach Art und Zeitraum.",
};

export default function AlarmeSeite() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-6 pt-5">
      <header className="mb-3">
        <h1 className="text-xl font-bold tracking-tight">Alarme</h1>
        <p className="text-xs text-white/50">
          Aktivitätsprotokoll der KI-Wache
        </p>
      </header>

      {/* useSearchParams (Deeplink aus der Benachrichtigung) braucht eine
          Suspense-Grenze — ohne sie verweigert Next das Rendern. */}
      <Suspense
        fallback={
          <p className="rounded-xl bg-stall-card p-4 text-xs text-white/40 ring-1 ring-white/10">
            Wird geladen …
          </p>
        }
      >
        <AlarmListe />
      </Suspense>
    </main>
  );
}
