/**
 * Tests der Langzeitauswertung (`lib/analytik.ts`).
 *
 * Warum gerade hier Tests? Die Analytik ist der einzige Teil der App, dessen
 * Fehler *plausibel aussehen*: Ein um zwei Stunden verschobener Tagesgang
 * oder ein falsch gerechneter Brunstabstand faellt niemandem auf — er wird
 * geglaubt und danach gehandelt. Ein schwarzes Livebild sieht man sofort,
 * eine falsche Zahl nie.
 *
 * Laeuft ohne Installation und ohne Build, wie die Testsuite des Edge-Agenten:
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  baueBericht,
  BESTAETIGUNG_STUNDEN,
  ZYKLUS_NORMAL_MIN,
} from "../lib/analytik.ts";
import type { EreignisTyp, StallEreignis } from "../lib/ereignis-modell.ts";

const TAG = 86_400_000;
const STUNDE = 3_600_000;

/** Fester Bezugspunkt: 10.08.2026, 12:00 UTC — Sommerzeit in Europe/Berlin. */
const JETZT = Date.parse("2026-08-10T12:00:00Z");

let laufendeNummer = 0;

function ereignis(
  typ: EreignisTyp,
  zeit: number | string,
  extra: Partial<StallEreignis> = {},
): StallEreignis {
  return {
    id: `t-${++laufendeNummer}`,
    typ,
    kuhId: null,
    kamera: "stallwache",
    nachricht: "Testereignis",
    konfidenz: null,
    zeit: typeof zeit === "number" ? new Date(zeit).toISOString() : zeit,
    bilder: 0,
    quittiert: null,
    ...extra,
  };
}

const bericht = (
  ereignisse: StallEreignis[],
  zeitraumTage = 7,
  zeitzone = "Europe/Berlin",
) => baueBericht(ereignisse, { zeitraumTage, zeitzone, jetzt: JETZT });

// ---------------------------------------------------------------------------
// Raster
// ---------------------------------------------------------------------------

test("Verlauf hat eine Saeule je Tag, auch fuer Tage ohne Ereignis", () => {
  const b = bericht([ereignis("brunstverdacht", JETZT - 2 * TAG)], 7);
  assert.equal(b.verlauf.length, 7);
  assert.equal(
    b.verlauf.reduce((s, p) => s + p.gesamt, 0),
    1,
    "genau ein Ereignis im Verlauf",
  );
  // Luecken sind Information: leere Tage bleiben als Nullsaeulen stehen.
  assert.equal(b.verlauf.filter((p) => p.gesamt === 0).length, 6);
});

test("Tagesgang rastert in Ortszeit, nicht in UTC (Sommerzeit)", () => {
  // 00:30 UTC im August = 02:30 in Berlin (CEST, UTC+2).
  const b = bericht([ereignis("austreibung", "2026-08-09T00:30:00Z")]);
  assert.equal(b.tagesgang[2].kalbung, 1, "muss in Stunde 2 liegen");
  assert.equal(b.tagesgang[0].gesamt, 0, "nicht in der UTC-Stunde 0");
});

test("Tagesgang beachtet die Winterzeit (CET, UTC+1)", () => {
  const winter = Date.parse("2026-01-20T12:00:00Z");
  const b = baueBericht([ereignis("austreibung", "2026-01-19T00:30:00Z")], {
    zeitraumTage: 7,
    zeitzone: "Europe/Berlin",
    jetzt: winter,
  });
  assert.equal(b.tagesgang[1].kalbung, 1, "muss in Stunde 1 liegen");
});

test("Systemmeldungen verzerren weder Verlauf noch Tagesgang", () => {
  const b = bericht([
    ereignis("info", JETZT - STUNDE),
    ereignis("info", JETZT - 2 * STUNDE),
    ereignis("brunstverdacht", JETZT - STUNDE),
  ]);
  assert.equal(b.gesamt.info, 2, "gezaehlt werden sie trotzdem");
  assert.equal(
    b.verlauf.reduce((s, p) => s + p.gesamt, 0),
    1,
    "aber nicht im Verlauf",
  );
  assert.equal(
    b.tagesgang.reduce((s, p) => s + p.gesamt, 0),
    1,
    "und nicht im Tagesgang",
  );
});

test("Ereignisse ausserhalb des Zeitraums zaehlen nicht mit", () => {
  const b = bericht([
    ereignis("brunstverdacht", JETZT - 2 * TAG),
    ereignis("brunstverdacht", JETZT - 20 * TAG),
  ]);
  assert.equal(b.gesamt.brunstverdacht, 1);
  assert.equal(b.datenbasis.ereignisse, 1);
});

test("Unbekannte Zeitzone faellt zurueck, statt zu werfen", () => {
  const b = bericht([ereignis("austreibung", JETZT - STUNDE)], 7, "Mars/Olympus");
  assert.equal(b.tagesgang.length, 24);
  assert.equal(b.gesamt.austreibung, 1);
});

// ---------------------------------------------------------------------------
// Datenbasis
// ---------------------------------------------------------------------------

test("Datenbasis meldet einen zu kurzen Speicher als begrenzt", () => {
  // 30 Tage gewuenscht, aeltester Eintrag ist 3 Tage alt -> Verlauf lueckenhaft.
  const knapp = bericht([ereignis("brunstverdacht", JETZT - 3 * TAG)], 30);
  assert.equal(knapp.datenbasis.begrenzt, true);

  const reicht = bericht(
    [ereignis("brunstverdacht", JETZT - 3 * TAG), ereignis("info", JETZT - 40 * TAG)],
    30,
  );
  assert.equal(reicht.datenbasis.begrenzt, false);
});

// ---------------------------------------------------------------------------
// Brunstrhythmus
// ---------------------------------------------------------------------------

test("Regelmaessiger 21-Tage-Zyklus ergibt eine Prognose", () => {
  const b = bericht([
    ereignis("brunstverdacht", JETZT - 42 * TAG, { kuhId: "Kuh #17" }),
    ereignis("brunstverdacht", JETZT - 21 * TAG, { kuhId: "Kuh #17" }),
    ereignis("brunstverdacht", JETZT - 1 * TAG, { kuhId: "Kuh #17" }),
  ]);
  const z = b.brunstZyklen.find((x) => x.kuhId === "Kuh #17");
  assert.ok(z, "Zyklus gefunden");
  assert.equal(z.brunsten.length, 3);
  assert.equal(z.medianTage, 20.5);
  assert.equal(z.bewertung, "regelmaessig");
  assert.ok(z.prognose, "Prognose vorhanden");
  // Letzte Brunst + Median, auf den Tag genau.
  const erwartet = JETZT - TAG + 20.5 * TAG;
  assert.ok(
    Math.abs(Date.parse(z.prognose) - erwartet) < STUNDE,
    "Prognose = letzte Brunst + Median",
  );
});

test("Mehrere Meldungen derselben Brunst zaehlen als eine", () => {
  const b = bericht([
    // Drei Aufspruenge innerhalb weniger Stunden = eine Brunst.
    ereignis("brunstverdacht", JETZT - 21 * TAG, { kuhId: "Kuh #8" }),
    ereignis("brunstverdacht", JETZT - 21 * TAG + 2 * STUNDE, { kuhId: "Kuh #8" }),
    ereignis("brunstverdacht", JETZT - 21 * TAG + 5 * STUNDE, { kuhId: "Kuh #8" }),
    ereignis("brunstverdacht", JETZT, { kuhId: "Kuh #8" }),
  ]);
  const z = b.brunstZyklen.find((x) => x.kuhId === "Kuh #8");
  assert.ok(z);
  assert.equal(z.brunsten.length, 2, "zwei Zyklen, nicht vier");
  assert.equal(z.medianTage, 21);
  assert.equal(z.bewertung, "regelmaessig");
});

test("Auffaelliger Abstand bekommt keine Prognose", () => {
  const b = bericht([
    ereignis("brunstverdacht", JETZT - 9 * TAG, { kuhId: "Kuh #3" }),
    ereignis("brunstverdacht", JETZT - 3 * TAG, { kuhId: "Kuh #3" }),
  ]);
  const z = b.brunstZyklen.find((x) => x.kuhId === "Kuh #3");
  assert.ok(z);
  assert.equal(z.medianTage, 6);
  assert.ok(z.medianTage < ZYKLUS_NORMAL_MIN);
  assert.equal(z.bewertung, "auffaellig");
  assert.equal(z.prognose, null, "kein Termin aus unplausibler Grundlage");
});

test("Eine einzelne Brunst ergibt keinen Rhythmus", () => {
  const b = bericht([ereignis("brunstverdacht", JETZT - TAG, { kuhId: "Kuh #5" })]);
  const z = b.brunstZyklen.find((x) => x.kuhId === "Kuh #5");
  assert.ok(z);
  assert.equal(z.bewertung, "zu_wenig_daten");
  assert.equal(z.medianTage, null);
  assert.equal(z.prognose, null);
});

test("Brunst ohne Kuh-Zuordnung erzeugt keinen Zyklus", () => {
  const b = bericht([ereignis("brunstverdacht", JETZT - TAG)]);
  assert.equal(b.brunstZyklen.length, 0);
});

test("Zyklen aelter als das Fenster zaehlen weiter mit", () => {
  // 21 Tage passen nicht in ein 7-Tage-Fenster - der Rhythmus muss ihn
  // trotzdem sehen, sonst gaebe es nie eine Prognose.
  const b = bericht(
    [
      ereignis("brunstverdacht", JETZT - 22 * TAG, { kuhId: "Kuh #9" }),
      ereignis("brunstverdacht", JETZT - TAG, { kuhId: "Kuh #9" }),
    ],
    7,
  );
  const z = b.brunstZyklen.find((x) => x.kuhId === "Kuh #9");
  assert.ok(z, "Zyklus trotz 7-Tage-Fenster erkannt");
  assert.equal(z.bewertung, "regelmaessig");
});

test("Naechster faelliger Termin steht oben", () => {
  const b = bericht([
    ereignis("brunstverdacht", JETZT - 40 * TAG, { kuhId: "Kuh #A" }),
    ereignis("brunstverdacht", JETZT - 19 * TAG, { kuhId: "Kuh #A" }),
    ereignis("brunstverdacht", JETZT - 23 * TAG, { kuhId: "Kuh #B" }),
    ereignis("brunstverdacht", JETZT - 2 * TAG, { kuhId: "Kuh #B" }),
  ]);
  assert.equal(b.brunstZyklen[0].kuhId, "Kuh #A", "A ist frueher faellig");
});

// ---------------------------------------------------------------------------
// Bestaetigungsquote
// ---------------------------------------------------------------------------

test("Austreibung innerhalb der Frist bestaetigt den Verdacht", () => {
  const b = bericht([
    ereignis("kalbeverdacht", JETZT - 6 * STUNDE, { kuhId: "Kuh #42" }),
    ereignis("austreibung", JETZT - 4 * STUNDE, { kuhId: "Kuh #42" }),
  ]);
  assert.equal(b.bestaetigung.verdachte, 1);
  assert.equal(b.bestaetigung.bestaetigt, 1);
  assert.equal(b.bestaetigung.quote, 1);
});

test("Austreibung nach der Frist bestaetigt nichts", () => {
  const spaeter = (BESTAETIGUNG_STUNDEN + 2) * STUNDE;
  const b = bericht([
    ereignis("kalbeverdacht", JETZT - spaeter - STUNDE, { kuhId: "Kuh #42" }),
    ereignis("austreibung", JETZT - STUNDE, { kuhId: "Kuh #42" }),
  ]);
  assert.equal(b.bestaetigung.verdachte, 1);
  assert.equal(b.bestaetigung.bestaetigt, 0);
  assert.equal(b.bestaetigung.quote, 0);
});

test("Austreibung einer anderen Kuh bestaetigt nicht", () => {
  const b = bericht([
    ereignis("kalbeverdacht", JETZT - 3 * STUNDE, { kuhId: "Kuh #42" }),
    ereignis("austreibung", JETZT - 2 * STUNDE, { kuhId: "Kuh #7" }),
  ]);
  assert.equal(b.bestaetigung.bestaetigt, 0);
});

test("Eine Austreibung VOR dem Verdacht bestaetigt ihn nicht", () => {
  const b = bericht([
    ereignis("austreibung", JETZT - 5 * STUNDE, { kuhId: "Kuh #42" }),
    ereignis("kalbeverdacht", JETZT - 2 * STUNDE, { kuhId: "Kuh #42" }),
  ]);
  assert.equal(b.bestaetigung.bestaetigt, 0, "Zeitrichtung zaehlt");
});

test("Ohne Kalbeverdacht bleibt die Quote leer statt 0 %", () => {
  const b = bericht([ereignis("brunstverdacht", JETZT - STUNDE)]);
  assert.equal(b.bestaetigung.verdachte, 0);
  assert.equal(b.bestaetigung.quote, null, "null heisst 'keine Aussage'");
});

// ---------------------------------------------------------------------------
// Reaktionszeit
// ---------------------------------------------------------------------------

test("Reaktionszeit ist der Median, nicht der Mittelwert", () => {
  const q = (min: number) => new Date(JETZT - STUNDE + min * 60_000).toISOString();
  const b = bericht([
    ereignis("brunstverdacht", JETZT - STUNDE, { quittiert: q(5) }),
    ereignis("brunstverdacht", JETZT - STUNDE, { quittiert: q(10) }),
    // Ein Ausreisser (Handy lag nachts im Haus) darf die Zahl nicht kippen.
    ereignis("brunstverdacht", JETZT - STUNDE, { quittiert: q(600) }),
  ]);
  assert.equal(b.reaktion.medianMinuten, 10);
  assert.equal(b.reaktion.quittiert, 3);
  assert.equal(b.reaktion.offen, 0);
});

test("Offene Alarme werden gezaehlt, Systemmeldungen nicht", () => {
  const b = bericht([
    ereignis("austreibung", JETZT - STUNDE),
    ereignis("info", JETZT - STUNDE),
  ]);
  assert.equal(b.reaktion.alarme, 1);
  assert.equal(b.reaktion.offen, 1);
  assert.equal(b.reaktion.medianMinuten, null);
});

// ---------------------------------------------------------------------------
// Robustheit
// ---------------------------------------------------------------------------

test("Leere Liste ergibt einen vollstaendigen, leeren Bericht", () => {
  const b = bericht([]);
  assert.equal(b.verlauf.length, 7);
  assert.equal(b.tagesgang.length, 24);
  assert.deepEqual(b.kameras, []);
  assert.deepEqual(b.brunstZyklen, []);
  assert.equal(b.datenbasis.aeltestes, null);
  assert.equal(b.datenbasis.begrenzt, false);
  assert.equal(b.bestaetigung.quote, null);
});

test("Kaputte Zeitstempel sprengen die Auswertung nicht", () => {
  const b = bericht([
    ereignis("brunstverdacht", "voelliger Unsinn"),
    ereignis("austreibung", JETZT - STUNDE),
  ]);
  // Unparsbares bleibt gezaehlt (wie im Protokoll), taucht aber in keinem
  // Zeitraster auf - lieber sichtbar in der Summe als still verschwunden.
  assert.equal(b.datenbasis.ereignisse, 2);
  assert.equal(b.gesamt.brunstverdacht, 1);
  assert.equal(
    b.tagesgang.reduce((s, p) => s + p.gesamt, 0),
    1,
  );
});

test("Kameras werden nach Haeufigkeit sortiert", () => {
  const b = bericht([
    ereignis("brunstverdacht", JETZT - STUNDE, { kamera: "futterwache" }),
    ereignis("brunstverdacht", JETZT - 2 * STUNDE, { kamera: "futterwache" }),
    ereignis("austreibung", JETZT - STUNDE, { kamera: "abkalbebox" }),
  ]);
  assert.equal(b.kameras[0].kamera, "futterwache");
  assert.equal(b.kameras[0].gesamt, 2);
  assert.equal(b.kameras[1].kamera, "abkalbebox");
  assert.equal(b.kameras[1].kalbung, 1);
});
