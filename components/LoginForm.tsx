"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [passwort, setPasswort] = useState("");
  const [fehler, setFehler] = useState(false);
  const [laedt, setLaedt] = useState(false);

  const anmelden = async (e: React.FormEvent) => {
    e.preventDefault();
    setLaedt(true);
    setFehler(false);
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passwort }),
      });
      if (!res.ok) {
        setFehler(true);
        setLaedt(false);
        return;
      }
      // Ziel aus ?weiter=… – nur interne Pfade zulassen (Open-Redirect-Schutz).
      // Backslash muss abgewiesen werden: Browser normalisieren "\" zu "/",
      // sonst wuerde "/\evil.com" zu "//evil.com" (protokoll-relativ, extern).
      const weiter = params.get("weiter") ?? "";
      const intern =
        weiter.startsWith("/") &&
        !weiter.startsWith("//") &&
        !weiter.includes("\\");
      const ziel = intern ? weiter : "/";
      router.replace(ziel);
      router.refresh();
    } catch {
      setFehler(true);
      setLaedt(false);
    }
  };

  return (
    <form onSubmit={anmelden} className="flex flex-col gap-3">
      <input
        type="password"
        value={passwort}
        onChange={(e) => setPasswort(e.target.value)}
        placeholder="Passwort"
        autoFocus
        autoComplete="current-password"
        className="rounded-xl bg-stall-card px-4 py-3 text-sm outline-none ring-1 ring-white/10 focus:ring-stall-accent/50"
      />
      {fehler && (
        <p className="text-center text-xs text-red-400">
          Falsches Passwort – bitte erneut versuchen.
        </p>
      )}
      <button
        type="submit"
        disabled={laedt || passwort.length === 0}
        className="rounded-xl bg-stall-accent px-4 py-3 text-sm font-semibold text-black transition active:scale-95 disabled:opacity-40"
      >
        {laedt ? "Anmelden …" : "Anmelden"}
      </button>
    </form>
  );
}
