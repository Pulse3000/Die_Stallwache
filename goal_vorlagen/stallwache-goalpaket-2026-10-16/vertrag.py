"""
Erkennungsvertrag v1 — Datentypen, Konfiguration, Keypoint-Eingang.

Reine Logik ohne I/O: kein Netz, keine Kamera, kein Modell. Die Integration
übersetzt die Modellausgabe (ONNX / ultralytics) in `Frame`-Objekte und reicht
`Ereignis`-Objekte an den Versand weiter.

Spezifikation: docs/erkennungsvertrag.md · Vertragstests: tests/test_erkennungsvertrag.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from typing import Dict, Mapping, Optional, Sequence, Tuple

Box = Tuple[float, float, float, float]      # x1, y1, x2, y2 in Pixeln
Keypoint = Tuple[float, float, float]        # x, y, Konfidenz

EREIGNIS_TYPEN = ("austreibung", "eskalation", "kalbeverdacht", "brunstverdacht", "info")


# --- Datentypen ---------------------------------------------------------------

@dataclass(frozen=True)
class Objekt:
    """Eine Modell-Detektion im Frame, Klassen- und Keypoint-Namen im Label-Vokabular."""
    klasse: str
    konfidenz: float
    box: Box
    keypoints: Mapping[str, Keypoint] = field(default_factory=dict)
    track_id: Optional[int] = None


@dataclass(frozen=True)
class Frame:
    zeit: float                              # Epoch-Sekunden
    kamera: str                              # stallwache | futterwache | stallbox
    objekte: Tuple[Objekt, ...] = ()


@dataclass(frozen=True)
class Ereignis:
    typ: str                                 # siehe EREIGNIS_TYPEN
    kamera: str
    kuh_id: Optional[str]
    zeit: float
    nachricht: str
    konfidenz: Optional[float] = None
    episode_id: Optional[str] = None
    belege: Tuple[Objekt, ...] = ()          # auslösende Detektionen -> Beweisbild (B1)


# --- Konfiguration ------------------------------------------------------------

@dataclass(frozen=True)
class Konfig:
    # V1/V2 Austreibung & Eskalation (AKTIV laut ki-wache-kern, B3)
    austreibung_schwelle: float = 0.80
    austreibung_klassen: Tuple[str, ...] = ("amniotic_sac", "calf_legs")
    episode_reset_sek: float = 1800.0
    eskalation_nach_sek: float = 3600.0
    zuordnung_rand: float = 0.15
    # V4 Keypoint-Vertrag (Indexreihenfolge = CVAT-Skelett = Datensatz-YAML; Name: B15)
    kuh_klasse: str = "kuh"
    keypoint_namen: Tuple[str, str, str] = ("spine_end", "tail_base", "tail_tip")
    keypoint_min_konfidenz: float = 0.5
    klassen_alias: Mapping[str, str] = field(default_factory=lambda: {"cow": "kuh"})
    # V5 Kalbeverdacht (Messgröße und Anteil: B16 — Vorlage, vorläufig)
    fenster_sek: float = 1800.0
    dominanz_anteil: float = 0.60
    min_abdeckung: float = 1.0 / 6.0
    wach_modus: bool = False
    # V6 Sperre
    cooldown_sek: float = 900.0
    # V7 API-Abbildung (B17 — Vorlage; bis dahin Eskalation als typ "austreibung")
    eskalation_api_typ: str = "austreibung"

    def __post_init__(self) -> None:
        pruefungen = [
            (0.0 < self.austreibung_schwelle < 1.0, "austreibung_schwelle muss in (0, 1) liegen"),
            (len(self.austreibung_klassen) > 0, "austreibung_klassen darf nicht leer sein"),
            (self.episode_reset_sek > 0, "episode_reset_sek muss > 0 sein"),
            (self.eskalation_nach_sek > 0, "eskalation_nach_sek muss > 0 sein"),
            (0.0 <= self.zuordnung_rand <= 1.0, "zuordnung_rand muss in [0, 1] liegen"),
            (len(self.keypoint_namen) == 3 and len(set(self.keypoint_namen)) == 3,
             "keypoint_namen braucht genau 3 verschiedene Namen (Rücken, Basis, Spitze)"),
            (0.0 < self.keypoint_min_konfidenz < 1.0, "keypoint_min_konfidenz muss in (0, 1) liegen"),
            (self.fenster_sek > 0, "fenster_sek muss > 0 sein"),
            (0.0 < self.dominanz_anteil < 1.0, "dominanz_anteil muss in (0, 1) liegen"),
            (0.0 < self.min_abdeckung <= 1.0, "min_abdeckung muss in (0, 1] liegen"),
            (self.cooldown_sek >= 0, "cooldown_sek muss >= 0 sein"),
            (self.eskalation_api_typ in ("austreibung", "eskalation"),
             "eskalation_api_typ muss 'austreibung' oder 'eskalation' sein"),
        ]
        for ok, meldung in pruefungen:
            if not ok:
                raise ValueError(meldung)

    @classmethod
    def aus_dict(cls, daten: Mapping[str, object]) -> "Konfig":
        """Liest eine Konfiguration. Unbekannte Schlüssel brechen den Start ab — laut, nicht still."""
        bekannt = {f.name for f in fields(cls)}
        unbekannt = sorted(set(daten) - bekannt)
        if unbekannt:
            raise ValueError(f"Unbekannte Konfig-Schlüssel: {', '.join(unbekannt)}")
        werte: Dict[str, object] = {}
        for name, wert in daten.items():
            if name in ("austreibung_klassen", "keypoint_namen") and isinstance(wert, (list, tuple)):
                wert = tuple(wert)
            werte[name] = wert
        return cls(**werte)  # type: ignore[arg-type]

    def kanonisch(self, klasse: str) -> str:
        """Bildet Modell-Klassennamen auf das Label-Vokabular ab (z. B. COCO 'cow' -> 'kuh')."""
        return self.klassen_alias.get(klasse, klasse)

    @property
    def dominanz_effektiv(self) -> float:
        """Wach-Modus (~14 Tage vor Termin): halbierter Anteilswert."""
        return self.dominanz_anteil / 2.0 if self.wach_modus else self.dominanz_anteil

    def min_frames_entscheidung(self, fps: float) -> int:
        """
        Mindestbelegung des Fensters, abgeleitet aus der realen Frame-Rate.
        1 fps, 30 min, Abdeckung 1/6 -> 300 Frames (bisheriger Codestand).
        Eine feste Zahl würde bei 0,1 fps (Snapshot-Pfad) nie erreicht.
        """
        if fps <= 0:
            raise ValueError("fps muss > 0 sein")
        n = math.ceil(round(self.fenster_sek * fps * self.min_abdeckung, 6))
        if self.wach_modus:
            n = math.ceil(n / 2)
        return max(1, n)


# --- Keypoint-Eingang ---------------------------------------------------------

def keypoints_aus_array(werte: Sequence[Sequence[float]], konfig: Konfig) -> Dict[str, Keypoint]:
    """
    Modellausgabe (3 Zeilen x, y, Konfidenz) -> benannte Keypoints.
    Die Indexreihenfolge ist Vertrag. Abweichende Form bricht laut ab, statt
    Punkte still zu vertauschen.
    """
    if len(werte) != len(konfig.keypoint_namen):
        raise ValueError(
            f"Modell liefert {len(werte)} Keypoints, Vertrag verlangt {len(konfig.keypoint_namen)}")
    ergebnis: Dict[str, Keypoint] = {}
    for name, zeile in zip(konfig.keypoint_namen, werte):
        if len(zeile) != 3:
            raise ValueError(f"Keypoint {name}: erwartet (x, y, Konfidenz), erhalten {len(zeile)} Werte")
        ergebnis[name] = (float(zeile[0]), float(zeile[1]), float(zeile[2]))
    return ergebnis


def winkel_aus_objekt(objekt: Objekt, konfig: Konfig) -> Optional[float]:
    """
    Rohwinkel zwischen Rückenvektor u (Rücken - Basis) und Schwanzvektor
    v (Spitze - Basis) — identisch zu kalibrierung.rohwinkel.

    None heißt Lücke: Der Frame darf nicht ins Schwanzfenster (Integrationspflicht I2).
    """
    ruecken, basis, spitze = konfig.keypoint_namen
    kp = objekt.keypoints or {}
    for name in (ruecken, basis, spitze):
        punkt = kp.get(name)
        if punkt is None or float(punkt[2]) < konfig.keypoint_min_konfidenz:
            return None
    ux, uy = kp[ruecken][0] - kp[basis][0], kp[ruecken][1] - kp[basis][1]
    vx, vy = kp[spitze][0] - kp[basis][0], kp[spitze][1] - kp[basis][1]
    nu, nv = math.hypot(ux, uy), math.hypot(vx, vy)
    if nu == 0.0 or nv == 0.0 or not math.isfinite(nu) or not math.isfinite(nv):
        return None
    cosinus = max(-1.0, min(1.0, (ux * vx + uy * vy) / (nu * nv)))
    return math.degrees(math.acos(cosinus))
