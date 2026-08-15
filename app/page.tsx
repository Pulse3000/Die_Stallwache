import StallblickApp from "@/components/StallblickApp";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Dashboard – Stallwache",
  description:
    "Livebild der Stallkameras und die Alarme der KI-Wache auf einen Blick.",
};

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-6 pt-5">
      <StallblickApp />
      <footer className="mt-auto pt-8">
        <p className="text-center text-[11px] text-white/30">
          Stallwache · Oberer Stollenhof
        </p>
      </footer>
    </main>
  );
}
