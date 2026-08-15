/**
 * Push-Benachrichtigungen ueber Firebase Cloud Messaging (FCM HTTP v1).
 *
 * Aufteilung der Verantwortung:
 *   - Der Browser holt sich mit dem Firebase-Web-SDK ein Geraete-Token und
 *     meldet es an POST /api/push/registrieren (siehe components/PushSchalter).
 *   - Diese Datei fuehrt die Token-Registrierung (KV, mit In-Memory-Fallback)
 *     und verschickt Alarme ueber die FCM-HTTP-v1-API. Der Legacy-Serverkey
 *     wird bewusst nicht genutzt (von Google abgekuendigt) — der Versand
 *     laeuft ueber das Service-Account-Token aus lib/gcp.ts.
 *
 * Zustellstrategie: Wir schicken **Daten-Nachrichten** statt fertiger
 * `notification`-Bloecke. Damit entscheidet unser eigener Service Worker
 * (public/sw.js) ueber Text, Vibration, Gruppierung und Deeplink — und die
 * Nachricht landet auch dann im Alarm-Puffer, wenn der Landwirt sie wegwischt.
 *
 * Umgebungsvariablen (serverseitig):
 *   GCP_SERVICE_ACCOUNT_JSON  Service Account mit FCM-Recht (siehe lib/gcp.ts)
 *   FIREBASE_PROJECT_ID       optional; sonst GCP_PROJECT_ID/Schluesseldatei
 *
 * Oeffentliche Firebase-Web-Konfiguration (per /api/push/konfig ausgeliefert;
 * diese Werte sind nach Firebase-Design oeffentlich, aber als Env-Variablen
 * hinterlegt, damit ein Wechsel ohne Rebuild moeglich ist):
 *   FIREBASE_API_KEY, FIREBASE_AUTH_DOMAIN, FIREBASE_MESSAGING_SENDER_ID,
 *   FIREBASE_APP_ID, FIREBASE_VAPID_KEY
 */

import { gcpAccessToken, gcpKonfiguriert, gcpProjekt, SCOPE_FCM } from "@/lib/gcp";
import { ALARM_TYPEN, type EreignisTyp, type StallEreignis } from "@/lib/events";

// ---------------------------------------------------------------------------
// Konfiguration
// ---------------------------------------------------------------------------

const FIREBASE_PROJEKT =
  process.env.FIREBASE_PROJECT_ID?.trim() || "";

export interface FirebaseWebKonfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  messagingSenderId: string;
  appId: string;
  vapidKey: string;
}

function projektId(): string {
  return FIREBASE_PROJEKT || gcpProjekt();
}

/** Oeffentliche Web-Konfiguration fuer das Firebase-SDK im Browser. */
export function firebaseWebKonfig(): FirebaseWebKonfig | null {
  const apiKey = process.env.FIREBASE_API_KEY?.trim() || "";
  const senderId = process.env.FIREBASE_MESSAGING_SENDER_ID?.trim() || "";
  const appId = process.env.FIREBASE_APP_ID?.trim() || "";
  const vapidKey = process.env.FIREBASE_VAPID_KEY?.trim() || "";
  const projekt = projektId();
  if (!apiKey || !senderId || !appId || !vapidKey || !projekt) return null;
  return {
    apiKey,
    authDomain:
      process.env.FIREBASE_AUTH_DOMAIN?.trim() || `${projekt}.firebaseapp.com`,
    projectId: projekt,
    messagingSenderId: senderId,
    appId,
    vapidKey,
  };
}

/** Kann der Server ueberhaupt versenden? (Client-Konfig zaehlt separat.) */
export function pushVersandMoeglich(): boolean {
  return gcpKonfiguriert() && Boolean(projektId());
}

// ---------------------------------------------------------------------------
// Token-Registrierung
// ---------------------------------------------------------------------------

export interface PushAbo {
  token: string;
  /** Welche Alarmtypen will dieses Geraet? Leer = alle Alarme. */
  typen: EreignisTyp[];
  /** Freitext zur Wiedererkennung in den Einstellungen ("Handy Hof"). */
  geraet: string;
  angelegt: string;
}

const KV_URL = process.env.KV_REST_API_URL?.trim() || "";
const KV_TOKEN = process.env.KV_REST_API_TOKEN?.trim() || "";
const kvAktiv = Boolean(KV_URL && KV_TOKEN);
const KV_ABOS = "kiwache:push:abos";

/** In-Memory-Fallback (pro Serverless-Instanz), damit Tests ohne KV laufen. */
const speicher: Map<string, PushAbo> = ((
  globalThis as Record<string, unknown>
).__kiwachePush ??= new Map<string, PushAbo>()) as Map<string, PushAbo>;

async function kvPipeline(
  befehle: (string | number)[][],
): Promise<{ result: unknown }[] | null> {
  if (!kvAktiv) return null;
  try {
    const res = await fetch(`${KV_URL}/pipeline`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${KV_TOKEN}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(befehle),
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`KV antwortet mit HTTP ${res.status}`);
    return (await res.json()) as { result: unknown }[];
  } catch (e) {
    console.error("KV nicht erreichbar – Push-Abos nur im Instanz-Speicher:", e);
    return null;
  }
}

export async function registriereAbo(
  abo: Omit<PushAbo, "angelegt">,
): Promise<PushAbo> {
  const voll: PushAbo = { ...abo, angelegt: new Date().toISOString() };
  speicher.set(voll.token, voll);
  await kvPipeline([["HSET", KV_ABOS, voll.token, JSON.stringify(voll)]]);
  return voll;
}

export async function entferneAbo(token: string): Promise<void> {
  speicher.delete(token);
  await kvPipeline([["HDEL", KV_ABOS, token]]);
}

export async function alleAbos(): Promise<PushAbo[]> {
  const kv = await kvPipeline([["HGETALL", KV_ABOS]]);
  const roh = kv?.[0]?.result;
  if (Array.isArray(roh) && roh.length > 0) {
    // Upstash liefert HGETALL als flaches [feld, wert, feld, wert, ...].
    const abos: PushAbo[] = [];
    for (let i = 1; i < roh.length; i += 2) {
      try {
        abos.push(JSON.parse(String(roh[i])) as PushAbo);
      } catch {
        // defekten Eintrag ueberspringen
      }
    }
    if (abos.length > 0) return abos;
  }
  return [...speicher.values()];
}

// ---------------------------------------------------------------------------
// Versand
// ---------------------------------------------------------------------------

const TITEL: Record<EreignisTyp, string> = {
  austreibung: "Kalbung läuft",
  kalbeverdacht: "Kalbeverdacht",
  brunstverdacht: "Brunstverdacht",
  info: "Stallwache",
};

/** Kurzer, im Stall lesbarer Benachrichtigungstext. */
export function pushTexte(e: StallEreignis): { titel: string; text: string } {
  const wer = e.kuhId ?? "Unbekanntes Tier";
  const konf =
    e.konfidenz !== null ? ` · ${Math.round(e.konfidenz * 100)} %` : "";
  return {
    titel: e.typ === "info" ? TITEL.info : `${TITEL[e.typ]} – ${wer}`,
    text: `${e.nachricht}${konf}`,
  };
}

/** Soll dieses Abo dieses Ereignis bekommen? */
function passt(abo: PushAbo, e: StallEreignis): boolean {
  if (!ALARM_TYPEN.includes(e.typ)) return false; // Systemmeldungen nie pushen
  if (!abo.typen || abo.typen.length === 0) return true;
  return abo.typen.includes(e.typ);
}

/**
 * Ab welchem Alter ein Ereignis nur noch Protokoll ist, kein Weckruf mehr
 * (Minuten). Ueber PUSH_MAX_ALTER_MINUTEN anpassbar.
 */
const MAX_ALTER_MS =
  Math.max(1, Number(process.env.PUSH_MAX_ALTER_MINUTEN) || 30) * 60_000;

/**
 * Ist das Ereignis noch handlungsrelevant?
 *
 * Wichtig fuer die Offline-Nachlieferung: Kommt der Edge-Agent nach sechs
 * Stunden Funkloch zurueck und liefert 40 gepufferte Alarme nach, darf das
 * Handy nicht 40-mal klingeln. Die Alarme stehen dann vollstaendig im
 * Aktivitaetsprotokoll — aber nachts um vier zur Kalbung von 22 Uhr
 * aufzuwecken hilft niemandem und kostet das Vertrauen in jeden weiteren Ton.
 */
function nochAktuell(e: StallEreignis): boolean {
  const t = Date.parse(e.zeit);
  if (Number.isNaN(t)) return true; // ohne belastbare Zeit lieber melden
  return Date.now() - t <= MAX_ALTER_MS;
}

interface VersandErgebnis {
  zugestellt: number;
  entfernt: number;
  fehler: number;
}

/**
 * Verschickt einen Alarm an alle passenden Geraete.
 * Abgelaufene Tokens werden dabei automatisch aus der Registrierung entfernt.
 */
export async function sendeAlarmPush(
  e: StallEreignis,
): Promise<VersandErgebnis> {
  const ergebnis: VersandErgebnis = { zugestellt: 0, entfernt: 0, fehler: 0 };
  if (!pushVersandMoeglich()) return ergebnis;
  if (!nochAktuell(e)) {
    console.info(
      `Push übersprungen – ${e.typ} von ${e.zeit} ist nachgeliefert, nicht aktuell.`,
    );
    return ergebnis;
  }

  const abos = (await alleAbos()).filter((a) => passt(a, e));
  if (abos.length === 0) return ergebnis;

  const { titel, text } = pushTexte(e);
  const token = await gcpAccessToken(SCOPE_FCM);
  const url = `https://fcm.googleapis.com/v1/projects/${projektId()}/messages:send`;

  const versuche = abos.map(async (abo) => {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        message: {
          token: abo.token,
          // Reine Daten-Nachricht: der Service Worker rendert sie selbst.
          data: {
            id: e.id,
            typ: e.typ,
            titel,
            text,
            kuhId: e.kuhId ?? "",
            kamera: e.kamera,
            zeit: e.zeit,
            bilder: String(e.bilder),
            // Austreibung ist der Sofortalarm – der Service Worker macht
            // daraus eine nicht selbst schliessende Meldung.
            dringend: e.typ === "austreibung" ? "1" : "0",
          },
          webpush: {
            headers: {
              // Sofortalarm darf nicht in der Zustellwarteschlange liegen.
              Urgency: e.typ === "austreibung" ? "high" : "normal",
              TTL: "3600",
            },
            fcm_options: { link: `/alarme?id=${encodeURIComponent(e.id)}` },
          },
          android: { priority: "high" },
        },
      }),
      cache: "no-store",
    });

    if (res.ok) {
      ergebnis.zugestellt++;
      return;
    }
    const fehlertext = await res.text();
    // 404 UNREGISTERED / 400 INVALID_ARGUMENT auf das Token = totes Geraet.
    if (res.status === 404 || /UNREGISTERED|INVALID_ARGUMENT/.test(fehlertext)) {
      await entferneAbo(abo.token);
      ergebnis.entfernt++;
      return;
    }
    ergebnis.fehler++;
    console.error(`FCM-Versand fehlgeschlagen (HTTP ${res.status}):`, fehlertext);
  });

  await Promise.allSettled(versuche);
  return ergebnis;
}
