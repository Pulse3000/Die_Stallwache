#!/usr/bin/env python3
"""
Formprüfung Radar-Bericht (Skill wettbewerbs-radar) — Stop-Bedingung des Späher-Goals.

Prüft den letzten Abschnitt „Radar #N" einer Markdown-Datei:
  1. Pflichtabschnitte vorhanden,
  2. jeder Eintrag der Beobachtungsliste steht in der Delta-Tabelle
     (Delta mit Quelle+Datum ODER „kein Delta" mit Prüfdatum),
  3. Evidenzfragen F1–F3 beantwortet (Quelle+Datum ODER „keine belastbare Quelle"),
  4. jeder Beschlussvorschlag ist ADOPT | ADAPT | REJECT | LATER,
  5. nächster Radar-Termin genannt.
Inhaltlich prüft das nichts — das bleibt beim Dirigenten.

Aufruf:  python tools/radar_check.py docs/wettbewerbsanalyse.md [--nummer 2]
         python tools/radar_check.py --selbsttest
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Dict, List, Optional, Tuple

BEOBACHTUNGSLISTE = ["Lely Zeta", "Lency", "BETSY", "NiLIMo", "Moocall", "CalveSense", "iVET",
                     "smaXtec", "SenseHub", "Nedap", "CowManager", "CowScout", "Frigate"]
EINSTUFUNGEN = {"ADOPT", "ADAPT", "REJECT", "LATER"}
PFLICHT = ["Deltas", "Evidenz Erkennungslogik", "Beschlussvorschläge",
           "Beobachtungsliste-Pflege", "Nächster Radar fällig"]
EVIDENZ = ["F1", "F2", "F3"]
DATUM = re.compile(r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\b")
KOPF = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _koepfe(zeilen: List[str]) -> List[Tuple[int, int, str]]:
    return [(i, len(m.group(1)), m.group(2)) for i, z in enumerate(zeilen) if (m := KOPF.match(z))]


def radar_abschnitt(text: str, nummer: Optional[int] = None) -> Tuple[Optional[str], int]:
    zeilen = text.splitlines()
    koepfe = _koepfe(zeilen)
    treffer = [(i, lvl, t) for i, lvl, t in koepfe
               if (m := re.match(r"Radar\s+#(\d+)", t)) and (nummer is None or int(m.group(1)) == nummer)]
    if not treffer:
        return None, 0
    start, lvl, _ = treffer[-1]
    ende = next((i for i, l, _ in koepfe if i > start and l <= lvl), len(zeilen))
    return "\n".join(zeilen[start:ende]), lvl


def unterabschnitte(abschnitt: str, lvl: int) -> Dict[str, str]:
    zeilen = abschnitt.splitlines()
    koepfe = [(i, l, t) for i, l, t in _koepfe(zeilen) if l > lvl]
    teile: Dict[str, str] = {}
    for n, (i, l, t) in enumerate(koepfe):
        ende = koepfe[n + 1][0] if n + 1 < len(koepfe) else len(zeilen)
        teile[t] = "\n".join(zeilen[i + 1:ende])
    return teile


def tabelle(text: str) -> List[List[str]]:
    zeilen = [z.strip() for z in text.splitlines() if z.strip().startswith("|")]
    zeilen = [z for z in zeilen if not re.fullmatch(r"\|[\s:\-|]+\|?", z)]
    return [[c.strip() for c in z.strip("|").split("|")] for z in zeilen[1:]]


def _finde(teile: Dict[str, str], name: str) -> Optional[str]:
    for titel, inhalt in teile.items():
        if titel.lower().startswith(name.lower()):
            return inhalt
    return None


def pruefe(text: str, nummer: Optional[int] = None) -> List[str]:
    abschnitt, lvl = radar_abschnitt(text, nummer)
    if abschnitt is None:
        return ["Kein Abschnitt 'Radar #N' gefunden"]
    teile = unterabschnitte(abschnitt, lvl)
    fehler = [f"Pflichtabschnitt fehlt: {p}" for p in PFLICHT if _finde(teile, p) is None]

    deltas = tabelle(_finde(teile, "Deltas") or "")
    anbieter = " ".join(r[0] for r in deltas if r).lower()
    fehler += [f"Beobachtungsliste ohne Zeile: {n}" for n in BEOBACHTUNGSLISTE if n.lower() not in anbieter]
    fehler += [f"Delta ohne Datum: {r[0]}" for r in deltas if r and not DATUM.search(r[-1])]

    evidenz = tabelle(_finde(teile, "Evidenz Erkennungslogik") or "")
    for f in EVIDENZ:
        zeile = next((r for r in evidenz if r and r[0].upper().startswith(f)), None)
        if zeile is None:
            fehler.append(f"Evidenzfrage ohne Zeile: {f}")
        elif not (DATUM.search(" ".join(zeile)) or "keine belastbare quelle" in " ".join(zeile).lower()):
            fehler.append(f"Evidenzfrage ohne Quelle/Datum: {f}")

    vorschlaege = tabelle(_finde(teile, "Beschlussvorschläge") or "")
    if not vorschlaege:
        fehler.append("Keine Beschlussvorschläge")
    for r in vorschlaege:
        stufe = r[1].replace("*", "").strip().upper() if len(r) > 1 else ""
        if stufe not in EINSTUFUNGEN:
            fehler.append(f"Ungültige Einstufung '{stufe}' bei: {r[0]}")

    naechster = (_finde(teile, "Nächster Radar fällig") or "").strip()
    if not naechster:
        fehler.append("Nächster Radar-Termin fehlt")
    return fehler


# --- Selbsttest ----------------------------------------------------------------

_GUT = """# Wettbewerbsanalyse
## Radar #2 — 2026-10-20
### Deltas
| Anbieter | Was ist neu | Dimension | Quelle (Datum) |
|---|---|---|---|
""" + "".join(f"| {n} | kein Delta | – | geprüft 2026-10-20 |\n" for n in BEOBACHTUNGSLISTE) + """
### Evidenz Erkennungslogik
| Frage | Befund | Quelle (Datum) | Folge für |
|---|---|---|---|
| F1 Schwanzheben | … | Studie (2026-10-20) | B16 |
| F2 Datensätze | keine belastbare Quelle gefunden | – | Trainer |
| F3 Erkennungsraten | … | Paper (2026-10-20) | Abnahme-Gate |
### Beschlussvorschläge
| Vorschlag | Einstufung | Begründung | betroffene Beschlüsse (B-Nr.) |
|---|---|---|---|
| Beispiel | **LATER** | … | B5 |
### Beobachtungsliste-Pflege
keine Änderung
### Nächster Radar fällig
Januar 2027
"""


def selbsttest() -> int:
    assert pruefe(_GUT) == [], pruefe(_GUT)
    assert any("Moocall" in f for f in pruefe(_GUT.replace("| Moocall |", "| Mucall |")))
    assert any("ohne Datum" in f for f in pruefe(_GUT.replace("| CowManager | kein Delta | – | geprüft 2026-10-20 |",
                                                                 "| CowManager | neu | Kosten | Website |")))
    assert any("Ungültige Einstufung" in f for f in pruefe(_GUT.replace("**LATER**", "VIELLEICHT")))
    assert any("F2" in f for f in pruefe(_GUT.replace("| F2 Datensätze | keine belastbare Quelle gefunden | – | Trainer |\n", "")))
    assert pruefe("# nichts") == ["Kein Abschnitt 'Radar #N' gefunden"]
    print("Selbsttest ok")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Formprüfung Radar-Bericht")
    p.add_argument("datei", nargs="?")
    p.add_argument("--nummer", type=int)
    p.add_argument("--selbsttest", action="store_true")
    a = p.parse_args(argv)
    if a.selbsttest:
        return selbsttest()
    if not a.datei:
        p.error("datei fehlt")
    with open(a.datei, encoding="utf-8") as f:
        fehler = pruefe(f.read(), a.nummer)
    for z in fehler:
        print(f"FEHL {z}")
    print("ok" if not fehler else f"{len(fehler)} Befund(e)")
    return 0 if not fehler else 1


if __name__ == "__main__":
    sys.exit(main())
