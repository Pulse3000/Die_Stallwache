/**
 * Service Worker der Stallwache-PWA.
 *
 * Vier Aufgaben, alle mit demselben Ziel: Der Landwirt bekommt seinen Alarm
 * auch dann, wenn das Netz im Stall gerade nicht will.
 *
 *   1. App-Shell offline halten  – die Oberflaeche startet ohne Netz.
 *   2. Ereignisse puffern        – der letzte bekannte Stand bleibt lesbar,
 *                                  neue Push-Alarme landen im lokalen Puffer.
 *   3. Push annehmen             – FCM liefert reine Daten-Nachrichten; Titel,
 *                                  Dringlichkeit und Deeplink entstehen hier.
 *   4. Aktionen nachliefern      – Quittierungen und Geraetebefehle, die
 *                                  offline ausgeloest wurden, gehen bei der
 *                                  naechsten Verbindung raus (Background Sync).
 *
 * Bewusst ohne Firebase-SDK im Worker: FCM stellt eine ganz normale
 * Web-Push-Nachricht zu, die wir selbst rendern. Das spart ~100 kB Skript im
 * Hintergrundprozess und haelt den Alarmweg unabhaengig vom SDK-Update.
 */

const VERSION = "stallwache-v1";
const SHELL_CACHE = `${VERSION}-shell`;
const DATEN_CACHE = `${VERSION}-daten`;
const BILD_CACHE = `${VERSION}-bilder`;

/** Was die App zum Kaltstart ohne Netz braucht. */
const SHELL = [
  "/",
  "/alarme",
  "/steuerung",
  "/einstellungen",
  "/offline",
  "/manifest.webmanifest",
  "/logo-mark.svg",
  "/icon-192.png",
  "/icon-512.png",
];

// ---------------------------------------------------------------------------
// Lebenszyklus
// ---------------------------------------------------------------------------

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Einzeln statt addAll: eine fehlende Datei darf die Installation
      // nicht scheitern lassen (sonst bleibt die PWA ganz ohne Worker).
      await Promise.allSettled(SHELL.map((pfad) => cache.add(pfad)));
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const namen = await caches.keys();
      await Promise.all(
        namen
          .filter((n) => !n.startsWith(VERSION))
          .map((n) => caches.delete(n)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (event.data === "skipWaiting") self.skipWaiting();
});

// ---------------------------------------------------------------------------
// Abrufstrategien
// ---------------------------------------------------------------------------

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // Bridge/Tuya nie anfassen

  // Alarmbilder aendern sich nie -> Cache zuerst. Damit funktioniert das
  // Replay eines Alarms auch im Funkloch.
  if (/^\/api\/events\/[^/]+\/bild\//.test(url.pathname)) {
    event.respondWith(cacheZuerst(req, BILD_CACHE));
    return;
  }

  // Ereignisliste: frisch bevorzugt, letzter Stand als Rueckfallebene.
  if (url.pathname === "/api/events") {
    event.respondWith(netzZuerst(req, DATEN_CACHE));
    return;
  }

  // Alles andere unter /api ist Zustand oder Steuerung – nie aus dem Cache.
  if (url.pathname.startsWith("/api/")) return;

  // Statische Build-Artefakte sind unveraenderlich (Hash im Namen).
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(cacheZuerst(req, SHELL_CACHE));
    return;
  }

  if (req.mode === "navigate") {
    event.respondWith(seiteLaden(req));
    return;
  }

  event.respondWith(cacheZuerst(req, SHELL_CACHE));
});

async function cacheZuerst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const treffer = await cache.match(req);
  if (treffer) return treffer;
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch {
    return treffer ?? Response.error();
  }
}

async function netzZuerst(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch {
    const treffer = await cache.match(req);
    if (treffer) {
      // Der Client soll erkennen koennen, dass er alte Daten sieht.
      const kopf = new Headers(treffer.headers);
      kopf.set("x-stallwache-offline", "1");
      return new Response(await treffer.blob(), {
        status: treffer.status,
        headers: kopf,
      });
    }
    return new Response(
      JSON.stringify({
        ereignisse: [],
        letzterKontakt: null,
        quelle: "edge-agent",
        offline: true,
      }),
      { headers: { "content-type": "application/json", "x-stallwache-offline": "1" } },
    );
  }
}

async function seiteLaden(req) {
  try {
    const res = await fetch(req);
    if (res.ok && !res.redirected) {
      const cache = await caches.open(SHELL_CACHE);
      cache.put(req, res.clone());
    }
    return res;
  } catch {
    const cache = await caches.open(SHELL_CACHE);
    return (
      (await cache.match(req)) ??
      (await cache.match("/offline")) ??
      new Response("Offline", { status: 503, headers: { "content-type": "text/plain" } })
    );
  }
}

// ---------------------------------------------------------------------------
// Lokaler Puffer (IndexedDB) – gemeinsam mit lib/offline.ts genutzt
// ---------------------------------------------------------------------------

const DB_NAME = "stallwache";
const DB_VERSION = 1;

function db() {
  return new Promise((auf, ab) => {
    const anfrage = indexedDB.open(DB_NAME, DB_VERSION);
    anfrage.onupgradeneeded = () => {
      const d = anfrage.result;
      if (!d.objectStoreNames.contains("alarme")) {
        d.createObjectStore("alarme", { keyPath: "id" });
      }
      if (!d.objectStoreNames.contains("warteschlange")) {
        d.createObjectStore("warteschlange", { keyPath: "id", autoIncrement: true });
      }
    };
    anfrage.onsuccess = () => auf(anfrage.result);
    anfrage.onerror = () => ab(anfrage.error);
  });
}

function alsPromise(anfrage) {
  return new Promise((auf, ab) => {
    anfrage.onsuccess = () => auf(anfrage.result);
    anfrage.onerror = () => ab(anfrage.error);
  });
}

async function merkeAlarm(alarm) {
  try {
    const d = await db();
    const tx = d.transaction("alarme", "readwrite");
    tx.objectStore("alarme").put(alarm);
    await new Promise((auf) => (tx.oncomplete = auf));
  } catch (e) {
    // Ein voller/gesperrter IndexedDB darf die Benachrichtigung nicht kosten.
    console.warn("Alarm konnte nicht gepuffert werden:", e);
  }
}

// ---------------------------------------------------------------------------
// Push
// ---------------------------------------------------------------------------

self.addEventListener("push", (event) => {
  event.waitUntil(zeigeAlarm(event.data));
});

async function zeigeAlarm(daten) {
  let nutzlast = {};
  try {
    const roh = daten ? daten.json() : {};
    // FCM verpackt Daten-Nachrichten in { data: {...} }; ein direkt
    // geschicktes Web-Push-Paket kommt flach an. Beides zulassen.
    nutzlast = roh.data ?? roh.notification ?? roh ?? {};
  } catch {
    nutzlast = { titel: "Stallwache", text: daten ? daten.text() : "Neuer Alarm" };
  }

  const dringend = nutzlast.dringend === "1" || nutzlast.typ === "austreibung";
  const titel = nutzlast.titel || "Stallwache";
  const text = nutzlast.text || "Neues Ereignis im Stall";
  const id = nutzlast.id || "";

  if (id) {
    await merkeAlarm({
      id,
      typ: nutzlast.typ || "info",
      kuhId: nutzlast.kuhId || null,
      kamera: nutzlast.kamera || "stallwache",
      nachricht: text,
      konfidenz: null,
      zeit: nutzlast.zeit || new Date().toISOString(),
      bilder: Number(nutzlast.bilder || 0),
      quittiert: null,
      /** Aus dem Push gepuffert, noch nicht mit dem Server abgeglichen. */
      ausPush: true,
    });
  }

  await self.registration.showNotification(titel, {
    body: text,
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    // Ein Alarm pro Tier ersetzt den vorherigen, statt das Handy zuzumüllen.
    tag: nutzlast.kuhId ? `kuh-${nutzlast.kuhId}` : `alarm-${id || Date.now()}`,
    renotify: true,
    // Die Geburt darf nicht wegscrollen, während der Landwirt schläft.
    requireInteraction: dringend,
    vibrate: dringend ? [300, 120, 300, 120, 300] : [200, 100, 200],
    timestamp: Date.parse(nutzlast.zeit || "") || Date.now(),
    data: { id, url: id ? `/alarme?id=${encodeURIComponent(id)}` : "/alarme" },
    actions: [
      { action: "oeffnen", title: "Ansehen" },
      { action: "quittieren", title: "Gesehen" },
    ],
  });

  // Offene Tabs sofort aktualisieren, ohne auf das naechste Polling zu warten.
  const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const c of clients) c.postMessage({ typ: "alarm", id });
}

self.addEventListener("notificationclick", (event) => {
  const daten = event.notification.data || {};
  event.notification.close();

  if (event.action === "quittieren" && daten.id) {
    event.waitUntil(
      warteschlangeAnhaengen({
        url: `/api/events/${encodeURIComponent(daten.id)}/quittieren`,
        methode: "POST",
        koerper: null,
      }).then(() => sofortSenden()),
    );
    return;
  }

  const ziel = daten.url || "/alarme";
  event.waitUntil(
    (async () => {
      const clients = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      for (const c of clients) {
        if ("focus" in c) {
          await c.focus();
          c.postMessage({ typ: "navigiere", url: ziel });
          return;
        }
      }
      await self.clients.openWindow(ziel);
    })(),
  );
});

// ---------------------------------------------------------------------------
// Offline-Warteschlange (Quittierungen, Geraetebefehle)
// ---------------------------------------------------------------------------

async function warteschlangeAnhaengen(eintrag) {
  const d = await db();
  const tx = d.transaction("warteschlange", "readwrite");
  tx.objectStore("warteschlange").add({ ...eintrag, zeit: Date.now() });
  return new Promise((auf) => (tx.oncomplete = auf));
}

/**
 * Arbeitet die Warteschlange ab. Ein Eintrag wird nur entfernt, wenn der
 * Server ihn angenommen (2xx) oder endgueltig abgelehnt hat (4xx) – bei
 * Netzfehlern bleibt er stehen und wird beim naechsten Versuch wiederholt.
 */
async function sofortSenden() {
  const d = await db();
  const eintraege = await alsPromise(
    d.transaction("warteschlange", "readonly").objectStore("warteschlange").getAll(),
  );

  for (const e of eintraege) {
    try {
      const res = await fetch(e.url, {
        method: e.methode || "POST",
        headers: e.koerper ? { "content-type": "application/json" } : undefined,
        body: e.koerper ? JSON.stringify(e.koerper) : undefined,
        credentials: "same-origin",
      });
      // 5xx: Server hat, Netz war da – spaeter erneut versuchen.
      if (res.status >= 500) continue;
    } catch {
      continue; // kein Netz
    }
    const tx = d.transaction("warteschlange", "readwrite");
    tx.objectStore("warteschlange").delete(e.id);
    await new Promise((auf) => (tx.oncomplete = auf));
  }

  const clients = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const c of clients) c.postMessage({ typ: "warteschlange-geleert" });
}

self.addEventListener("sync", (event) => {
  if (event.tag === "stallwache-warteschlange") {
    event.waitUntil(sofortSenden());
  }
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.typ === "warteschlange-senden") {
    event.waitUntil(sofortSenden());
  }
});
