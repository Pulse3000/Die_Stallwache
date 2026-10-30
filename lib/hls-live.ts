/**
 * hls.js-Einstellungen fuer das Livebild (Tuya-Cloud und go2rtc-Fernzugriff).
 *
 * Warum dieses Modul existiert: hls.js springt mit den Voreinstellungen nie
 * zurueck ans Live-Ende (`liveMaxLatencyDuration` ungesetzt = unendlich).
 * Jede Pause — Handy gesperrt, Tab im Hintergrund, kurzer Funkausfall —
 * macht die Verzoegerung dann dauerhaft um genau diese Pause groesser; sie
 * sinkt erst, wenn die Kachel neu aufgebaut wird. Gemessen im Browser:
 * tests/e2e/hls-aufholen.mjs.
 *
 * Bewusst KEIN schnelleres Abspielen zum Aufholen (`maxLiveSyncPlaybackRate`
 * bleibt 1): Gemessen (qa-waechter, 2-s-Segmente mit schwankender
 * Ladezeit) zog es den Puffer auf ~1 s herunter und erzeugte 2–6 kurze
 * Standbilder je Minute, die alte Einstellung keines. Ausserdem beschleunigt
 * hls.js nur innerhalb einer Segmentdauer um den Zielabstand — einen
 * Rueckstand unterhalb der Sprunggrenze baut es so kaum ab.
 *
 * Die Verzoegerung der Quelle selbst (Tuya packt sein HLS in der Cloud) liegt
 * ausserhalb der Kontrolle der App; hier geht es nur darum, dass der Player
 * sie nicht zusaetzlich vergroessert.
 */

/** Abstand zum Live-Ende, den der Player anpeilt (Sekunden). */
export const LIVE_SYNC_S = 2;

/** Untere/obere Grenze des Rueckstands, ab dem der Player ans Live-Ende springt. */
export const MAX_LATENZ_MIN_S = 8;
export const MAX_LATENZ_MAX_S = 30;

/** Vorgabe, bis die erste Playlist die Segmentdauer verraet. */
export const MAX_LATENZ_START_S = 12;

/**
 * Rueckstand (Sekunden zum Playlist-Ende), ab dem der Player springt.
 *
 * Im normalen Lauf pendelt der Abstand etwa zwischen einer und zwei
 * Segmentdauern (hls.js setzt nie naeher als eine Segmentdauer ans Ende;
 * jedes neue Segment schiebt das Ende um eine weiter, gemessen von
 * qa-waechter). Die Grenze LIVE_SYNC_S + 3 Segmente liegt damit mindestens
 * ein Segment plus 2 s ueber dem Normalbetrieb: kein Springen im Takt, aber
 * ein Sprung, sobald eine Pause laenger als etwa ein bis zwei Segmente
 * dauerte. Der Rueckstand bleibt also immer unter dieser Grenze; darunter
 * wird er nicht abgebaut. Ohne bekannte Segmentdauer gilt
 * MAX_LATENZ_START_S. Sprung-Schleifen waeren erst ab etwa 13-s-Segmenten
 * denkbar (Obergrenze 30 s); Tuya und go2rtc liefern kuerzere.
 */
export function maxLatenzS(segmentDauerS: number | undefined | null): number {
  if (
    typeof segmentDauerS !== "number" ||
    !Number.isFinite(segmentDauerS) ||
    segmentDauerS <= 0
  ) {
    return MAX_LATENZ_START_S;
  }
  const grenze = LIVE_SYNC_S + 3 * segmentDauerS;
  return Math.min(MAX_LATENZ_MAX_S, Math.max(MAX_LATENZ_MIN_S, grenze));
}

/**
 * Stellt die Sprunggrenze auf die Segmentdauer der geladenen Playlist ein.
 * Aufruf bei jedem LEVEL_LOADED; hls.js liest `config` bei jedem Tick neu,
 * die Aenderung wirkt also sofort (belegt: tests/e2e/hls-aufholen.mjs).
 */
export function passeLatenzGrenzeAn(
  config: { liveMaxLatencyDuration?: number },
  details: { targetduration?: number } | undefined | null,
): void {
  config.liveMaxLatencyDuration = maxLatenzS(details?.targetduration);
}

/**
 * Konfiguration fuer `new Hls(...)`. Kurzer Puffer und kein Rueckpuffer, weil
 * bis zu vier Player gleichzeitig laufen.
 */
export function hlsLiveConfig() {
  return {
    lowLatencyMode: true,
    liveSyncDuration: LIVE_SYNC_S,
    liveMaxLatencyDuration: MAX_LATENZ_START_S,
    maxBufferLength: 8,
    maxMaxBufferLength: 12,
    backBufferLength: 0,
  };
}
