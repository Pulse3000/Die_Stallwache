"use client";

import { useEffect, useState } from "react";

/** Lokale Uhrzeit, clientseitig (vermeidet Hydration-Mismatch). */
export default function LiveClock() {
  const [now, setNow] = useState<string>("");

  useEffect(() => {
    const tick = () =>
      setNow(
        new Date().toLocaleTimeString("de-DE", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
      );
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return <span className="font-mono tabular-nums">{now || "--:--:--"}</span>;
}
