/**
 * Tests `zaehleOffeneAlarme` aus `lib/ereignis-modell.ts`: der rote Punkt an
 * „Alarme" zaehlt nur unquittierte Alarme des Edge-Agenten, nie Beispieldaten.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  fuehreEreignisseZusammen,
  kuerzeEreignisse,
  zaehleOffeneAlarme,
} from "../lib/ereignis-modell.ts";

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

// --- Alarme fallen nie wegen Systemmeldungen aus der Liste (§9.8) ---------

type E = { id: string; typ: "info" | "austreibung" | "kalbeverdacht"; zeit: string };
const ev = (id: string, typ: E["typ"], minute: number): E => ({
  id,
  typ,
  zeit: new Date(Date.UTC(2026, 10, 17, 0, minute)).toISOString(),
});

test("300 Meldungen nach einem Alarm: der Alarm bleibt", () => {
  // neueste zuerst: 300 Meldungen, ganz hinten (aeltester) der Alarm
  const liste: E[] = [];
  for (let i = 300; i >= 1; i--) liste.push(ev(`m${i}`, "info", i));
  liste.push(ev("alarm", "austreibung", 0));
  const kurz = kuerzeEreignisse(liste, 200);
  assert.equal(kurz.length, 200);
  assert.ok(kurz.some((e) => e.id === "alarm"), "Alarm verdraengt");
  // geopfert wurden die aeltesten Meldungen, die neuesten stehen noch vorn
  assert.equal(kurz[0].id, "m300");
  assert.ok(!kurz.some((e) => e.id === "m1"));
});

test("Reihenfolge bleibt, Liste unter der Grenze bleibt unveraendert", () => {
  const liste = [ev("b", "info", 2), ev("a", "kalbeverdacht", 1)];
  assert.equal(kuerzeEreignisse(liste, 200), liste);
  const kurz = kuerzeEreignisse(
    [ev("c", "info", 3), ev("b", "kalbeverdacht", 2), ev("a", "info", 1)],
    2,
  );
  assert.deepEqual(kurz.map((e) => e.id), ["c", "b"]);
});

test("nur Alarme: dann fallen die aeltesten Alarme", () => {
  const liste = [3, 2, 1].map((i) => ev(`a${i}`, "austreibung", i));
  assert.deepEqual(kuerzeEreignisse(liste, 2).map((e) => e.id), ["a3", "a2"]);
});

test("Eingabeliste wird nicht veraendert", () => {
  const liste = [ev("b", "info", 2), ev("a", "info", 1)];
  kuerzeEreignisse(liste, 1);
  assert.equal(liste.length, 2);
});

test("Zusammenfuehren: nach Zeit, jede ID einmal, unlesbare Zeit vorn", () => {
  const alarme = [ev("x", "austreibung", 5), ev("alt", "info", 1)];
  const meldungen = [ev("y", "info", 9), ev("alt", "info", 1), { ...ev("kaputt", "info", 0), zeit: "?" }];
  assert.deepEqual(
    fuehreEreignisseZusammen(alarme, meldungen).map((e) => e.id),
    ["kaputt", "y", "x", "alt"],
  );
});

