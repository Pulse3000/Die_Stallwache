import StallblickApp from "@/components/StallblickApp";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col px-4 pb-8 pt-5">
      <StallblickApp />
      <footer className="mt-auto pt-8">
        <p className="text-center text-[11px] text-white/30">
          Stallblick · Oberer Stollenhof
        </p>
      </footer>
    </main>
  );
}
