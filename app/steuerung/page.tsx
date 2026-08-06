import Assistent from "@/components/Assistent";
import GeraeteSteuerung from "@/components/GeraeteSteuerung";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Steuerung – Stallwache",
  description:
    "Tuya-Geräte im Stall schalten und abfragen, dazu Freitext- und Sprachanfragen an die Stalldaten.",
};

export default function SteuerungSeite() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-6 pt-5">
      <header className="mb-3">
        <h1 className="text-xl font-bold tracking-tight">Steuerung</h1>
        <p className="text-xs text-white/50">Geräte und Anfragen</p>
      </header>

      <section aria-label="Anfrage">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          Frag den Stall
        </p>
        <Assistent />
      </section>

      <section aria-label="Geräte" className="mt-4">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-white/40">
          Tuya-Geräte
        </p>
        <GeraeteSteuerung />
      </section>
    </main>
  );
}
