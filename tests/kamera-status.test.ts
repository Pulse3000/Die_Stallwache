/**
 * Tests `lib/kamera-status.ts` – die Tabellen aus
 * docs/vorschau-status-spezifikation.md §3, Zeile fuer Zeile:
 * Kopftext und System-Punkt, Status-Ping der Vorschau ohne Bridge,
 * Ereignisliste nur bei belegtem Wechsel.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  type Anzeige,
  PING_BESTAETIGUNG_MS,
  PING_OFFLINE_MS,
  PING_OK_MS,
  PING_START_MS,
  belegterWechsel,
  bewertePing,
  kopfStatus,
  wartezeitBisPing,
} from "../lib/kamera-status.ts";

// ---- Kopf ----

const faelle: Array<[string, Anzeige[], string, string]> = [
  ["alle online", ["online", "online", "online", "online"], "4 Kameras online", "ok"],
  [
    "gezaehlte alle online, dazu Vorschau und Pausiert",
    ["online", "ungeprueft", "ungeprueft", "pausiert"],
    "1 online · 2 ungeprüft · 1 pausiert",
    "ok",
  ],
  [
    "gezaehlte teils online, dazu Vorschau",
    ["online", "offline", "ungeprueft", "ungeprueft"],
    "1 von 2 online · 2 ungeprüft",
    "hinweis",
  ],
  [
    "nur gezaehlte, nicht alle online",
    ["online", "instabil", "offline", "online"],
    "2 von 4 Kameras online",
    "hinweis",
  ],
  ["Aufbau: laedt ist gelb, nicht rot", ["laedt", "laedt", "laedt", "pausiert"], "3 laden · 1 pausiert", "hinweis"],
  ["eine Kachel laedt", ["online", "laedt", "pausiert", "pausiert"], "1 online · 1 lädt · 2 pausiert", "hinweis"],
  [
    "echter Ausfall: offline und keine online",
    ["offline", "ungeprueft", "ungeprueft", "ungeprueft"],
    "0 von 1 online · 3 ungeprüft",
    "stoerung",
  ],
  [
    "nur Vorschau und Pausiert: grau",
    ["ungeprueft", "ungeprueft", "ungeprueft", "pausiert"],
    "3 ungeprüft · 1 pausiert",
    "neutral",
  ],
  ["alles pausiert", ["pausiert", "pausiert", "pausiert", "pausiert"], "Livebilder pausiert", "neutral"],
  [
    "pausierte, zuvor online gewesene Kachel zaehlt als pausiert",
    ["online", "online", "online", "pausiert"],
    "3 online · 1 pausiert",
    "ok",
  ],
  ["Einzahl", ["online"], "1 Kamera online", "ok"],
  ["Einzahl gezaehlt, nicht online", ["instabil"], "0 von 1 Kamera online", "hinweis"],
];

for (const [name, anzeigen, text, ton] of faelle) {
  test(`Kopf: ${name}`, () => {
    assert.deepEqual(kopfStatus(anzeigen), { text, ton });
  });
}

test("Kopf: Produktionsfall (ohne Bridge, Datensparen, Kameras senden) zeigt nie „0 von“ und ist nie rot", () => {
  // Vorher: drei Vorschau-Kacheln „laedt", eine pausiert -> „0 von 3 Kameras online", rot.
  const k = kopfStatus(["ungeprueft", "ungeprueft", "ungeprueft", "pausiert"]);
  assert.doesNotMatch(k.text, /0 von/);
  assert.notEqual(k.ton, "stoerung");
});

test("Kopf: Ungeprueft, Laden und Pausiert faerben nie rot", () => {
  const sanft: Anzeige[] = ["ungeprueft", "laedt", "pausiert", "instabil"];
  for (const a of sanft) for (const b of sanft) for (const c of sanft) {
    assert.notEqual(kopfStatus([a, b, c]).ton, "stoerung", `${a},${b},${c}`);
  }
});

test("Kopf: rot nur mit offline und ohne online", () => {
  assert.equal(kopfStatus(["offline", "pausiert"]).ton, "stoerung");
  assert.equal(kopfStatus(["offline", "online"]).ton, "hinweis");
});

// ---- Status-Ping ----

test("Ping 2xx: ungeprueft, Fehlerzaehler 0, naechster in 5 min", () => {
  assert.deepEqual(bewertePing(0, true), { fehlschlaege: 0, zustand: "ungeprueft", warteMs: PING_OK_MS });
  assert.equal(PING_OK_MS, 5 * 60_000);
});

test("1. Fehlschlag: Zustand unveraendert, Bestaetigung nach 60 s", () => {
  assert.deepEqual(bewertePing(0, false), { fehlschlaege: 1, zustand: null, warteMs: PING_BESTAETIGUNG_MS });
  assert.equal(PING_BESTAETIGUNG_MS, 60_000);
});

test("2. Fehlschlag in Folge: offline, dann alle 2 min", () => {
  assert.deepEqual(bewertePing(1, false), { fehlschlaege: 2, zustand: "offline", warteMs: PING_OFFLINE_MS });
  assert.equal(PING_OFFLINE_MS, 2 * 60_000);
});

test("weitere Fehlschlaege: bleibt offline", () => {
  assert.deepEqual(bewertePing(2, false), { fehlschlaege: 3, zustand: "offline", warteMs: PING_OFFLINE_MS });
});

test("nach offline: ein erfolgreicher Ping nimmt offline zurueck (auf ungeprueft, nie online)", () => {
  const e = bewertePing(3, true);
  assert.equal(e.zustand, "ungeprueft");
  assert.equal(e.fehlschlaege, 0);
});

test("ein Ping fuehrt nie zu „online“", () => {
  for (let f = 0; f < 5; f++) {
    assert.notEqual(bewertePing(f, true).zustand, "online");
    assert.notEqual(bewertePing(f, false).zustand, "online");
  }
});

test("Faelligkeit absolut: Eintritt pingt fruehestens nach 3 s, sonst zum faelligen Zeitpunkt", () => {
  const jetzt = 1_000_000;
  assert.equal(PING_START_MS, 3_000);
  assert.equal(wartezeitBisPing(0, jetzt), PING_START_MS); // nie gepingt
  assert.equal(wartezeitBisPing(jetzt - 10_000, jetzt), PING_START_MS); // ueberfaellig
  assert.equal(wartezeitBisPing(jetzt + 4 * 60_000, jetzt), 4 * 60_000); // Rollenwechsel kurz nach Livebild
});

/** Simuliert eine Stunde Ping-Takt und zaehlt die Pings. */
function pingsProStunde(ok: boolean): number {
  let t = PING_START_MS;
  let fehl = 0;
  let n = 0;
  while (t <= 60 * 60_000) {
    n++;
    const e = bewertePing(fehl, ok);
    fehl = e.fehlschlaege;
    t += e.warteMs;
  }
  return n;
}

test("Kosten: hoechstens 12 Pings pro Stunde im Normalbetrieb, 31 bei Stoerung", () => {
  assert.ok(pingsProStunde(true) <= 12, `ok: ${pingsProStunde(true)}`);
  assert.ok(pingsProStunde(false) <= 31, `stoerung: ${pingsProStunde(false)}`);
});

// ---- Ereignisliste ----

test("Ereignis nur bei belegtem Wechsel online <-> offline", () => {
  assert.equal(belegterWechsel(undefined, "online"), true);
  assert.equal(belegterWechsel(undefined, "offline"), true);
  assert.equal(belegterWechsel("online", "online"), false);
  assert.equal(belegterWechsel("online", "offline"), true);
  assert.equal(belegterWechsel("offline", "online"), true);
});

test("Zwischenzustaende erzeugen keinen Eintrag (Rollenwechsel wiederholt nicht „ist online“)", () => {
  for (const z of ["ungeprueft", "laedt", "instabil"] as const) {
    assert.equal(belegterWechsel(undefined, z), false);
    assert.equal(belegterWechsel("online", z), false);
    assert.equal(belegterWechsel("offline", z), false);
  }
});
