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
  # Messen und vergleichen (--kuehe: so viele Kuehe stehen wirklich im Bild):
  python3 tracking_pruefung.py nacht.mp4 --modell best.pt --kuehe 2 \\
      --tracker ../tracker-kuh.yaml bytetrack.yaml
  # Weitere Einstellungen ohne neue Inferenz (Erkennungen aus der JSON):
  python3 tracking_pruefung.py nacht.mp4 --kuehe 2 --tracker variante.yaml

Ausgabe: Markdown-Tabelle fuer die Modellkarte; Exit 1, wenn eine Einstellung
das Ziel verfehlt. Braucht ultralytics und opencv (Analyse-Image, Colab); die
Kennzahlen selbst sind reines Python (Tests: edge-agent/tests/test_tracking_pruefung.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ZIEL_WECHSEL_PRO_KUH_10MIN = 1.0
MIN_LEBENSDAUER_S = 10       # kuerzere IDs zaehlen nicht als Kuh (Flackern)
GRENZE_ANTEIL = 0.05         # Erkennungen ab conf 0.25 ohne bzw. mit Kurz-ID
MAX_LUECKE_S = 30 * 60       # ein Kalbeverdachts-Fenster
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

    Kuehe = `kuehe_echt` oder, ohne Angabe, die hoechste Zahl gleichzeitiger
    langer IDs (Schaetzung; ein Geist mit eigener ID zaehlt dann mit).
    ID-Wechsel = IDs mit >= MIN_LEBENSDAUER_S Bildern minus Kuehe. Schnelles
    Wechseln (neue ID alle paar Sekunden) taucht dort nicht auf und wird als
    Anteil der Erkennungen mit Kurz-ID ausgewiesen.
    """
    leben: dict[int, int] = {}
    je_bild: list[set[int]] = []
    pro_band = {b: [0, 0] for b in BAENDER}  # [Erkennungen, davon ohne ID]
    luecke = laengste = 0
    for bild in bilder:
        ids_im_bild = set()
        ohne_im_bild = False
        for conf, tid in bild:
            for unten, oben in BAENDER:
                if unten <= conf < oben:
                    pro_band[(unten, oben)][0] += 1
                    if tid is None:
                        pro_band[(unten, oben)][1] += 1
            if tid is not None:
                ids_im_bild.add(tid)
            elif conf >= 0.25:
                ohne_im_bild = True
        for tid in ids_im_bild:
            leben[tid] = leben.get(tid, 0) + 1
        je_bild.append(ids_im_bild)
        luecke = luecke + 1 if ohne_im_bild else 0
        laengste = max(laengste, luecke)
    lange = sorted(t for t, n in leben.items() if n >= MIN_LEBENSDAUER_S)
    # Kurzes Flackern zaehlt nicht als weitere Kuh
    gleichzeitig = max((len(ids & set(lange)) for ids in je_bild), default=0)
    geschaetzt = max(gleichzeitig, 1) if leben else 0
    kuehe = kuehe_echt if kuehe_echt else geschaetzt
    wechsel = max(0, len(lange) - kuehe)
    minuten = len(bilder) / 60
    je_kuh_10 = (wechsel / kuehe / (minuten / 10)) if kuehe and minuten else 0.0
    ab_025 = [(c, t) for bild in bilder for c, t in bild if c >= 0.25]
    kurz = sum(1 for _, t in ab_025 if t is not None and leben[t] < MIN_LEBENSDAUER_S)
    e = {
        "dauer_min": round(minuten, 1),
        "ids": len(leben),
        "ids_lang": len(lange),
        "kuehe": kuehe,
        "kuehe_geschaetzt": geschaetzt,
        "kuehe_echt": kuehe_echt,
        "wechsel": wechsel,
        "wechsel_je_kuh_10min": round(je_kuh_10, 2),
        "wechsel_ok": bool(kuehe) and bool(lange) and je_kuh_10 < ZIEL_WECHSEL_PRO_KUH_10MIN,
        "kurz_anteil": kurz / len(ab_025) if ab_025 else 0.0,
        "laengste_luecke_min": round(laengste / 60, 1),
        "geister": bool(kuehe_echt) and geschaetzt > kuehe_echt,
        "ohne_id": {f"{u:.2f}–{min(o, 1.0):.2f}": (n, ohne) for (u, o), (n, ohne) in pro_band.items()},
    }
    e["ziel_erfuellt"] = (e["wechsel_ok"]
                          and ohne_id_anteil(e) <= GRENZE_ANTEIL
                          and e["kurz_anteil"] <= GRENZE_ANTEIL
                          and laengste < MAX_LUECKE_S
                          and not e["geister"])
    return e


def ohne_id_anteil(e: dict) -> float:
    """Anteil der Erkennungen ab conf 0.25, die keine ID bekamen."""
    n = ohne = 0
    for band, (anz, o) in e["ohne_id"].items():
        if float(band.split("–")[0]) >= 0.25:
            n, ohne = n + anz, ohne + o
    return ohne / n if n else 0.0


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

    zeile("Dauer", lambda e: f"{e['dauer_min']} min")
    zeile("Kühe im Bild (geschätzt)", lambda e: str(e["kuehe_geschaetzt"])
          + (f" (echt: {e['kuehe_echt']})" if e["kuehe_echt"] else ""))
    zeile(f"IDs (≥ {MIN_LEBENSDAUER_S} s)", lambda e: f"{e['ids_lang']} (alle: {e['ids']})")
    zeile("ID-Wechsel je Kuh / 10 min", lambda e: f"{e['wechsel_je_kuh_10min']}"
          + (" ✓" if e["wechsel_ok"] else " ✗"))
    zeile(f"Erkennungen ab conf 0.25 mit ID < {MIN_LEBENSDAUER_S} s",
          lambda e: f"{e['kurz_anteil']:.0%}")
    zeile("Längste Lücke ohne ID (ab conf 0.25)", lambda e: f"{e['laengste_luecke_min']} min")
    for band in next(iter(ergebnisse.values()))["ohne_id"]:
        zeile(f"Erkennungen conf {band} ohne ID",
              lambda e, b=band: (f"{e['ohne_id'][b][1]} von {e['ohne_id'][b][0]}"
                                 if e["ohne_id"][b][0] else "–"))
    zeile("**Gesamt**", lambda e: "✓" if e["ziel_erfuellt"] else "✗")
    for n in namen:
        e = ergebnisse[n]
        hinweise = []
        if ohne_id_anteil(e) > GRENZE_ANTEIL:
            hinweise.append(f"{ohne_id_anteil(e):.0%} der Erkennungen ab conf 0.25 ohne ID – "
                            "diese Kühe fehlen in der Auswertung, die ID-Wechsel-Zahl allein trügt.")
        if e["kurz_anteil"] > GRENZE_ANTEIL:
            hinweise.append(f"{e['kurz_anteil']:.0%} der Erkennungen ab conf 0.25 tragen eine ID, "
                            f"die keine {MIN_LEBENSDAUER_S} s hält – schneller ID-Wechsel, das "
                            "30-Minuten-Fenster beginnt ständig neu.")
        if e["laengste_luecke_min"] * 60 >= MAX_LUECKE_S:
            hinweise.append(f"{e['laengste_luecke_min']} min am Stück eine Erkennung ohne ID – "
                            "länger als ein Kalbeverdachts-Fenster.")
        if e["geister"]:
            hinweise.append(f"{e['kuehe_geschaetzt']} Kühe gleichzeitig mit ID, im Bild stehen "
                            f"{e['kuehe_echt']} – Dauer-Fehlerkennung mit eigener ID (Geist).")
        for h in hinweise:
            z.append("")
            z.append(f"**Achtung {n}:** {h}")
    z.append("")
    z.append(f"Ziel: < {ZIEL_WECHSEL_PRO_KUH_10MIN:g} ID-Wechsel je Kuh in 10 min, höchstens "
             f"{GRENZE_ANTEIL:.0%} der Erkennungen ab conf 0.25 ohne ID bzw. mit Kurz-ID, keine "
             f"Lücke ohne ID ab {MAX_LUECKE_S // 60} min, keine Geister. Viele Erkennungen ohne ID "
             "in einem Band heißen: Diese Kühe werden nicht ausgewertet (Schwanzwinkel, Brunst) – "
             "Abwägung im Skill bytetrack-tuning.")
    if any(not e["kuehe_echt"] for e in ergebnisse.values()):
        z.append("Ohne --kuehe ist die Kuhzahl geschätzt; ein Geist mit eigener ID zählt dann "
                 "als Kuh und verdeckt sich selbst.")
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
        raise SystemExit(f"Klasse(n) {fehlen} nicht im Modell: {sorted(namen)}")
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


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("clip", type=Path)
    a.add_argument("--modell", help="best.pt/.onnx; ohne: Erkennungen aus <clip>.erkennungen.json")
    a.add_argument("--tier-klassen", nargs="+",
                   help="wie modell.tier_klassen in config.yaml (Default: kuh)")
    a.add_argument("--kuehe", type=int, help="so viele Kuehe stehen wirklich im Bild")
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
            raise SystemExit(f"{ablage} enthaelt Tierklassen {gespeichert}, verlangt "
                             f"{arg.tier_klassen} – mit --modell neu erzeugen.")
        print(f"Erkennungen aus {ablage} (Modell {daten.get('modell', '?')}, "
              f"Tierklassen {gespeichert})", file=sys.stderr)
    else:
        raise SystemExit(f"{ablage} fehlt – einmal mit --modell aufrufen.")

    ergebnisse = {Path(t).name: kennzahlen(verfolge(bilder, t, set(tier_ids)), arg.kuehe)
                  for t in arg.tracker}
    print(f"## Tracking-Prüfung {arg.clip.name}\n")
    print(tabelle(ergebnisse, fps_geraet))
    return 0 if all(e["ziel_erfuellt"] for e in ergebnisse.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
