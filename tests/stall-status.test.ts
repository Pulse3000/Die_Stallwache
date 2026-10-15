/**
 * Tests der Statusabfrage (`lib/stall-status.ts`).
 *
 * Die gefaehrlichste Fehlerart hier ist ein falsches „OK": Der Landwirt
 * fragt nachts „alles ruhig?", bekommt „OK" und schlaeft weiter — obwohl
 * der Agent seit einer Stunde schweigt. Deshalb pruefen die meisten Faelle,
 * wann es KEIN OK geben darf. Abnahmekriterien 1–14 aus
 * docs/statusabfrage-spezifikation.md.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  baueStallStatus,
  type Lebenszeichen,
  type StatusEingabe,
  type StatusOptionen,
} from "../lib/stall-status.ts";
import type { EreignisTyp, StallEreignis } from "../lib/ereignis-modell.ts";

const MIN = 60_000;
/** 14.10.2026, 04:00 Ortszeit (Europe/Berlin, Sommerzeit = UTC+2). */
const JETZT = Date.parse("2026-10-14T02:00:00Z");
const vor = (minuten: number) => new Date(JETZT - minuten * MIN).toISOString();

let nr = 0;
function ereignis(
  typ: EreignisTyp,
  minutenVorher: number,
  extra: Partial<StallEreignis> = {},
): StallEreignis {
  return {
    id: `t-${++nr}`,
    typ,
    kuhId: null,
    kamera: "stallwache",
    nachricht: "Testereignis",
    konfidenz: null,
    zeit: vor(minutenVorher),
    bilder: 0,
    quittiert: null,
    ...extra,
  };
}

const frisch = (extra: Partial<Lebenszeichen> = {}): Lebenszeichen => ({
  zeit: vor(2),
  modus: "analyse",
  bild: true,
  ...extra,
});

function status(
  ereignisse: StallEreignis[],
  lebenszeichen: Record<string, Lebenszeichen> = { stallwache: frisch() },
  optionen: StatusOptionen = {},
  eingabe: Partial<StatusEingabe> = {},
) {
  return baueStallStatus(
    {
      ereignisse,
      quelle: "edge-agent",
      letzterKontakt: vor(2),
      lebenszeichen,
      speicher: "kv",
      ...eingabe,
    },
    { jetzt: JETZT, ...optionen },
  );
}

test("1: Demo-Daten sind nie OK und werden nicht eingeordnet", () => {
  const s = status([ereignis("kalbeverdacht", 5, { kuhId: "Kuh #42" })], {}, {}, {
    quelle: "demo",
  });
  assert.equal(s.stufe, "UNBEKANNT");
  assert.equal(s.kameras.length, 0);
  assert.match(s.text, /Demo-Daten/);
});

test("1b: Agent meldet sich per Lebenszeichen, aber noch ohne Ereignis -> keine Demo", () => {
  const s = status([ereignis("kalbeverdacht", 5, { kuhId: "Kuh #42" })], undefined, {}, {
    quelle: "demo",
    letzterKontakt: null,
  });
  assert.equal(s.quelle, "edge-agent");
  assert.equal(s.stufe, "OK");
  assert.equal(s.kameras[0].kuehe.length, 0);
});

test("1c: Instanzwechsel ohne KV — Lebenszeichen da, Alarme verloren -> nie OK", () => {
  // Befund qa-waechter: Austreibung auf Instanz A, Redeploy, naechstes
  // Lebenszeichen landet auf frischer Instanz B -> frueher faelschlich OK.
  const s = status([], undefined, {}, { quelle: "demo", letzterKontakt: null, speicher: "instanz" });
  assert.equal(s.stufe, "UNBEKANNT");
  assert.equal(s.speicher, "instanz");
  assert.match(s.kameras[0].text, /keine dauerhafte Ereignisablage/);
});

test("1d: ohne KV nie OK, auch mit Ereignissen im Instanzpuffer", () => {
  const ruhig = status([ereignis("info", 5, { nachricht: "Edge-Agent gestartet" })], undefined, {}, {
    speicher: "instanz",
  });
  assert.equal(ruhig.stufe, "UNBEKANNT");
  // Echte Befunde bleiben sichtbar — mit Hinweis
  const alarm = status([ereignis("austreibung", 3, { konfidenz: 0.9 })], undefined, {}, {
    speicher: "instanz",
  });
  assert.equal(alarm.stufe, "KRITISCH");
  assert.match(alarm.kameras[0].text, /Achtung: keine dauerhafte Ereignisablage/);
});

test("2: aktuelles Lebenszeichen, Analyse, Bild, keine Alarme -> OK", () => {
  const s = status([]);
  assert.equal(s.stufe, "OK");
  assert.equal(s.kameras[0].stufe, "OK");
  assert.match(s.kameras[0].text, /^Stallwache: OK – keine offenen Alarme in den letzten 12 h\. Analyse läuft, letztes Lebenszeichen 03:58\./);
});

test("3: Lebenszeichen aelter als 15 min -> UNBEKANNT mit Alter", () => {
  const s = status([], { stallwache: frisch({ zeit: vor(52) }) });
  assert.equal(s.stufe, "UNBEKANNT");
  assert.equal(s.kameras[0].datenlage.aktuell, false);
  assert.match(s.kameras[0].text, /letztes Lebenszeichen 03:08 \(vor 52 min\)\. Keine Aussage über die Tiere möglich/);
});

test("3b: Grenze — genau 15 min alt ist noch aktuell", () => {
  assert.equal(status([], { stallwache: frisch({ zeit: vor(15) }) }).stufe, "OK");
  assert.equal(status([], { stallwache: frisch({ zeit: vor(16) }) }).stufe, "UNBEKANNT");
});

test("4: Silent Mode -> UNBEKANNT", () => {
  const s = status([], { stallwache: frisch({ modus: "silent" }) });
  assert.equal(s.stufe, "UNBEKANNT");
  assert.match(s.text, /Silent Mode/);
});

test("5: Kamera ohne Bild oder unbekannter Bildzustand -> UNBEKANNT", () => {
  const blind = status([], { stallwache: frisch({ bild: false }) });
  assert.equal(blind.stufe, "UNBEKANNT");
  assert.match(blind.text, /Kamera liefert kein Bild/);
  assert.equal(status([], { stallwache: frisch({ bild: null }) }).stufe, "UNBEKANNT");
  assert.equal(status([], { stallwache: frisch({ modus: null }) }).stufe, "UNBEKANNT");
});

test("6: offene Austreibung ohne Kuh-ID -> Kamera KRITISCH, keine Kuh", () => {
  const s = status([ereignis("austreibung", 48, { konfidenz: 0.87 })]);
  assert.equal(s.stufe, "KRITISCH");
  const k = s.kameras[0];
  assert.equal(k.kuehe.length, 0);
  assert.equal(k.kameraAlarme[0].evidenz, "modellbasiert");
  assert.match(k.text, /^Stallwache: KRITISCH – Austreibung 03:12, offen \(modellbasiert, Konfidenz 87 %\)\./);
});

test("6b: KRITISCH bleibt auch bei veraltetem Lebenszeichen — mit Hinweis", () => {
  const s = status([ereignis("austreibung", 48, { konfidenz: 0.9 })], {
    stallwache: frisch({ zeit: vor(40) }),
  });
  assert.equal(s.stufe, "KRITISCH");
  assert.match(s.kameras[0].text, /Achtung: letztes Lebenszeichen/);
});

test("7: Eskalation ist Kamera-Ereignis, keine Kuh 'Eskalation'", () => {
  const s = status([
    ereignis("austreibung", 70, { konfidenz: 0.9 }),
    ereignis("austreibung", 5, { kuhId: "Eskalation", konfidenz: 0.88 }),
  ]);
  const k = s.kameras[0];
  assert.equal(k.stufe, "KRITISCH");
  assert.equal(k.kuehe.length, 0);
  assert.equal(k.kameraAlarme.filter((a) => a.eskalation).length, 1);
  assert.match(k.text, /Kein Geburtsfortschritt 03:55, offen/);
  // Eskalation feuert einmal pro Episode — kein Cooldown-Eintrag dafuer.
  assert.equal(k.cooldown.length, 0);
});

test("8: offener Kalbeverdacht -> Kuh und Kamera WARNUNG, regelbasiert", () => {
  const s = status([ereignis("kalbeverdacht", 6, { kuhId: "Kuh #42" })]);
  assert.equal(s.stufe, "WARNUNG");
  const kuh = s.kameras[0].kuehe[0];
  assert.equal(kuh.kuhId, "Kuh #42");
  assert.equal(kuh.stufe, "WARNUNG");
  assert.equal(kuh.alarme[0].evidenz, "regelbasiert");
  assert.match(kuh.text, /^Kuh #42: WARNUNG – Kalbeverdacht 03:54, offen \(regelbasiert, Verdacht ohne Objekt-Evidenz\)\. Folgemeldungen Kalbeverdacht gebündelt bis 04:09\./);
  assert.match(s.kameras[0].text, /Offene Verdachtsmeldungen: Kuh #42/);
});

test("9: quittierter Alarm wird gezeigt, hebt die Stufe aber nicht", () => {
  const s = status([
    ereignis("kalbeverdacht", 30, { kuhId: "Kuh #42", quittiert: vor(25) }),
    ereignis("austreibung", 20, { konfidenz: 0.9, quittiert: vor(18) }),
  ]);
  assert.equal(s.stufe, "OK");
  assert.equal(s.kameras[0].kuehe[0].stufe, "OK");
  assert.match(s.kameras[0].kuehe[0].text, /gesehen 03:35/);
  assert.match(s.kameras[0].text, /Zuletzt: Austreibung 03:40, gesehen 03:42/);
});

test("10: Alarme ausserhalb des Fensters zaehlen nicht", () => {
  const alt = [ereignis("austreibung", 13 * 60, { konfidenz: 0.9 })];
  assert.equal(status(alt).stufe, "OK");
  assert.equal(status(alt, undefined, { stunden: 24 }).stufe, "KRITISCH");
});

test("11: Cooldown = letzter Alarm (Kuh, Typ) + 15 min, danach weg", () => {
  const laufend = status([
    ereignis("brunstverdacht", 20, { kuhId: "Kuh #17" }),
    ereignis("brunstverdacht", 4, { kuhId: "Kuh #17" }),
  ]);
  const kuh = laufend.kameras[0].kuehe[0];
  assert.equal(kuh.cooldown.length, 1);
  assert.equal(kuh.cooldown[0].bis, new Date(JETZT + 11 * MIN).toISOString());
  assert.match(kuh.text, /1 weitere offene Meldung/);

  const abgelaufen = status([ereignis("brunstverdacht", 16, { kuhId: "Kuh #17" })]);
  assert.equal(abgelaufen.kameras[0].kuehe[0].cooldown.length, 0);
  // Cooldown-Spiegel einstellbar
  const lang = status([ereignis("brunstverdacht", 16, { kuhId: "Kuh #17" })], undefined, {
    cooldownMinuten: 30,
  });
  assert.equal(lang.kameras[0].kuehe[0].cooldown.length, 1);
});

test("12: Kuh-Filter vergleicht die Nummer exakt", () => {
  const liste = [
    ereignis("kalbeverdacht", 5, { kuhId: "Kuh #42" }),
    ereignis("kalbeverdacht", 5, { kuhId: "Kuh #420" }),
  ];
  for (const filter of ["42", "Kuh #42", "kuh 42", "#042"]) {
    const s = status(liste, undefined, { kuh: filter });
    assert.deepEqual(s.kameras[0].kuehe.map((k) => k.kuhId), ["Kuh #42"], filter);
  }
  const keine = status(liste, undefined, { kuh: "12" });
  assert.equal(keine.kameras[0].kuehe.length, 0);
  assert.match(keine.text, /^Kuh #12: keine Alarme in den letzten 12 h\./);
});

test("12b: Austreibung bleibt bei Kuh-Filter sichtbar (Bucht-Kontext)", () => {
  const s = status([ereignis("austreibung", 5, { konfidenz: 0.9 })], undefined, { kuh: "12" });
  assert.equal(s.stufe, "KRITISCH");
});

test("13: Kamera-Filter liefert nur die gewuenschte Kamera", () => {
  const liste = [
    ereignis("austreibung", 5, { konfidenz: 0.9 }),
    ereignis("brunstverdacht", 5, { kuhId: "Kuh #3", kamera: "futterwache" }),
  ];
  const lz = { stallwache: frisch(), futterwache: frisch() };
  const alle = status(liste, lz);
  assert.deepEqual(alle.kameras.map((k) => k.kamera), ["futterwache", "stallwache"]);
  assert.equal(alle.stufe, "KRITISCH");

  const nurFutter = status(liste, lz, { kamera: "Futterwache" });
  assert.deepEqual(nurFutter.kameras.map((k) => k.kamera), ["futterwache"]);
  assert.equal(nurFutter.stufe, "WARNUNG");

  const unbekannt = status(liste, lz, { kamera: "weidewache" });
  assert.equal(unbekannt.kameras[0].kamera, "weidewache");
  assert.equal(unbekannt.stufe, "UNBEKANNT");
});

test("14: alter Agent ohne Kamera-Lebenszeichen -> hoechstens UNBEKANNT", () => {
  const s = status([ereignis("info", 3, { nachricht: "Edge-Agent gestartet" })], {});
  assert.equal(s.stufe, "UNBEKANNT");
  assert.equal(s.kameras[0].datenlage.quelle, "global");
  assert.match(s.text, /kein Kamera-Lebenszeichen \(Agent-Update nötig\), letzter Kontakt 03:58/);

  const nieGemeldet = status([], {}, {}, { letzterKontakt: null });
  assert.equal(nieGemeldet.stufe, "UNBEKANNT");
  assert.equal(nieGemeldet.kameras.length, 0);
  assert.match(nieGemeldet.text, /Kein Edge-Agent hat sich gemeldet/);
});

test("Gesamtstufe ist das Maximum: KRITISCH > WARNUNG > UNBEKANNT > OK", () => {
  const s = status(
    [ereignis("kalbeverdacht", 5, { kuhId: "Kuh #1", kamera: "futterwache" })],
    { stallwache: frisch({ zeit: vor(60) }), futterwache: frisch() },
  );
  assert.equal(s.kameras.find((k) => k.kamera === "stallwache")!.stufe, "UNBEKANNT");
  assert.equal(s.stufe, "WARNUNG");
});

test("Info-Ereignisse heben die Stufe nie", () => {
  const s = status([ereignis("info", 5, { nachricht: "Kamerastream wieder da" })]);
  assert.equal(s.stufe, "OK");
});

test("Fenster wird auf 1–72 h begrenzt, Alarme vom Vortag tragen ein Datum", () => {
  const s = status([ereignis("austreibung", 30 * 60, { konfidenz: 0.9 })], undefined, {
    stunden: 500,
  });
  assert.equal(s.fensterStunden, 72);
  assert.match(s.kameras[0].text, /Austreibung 12\.10\. 22:00/);
});
