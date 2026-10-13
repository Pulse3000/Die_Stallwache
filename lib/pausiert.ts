"use client";

/**
 * Streams nur bei Sicht: Welche Kamerakacheln gerade pausiert sein sollen.
 *
 * Seit alle Kameras beim Oeffnen live laufen, wuerden auch Kacheln streamen,
 * die niemand sieht – weiter unten auf der Seite oder in einem Tab im
 * Hintergrund. Das kostet Mobilfunkdaten, Akku und bei Tuya jedes Mal einen
 * API-Aufruf beim Neuverbinden. Daher:
 *
 *   • Tab verborgen (Bildschirm aus, andere App)  → sofort pausieren.
 *   • Kachel aus dem Bild gescrollt               → nach VERZOEGERUNG_MS
 *     pausieren (kurzes Wegscrollen kostet keine neue Verbindung).
 *   • Wieder sichtbar                             → sofort fortsetzen.
 *
 * Die Kacheln werden ueber das Attribut `data-kamera="<id>"` gefunden.
 * Anfangszustand ist „pausiert", bis der erste Sichtbarkeitsbefund vorliegt:
 * So verbindet sich eine Kachel unterhalb des Bildschirms gar nicht erst.
 * Ohne IntersectionObserver (sehr alte Browser) wird nie pausiert.
 */

import { useEffect, useState } from "react";

export const VERZOEGERUNG_MS = 5000;
/**
 * Beim Laden verschiebt sich das Layout noch kurz (Inhalte kommen nach): Ein
 * erster Sichtbarkeitsbefund gilt deshalb erst nach dieser Beruhigungszeit.
 * Sonst verbindet sich eine Kachel am Bildrand, die gleich darauf nach unten
 * rutscht – samt Tuya-API-Aufruf.
 */
export const BERUHIGUNG_MS = 350;
/** Kachel gilt schon kurz vor dem Bildrand als sichtbar (kein Nachladen im Scrollen). */
const RAND = "150px";

export function usePausiert(ids: readonly string[]): Record<string, boolean> {
  const schluessel = ids.join(",");
  const [pausiert, setPausiert] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(ids.map((id) => [id, true])),
  );

  useEffect(() => {
    const liste = schluessel ? schluessel.split(",") : [];
    if (typeof IntersectionObserver === "undefined") {
      // Kein Beobachter verfuegbar: nie pausieren (asynchron, nicht im Effekt-Rumpf).
      const t = setTimeout(
        () => setPausiert(Object.fromEntries(liste.map((id) => [id, false]))),
        0,
      );
      return () => clearTimeout(t);
    }

    const imBild = new Map<string, boolean>();
    const timer = new Map<string, ReturnType<typeof setTimeout>>();
    let tabSichtbar = document.visibilityState === "visible";
    let bereit = false; // erst nach der Beruhigungszeit gelten Befunde

    const setze = (id: string, p: boolean) =>
      setPausiert((alt) => (alt[id] === p ? alt : { ...alt, [id]: p }));

    const bewerte = (id: string) => {
      const t = timer.get(id);
      if (t) clearTimeout(t);
      timer.delete(id);
      if (!bereit || !imBild.has(id)) return; // Anfangszustand (pausiert) bleibt
      if (tabSichtbar && imBild.get(id)) return setze(id, false);
      if (!tabSichtbar) return setze(id, true); // Tab verborgen: sofort
      timer.set(id, setTimeout(() => setze(id, true), VERZOEGERUNG_MS));
    };

    const beobachter = new IntersectionObserver(
      (eintraege) => {
        for (const e of eintraege) {
          const id = (e.target as HTMLElement).dataset.kamera;
          if (!id) continue;
          imBild.set(id, e.isIntersecting);
          bewerte(id);
        }
      },
      { rootMargin: RAND },
    );
    for (const id of liste) {
      document
        .querySelectorAll<HTMLElement>(`[data-kamera="${id}"]`)
        .forEach((el) => beobachter.observe(el));
    }

    const beiSichtwechsel = () => {
      tabSichtbar = document.visibilityState === "visible";
      liste.forEach(bewerte);
    };
    document.addEventListener("visibilitychange", beiSichtwechsel);
    const beruhigung = setTimeout(() => {
      bereit = true;
      liste.forEach(bewerte);
    }, BERUHIGUNG_MS);

    return () => {
      clearTimeout(beruhigung);
      document.removeEventListener("visibilitychange", beiSichtwechsel);
      beobachter.disconnect();
      timer.forEach((t) => clearTimeout(t));
    };
  }, [schluessel]);

  return pausiert;
}
