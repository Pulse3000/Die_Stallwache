/**
 * Tests der KI-Ansicht an der Stallwache-Kachel (`lib/ki-ansicht.ts`,
 * docs/ki-ansicht-spezifikation.md §5).
 *
 * Sie sichern ab, dass ein Bild nur als aktuell gilt, solange sich seine
 * Bildzeit bewegt (gemessen mit der Handy-Uhr, unabhaengig von der Uhr des
 * Stall-Rechners), dass 404 „Agent analysiert nicht" bzw. „nicht aktuell"
 * heisst, und dass die Texte der Spezifikation entsprechen.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  KI_ANSICHT_URL,
  KI_FRISCH_MS,
  KI_START,
  kiTaktMs,
  kiText,
  leseBildZeit,
  naechsterKiStand,
} from "../lib/ki-ansicht.ts";

const uhr = (s: number) => `U${s}`;

test("Pfad und Takt", () => {
  assert.equal(KI_ANSICHT_URL, "/api/stallwache/fern/ki-ansicht.jpg");
  assert.equal(kiTaktMs(false), 1_000);
  assert.equal(kiTaktMs(true), 5_000);
});

test("Bildzeit bewegt sich -> Bild aktuell", () => {
  let s = naechsterKiStand(KI_START, 200, 1000, 0);
  assert.deepEqual(s, { zustand: "bild", bildZeit: 1000, seit: 0 });
  s = naechsterKiStand(s, 200, 1001, 1_000);
  assert.deepEqual(s, { zustand: "bild", bildZeit: 1001, seit: 1_000 });
});

test("Bildzeit steht still -> nach 10 s nicht aktuell, egal wie die Stall-Uhr geht", () => {
  // Stall-Uhr 1 h hinter dem Handy: solange sich das Bild bewegt, ist es aktuell.
  let s = naechsterKiStand(KI_START, 200, 5000, 3_600_000 + 5_000_000);
  assert.equal(s.zustand, "bild");
  s = naechsterKiStand(s, 200, 5000, 3_600_000 + 5_000_000 + KI_FRISCH_MS);
  assert.equal(s.zustand, "bild", "genau 10 s ist noch aktuell");
  s = naechsterKiStand(s, 200, 5000, 3_600_000 + 5_000_000 + KI_FRISCH_MS + 1);
  assert.equal(s.zustand, "alt");
  s = naechsterKiStand(s, 200, 5001, 3_600_000 + 5_000_000 + KI_FRISCH_MS + 2);
  assert.equal(s.zustand, "bild", "neues Bild -> wieder aktuell");
});

test("404: ohne Bild 'aus', nach einem Bild 'alt'", () => {
  assert.equal(naechsterKiStand(KI_START, 404, null, 0).zustand, "aus");
  const mitBild = naechsterKiStand(KI_START, 200, 1000, 0);
  const s = naechsterKiStand(mitBild, 404, null, 2_000);
  assert.deepEqual(s, { zustand: "alt", bildZeit: 1000, seit: 0 });
});

test("401 -> neu anmelden, Netz- und Proxyfehler -> gestoert, Bild bleibt gemerkt", () => {
  const mitBild = naechsterKiStand(KI_START, 200, 1000, 0);
  assert.equal(naechsterKiStand(mitBild, 401, null, 1).zustand, "anmelden");
  for (const status of [null, 502, 503, 504, 500]) {
    const s = naechsterKiStand(mitBild, status, null, 1);
    assert.equal(s.zustand, "gestoert", String(status));
    assert.equal(s.bildZeit, 1000);
  }
  assert.equal(naechsterKiStand(mitBild, 200, null, 1).zustand, "gestoert", "200 ohne Bildzeit");
});

test("Texte wie in der Spezifikation", () => {
  const bild = naechsterKiStand(KI_START, 200, 7, 0);
  assert.equal(kiText(bild, uhr), "KI-Ansicht · Stand U7 · Nummern vom Tracker, keine Ohrmarken");
  assert.equal(kiText({ ...bild, zustand: "alt" }, uhr), "KI-Ansicht nicht aktuell – letztes Bild von U7.");
  assert.equal(
    kiText(naechsterKiStand(KI_START, 404, null, 0), uhr),
    "Keine KI-Ansicht – der Edge-Agent analysiert gerade nicht (Silent Mode ohne Modell oder Agent aus).",
  );
  assert.equal(kiText({ ...bild, zustand: "anmelden" }, uhr), "KI-Ansicht nicht erreichbar – bitte neu anmelden.");
  assert.equal(
    kiText({ ...bild, zustand: "gestoert" }, uhr),
    "KI-Ansicht nicht erreichbar – Fernzugriff zum Stall gestört.",
  );
  assert.equal(kiText(KI_START, uhr), "KI-Ansicht lädt …");
});

test("Bildzeit nur als Ganzzahl", () => {
  assert.equal(leseBildZeit("1761577200"), 1761577200);
  for (const w of [null, "", "1.5", "-1", "1e9", "abc", "1".repeat(13)]) {
    assert.equal(leseBildZeit(w), null, JSON.stringify(w));
  }
});
