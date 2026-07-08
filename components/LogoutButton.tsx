"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/** Dezenter Abmelde-Link; erscheint nur, wenn der Passwortschutz aktiv ist. */
export default function LogoutButton() {
  const router = useRouter();
  const [laedt, setLaedt] = useState(false);

  const abmelden = async () => {
    setLaedt(true);
    try {
      await fetch("/api/logout", { method: "POST" });
    } catch {
      // ignorieren – Cookie kann auch abgelaufen sein
    }
    router.replace("/login");
    router.refresh();
  };

  return (
    <button
      onClick={abmelden}
      disabled={laedt}
      className="text-[11px] text-white/30 underline-offset-2 transition hover:text-white/60 hover:underline disabled:opacity-50"
    >
      {laedt ? "Abmelden …" : "Abmelden"}
    </button>
  );
}
