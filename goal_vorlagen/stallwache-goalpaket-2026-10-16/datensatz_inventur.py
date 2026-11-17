#!/usr/bin/env python3
"""
Datensatz-Inventur der Silent-Mode-Aufnahmen — macht Punkt 4 des Tagesreports messbar.

Liest ./aufnahmen (nur lesen: nichts wird verschoben, gelöscht oder hochgeladen)
und liefert je Kamera und Stall-Tag:
  * Bildzahl, einzigartige Bilder (dHash-Dubletten gegen das letzte behaltene Bild),
  * Lichtphase je Bild: tag | daemmerung | ir_nacht,
  * IR-Anteil gegen Beschluss B9 (IR-Nacht >= 1/3),
  * einen Split-Vorschlag nach ganzen Stall-Tagen (12-Uhr-Grenze, nie nach Frames).

Aufruf:
    python tools/datensatz_inventur.py ./aufnahmen --md metriken-datensatz.md --json inventur.json

Abhängigkeiten: numpy + Pillow (Fallback: OpenCV).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

BILD_ENDUNGEN = (".jpg", ".jpeg", ".png")
PHASEN = ("tag", "daemmerung", "ir_nacht")
STALLTAG_VERSATZ = timedelta(hours=12)       # eine Nacht gehört genau einem Stall-Tag

# Kamerapraefix optional (B21): neue Silent-Mode-Bilder heissen
# <kamera>_<YYYYmmdd-HHMMSS>.jpg (UTC), der Altbestand nur <YYYYmmdd-HHMMSS>.jpg.
_MUSTER = re.compile(
    r"^(?:(?P<kamera>[A-Za-z][A-Za-z0-9]*)[_-])?"
    r"(?P<datum>\d{4}-?\d{2}-?\d{2})[_T-]?"
    r"(?P<zeit>\d{2}[-:.]?\d{2}[-:.]?\d{2})"
)


@dataclass(frozen=True)
class InventurKonfig:
    ir_spreizung_max: float = 3.0       # mittlere Farbkanal-Spreizung (0..255) darunter = IR/grau
    dunkel_max: float = 60.0            # mittlere Helligkeit darunter = Dämmerung (nur Farbbilder)
    dublette_hamming: int = 4           # dHash-Abstand bis einschließlich = Dublette
    val_anteil: float = 0.15
    ir_ziel_anteil: float = 1.0 / 3.0   # Beschluss B9


# --- Bild-Grundfunktionen ------------------------------------------------------

def _lade_rgb(pfad: str) -> np.ndarray:
    """RGB uint8 (H, W, 3) oder Graubild (H, W). Wirft bei unlesbaren Dateien."""
    try:
        from PIL import Image
        with Image.open(pfad) as bild:
            bild.load()
            if bild.mode not in ("RGB", "L"):
                bild = bild.convert("RGB")
            return np.asarray(bild)
    except ImportError:
        import cv2
        bgr = cv2.imread(pfad, cv2.IMREAD_UNCHANGED)
        if bgr is None:
            raise OSError(f"unlesbar: {pfad}")
        return bgr if bgr.ndim == 2 else bgr[:, :, ::-1]


def _verkleinern(arr: np.ndarray, breite: int, hoehe: int) -> np.ndarray:
    """Flächenmittel ohne Zusatzbibliothek; robust gegen JPEG-Rauschen."""
    h, w = arr.shape[:2]
    ys = np.linspace(0, h, hoehe + 1).astype(int)
    xs = np.linspace(0, w, breite + 1).astype(int)
    a = arr.astype(np.float64)
    zeilen = [a[ys[i]:max(ys[i + 1], ys[i] + 1)].mean(axis=0) for i in range(hoehe)]
    zeilen_arr = np.stack(zeilen)
    spalten = [zeilen_arr[:, xs[j]:max(xs[j + 1], xs[j] + 1)].mean(axis=1) for j in range(breite)]
    return np.stack(spalten, axis=1)


def lichtphase(arr: np.ndarray, konfig: InventurKonfig = InventurKonfig()) -> str:
    """tag | daemmerung | ir_nacht. IR-Nachtbilder der Kameras sind praktisch grau."""
    if arr.ndim == 2:
        return "ir_nacht"
    klein = _verkleinern(arr[:, :, :3], 64, 36)
    r, g, b = klein[:, :, 0], klein[:, :, 1], klein[:, :, 2]
    spreizung = float((np.abs(r - g) + np.abs(g - b) + np.abs(b - r)).mean() / 3.0)
    if spreizung < konfig.ir_spreizung_max:
        return "ir_nacht"
    if float(klein.mean()) < konfig.dunkel_max:
        return "daemmerung"
    return "tag"


def dhash(arr: np.ndarray) -> int:
    """64-Bit-Differenz-Hash auf 9x8 Graustufen."""
    grau = arr.astype(np.float64) if arr.ndim == 2 else arr[:, :, :3].astype(np.float64).mean(axis=2)
    klein = _verkleinern(grau, 9, 8)
    bits = (klein[:, 1:] > klein[:, :-1]).flatten()
    wert = 0
    for bit in bits:
        wert = (wert << 1) | int(bit)
    return wert


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# --- Zeit und Stall-Tag --------------------------------------------------------

def zeit_aus_dateiname(name: str) -> Optional[Tuple[str, datetime]]:
    """'stallwache_20261014_031500.jpg' u. ä. -> ('stallwache', datetime). Sonst None."""
    treffer = _MUSTER.match(os.path.basename(name))
    if not treffer:
        return None
    datum = treffer.group("datum").replace("-", "")
    zeit = re.sub(r"[-:.]", "", treffer.group("zeit"))
    try:
        kamera = (treffer.group("kamera") or "unbekannt").lower()  # ohne Praefix: Altbestand
        return kamera, datetime.strptime(datum + zeit, "%Y%m%d%H%M%S")
    except ValueError:
        return None


def stall_tag(zeitpunkt: datetime) -> date:
    """Stall-Tag beginnt um 12:00 Ortszeit (Europe/Berlin) — so liegt eine Nacht nie
    auf zwei Tagen. Naive Zeitpunkte sind UTC wie die Dateinamen (B21); gleiche
    Rechnung wie cvat_zu_yolo_pose.stalltag und abnahme_gates.stalltag."""
    from zoneinfo import ZoneInfo
    utc = zeitpunkt if zeitpunkt.tzinfo else zeitpunkt.replace(tzinfo=timezone.utc)
    return (utc.astimezone(ZoneInfo("Europe/Berlin")) - STALLTAG_VERSATZ).date()


# --- Inventur ------------------------------------------------------------------

@dataclass
class KameraStat:
    bilder: int = 0
    einzigartig: int = 0
    unlesbar: int = 0
    zeit_fallback: int = 0
    phasen: Dict[str, int] = field(default_factory=lambda: {p: 0 for p in PHASEN})
    tage: Dict[str, int] = field(default_factory=dict)


@dataclass
class Inventur:
    kameras: Dict[str, KameraStat] = field(default_factory=dict)
    tage_ir: Dict[str, int] = field(default_factory=dict)       # Stall-Tag -> einzigartige IR-Bilder
    tage_alle: Dict[str, int] = field(default_factory=dict)     # Stall-Tag -> einzigartige Bilder

    def gesamt(self) -> Dict[str, int]:
        s = {"bilder": 0, "einzigartig": 0, "unlesbar": 0, "zeit_fallback": 0}
        for k in self.kameras.values():
            for key in s:
                s[key] += getattr(k, key)
        for p in PHASEN:
            s[p] = sum(k.phasen[p] for k in self.kameras.values())
        return s


def _dateien(ordner: str) -> Iterable[str]:
    for wurzel, _, namen in os.walk(ordner):
        if os.sep + "crops" in wurzel + os.sep:     # Re-ID-Crops (B6) gehören nicht in die Inventur
            continue
        for n in namen:
            if n.lower().endswith(BILD_ENDUNGEN):
                yield os.path.join(wurzel, n)


def inventur(ordner: str, konfig: InventurKonfig = InventurKonfig()) -> Inventur:
    eintraege: List[Tuple[str, datetime, str, bool]] = []
    for pfad in _dateien(ordner):
        geparst = zeit_aus_dateiname(pfad)
        if geparst:
            kamera, zeitpunkt = geparst
            fallback = False
        else:
            kamera = re.split(r"[_-]", os.path.basename(pfad))[0].lower() or "unbekannt"
            # UTC wie die Namenszeit, damit stall_tag beide gleich behandelt
            zeitpunkt = datetime.fromtimestamp(os.path.getmtime(pfad), tz=timezone.utc).replace(tzinfo=None)
            fallback = True
        eintraege.append((kamera, zeitpunkt, pfad, fallback))

    inv = Inventur()
    letzter_hash: Dict[str, int] = {}
    for kamera, zeitpunkt, pfad, fallback in sorted(eintraege, key=lambda e: (e[0], e[1], e[2])):
        stat = inv.kameras.setdefault(kamera, KameraStat())
        stat.bilder += 1
        stat.zeit_fallback += int(fallback)
        try:
            arr = _lade_rgb(pfad)
        except Exception:
            stat.unlesbar += 1
            continue
        h = dhash(arr)
        vorher = letzter_hash.get(kamera)
        if vorher is not None and hamming(h, vorher) <= konfig.dublette_hamming:
            continue
        letzter_hash[kamera] = h
        stat.einzigartig += 1
        phase = lichtphase(arr, konfig)
        stat.phasen[phase] += 1
        tag = stall_tag(zeitpunkt).isoformat()
        stat.tage[tag] = stat.tage.get(tag, 0) + 1
        inv.tage_alle[tag] = inv.tage_alle.get(tag, 0) + 1
        if phase == "ir_nacht":
            inv.tage_ir[tag] = inv.tage_ir.get(tag, 0) + 1
    return inv


# --- Split nach Stall-Tagen ----------------------------------------------------

def split_nach_tagen(inv: Inventur, konfig: InventurKonfig = InventurKonfig()) -> Dict[str, str]:
    """
    Ganze Stall-Tage nach train | val. Val = jüngste Tage (~15 %), mindestens ein
    Tag mit IR-Nachtbildern im Val-Set. Weniger als 2 Tage: kein Val-Set.
    """
    tage = sorted(inv.tage_alle)
    if len(tage) < 2:
        return {t: "train" for t in tage}
    n_val = max(1, round(len(tage) * konfig.val_anteil))
    val = tage[-n_val:]
    train = tage[:-n_val]
    if inv.tage_ir and not any(t in inv.tage_ir for t in val):
        ir_train = [t for t in train if t in inv.tage_ir]
        if ir_train:
            rein, raus = ir_train[-1], val[0]
            val = sorted(set(val) - {raus} | {rein})
            train = sorted(set(train) - {rein} | {raus})
    return {**{t: "train" for t in train}, **{t: "val" for t in val}}


# --- Ausgabe -------------------------------------------------------------------

def _prozent(teil: int, ganz: int) -> str:
    return "–" if ganz == 0 else f"{100.0 * teil / ganz:.0f} %"


def metriken_markdown(inv: Inventur, split: Dict[str, str],
                      konfig: InventurKonfig = InventurKonfig(),
                      stand: Optional[str] = None) -> str:
    stand = stand or datetime.now().strftime("%d.%m.%Y %H:%M")
    g = inv.gesamt()
    ir_anteil = 0.0 if g["einzigartig"] == 0 else g["ir_nacht"] / g["einzigartig"]
    b9 = "erfüllt" if ir_anteil >= konfig.ir_ziel_anteil else "nicht erfüllt"
    zeilen = [
        f"## Datensatz (Silent Mode) — Stand {stand}",
        "",
        "Quelle: `tools/datensatz_inventur.py` (nur lesend). Phasenanteile über einzigartige Bilder.",
        "",
        "| Kamera | Bilder | einzigartig | Stall-Tage | Tag | Dämmerung | IR-Nacht | unlesbar | Zeit aus Dateidatum |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in sorted(inv.kameras):
        k = inv.kameras[name]
        zeilen.append(
            f"| {name} | {k.bilder} | {k.einzigartig} | {len(k.tage)} | "
            f"{_prozent(k.phasen['tag'], k.einzigartig)} | {_prozent(k.phasen['daemmerung'], k.einzigartig)} | "
            f"{_prozent(k.phasen['ir_nacht'], k.einzigartig)} | {k.unlesbar} | {k.zeit_fallback} |")
    val_tage = sorted(t for t, s in split.items() if s == "val")
    train_tage = sorted(t for t, s in split.items() if s == "train")
    zeilen += [
        "",
        f"- **Einzigartige Bilder gesamt:** {g['einzigartig']} (Ziel Labelsatz v1: 1.500–3.000)",
        f"- **IR-Anteil (B9, Ziel ≥ 33 %):** {ir_anteil * 100:.0f} % — {b9}",
        f"- **Split-Vorschlag (Stall-Tage, 12-Uhr-Grenze):** train {len(train_tage)} · val {len(val_tage)}"
        + (f" ({', '.join(val_tage)})" if val_tage else " — zu wenige Tage für ein Val-Set"),
        "- **Austreibungs-Material (amniotic_sac / calf_legs):** nicht automatisch erfassbar — manuell eintragen",
        "",
    ]
    return "\n".join(zeilen)


def als_json(inv: Inventur, split: Dict[str, str]) -> dict:
    return {
        "kameras": {n: {"bilder": k.bilder, "einzigartig": k.einzigartig, "unlesbar": k.unlesbar,
                        "zeit_fallback": k.zeit_fallback, "phasen": k.phasen, "tage": k.tage}
                    for n, k in inv.kameras.items()},
        "gesamt": inv.gesamt(),
        "split": split,
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Datensatz-Inventur der Silent-Mode-Aufnahmen (nur lesend)")
    p.add_argument("ordner", help="Pfad zu ./aufnahmen")
    p.add_argument("--md", help="Markdown-Abschnitt für docs/metriken.md hierhin schreiben")
    p.add_argument("--json", help="Rohzahlen als JSON hierhin schreiben")
    a = p.parse_args(argv)
    if not os.path.isdir(a.ordner):
        print(f"Ordner nicht gefunden: {a.ordner}", file=sys.stderr)
        return 2
    inv = inventur(a.ordner)
    split = split_nach_tagen(inv)
    md = metriken_markdown(inv, split)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write(md)
    else:
        print(md)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(als_json(inv, split), f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
