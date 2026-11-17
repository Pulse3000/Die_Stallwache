"""
Sperre, Fähigkeitsprüfung und API-Abbildung — Erkennungsvertrag V0, V6, V7.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .vertrag import Ereignis, Konfig

NIE_SPERREN = frozenset({"austreibung", "eskalation"})
API_TYPEN_BASIS = ("kalbeverdacht", "austreibung", "brunstverdacht", "info")


# --- V6 Sperre ----------------------------------------------------------------

class Sperre:
    """Cooldown je (Kuh-ID, Alarmtyp). Austreibung und Eskalation sind nicht sperrbar."""

    def __init__(self, dauer_sek: float = 900.0) -> None:
        self.dauer_sek = float(dauer_sek)
        self._bis: Dict[Tuple[Optional[str], str], float] = {}

    def sperren(self, kuh_id: Optional[str], typ: str, jetzt: float) -> None:
        if typ in NIE_SPERREN:
            raise ValueError(f"'{typ}' darf nie gesperrt werden (Recall-Vertrag)")
        self._bis[(kuh_id, typ)] = jetzt + self.dauer_sek

    def gesperrt(self, kuh_id: Optional[str], typ: str, jetzt: float) -> bool:
        if typ in NIE_SPERREN:
            return False
        return jetzt < self._bis.get((kuh_id, typ), float("-inf"))


# --- V0 Fähigkeitsprüfung -----------------------------------------------------

def _info(kamera: str, jetzt: float, text: str) -> Ereignis:
    return Ereignis(typ="info", kamera=kamera, kuh_id=None, zeit=jetzt, nachricht=text)


def faehigkeitspruefung(modell_klassen: Iterable[str],
                        modell_keypoints: Sequence[str],
                        kamera: str,
                        konfig: Optional[Konfig] = None,
                        jetzt: float = 0.0) -> List[Ereignis]:
    """
    Prüft beim Start, was das geladene Modell überhaupt erkennen kann.
    Jede fehlende Fähigkeit wird als info-Ereignis gemeldet — nie still übergangen.
    Leere Liste = Modell erfüllt den Vertrag.
    """
    k = konfig or Konfig()
    klassen = {k.kanonisch(c) for c in modell_klassen}
    meldungen: List[Ereignis] = []

    fehlend = [c for c in k.austreibung_klassen if c not in klassen]
    if len(fehlend) == len(k.austreibung_klassen):
        meldungen.append(_info(kamera, jetzt,
            "Austreibungserkennung nicht verfügbar: Modell kennt die Klassen "
            f"{', '.join(k.austreibung_klassen)} nicht."))
    elif fehlend:
        meldungen.append(_info(kamera, jetzt,
            f"Austreibungserkennung eingeschränkt: Klasse(n) {', '.join(fehlend)} fehlen im Modell."))

    if k.kuh_klasse not in klassen:
        meldungen.append(_info(kamera, jetzt,
            f"Kalbeverdacht nicht verfügbar: Klasse {k.kuh_klasse} fehlt im Modell."))
    else:
        vorhanden = set(modell_keypoints)
        fehlende_kp = [n for n in k.keypoint_namen if n not in vorhanden]
        if fehlende_kp:
            meldungen.append(_info(kamera, jetzt,
                "Kalbeverdacht nicht verfügbar: Keypoint(s) "
                f"{', '.join(fehlende_kp)} fehlen im Modell (Label-Vertrag)."))
    return meldungen


# --- V7 API-Abbildung (POST /api/events) --------------------------------------

def api_nutzlast(ereignis: Ereignis, konfig: Optional[Konfig] = None) -> dict:
    """
    Ereignis -> Body für POST /api/events. Genau die fünf Vertragsfelder.
    Bis B17 entschieden ist, reist die Eskalation als typ 'austreibung' mit
    Präfix 'ESKALATION' in der Nachricht.
    """
    k = konfig or Konfig()
    typ = ereignis.typ
    erlaubt: Tuple[str, ...] = API_TYPEN_BASIS
    if k.eskalation_api_typ == "eskalation":
        erlaubt = erlaubt + ("eskalation",)
    if typ == "eskalation":
        typ = k.eskalation_api_typ
    if typ not in erlaubt:
        raise ValueError(f"typ '{ereignis.typ}' ist im Ereignis-Schema nicht erlaubt")
    nachricht = (ereignis.nachricht or "").strip()
    if not nachricht:
        raise ValueError("nachricht ist Pflicht")
    konfidenz = ereignis.konfidenz
    if konfidenz is not None:
        konfidenz = float(konfidenz)
        if not 0.0 <= konfidenz <= 1.0:
            raise ValueError("konfidenz muss in [0, 1] liegen oder None sein")
        konfidenz = round(konfidenz, 3)
    return {
        "typ": typ,
        "kuhId": ereignis.kuh_id,
        "kamera": ereignis.kamera,
        "nachricht": nachricht,
        "konfidenz": konfidenz,
    }
