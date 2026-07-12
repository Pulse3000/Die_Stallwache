import LoginForm from "@/components/LoginForm";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Anmelden – Stallblick",
};

export default function LoginPage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-4">
      <div className="mb-6 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/logo-stallwache.jpg"
          alt="Stallwache – Oberer Stollenhof"
          className="mx-auto mb-4 w-full max-w-[220px] rounded-2xl ring-1 ring-white/10"
        />
        <p className="text-xs text-white/50">Bitte anmelden</p>
      </div>
      <LoginForm />
      <p className="mt-8 text-center text-[11px] text-white/30">
        Oberer Stollenhof · seit 1497
      </p>
    </main>
  );
}
