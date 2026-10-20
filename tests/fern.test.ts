/**
 * Tests des Stallwache-Fernzugriffs (`lib/fern.ts`).
 *
 * Sie sichern ab, dass ueber die Durchleitung nur das Stallwache-HLS
 * erreichbar ist – nie die go2rtc-API (die u. a. Befehle auf dem Stall-Rechner
 * ausfuehren koennte) –, dass das Manifest den Browser an diese App bindet und
 * dass ein gescheiterter Abruf seine Ursache nennt, ohne die Stall-Adresse
 * preiszugeben.
 *
 *     npm test        (node --test --experimental-strip-types)
 */

import { strict as assert } from "node:assert";
import { createServer, type Server, type Socket } from "node:net";
import { test } from "node:test";
import { fernAbruf, fernFehlerUrsache, fernZiel, schreibeManifestUm } from "../lib/fern.ts";

const BASIS = "https://stall.example.ts.net:8443";
const q = (s: string) => new URLSearchParams(s);

test("Einstieg erzwingt die Quelle stallwache_sd, auch gegen src=...", () => {
  assert.equal(
    fernZiel(BASIS, "stream.m3u8", q("src=rollei")),
    `${BASIS}/api/stream.m3u8?src=stallwache_sd`,
  );
  assert.equal(
    fernZiel(BASIS, "stream.m3u8", q("")),
    `${BASIS}/api/stream.m3u8?src=stallwache_sd`,
  );
});

test("HLS-Folgeabrufe behalten nur erlaubte Parameter", () => {
  assert.equal(
    fernZiel(BASIS, "hls/segment.ts", q("id=abc123&n=7&src=rollei&x=1")),
    `${BASIS}/api/hls/segment.ts?id=abc123&n=7`,
  );
  assert.equal(
    fernZiel(BASIS, "hls/playlist.m3u8", q("id=abc123")),
    `${BASIS}/api/hls/playlist.m3u8?id=abc123`,
  );
});

test("go2rtc-API und unbekannte Pfade sind gesperrt", () => {
  for (const p of [
    "streams",
    "config",
    "restart",
    "frame.jpeg",
    "exec",
    "ws",
    "webrtc",
    "../api/config",
    "hls/../config",
    "hls/segment.ts/../../config",
    "",
  ]) {
    assert.equal(fernZiel(BASIS, p, q("")), null, `Pfad "${p}"`);
  }
});

test("Parameterwerte mit Sonderzeichen werden abgelehnt", () => {
  for (const wert of ["../x", "a b", "a;b", "a%2fb", "x".repeat(65), ""]) {
    assert.equal(
      fernZiel(BASIS, "hls/playlist.m3u8", new URLSearchParams({ id: wert })),
      null,
      `id="${wert}"`,
    );
  }
});

test("Manifest: relative und absolute Pfade laufen ueber diese App", () => {
  const url = `${BASIS}/api/stream.m3u8?src=stallwache_sd`;
  const roh = [
    "#EXTM3U",
    "#EXT-X-STREAM-INF:BANDWIDTH=900000",
    "hls/playlist.m3u8?id=abc",
    "#EXT-X-MAP:URI=\"hls/init.mp4?id=abc\"",
    "/api/hls/segment.ts?id=abc&n=3",
    "",
  ].join("\n");
  const neu = schreibeManifestUm(roh, url);
  assert.equal(
    neu,
    [
      "#EXTM3U",
      "#EXT-X-STREAM-INF:BANDWIDTH=900000",
      "/api/stallwache/fern/hls/playlist.m3u8?id=abc",
      "#EXT-X-MAP:URI=\"/api/stallwache/fern/hls/init.mp4?id=abc\"",
      "/api/stallwache/fern/hls/segment.ts?id=abc&n=3",
      "",
    ].join("\n"),
  );
  assert.ok(!neu.includes("example.ts.net"), "Stall-Adresse darf nie im Manifest stehen");
});

test("Manifest aus Unterpfad (hls/playlist.m3u8) loest relative Segmente richtig auf", () => {
  const url = `${BASIS}/api/hls/playlist.m3u8?id=abc`;
  const neu = schreibeManifestUm("#EXTINF:1.0,\nsegment.ts?id=abc&n=9\n", url);
  assert.equal(neu, "#EXTINF:1.0,\n/api/stallwache/fern/hls/segment.ts?id=abc&n=9\n");
});

// Fehlerformen wie sie Node 22 (undici) bei fetch() liefert, gemessen am
// 20.10.2026: TypeError „fetch failed" mit der eigentlichen Ursache in cause.
const fetchFehler = (code: string, meldung: string) =>
  new TypeError("fetch failed", { cause: Object.assign(new Error(meldung), { code }) });

test("Fehlerursache: DNS, Abweisung, Reset, TLS und Zeitueberschreitung", () => {
  assert.equal(
    fernFehlerUrsache(fetchFehler("ENOTFOUND", "getaddrinfo ENOTFOUND stall.example.ts.net")),
    "Name nicht auflösbar (ENOTFOUND)",
  );
  assert.equal(
    fernFehlerUrsache(fetchFehler("ECONNREFUSED", "connect ECONNREFUSED 100.64.0.1:8443")),
    "Verbindung abgelehnt (ECONNREFUSED)",
  );
  assert.equal(
    fernFehlerUrsache(fetchFehler("ECONNRESET", "Client network socket disconnected before secure TLS connection was established")),
    "Verbindung abgebrochen (ECONNRESET)",
  );
  assert.equal(fernFehlerUrsache(fetchFehler("UND_ERR_SOCKET", "other side closed")), "Verbindung abgebrochen (UND_ERR_SOCKET)");
  assert.equal(fernFehlerUrsache(fetchFehler("CERT_HAS_EXPIRED", "certificate has expired")), "TLS-Fehler (CERT_HAS_EXPIRED)");
  assert.equal(
    fernFehlerUrsache(fetchFehler("ERR_TLS_CERT_ALTNAME_INVALID", "Hostname/IP does not match")),
    "TLS-Fehler (ERR_TLS_CERT_ALTNAME_INVALID)",
  );
  // AbortSignal.timeout(): DOMException mit numerischem code (23) – zaehlt ueber den Namen.
  assert.equal(
    fernFehlerUrsache(new DOMException("The operation was aborted due to timeout", "TimeoutError")),
    "Zeitüberschreitung",
  );
  // Happy Eyeballs: mehrere Adressen -> AggregateError in cause.
  const sammel = Object.assign(new AggregateError([Object.assign(new Error("x"), { code: "ENETUNREACH" })]), {});
  assert.equal(fernFehlerUrsache(new TypeError("fetch failed", { cause: sammel })), "Netz nicht erreichbar (ENETUNREACH)");
});

test("Fehlerursache gibt nie Meldungstext, Host oder fremde Codes weiter", () => {
  const ursache = fernFehlerUrsache(fetchFehler("ENOTFOUND", "getaddrinfo ENOTFOUND stall.example.ts.net"));
  assert.ok(!ursache.includes("example"), "Hostname darf nicht in der Meldung stehen");
  assert.equal(fernFehlerUrsache(fetchFehler("EIRGENDWAS", "x")), "unbekannt (EIRGENDWAS)");
  assert.equal(fernFehlerUrsache(fetchFehler("<script>", "x")), "Ursache unbekannt");
  assert.equal(fernFehlerUrsache(new Error("ohne Code")), "Ursache unbekannt");
  assert.equal(fernFehlerUrsache("nur ein String"), "Ursache unbekannt");
  assert.equal(fernFehlerUrsache(undefined), "Ursache unbekannt");
});

/** Lokaler Server, damit die Fehlerfaelle ohne Netz reproduzierbar sind. */
async function lokalerServer(beiVerbindung: (s: Socket) => void): Promise<Server> {
  const s = createServer(beiVerbindung);
  await new Promise<void>((fertig) => s.listen(0, "127.0.0.1", fertig));
  return s;
}
const portVon = (s: Server) => (s.address() as { port: number }).port;

async function mitFernzugriff(basis: string, fn: () => Promise<void>): Promise<void> {
  const vorher = [process.env.STALLWACHE_FERN_URL, process.env.STALLWACHE_FERN_TOKEN];
  process.env.STALLWACHE_FERN_URL = basis;
  process.env.STALLWACHE_FERN_TOKEN = "t".repeat(32);
  try {
    await fn();
  } finally {
    [process.env.STALLWACHE_FERN_URL, process.env.STALLWACHE_FERN_TOKEN] = vorher;
    if (vorher[0] === undefined) delete process.env.STALLWACHE_FERN_URL;
    if (vorher[1] === undefined) delete process.env.STALLWACHE_FERN_TOKEN;
  }
}

test("fernAbruf nennt die Ursache: abgelehnte Verbindung", async (t) => {
  t.mock.method(console, "error", () => {});
  const frei = await lokalerServer(() => {});
  const port = portVon(frei);
  await new Promise((fertig) => frei.close(fertig)); // Port jetzt geschlossen
  await mitFernzugriff(`http://127.0.0.1:${port}`, async () => {
    const r = await fernAbruf("stream.m3u8", new URLSearchParams());
    assert.deepEqual(r, {
      ok: false,
      status: 502,
      fehler: "Stall-Rechner nicht erreichbar – Verbindung abgelehnt (ECONNREFUSED)",
    });
  });
});

test("fernAbruf nennt die Ursache: Zeitueberschreitung und Reset", async (t) => {
  const log = t.mock.method(console, "error", () => {});
  const stumm = await lokalerServer(() => {}); // nimmt an, antwortet nie
  const reset = await lokalerServer((so) => so.resetAndDestroy());
  try {
    await mitFernzugriff(`http://127.0.0.1:${portVon(stumm)}`, async () => {
      const r = await fernAbruf("stream.m3u8", new URLSearchParams(), 200);
      assert.equal(r.ok, false);
      assert.equal(!r.ok && r.fehler, "Stall-Rechner nicht erreichbar – Zeitüberschreitung");
    });
    await mitFernzugriff(`http://127.0.0.1:${portVon(reset)}`, async () => {
      const r = await fernAbruf("stream.m3u8", new URLSearchParams());
      assert.equal(!r.ok && r.status, 502);
      assert.match(!r.ok ? r.fehler : "", /^Stall-Rechner nicht erreichbar – Verbindung abgebrochen \((ECONNRESET|UND_ERR_SOCKET)\)$/);
    });
    // Das Server-Log nennt Pfad und Ursache, nie Adresse oder Token.
    const zeilen = log.mock.calls.map((c) => c.arguments.join(" "));
    assert.equal(zeilen.length, 2);
    for (const z of zeilen) {
      assert.ok(z.startsWith("Fernzugriff (stream.m3u8) gescheitert:"), z);
      assert.ok(!z.includes("127.0.0.1") && !z.includes("tttt"), z);
    }
  } finally {
    stumm.close();
    reset.close();
  }
});
