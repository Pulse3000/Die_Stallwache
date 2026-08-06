/**
 * Google-Cloud-Zugang fuer die serverseitigen Routen (Pub/Sub, FCM, Vertex AI).
 *
 * Bewusst ohne `google-auth-library`: ein Service-Account-Token ist ein
 * selbst signiertes RS256-JWT, das gegen ein OAuth2-Access-Token getauscht
 * wird. Das sind ~40 Zeilen `node:crypto` statt eines Pakets mit grossem
 * Abhaengigkeitsbaum — und es haelt die Cold-Start-Zeit auf Vercel klein.
 *
 * Umgebungsvariablen (nur serverseitig, NIE NEXT_PUBLIC_*):
 *   GCP_SERVICE_ACCOUNT_JSON  Schluesseldatei des Service Accounts, entweder
 *                             als JSON-Text oder Base64-kodiert (praktischer
 *                             fuer Vercel, weil einzeilig).
 *   GCP_PROJECT_ID            optional; sonst aus der Schluesseldatei.
 *
 * Rechte, die der Service Account je nach genutztem Baustein braucht:
 *   Pub/Sub-Publish  -> roles/pubsub.publisher
 *   FCM-Versand      -> roles/firebasemessaging.admin (oder cloudmessaging.messages.create)
 *   Vertex AI        -> roles/aiplatform.user
 */

import { createSign } from "node:crypto";

interface ServiceAccount {
  client_email: string;
  private_key: string;
  project_id?: string;
  token_uri?: string;
}

let geparst: ServiceAccount | null | undefined;

/** Liest die Schluesseldatei einmal pro Instanz; null wenn nicht konfiguriert. */
function serviceAccount(): ServiceAccount | null {
  if (geparst !== undefined) return geparst;
  const roh = process.env.GCP_SERVICE_ACCOUNT_JSON?.trim() || "";
  if (!roh) return (geparst = null);
  try {
    // Vercel-freundlich: JSON darf auch Base64-kodiert hinterlegt sein.
    const text = roh.startsWith("{")
      ? roh
      : Buffer.from(roh, "base64").toString("utf8");
    const sa = JSON.parse(text) as ServiceAccount;
    if (!sa.client_email || !sa.private_key) {
      throw new Error("client_email oder private_key fehlt");
    }
    // In Vercel eingefuegte Schluessel enthalten oft literale \n.
    sa.private_key = sa.private_key.replace(/\\n/g, "\n");
    return (geparst = sa);
  } catch (e) {
    console.error("GCP_SERVICE_ACCOUNT_JSON ist ungültig:", e);
    return (geparst = null);
  }
}

/** Ist ein Service Account hinterlegt? */
export function gcpKonfiguriert(): boolean {
  return serviceAccount() !== null;
}

/** Projekt-ID aus Env oder Schluesseldatei. */
export function gcpProjekt(): string {
  return (
    process.env.GCP_PROJECT_ID?.trim() ||
    serviceAccount()?.project_id ||
    ""
  );
}

function base64url(b: Buffer | string): string {
  return (typeof b === "string" ? Buffer.from(b, "utf8") : b)
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

// Access-Tokens gelten 1 h und sind scope-gebunden -> Cache je Scope.
const tokenCache = new Map<string, { token: string; ablauf: number }>();

/**
 * Besorgt ein OAuth2-Access-Token fuer den angegebenen Scope.
 * Wirft, wenn kein Service Account hinterlegt ist — die Aufrufer pruefen
 * vorher mit `gcpKonfiguriert()` und degradieren sauber.
 */
export async function gcpAccessToken(scope: string): Promise<string> {
  const zwischen = tokenCache.get(scope);
  if (zwischen && Date.now() < zwischen.ablauf) return zwischen.token;

  const sa = serviceAccount();
  if (!sa) throw new Error("GCP nicht konfiguriert (GCP_SERVICE_ACCOUNT_JSON fehlt)");

  const tokenUri = sa.token_uri || "https://oauth2.googleapis.com/token";
  const jetzt = Math.floor(Date.now() / 1000);
  const header = base64url(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const payload = base64url(
    JSON.stringify({
      iss: sa.client_email,
      scope,
      aud: tokenUri,
      iat: jetzt,
      exp: jetzt + 3600,
    }),
  );
  const signatur = base64url(
    createSign("RSA-SHA256").update(`${header}.${payload}`).sign(sa.private_key),
  );

  const res = await fetch(tokenUri, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: `${header}.${payload}.${signatur}`,
    }),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(
      `Google-Token-Tausch fehlgeschlagen (HTTP ${res.status}): ${await res.text()}`,
    );
  }
  const json = (await res.json()) as { access_token: string; expires_in: number };
  tokenCache.set(scope, {
    token: json.access_token,
    // 60 s Sicherheitsabstand, damit kein Request mit ablaufendem Token startet.
    ablauf: Date.now() + Math.max(60, json.expires_in - 60) * 1000,
  });
  return json.access_token;
}

export const SCOPE_CLOUD_PLATFORM = "https://www.googleapis.com/auth/cloud-platform";
export const SCOPE_FCM = "https://www.googleapis.com/auth/firebase.messaging";
export const SCOPE_PUBSUB = "https://www.googleapis.com/auth/pubsub";
