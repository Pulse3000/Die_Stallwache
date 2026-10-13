/**
 * `setInterval`, das bei verborgenem Tab pausiert.
 *
 * Die Dashboard-Komponenten fragen alle 20-60 s die API ab. Ein Handy mit
 * der App im Hintergrund oder bei ausgeschaltetem Bildschirm hat davon nichts
 * – kostet aber Function-Aufrufe, Mobilfunk und (Geraetesteuerung) Tuya-
 * Kontingent. Daher: Verborgen -> keine Abrufe; sichtbar -> sofort ein Abruf
 * (frische Daten beim Zurueckkehren), danach wieder im Takt.
 *
 * Gibt die Aufraeum-Funktion zurueck. Ohne `document` (Server) passiert nichts.
 */
export function sichtbaresIntervall(fn: () => void, ms: number): () => void {
  if (typeof document === "undefined") return () => {};

  let timer: ReturnType<typeof setInterval> | null = null;
  const starten = () => {
    if (timer === null) timer = setInterval(fn, ms);
  };
  const stoppen = () => {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
  const beiSichtwechsel = () => {
    if (document.visibilityState === "visible") {
      if (timer === null) {
        fn();
        starten();
      }
    } else {
      stoppen();
    }
  };

  if (document.visibilityState === "visible") starten();
  document.addEventListener("visibilitychange", beiSichtwechsel);
  return () => {
    stoppen();
    document.removeEventListener("visibilitychange", beiSichtwechsel);
  };
}
