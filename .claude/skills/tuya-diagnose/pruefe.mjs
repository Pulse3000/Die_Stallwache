#!/usr/bin/env node
/**
 * Tuya-Zugangsdaten pruefen — welcher Fehler liegt wirklich vor?
 *
 * Gehoert zum Skill `tuya-diagnose`; Lesart der Ergebnisse dort in SKILL.md.
 *
 * Die Stallwache meldet in Produktion "Tuya-API-Fehler 1004: sign invalid".
 * Dieser Code hat zwei plausible Ursachen, die sich von aussen nicht
 * unterscheiden lassen:
 *
 *   1. Access ID und Access Secret passen nicht zusammen (Secret rotiert,
 *      oder die Werte stammen aus zwei verschiedenen Cloud-Projekten).
 *   2. Das Rechenzentrum stimmt nicht. Ein Tuya-Projekt lebt in genau einem
 *      Data Center; dieselben Schluessel sind in jedem anderen ungueltig.
 *      TUYA_API_BASE steht per Default auf openapi.tuyaeu.com (Zentraleuropa).
 *
 * Das Skript probiert dieselbe Signatur, die lib/tuya.ts baut, gegen alle
 * Tuya-Rechenzentren durch und sagt, welches antwortet.
 *
 * Aufruf (Zugangsdaten NUR ueber die Umgebung, nie als Argument — sonst
 * stehen sie in der Shell-History und in der Prozessliste):
 *
 *   TUYA_ACCESS_ID=... TUYA_ACCESS_SECRET=... node .claude/skills/tuya-diagnose/pruefe.mjs
 *
 * Optional die Geraete-ID mitgeben, dann wird zusaetzlich geprueft, ob das
 * Geraet in diesem Projekt sichtbar ist:
 *
 *   TUYA_DEVICE_ID_FUTTERWACHE=... node .claude/skills/tuya-diagnose/pruefe.mjs
 *
 * Das Skript gibt weder ID noch Secret aus.
 */

import { createHash, createHmac } from "node:crypto";

const ID = (process.env.TUYA_ACCESS_ID ?? "").trim();
const SECRET = (process.env.TUYA_ACCESS_SECRET ?? "").trim();
const GERAET = (process.env.TUYA_DEVICE_ID_FUTTERWACHE ?? "").trim();

if (!ID || !SECRET) {
  console.error(
    "TUYA_ACCESS_ID und TUYA_ACCESS_SECRET muessen gesetzt sein.\n" +
      "Beispiel: TUYA_ACCESS_ID=xxx TUYA_ACCESS_SECRET=yyy node .claude/skills/tuya-diagnose/pruefe.mjs",
  );
  process.exit(2);
}

/** Alle oeffentlichen Tuya-Rechenzentren. */
const HOSTS = [
  ["https://openapi.tuyaeu.com", "Zentraleuropa (Default der App)"],
  ["https://openapi-weaz.tuyaeu.com", "Westeuropa"],
  ["https://openapi.tuyacn.com", "China"],
  ["https://openapi.tuyaus.com", "Westamerika"],
  ["https://openapi-ueaz.tuyaus.com", "Ostamerika"],
  ["https://openapi.tuyain.com", "Indien"],
];

const sha256Hex = (s) => createHash("sha256").update(s).digest("hex");
const hmacUpper = (s) =>
  createHmac("sha256", SECRET).update(s).digest("hex").toUpperCase();

/** Signiert und sendet wie lib/tuya.ts. */
async function anfrage(basis, method, pfad, token) {
  const t = Date.now().toString();
  const stringToSign = [method, sha256Hex(""), "", pfad].join("\n");
  const sign = hmacUpper(ID + (token ?? "") + t + stringToSign);
  const res = await fetch(`${basis}${pfad}`, {
    method,
    headers: {
      client_id: ID,
      t,
      sign_method: "HMAC-SHA256",
      sign,
      ...(token ? { access_token: token } : {}),
    },
  });
  return res.json();
}

console.log(
  `Access ID: ${ID.slice(0, 4)}…${ID.slice(-2)} (${ID.length} Zeichen) · ` +
    `Secret: ${SECRET.length} Zeichen\n`,
);
console.log(
  "Fehlercodes lesen:\n" +
    "  2009 clientId is invalid → die Access ID kennt dieses Rechenzentrum nicht\n" +
    "                             (falsches DC oder falsche/vertippte ID).\n" +
    "  1004 sign invalid        → die ID ist hier bekannt, aber die Signatur\n" +
    "                             passt nicht — also das Secret gehoert nicht\n" +
    "                             zu dieser ID.\n",
);

let treffer = null;
for (const [basis, name] of HOSTS) {
  let ergebnis;
  try {
    const j = await anfrage(basis, "GET", "/v1.0/token?grant_type=1");
    ergebnis = j.success
      ? "✅ TOKEN OK"
      : `❌ ${j.code ?? "?"}: ${j.msg ?? "unbekannt"}`;
    if (j.success && !treffer) treffer = { basis, name, token: j.result.access_token };
  } catch (e) {
    ergebnis = `⚠️  nicht erreichbar (${e.message})`;
  }
  console.log(`  ${name.padEnd(32)} ${basis.padEnd(34)} ${ergebnis}`);
}

console.log();

if (!treffer) {
  console.log(
    "Ergebnis: In KEINEM Rechenzentrum gilt dieses Schluesselpaar.\n" +
      "  → Access ID und Secret passen nicht zusammen. Im Tuya-Portal unter\n" +
      "    Cloud → Development → <Projekt> → Overview beide Werte frisch\n" +
      "    kopieren (das Secret wird dort ein-/ausgeblendet) und in Vercel\n" +
      "    unter Settings → Environment Variables neu setzen.\n" +
      "  → Danach ein Redeploy, damit die neuen Werte greifen.",
  );
  process.exit(1);
}

console.log(
  `Ergebnis: Die Schluessel gelten im Rechenzentrum "${treffer.name}".`,
);
if (treffer.basis !== "https://openapi.tuyaeu.com") {
  console.log(
    `  → Die App fragt aber openapi.tuyaeu.com. In Vercel setzen:\n` +
      `      TUYA_API_BASE=${treffer.basis}\n` +
      `    danach Redeploy. Das erklaert den Fehler 1004 vollstaendig.`,
  );
} else {
  console.log(
    "  → Das ist der Default der App. Die Schluessel sind also in Ordnung;\n" +
      "    dann weicht der Wert in Vercel von dem hier getesteten ab\n" +
      "    (Tippfehler, Leerzeichen, oder nur fuer Preview statt Production\n" +
      "    gesetzt). In Vercel pruefen, ob die Variable fuer 'Production'\n" +
      "    angehakt ist, und neu deployen.",
  );
}

if (GERAET) {
  const j = await anfrage(
    treffer.basis,
    "GET",
    `/v1.0/iot-03/devices/${encodeURIComponent(GERAET)}`,
    treffer.token,
  );
  console.log(
    `\nGeraet ${GERAET}: ` +
      (j.success
        ? `✅ gefunden ("${j.result?.name ?? "?"}", online: ${j.result?.online})`
        : `❌ ${j.code ?? "?"}: ${j.msg ?? "unbekannt"}` +
          "\n  → Geraet ist dem Cloud-Projekt nicht zugeordnet. Im Tuya-Portal\n" +
          "    unter Cloud → Projekt → Devices → Link App Account verknuepfen."),
  );
}
