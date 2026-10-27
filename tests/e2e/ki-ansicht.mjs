/**
 * E2E-Pruefung „KI-Ansicht der Stallwache" (docs/ki-ansicht-spezifikation.md
 * §6, Kriterium 5) im echten Browser: Schalter nur an der Stallwache mit
 * Fernzugriff, Bild je Sekunde (bei Datensparen alle 5 s), im verborgenen Tab
 * keine Abrufe, Texte fuer „aus", „nicht aktuell", „gestoert".
 *
 * Der Endpunkt /api/stallwache/fern/ki-ansicht wird nachgebildet (JPEG
 * mit X-Bild-Zeit, 404, 502); der Rest der App laeuft echt.
 *
 *   NEXT_PUBLIC_STALLWACHE_FERN=1 NEXT_PUBLIC_BRIDGE_URL= npm run build
 *   npm start -- -p 3108                        (anderes Terminal)
 *   node tests/e2e/ki-ansicht.mjs               (BASE=http://localhost:3108)
 *
 * Braucht Chromium (CHROMIUM=/opt/pw-browsers/chromium), ffmpeg und die
 * Dev-Dependency playwright-core. Gehoert nicht zu `npm test`.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright-core";

const BASE = process.env.BASE ?? "http://localhost:3108";
const CHROMIUM = process.env.CHROMIUM ?? "/opt/pw-browsers/chromium";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const dir = mkdtempSync(join(tmpdir(), "ki-ansicht-"));
execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=320x180",
  "-frames:v", "1", join(dir, "bild.jpg")]);
const JPEG = readFileSync(join(dir, "bild.jpg"));

const browser = await chromium.launch({ executablePath: CHROMIUM });
const ergebnisse = [];
const pruefe = (name, ok, detail) => {
  ergebnisse.push(ok);
  console.log(`${ok ? "OK  " : "FEHL"} ${name}${detail ? ` – ${detail}` : ""}`);
};

/** Kontext mit nachgebildeter KI-Ansicht; `modus` steuert die Antwort. */
async function oeffne(datensparen) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
  await ctx.addInitScript((ds) => {
    localStorage.setItem("stallwache:einstellungen", JSON.stringify({ datensparen: ds, version: 2 }));
  }, datensparen);
  const page = await ctx.newPage();
  const zustand = { modus: "404", bildZeit: Math.floor(Date.now() / 1000), anfragen: 0 };
  await page.route(/\/api\/stallwache\/fern\/ki-ansicht(\?|$)/, (route) => {
    zustand.anfragen++;
    if (zustand.modus === "bild" || zustand.modus === "fest") {
      if (zustand.modus === "bild") zustand.bildZeit++;
      route.fulfill({
        status: 200,
        contentType: "image/jpeg",
        headers: { "X-Bild-Zeit": String(zustand.bildZeit), "Cache-Control": "no-store" },
        body: JPEG,
      });
    } else {
      const status = Number(zustand.modus);
      route.fulfill({ status, contentType: "application/json", body: '{"fehler":"test"}' });
    }
  });
  // Livebild-Wege still halten (nicht Gegenstand dieses Tests)
  await page.route(/\/api\/(\w+)\/stream$|\/api\/stallwache\/fern\/(stream|hls)/, (route) =>
    route.fulfill({ status: 502, contentType: "application/json", body: '{"fehler":"test"}' }),
  );
  const fehler = [];
  page.on("pageerror", (e) => fehler.push(e.message));
  await page.goto(BASE, { waitUntil: "networkidle" });
  return { ctx, page, zustand, fehler };
}

const knopf = (page, kam) =>
  page.locator(`[data-kamera="${kam}"] button[aria-pressed]`);
const fuss = (page) =>
  page.evaluate(() => {
    const el = document.querySelector("[data-ki-zustand]");
    return el ? { zustand: el.dataset.kiZustand, text: el.querySelector("p").textContent } : null;
  });
async function warteAufText(page, teil, ms = 15000) {
  const ende = Date.now() + ms;
  while (Date.now() < ende) {
    const f = await fuss(page);
    if (f && f.text.includes(teil)) return true;
    await sleep(200);
  }
  return false;
}

// ---- 1. Datensparen aus: Schalter, Texte, Takt, verborgener Tab ----
{
  console.log("\n# Datensparen aus");
  const { ctx, page, zustand, fehler } = await oeffne(false);
  pruefe("Schalter nur an der Stallwache", (await knopf(page, "stallwache").count()) === 1
    && (await knopf(page, "futterwache").count()) === 0
    && (await knopf(page, "abkalbebox").count()) === 0, "");
  pruefe("vor dem Einschalten keine Abrufe", zustand.anfragen === 0, String(zustand.anfragen));

  await knopf(page, "stallwache").click();
  pruefe("Klick oeffnet kein Vollbild", (await page.locator("article.fixed").count()) === 0);
  pruefe("404 -> „Keine KI-Ansicht … analysiert gerade nicht“",
    await warteAufText(page, "der Edge-Agent analysiert gerade nicht"));

  zustand.modus = "bild";
  pruefe("Bild -> „KI-Ansicht · Stand …“", await warteAufText(page, "KI-Ansicht · Stand"));
  pruefe("Bild sichtbar", (await page.locator('[data-ki-zustand="bild"] img').count()) === 1);
  pruefe("LIVE-Kennzeichen ausgeblendet",
    (await page.locator('[data-kamera="stallwache"] span', { hasText: "LIVE" }).count()) === 0);
  const vorher = zustand.anfragen;
  await sleep(5000);
  const takt = zustand.anfragen - vorher;
  pruefe("etwa 1 Abruf je Sekunde (4–6 in 5 s)", takt >= 4 && takt <= 6, String(takt));

  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  const verborgen = zustand.anfragen;
  await sleep(4000);
  pruefe("verborgener Tab: keine Abrufe", zustand.anfragen === verborgen, String(zustand.anfragen - verborgen));
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await sleep(1500);
  pruefe("wieder sichtbar: Abrufe laufen weiter", zustand.anfragen > verborgen);

  zustand.modus = "fest";
  pruefe("Bildzeit steht still -> nach > 10 s „nicht aktuell“",
    await warteAufText(page, "KI-Ansicht nicht aktuell – letztes Bild von", 16000));
  pruefe("altes Bild bleibt abgeblendet stehen",
    (await page.locator('[data-ki-zustand="alt"] img.opacity-40').count()) === 1);

  zustand.modus = "502";
  pruefe("502 -> „Fernzugriff zum Stall gestört“", await warteAufText(page, "Fernzugriff zum Stall gestört"));
  zustand.modus = "401";
  pruefe("401 -> „bitte neu anmelden“", await warteAufText(page, "bitte neu anmelden"));

  await knopf(page, "stallwache").click();
  await sleep(300);
  const aus = zustand.anfragen;
  await sleep(3000);
  pruefe("„Video“: Ansicht weg, keine Abrufe mehr",
    (await fuss(page)) === null && zustand.anfragen === aus, String(zustand.anfragen - aus));

  await knopf(page, "stallwache").click();
  await page.locator('[data-kamera="futterwache"] button', { hasText: "Als Hauptbild" }).first().click();
  await sleep(500);
  pruefe("andere Kamera als Hauptbild: kein Schalter, keine Ansicht",
    (await knopf(page, "futterwache").count()) === 0 && (await fuss(page)) === null);
  pruefe("keine Seitenfehler", fehler.length === 0, fehler.join(" | "));
  await ctx.close();
}

// ---- 2. Datensparen an: alle 5 s ----
{
  console.log("\n# Datensparen an");
  const { ctx, page, zustand, fehler } = await oeffne(true);
  zustand.modus = "bild";
  await knopf(page, "stallwache").click();
  pruefe("Bild kommt", await warteAufText(page, "KI-Ansicht · Stand"));
  pruefe("„Live starten“ verdeckt die Fusszeile nicht",
    (await page.locator('[data-kamera="stallwache"] button', { hasText: "Live starten" }).count()) === 0);
  const vorher = zustand.anfragen;
  await sleep(11000);
  const takt = zustand.anfragen - vorher;
  pruefe("etwa alle 5 s (2–3 in 11 s)", takt >= 2 && takt <= 3, String(takt));
  pruefe("keine Seitenfehler", fehler.length === 0, fehler.join(" | "));
  await ctx.close();
}

await browser.close();
rmSync(dir, { recursive: true, force: true });
const fehl = ergebnisse.filter((x) => !x).length;
console.log(`\nKI-Ansicht E2E: ${ergebnisse.length - fehl}/${ergebnisse.length} bestanden`);
process.exit(fehl ? 1 : 0);
