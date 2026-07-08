import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * CORS-Umgehung fuer den Tuya-Livestream.
 *
 * Tuyas Video-CDN setzt keine Access-Control-Allow-Origin-Header, wodurch
 * hls.js (das im Browser Manifest und Segmente per fetch/XHR laedt) die
 * Antworten nicht lesen kann -> schwarzes Bild ohne sichtbaren Fehler.
 *
 * Loesung: Dieser Proxy holt Manifest/Segmente serverseitig (kein CORS
 * zwischen Servern) und reicht sie unter der eigenen Domain durch. Im
 * HLS-Manifest werden alle referenzierten URIs (Sub-Playlists, Segmente,
 * Verschluesselungs-Keys) auf denselben Proxy umgeschrieben, damit der
 * Browser ausschliesslich mit der eigenen Origin spricht.
 *
 * Sicherheit: Nur Tuya-Stream-Hosts werden akzeptiert, damit dies nicht als
 * offener Allzweck-Proxy missbraucht werden kann.
 */

/** Endungen bekannter Tuya-Stream-CDN-Hosts (bei Bedarf um weitere Regionen ergaenzen). */
const ERLAUBTE_HOST_ENDUNGEN = [
  ".iot-11.com",
  ".tuyaeu.com",
  ".tuyaus.com",
  ".tuyacn.com",
  ".tuyain.com",
];

function istErlaubterHost(hostname: string): boolean {
  return ERLAUBTE_HOST_ENDUNGEN.some((endung) => hostname.endsWith(endung));
}

function istPlaylist(contentType: string | null, url: string): boolean {
  return (
    !!contentType?.includes("mpegurl") ||
    !!contentType?.includes("x-mpegURL") ||
    url.endsWith(".m3u8")
  );
}

function proxyUrl(zielUrl: string): string {
  return `/api/futterwache/proxy?url=${encodeURIComponent(zielUrl)}`;
}

/** Schreibt alle URI-Referenzen im HLS-Manifest auf den Proxy um. */
function schreibeManifestUm(text: string, basisUrl: string): string {
  return text
    .split("\n")
    .map((zeile) => {
      const z = zeile.trim();
      if (!z) return zeile;

      // Attribut-URIs in #EXT-X-KEY / #EXT-X-MAP, z.B. URI="https://..."
      if (z.startsWith("#")) {
        return zeile.replace(/URI="([^"]+)"/, (_m, uri: string) => {
          const absolut = new URL(uri, basisUrl).toString();
          return `URI="${proxyUrl(absolut)}"`;
        });
      }

      // Segment- oder Sub-Playlist-Zeile (keine Kommentarzeile).
      const absolut = new URL(z, basisUrl).toString();
      return proxyUrl(absolut);
    })
    .join("\n");
}

export async function GET(req: NextRequest) {
  const ziel = req.nextUrl.searchParams.get("url");
  if (!ziel) {
    return NextResponse.json({ fehler: "url fehlt" }, { status: 400 });
  }

  let zielUrl: URL;
  try {
    zielUrl = new URL(ziel);
  } catch {
    return NextResponse.json({ fehler: "Ungültige url" }, { status: 400 });
  }
  if (zielUrl.protocol !== "https:" || !istErlaubterHost(zielUrl.hostname)) {
    return NextResponse.json({ fehler: "Host nicht erlaubt" }, { status: 403 });
  }

  let antwort: Response;
  try {
    antwort = await fetch(zielUrl.toString(), { cache: "no-store" });
  } catch {
    return NextResponse.json({ fehler: "Stream nicht erreichbar" }, { status: 502 });
  }
  if (!antwort.ok) {
    return NextResponse.json(
      { fehler: `Stream-HTTP-Fehler ${antwort.status}` },
      { status: 502 },
    );
  }

  const contentType = antwort.headers.get("content-type");

  if (istPlaylist(contentType, zielUrl.pathname)) {
    const text = await antwort.text();
    const umgeschrieben = schreibeManifestUm(text, zielUrl.toString());
    return new NextResponse(umgeschrieben, {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.apple.mpegurl",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
      },
    });
  }

  // Binaeres Segment (TS/fMP4/Key) unveraendert durchreichen.
  return new NextResponse(antwort.body, {
    status: 200,
    headers: {
      "Content-Type": contentType || "application/octet-stream",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store",
    },
  });
}
