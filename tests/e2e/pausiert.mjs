/**
 * E2E-Pruefung „Streams nur bei Sicht" (lib/pausiert.ts) im echten Browser.
 *
 * Die Stream-Endpunkte der Tuya-Kameras werden mit 503 beantwortet; die
 * Kacheln versuchen es dann im Backoff erneut. Gezaehlt werden diese
 * Anfragen – wer pausiert ist, fragt nicht mehr an.
 *
 *   npm run build && npm start -- -p 3102      (anderes Terminal)
 *   node tests/e2e/pausiert.mjs                (BASE=http://localhost:3102)
 *
 * Braucht Chromium (CHROMIUM=/opt/pw-browsers/chromium) und die Dev-Dependency
 * playwright-core. Gehoert nicht zu `npm test` (kein Browser noetig dort).
 */

import { chromium } from "playwright-core";

const BASE = process.env.BASE ?? "http://localhost:3102";
const CHROMIUM = process.env.CHROMIUM ?? "/opt/pw-browsers/chromium";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ executablePath: CHROMIUM });
const page = await (await browser.newContext({ viewport: { width: 390, height: 844 } })).newPage();

const n = { futterwache: 0, abkalbebox: 0, weidewache: 0, stallwache: 0 };
await page.route(/\/api\/(\w+)\/stream$/, (route) => {
  n[route.request().url().match(/api\/(\w+)\/stream/)[1]]++;
  route.fulfill({ status: 503, contentType: "application/json", body: '{"fehler":"test"}' });
});
const fehler = [];
page.on("pageerror", (e) => fehler.push(e.message));

const ergebnisse = [];
const pruefe = (name, ok, detail) => {
  ergebnisse.push(ok);
  console.log(`${ok ? "OK  " : "FEHL"} ${name}${detail ? ` – ${detail}` : ""}`);
};
const setzeTab = (sichtbar) =>
  page.evaluate((s) => {
    Object.defineProperty(document, "visibilityState", {
      value: s ? "visible" : "hidden",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
  }, sichtbar);

await page.goto(BASE, { waitUntil: "networkidle" });
await sleep(2500);
const unten = await page.evaluate(
  () => document.querySelector('[data-kamera="weidewache"]').getBoundingClientRect().top,
);
pruefe("Testlayout: Weidewache-Kachel liegt unterhalb des Bildschirms", unten > 844 + 150, `top=${Math.round(unten)}`);
pruefe("sichtbare Kachel verbindet sich", n.futterwache > 0, JSON.stringify(n));
pruefe("Kachel unterhalb des Bildschirms verbindet sich NICHT", n.weidewache === 0, `weidewache=${n.weidewache}`);

await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await sleep(2000);
pruefe("nach dem Scrollen verbindet sich die Kachel", n.weidewache > 0, `weidewache=${n.weidewache}`);

await page.evaluate(() => window.scrollTo(0, 0));
await sleep(7000); // Verzoegerung 5 s
const vor = n.weidewache;
await sleep(9000);
pruefe("aus dem Bild gescrollt: nach 5 s keine Anfragen mehr", n.weidewache === vor, `${vor} -> ${n.weidewache}`);

await setzeTab(false);
await sleep(500);
const h1 = JSON.stringify(n);
await sleep(12000);
pruefe("Tab verborgen: keine Anfragen", JSON.stringify(n) === h1, `${h1} -> ${JSON.stringify(n)}`);

const vorher = n.futterwache;
await setzeTab(true);
await sleep(2500);
pruefe("Tab wieder sichtbar: sichtbare Kachel verbindet sich neu", n.futterwache > vorher, `${vorher} -> ${n.futterwache}`);
pruefe("keine Seitenfehler", fehler.length === 0, fehler.slice(0, 2).join(" | "));

await browser.close();
process.exit(ergebnisse.every(Boolean) ? 0 : 1);
