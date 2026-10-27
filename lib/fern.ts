/**
 * Fernzugriff auf das Stallwache-Livebild (Tapo) ohne Tailscale-App.
 *
 * Die Tapo-Kamera haengt nur im Stall-LAN; go2rtc auf dem Stall-Rechner macht
 * daraus HLS. Eine kleine Absicherung (bridge/fern-proxy.py) ist per
 * `tailscale funnel` oeffentlich erreichbar, laesst NUR das HLS der Stallwache
 * durch und verlangt einen geheimen Schluessel. Diese App holt das HLS
 * serverseitig mit dem Schluessel und reicht es hinter dem App-Login weiter –
 * der Browser sieht weder Schluessel noch Stall-Adresse.
 *
 * Env (serverseitig, nie NEXT_PUBLIC):
 *   STALLWACHE_FERN_URL    https://<geraet>.<tailnet>.ts.net:8443
 *   STALLWACHE_FERN_TOKEN  gemeinsamer Schluessel mit bridge/fern-proxy.py
 * Build-Flag (damit die Kachel den Fernweg versucht):
 *   NEXT_PUBLIC_STALLWACHE_FERN=1
 *
 * Reine Funktionen ohne Framework-Importe, damit `npm test` sie ohne Build
 * pruefen kann.
 */

/** Oeffentlicher Praefix der Durchleitung in dieser App. */
export const FERN_PRAEFIX = "/api/stallwache/fern";

export function fernKonfiguriert(): boolean {
  return !!(
    process.env.STALLWACHE_FERN_URL?.trim() &&
    process.env.STALLWACHE_FERN_TOKEN?.trim()
  );
}

/** Pfad der KI-Kaesten: Kaesten und Kuh-Nummern der letzten Analyse des
 *  Edge-Agenten als JSON (docs/ki-ansicht-spezifikation.md). fern-proxy.py
 *  liest sie aus einer festen Datei, nicht von go2rtc. Bewusst OHNE Endung:
 *  Der Matcher in middleware.ts nimmt Pfade auf .jpg/.png usw. vom Login
 *  aus (statische Bilder); die Route prueft die Sitzung ohnehin selbst. */
export const KI_ANSICHT_PFAD = "ki-kaesten";

/** Erlaubte Pfade (relativ zu /api/) und ihre Query-Parameter – Spiegel von
 *  ERLAUBT und KI_ANSICHT_PFAD in bridge/fern-proxy.py. */
const ERLAUBT: Record<string, readonly string[]> = {
  "stream.m3u8": [],
  "hls/playlist.m3u8": ["id"],
  "hls/segment.ts": ["id", "n"],
  "hls/init.mp4": ["id"],
  "hls/segment.m4s": ["id", "n"],
  [KI_ANSICHT_PFAD]: [],
};

const PARAMETER_WERT = /^[A-Za-z0-9_-]{1,64}$/;

/**
 * Baut aus dem angefragten Pfad die Ziel-URL am Stall – oder null, wenn der
 * Pfad nicht erlaubt ist. Die Quelle (`src`) setzt immer der Server, nie der
 * Browser: Ueber diesen Weg ist ausschliesslich die Stallwache abrufbar, nie
 * die go2rtc-API (die u. a. Befehle auf dem Stall-Rechner ausfuehren kann).
 */
export function fernZiel(
  basis: string,
  pfad: string,
  query: URLSearchParams,
): string | null {
  const erlaubteParameter = ERLAUBT[pfad];
  if (!erlaubteParameter) return null;
  const ziel = new URL(`/api/${pfad}`, basis);
  if (pfad === "stream.m3u8") {
    ziel.searchParams.set("src", "stallwache_sd");
  }
  for (const p of erlaubteParameter) {
    const wert = query.get(p);
    if (wert !== null) {
      if (!PARAMETER_WERT.test(wert)) return null;
      ziel.searchParams.set(p, wert);
    }
  }
  return ziel.toString();
}

/**
 * Schreibt die URIs eines HLS-Manifests so um, dass der Browser nur diese App
 * anspricht (auch wenn go2rtc absolute Pfade statt relativer liefert).
 * `manifestUrl` ist die URL, unter der das Manifest am Stall abgerufen wurde.
 */
export function schreibeManifestUm(text: string, manifestUrl: string): string {
  const umschreiben = (uri: string): string => {
    const abs = new URL(uri, manifestUrl);
    const rest = abs.pathname.startsWith("/api/")
      ? abs.pathname.slice("/api/".length)
      : abs.pathname.replace(/^\//, "");
    return `${FERN_PRAEFIX}/${rest}${abs.search}`;
  };
  return text
    .split("\n")
    .map((zeile) => {
      const z = zeile.trim();
      if (!z) return zeile;
      if (z.startsWith("#")) {
        return zeile.replace(/URI="([^"]+)"/, (_m, uri: string) => `URI="${umschreiben(uri)}"`);
      }
      return umschreiben(z);
    })
    .join("\n");
}

/**
 * Fehlercode -> Art des Scheiterns. Die Reihenfolge ist die Prioritaet, wenn
 * ein Fehler mehrere Codes traegt (Happy Eyeballs: je Adresse ein Versuch,
 * AggregateError): Was am weitesten kam, erklaert am meisten. Ein IPv6-Fehler
 * an der ersten Adresse darf die Ursache an der IPv4-Adresse nicht verdecken.
 */
const FEHLERARTEN: ReadonlyArray<readonly [RegExp, string]> = [
  [/^(CERT_|ERR_TLS_|ERR_SSL_|UNABLE_TO_|DEPTH_ZERO_SELF_SIGNED_CERT$|SELF_SIGNED_CERT_IN_CHAIN$)/, "TLS-Fehler"],
  [/^(ECONNRESET|EPIPE|UND_ERR_SOCKET)$/, "Verbindung abgebrochen"],
  [/^ECONNREFUSED$/, "Verbindung abgelehnt"],
  [/^(ETIMEDOUT|UND_ERR_CONNECT_TIMEOUT|UND_ERR_HEADERS_TIMEOUT|UND_ERR_BODY_TIMEOUT)$/, "Zeitüberschreitung"],
  // Node bildet EAI_NONAME/EAI_NODATA auf ENOTFOUND ab; EAI_FAIL = SERVFAIL.
  [/^(ENOTFOUND|EAI_AGAIN|EAI_FAIL)$/, "Name nicht auflösbar"],
  [/^(EHOSTUNREACH|ENETUNREACH|EHOSTDOWN|ENETDOWN|EAFNOSUPPORT)$/, "Netz nicht erreichbar"],
];

const rang = (code: string): number => {
  const i = FEHLERARTEN.findIndex(([muster]) => muster.test(code));
  return i === -1 ? FEHLERARTEN.length : i;
};

/**
 * Benennt, woran ein Abruf am Stall-Rechner vor jeder HTTP-Antwort gescheitert
 * ist (fetch wirft). Ohne diese Angabe sahen ein fehlender DNS-Eintrag des
 * Funnels, ein Reset und eine Zeitueberschreitung gleich aus
 * (docs/fernzugriff-spezifikation.md §5).
 *
 * Gibt nur feste Texte und Fehlercodes weiter, nie die Fehlermeldung selbst –
 * die enthaelt Hostname bzw. IP des Stall-Rechners.
 */
export function fernFehlerUrsache(fehler: unknown): string {
  const codes: string[] = [];
  let zeitueberschreitung = false;
  const besuche = (e: unknown, tiefe: number): void => {
    if (!e || typeof e !== "object" || tiefe > 3) return;
    const { name, code, cause, errors } = e as {
      name?: unknown;
      code?: unknown;
      cause?: unknown;
      errors?: unknown;
    };
    // AbortSignal.timeout(): DOMException „TimeoutError" (code ist dort eine Zahl).
    if (name === "TimeoutError") zeitueberschreitung = true;
    if (typeof code === "string" && /^[A-Z0-9_]{2,64}$/.test(code)) codes.push(code);
    if (Array.isArray(errors)) for (const x of errors) besuche(x, tiefe + 1);
    besuche(cause, tiefe + 1);
  };
  besuche(fehler, 0);
  if (zeitueberschreitung) return "Zeitüberschreitung";
  if (!codes.length) return "Ursache unbekannt";
  // Stabil sortiert: bei gleichem Rang bleibt der zuerst gefundene Code vorn.
  const code = [...codes].sort((a, b) => rang(a) - rang(b))[0];
  const art = FEHLERARTEN[rang(code)]?.[1] ?? "unbekannt";
  return `${art} (${code})`;
}

/** Ergebnis eines Abrufs am Stall-Rechner. `upstream` ist der Status, mit
 *  dem der Stall-Rechner selbst geantwortet hat (fehlt bei Netzfehlern). */
export type FernAntwort =
  | { ok: true; antwort: Response }
  | { ok: false; status: number; fehler: string; upstream?: number };

/** Holt einen erlaubten Pfad vom Stall-Rechner (mit Token, kurzem Timeout). */
export async function fernAbruf(
  pfad: string,
  query: URLSearchParams,
  timeoutMs = 15_000,
): Promise<FernAntwort> {
  if (!fernKonfiguriert()) {
    return {
      ok: false,
      status: 503,
      fehler: "Fernzugriff nicht konfiguriert – STALLWACHE_FERN_URL und STALLWACHE_FERN_TOKEN setzen.",
    };
  }
  const ziel = fernZiel(process.env.STALLWACHE_FERN_URL!.trim(), pfad, query);
  if (!ziel) return { ok: false, status: 404, fehler: "Nicht erlaubt" };
  try {
    const antwort = await fetch(ziel, {
      headers: { "x-stallwache-token": process.env.STALLWACHE_FERN_TOKEN!.trim() },
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!antwort.ok) {
      return {
        ok: false,
        status: 502,
        fehler: `Stall-Rechner antwortet mit ${antwort.status}`,
        upstream: antwort.status,
      };
    }
    return { ok: true, antwort };
  } catch (e) {
    const ursache = fernFehlerUrsache(e);
    console.error(`Fernzugriff (${pfad}) gescheitert:`, ursache);
    return { ok: false, status: 502, fehler: `Stall-Rechner nicht erreichbar – ${ursache}` };
  }
}
