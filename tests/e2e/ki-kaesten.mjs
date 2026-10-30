/**
 * E2E-Pruefung „KI-Kaesten auf dem Livebild der Stallwache"
 * (docs/ki-ansicht-spezifikation.md §6, Kriterium 5) im echten Browser:
 * echtes HLS-Livevideo (hls.js), darueber die Kaesten an der richtigen
 * Stelle, mit dem Versatz des Videos, Texte fuer jeden Zustand, Takt 1/s,
 * im verborgenen Tab keine Abrufe, Klicks gehen durch die Kaesten hindurch.
 *
 * Nachgebildet werden die Stream-Zuteilung, eine mitlaufende HLS-Playlist
 * (Segmente aus ffmpeg) und /api/stallwache/fern/ki-kaesten (JSON wie
 * edge-agent/main.py KiAnsicht.daten(), Stall-Uhr absichtlich 1 h
 * daneben); der Rest der App laeuft echt.
 *
 *   NEXT_PUBLIC_STALLWACHE_FERN=1 NEXT_PUBLIC_BRIDGE_URL= npm run build
 *   npm start -- -p 3108                        (anderes Terminal)
 *   node tests/e2e/ki-kaesten.mjs               (BASE=http://localhost:3108)
 *
 * Braucht Chromium (CHROMIUM=/opt/pw-browsers/chromium), ffmpeg mit libx264
 * und die Dev-Dependency playwright-core. Gehoert nicht zu `npm test`.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright-core";

const BASE = process.env.BASE ?? "http://localhost:3108";
const CHROMIUM = process.env.CHROMIUM ?? "/opt/pw-browsers/chromium";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 1-s-Segmente, 640x360 (16:9 wie die Analyse 1920x1080)
const SEGMENTE = 240;
const FENSTER = 6;
const dir = mkdtempSync(join(tmpdir(), "ki-kaesten-"));
execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-f", "lavfi", "-i",
  `testsrc=size=640x360:rate=10:duration=${SEGMENTE}`, "-c:v", "libx264", "-preset", "ultrafast",
  "-pix_fmt", "yuv420p", "-g", "10", "-keyint_min", "10", "-sc_threshold", "0",
  "-f", "hls", "-hls_time", "1", "-hls_list_size", "0",
  "-hls_segment_filename", join(dir, "seg%03d.ts"), join(dir, "voll.m3u8")]);
const segment = (n) => readFileSync(join(dir, `seg${String(n).padStart(3, "0")}.ts`));

/** Mitlaufende Live-Playlist: je Sekunde ein Segment mehr. */
function playlist(start) {
  const ende = Math.min(SEGMENTE, FENSTER + Math.floor((Date.now() - start) / 1000));
  const zeilen = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:1",
    `#EXT-X-MEDIA-SEQUENCE:${ende - FENSTER}`];
  for (let n = ende - FENSTER; n < ende; n++) zeilen.push("#EXTINF:1.000,", `hls/seg${String(n).padStart(3, "0")}.ts`);
  return zeilen.join("\n") + "\n";
}

const STALL_UHR_VERSATZ_S = -3600; // Stall-Rechner geht 1 h nach

const browser = await chromium.launch({ executablePath: CHROMIUM });
const ergebnisse = [];
const pruefe = (name, ok, detail) => {
  ergebnisse.push(ok);
  console.log(`${ok ? "OK  " : "FEHL"} ${name}${detail ? ` – ${detail}` : ""}`);
};

async function oeffne(datensparen) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: "block" });
  await ctx.addInitScript((ds) => {
    localStorage.setItem("stallwache:einstellungen", JSON.stringify({ datensparen: ds, version: 2 }));
  }, datensparen);
  const page = await ctx.newPage();
  const zustand = { modus: "404", anfragen: 0, letzteSek: null, festZeit: null, start: Date.now() };

  await page.route(/\/api\/stallwache\/fern\/ki-kaesten(\?|$)/, (route) => {
    zustand.anfragen++;
    const m = zustand.modus;
    if (m === "bild" || m === "fest" || m === "schief") {
      const jetzt = Date.now() / 1000 + STALL_UHR_VERSATZ_S;
      const zeit = m === "fest" ? (zustand.festZeit ??= jetzt) : jetzt;
      if (m !== "fest") zustand.festZeit = null;
      const sek = Math.floor(zeit);
      zustand.letzteSek = sek;
      route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "Cache-Control": "no-store" },
        body: JSON.stringify({
          v: 1, kamera: "stallwache", zeit: Math.round(zeit * 100) / 100,
          breite: m === "schief" ? 1440 : 1920, hoehe: 1080, alarm_ab: 0.8,
          kuehe: [
            // Nummer = Sekunde der Erkennung: zeigt, welche Erkennung gewaehlt wurde
            { id: sek % 100000, box: [0.25, 0.25, 0.5, 0.75], winkel: 52.4 },
            // per Telegram /kuh benannt (docs/kuh-namen-spezifikation.md)
            { id: 7, box: [0.7, 0.1, 1.0, 0.45], winkel: null, name: "Berta" },
          ],
          objekte: [
            { klasse: "amniotic_sac", box: [0.05, 0.6, 0.15, 0.8], prozent: 91, alarm: true },
            // fast an derselben Stelle (Austreibung): Beschriftungen ueberlappen
            { klasse: "calf_legs", box: [0.07, 0.62, 0.17, 0.82], prozent: 79, alarm: false },
          ],
        }),
      });
    } else {
      route.fulfill({ status: Number(m), contentType: "application/json", body: '{"fehler":"test"}' });
    }
  });
  // Livebild: Zuteilung -> Fernzugriff-Playlist -> Segmente
  await page.route(/\/api\/stallwache\/stream$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json",
      body: JSON.stringify({ url: "/api/stallwache/fern/stream.m3u8", typ: "hls" }) }));
  await page.route(/\/api\/stallwache\/fern\/stream\.m3u8/, (route) =>
    route.fulfill({ status: 200, contentType: "application/vnd.apple.mpegurl",
      headers: { "Cache-Control": "no-store" }, body: playlist(zustand.start) }));
  await page.route(/\/api\/stallwache\/fern\/hls\/seg(\d+)\.ts/, (route) => {
    const n = Number(route.request().url().match(/seg(\d+)\.ts/)[1]);
    route.fulfill({ status: 200, contentType: "video/mp2t", body: segment(n) });
  });
  // Zweitkameras still halten (nicht Gegenstand dieses Tests)
  await page.route(/\/api\/(futterwache|abkalbebox|weidewache)\/stream$/, (route) =>
    route.fulfill({ status: 502, contentType: "application/json", body: '{"fehler":"test"}' }));

  const fehler = [];
  page.on("pageerror", (e) => fehler.push(e.message));
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-kamera="stallwache"]');
  return { ctx, page, zustand, fehler };
}

const knopf = (page, kam) => page.locator(`[data-kamera="${kam}"] button[aria-pressed]`);
const ki = (page) =>
  page.evaluate(() => {
    const el = document.querySelector("[data-ki-zustand]");
    if (!el) return null;
    return {
      zustand: el.dataset.kiZustand,
      kaesten: Number(el.dataset.kiKaesten),
      text: el.querySelector("p").textContent,
    };
  });
async function warteAuf(page, bedingung, ms = 20000) {
  const ende = Date.now() + ms;
  while (Date.now() < ende) {
    const k = await ki(page);
    if (k && bedingung(k)) return true;
    await sleep(200);
  }
  return false;
}
const warteAufText = (page, teil, ms) => warteAuf(page, (k) => k.text.includes(teil), ms);
const videoLaeuft = (page) =>
  page.evaluate(() => {
    const v = document.querySelector('[data-kamera="stallwache"] video');
    return !!v && !v.paused && v.readyState >= 2 && v.videoWidth > 0;
  });

// ---- 1. Datensparen aus ----
{
  console.log("\n# Datensparen aus");
  const { ctx, page, zustand, fehler } = await oeffne(false);
  pruefe("Schalter nur an der Stallwache", (await knopf(page, "stallwache").count()) === 1
    && (await knopf(page, "futterwache").count()) === 0
    && (await knopf(page, "abkalbebox").count()) === 0);
  await sleep(1500);
  pruefe("vor dem Einschalten keine Abrufe", zustand.anfragen === 0, String(zustand.anfragen));

  await knopf(page, "stallwache").click();
  pruefe("Klick auf den Schalter oeffnet kein Vollbild", (await page.locator("article.fixed").count()) === 0);
  pruefe("aria-pressed=true", (await knopf(page, "stallwache").getAttribute("aria-pressed")) === "true");
  pruefe("404 -> „Keine KI-Kästen – vom Stall-Rechner kommen gerade keine Erkennungen“",
    await warteAufText(page, "vom Stall-Rechner kommen gerade keine Erkennungen"));

  let laeuft = false;
  for (let i = 0; i < 60 && !laeuft; i++) { await sleep(250); laeuft = await videoLaeuft(page); }
  pruefe("HLS-Livevideo laeuft", laeuft);

  zustand.modus = "bild";
  pruefe("Erkennungen -> „KI · 2 Kühe · Versatz ≈ … s“",
    await warteAuf(page, (k) => /^KI · 2 Kühe · Versatz ≈ \d+ s · Nr\. von der KI, nicht Ohrmarke$/.test(k.text) && k.kaesten === 4));
  const arten = await page.$$eval("[data-ki-art]", (els) => els.map((e) => [e.dataset.kiArt, e.textContent]));
  pruefe("4 Kaesten: 2 Kuh, 1 Alarm, 1 unter Schwelle",
    JSON.stringify(arten.map((a) => a[0]).sort()) === JSON.stringify(["alarm", "kuh", "kuh", "unter"]),
    JSON.stringify(arten));
  pruefe("Fruchtblase rot mit „ALARM“", arten.some(([a, t]) => a === "alarm" && t === "Fruchtblase 91 % ALARM"));
  pruefe("Kälberfüße unter Schwelle ohne „ALARM“",
    arten.some(([a, t]) => a === "unter" && t === "Kälberfüße? 79 % (Alarm ab 80 %)"));
  pruefe("Kuh mit Namen, ohne Winkel: „Kuh #7 · Berta“",
    arten.some(([a, t]) => a === "kuh" && t === "Kuh #7 · Berta"));
  pruefe("Kuh ohne Namen: „Kuh #N · 52°“", arten.some(([a, t]) => a === "kuh" && /^Kuh #\d+ · 52°$/.test(t)));
  pruefe("LIVE-Kennzeichen bleibt sichtbar",
    (await page.locator('[data-kamera="stallwache"] span', { hasText: /^LIVE$/ }).count()) === 1);

  // Lage: Kachel 16:9, Video 16:9 -> Kasten [0.25,0.25,0.5,0.75] relativ zur Flaeche
  const lage = await page.evaluate(() => {
    const f = document.querySelector("[data-ki-zustand]").getBoundingClientRect();
    const kuh = [...document.querySelectorAll('[data-ki-art="kuh"]')]
      .find((e) => e.textContent.endsWith("· 52°")).getBoundingClientRect();
    return { x: (kuh.left - f.left) / f.width, y: (kuh.top - f.top) / f.height,
      w: kuh.width / f.width, h: kuh.height / f.height };
  });
  const nah = (a, b) => Math.abs(a - b) < 0.01;
  pruefe("Kasten sitzt an der richtigen Stelle (±1 %)",
    nah(lage.x, 0.25) && nah(lage.y, 0.25) && nah(lage.w, 0.25) && nah(lage.h, 0.5), JSON.stringify(lage));

  const marken = await page.evaluate(() => {
    const flaeche = document.querySelector("[data-ki-zustand]");
    const f = flaeche.getBoundingClientRect();
    flaeche.style.pointerEvents = "auto"; // nur fuer elementFromPoint
    const s = document.querySelector('[data-kamera="stallwache"] button[aria-pressed]').getBoundingClientRect();
    const ueber = (a, b) => a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
    const liste = [...document.querySelectorAll("[data-ki-art] > span")].map((m) => {
      const r = m.getBoundingClientRect();
      // Liegt die Beschriftung an Mitte und Ecken wirklich oben?
      const punkte = [[0.5, 0.5], [0.05, 0.2], [0.95, 0.2], [0.05, 0.8], [0.95, 0.8]];
      const sichtbar = punkte.every(([px, py]) => m.contains(document.elementFromPoint(
        r.left + px * r.width, r.top + py * r.height)));
      return { text: m.textContent, drin: r.left >= f.left - 0.5 && r.right <= f.right + 0.5
        && r.top >= f.top - 0.5, unterSchalter: ueber(r, s), sichtbar };
    });
    flaeche.style.pointerEvents = "";
    return liste;
  });
  pruefe("Beschriftungen ganz im Bild und nicht unter dem Schalter",
    marken.length === 4 && marken.every((m) => m.drin && !m.unterSchalter), JSON.stringify(marken));
  pruefe("ALARM-Beschriftung wird von nichts verdeckt (Kälberfüße an derselben Stelle)",
    marken.some((m) => m.text.endsWith("ALARM") && m.sichtbar), JSON.stringify(marken));

  // Versatz: gezeigte Erkennung liegt um den Video-Versatz hinter der neuesten
  await sleep(3000);
  const v = await page.evaluate(() => {
    const t = document.querySelector("[data-ki-zustand] p").textContent;
    const kuh = [...document.querySelectorAll('[data-ki-art="kuh"]')].find((e) => e.textContent.endsWith("· 52°"));
    return { versatz: Number(t.match(/Versatz ≈ (\d+) s/)?.[1]), id: Number(kuh?.textContent.match(/#(\d+)/)?.[1]) };
  });
  const rueck = (zustand.letzteSek % 100000) - v.id;
  pruefe("gezeigte Erkennung liegt um den Versatz zurueck (nicht die neueste)",
    rueck >= 1 && Math.abs(rueck - v.versatz) <= 2, `zurueck ${rueck} s, Versatz ≈ ${v.versatz} s`);

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

  // Klick mitten ins Bild (auf einen Kasten) oeffnet das Vollbild: Kaesten nehmen keine Klicks
  const kasten = await page.locator('[data-ki-art="kuh"]').first().boundingBox();
  await page.mouse.click(kasten.x + kasten.width / 2, kasten.y + kasten.height / 2);
  await sleep(500);
  pruefe("Klick durch die Kaesten oeffnet das Vollbild", (await page.locator("article.fixed").count()) === 1);
  pruefe("Kaesten auch im Vollbild", await warteAuf(page, (k) => k.kaesten === 4, 5000));
  await page.locator("article.fixed button", { hasText: "Zurück" }).click();
  await sleep(500);

  zustand.modus = "schief";
  pruefe("anderes Seitenverhaeltnis -> Kaesten ausgeblendet mit Hinweis",
    await warteAuf(page, (k) => k.kaesten === 0 && k.text.startsWith("KI-Kästen ausgeblendet")));

  zustand.modus = "fest";
  pruefe("Erkennungszeit steht still -> nach > 10 s „nicht aktuell“, keine Kaesten",
    await warteAuf(page, (k) => k.kaesten === 0 && k.text.startsWith("KI-Kästen nicht aktuell – letzte Erkennung"), 20000));

  zustand.modus = "502";
  pruefe("502 -> „Fernzugriff zum Stall gestört“", await warteAufText(page, "Fernzugriff zum Stall gestört"));
  zustand.modus = "401";
  pruefe("401 -> „bitte neu anmelden“", await warteAufText(page, "bitte neu anmelden"));

  await knopf(page, "stallwache").click();
  await sleep(300);
  const aus = zustand.anfragen;
  await sleep(3000);
  pruefe("ausgeschaltet: Kaesten weg, keine Abrufe mehr, Video laeuft weiter",
    (await ki(page)) === null && zustand.anfragen === aus && (await videoLaeuft(page)),
    String(zustand.anfragen - aus));

  await knopf(page, "stallwache").click();
  await page.locator('[data-kamera="futterwache"] button', { hasText: "Als Hauptbild" }).first().click();
  await sleep(500);
  pruefe("andere Kamera als Hauptbild: kein Schalter, keine Kaesten",
    (await knopf(page, "futterwache").count()) === 0 && (await ki(page)) === null);
  pruefe("keine Seitenfehler", fehler.length === 0, fehler.join(" | "));
  await ctx.close();
}

// ---- 2. Datensparen an: Einschalten startet das Livebild ----
{
  console.log("\n# Datensparen an");
  const { ctx, page, zustand, fehler } = await oeffne(true);
  await sleep(1500);
  pruefe("Vorschau: „Live starten“ sichtbar",
    (await page.locator('[data-kamera="stallwache"] button', { hasText: "Live starten" }).count()) === 1);
  zustand.modus = "bild";
  await knopf(page, "stallwache").click();
  pruefe("Einschalten startet das Livebild („Live starten“ weg)",
    (await page.locator('[data-kamera="stallwache"] button', { hasText: "Live starten" }).count()) === 0);
  pruefe("Kaesten erscheinen auf dem Livebild", await warteAuf(page, (k) => k.kaesten === 4, 25000));
  pruefe("keine Seitenfehler", fehler.length === 0, fehler.join(" | "));
  await ctx.close();
}

await browser.close();
rmSync(dir, { recursive: true, force: true });
const fehl = ergebnisse.filter((x) => !x).length;
console.log(`\nKI-Kästen E2E: ${ergebnisse.length - fehl}/${ergebnisse.length} bestanden`);
process.exit(fehl ? 1 : 0);
