"""
Erkennungsvertrag v1 (Edge) — Referenzimplementierung.

Reine Logik, keine Abhängigkeiten außer der Standardbibliothek.
Spezifikation: docs/erkennungsvertrag.md
"""

from .ausgabe import API_TYPEN_BASIS, NIE_SPERREN, Sperre, api_nutzlast, faehigkeitspruefung
from .austreibung import Austreibungswaechter, zuordnen
from .vertrag import (
    EREIGNIS_TYPEN,
    Ereignis,
    Frame,
    Konfig,
    Objekt,
    keypoints_aus_array,
    winkel_aus_objekt,
)

__all__ = [
    "API_TYPEN_BASIS", "NIE_SPERREN", "EREIGNIS_TYPEN",
    "Austreibungswaechter", "Ereignis", "Frame", "Konfig", "Objekt", "Sperre",
    "api_nutzlast", "faehigkeitspruefung", "keypoints_aus_array",
    "winkel_aus_objekt", "zuordnen",
]
