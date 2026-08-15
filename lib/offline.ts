/**
 * Offline-Puffer und Aktions-Warteschlange im Browser.
 *
 * Der Stall ist der Ort mit dem schlechtesten Empfang des Betriebs. Die App
 * muss deshalb zwei Dinge koennen, wenn das Netz weg ist:
 *
 *   - **Lesen**: der zuletzt bekannte Ereignisstand bleibt sichtbar, ergaenzt
 *     um Alarme, die der Service Worker per Push empfangen hat.
 *   - **Handeln**: Quittierungen und Geraetebefehle wandern in eine
 *     Warteschlange und gehen raus, sobald wieder Verbindung besteht.
 *
 * Dieselbe IndexedDB nutzt auch public/sw.js — Schema-Aenderungen also immer
 * an beiden Stellen. Alle Funktionen sind no-ops, wenn IndexedDB fehlt
 * (aelteres iOS im privaten Modus), damit die App nie daran scheitert.
 */

import type { StallEreignis } from "@/lib/ereignis-modell";

const DB_NAME = "stallwache";
const DB_VERSION = 1;

export interface WarteEintrag {
  id?: number;
  url: string;
  methode: "POST" | "DELETE";
  koerper: unknown | null;
  zeit: number;
}

function verfuegbar(): boolean {
  return typeof indexedDB !== "undefined";
}

function oeffne(): Promise<IDBDatabase> {
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

function alsPromise<T>(anfrage: IDBRequest<T>): Promise<T> {
  return new Promise((auf, ab) => {
    anfrage.onsuccess = () => auf(anfrage.result);
    anfrage.onerror = () => ab(anfrage.error);
  });
}

// ---------------------------------------------------------------------------
// Ereignispuffer
// ---------------------------------------------------------------------------

/** Legt den zuletzt geladenen Stand ab (begrenzt, damit der Puffer klein bleibt). */
export async function merkeEreignisse(ereignisse: StallEreignis[]): Promise<void> {
  if (!verfuegbar() || ereignisse.length === 0) return;
  try {
    const d = await oeffne();
    const tx = d.transaction("alarme", "readwrite");
    const store = tx.objectStore("alarme");
    for (const e of ereignisse.slice(0, 100)) store.put(e);
    await new Promise((auf) => (tx.oncomplete = auf));
  } catch {
    // Puffern ist Komfort, kein Muss – Fehler bleiben folgenlos.
  }
}

/** Liest den gepufferten Stand (neueste zuerst) — inkl. per Push empfangener Alarme. */
export async function gepufferteEreignisse(): Promise<StallEreignis[]> {
  if (!verfuegbar()) return [];
  try {
    const d = await oeffne();
    const alle = await alsPromise<StallEreignis[]>(
      d.transaction("alarme", "readonly").objectStore("alarme").getAll(),
    );
    return alle.sort((a, b) => Date.parse(b.zeit) - Date.parse(a.zeit));
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Aktions-Warteschlange
// ---------------------------------------------------------------------------

/**
 * Fuehrt eine Aktion aus – oder merkt sie vor, wenn kein Netz da ist.
 * Gibt zurueck, ob die Aktion sofort beim Server ankam.
 */
export async function aktion(
  url: string,
  koerper: unknown | null = null,
  methode: "POST" | "DELETE" = "POST",
): Promise<boolean> {
  try {
    const res = await fetch(url, {
      method: methode,
      headers: koerper ? { "content-type": "application/json" } : undefined,
      body: koerper ? JSON.stringify(koerper) : undefined,
      credentials: "same-origin",
    });
    // 5xx ist ein Serverproblem – wiederholen lohnt. 4xx nicht.
    if (res.status < 500) return res.ok;
  } catch {
    // kein Netz -> unten einreihen
  }
  await einreihen({ url, methode, koerper, zeit: Date.now() });
  return false;
}

async function einreihen(eintrag: WarteEintrag): Promise<void> {
  if (!verfuegbar()) return;
  try {
    const d = await oeffne();
    const tx = d.transaction("warteschlange", "readwrite");
    tx.objectStore("warteschlange").add(eintrag);
    await new Promise((auf) => (tx.oncomplete = auf));
    await meldeSyncAn();
  } catch {
    // Wenn selbst das Einreihen scheitert, geht die Aktion verloren – der
    // Aufrufer hat bereits `false` bekommen und zeigt das an.
  }
}

/** Anzahl noch nicht zugestellter Aktionen (fuer die Statusanzeige). */
export async function warteschlangeLaenge(): Promise<number> {
  if (!verfuegbar()) return 0;
  try {
    const d = await oeffne();
    return await alsPromise<number>(
      d.transaction("warteschlange", "readonly").objectStore("warteschlange").count(),
    );
  } catch {
    return 0;
  }
}

interface SyncRegistration extends ServiceWorkerRegistration {
  sync?: { register(tag: string): Promise<void> };
}

/**
 * Bittet den Service Worker, die Warteschlange abzuarbeiten.
 * Background Sync wo vorhanden (Chrome/Android), sonst direkte Nachricht —
 * iOS kennt Background Sync nicht, dort laeuft es beim naechsten App-Start.
 */
export async function meldeSyncAn(): Promise<void> {
  if (typeof navigator === "undefined" || !navigator.serviceWorker) return;
  try {
    const reg = (await navigator.serviceWorker.ready) as SyncRegistration;
    if (reg.sync) {
      await reg.sync.register("stallwache-warteschlange");
      return;
    }
    reg.active?.postMessage({ typ: "warteschlange-senden" });
  } catch {
    // Ohne Service Worker bleibt die Aktion bis zum naechsten Versuch liegen.
  }
}
