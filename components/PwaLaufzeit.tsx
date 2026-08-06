"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { meldeSyncAn, warteschlangeLaenge } from "@/lib/offline";

/**
 * Laufzeit-Teil der PWA: Service Worker anmelden, Netzstatus zeigen,
 * offline vorgemerkte Aktionen nachliefern.
 *
 * Rendert selbst nichts, solange alles normal laeuft — nur wenn das Netz weg
 * ist oder Aktionen in der Warteschlange stehen, erscheint ein schmaler
 * Streifen ueber der Tab-Leiste. Der Landwirt soll sehen, ob er gerade
 * verlaesslich informiert wird.
 */
export default function PwaLaufzeit() {
  const router = useRouter();
  const [online, setOnline] = useState(true);
  const [wartend, setWartend] = useState(0);

  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    // Nach dem Laden anmelden, damit der erste Bildaufbau nichts abbekommt.
    const anmelden = () =>
      navigator.serviceWorker
        .register("/sw.js")
        .catch((e) => console.error("Service Worker nicht angemeldet:", e));
    if (document.readyState === "complete") anmelden();
    else window.addEventListener("load", anmelden, { once: true });
  }, []);

  useEffect(() => {
    const pruefen = () => {
      setOnline(navigator.onLine);
      if (navigator.onLine) void meldeSyncAn();
      void warteschlangeLaenge().then(setWartend);
    };
    pruefen();
    window.addEventListener("online", pruefen);
    window.addEventListener("offline", pruefen);

    // Nachrichten des Service Workers: Deeplink aus der Benachrichtigung und
    // Rueckmeldung, dass die Warteschlange leer ist.
    const aufNachricht = (e: MessageEvent) => {
      const daten = e.data as { typ?: string; url?: string } | undefined;
      if (daten?.typ === "navigiere" && daten.url) router.push(daten.url);
      if (daten?.typ === "warteschlange-geleert") void warteschlangeLaenge().then(setWartend);
      if (daten?.typ === "alarm") router.refresh();
    };
    navigator.serviceWorker?.addEventListener("message", aufNachricht);

    const t = setInterval(() => void warteschlangeLaenge().then(setWartend), 30_000);
    return () => {
      window.removeEventListener("online", pruefen);
      window.removeEventListener("offline", pruefen);
      navigator.serviceWorker?.removeEventListener("message", aufNachricht);
      clearInterval(t);
    };
  }, [router]);

  if (online && wartend === 0) return null;

  return (
    <div
      role="status"
      className={`fixed inset-x-0 bottom-[calc(3.25rem+env(safe-area-inset-bottom))] z-40 px-3 py-1.5 text-center text-[11px] font-semibold ${
        online ? "bg-amber-500/90 text-black" : "bg-red-600/90 text-white"
      }`}
    >
      {online
        ? `${wartend} Aktion${wartend === 1 ? "" : "en"} werden nachgesendet …`
        : "Offline – angezeigt wird der zuletzt bekannte Stand"}
    </div>
  );
}
