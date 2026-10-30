/**
 * Tests der Live-Einstellungen fuer hls.js (`lib/hls-live.ts`).
 *
 * Sie sichern ab: Der Player hat immer eine Sprunggrenze (sonst bleibt die
 * Verzoegerung nach einer Pause dauerhaft groesser), die Grenze liegt sicher
 * ueber dem normalen Pendeln im Segmenttakt (kein Springen im Betrieb), und
 * hls.js nimmt die Konfiguration an (Grenze > liveSyncDuration, keine
 * Mischung von *Count- und *Duration-Werten). Das Verhalten im Browser misst
 * tests/e2e/hls-aufholen.mjs.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  LIVE_SYNC_S,
  MAX_LATENZ_MAX_S,
  MAX_LATENZ_MIN_S,
  MAX_LATENZ_START_S,
  hlsLiveConfig,
  maxLatenzS,
  passeLatenzGrenzeAn,
} from "../lib/hls-live.ts";

test("Konfiguration: Sprunggrenze gesetzt, kein schnelleres Abspielen", () => {
  const c = hlsLiveConfig();
  assert.equal(c.liveSyncDuration, LIVE_SYNC_S);
  assert.equal(c.liveMaxLatencyDuration, MAX_LATENZ_START_S);
  // Gemessen (qa-waechter): Rate > 1 erzeugte bei schwankender Ladezeit
  // kurze Standbilder. hls.js-Vorgabe ist 1 — nicht ueberschreiben.
  assert.ok(!("maxLiveSyncPlaybackRate" in c));
  assert.equal(c.lowLatencyMode, true);
  // hls.js verwirft liveMaxLatencyDuration <= liveSyncDuration und das
  // Mischen mit *Count-Werten (src/config.ts, Pruefung beim Erzeugen).
  assert.ok(c.liveMaxLatencyDuration > c.liveSyncDuration);
  assert.ok(!("liveSyncDurationCount" in c) && !("liveMaxLatencyDurationCount" in c));
});

test("Sprunggrenze: zwei Segmente ueber dem normalen Pendeln", () => {
  // Normalbetrieb pendelt zwischen LIVE_SYNC_S und LIVE_SYNC_S + Segment.
  for (const seg of [1, 2, 4, 6, 8]) {
    const g = maxLatenzS(seg);
    assert.ok(g >= LIVE_SYNC_S + seg + Math.min(2 * seg, MAX_LATENZ_MAX_S - LIVE_SYNC_S - seg),
      `Segment ${seg} s: Grenze ${g} zu knapp`);
  }
  assert.equal(maxLatenzS(2), 8);
  assert.equal(maxLatenzS(6), 20);
});

test("Sprunggrenze: Unter- und Obergrenze", () => {
  assert.equal(maxLatenzS(0.5), MAX_LATENZ_MIN_S);
  assert.equal(maxLatenzS(1), MAX_LATENZ_MIN_S);
  assert.equal(maxLatenzS(10), MAX_LATENZ_MAX_S);
  assert.equal(maxLatenzS(60), MAX_LATENZ_MAX_S);
  for (const seg of [0.2, 1, 3, 9, 100]) {
    assert.ok(maxLatenzS(seg) > LIVE_SYNC_S, "Grenze immer > liveSyncDuration");
  }
});

test("Sprunggrenze: unbrauchbare Segmentdauer -> Startwert", () => {
  for (const wert of [undefined, null, 0, -2, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(maxLatenzS(wert as number | undefined), MAX_LATENZ_START_S, String(wert));
  }
});

test("passeLatenzGrenzeAn: setzt die Grenze aus der Playlist", () => {
  const config: { liveMaxLatencyDuration?: number } = { liveMaxLatencyDuration: 12 };
  passeLatenzGrenzeAn(config, { targetduration: 6 });
  assert.equal(config.liveMaxLatencyDuration, 20);
  passeLatenzGrenzeAn(config, { targetduration: 2 });
  assert.equal(config.liveMaxLatencyDuration, 8);
  passeLatenzGrenzeAn(config, undefined);
  assert.equal(config.liveMaxLatencyDuration, MAX_LATENZ_START_S);
});
