/**
 * Messung „Livebild holt nach einer Pause auf" im echten Browser (hls.js).
 *
 * Hintergrund: Mit den frueheren Player-Einstellungen blieb die Verzoegerung
 * nach jeder Pause (Handy gesperrt, Tab im Hintergrund) dauerhaft um die
 * Pausenlaenge groesser (lib/hls-live.ts). Dieser Test stellt das mit einer
 * mitlaufenden Live-Playlist nach — alte und neue Konfiguration nebeneinander —
 * und misst den Abstand der Wiedergabe zum Playlist-Ende (dieselbe Groesse,
 * aus der die KI-Kaesten ihren Versatz bilden). Der Code aus lib/hls-live.ts
 * laeuft dabei unveraendert im Browser.
 *
 *   node tests/e2e/hls-aufholen.mjs
 *   LIB=pfad/zu/hls-live.ts node tests/e2e/hls-aufholen.mjs   # Gegenprobe mit anderer Fassung
 *
 * Braucht Chromium (CHROMIUM=/opt/pw-browsers/chromium), ffmpeg mit libx264
 * und playwright-core. Keine Webapp noetig. Gehoert nicht zu `npm test`.
 * Exit 0 = das Testmaterial reicht fuer jeden Lauf UND die alte Einstellung
 * haengt fest UND die neue holt auf UND die neue friert bei schwankender
 * Segment-Ladezeit nicht oefter ein als die alte (Befund qa-waechter:
 * Aufholen per 1,15-facher Geschwindigkeit tat das).
 */

import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { stripTypeScriptTypes } from "node:module";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const CHROMIUM = process.env.CHROMIUM ?? "/opt/pw-browsers/chromium";
const hier = dirname(fileURLToPath(import.meta.url));
const HLS_JS = join(hier, "../../node_modules/hls.js/dist/hls.min.js");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Das echte Modul: Typen entfernen, `export` weglassen, als Skript laden.
const libJs = stripTypeScriptTypes(readFileSync(process.env.LIB ?? join(hier, "../../lib/hls-live.ts"), "utf8"))
  .replace(/^export /gm, "");

const SEG_S = Number(process.env.SEG_S ?? 2);       // Segmentdauer (Cloud-HLS: 2..6 s)
const FENSTER = Math.max(6, Math.ceil(30 / SEG_S));  // Segmente in der Playlist (~30 s)
const SEGMENTE = Math.ceil(150 / SEG_S);            // 150 s Material
const PAUSE_S = Number(process.env.PAUSE_S ?? 10);  // Pause, wie bei einem kurz gesperrten Handy
const ERHOLUNG_S = 16; // so lange darf das Aufholen dauern
const SCHWANKUNG_MS = Number(process.env.JITTER ?? 1500); // Ladezeit je Segment 0..x ms
const SCHWANKUNG_S = 40; // Dauer des Laufs mit schwankender Ladezeit

const dir = mkdtempSync(join(tmpdir(), "hls-aufholen-"));
execFileSync("ffmpeg", ["-loglevel", "error", "-y", "-f", "lavfi", "-i",
  `testsrc=size=320x180:rate=10:duration=${SEGMENTE * SEG_S}`, "-c:v", "libx264",
  "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", "20", "-keyint_min", "20",
  "-sc_threshold", "0", "-f", "hls", "-hls_time", String(SEG_S), "-hls_list_size", "0",
  "-hls_segment_filename", join(dir, "seg%03d.ts"), join(dir, "voll.m3u8")]);
const segment = (n) => readFileSync(join(dir, `seg${String(n).padStart(3, "0")}.ts`));

// Jeder Lauf startet die Live-Uhr neu. Mit einer gemeinsamen Uhr war das
// Material in den spaeteren Laeufen erschoepft: Die Playlist wuchs nicht mehr,
// und die Netz-Laeufe verglichen nur noch das Materialende (Befund qa-waechter M1).
const uhr = { start: Date.now() };
const MATERIAL_MS = (SEGMENTE - FENSTER) * SEG_S * 1000; // so lange waechst die Playlist
function playlist() {
  const ende = Math.min(SEGMENTE, FENSTER + Math.floor((Date.now() - uhr.start) / (SEG_S * 1000)));
  const z = ["#EXTM3U", "#EXT-X-VERSION:3", `#EXT-X-TARGETDURATION:${SEG_S}`,
    `#EXT-X-MEDIA-SEQUENCE:${ende - FENSTER}`];
  for (let n = ende - FENSTER; n < ende; n++)
    z.push(`#EXTINF:${SEG_S}.000,`, `seg/${String(n).padStart(3, "0")}.ts`);
  return z.join("\n") + "\n";
}

const hlsJs = readFileSync(HLS_JS);
// Schwankende Ladezeit: fuer jeden Lauf dieselbe Folge (gleiche Bedingungen alt/neu).
const netz = { schwankung: 0, saat: 1 };
const zufall = () => ((netz.saat = (netz.saat * 1103515245 + 12345) % 2147483648) / 2147483648);
const server = createServer((req, res) => {
  const u = req.url ?? "";
  if (u.startsWith("/hls.js")) {
    res.writeHead(200, { "Content-Type": "text/javascript" }).end(hlsJs);
  } else if (u.startsWith("/live.m3u8")) {
    res.writeHead(200, { "Content-Type": "application/vnd.apple.mpegurl", "Cache-Control": "no-store" })
      .end(playlist());
  } else if (/^\/seg\/\d+\.ts/.test(u)) {
    const n = Number(u.match(/seg\/(\d+)\.ts/)[1]);
    const senden = () => res.writeHead(200, { "Content-Type": "video/mp2t" }).end(segment(n));
    if (netz.schwankung) setTimeout(senden, zufall() * netz.schwankung);
    else senden();
  } else {
    res.writeHead(200, { "Content-Type": "text/html" }).end("<!doctype html><video id=v muted playsinline></video>");
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch({
  executablePath: CHROMIUM,
  args: ["--autoplay-policy=no-user-gesture-required", "--no-sandbox"],
});

/** Abstand der Wiedergabe zum Playlist-Ende in Sekunden. */
const abstand = (page) => page.evaluate(() => {
  const v = document.getElementById("v");
  return v.seekable.length ? v.seekable.end(v.seekable.length - 1) - v.currentTime : null;
});

/** neu=false: Einstellung vor der Korrektur; neu=true: lib/hls-live.ts wie in CameraStream.tsx. */
async function messe(name, neu, mitPause, schwankung = 0) {
  netz.schwankung = schwankung;
  netz.saat = 1;
  uhr.start = Date.now();
  const page = await browser.newPage();
  const fehler = [];
  page.on("pageerror", (e) => fehler.push(e.message));
  await page.goto(BASE + "/");
  await page.addScriptTag({ url: BASE + "/hls.js" });
  await page.addScriptTag({ content: libJs });
  await page.evaluate((neu) => {
    const v = document.getElementById("v");
    const hls = new Hls(neu
      ? hlsLiveConfig()
      : { lowLatencyMode: true, liveSyncDuration: 2, maxBufferLength: 8, maxMaxBufferLength: 12, backBufferLength: 0 });
    if (neu) hls.on(Hls.Events.LEVEL_LOADED, (_e, d) => passeLatenzGrenzeAn(hls.config, d.details));
    window.__seeks = 0;
    window.__standbilder = 0;
    v.addEventListener("seeking", () => { window.__seeks++; });
    v.addEventListener("waiting", () => { window.__standbilder++; });
    hls.loadSource("/live.m3u8");
    hls.attachMedia(v);
    v.play();
    window.__hls = hls;
  }, neu);
  for (let i = 0; i < 60; i++) { // bis das Bild laeuft
    if (await page.evaluate(() => document.getElementById("v").currentTime > 3)) break;
    await sleep(500);
  }
  await sleep(2000);
  const grenze = await page.evaluate(() => window.__hls.config.liveMaxLatencyDuration ?? null);
  const abtasten = async (sekunden) => {
    const werte = [];
    for (let i = 0; i < sekunden; i++) { werte.push(await abstand(page)); await sleep(1000); }
    return werte.filter((w) => w !== null);
  };
  const ruhig = await abtasten(8);          // Normalbetrieb vor der Pause
  const seeksVorher = await page.evaluate(() => window.__seeks);
  const standVorher = await page.evaluate(() => window.__standbilder);
  let danach = ruhig;
  if (schwankung) {
    danach = await abtasten(SCHWANKUNG_S);
  } else if (mitPause) {
    await page.evaluate(() => document.getElementById("v").pause());
    await sleep(PAUSE_S * 1000);
    await page.evaluate(() => document.getElementById("v").play());
    danach = await abtasten(ERHOLUNG_S);
  } else {
    danach = await abtasten(ERHOLUNG_S);
  }
  const seeks = (await page.evaluate(() => window.__seeks)) - seeksVorher;
  const standbilder = (await page.evaluate(() => window.__standbilder)) - standVorher;
  const erschoepft = Date.now() - uhr.start > MATERIAL_MS;
  netz.schwankung = 0;
  await page.close();
  const max = (a) => Math.max(...a), letzte = danach.slice(-5);
  const mittel = letzte.reduce((a, b) => a + b, 0) / letzte.length;
  console.log(`${name} Sprunggrenze ${grenze ?? "keine"} s · Abstand ruhig ${Math.min(...ruhig).toFixed(1)}..${max(ruhig).toFixed(1)} s · ` +
    `${mitPause ? "nach der Pause" : "weiter ruhig"}: Verlauf ${danach.map((w) => w.toFixed(0)).join(" ")} · ` +
    `Ende ${mittel.toFixed(1)} s · Spruenge ${seeks} · Standbilder ${standbilder}` +
    `${erschoepft ? " · MATERIAL ERSCHOEPFT" : ""}${fehler.length ? ` · Seitenfehler: ${fehler[0]}` : ""}`);
  return { ruhigMax: max(ruhig), ende: mittel, seeks, standbilder, grenze, erschoepft };
}

let ok = true;
try {
  console.log(`Pause ${PAUSE_S} s, Segment ${SEG_S} s, Fenster ${FENSTER * SEG_S} s\n`);
  const alt = await messe("ALT      ", false, true);
  const neu = await messe("NEU      ", true, true);
  const still = await messe("NEU ruhig", true, false);
  const altWackel = await messe("ALT Netz ", false, false, SCHWANKUNG_MS);
  const neuWackel = await messe("NEU Netz ", true, false, SCHWANKUNG_MS);

  // Aussagekraeftig nur, wenn jeder Lauf auf wachsender Playlist misst ...
  const materialReicht = [alt, neu, still, altWackel, neuWackel].every((l) => !l.erschoepft);
  // ... und die alte Einstellung das Problem wirklich zeigt.
  const altHaengt = alt.ende > alt.ruhigMax + PAUSE_S * 0.6;
  const neuHolt = neu.ende <= neu.grenze && neu.ende < alt.ende - PAUSE_S * 0.3;
  const neuRuhig = still.seeks === 0;
  const neuStabil = neuWackel.standbilder <= altWackel.standbilder;
  const pruefe = (b, t) => console.log(`${b ? "OK  " : "FEHL"} ${t}`);
  console.log("");
  pruefe(materialReicht, "Testmaterial reicht fuer jeden Lauf (sonst misst ein Lauf nur das Materialende)");
  pruefe(altHaengt, "alt: Verzoegerung bleibt nach der Pause groesser (Problem nachgestellt)");
  pruefe(neuHolt, "neu: Player holt nach der Pause auf (Ende unter der Sprunggrenze und deutlich unter alt)");
  pruefe(neuRuhig, "neu: im ruhigen Betrieb kein Springen");
  pruefe(neuStabil, `neu: bei schwankender Ladezeit (0..${SCHWANKUNG_MS} ms) nicht oefter Standbild als alt ` +
    `(${neuWackel.standbilder} gegen ${altWackel.standbilder})`);
  ok = materialReicht && altHaengt && neuHolt && neuRuhig && neuStabil;
} finally {
  await browser.close();
  server.close();
  rmSync(dir, { recursive: true, force: true });
}
process.exit(ok ? 0 : 1);
