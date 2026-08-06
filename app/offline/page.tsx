export const metadata = {
  title: "Offline – Stallwache",
};

/**
 * Rueckfallseite des Service Workers, wenn eine noch nie besuchte Seite ohne
 * Netz aufgerufen wird. Bereits besuchte Seiten kommen aus dem Cache und
 * landen hier gar nicht.
 */
export default function OfflineSeite() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="h-14 w-14 rounded-full bg-white/10 ring-1 ring-white/15" aria-hidden />
      <h1 className="text-xl font-bold tracking-tight">Keine Verbindung</h1>
      <p className="text-sm leading-relaxed text-white/60">
        Diese Seite war noch nicht auf dem Gerät. Alarme, die bereits
        angekommen sind, stehen weiterhin unter <strong>Alarme</strong> — auch
        ohne Netz.
      </p>
      <p className="text-xs text-white/40">
        Die Analyse läuft unabhängig davon weiter im Stall. Neue Ereignisse
        werden vom Edge-Agenten gepuffert und nachgeliefert, sobald die
        Verbindung zurück ist.
      </p>
      <a
        href="/alarme"
        className="rounded-xl bg-white/10 px-4 py-2.5 text-sm font-semibold ring-1 ring-white/10 active:bg-white/25"
      >
        Zu den Alarmen
      </a>
    </main>
  );
}
