/**
 * E2E-Pruefung „Kachel-Status ohne Bridge" (docs/vorschau-status-spezifikation.md
 * §6.3) im echten Browser: Kopfzaehler, System-Punkt und Kachel-Status mit
 * leerer NEXT_PUBLIC_BRIDGE_URL – Datensparen an und aus, mit Rollenwechsel.
 *
 * Die Stream-Endpunkte werden nachgebildet (200 mit HLS-URL bzw. 502); das
 * HLS ist ein echter VP9-fMP4-Stream (ffmpeg), damit „Online" am echten
 * `playing`-Ereignis haengt und nicht an einer Attrappe.
 *
 *   NEXT_PUBLIC_STALLWACHE_FERN=1 NEXT_PUBLIC_BRIDGE_URL= npm run build
 *   npm start -- -p 3107                        (anderes Terminal)
 *   node tests/e2e/vorschau-status.mjs          (BASE=http://localhost:3107)
 *
 * Braucht Chromium (CHROMIUM=/opt/pw-browsers/chromium), ffmpeg mit libvpx
 * und die Dev-Dependency playwright-core. Gehoert nicht zu `npm test`.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright-core";

const BASE = process.env.BASE ?? "http://localhost:3107";
const CHROMIUM = process.env.CHROMIUM ?? "/opt/pw-browsers/chromium";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const KAMERAS = ["stallwache", "futterwache", "abkalbebox", "weidewache"];

// ---- Testbild: 2 min VP9 in fMP4-HLS (Chromium kann ohne H.264 nur so MSE) ----
const hlsDir = mkdtempSync(join(tmpdir(), "vorschau-hls-"));
execFileSync("ffmpeg", [
  "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10",
  "-t", "120", "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
  "-b:v", "200k", "-g", "10", "-f", "hls", "-hls_segment_type", "fmp4",
  "-hls_time", "2", "-hls_list_size", "0", "-hls_playlist_type", "vod",
  join(hlsDir, "index.m3u8"),
]);

const browser = await chromium.launch({ executablePath: CHROMIUM });
const ergebnisse = [];
const pruefe = (name, ok, detail) => {
  ergebnisse.push(ok);
  console.log(`${ok ? "OK  " : "FEHL"} ${name}${detail ? ` – ${detail}` : ""}`);
};

/** Neuer Browser-Kontext mit Datensparen-Einstellung und nachgebildeten Quellen. */
async function oeffne({ datensparen, quelle = {}, uhr = false }) {
  // Service Worker blockieren: Er holt sonst die HLS-Dateien selbst, und
  // page.route sieht diese Anfragen nicht (404 vom Server statt Testbild).
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
  await ctx.addInitScript((ds) => {
    localStorage.setItem("stallwache:einstellungen", JSON.stringify({ datensparen: ds, version: 2 }));
  }, datensparen);
  const page = await ctx.newPage();
  if (uhr) await page.clock.install();
  const anfragen = Object.fromEntries(KAMERAS.map((k) => [k, 0]));
  await page.route(/\/api\/(\w+)\/stream$/, (route) => {
    const kam = route.request().url().match(/api\/(\w+)\/stream/)[1];
    anfragen[kam]++;
    if ((quelle[kam] ?? "ok") === "ok") {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ url: `/e2e-hls/${kam}/index.m3u8`, typ: "hls" }),
      });
    } else {
      route.fulfill({ status: 502, contentType: "application/json", body: '{"fehler":"test"}' });
    }
  });
  await page.route(/\/e2e-hls\/\w+\/([\w.]+)$/, (route) => {
    const datei = route.request().url().match(/\/e2e-hls\/\w+\/([\w.]+)$/)[1];
    const typ = datei.endsWith(".m3u8") ? "application/vnd.apple.mpegurl" : "video/mp4";
    route.fulfill({ status: 200, contentType: typ, body: readFileSync(join(hlsDir, datei)) });
  });
  const fehler = [];
  page.on("pageerror", (e) => fehler.push(e.message));
  await page.goto(BASE, { waitUntil: "networkidle" });
  return { ctx, page, anfragen, fehler };
}

const zustaende = (page) =>
  page.evaluate(() =>
    Object.fromEntries(
      [...document.querySelectorAll("[data-kamera]")].map((el) => [el.dataset.kamera, el.dataset.zustand]),
    ),
  );
const kopf = (page) =>
  page.evaluate(() => ({
    text: document.querySelector("[data-kopftext]").textContent,
    ton: document.querySelector('[aria-label="Systemstatus"]').dataset.ton,
  }));
async function warteAuf(page, kam, zustand, ms = 20000) {
  const ende = Date.now() + ms;
  while (Date.now() < ende) {
    if ((await zustaende(page))[kam] === zustand) return true;
    await sleep(250);
  }
  return false;
}
const klick = (page, kam, text) =>
  page.locator(`[data-kamera="${kam}"] button`, { hasText: text }).first().click();

// ---- 1. Datensparen an, alle Quellen 2xx ----
{
  console.log("\n# Datensparen an, alle Quellen senden");
  const { ctx, page, anfragen, fehler } = await oeffne({ datensparen: true });
  await sleep(5000);
  const z = await zustaende(page);
  const k = await kopf(page);
  const sichtbar = KAMERAS.filter((c) => z[c] !== "pausiert");
  pruefe("Testlayout: mind. drei Kacheln sichtbar, eine pausiert", sichtbar.length >= 3 && sichtbar.length < 4, JSON.stringify(z));
  pruefe("keine sichtbare Kachel „Lädt“ oder „Online“", sichtbar.every((c) => z[c] === "ungeprueft"), JSON.stringify(z));
  pruefe("Kopf nennt „ungeprüft“, nie „0 von“", k.text.includes("ungeprüft") && !k.text.includes("0 von"), k.text);
  pruefe("System-Punkt nicht rot", k.ton !== "stoerung", k.ton);

  await sleep(15000);
  const pausierte = KAMERAS.filter((c) => z[c] === "pausiert");
  pruefe(
    "Sparsamkeit: je Vorschau-Kachel hoechstens 1 Ping in 20 s, pausierte 0",
    sichtbar.every((c) => anfragen[c] <= 1) && pausierte.every((c) => anfragen[c] === 0),
    JSON.stringify(anfragen),
  );

  await klick(page, "stallwache", "Live starten");
  pruefe("„Live starten“: Hauptbild wird „Online“ (echtes playing)", await warteAuf(page, "stallwache", "online"));
  const k2 = await kopf(page);
  pruefe("Kopf beginnt mit „1 online“, Punkt gruen", k2.text.startsWith("1 online") && k2.ton === "ok", `${k2.text} / ${k2.ton}`);

  await klick(page, "futterwache", "Als Hauptbild");
  await sleep(800);
  const z3 = await zustaende(page);
  pruefe("Rollenwechsel: bisheriges Hauptbild „Ungeprüft“, nicht „Online“", z3.stallwache === "ungeprueft", JSON.stringify(z3));
  pruefe("Rollenwechsel: neues Hauptbild wird „Online“", await warteAuf(page, "futterwache", "online"));
  await sleep(3000);
  pruefe("bisheriges Hauptbild bleibt ohne Beweis „Ungeprüft“", (await zustaende(page)).stallwache === "ungeprueft");
  const k3 = await kopf(page);
  pruefe("Kopf nach Rollenwechsel ehrlich", k3.text.startsWith("1 online") && k3.text.includes("2 ungeprüft") && k3.ton === "ok", k3.text);

  await klick(page, "stallwache", "Als Hauptbild");
  await warteAuf(page, "stallwache", "online");
  await sleep(1500);
  const liste = await page.locator('[aria-label="Letzte Ereignisse"]').innerText();
  const n = liste.split("Stallwache ist online").length - 1;
  pruefe("Ereignisliste: „Stallwache ist online“ nach Hin- und Rueckwechsel nur einmal", n === 1, `${n}×`);
  pruefe("keine Seitenfehler", fehler.length === 0, fehler.slice(0, 2).join(" | "));
  console.log(`  Kopf: „${k.text}“ → „${k2.text}“ → „${k3.text}“`);
  await ctx.close();
}

// ---- 2. Datensparen an, eine Quelle gestoert (502) ----
{
  console.log("\n# Datensparen an, Abkalbebox antwortet 502");
  const { ctx, page, anfragen, fehler } = await oeffne({ datensparen: true, quelle: { abkalbebox: "fehler" }, uhr: true });
  await page.clock.runFor(5000);
  await sleep(500);
  pruefe("nach dem 1. Fehlschlag noch nicht „Offline“", (await zustaende(page)).abkalbebox === "ungeprueft", `Anfragen ${anfragen.abkalbebox}`);
  await page.clock.runFor(61000);
  await sleep(500);
  const z = await zustaende(page);
  const k = await kopf(page);
  pruefe("nach dem 2. Fehlschlag „Offline“", z.abkalbebox === "offline", `${JSON.stringify(z)}, Anfragen ${anfragen.abkalbebox}`);
  pruefe("Kopf zaehlt sie, Punkt rot (keine Kamera online)", k.text.startsWith("0 von 1 online") && k.ton === "stoerung", `${k.text} / ${k.ton}`);
  pruefe("gesunde Vorschau-Kacheln bleiben „Ungeprüft“", z.stallwache === "ungeprueft" && z.futterwache === "ungeprueft", JSON.stringify(z));
  pruefe("keine Seitenfehler", fehler.length === 0, fehler.slice(0, 2).join(" | "));
  await ctx.close();
}

// ---- 3. Datensparen aus: alle sichtbaren Kacheln live ----
{
  console.log("\n# Datensparen aus");
  const { ctx, page, fehler } = await oeffne({ datensparen: false });
  const sichtbar = KAMERAS.filter((c) => c !== "weidewache");
  let alleOnline = true;
  for (const c of sichtbar) alleOnline = (await warteAuf(page, c, "online")) && alleOnline;
  const z = await zustaende(page);
  const k = await kopf(page);
  pruefe("sichtbare Kacheln „Online“ (echtes playing)", alleOnline, JSON.stringify(z));
  pruefe("keine Kachel „Ungeprüft“", !Object.values(z).includes("ungeprueft"), JSON.stringify(z));
  pruefe("Kopf ohne „ungeprüft“, Punkt gruen", !k.text.includes("ungeprüft") && k.ton === "ok", `${k.text} / ${k.ton}`);

  await klick(page, "futterwache", "Als Hauptbild");
  await sleep(2500);
  const z2 = await zustaende(page);
  pruefe("Rollenwechsel ohne Datensparen: alle sichtbaren bleiben/werden „Online“", sichtbar.every((c) => z2[c] === "online"), JSON.stringify(z2));
  pruefe("keine Seitenfehler", fehler.length === 0, fehler.slice(0, 2).join(" | "));
  console.log(`  Kopf: „${k.text}“`);
  await ctx.close();
}

await browser.close();
rmSync(hlsDir, { recursive: true, force: true });
process.exit(ergebnisse.every(Boolean) ? 0 : 1);
