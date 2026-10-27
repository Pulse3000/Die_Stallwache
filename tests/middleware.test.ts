/**
 * Regressionstest fuer den Matcher in `middleware.ts`.
 *
 * Der Matcher nimmt statische Dateien vom Login aus, darunter alles, was auf
 * .jpg/.png/… endet. Ein Stallbild unter so einem Pfad waere ohne Anmeldung
 * abrufbar (gefunden beim Bau der KI-Ansicht, docs/ki-ansicht-spezifikation.md
 * §4). Dieser Test haelt fest, dass jeder Pfad des Fernzugriffs von der
 * Middleware erfasst wird. Die Fernzugriff-Route prueft die Sitzung
 * zusaetzlich selbst.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { FERN_PRAEFIX, KI_ANSICHT_PFAD } from "../lib/fern.ts";
import { KI_ANSICHT_URL } from "../lib/ki-ansicht.ts";

const quelle = readFileSync(new URL("../middleware.ts", import.meta.url), "utf8");
const muster = JSON.parse(quelle.match(/matcher:\s*\[\s*("(?:[^"\\]|\\.)*")/)![1]) as string;
// Next.js wertet den Matcher wie einen ganzen Pfad-Ausdruck aus.
const erfasst = (pfad: string) => new RegExp(`^${muster}$`).test(pfad);

test("Matcher-Muster gelesen und plausibel", () => {
  assert.ok(muster.startsWith("/((?!"), muster);
  assert.ok(erfasst("/api/events"));
  assert.ok(!erfasst("/sw.js"), "sw.js bleibt ausgenommen (PWA)");
  assert.ok(!erfasst("/_next/static/x.js"));
  assert.ok(!erfasst("/irgendwas/bild.jpg"), "statische Bilder bleiben ausgenommen");
});

test("Jeder Fernzugriff-Pfad laeuft durch die Middleware (Login)", () => {
  assert.equal(KI_ANSICHT_URL, `${FERN_PRAEFIX}/${KI_ANSICHT_PFAD}`);
  for (const pfad of [
    KI_ANSICHT_URL,
    `${FERN_PRAEFIX}/stream.m3u8`,
    `${FERN_PRAEFIX}/hls/playlist.m3u8`,
    `${FERN_PRAEFIX}/hls/segment.ts`,
    `${FERN_PRAEFIX}/hls/init.mp4`,
    `${FERN_PRAEFIX}/hls/segment.m4s`,
  ]) {
    assert.ok(erfasst(pfad), `${pfad} muss hinter dem Login liegen`);
  }
});
