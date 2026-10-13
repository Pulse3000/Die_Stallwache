/**
 * Tests `lib/sichtbares-intervall.ts`: Takt bei sichtbarem Tab, Pause bei
 * verborgenem Tab, sofortiger Abruf beim Zurueckkehren, sauberes Aufraeumen.
 * Laeuft ohne Browser mit gefaelschtem `document` und gemockten Timern.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { afterEach, beforeEach, test, mock } from "node:test";
import { sichtbaresIntervall } from "../lib/sichtbares-intervall.ts";

type Listener = () => void;
const g = globalThis as unknown as { document?: unknown };

function fakeDocument(sichtbar: boolean) {
  const listener = new Set<Listener>();
  const doc = {
    visibilityState: sichtbar ? "visible" : "hidden",
    addEventListener: (_: string, l: Listener) => void listener.add(l),
    removeEventListener: (_: string, l: Listener) => void listener.delete(l),
    setze(s: boolean) {
      doc.visibilityState = s ? "visible" : "hidden";
      [...listener].forEach((l) => l());
    },
    anzahl: () => listener.size,
  };
  return doc;
}

beforeEach(() => mock.timers.enable({ apis: ["setInterval"] }));
afterEach(() => {
  mock.timers.reset();
  delete g.document;
});

test("sichtbarer Tab: laeuft im Takt, kein Abruf beim Start", () => {
  g.document = fakeDocument(true);
  let n = 0;
  const ende = sichtbaresIntervall(() => n++, 1000);
  assert.equal(n, 0);
  mock.timers.tick(3500);
  assert.equal(n, 3);
  ende();
});

test("verborgener Tab: keine Abrufe", () => {
  const doc = fakeDocument(true);
  g.document = doc;
  let n = 0;
  const ende = sichtbaresIntervall(() => n++, 1000);
  mock.timers.tick(2000);
  assert.equal(n, 2);
  doc.setze(false);
  mock.timers.tick(60_000);
  assert.equal(n, 2, "im Hintergrund darf nichts laufen");
  ende();
});

test("Zurueckkehren: sofort ein Abruf, danach wieder im Takt", () => {
  const doc = fakeDocument(true);
  g.document = doc;
  let n = 0;
  const ende = sichtbaresIntervall(() => n++, 1000);
  doc.setze(false);
  mock.timers.tick(10_000);
  doc.setze(true);
  assert.equal(n, 1, "sofort frische Daten");
  mock.timers.tick(2000);
  assert.equal(n, 3);
  ende();
});

test("Start im verborgenen Tab: erst beim Sichtbarwerden", () => {
  const doc = fakeDocument(false);
  g.document = doc;
  let n = 0;
  const ende = sichtbaresIntervall(() => n++, 1000);
  mock.timers.tick(5000);
  assert.equal(n, 0);
  doc.setze(true);
  assert.equal(n, 1);
  ende();
});

test("mehrfaches Sichtbar-Signal startet keinen zweiten Timer", () => {
  const doc = fakeDocument(true);
  g.document = doc;
  let n = 0;
  const ende = sichtbaresIntervall(() => n++, 1000);
  doc.setze(true);
  doc.setze(true);
  mock.timers.tick(2000);
  assert.equal(n, 2, "genau ein Timer");
  ende();
});

test("Aufraeumen: kein Abruf mehr, Listener entfernt", () => {
  const doc = fakeDocument(true);
  g.document = doc;
  let n = 0;
  const ende = sichtbaresIntervall(() => n++, 1000);
  assert.equal(doc.anzahl(), 1);
  ende();
  assert.equal(doc.anzahl(), 0);
  mock.timers.tick(10_000);
  doc.setze(true);
  assert.equal(n, 0);
});

test("ohne document (Server): tut nichts und wirft nicht", () => {
  delete g.document;
  const ende = sichtbaresIntervall(() => assert.fail("darf nie laufen"), 1000);
  mock.timers.tick(5000);
  ende();
});
