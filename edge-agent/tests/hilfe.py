"""Gemeinsame Testhilfe: laedt main.py ohne cv2/numpy-Installation.

Die Logiktests laufen auf jedem Rechner mit purem Python 3.10+ — die
schweren Abhaengigkeiten werden gestubbt (dank `from __future__ import
annotations` in main.py werden Typ-Hints nicht ausgewertet). Der
requests-Stub zeichnet alle HTTP-Aufrufe auf, damit Tests sie pruefen
koennen, ohne dass je ein echter Request rausgeht.
"""

import importlib.util
import sys
import types
from pathlib import Path

MAIN_PY = Path(__file__).resolve().parent.parent / "main.py"


def lade_main(mit_requests_stub: bool = False):
    """Laedt main.py als Modul 'stall_main'; gibt (modul, gesendet) zurueck.

    gesendet: Liste (url, kwargs) aller requests.post-Aufrufe, wenn
    mit_requests_stub=True, sonst None (dann bleibt echtes requests aussen
    vor, aber ungenutzt, weil die Tests keine Netzpfade beruehren).
    """
    gesendet: list | None = None
    if mit_requests_stub or "requests" not in sys.modules:
        gesendet = []
        stub = types.ModuleType("requests")
        stub.RequestException = Exception
        antwort = types.SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"result": []}
        )
        stub.post = lambda url, **kw: (gesendet.append((url, kw)), antwort)[1]
        stub.get = lambda url, **kw: antwort
        sys.modules["requests"] = stub

    for name in ("cv2", "yaml"):
        sys.modules.setdefault(name, types.ModuleType(name))
    np = types.ModuleType("numpy")
    np.ndarray = object
    sys.modules.setdefault("numpy", np)

    spec = importlib.util.spec_from_file_location("stall_main", MAIN_PY)
    m = importlib.util.module_from_spec(spec)
    sys.modules["stall_main"] = m  # noetig fuer @dataclass-Introspektion
    spec.loader.exec_module(m)
    return m, gesendet


class Pruefer:
    """Minimaler Check-Sammler mit Abschlussbericht (kein pytest noetig)."""

    def __init__(self, name: str):
        self.name = name
        self.faelle: list[tuple[str, bool]] = []

    def check(self, beschreibung: str, bedingung) -> None:
        self.faelle.append((beschreibung, bool(bedingung)))

    def bericht(self) -> int:
        fehler = [f for f in self.faelle if not f[1]]
        for beschreibung, ok in self.faelle:
            print(f"{'OK  ' if ok else 'FEHL'} {beschreibung}")
        print(f"\n{self.name}: {len(self.faelle) - len(fehler)}/{len(self.faelle)} Checks bestanden")
        return 1 if fehler else 0
