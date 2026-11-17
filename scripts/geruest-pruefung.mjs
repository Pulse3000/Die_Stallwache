#!/usr/bin/env node
/**
 * Geruest-Pruefung: haelt Anweisungen (CLAUDE.md, Skills, Agenten, docs/)
 * und Code deckungsgleich.
 *
 *   node scripts/geruest-pruefung.mjs        (oder: npm run geruest)
 *
 * Warum es das gibt: Anweisungen veralten leise. Eine Sitzung, die sich auf
 * einen Pfad, einen Skill oder einen Schwellenwert verlaesst, den es so nicht
 * mehr gibt, arbeitet sauber am Falschen. Diese Pruefung macht solche Drift
 * rot, statt darauf zu hoffen, dass sie jemandem auffaellt.
 *
 * Keine Abhaengigkeiten (nur Node-Bordmittel), laeuft in unter einer Sekunde.
 * Exit 0 = gruen, Exit 1 = mindestens ein Befund.
 *
 * Bei einem Befund: die DOKU oder den CODE richtigstellen. Die Ausnahmelisten
 * unten nur erweitern, wenn der Verweis wirklich so gemeint ist – jeweils mit
 * Begruendung in derselben Zeile.
 */

import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WURZEL = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const befunde = [];
const hinweise = [];

/** Befund melden. `ort` = Datei oder Datei:Zeile, relativ zur Repo-Wurzel. */
function rot(regel, ort, text) {
  befunde.push({ regel, ort, text });
}

const lies = (pfad) => readFileSync(join(WURZEL, pfad), "utf8");
const gibtEs = (pfad) => existsSync(join(WURZEL, pfad));

function dateienIn(ordner, filter) {
  const voll = join(WURZEL, ordner);
  if (!existsSync(voll)) return [];
  const aus = [];
  for (const eintrag of readdirSync(voll)) {
    const rel = join(ordner, eintrag);
    const st = statSync(join(WURZEL, rel));
    if (st.isDirectory()) aus.push(...dateienIn(rel, filter));
    else if (filter(rel)) aus.push(rel);
  }
  return aus;
}

// ---------------------------------------------------------------------------
// Ausnahmen – jede mit Grund. Kurz halten.
// ---------------------------------------------------------------------------

/** Pfade, die es im Repo absichtlich nicht gibt (Laufzeit, gitignoriert, entfernt). */
const PFAD_AUSNAHMEN = new Map([
  ["edge-agent/config.yaml", "gitignoriert, entsteht aus config.example.yaml"],
  ["edge-agent/aufnahmen", "Laufzeitordner des Agenten, gitignoriert"],
  ["edge-agent/daten", "Laufzeitordner des Agenten, gitignoriert"],
  ["edge-agent/__pycache__", "Python-Cache, darf nie ins Repo"],
  ["bridge/.env", "gitignoriert, entsteht aus bridge/.env.example"],
  ["bridge/termux", "eingestellt 15.10.2026, in der Roadmap als entfernt dokumentiert"],
  ["app/camera/rtsp_reader.py", "Datei des Alt-Projekts kuhwatch, in der Roadmap zitiert"],
  ["tests/test_haertung.py", "Datei des Alt-Projekts kuhwatch, in der Roadmap zitiert"],
  ["tests/messe_bildalter.py", "Datei des Alt-Projekts kuhwatch, in der Bildfrische-Spezifikation zitiert"],
  // Geplante Dateien einer noch nicht umgesetzten Spezifikation. Beim Umsetzen
  // (Skill spezifikation-umsetzen) den Eintrag hier wieder entfernen.
  ["edge-agent/tests/test_eskalation.py", "geplant: eskalationskette-spezifikation.md §7.1"],
  ["app/api/events/quittierungen/route.ts", "geplant: eskalationskette-spezifikation.md §3.2"],
]);

/** Env-Variablen, die bewusst nicht in .env.example stehen. */
const ENV_AUSNAHMEN = new Map([
  ["NODE_ENV", "setzt Next.js selbst"],
  ["BASE44_PUBLIC_HOST_SUFFIX", "setzt die Base44-Umgebung, dokumentiert in AGENTS.md"],
  ["BASE44_SANDBOX_HOST_DOMAIN", "setzt die Base44-Umgebung, dokumentiert in AGENTS.md"],
]);

/**
 * Referenzwerte der Erkennungslogik (edge-agent/config.example.yaml).
 * Aendern nur mit dokumentierter Betreiber-Entscheidung in docs/roadmap.md –
 * dann hier, in CLAUDE.md und in .claude/agents/ki-wache.md nachziehen.
 */
const REFERENZWERTE = {
  logik: {
    winkel_schwelle_grad: 45,
    fenster_minuten: 30,
    anteil_schwelle: 0.2,
    override_konfidenz: 0.8,
    brunst_min_dauer_s: 4,
    eskalation_minuten: 60,
  },
  telegram: { cooldown_minuten: 15 },
  stream: { totmann_minuten: 5 },
};

const HOECHSTZEILEN_CLAUDE_MD = 220;

// ---------------------------------------------------------------------------
// Hilfen
// ---------------------------------------------------------------------------

/** Liest den YAML-Kopf einer Markdown-Datei als flache Schluessel/Wert-Liste. */
function kopfdaten(text) {
  const m = /^---\n([\s\S]*?)\n---\n/.exec(text);
  if (!m) return null;
  const daten = {};
  for (const zeile of m[1].split("\n")) {
    const z = /^([A-Za-z_-]+):\s*(.*)$/.exec(zeile);
    if (z) daten[z[1]] = z[2].trim();
  }
  return daten;
}

/** Markdown-Zeilen ohne eingezaeunte Codebloecke (dort stehen Befehle, keine Verweise). */
function zeilenOhneCodebloecke(text) {
  const aus = [];
  let imBlock = false;
  text.split("\n").forEach((zeile, i) => {
    if (/^\s*(```|~~~)/.test(zeile)) {
      imBlock = !imBlock;
      return;
    }
    if (!imBlock) aus.push({ nr: i + 1, zeile });
  });
  return aus;
}

const WURZEL_ORDNER = [
  "app", "lib", "components", "docs", "edge-agent", "bridge", "tests",
  "public", "scripts", "cloud-functions", ".claude", ".github",
];
const PFAD_MUSTER = new RegExp(
  `^(?:${WURZEL_ORDNER.map((o) => o.replace(".", "\\.")).join("|")})/[^\\s]*$`,
);

// ---------------------------------------------------------------------------
// 1. Skills und Agenten: Kopfdaten gueltig, kein Modell festgenagelt
// ---------------------------------------------------------------------------

const skillOrdner = existsSync(join(WURZEL, ".claude/skills"))
  ? readdirSync(join(WURZEL, ".claude/skills")).filter((n) =>
      statSync(join(WURZEL, ".claude/skills", n)).isDirectory(),
    )
  : [];
const skills = new Set();

for (const name of skillOrdner) {
  const pfad = `.claude/skills/${name}/SKILL.md`;
  if (!gibtEs(pfad)) {
    rot("skill", `.claude/skills/${name}`, "Ordner ohne SKILL.md");
    continue;
  }
  const kopf = kopfdaten(lies(pfad));
  if (!kopf) {
    rot("skill", pfad, "Kopfdaten (--- name/description ---) fehlen");
    continue;
  }
  if (kopf.name !== name)
    rot("skill", pfad, `name "${kopf.name}" weicht vom Ordnernamen "${name}" ab`);
  if (!kopf.description) rot("skill", pfad, "description fehlt – ohne sie wird der Skill nie gewaehlt");
  else if (kopf.description.length > 1024)
    rot("skill", pfad, `description hat ${kopf.description.length} Zeichen (Grenze 1024)`);
  if ("model" in kopf)
    rot("skill", pfad, "model: im Kopf – das Geruest bleibt modellneutral, Zeile entfernen");
  skills.add(name);
}

const agentenDateien = dateienIn(".claude/agents", (p) => p.endsWith(".md"));
const agenten = new Set();

for (const pfad of agentenDateien) {
  const name = pfad.split("/").pop().replace(/\.md$/, "");
  const kopf = kopfdaten(lies(pfad));
  if (!kopf) {
    rot("agent", pfad, "Kopfdaten (--- name/description/tools ---) fehlen");
    continue;
  }
  if (kopf.name !== name)
    rot("agent", pfad, `name "${kopf.name}" weicht vom Dateinamen "${name}" ab`);
  if (!kopf.description) rot("agent", pfad, "description fehlt");
  if (!kopf.tools) rot("agent", pfad, "tools fehlt – das Mandat des Agenten haengt an der Werkzeugliste");
  if ("model" in kopf)
    rot("agent", pfad, "model: im Kopf – ein festgenageltes Modell bricht, sobald es abgeschaltet wird");
  agenten.add(name);
}

// ---------------------------------------------------------------------------
// 2. Markdown: relative Links, zitierte Pfade, genannte Skills und Agenten
// ---------------------------------------------------------------------------

const markdownDateien = [
  ...["CLAUDE.md", "AGENTS.md", "README.md"].filter(gibtEs),
  ...dateienIn("docs", (p) => p.endsWith(".md")),
  ...dateienIn(".claude", (p) => p.endsWith(".md")),
  ...dateienIn("edge-agent", (p) => p.endsWith(".md") && !p.includes("/wheels/")),
  ...dateienIn("bridge", (p) => p.endsWith(".md")),
  ...dateienIn("cloud-functions", (p) => p.endsWith(".md") && !p.includes("node_modules")),
];

for (const datei of markdownDateien) {
  const text = lies(datei);
  for (const { nr, zeile } of zeilenOhneCodebloecke(text)) {
    const ort = `${datei}:${nr}`;

    // 2a. Relative Links [Text](ziel)
    for (const m of zeile.matchAll(/\]\(([^)\s]+)\)/g)) {
      const ziel = m[1];
      if (/^(https?:|mailto:|tel:|#)/.test(ziel)) continue;
      const ohneAnker = ziel.split("#")[0];
      if (!ohneAnker) continue;
      const aufgeloest = relative(WURZEL, resolve(WURZEL, dirname(datei), ohneAnker));
      if (!gibtEs(aufgeloest)) rot("link", ort, `Link-Ziel fehlt: ${ziel}`);
    }

    // 2b. Zitierte Repo-Pfade in `Code-Spannen`
    for (const m of zeile.matchAll(/`([^`]+)`/g)) {
      let token = m[1].trim();
      if (/[<>*{}$…|,"' ]/.test(token)) continue; // Platzhalter, Muster, Befehle
      token = token.replace(/[.,;:)]+$/, "").replace(/#.*$/, "").replace(/:\d+(-\d+)?$/, "");
      if (!PFAD_MUSTER.test(token)) continue;
      const ohneSchraeg = token.replace(/\/+$/, "");
      if (PFAD_AUSNAHMEN.has(token) || PFAD_AUSNAHMEN.has(ohneSchraeg)) continue;
      if (!gibtEs(ohneSchraeg)) rot("pfad", ort, `zitierter Pfad fehlt: ${token}`);
    }

    // 2c. Genannte Skills und Agenten muessen existieren
    for (const m of zeile.matchAll(/\bSkills?\s+`([a-z0-9][a-z0-9-]*)`/g)) {
      if (!skills.has(m[1])) rot("verweis", ort, `Skill \`${m[1]}\` gibt es nicht`);
    }
    for (const m of zeile.matchAll(/\bAgent(?:en)?\s+`([a-z0-9][a-z0-9-]*)`/g)) {
      if (!agenten.has(m[1])) rot("verweis", ort, `Agent \`${m[1]}\` gibt es nicht`);
    }
  }
}

// ---------------------------------------------------------------------------
// 3. Orchestrierung: jeder Skill und jeder Agent ist im Handbuch auffindbar
// ---------------------------------------------------------------------------

const HANDBUCH = "docs/agenten-orchestrierung.md";
if (!gibtEs(HANDBUCH)) {
  rot("handbuch", HANDBUCH, "Orchestrierungs-Handbuch fehlt");
} else {
  const handbuch = lies(HANDBUCH);
  const baum = /```[^\n]*\n([\s\S]*?)```/.exec(handbuch)?.[1] ?? "";
  for (const s of skills) {
    if (!handbuch.includes(`\`${s}\``))
      rot("handbuch", HANDBUCH, `Skill \`${s}\` fehlt in der Gruppentabelle`);
    if (!new RegExp(`Skill ${s}\\b`).test(baum))
      rot("handbuch", HANDBUCH, `Skill ${s} fehlt im Entscheidungsbaum („Wann was?")`);
  }
  for (const a of agenten) {
    if (!handbuch.includes(`\`${a}\``))
      rot("handbuch", HANDBUCH, `Agent \`${a}\` fehlt in der Rollentabelle`);
  }
}

// ---------------------------------------------------------------------------
// 4. Zaehlerstaende in der Doku stimmen (oder stehen gar nicht erst da)
// ---------------------------------------------------------------------------

for (const datei of ["README.md", "CLAUDE.md", "AGENTS.md", HANDBUCH].filter(gibtEs)) {
  lies(datei).split("\n").forEach((zeile, i) => {
    const s = /(\d+)\s+Skills\b/.exec(zeile);
    if (s && Number(s[1]) !== skills.size)
      rot("zaehler", `${datei}:${i + 1}`, `nennt ${s[1]} Skills, im Repo sind es ${skills.size}`);
    const a = /(\d+)\s+(?:Projekt-)?Agenten\b/.exec(zeile);
    if (a && Number(a[1]) !== agenten.size)
      rot("zaehler", `${datei}:${i + 1}`, `nennt ${a[1]} Agenten, im Repo sind es ${agenten.size}`);
  });
}

// ---------------------------------------------------------------------------
// 5. Jede Spezifikation und Entscheidung haengt an der Roadmap
// ---------------------------------------------------------------------------

const ROADMAP = "docs/roadmap.md";
if (gibtEs(ROADMAP)) {
  const roadmap = lies(ROADMAP);
  for (const datei of dateienIn("docs", (p) => /-(spezifikation|entscheidung)\.md$/.test(p))) {
    const name = datei.split("/").pop();
    if (!roadmap.includes(name))
      rot("roadmap", datei, "in docs/roadmap.md nicht verlinkt – Spezifikation ohne Status");
  }
} else {
  rot("roadmap", ROADMAP, "Roadmap fehlt (Single Source of Truth für den Umsetzungsstand)");
}

// ---------------------------------------------------------------------------
// 6. Env-Variablen: was der Code liest, steht in .env.example
// ---------------------------------------------------------------------------

const quelltext = [
  ...dateienIn("app", (p) => /\.(ts|tsx)$/.test(p)),
  ...dateienIn("lib", (p) => /\.(ts|tsx)$/.test(p)),
  ...dateienIn("components", (p) => /\.(ts|tsx)$/.test(p)),
  ...["middleware.ts", "proxy.ts", "next.config.mjs"].filter(gibtEs),
];
const envBeispiel = gibtEs(".env.example") ? lies(".env.example") : "";
const gemeldet = new Set();
for (const datei of quelltext) {
  lies(datei).split("\n").forEach((zeile, i) => {
    for (const m of zeile.matchAll(/process\.env\.([A-Z][A-Z0-9_]*)/g)) {
      const name = m[1];
      if (ENV_AUSNAHMEN.has(name) || gemeldet.has(name)) continue;
      if (!new RegExp(`\\b${name}\\b`).test(envBeispiel)) {
        gemeldet.add(name);
        rot("env", `${datei}:${i + 1}`, `${name} wird gelesen, fehlt aber in .env.example`);
      }
    }
  });
}

// ---------------------------------------------------------------------------
// 7. Referenzwerte der Erkennungslogik unveraendert
// ---------------------------------------------------------------------------

const AGENT_CONFIG = "edge-agent/config.example.yaml";
if (gibtEs(AGENT_CONFIG)) {
  // Flacher Leser: Abschnitt = Zeile ohne Einrueckung, Wert = "  schluessel: wert".
  const werte = {};
  let abschnitt = null;
  for (const zeile of lies(AGENT_CONFIG).split("\n")) {
    const kopf = /^([a-z_]+):\s*(#.*)?$/.exec(zeile);
    if (kopf) {
      abschnitt = kopf[1];
      werte[abschnitt] = {};
      continue;
    }
    const wert = /^ {2}([a-z_]+):\s*([^#\s]+)/.exec(zeile);
    if (wert && abschnitt) werte[abschnitt][wert[1]] = wert[2];
  }
  for (const [abschn, soll] of Object.entries(REFERENZWERTE)) {
    for (const [schluessel, sollWert] of Object.entries(soll)) {
      const ist = werte[abschn]?.[schluessel];
      if (ist === undefined)
        rot("referenz", AGENT_CONFIG, `${abschn}.${schluessel} fehlt (Referenz: ${sollWert})`);
      else if (Number(ist) !== sollWert)
        rot(
          "referenz",
          AGENT_CONFIG,
          `${abschn}.${schluessel} = ${ist}, Referenz ist ${sollWert}. ` +
            "Schwellenwerte aendern nur mit Betreiber-Entscheidung in docs/roadmap.md.",
        );
    }
  }
} else {
  rot("referenz", AGENT_CONFIG, "Referenz-Konfiguration des Edge-Agenten fehlt");
}

// ---------------------------------------------------------------------------
// 8. CLAUDE.md: vorhanden, knapp, nennt das Pruef-Kommando
// ---------------------------------------------------------------------------

if (!gibtEs("CLAUDE.md")) {
  rot("einstieg", "CLAUDE.md", "fehlt – ohne sie startet jede Sitzung ohne Projektregeln");
} else {
  const text = lies("CLAUDE.md");
  const zeilen = text.split("\n").length;
  if (zeilen > HOECHSTZEILEN_CLAUDE_MD)
    rot(
      "einstieg",
      "CLAUDE.md",
      `${zeilen} Zeilen (Grenze ${HOECHSTZEILEN_CLAUDE_MD}). Sie wird in jeder Sitzung geladen – ` +
        "Einzelheiten gehoeren in docs/ oder einen Skill.",
    );
  if (!text.includes("npm run pruefen"))
    rot("einstieg", "CLAUDE.md", "nennt das Pruef-Kommando `npm run pruefen` nicht");
}

// ---------------------------------------------------------------------------
// 9. Hooks: was in .claude/hooks liegt, ist auch registriert (und umgekehrt)
// ---------------------------------------------------------------------------

const EINSTELLUNGEN = ".claude/settings.json";
if (gibtEs(EINSTELLUNGEN)) {
  let einstellungen = null;
  try {
    einstellungen = JSON.parse(lies(EINSTELLUNGEN));
  } catch (fehler) {
    rot("hooks", EINSTELLUNGEN, `kein gueltiges JSON: ${fehler.message}`);
  }
  if (einstellungen) {
    const registriert = JSON.stringify(einstellungen.hooks ?? {});
    for (const datei of dateienIn(".claude/hooks", () => true)) {
      const name = datei.split("/").pop();
      if (!registriert.includes(name))
        rot("hooks", datei, `nicht in ${EINSTELLUNGEN} registriert – das Skript laeuft nie`);
    }
    for (const m of registriert.matchAll(/\.claude\/hooks\/([A-Za-z0-9._-]+)/g)) {
      if (!gibtEs(`.claude/hooks/${m[1]}`))
        rot("hooks", EINSTELLUNGEN, `registrierter Hook fehlt: .claude/hooks/${m[1]}`);
    }
  }
}

// ---------------------------------------------------------------------------
// Bericht
// ---------------------------------------------------------------------------

const geprueft =
  `${skills.size} Skills, ${agenten.size} Agenten, ${markdownDateien.length} Markdown-Dateien, ` +
  `${quelltext.length} Quelldateien`;

for (const h of hinweise) console.log(`HINWEIS ${h}`);

if (befunde.length === 0) {
  console.log(`Geruest-Pruefung GRUEN (${geprueft}).`);
  process.exit(0);
}

const jeRegel = new Map();
for (const b of befunde) {
  if (!jeRegel.has(b.regel)) jeRegel.set(b.regel, []);
  jeRegel.get(b.regel).push(b);
}
for (const [regel, liste] of jeRegel) {
  console.log(`\n[${regel}] ${liste.length} Befund(e)`);
  for (const b of liste) console.log(`  ${b.ort} — ${b.text}`);
}
console.log(`\nGeruest-Pruefung ROT: ${befunde.length} Befund(e) (${geprueft}).`);
console.log("Doku oder Code richtigstellen; Ausnahmen nur mit Grund im Skript.");
process.exit(1);
