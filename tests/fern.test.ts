/**
 * Tests des Stallwache-Fernzugriffs (`lib/fern.ts`).
 *
 * Sie sichern ab, dass ueber die Durchleitung nur das Stallwache-HLS
 * erreichbar ist – nie die go2rtc-API (die u. a. Befehle auf dem Stall-Rechner
 * ausfuehren koennte) – und dass das Manifest den Browser an diese App bindet.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import { fernZiel, schreibeManifestUm } from "../lib/fern.ts";

const BASIS = "https://stall.example.ts.net:8443";
const q = (s: string) => new URLSearchParams(s);

test("Einstieg erzwingt die Quelle stallwache_sd, auch gegen src=...", () => {
  assert.equal(
    fernZiel(BASIS, "stream.m3u8", q("src=rollei")),
    `${BASIS}/api/stream.m3u8?src=stallwache_sd`,
  );
  assert.equal(
    fernZiel(BASIS, "stream.m3u8", q("")),
    `${BASIS}/api/stream.m3u8?src=stallwache_sd`,
  );
});

test("HLS-Folgeabrufe behalten nur erlaubte Parameter", () => {
  assert.equal(
    fernZiel(BASIS, "hls/segment.ts", q("id=abc123&n=7&src=rollei&x=1")),
    `${BASIS}/api/hls/segment.ts?id=abc123&n=7`,
  );
  assert.equal(
    fernZiel(BASIS, "hls/playlist.m3u8", q("id=abc123")),
    `${BASIS}/api/hls/playlist.m3u8?id=abc123`,
  );
});

test("go2rtc-API und unbekannte Pfade sind gesperrt", () => {
  for (const p of [
    "streams",
    "config",
    "restart",
    "frame.jpeg",
    "exec",
    "ws",
    "webrtc",
    "../api/config",
    "hls/../config",
    "hls/segment.ts/../../config",
    "",
  ]) {
    assert.equal(fernZiel(BASIS, p, q("")), null, `Pfad "${p}"`);
  }
});

test("Parameterwerte mit Sonderzeichen werden abgelehnt", () => {
  for (const wert of ["../x", "a b", "a;b", "a%2fb", "x".repeat(65), ""]) {
    assert.equal(
      fernZiel(BASIS, "hls/playlist.m3u8", new URLSearchParams({ id: wert })),
      null,
      `id="${wert}"`,
    );
  }
});

test("Manifest: relative und absolute Pfade laufen ueber diese App", () => {
  const url = `${BASIS}/api/stream.m3u8?src=stallwache_sd`;
  const roh = [
    "#EXTM3U",
    "#EXT-X-STREAM-INF:BANDWIDTH=900000",
    "hls/playlist.m3u8?id=abc",
    "#EXT-X-MAP:URI=\"hls/init.mp4?id=abc\"",
    "/api/hls/segment.ts?id=abc&n=3",
    "",
  ].join("\n");
  const neu = schreibeManifestUm(roh, url);
  assert.equal(
    neu,
    [
      "#EXTM3U",
      "#EXT-X-STREAM-INF:BANDWIDTH=900000",
      "/api/stallwache/fern/hls/playlist.m3u8?id=abc",
      "#EXT-X-MAP:URI=\"/api/stallwache/fern/hls/init.mp4?id=abc\"",
      "/api/stallwache/fern/hls/segment.ts?id=abc&n=3",
      "",
    ].join("\n"),
  );
  assert.ok(!neu.includes("example.ts.net"), "Stall-Adresse darf nie im Manifest stehen");
});

test("Manifest aus Unterpfad (hls/playlist.m3u8) loest relative Segmente richtig auf", () => {
  const url = `${BASIS}/api/hls/playlist.m3u8?id=abc`;
  const neu = schreibeManifestUm("#EXTINF:1.0,\nsegment.ts?id=abc&n=9\n", url);
  assert.equal(neu, "#EXTINF:1.0,\n/api/stallwache/fern/hls/segment.ts?id=abc&n=9\n");
});
