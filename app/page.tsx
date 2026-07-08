import StallblickApp from "@/components/StallblickApp";
import LogoutButton from "@/components/LogoutButton";
import { authAktiv } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-8 pt-5">
      <StallblickApp />
      <footer className="mt-auto flex flex-col items-center gap-2 pt-8">
        <p className="text-center text-[11px] text-white/30">
          Stallblick · Oberer Stollenhof
        </p>
        {authAktiv() && <LogoutButton />}
      </footer>
    </main>
  );
}
