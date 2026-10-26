#!/usr/bin/env python3
"""ID-Stabilitaet am echten Clip messen und Tracker-Einstellungen vergleichen.

Skill bytetrack-tuning, Ziel: < 1 ID-Wechsel pro Kuh in 10 Minuten, je
Lichtverhaeltnis (Tag UND IR-Nacht). Das Modell rechnet den Clip nur EINMAL
durch (1 Bild je Sekunde wie im Agenten); die Erkennungen landen in einer
JSON-Datei. Danach laeuft jede tracker-*.yaml auf denselben Erkennungen —
auf dem langsamen Stall-Rechner spart das Stunden.

  # Clip aufnehmen (10 min, 1 FPS wie im Betrieb), Quelle = stream.url
  # aus config.yaml (die Adresse, die der Agent liest):
  ffmpeg -i "rtsp://…" -t 600 -r 1 nacht.mp4
  # Messen und vergleichen (--kuehe: so viele Kuehe stehen wirklich im Bild,
  # ohne die Angabe gibt es kein Gesamturteil):
  python3 tracking_pruefung.py nacht.mp4 --modell best.pt --kuehe 2 \\
      --tracker ../tracker-kuh.yaml bytetrack.yaml
  # Weitere Einstellungen ohne neue Inferenz (Erkennungen aus der JSON):
  python3 tracking_pruefung.py nacht.mp4 --kuehe 2 --tracker variante.yaml

Fuer Szenen, in denen dieselben Kuehe den ganzen Clip ueber im Bild
bleiben (Abkalbebox, Liegebereich); --kuehe ist ihre Zahl. Kommen und
gehen Tiere (Futtertisch), zaehlt jede Besucherin als ID-Wechsel.

Ausgabe: Markdown-Tabelle fuer die Modellkarte. Je Einstellung ✓, ✗ oder
„?“: Aus Zaehlungen allein ist nicht zu unterscheiden, ob eine dauerhafte
Erkennung ohne ID eine Kuh oder eine Fehlerkennung ist. Dann nennt die
Tabelle Zeit und Ort zum Ansehen statt eines Urteils. Exit 0 = alle ✓,
1 = mindestens ein ✗, 3 = sonst mindestens ein „?“, 2 = ohne --kuehe oder
Eingabefehler. Braucht ultralytics und opencv (Analyse-Image, Colab); die
Kennzahlen selbst sind reines Python
(Tests: edge-agent/tests/test_tracking_pruefung.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ZIEL_WECHSEL_PRO_KUH_10MIN = 1.0   # gilt auch fuer Kurz-IDs
MIN_LEBENSDAUER_S = 10       # kuerzere IDs zaehlen nicht als Kuh (Flackern)
GRENZE_OHNE_ID = 0.05        # Anteil sichtbarer Kuh-Sekunden ohne lange ID
MAX_LUECKE_S = 30 * 60       # ein Kalbeverdachts-Fenster
LUECKE_CLIPANTEIL = 0.8      # kuerzere Clips: so viel des Clips am Stueck
DAUER_OHNE_ID_S = 60         # Erkennung ohne ID so lange -> Kuh oder Fehlerkennung?
DAUER_DICHTE = 0.5           # … in mindestens diesem Anteil der Bilder der Strecke
BAENDER = ((0.1, 0.25), (0.25, 0.4), (0.4, 0.5), (0.5, 1.01))
# Wie im Agenten (main.py OBJEKT_KLASSEN): Fruchtblase und Kaelberfuesse
# laufen durch denselben Tracker wie die Kuehe und lassen verlorene Spuren
# altern; gemessen werden nur die Tierklassen.
OBJEKT_KLASSEN = ("amniotic_sac", "calf_legs")


# --------------------------------------------------------------------------
# Reine Logik (ohne ultralytics/cv2 testbar)
# --------------------------------------------------------------------------

def sekundenwahl(fps: float):
    """Entscheider je Bildindex (aufsteigend abgefragt): 1 Bild je Sekunde.

    Braucht die Bildzahl nicht — manche Container melden sie als 0.
    """
    schritt = fps if fps and fps > 1.0 else 1.0
    naechstes = 0.0

    def nimm(i: int) -> bool:
        nonlocal naechstes
        if i >= naechstes - 1e-9:
            naechstes += schritt
            return True
        return False

    return nimm


def sekundenbilder(fps: float, anzahl: int) -> list[int]:
    """Indizes der Videobilder, die 1 Bild je Sekunde ergeben (wie der Agent)."""
    nimm = sekundenwahl(fps)
    return [i for i in range(max(anzahl, 0)) if nimm(i)]


def ist_tier(zeile: list, tier_ids: set[int]) -> bool:
    """Erkennung [cx, cy, w, h, conf, cls]; ohne cls (alte Ablage) = Tier."""
    return len(zeile) < 6 or int(zeile[5]) in tier_ids


def _strecken(flags: list[bool], bruecke: int) -> list[tuple[int, int]]:
    """(Start, Ende) der Bildfolgen mit Flag; Pausen bis `bruecke` Bilder ueberbrueckt."""
    out: list[tuple[int, int]] = []
    for i, f in enumerate(flags):
        if not f:
            continue
        if out and i - out[-1][1] - 1 <= bruecke:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def _laengste_folge(flags: list[bool]) -> int:
    laengste = lauf = 0
    for f in flags:
        lauf = lauf + 1 if f else 0
        laengste = max(laengste, lauf)
    return laengste


def kennzahlen(bilder: list[list[tuple]], kuehe_echt: int | None = None) -> dict:
    """Kennzahlen aus (Konfidenz, Track-ID oder None[, Box cx/cy/w/h]) je
    Tier-Erkennung und Bild.

    `kuehe_echt` = so viele Kuehe stehen den ganzen Clip ueber im Bild; ohne
    die Angabe gibt es kein Urteil (`urteil` „–“), die Kuhzahl ist dann die
    hoechste Zahl gleichzeitiger langer IDs (ein Geist zaehlt mit).

    Rein aus IDs (eindeutig, ✗ hat Vorrang):
    - ID-Wechsel: IDs mit >= MIN_LEBENSDAUER_S Bildern minus Kuehe, je Kuh
      und 10 min.
    - Kurz-IDs: IDs darunter (ab conf 0.25), je Kuh und 10 min. Schnelles
      Wechseln und kurze Geister landen hier.
    - Geist: mindestens MIN_LEBENSDAUER_S Bilder am Stueck mehr lange IDs als
      Kuehe (ein kurzer Doppelrahmen beim Aufstehen zaehlt nicht).
    Mit Erkennungen ohne ID (nur in eindeutiger Szene ein Urteil):
    - Ohne ID: je Bild sichtbare Kuehe (Tier-Erkennungen, hoechstens die
      Kuhzahl) minus lange IDs. Laengste Luecke = laengste Strecke mit einer
      sichtbaren Kuh ohne lange ID. Bilder, in denen eine Kuh gar nicht
      erkannt wird, werden bis MIN_LEBENSDAUER_S ueberbrueckt; ein Bild mit
      allen Kuehen samt langer ID beendet die Strecke. Grenze: MAX_LUECKE_S,
      in kuerzeren Clips LUECKE_CLIPANTEIL der Clipdauer.
    - Mehrdeutig („?“): Eine Erkennung ohne ID haelt sich DAUER_OHNE_ID_S
      oder laenger (dicht), oder nie sind so viele Kuehe gleichzeitig erkannt
      wie angegeben. Ob dort eine Kuh ohne ID steht oder eine Fehlerkennung
      und ob eine lange ID ein Geist ist, zeigt nur das Bild.
    """
    if kuehe_echt is not None and kuehe_echt < 0:
        raise ValueError("kuehe_echt muss >= 0 sein")
    leben: dict[int, int] = {}
    je_bild: list[tuple[set[int], int]] = []  # (IDs, Zahl der Tier-Erkennungen)
    pro_band = {b: [0, 0] for b in BAENDER}  # [Erkennungen, davon ohne ID]
    for bild in bilder:
        ids_im_bild = set()
        for d in bild:
            conf, tid = d[0], d[1]
            for unten, oben in BAENDER:
                if unten <= conf < oben:
                    pro_band[(unten, oben)][0] += 1
                    if tid is None:
                        pro_band[(unten, oben)][1] += 1
            if tid is not None:
                ids_im_bild.add(tid)
        for tid in ids_im_bild:
            leben[tid] = leben.get(tid, 0) + 1
        je_bild.append((ids_im_bild, len(bild)))
    lange = {t for t, n in leben.items() if n >= MIN_LEBENSDAUER_S}
    lang_je_bild = [len(ids & lange) for ids, _ in je_bild]
    # Kurzes Flackern zaehlt nicht als weitere Kuh
    geschaetzt = max(max(lang_je_bild, default=0), 1) if leben else 0
    kuehe = geschaetzt if kuehe_echt is None else kuehe_echt
    hoechstens_erkannt = max((n for _, n in je_bild), default=0)
    wechsel = max(0, len(lange) - kuehe)
    zehner = len(bilder) / 600  # Einheiten zu 10 min
    je_kuh_10 = (wechsel / kuehe / zehner) if kuehe and zehner else 0.0
    kurz = {d[1] for bild in bilder for d in bild
            if d[1] is not None and d[0] >= 0.25 and leben[d[1]] < MIN_LEBENSDAUER_S}
    kurz_10 = (len(kurz) / max(kuehe, 1) / zehner) if zehner else 0.0
    geist_s = (_laengste_folge([n > kuehe for n in lang_je_bild])
               if kuehe_echt is not None else 0)

    sichtbar = defizit = 0
    start = letzt = None
    laengste = 0
    for i, ((ids, n), n_lang) in enumerate(zip(je_bild, lang_je_bild)):
        s_bild = min(kuehe, n)
        d = max(0, s_bild - n_lang)
        sichtbar += s_bild
        defizit += d
        if d:
            if letzt is None or i - letzt - 1 > MIN_LEBENSDAUER_S:  # Pause in Bildern
                start = i
            letzt = i
            laengste = max(laengste, letzt - start + 1)
        elif kuehe and s_bild == kuehe:  # alle Kuehe sichtbar, alle mit langer ID
            letzt = None

    # Dauer-Erkennungen ohne ID: Kuh oder Fehlerkennung? Nur das Bild weiss es.
    ohne = [any(d[1] is None for d in bild) for bild in bilder]
    dauer = []
    for a, b in _strecken(ohne, MIN_LEBENSDAUER_S):
        laenge = b - a + 1
        if laenge < DAUER_OHNE_ID_S or sum(ohne[a:b + 1]) < DAUER_DICHTE * laenge:
            continue
        treffer = [d for bild in bilder[a:b + 1] for d in bild if d[1] is None]
        boxen = [d[2] for d in treffer if len(d) > 2]
        dauer.append({
            "start_s": a, "ende_s": b,
            "conf_min": min(d[0] for d in treffer), "conf_max": max(d[0] for d in treffer),
            "box": (tuple(sum(v[k] for v in boxen) / len(boxen) for k in range(4))
                    if boxen else None),
        })

    e = {
        "dauer_min": round(len(bilder) / 60, 1),
        "ids": len(leben),
        "ids_lang": len(lange),
        "kuehe": kuehe,
        "kuehe_geschaetzt": geschaetzt,
        "kuehe_echt": kuehe_echt,
        "hoechstens_erkannt": hoechstens_erkannt,
        "beurteilt": kuehe_echt is not None,
        "wechsel": wechsel,
        "wechsel_je_kuh_10min": round(je_kuh_10, 2),
        "kurz_ids": len(kurz),
        "kurz_je_kuh_10min": round(kurz_10, 2),
        "geist_s": geist_s,
        "kuh_anteil_ohne_id": defizit / sichtbar if sichtbar else 0.0,
        "laengste_luecke_s": laengste,
        "luecke_grenze_s": min(MAX_LUECKE_S, int(LUECKE_CLIPANTEIL * len(bilder))) or 1,
        "dauer_ohne_id": dauer,
        "ohne_id": {f"{u:.2f}–{min(o, 1.0):.2f}": (n, o_) for (u, o), (n, o_) in pro_band.items()},
    }
    # Bei 0 Kuehen ist das Ziel: keine lange ID (sonst ein Geist). Schnelles
    # Wechseln ohne jede lange ID faengt die Kurz-ID-Grenze.
    e["wechsel_ok"] = (not lange) if kuehe == 0 else je_kuh_10 < ZIEL_WECHSEL_PRO_KUH_10MIN
    e["kurz_ok"] = kurz_10 < ZIEL_WECHSEL_PRO_KUH_10MIN
    e["geister"] = geist_s >= MIN_LEBENSDAUER_S
    e["ohne_id_ok"] = e["kuh_anteil_ohne_id"] <= GRENZE_OHNE_ID
    e["luecke_ok"] = laengste < e["luecke_grenze_s"]
    e["nie_alle_erkannt"] = bool(kuehe_echt) and hoechstens_erkannt < kuehe_echt
    # Bei 0 Kuehen kann keine Kuh ohne ID im Bild stehen
    e["mehrdeutig"] = bool(kuehe_echt) and (bool(dauer) or e["nie_alle_erkannt"])
    if not e["beurteilt"]:
        e["urteil"] = "–"
    elif not (e["wechsel_ok"] and e["kurz_ok"]) or e["geister"]:
        e["urteil"] = "✗"
    elif e["mehrdeutig"]:
        e["urteil"] = "?"
    elif not (e["ohne_id_ok"] and e["luecke_ok"]):
        e["urteil"] = "✗"
    else:
        e["urteil"] = "✓"
    e["ziel_erfuellt"] = e["urteil"] == "✓"
    return e


def _minuten(sekunden: int) -> str:
    """Abgerundet, damit 1798 s nicht als „30.0 min“ erscheint."""
    return f"{sekunden // 6 / 10:.1f} min"


def _zeit(sekunden: int) -> str:
    h, rest = divmod(int(sekunden), 3600)
    return f"{h}:{rest // 60:02d}:{rest % 60:02d}" if h else f"{rest // 60:02d}:{rest % 60:02d}"


GESAMT_TEXT = {"✓": "✓", "✗": "✗", "?": "? Bilder ansehen", "–": "– (--kuehe fehlt)"}


def tabelle(ergebnisse: dict[str, dict], fps_geraet: float | None) -> str:
    """Markdown fuer die Modellkarte."""
    z = []
    if fps_geraet is not None:
        z.append(f"Inferenz auf diesem Rechner: {fps_geraet:.2f} Bilder/s "
                 f"({'reicht' if fps_geraet >= 1 else 'UNTER 1 FPS – track_buffer zaehlt dann mehr als Sekunden'}).")
        z.append("")
    namen = list(ergebnisse)
    z.append("| Kennzahl | " + " | ".join(namen) + " |")
    z.append("|---|" + "---|" * len(namen))

    def zeile(titel, f):
        z.append(f"| {titel} | " + " | ".join(f(ergebnisse[n]) for n in namen) + " |")

    def haken(ok: bool) -> str:
        return " ✓" if ok else " ✗"

    zeile("Dauer", lambda e: f"{e['dauer_min']} min")
    zeile("Kühe im Bild", lambda e: f"geschätzt {e['kuehe_geschaetzt']}"
          + (f", angegeben {e['kuehe_echt']}" if e["beurteilt"] else "")
          + f", höchstens {e['hoechstens_erkannt']} gleichzeitig erkannt")
    zeile(f"IDs (≥ {MIN_LEBENSDAUER_S} s)", lambda e: f"{e['ids_lang']} (alle: {e['ids']})")
    zeile("ID-Wechsel je Kuh / 10 min",
          lambda e: (f"{e['wechsel_je_kuh_10min']}" if e["kuehe"]
                     else f"{e['ids_lang']} lange ID(s) bei 0 Kühen") + haken(e["wechsel_ok"]))
    zeile(f"Kurz-IDs (< {MIN_LEBENSDAUER_S} s) je Kuh / 10 min",
          lambda e: f"{e['kurz_je_kuh_10min']}" + haken(e["kurz_ok"]))
    zeile("Geist (mehr lange IDs als Kühe, längste Strecke)",
          lambda e: (f"{e['geist_s']} s" + haken(not e["geister"])) if e["beurteilt"] else "–")
    zeile("Sichtbare Kuh-Sekunden ohne lange ID",
          lambda e: f"{e['kuh_anteil_ohne_id']:.0%}" + haken(e["ohne_id_ok"]))
    zeile("Längste Lücke (Kuh sichtbar, ohne lange ID)",
          lambda e: _minuten(e["laengste_luecke_s"]) + haken(e["luecke_ok"]))
    zeile(f"Dauer-Erkennungen ohne ID (≥ {DAUER_OHNE_ID_S} s)",
          lambda e: str(len(e["dauer_ohne_id"])) + (" ?" if e["dauer_ohne_id"] else ""))
    for band in next(iter(ergebnisse.values()))["ohne_id"]:
        zeile(f"Erkennungen conf {band} ohne ID",
              lambda e, b=band: (f"{e['ohne_id'][b][1]} von {e['ohne_id'][b][0]}"
                                 if e["ohne_id"][b][0] else "–"))
    zeile("**Gesamt**", lambda e: GESAMT_TEXT[e["urteil"]])
    for n in namen:
        e = ergebnisse[n]
        unsicher = " (falls die Erkennungen ohne ID Kühe sind)" if e["mehrdeutig"] else ""
        hinweise = []
        if not e["kurz_ok"]:
            hinweise.append(f"**Achtung {n}:** {e['kurz_ids']} IDs hielten keine "
                            f"{MIN_LEBENSDAUER_S} s – schneller ID-Wechsel oder kurze Geister, "
                            "das 30-Minuten-Fenster beginnt bei jedem Wechsel neu.")
        if e["geister"]:
            hinweise.append(f"**Achtung {n}:** {e['geist_s']} s am Stück mehr lange IDs als "
                            f"{e['kuehe']} Kühe – Dauer-Fehlerkennung mit eigener ID (Geist) "
                            "oder --kuehe zu klein.")
        if not e["ohne_id_ok"]:
            hinweise.append(f"**Achtung {n}:** {e['kuh_anteil_ohne_id']:.0%} der sichtbaren "
                            f"Kuh-Sekunden ohne lange ID{unsicher} – diese Kühe werden nicht "
                            "ausgewertet.")
        if not e["luecke_ok"]:
            wie = ("länger als ein Kalbeverdachts-Fenster" if e["laengste_luecke_s"] >= MAX_LUECKE_S
                   else f"{LUECKE_CLIPANTEIL:.0%} des Clips oder mehr, diese Kuh wurde kaum verfolgt")
            hinweise.append(f"**Achtung {n}:** {_minuten(e['laengste_luecke_s'])} am Stück eine "
                            f"sichtbare Kuh ohne lange ID{unsicher} – {wie}.")
        if e["nie_alle_erkannt"]:
            hinweise.append(f"**Prüfen {n}:** angegeben {e['kuehe_echt']} Kühe, nie mehr als "
                            f"{e['hoechstens_erkannt']} gleichzeitig erkannt – eine Kuh wurde "
                            "nie erkannt (Modell) oder --kuehe stimmt nicht.")
        for d in e["dauer_ohne_id"][:5]:
            wo = (f", Box um ({d['box'][0]:.0f}, {d['box'][1]:.0f}), "
                  f"{d['box'][2]:.0f}×{d['box'][3]:.0f} px" if d["box"] else "")
            hinweise.append(f"**Prüfen {n}:** Erkennung ohne ID {_zeit(d['start_s'])}–"
                            f"{_zeit(d['ende_s'])}, conf {d['conf_min']:.2f}–{d['conf_max']:.2f}{wo}. "
                            "Kuh: blinde Kuh, gilt als ✗. Fehlerkennung: als Hard Negative "
                            "labeln (Skill fehlalarm-triage).")
        if len(e["dauer_ohne_id"]) > 5:
            hinweise.append(f"**Prüfen {n}:** … und {len(e['dauer_ohne_id']) - 5} weitere Stellen.")
        for h in hinweise:
            z.append("")
            z.append(h)
    z.append("")
    z.append(f"Ziel je Einstellung: < {ZIEL_WECHSEL_PRO_KUH_10MIN:g} ID-Wechsel und < "
             f"{ZIEL_WECHSEL_PRO_KUH_10MIN:g} Kurz-ID je Kuh in 10 min, kein Geist, höchstens "
             f"{GRENZE_OHNE_ID:.0%} der sichtbaren Kuh-Sekunden ohne lange ID, keine Lücke ab dem "
             f"Kleineren aus {MAX_LUECKE_S // 60} min und {LUECKE_CLIPANTEIL:.0%} der Clipdauer. "
             "„?“: Dauer-Erkennung ohne ID oder nie alle Kühe erkannt – die genannten Stellen "
             "im Clip ansehen. Abwägung im Skill bytetrack-tuning.")
    if not all(e["beurteilt"] for e in ergebnisse.values()):
        z.append("Ohne --kuehe kein Urteil: Die Kuhzahl ist dann geschätzt, ein Geist "
                 "mit eigener ID zählt als Kuh und eine Kuh, die nie eine ID bekommt, fehlt.")
    return "\n".join(z)


def exit_code(ergebnisse: dict[str, dict]) -> int:
    """0 alle ✓, 1 mindestens ein ✗, 3 sonst mindestens ein „?“, 2 ohne Urteil."""
    urteile = {e["urteil"] for e in ergebnisse.values()}
    if "–" in urteile:
        return 2
    if "✗" in urteile:
        return 1
    return 3 if "?" in urteile else 0


# --------------------------------------------------------------------------
# Inferenz und Tracker (brauchen ultralytics/cv2)
# --------------------------------------------------------------------------

def erkennungen_aus_clip(clip: Path, modell_pfad: str,
                         tier_klassen: list[str]) -> tuple[list, list[int], float]:
    """Je Sekundenbild die Erkennungen [[cx, cy, w, h, conf, cls], …],
    die Klassen-IDs der Tiere und die Bilder/s des Rechners."""
    import cv2
    from ultralytics import YOLO

    modell = YOLO(modell_pfad)
    namen = {v: k for k, v in modell.names.items()}
    fehlen = [k for k in tier_klassen if k not in namen]
    if fehlen:
        abbruch(f"Klasse(n) {fehlen} nicht im Modell: {sorted(namen)}")
    tier_ids = sorted(namen[k] for k in tier_klassen)
    # Wie InferenceEngine.klassen_filter: Tiere + Fruchtblase/Kaelberfuesse
    filter_ids = sorted(set(tier_ids) | {namen[k] for k in OBJEKT_KLASSEN if k in namen})
    cap = cv2.VideoCapture(str(clip))
    nimm = sekundenwahl(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    bilder, rechenzeit, i = [], 0.0, -1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        i += 1
        if not nimm(i):
            continue
        t0 = time.perf_counter()
        # conf 0.1 wie model.track() im Agenten
        erg = modell.predict(frame, conf=0.1, classes=filter_ids, verbose=False)[0]
        rechenzeit += time.perf_counter() - t0
        b = erg.boxes
        bilder.append([[*map(float, b.xywh[j].tolist()), float(b.conf[j]), int(b.cls[j])]
                       for j in range(len(b))])
    cap.release()
    return bilder, tier_ids, (len(bilder) / rechenzeit if rechenzeit else 0.0)


def verfolge(bilder: list, tracker_pfad: str,
             tier_ids: set[int]) -> list[list[tuple[float, int | None]]]:
    """Alle Erkennungen durch den echten BYTETracker (wie im Agenten,
    ohne Trennung nach Klassen); je Tier-Erkennung (conf, ID|None, Box)."""
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tracker_simulation import lade_tracker

    class Boxen:
        def __init__(self, zeilen):
            a = np.array([[*z[:5], z[5] if len(z) > 5 else 0] for z in zeilen],
                         dtype=np.float32).reshape(-1, 6)
            self.xywh, self.conf, self.cls = a[:, :4], a[:, 4], a[:, 5]

        def __len__(self):
            return len(self.conf)

    tracker = lade_tracker(tracker_pfad)
    out = []
    for zeilen in bilder:
        ids: dict[int, int] = {}
        if zeilen:  # wie ultralytics track.py: ohne Erkennung kein update()
            for t in tracker.update(Boxen(zeilen)):
                ids[int(t[-1])] = int(t[4])
        out.append([(z[4], ids.get(j), tuple(z[:4]))
                    for j, z in enumerate(zeilen) if ist_tier(z, tier_ids)])
    return out


def abbruch(meldung: str) -> None:
    """Eingabefehler: Exit 2 (1 = ✗, 3 = „?“)."""
    print(meldung, file=sys.stderr)
    sys.exit(2)


def kuhzahl(text: str) -> int:
    n = int(text)
    if n < 0:
        raise argparse.ArgumentTypeError("muss >= 0 sein")
    return n


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("clip", type=Path)
    a.add_argument("--modell", help="best.pt/.onnx; ohne: Erkennungen aus <clip>.erkennungen.json")
    a.add_argument("--tier-klassen", nargs="+",
                   help="wie modell.tier_klassen in config.yaml (Default: kuh)")
    a.add_argument("--kuehe", type=kuhzahl,
                   help="so viele Kuehe bleiben den ganzen Clip im Bild (ohne: kein Urteil)")
    a.add_argument("--tracker", nargs="+", default=["../tracker-kuh.yaml", "bytetrack.yaml"])
    arg = a.parse_args()

    ablage = arg.clip.with_suffix(".erkennungen.json")
    fps_geraet = None
    if arg.modell:
        tier_klassen = arg.tier_klassen or ["kuh"]
        bilder, tier_ids, fps_geraet = erkennungen_aus_clip(arg.clip, arg.modell, tier_klassen)
        ablage.write_text(json.dumps({"modell": arg.modell, "tier_klassen": tier_klassen,
                                      "tier_ids": tier_ids, "fps_geraet": fps_geraet,
                                      "bilder": bilder}))
        print(f"Erkennungen gespeichert: {ablage}", file=sys.stderr)
    elif ablage.exists():
        daten = json.loads(ablage.read_text())
        bilder, fps_geraet = daten["bilder"], daten.get("fps_geraet")
        tier_ids = daten.get("tier_ids", [])
        gespeichert = daten.get("tier_klassen") or [daten.get("klasse", "kuh")]
        if arg.tier_klassen and sorted(arg.tier_klassen) != sorted(gespeichert):
            abbruch(f"{ablage} enthaelt Tierklassen {gespeichert}, verlangt "
                    f"{arg.tier_klassen} – mit --modell neu erzeugen.")
        print(f"Erkennungen aus {ablage} (Modell {daten.get('modell', '?')}, "
              f"Tierklassen {gespeichert})", file=sys.stderr)
    else:
        abbruch(f"{ablage} fehlt – einmal mit --modell aufrufen.")

    ergebnisse = {Path(t).name: kennzahlen(verfolge(bilder, t, set(tier_ids)), arg.kuehe)
                  for t in arg.tracker}
    print(f"## Tracking-Prüfung {arg.clip.name}\n")
    print(tabelle(ergebnisse, fps_geraet))
    return exit_code(ergebnisse)


if __name__ == "__main__":
    sys.exit(main())
