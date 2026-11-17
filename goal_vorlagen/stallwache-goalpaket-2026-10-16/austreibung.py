"""
Austreibung (Prio 1) und Eskalation — Erkennungsvertrag V1–V3.

Grundsätze:
  * Ausgewertet wird der ganze Frame. Eine Fruchtblase oder Kälberfüße lösen aus,
    auch wenn keine Kuh erkannt wurde (liegende Kuh, IR, Verdeckung).
  * Der erste Treffer einer Episode wird im selben Aufruf gemeldet — keine
    Verzögerung, kein Fenster, keine Sperre.
  * Wiederholungen innerhalb einer Episode sind kein neuer Alarm. Genau eine
    Eskalation pro Episode, wenn nach 60 min weiterhin Austreibung sichtbar ist.
  * Die Kuh-Zuordnung reichert an, sie ist nie Bedingung.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .vertrag import Box, Ereignis, Frame, Konfig, Objekt

KuhIdVon = Callable[[Objekt], Optional[str]]


def _standard_kuh_id(kuh: Objekt) -> Optional[str]:
    """Platzhalter. In der Integration den Identitätsauflöser (stabile IDs) übergeben."""
    return None if kuh.track_id is None else f"Kuh #{kuh.track_id}"


def _ueberlappung(a: Box, b: Box) -> float:
    breite = min(a[2], b[2]) - max(a[0], b[0])
    hoehe = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, breite) * max(0.0, hoehe)


def zuordnen(box: Box, kuehe: Sequence[Objekt], rand: float) -> Optional[Objekt]:
    """
    Kuh, deren um `rand` erweiterte Box den Mittelpunkt der Detektion enthält.
    Mehrere Kandidaten: größte Überlappung gewinnt. Kein Kandidat: None.
    Der Rand fängt Fruchtblasen ab, die hinter der Kuh-Box austreten.
    """
    cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    kandidaten: List[Tuple[float, int, Objekt]] = []
    for i, kuh in enumerate(kuehe):
        x1, y1, x2, y2 = kuh.box
        rx, ry = rand * (x2 - x1), rand * (y2 - y1)
        if x1 - rx <= cx <= x2 + rx and y1 - ry <= cy <= y2 + ry:
            kandidaten.append((_ueberlappung(box, kuh.box), -i, kuh))
    if not kandidaten:
        return None
    return max(kandidaten, key=lambda t: (t[0], t[1]))[2]


@dataclass
class _Episode:
    id: str
    start: float
    letzte: float
    eskaliert: bool = False


class Austreibungswaechter:
    """Hält Episoden je (Kamera, Kuh-ID). Kuh-ID None ist ein eigener, gültiger Schlüssel."""

    def __init__(self, konfig: Optional[Konfig] = None,
                 kuh_id_von: Optional[KuhIdVon] = None) -> None:
        self.konfig = konfig or Konfig()
        self.kuh_id_von: KuhIdVon = kuh_id_von or _standard_kuh_id
        self._episoden: Dict[Tuple[str, Optional[str]], _Episode] = {}

    # -- Abfragen --------------------------------------------------------------

    def episode_aktiv(self, kamera: str, kuh_id: Optional[str], jetzt: float) -> bool:
        """True, solange die Episode nicht abgelaufen ist (Integrationspflicht I3)."""
        ep = self._episoden.get((kamera, kuh_id))
        return ep is not None and (jetzt - ep.letzte) <= self.konfig.episode_reset_sek

    # -- Hauptweg --------------------------------------------------------------

    def verarbeite(self, frame: Frame) -> List[Ereignis]:
        k = self.konfig
        self._aufraeumen(frame.zeit)

        ausloeser = [o for o in frame.objekte
                     if k.kanonisch(o.klasse) in k.austreibung_klassen
                     and float(o.konfidenz) > k.austreibung_schwelle]
        if not ausloeser:
            return []

        kuehe = [o for o in frame.objekte if k.kanonisch(o.klasse) == k.kuh_klasse]
        gruppen: Dict[Optional[str], List[Objekt]] = {}
        for objekt in ausloeser:
            kuh = zuordnen(objekt.box, kuehe, k.zuordnung_rand)
            kuh_id = self.kuh_id_von(kuh) if kuh is not None else None
            gruppen.setdefault(kuh_id, []).append(objekt)

        ereignisse: List[Ereignis] = []
        for kuh_id, belege in gruppen.items():
            schluessel = (frame.kamera, kuh_id)
            ep = self._episoden.get(schluessel)
            if ep is None:
                ep = _Episode(id=f"{frame.kamera}:{kuh_id or 'unbekannt'}:{int(frame.zeit)}",
                              start=frame.zeit, letzte=frame.zeit)
                self._episoden[schluessel] = ep
                ereignisse.append(self._ereignis("austreibung", frame, kuh_id, belege, ep))
                continue
            ep.letzte = max(ep.letzte, frame.zeit)
            if not ep.eskaliert and frame.zeit - ep.start >= k.eskalation_nach_sek:
                ep.eskaliert = True
                ereignisse.append(self._ereignis("eskalation", frame, kuh_id, belege, ep))
        return ereignisse

    # -- intern ----------------------------------------------------------------

    def _aufraeumen(self, jetzt: float) -> None:
        grenze = self.konfig.episode_reset_sek
        abgelaufen = [s for s, ep in self._episoden.items() if jetzt - ep.letzte > grenze]
        for s in abgelaufen:
            del self._episoden[s]

    def _ereignis(self, typ: str, frame: Frame, kuh_id: Optional[str],
                  belege: List[Objekt], ep: _Episode) -> Ereignis:
        klassen = {self.konfig.kanonisch(o.klasse) for o in belege}
        if {"amniotic_sac", "calf_legs"} <= klassen:
            wort = "Fruchtblase und Kälberfüße"
        elif "calf_legs" in klassen:
            wort = "Kälberfüße"
        else:
            wort = "Fruchtblase"
        kuh_text = kuh_id or "nicht zugeordneter Kuh"
        if typ == "austreibung":
            text = f"SOFORT-ALARM: {wort} bei {kuh_text} erkannt! (Kamera {frame.kamera})"
        else:
            minuten = int((frame.zeit - ep.start) // 60)
            text = (f"ESKALATION: {wort} bei {kuh_text} seit {minuten} Min. sichtbar – "
                    f"Geburt kontrollieren. (Kamera {frame.kamera})")
        return Ereignis(
            typ=typ,
            kamera=frame.kamera,
            kuh_id=kuh_id,
            zeit=frame.zeit,
            nachricht=text,
            konfidenz=round(max(float(o.konfidenz) for o in belege), 3),
            episode_id=ep.id,
            belege=tuple(belege),
        )
