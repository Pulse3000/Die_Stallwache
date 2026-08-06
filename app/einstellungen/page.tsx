import EinstellungenApp from "@/components/EinstellungenApp";
import LogoutButton from "@/components/LogoutButton";
import { authAktiv } from "@/lib/auth";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Einstellungen – Stallwache",
  description:
    "Benachrichtigungen, Datenverbrauch, Kameraauswahl und Diagnose der Stallwache-App.",
};

export default function EinstellungenSeite() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-6 pt-5">
      <header className="mb-3">
        <h1 className="text-xl font-bold tracking-tight">Einstellungen</h1>
        <p className="text-xs text-white/50">Gilt für dieses Gerät</p>
      </header>

      <EinstellungenApp />

      <footer className="mt-6 flex flex-col items-center gap-2">
        <p className="text-center text-[11px] text-white/30">
          Stallwache · Oberer Stollenhof
        </p>
        {authAktiv() && <LogoutButton />}
      </footer>
    </main>
  );
}
