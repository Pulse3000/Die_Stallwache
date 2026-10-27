/**
 * Tests der KI-Kaesten auf dem Livebild der Stallwache (`lib/ki-ansicht.ts`,
 * docs/ki-ansicht-spezifikation.md §5).
 *
 * Sie sichern ab: Daten vom Stall-Rechner werden streng geprueft (nur Zahlen
 * und bekannte Klassen landen im DOM); zum Videobild passt die Erkennung,
 * deren Zeit um den Video-Versatz hinter der neuesten liegt; rot und
 * „ALARM" nur mit Alarm; Erkennungen gelten nur als aktuell, solange sich
 * ihre Zeit bewegt (Handy-Uhr, unabhaengig von der Uhr am Stall).
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  KI_FRISCH_MS,
  KI_KAESTEN_URL,
  KI_LUECKE_S,
  KI_PUFFER_S,
  KI_START,
  KI_TAKT_MS,
  KI_ZUSCHLAG_S,
  type KiBild,
  kaesten,
  kiText,
  leseKiBild,
  naechsterKiStand,
  puffere,
  seitenAbweichung,
  videoRechteck,
  videoVersatzS,
  waehleBild,
  wirksamerVersatzS,
} from "../lib/ki-ansicht.ts";

const uhr = (s: number) => `U${s}`;

/** Antwort wie edge-agent/main.py KiAnsicht.daten() */
const roh = (zeit = 1761577200.5) => ({
  v: 1,
  kamera: "stallwache",
  zeit,
  breite: 1920,
  hoehe: 1080,
  alarm_ab: 0.8,
  kuehe: [
    { id: 12, box: [0.25, 0.25, 0.5, 0.75], winkel: 52.4 },
    { id: 7, box: [0.5208, 0.0926, 1.0, 0.463], winkel: null },
  ],
  objekte: [
    { klasse: "amniotic_sac", box: [0.1562, 0.3704, 0.2083, 0.463], prozent: 91, alarm: true },
    { klasse: "calf_legs", box: [0.1, 0.1, 0.2, 0.2], prozent: 79, alarm: false },
  ],
});

const bild = (zeit: number): KiBild => leseKiBild(roh(zeit))!;

test("Pfad und Takt", () => {
  assert.equal(KI_KAESTEN_URL, "/api/stallwache/fern/ki-kaesten");
  assert.equal(KI_TAKT_MS, 1_000);
});

test("leseKiBild: gueltige Antwort", () => {
  const b = leseKiBild(roh());
  assert.ok(b);
  assert.equal(b.zeit, 1761577200.5);
  assert.equal(b.alarmAb, 0.8);
  assert.deepEqual(b.kuehe[0], { id: 12, box: [0.25, 0.25, 0.5, 0.75], winkel: 52.4 });
  assert.equal(b.kuehe[1].winkel, null);
  assert.deepEqual(b.objekte[0], {
    klasse: "amniotic_sac",
    box: [0.1562, 0.3704, 0.2083, 0.463],
    prozent: 91,
    alarm: true,
  });
});

test("leseKiBild: alles Unpassende -> null", () => {
  const mit = (f: (d: ReturnType<typeof roh>) => void) => {
    const d = roh();
    f(d);
    return leseKiBild(d);
  };
  for (const x of [null, undefined, "x", 3, [], {}]) assert.equal(leseKiBild(x), null);
  assert.equal(mit((d) => ((d as { v: number }).v = 2)), null, "andere Version");
  assert.equal(mit((d) => ((d as { zeit: unknown }).zeit = "1")), null);
  assert.equal(mit((d) => (d.breite = 0)), null);
  assert.equal(mit((d) => ((d as { alarm_ab: unknown }).alarm_ab = null)), null);
  assert.equal(mit((d) => (d.kuehe[0].box = [0.5, 0, 0.4, 1])), null, "x2 < x1");
  assert.equal(mit((d) => (d.kuehe[0].box = [0, 0, 1.2, 1])), null, "ausserhalb 0..1");
  assert.equal(mit((d) => (d.kuehe[0].box = [0, 0, 1])), null, "drei Werte");
  assert.equal(mit((d) => (d.kuehe[0].id = -1)), null, "Kuh ohne Nummer");
  assert.equal(mit((d) => (d.kuehe[0].id = 1.5)), null);
  assert.equal(mit((d) => ((d.kuehe[0] as { winkel: unknown }).winkel = "52")), null);
  assert.equal(mit((d) => (d.objekte[0].klasse = "<img src=x onerror=alert(1)>")), null);
  assert.equal(mit((d) => (d.objekte[0].prozent = 91.5)), null);
  assert.equal(mit((d) => ((d.objekte[0] as { alarm: unknown }).alarm = "true")), null);
  assert.equal(
    mit((d) => (d.kuehe = Array.from({ length: 201 }, (_, i) => ({ id: i, box: [0, 0, 1, 1], winkel: null })))),
    null,
    "mehr als 200 Eintraege",
  );
});

test("puffere: sortiert, ohne Doppel, 30 s", () => {
  let p: KiBild[] = [];
  for (const z of [100, 102, 101, 102]) p = puffere(p, bild(z));
  assert.deepEqual(p.map((b) => b.zeit), [100, 101, 102]);
  p = puffere(p, bild(100 + KI_PUFFER_S + 1));
  assert.deepEqual(p.map((b) => b.zeit), [101, 102, 131]);
});

test("waehleBild: neueste minus Versatz, keine Kaesten bei Luecke", () => {
  let p: KiBild[] = [];
  for (let z = 100; z <= 110; z++) p = puffere(p, bild(z));
  assert.equal(waehleBild([], 4), null);
  assert.equal(waehleBild(p, 0)!.zeit, 110);
  assert.equal(waehleBild(p, 4)!.zeit, 106);
  assert.equal(waehleBild(p, 4.5)!.zeit, 105, "das juengste davor, nie eins aus der Zukunft");
  assert.equal(waehleBild(p, -3)!.zeit, 110, "negativer Versatz zaehlt als 0");
  assert.equal(waehleBild(p, 20), null, "Puffer reicht nicht so weit zurueck");
});

test("waehleBild: Luecke groesser als KI_LUECKE_S -> null", () => {
  const p = [bild(100), bild(100 + KI_LUECKE_S + 2)];
  // Ziel = 105 - 1 = 104; letztes davor 100 -> 4 s > 3 s
  assert.equal(waehleBild(p, 1), null);
  // Ziel = 105 - 2 = 103 -> 3 s -> noch passend
  assert.equal(waehleBild(p, 2)!.zeit, 100);
});

test("videoVersatzS: Abstand zum Playlist-Ende plus Zuschlag", () => {
  assert.equal(videoVersatzS(20, 16), 4 + KI_ZUSCHLAG_S);
  assert.equal(videoVersatzS(null, 16), KI_ZUSCHLAG_S, "unbekannt");
  assert.equal(videoVersatzS(Number.POSITIVE_INFINITY, 16), KI_ZUSCHLAG_S);
  assert.equal(videoVersatzS(10, 12), KI_ZUSCHLAG_S, "nie negativ");
});

test("wirksamerVersatzS: Zeit seit dem letzten Abruf zieht ab", () => {
  assert.equal(wirksamerVersatzS(5, null, 1_000), 5);
  assert.equal(wirksamerVersatzS(5, 1_000, 1_000), 5);
  assert.equal(wirksamerVersatzS(5, 1_000, 1_750), 4.25);
  assert.equal(wirksamerVersatzS(5, 1_000, 9_000), 0, "nie negativ");
  assert.equal(wirksamerVersatzS(5, 2_000, 1_000), 5, "Handy-Uhr rueckwaerts: nichts abziehen");
});

test("videoRechteck: object-contain", () => {
  assert.deepEqual(videoRechteck(400, 300, 1920, 1080), { x: 0, y: 37.5, w: 400, h: 225 });
  assert.deepEqual(videoRechteck(400, 225, 1920, 1080), { x: 0, y: 0, w: 400, h: 225 });
  assert.deepEqual(videoRechteck(400, 100, 1600, 1600), { x: 150, y: 0, w: 100, h: 100 });
  assert.equal(videoRechteck(400, 300, 0, 0), null, "Video noch ohne Groesse");
  assert.equal(videoRechteck(0, 300, 1920, 1080), null);
});

test("seitenAbweichung: mehr als 3 %", () => {
  const b = bild(1);
  assert.equal(seitenAbweichung(b, 1920, 1080), false);
  assert.equal(seitenAbweichung(b, 640, 360), false, "Unterstrom gleiches Format");
  assert.equal(seitenAbweichung(b, 1920, 1088), false, "Codec-Aufrundung");
  assert.equal(seitenAbweichung(b, 640, 480), true, "4:3 gegen 16:9");
  assert.equal(seitenAbweichung(b, 0, 0), false, "unbekannt");
});

test("kaesten: Beschriftung, rot nur mit Alarm (Befund ki-wache)", () => {
  const k = kaesten(bild(1));
  assert.deepEqual(
    k.map((x) => [x.art, x.text]),
    [
      ["kuh", "Kuh #12 · 52°"],
      ["kuh", "Kuh #7"],
      ["alarm", "Fruchtblase 91 % ALARM"],
      ["unter", "Kälberfüße? 79 % (Alarm ab 80 %)"],
    ],
  );
  assert.ok(!k.some((x) => x.art !== "alarm" && x.text.includes("ALARM")));
});

test("Zustand: Erkennungszeit bewegt sich -> aktuell", () => {
  let s = naechsterKiStand(KI_START, 200, 1000, 0);
  assert.deepEqual(s, { zustand: "bild", neueste: 1000, seit: 0 });
  s = naechsterKiStand(s, 200, 1001, 1_000);
  assert.deepEqual(s, { zustand: "bild", neueste: 1001, seit: 1_000 });
  s = naechsterKiStand(s, 200, 999, 2_000);
  assert.deepEqual(s, { zustand: "bild", neueste: 1001, seit: 1_000 }, "aeltere Antwort zaehlt nicht");
});

test("Zustand: Zeit steht still -> nach 10 s nicht aktuell, egal wie die Stall-Uhr geht", () => {
  // Stall-Uhr 1 h hinter dem Handy: solange sich die Zeit bewegt, ist es aktuell.
  const t0 = 3_600_000 + 5_000_000;
  let s = naechsterKiStand(KI_START, 200, 5000, t0);
  assert.equal(s.zustand, "bild");
  s = naechsterKiStand(s, 200, 5000, t0 + KI_FRISCH_MS);
  assert.equal(s.zustand, "bild", "genau 10 s ist noch aktuell");
  s = naechsterKiStand(s, 200, 5000, t0 + KI_FRISCH_MS + 1);
  assert.equal(s.zustand, "alt");
  s = naechsterKiStand(s, 200, 5001, t0 + KI_FRISCH_MS + 2);
  assert.equal(s.zustand, "bild", "neue Erkennung -> wieder aktuell");
});

test("Zustand: 404, 401, Netzfehler, unbrauchbare Antwort", () => {
  assert.equal(naechsterKiStand(KI_START, 404, null, 0).zustand, "aus");
  const gesehen = naechsterKiStand(KI_START, 200, 1000, 0);
  const s404 = naechsterKiStand(gesehen, 404, null, 1_000);
  assert.deepEqual(s404, { zustand: "alt", neueste: 1000, seit: 0 }, "erst da, dann 404 -> nicht aktuell");
  assert.equal(naechsterKiStand(gesehen, 401, null, 0).zustand, "anmelden");
  assert.equal(naechsterKiStand(gesehen, 502, null, 0).zustand, "gestoert");
  assert.equal(naechsterKiStand(gesehen, null, null, 0).zustand, "gestoert");
  assert.equal(naechsterKiStand(gesehen, 200, null, 0).zustand, "gestoert", "200 mit kaputtem JSON");
});

test("Texte der Statuszeile", () => {
  const info = { videoLaeuft: true, kuehe: 2, versatzS: 4.4, passend: true, schief: false };
  const bildStand = naechsterKiStand(KI_START, 200, 1000, 0);
  assert.equal(kiText(KI_START, uhr, info), "KI-Kästen laden …");
  assert.equal(
    kiText(bildStand, uhr, info),
    "KI · 2 Kühe · Versatz ≈ 4 s · Nr. von der KI, nicht Ohrmarke",
  );
  assert.ok(kiText(bildStand, uhr, { ...info, kuehe: 1 }).startsWith("KI · 1 Kuh ·"));
  assert.equal(
    kiText(bildStand, uhr, { ...info, videoLaeuft: false }),
    "KI-Kästen erscheinen, sobald das Livebild läuft.",
  );
  assert.equal(
    kiText(bildStand, uhr, { ...info, passend: false }),
    "KI-Kästen: keine Erkennung zum gezeigten Moment.",
  );
  assert.ok(kiText(bildStand, uhr, { ...info, schief: true }).startsWith("KI-Kästen ausgeblendet"));
  assert.equal(
    kiText({ zustand: "alt", neueste: 1000, seit: 0 }, uhr, info),
    "KI-Kästen nicht aktuell – letzte Erkennung U1000.",
  );
  const aus = kiText(naechsterKiStand(KI_START, 404, null, 0), uhr, info);
  assert.ok(aus.startsWith("Keine KI-Kästen – vom Stall-Rechner kommen gerade keine Erkennungen"), aus);
  assert.ok(aus.includes("noch kein Modell") && aus.includes("dort nicht eingerichtet"), aus);
  assert.equal(
    kiText({ ...bildStand, zustand: "anmelden" }, uhr, info),
    "KI-Kästen nicht erreichbar – bitte neu anmelden.",
  );
  assert.equal(
    kiText({ ...bildStand, zustand: "gestoert" }, uhr, info),
    "KI-Kästen nicht erreichbar – Fernzugriff zum Stall gestört.",
  );
});
