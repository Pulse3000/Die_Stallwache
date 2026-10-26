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

Ausgabe: Markdown-Tabelle fuer die Modellkarte. Exit 0 = alle Einstellungen
erfuellen das Ziel, 1 = mindestens eine verfehlt es, 2 = nicht beurteilbar
(ohne --kuehe) oder Eingabefehler. Braucht ultralytics und opencv
(Analyse-Image, Colab); die Kennzahlen selbst sind reines Python
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


def kennzahlen(bilder: list[list[tuple[float, int | None]]],
               kuehe_echt: int | None = None) -> dict:
    """Kennzahlen aus (Konfidenz, Track-ID oder None) je Tier-Erkennung und Bild.

    `kuehe_echt` = so viele Kuehe stehen wirklich im Bild; ohne die Angabe
    gibt es kein Gesamturteil (`beurteilt` False), die Kuhzahl ist dann die
    hoechste Zahl gleichzeitiger langer IDs (ein Geist zaehlt mit).

    - ID-Wechsel: IDs mit >= MIN_LEBENSDAUER_S Bildern minus Kuehe.
    - Kurz-IDs: IDs darunter (ab conf 0.25), je Kuh und 10 min. Schnelles
      Wechseln (neue ID alle paar Sekunden) und kurze Geister landen hier.
    - Ohne ID: je Bild sichtbare Kuehe (Tier-Erkennungen, hoechstens die
      Kuhzahl) minus lange IDs. Eine ganz verdeckte Kuh zaehlt nicht; eine,
      die nur schwach erkannt wird, schon. Laengste Luecke = laengste Strecke
      mit mindestens einer sichtbaren Kuh ohne lange ID; Unterbrechungen bis
      MIN_LEBENSDAUER_S werden ueberbrueckt. Grenze: MAX_LUECKE_S, in
      kuerzeren Clips LUECKE_CLIPANTEIL der Clipdauer (sonst verschwindet
      eine nie getrackte Kuh in grossen Herden unter der Anteilsgrenze).
    """
    if kuehe_echt is not None and kuehe_echt < 0:
        raise ValueError("kuehe_echt muss >= 0 sein")
    leben: dict[int, int] = {}
    je_bild: list[tuple[set[int], int]] = []  # (IDs, Zahl der Tier-Erkennungen)
    pro_band = {b: [0, 0] for b in BAENDER}  # [Erkennungen, davon ohne ID]
    for bild in bilder:
        ids_im_bild = set()
        for conf, tid in bild:
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
    # Kurzes Flackern zaehlt nicht als weitere Kuh
    gleichzeitig = max((len(ids & lange) for ids, _ in je_bild), default=0)
    geschaetzt = max(gleichzeitig, 1) if leben else 0
    kuehe = geschaetzt if kuehe_echt is None else kuehe_echt
    wechsel = max(0, len(lange) - kuehe)
    zehner = len(bilder) / 600  # Einheiten zu 10 min
    je_kuh_10 = (wechsel / kuehe / zehner) if kuehe and zehner else 0.0
    kurz = {t for bild in bilder for c, t in bild
            if t is not None and c >= 0.25 and leben[t] < MIN_LEBENSDAUER_S}
    kurz_10 = (len(kurz) / max(kuehe, 1) / zehner) if zehner else 0.0

    sichtbar = defizit = 0
    start = letzt = None
    laengste = 0
    for i, (ids, n) in enumerate(je_bild):
        s_bild = min(kuehe, n)
        d = max(0, s_bild - len(ids & lange))
        sichtbar += s_bild
        defizit += d
        if d:
            if letzt is None or i - letzt - 1 > MIN_LEBENSDAUER_S:  # Pause in Bildern
                start = i
            letzt = i
            laengste = max(laengste, letzt - start + 1)

    e = {
        "dauer_min": round(len(bilder) / 60, 1),
        "ids": len(leben),
        "ids_lang": len(lange),
        "kuehe": kuehe,
        "kuehe_geschaetzt": geschaetzt,
        "kuehe_echt": kuehe_echt,
        "beurteilt": kuehe_echt is not None,
        "wechsel": wechsel,
        "wechsel_je_kuh_10min": round(je_kuh_10, 2),
        "kurz_ids": len(kurz),
        "kurz_je_kuh_10min": round(kurz_10, 2),
        "kuh_anteil_ohne_id": defizit / sichtbar if sichtbar else 0.0,
        "laengste_luecke_s": laengste,
        "luecke_grenze_s": min(MAX_LUECKE_S, int(LUECKE_CLIPANTEIL * len(bilder))) or 1,
        "ohne_id": {f"{u:.2f}–{min(o, 1.0):.2f}": (n, ohne) for (u, o), (n, ohne) in pro_band.items()},
    }
    # Bei 0 Kuehen ist das Ziel: keine lange ID (sonst ein Geist)
    e["wechsel_ok"] = (not lange) if kuehe == 0 else (
        bool(lange) and je_kuh_10 < ZIEL_WECHSEL_PRO_KUH_10MIN)
    e["kurz_ok"] = kurz_10 < ZIEL_WECHSEL_PRO_KUH_10MIN
    e["ohne_id_ok"] = e["kuh_anteil_ohne_id"] <= GRENZE_OHNE_ID
    e["luecke_ok"] = laengste < e["luecke_grenze_s"]
    e["geister"] = kuehe_echt is not None and geschaetzt > kuehe_echt
    e["ziel_erfuellt"] = (e["beurteilt"] and e["wechsel_ok"] and e["kurz_ok"]
                          and e["ohne_id_ok"] and e["luecke_ok"] and not e["geister"])
    return e


def ohne_id_anteil(e: dict) -> float:
    """Anteil der Erkennungen ab conf 0.25, die keine ID bekamen (Kuehe
    ODER Fehlerkennungen – nur Hinweis, nicht Teil des Urteils)."""
    n = ohne = 0
    for band, (anz, o) in e["ohne_id"].items():
        if float(band.split("–")[0]) >= 0.25:
            n, ohne = n + anz, ohne + o
    return ohne / n if n else 0.0


def _minuten(sekunden: int) -> str:
    """Abgerundet, damit 1798 s nicht als „30.0 min“ erscheint."""
    return f"{sekunden // 6 / 10:.1f} min"


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
          + (f", angegeben {e['kuehe_echt']}" if e["beurteilt"] else ""))
    zeile(f"IDs (≥ {MIN_LEBENSDAUER_S} s)", lambda e: f"{e['ids_lang']} (alle: {e['ids']})")
    zeile("ID-Wechsel je Kuh / 10 min",
          lambda e: f"{e['wechsel_je_kuh_10min']}" + haken(e["wechsel_ok"]))
    zeile(f"Kurz-IDs (< {MIN_LEBENSDAUER_S} s) je Kuh / 10 min",
          lambda e: f"{e['kurz_je_kuh_10min']}" + haken(e["kurz_ok"]))
    zeile("Sichtbare Kuh-Sekunden ohne lange ID",
          lambda e: f"{e['kuh_anteil_ohne_id']:.0%}" + haken(e["ohne_id_ok"]))
    zeile("Längste Lücke (Kuh sichtbar, ohne lange ID)",
          lambda e: _minuten(e["laengste_luecke_s"]) + haken(e["luecke_ok"]))
    for band in next(iter(ergebnisse.values()))["ohne_id"]:
        zeile(f"Erkennungen conf {band} ohne ID",
              lambda e, b=band: (f"{e['ohne_id'][b][1]} von {e['ohne_id'][b][0]}"
                                 if e["ohne_id"][b][0] else "–"))
    zeile("**Gesamt**", lambda e: ("✓" if e["ziel_erfuellt"] else "✗")
          if e["beurteilt"] else "– (--kuehe fehlt)")
    for n in namen:
        e = ergebnisse[n]
        hinweise = []
        if not e["kurz_ok"]:
            hinweise.append(f"Achtung {n}:** {e['kurz_ids']} IDs hielten keine "
                            f"{MIN_LEBENSDAUER_S} s – schneller ID-Wechsel oder kurze Geister, "
                            "das 30-Minuten-Fenster beginnt bei jedem Wechsel neu.")
        if not e["ohne_id_ok"]:
            hinweise.append(f"Achtung {n}:** {e['kuh_anteil_ohne_id']:.0%} der sichtbaren "
                            "Kuh-Sekunden ohne lange ID – diese Kühe werden nicht ausgewertet.")
        if not e["luecke_ok"]:
            wie = ("länger als ein Kalbeverdachts-Fenster" if e["laengste_luecke_s"] >= MAX_LUECKE_S
                   else f"{LUECKE_CLIPANTEIL:.0%} des Clips oder mehr, diese Kuh wurde kaum verfolgt")
            hinweise.append(f"Achtung {n}:** {_minuten(e['laengste_luecke_s'])} am Stück eine "
                            f"sichtbare Kuh ohne lange ID – {wie}.")
        if e["geister"]:
            hinweise.append(f"Achtung {n}:** {e['kuehe_geschaetzt']} Kühe gleichzeitig mit ID, "
                            f"angegeben {e['kuehe_echt']} – Dauer-Fehlerkennung mit eigener ID (Geist).")
        if ohne_id_anteil(e) > 0.05:
            hinweise.append(f"Hinweis {n}:** {ohne_id_anteil(e):.0%} der Erkennungen ab conf 0.25 "
                            "ohne ID – fehlende Kühe oder Fehlerkennungen, Bilder ansehen.")
        for h in hinweise:
            z.append("")
            z.append("**" + h)
    z.append("")
    z.append(f"Ziel je Einstellung: < {ZIEL_WECHSEL_PRO_KUH_10MIN:g} ID-Wechsel und < "
             f"{ZIEL_WECHSEL_PRO_KUH_10MIN:g} Kurz-ID je Kuh in 10 min, höchstens "
             f"{GRENZE_OHNE_ID:.0%} der sichtbaren Kuh-Sekunden ohne lange ID, keine Lücke ab "
             f"{MAX_LUECKE_S // 60} min (in kürzeren Clips ab {LUECKE_CLIPANTEIL:.0%} der Clipdauer), "
             "keine Geister. Abwägung im Skill bytetrack-tuning.")
    if not all(e["beurteilt"] for e in ergebnisse.values()):
        z.append("Ohne --kuehe kein Gesamturteil: Die Kuhzahl ist dann geschätzt, ein Geist "
                 "mit eigener ID zählt als Kuh und eine Kuh, die nie eine ID bekommt, fehlt.")
    return "\n".join(z)


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
    ohne Trennung nach Klassen); je Tier-Erkennung (conf, ID|None)."""
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
        out.append([(z[4], ids.get(j)) for j, z in enumerate(zeilen) if ist_tier(z, tier_ids)])
    return out


def abbruch(meldung: str) -> None:
    """Eingabefehler: Exit 2 (1 bedeutet „Ziel verfehlt“)."""
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
                   help="so viele Kuehe stehen wirklich im Bild (ohne: kein Gesamturteil)")
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
    if not all(e["beurteilt"] for e in ergebnisse.values()):
        return 2
    return 0 if all(e["ziel_erfuellt"] for e in ergebnisse.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
