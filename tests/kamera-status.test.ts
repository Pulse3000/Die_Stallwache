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
  LEERER_PING_STAND,
  PING_BESTAETIGUNG_MS,
  PING_FOLGE_MAX_MS,
  PING_OFFLINE_MS,
  PING_OK_MS,
  PING_START_MS,
  PING_TIMEOUT_MS,
  type PingStand,
  belegterWechsel,
  bewertePing,
  kopfStatus,
  nachLivebild,
  pingAntwort,
  wartezeitBisPing,
} from "../lib/kamera-status.ts";

/** Kopftext mit normalen Leerzeichen (Zahl und Wort sind per NBSP verbunden). */
const kopf = (a: Anzeige[]) => {
  const k = kopfStatus(a);
  return { ...k, text: k.text.replaceAll("\u00a0", " ") };
};

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
    assert.deepEqual(kopf(anzeigen), { text, ton });
  });
}

test("Kopf: Produktionsfall (ohne Bridge, Datensparen, Kameras senden) zeigt nie „0 von“ und ist nie rot", () => {
  // Vorher: drei Vorschau-Kacheln „laedt", eine pausiert -> „0 von 3 Kameras online", rot.
  const k = kopf(["ungeprueft", "ungeprueft", "ungeprueft", "pausiert"]);
  assert.doesNotMatch(k.text, /0 von/);
  assert.notEqual(k.ton, "stoerung");
});

test("Kopf: Ungeprueft, Laden und Pausiert faerben nie rot", () => {
  const sanft: Anzeige[] = ["ungeprueft", "laedt", "pausiert", "instabil"];
  for (const a of sanft) for (const b of sanft) for (const c of sanft) {
    assert.notEqual(kopfStatus([a, b, c]).ton, "stoerung", `${a},${b},${c}`);
  }
});

test("Kopf: Zahl und Wort brechen nie auseinander (geschuetztes Leerzeichen)", () => {
  const t = kopfStatus(["offline", "ungeprueft", "ungeprueft", "pausiert"]).text;
  assert.equal(t, "0\u00a0von\u00a01\u00a0online · 2\u00a0ungeprüft · 1\u00a0pausiert");
  for (const teil of t.split(" · ")) assert.doesNotMatch(teil, / /, teil);
});

test("Kopf: rot nur mit offline und ohne online", () => {
  assert.equal(kopfStatus(["offline", "pausiert"]).ton, "stoerung");
  assert.equal(kopfStatus(["offline", "online"]).ton, "hinweis");
});

// ---- Status-Ping ----

const T0 = 10_000_000;
const stand = (teil: Partial<PingStand> = {}): PingStand => ({ ...LEERER_PING_STAND, ...teil });

test("Antwortklassen: 2xx ok, >= 500 Stoerung, sonst unklar (kein Netz, Frist, 401)", () => {
  assert.equal(pingAntwort(200), "ok");
  assert.equal(pingAntwort(204), "ok");
  assert.equal(pingAntwort(502), "stoerung");
  assert.equal(pingAntwort(503), "stoerung"); // Tuya nicht konfiguriert: Quelle fehlt wirklich
  assert.equal(pingAntwort(null), "unklar"); // Netzfehler oder Frist
  assert.equal(pingAntwort(401), "unklar"); // Login abgelaufen sagt nichts ueber die Kamera
  assert.equal(pingAntwort(404), "unklar");
  assert.equal(PING_TIMEOUT_MS, 20_000);
});

test("Ping ok: ungeprueft, Stand zurueckgesetzt, naechster in 5 min", () => {
  const e = bewertePing(stand({ fehlschlaege: 1, letzterFehlschlag: T0 - 1000, belegtOffline: true }), "ok", T0);
  assert.equal(e.zustand, "ungeprueft");
  assert.equal(e.warteMs, PING_OK_MS);
  assert.deepEqual(e.stand, { fehlschlaege: 0, letzterFehlschlag: 0, faellig: T0 + PING_OK_MS, belegtOffline: false });
  assert.equal(PING_OK_MS, 5 * 60_000);
});

test("1. Stoerung: Zustand unveraendert, Bestaetigung nach 60 s", () => {
  const e = bewertePing(stand(), "stoerung", T0);
  assert.equal(e.zustand, null);
  assert.equal(e.warteMs, PING_BESTAETIGUNG_MS);
  assert.equal(e.stand.fehlschlaege, 1);
  assert.equal(e.stand.belegtOffline, false);
  assert.equal(PING_BESTAETIGUNG_MS, 60_000);
});

test("2. Stoerung in Folge: offline (belegt), dann alle 2 min", () => {
  const erste = bewertePing(stand(), "stoerung", T0).stand;
  const e = bewertePing(erste, "stoerung", T0 + PING_BESTAETIGUNG_MS);
  assert.equal(e.zustand, "offline");
  assert.equal(e.warteMs, PING_OFFLINE_MS);
  assert.equal(e.stand.belegtOffline, true);
  assert.equal(PING_OFFLINE_MS, 2 * 60_000);
});

test("weitere Stoerungen im Offline-Takt: bleibt offline", () => {
  const s1 = stand({ fehlschlaege: 2, letzterFehlschlag: T0, belegtOffline: true });
  const e = bewertePing(s1, "stoerung", T0 + PING_OFFLINE_MS);
  assert.equal(e.zustand, "offline");
  assert.equal(e.stand.fehlschlaege, 3);
});

test("Folge-Fenster: eine alte Stoerung vor langer Pause macht die naechste nicht zur zweiten", () => {
  const alt = stand({ fehlschlaege: 1, letzterFehlschlag: T0 });
  const e = bewertePing(alt, "stoerung", T0 + PING_FOLGE_MAX_MS + 1);
  assert.equal(e.zustand, null, "nach Pause zaehlt die Stoerung als erste");
  assert.equal(e.stand.fehlschlaege, 1);
  assert.equal(e.warteMs, PING_BESTAETIGUNG_MS);
  assert.equal(bewertePing(alt, "stoerung", T0 + PING_FOLGE_MAX_MS).zustand, "offline");
  assert.equal(PING_FOLGE_MAX_MS, 3 * 60_000);
});

test("unklar (kein Netz, Frist, 401): aendert nichts, zaehlt nicht, naechster in 2 min", () => {
  const s1 = stand({ fehlschlaege: 1, letzterFehlschlag: T0 });
  const e = bewertePing(s1, "unklar", T0 + 1000);
  assert.equal(e.zustand, null);
  assert.equal(e.stand.fehlschlaege, 1);
  assert.equal(e.stand.belegtOffline, false);
  assert.equal(e.warteMs, PING_OFFLINE_MS);
  // Funkloch: beliebig viele unklare Antworten faerben nichts rot.
  let st = stand();
  for (let i = 0; i < 10; i++) {
    const r = bewertePing(st, "unklar", T0 + i * PING_OFFLINE_MS);
    assert.equal(r.zustand, null);
    st = r.stand;
  }
  assert.equal(st.belegtOffline, false);
});

test("belegtes offline bleibt bei einer einzelnen Stoerung nach Pause stehen", () => {
  const s1 = stand({ fehlschlaege: 2, letzterFehlschlag: T0, belegtOffline: true });
  const e = bewertePing(s1, "stoerung", T0 + 60 * 60_000);
  assert.equal(e.zustand, null); // Anzeige bleibt „offline" (nicht zurueckgenommen)
  assert.equal(e.stand.belegtOffline, true);
});

test("ein Ping fuehrt nie zu „online“", () => {
  for (const a of ["ok", "stoerung", "unklar"] as const) {
    for (let f = 0; f < 4; f++) {
      assert.notEqual(bewertePing(stand({ fehlschlaege: f, letzterFehlschlag: T0 }), a, T0 + 1).zustand, "online");
    }
  }
});

test("Livebild setzt den Stand zurueck; naechster Ping 5 min danach", () => {
  assert.deepEqual(nachLivebild(T0), { fehlschlaege: 0, letzterFehlschlag: 0, faellig: T0 + PING_OK_MS, belegtOffline: false });
});

test("Faelligkeit absolut: Eintritt pingt fruehestens nach 3 s, sonst zum faelligen Zeitpunkt", () => {
  assert.equal(PING_START_MS, 3_000);
  assert.equal(wartezeitBisPing(0, T0), PING_START_MS); // nie gepingt
  assert.equal(wartezeitBisPing(T0 - 10_000, T0), PING_START_MS); // ueberfaellig
  assert.equal(wartezeitBisPing(T0 + 4 * 60_000, T0), 4 * 60_000); // Rollenwechsel/Rueckkehr kurz nach Ping
});

/** Simuliert eine Stunde Ping-Takt mit fester Antwort und zaehlt die Pings. */
function pingsProStunde(antwort: "ok" | "stoerung" | "unklar"): number {
  let t = PING_START_MS;
  let st = stand();
  let n = 0;
  while (t <= 60 * 60_000) {
    n++;
    const e = bewertePing(st, antwort, t);
    st = e.stand;
    t += e.warteMs;
  }
  return n;
}

test("Kosten: hoechstens 12 Pings pro Stunde im Normalbetrieb, 31 bei Stoerung, 30 bei unklarer Lage", () => {
  assert.ok(pingsProStunde("ok") <= 12, `ok: ${pingsProStunde("ok")}`);
  assert.ok(pingsProStunde("stoerung") <= 31, `stoerung: ${pingsProStunde("stoerung")}`);
  assert.ok(pingsProStunde("unklar") <= 30, `unklar: ${pingsProStunde("unklar")}`);
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
