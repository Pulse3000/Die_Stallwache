/**
 * E2E-Pruefung „Polling nur bei sichtbarem Tab" (lib/sichtbares-intervall.ts).
 *
 * /api/events und /api/tuya/geraete werden gestubbt und gezaehlt; die Uhr der
 * Seite laeuft simuliert (page.clock), damit Minuten in Sekunden vergehen.
 *
 *   npm run build && npm start -- -p 3102      (anderes Terminal)
 *   node tests/e2e/polling.mjs                 (BASE=http://localhost:3102)
 *
 * Braucht Chromium (CHROMIUM=/opt/pw-browsers/chromium) und playwright-core.
 * Gehoert nicht zu `npm test`.
 */

import { chromium } from "playwright-core";

const BASE = process.env.BASE ?? "http://localhost:3102";
const CHROMIUM = process.env.CHROMIUM ?? "/opt/pw-browsers/chromium";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ executablePath: CHROMIUM });
// Service Worker blocken: Er wickelt Abrufe sonst selbst ab, und page.route sieht sie nicht.
const page = await (
  await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" })
).newPage();

const n = { events: 0, geraete: 0 };
await page.route(/\/api\/events(\?.*)?$/, (r) => {
  n.events++;
  r.fulfill({ contentType: "application/json", body: JSON.stringify({ ereignisse: [], letzterKontakt: null, quelle: "demo" }) });
});
await page.route(/\/api\/tuya\/geraete$/, (r) => {
  n.geraete++;
  r.fulfill({ contentType: "application/json", body: JSON.stringify({ geraete: [] }) });
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
    Object.defineProperty(document, "visibilityState", { value: s ? "visible" : "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  }, sichtbar);
const gesamt = () => n.events + n.geraete;

for (const pfad of ["/wache", "/steuerung"]) {
  n.events = n.geraete = 0;
  await page.clock.install();
  await page.goto(BASE + pfad, { waitUntil: "networkidle" });
  await sleep(500);
  const start = gesamt();
  pruefe(`${pfad}: Erstabruf beim Laden`, start >= 1, `Anfragen=${start}`);

  await page.clock.runFor(130_000);
  const sichtbar = gesamt();
  pruefe(`${pfad}: sichtbarer Tab fragt im Takt an`, sichtbar > start, `${start} -> ${sichtbar}`);

  await setzeTab(false);
  await sleep(300);
  const vorPause = gesamt();
  await page.clock.runFor(10 * 60_000);
  await sleep(300);
  pruefe(`${pfad}: verborgener Tab, 10 min lang keine Anfragen`, gesamt() === vorPause, `${vorPause} -> ${gesamt()}`);

  await setzeTab(true);
  await sleep(500);
  pruefe(`${pfad}: Zurueckkehren laedt sofort frische Daten`, gesamt() > vorPause, `${vorPause} -> ${gesamt()}`);

  const nachSofort = gesamt();
  await page.clock.runFor(130_000);
  pruefe(`${pfad}: danach wieder im Takt`, gesamt() > nachSofort, `${nachSofort} -> ${gesamt()}`);
}
pruefe("keine Seitenfehler", fehler.length === 0, fehler.slice(0, 2).join(" | "));

await browser.close();
process.exit(ergebnisse.every(Boolean) ? 0 : 1);
