import AnalytikApp from "@/components/AnalytikApp";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Analytik – Stallwache",
  description:
    "Langzeitauswertung der KI-Wache: Verlauf, Tagesgang, Brunstrhythmus je Kuh und Reaktionszeiten.",
};

export default function AnalytikSeite() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-6 pt-5">
      <header className="mb-3">
        <h1 className="text-xl font-bold tracking-tight">Analytik</h1>
        <p className="text-xs text-white/50">
          Was die Herde über Wochen erzählt
        </p>
      </header>

      <AnalytikApp />
    </main>
  );
}
