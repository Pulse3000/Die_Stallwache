/**
 * Tests `zaehleOffeneAlarme` aus `lib/ereignis-modell.ts`: der rote Punkt an
 * „Alarme" zaehlt nur unquittierte Alarme des Edge-Agenten, nie Beispieldaten.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import { zaehleOffeneAlarme } from "../lib/ereignis-modell.ts";

const zwei = [{ quittiert: null }, { quittiert: null }, { quittiert: "2026-10-15T08:00:00Z" }];

test("echte Alarme: unquittierte zaehlen", () => {
  assert.equal(zaehleOffeneAlarme({ ereignisse: zwei, quelle: "edge-agent" }), 2);
});

test("Beispieldaten erzeugen keinen roten Punkt", () => {
  assert.equal(zaehleOffeneAlarme({ ereignisse: zwei, quelle: "demo" }), 0);
});

test("ohne oder mit unbekannter Quelle: kein Punkt (im Zweifel still)", () => {
  assert.equal(zaehleOffeneAlarme({ ereignisse: zwei }), 0);
  assert.equal(zaehleOffeneAlarme({ ereignisse: zwei, quelle: "irgendwas" }), 0);
});

test("leere Liste und alles quittiert: 0", () => {
  assert.equal(zaehleOffeneAlarme({ ereignisse: [], quelle: "edge-agent" }), 0);
  assert.equal(
    zaehleOffeneAlarme({ ereignisse: [{ quittiert: "2026-10-15T08:00:00Z" }], quelle: "edge-agent" }),
    0,
  );
});
