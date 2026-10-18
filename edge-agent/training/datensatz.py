#!/usr/bin/env python3
"""Datensatz-Werkzeug der Training-Pipeline: Sammeln -> Sichten -> Split.

  python3 datensatz.py bilanz     ./aufnahmen
  python3 datensatz.py ausduennen ./aufnahmen ./auswahl [--schwelle 6]
  python3 datensatz.py split      ./cvat-export ./datensatz [--val-anteil 0.15]
                                  [--val-tag 20261014 ...]

bilanz      Bilder je Kamera und Lichtphase (Tag/Daemmerung/IR-Nacht).
            Exit 1, wenn IR-Nacht unter 1/3 liegt (Beschluss B9: die
            Kalbung kommt nachts).
ausduennen  Kopiert nur Bilder, die sich vom zuletzt behaltenen Bild
            derselben Kamera (bzw. desselben Unterordners) sichtbar
            unterscheiden (leere Bucht, schlafende Herde). Die
            Ordnerstruktur bleibt erhalten, das Ziel muss leer sein;
            Originale bleiben unangetastet.
split       Teilt einen CVAT-Export (Format "Ultralytics YOLO Pose") nach
            Stalltagen in train/val, nie zufaellig nach Frames: Nachbarframes
            sind fast identisch und wuerden die Val-Werte schoenen.
            Ein Stalltag laeuft 12:00 bis 12:00, damit jede Nacht ganz in
            einer Haelfte liegt. Val fuellt sich mit --val-tag, dann je
            Austreibungsklasse (Fruchtblase, Kaelberfuesse) mit deren
            juengstem Tag, dann mit den juengsten Tagen bis zum Val-Anteil.
            Bilder ohne Zeitstempel im Namen (offene Datensaetze,
            Fehlalarm-Ablage) gehen immer nach train.

Die Entscheidungslogik ist reines Python (getestet in
tests/test_training.py). numpy/cv2 laden erst die Befehle, die Bilder lesen.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

# Beschluss B9: mindestens ein Drittel IR-Nacht im Datensatz.
IR_MIN_ANTEIL = 1 / 3
# Mittlerer Farbabstand (max - min der BGR-Kanaele, 0-255). IR-Bilder sind
# graustufig, JPEG-Artefakte bleiben darunter.
FARBIGKEIT_IR_MAX = 4.0
# Mittlere Helligkeit (0-255), unter der ein Farbbild als Daemmerung zaehlt.
HELLIGKEIT_DAEMMERUNG_MAX = 70.0
# Stalltag-Wechsel um 12:00: die Nacht 18:00-06:00 bleibt ungeteilt.
STALLTAG_WECHSEL_STUNDE = 12
# Klassen-Indizes aus stall.yaml, die eine Geburt belegen.
AUSTREIBUNG_KLASSEN = {1: "amniotic_sac", 2: "calf_legs"}
BILDENDUNGEN = {".jpg", ".jpeg", ".png"}

_ZEIT = re.compile(r"(\d{8})-(\d{6})")


# --------------------------------------------------------------------------
# Reine Logik
# --------------------------------------------------------------------------

def zeit_aus_name(name: str) -> dt.datetime | None:
    """Aufnahmezeit aus dem Dateinamen (..._JJJJMMTT-HHMMSS...), sonst None."""
    treffer = _ZEIT.search(Path(name).stem)
    if not treffer:
        return None
    try:
        return dt.datetime.strptime("".join(treffer.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def kamera_aus_name(name: str) -> str:
    """Kamera-Praefix vor dem Zeitstempel (stallwache_2026...), sonst 'unbekannt'."""
    stamm = Path(name).stem
    treffer = _ZEIT.search(stamm)
    if treffer and treffer.start() > 1 and stamm[treffer.start() - 1] == "_":
        return stamm[: treffer.start() - 1]
    return "unbekannt"


def stalltag(zeit: dt.datetime) -> str:
    """Stalltag JJJJMMTT: 12:00 bis 12:00 des Folgetags."""
    return (zeit - dt.timedelta(hours=STALLTAG_WECHSEL_STUNDE)).strftime("%Y%m%d")


def lichtphase(helligkeit: float, farbigkeit: float) -> str:
    """'ir' (graustufig), 'daemmerung' (dunkles Farbbild) oder 'tag'."""
    if farbigkeit <= FARBIGKEIT_IR_MAX:
        return "ir"
    if helligkeit <= HELLIGKEIT_DAEMMERUNG_MAX:
        return "daemmerung"
    return "tag"


def bilanz(eintraege: list[tuple[str, str]]) -> dict:
    """eintraege: (kamera, lichtphase) je Bild -> Zaehler und IR-Anteil."""
    je_kamera: dict[str, dict[str, int]] = {}
    for kamera, phase in eintraege:
        zeile = je_kamera.setdefault(kamera, {"tag": 0, "daemmerung": 0, "ir": 0})
        zeile[phase] += 1
    gesamt = len(eintraege)
    ir = sum(1 for _, phase in eintraege if phase == "ir")
    anteil = ir / gesamt if gesamt else 0.0
    return {
        "gesamt": gesamt,
        "je_kamera": je_kamera,
        "ir_anteil": anteil,
        "b9_erfuellt": gesamt > 0 and anteil >= IR_MIN_ANTEIL,
    }


def waehle_aus(bilder: list[tuple[str, str, object]], distanz, schwelle: float) -> list[str]:
    """Duennt zeitlich sortierte Bilder aus.

    bilder: (name, kamera, signatur), chronologisch. Behalten wird das erste
    Bild je Kamera und danach jedes, das vom zuletzt behaltenen derselben
    Kamera mindestens `schwelle` entfernt ist.
    """
    zuletzt: dict[str, object] = {}
    behalten: list[str] = []
    for name, kamera, signatur in bilder:
        if kamera not in zuletzt or distanz(signatur, zuletzt[kamera]) >= schwelle:
            zuletzt[kamera] = signatur
            behalten.append(name)
    return behalten


def teile_nach_tagen(
    bilder: list[tuple[str, str | None, object]],
    val_anteil: float = 0.15,
    val_tage: list[str] | None = None,
) -> tuple[list[str], list[str], dict]:
    """Split nach Stalltagen.

    bilder: (name, stalltag oder None, Austreibungsklassen im Label als
    Menge von Klassen-Indizes; True/False fuer "irgendeine"). Rueckgabe:
    (train, val, protokoll). Kein Stalltag liegt in beiden Haelften. Jede
    Austreibungsklasse, die vorkommt, hat mindestens einen Tag in val –
    sonst waere ihr Recall in der Abnahme ungeprueft (Geburt ueber 12 Uhr:
    Fruchtblase am einen, Kaelberfuesse am naechsten Stalltag).
    """
    if not 0 < val_anteil < 1:
        raise ValueError("val_anteil muss zwischen 0 und 1 liegen")
    tage: dict[str, list[str]] = {}
    je_klasse: dict[object, set[str]] = {}
    ohne_datum: list[str] = []
    for name, tag, austreibung in bilder:
        if tag is None:
            ohne_datum.append(name)
            continue
        tage.setdefault(tag, []).append(name)
        if isinstance(austreibung, bool):
            klassen = {"austreibung"} if austreibung else set()
        else:
            klassen = set(austreibung or ())
        for k in klassen:
            je_klasse.setdefault(k, set()).add(tag)
    geburtstage = set().union(*je_klasse.values()) if je_klasse else set()
    if len(tage) < 2:
        raise ValueError(
            "Split nach Tagen braucht Bilder von mindestens zwei Stalltagen "
            f"(gefunden: {len(tage)})"
        )

    warnungen: list[str] = []
    val: list[str] = []
    for tag in val_tage or []:
        if tag in tage:
            if tag not in val:
                val.append(tag)
        else:
            warnungen.append(f"Stalltag {tag} kommt im Export nicht vor")
    for k in sorted(je_klasse, key=str):
        if not je_klasse[k] & set(val):
            val.append(max(je_klasse[k]))
    datiert = sum(len(n) for n in tage.values())
    for tag in sorted(tage, reverse=True):
        if sum(len(tage[t]) for t in val) >= val_anteil * datiert:
            break
        if tag not in val:
            val.append(tag)
    if len(val) >= len(tage):
        hinweis = "weniger --val-tag angeben, " if val_tage else ""
        raise ValueError(
            f"Alle Stalltage landeten in val – {hinweis}mehr Stalltage sammeln "
            "oder --val-anteil senken"
        )
    for k in sorted(je_klasse, key=str):
        if not je_klasse[k] - set(val):
            name = AUSTREIBUNG_KLASSEN.get(k, "Austreibung")
            warnungen.append(
                f"Alle Tage mit {name} liegen in val: Das Modell lernt die Klasse "
                "nur aus Beimischung. Die Abnahme prueft den Recall trotzdem ehrlich."
            )
    train_tage = sorted(t for t in tage if t not in val)
    val = sorted(val)
    train = [n for t in train_tage for n in tage[t]] + ohne_datum
    val_namen = [n for t in val for n in tage[t]]
    protokoll = {
        "train_tage": train_tage,
        "val_tage": val,
        "geburtstage": sorted(geburtstage),
        "geburtstage_je_klasse": {
            AUSTREIBUNG_KLASSEN.get(k, str(k)): sorted(v) for k, v in je_klasse.items()
        },
        "bilder_train": len(train),
        "bilder_val": len(val_namen),
        "ohne_datum_in_train": len(ohne_datum),
        "val_anteil_datiert": round(len(val_namen) / datiert, 3),
        "warnungen": warnungen,
    }
    return train, val_namen, protokoll


# --------------------------------------------------------------------------
# Bildzugriff (numpy/cv2 erst hier)
# --------------------------------------------------------------------------

def _bilder(ordner: Path) -> list[Path]:
    return sorted(
        p for p in ordner.rglob("*") if p.is_file() and p.suffix.lower() in BILDENDUNGEN
    )


def kennwerte(bild) -> tuple[float, float]:
    """(Helligkeit, Farbigkeit) eines BGR-Bilds, auf jedem 8. Pixel gemessen."""
    probe = bild[::8, ::8].astype("float32")
    helligkeit = float(probe.mean())
    farbigkeit = float((probe.max(axis=2) - probe.min(axis=2)).mean())
    return helligkeit, farbigkeit


def befehl_bilanz(args) -> int:
    import cv2

    eintraege = []
    for pfad in _bilder(Path(args.ordner)):
        bild = cv2.imread(str(pfad))
        if bild is None:
            print(f"übersprungen (nicht lesbar): {pfad}", file=sys.stderr)
            continue
        eintraege.append((kamera_aus_name(pfad.name), lichtphase(*kennwerte(bild))))
    b = bilanz(eintraege)
    print(f"{'Kamera':<14}{'Tag':>8}{'Dämmerung':>11}{'IR-Nacht':>10}")
    for kamera, z in sorted(b["je_kamera"].items()):
        print(f"{kamera:<14}{z['tag']:>8}{z['daemmerung']:>11}{z['ir']:>10}")
    print(f"\nGesamt {b['gesamt']} Bilder, IR-Nacht {b['ir_anteil']:.0%} "
          f"(Ziel ≥ {IR_MIN_ANTEIL:.0%}): {'OK' if b['b9_erfuellt'] else 'ZU WENIG'}")
    return 0 if b["b9_erfuellt"] else 1


def vergleichsgruppe(quelle: Path, pfad: Path) -> str:
    """Wogegen ein Bild beim Ausduennen verglichen wird: die Kamera aus dem
    Namen, sonst der Unterordner (Fehlalarm-Ablage, alte Namen ohne Kamera)."""
    kamera = kamera_aus_name(pfad.name)
    if kamera != "unbekannt":
        return kamera
    return f"ordner:{pfad.parent.relative_to(quelle).as_posix()}"


def zielpfad(quelle: Path, pfad: Path, ziel: Path) -> Path:
    """Kopie unter demselben relativen Pfad: gleichnamige Bilder aus
    verschiedenen Unterordnern (z. B. fehlalarme/<Tag>/kalbeverdacht-0-0.jpg)
    ueberschreiben sich nicht."""
    return ziel / pfad.relative_to(quelle)


def befehl_ausduennen(args) -> int:
    import cv2

    quelle, ziel = Path(args.quelle), Path(args.ziel)
    if ziel.exists() and any(ziel.iterdir()):
        print(f"{ziel} ist nicht leer – bitte leeren Zielordner angeben.", file=sys.stderr)
        return 1
    eintraege = []
    for pfad in _bilder(quelle):
        zeit = zeit_aus_name(pfad.name)
        bild = cv2.imread(str(pfad), cv2.IMREAD_GRAYSCALE)
        if bild is None:
            continue
        klein = cv2.resize(bild, (32, 24), interpolation=cv2.INTER_AREA).astype("float32")
        eintraege.append((zeit or dt.datetime.min, pfad, vergleichsgruppe(quelle, pfad), klein))
    eintraege.sort(key=lambda e: (e[0], e[1].relative_to(quelle).as_posix()))
    behalten = waehle_aus(
        [(str(p), k, s) for _, p, k, s in eintraege],
        lambda a, b: float(abs(a - b).mean()),
        args.schwelle,
    )
    for name in behalten:
        kopie = zielpfad(quelle, Path(name), ziel)
        kopie.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(name, kopie)
    print(f"{len(behalten)} von {len(eintraege)} Bildern nach {ziel} kopiert "
          f"(Schwelle {args.schwelle}).")
    return 0


def _label_zu(bild: Path) -> Path:
    teile = list(bild.parts)
    for i in range(len(teile) - 1, -1, -1):
        if teile[i] == "images":
            teile[i] = "labels"
            break
    return Path(*teile).with_suffix(".txt")


def austreibungsklassen(text: str) -> set[int]:
    """Austreibungsklassen (Indizes aus stall.yaml) in einem YOLO-Label."""
    klassen = set()
    for zeile in text.splitlines():
        teile = zeile.split()
        if teile and teile[0].isdigit() and int(teile[0]) in AUSTREIBUNG_KLASSEN:
            klassen.add(int(teile[0]))
    return klassen


def _label_klassen(label: Path) -> set[int]:
    return austreibungsklassen(label.read_text(encoding="utf-8")) if label.exists() else set()


def befehl_split(args) -> int:
    export, ziel = Path(args.export), Path(args.ziel)
    if ziel.exists() and any(ziel.iterdir()):
        print(f"{ziel} ist nicht leer – bitte leeren Zielordner angeben.", file=sys.stderr)
        return 1
    pfade: dict[str, Path] = {}
    for bild in _bilder(export):
        if bild.name in pfade:
            print(f"Doppelter Dateiname: {bild.name}", file=sys.stderr)
            return 1
        pfade[bild.name] = bild
    eintraege = []
    for name, bild in pfade.items():
        zeit = zeit_aus_name(name)
        eintraege.append((name, stalltag(zeit) if zeit else None, _label_klassen(_label_zu(bild))))
    try:
        train, val, protokoll = teile_nach_tagen(eintraege, args.val_anteil, args.val_tag)
    except ValueError as e:
        print(f"Split nicht möglich: {e}", file=sys.stderr)
        return 1
    for haelfte, namen in (("train", train), ("val", val)):
        (ziel / "images" / haelfte).mkdir(parents=True, exist_ok=True)
        (ziel / "labels" / haelfte).mkdir(parents=True, exist_ok=True)
        for name in namen:
            shutil.copy2(pfade[name], ziel / "images" / haelfte / name)
            label = _label_zu(pfade[name])
            if label.exists():  # ohne Label = Hintergrundbild (Negativbeispiel)
                shutil.copy2(label, ziel / "labels" / haelfte / label.name)
    (ziel / "split.json").write_text(json.dumps(protokoll, indent=2, ensure_ascii=False))
    print(json.dumps(protokoll, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="befehl", required=True)
    b = sub.add_parser("bilanz", help="Lichtphasen je Kamera, B9-Pruefung")
    b.add_argument("ordner")
    b.set_defaults(fn=befehl_bilanz)
    a = sub.add_parser("ausduennen", help="nahezu identische Bilder aussortieren")
    a.add_argument("quelle")
    a.add_argument("ziel")
    a.add_argument("--schwelle", type=float, default=6.0,
                   help="mittlere Grauwert-Differenz 0-255 (Standard 6)")
    a.set_defaults(fn=befehl_ausduennen)
    s = sub.add_parser("split", help="CVAT-Export nach Stalltagen teilen")
    s.add_argument("export")
    s.add_argument("ziel")
    s.add_argument("--val-anteil", type=float, default=0.15)
    s.add_argument("--val-tag", action="append", default=[],
                   help="Stalltag JJJJMMTT fest nach val (mehrfach moeglich)")
    s.set_defaults(fn=befehl_split)
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
