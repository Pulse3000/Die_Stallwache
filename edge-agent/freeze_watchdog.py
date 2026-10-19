"""Freeze-Watchdog für den KI-Wache-Agent (Stallblick / Oberer Stollenhof).

Erkennt zwei Kamera-Defekte, die sonst niemand bemerkt:
  1. Eingefrorenes Bild  – N aufeinanderfolgende Frames (nahezu) identisch.
  2. Streifen-Korruption – Bildbereich aus senkrechten Farbstreifen
     (jede Spalte vertikal konstant -> Zeilen-Differenz ~ 0).

Ruhe vor Fülle: genau EIN `info`-Ereignis beim Eintritt in den Fehlerzustand,
eines bei Erholung. Kein Spam dazwischen. Blockiert die Analyse nie.
Die Entwarnung kommt erst nach `frames_bis_alarm` sauberen Bildern in Folge;
ein Rückfall vorher gehört zur selben Störung (keine neue Meldung). Gesperrt
ist trotzdem nur, solange das Bild defekt ist: Ein sauberes Bild gibt Analyse
und Trainingsbilder sofort wieder frei.

Einbindung (pro Kamera eine Instanz):
    wd = FreezeWatchdog("stallwache")
    ev = wd.pruefe(frame_bgr)          # numpy-Array HxWx3, uint8
    if ev: sende_event(ev)             # Telegram + POST /api/events
    if wd.defekt: ueberspringe Trainingsbild-Speicherung / Analyse

Im Agenten übernimmt das `pruefe_kamerabild()` in main.py; die Schwelle
`frames_bis_alarm` kommt aus `watchdog.frames_bis_alarm` (config.yaml) bzw.
`baue_watchdog()` (Silent Mode 5 Aufnahmen, Analyse-Modus 300 Frames).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger("stallblick-agent")

# Silent Mode: geprüft wird jedes gespeicherte Trainingsbild (alle
# `silent_mode.intervall_sekunden`, z. B. 60-120 s) -> 5 Bilder = 5-10 min.
FRAMES_SILENT = 5
# Analyse-Modus: geprüft wird jeder Frame bei ~1 FPS -> 300 Frames = 5 min.
FRAMES_ANALYSE = 300


@dataclass
class FreezeWatchdog:
    kamera: str
    frames_bis_alarm: int = 5          # Silent Mode @120 s -> 10 min; Analyse @1 FPS -> 5 s (ggf. 300 setzen)
    diff_schwelle: float = 0.5         # mittlere abs. Grauwert-Differenz (0..255) = "identisch"
    streifen_schwelle: float = 1.0     # mittlere Zeilen-Differenz im Band = "Streifen"
    streifen_anteil: float = 0.15      # Mindesthöhe eines Streifenbands (Anteil der Bildhöhe)
    _letztes: np.ndarray | None = field(default=None, repr=False)
    _gleich: int = 0
    _streifen: int = 0
    _seit: float | None = None
    defekt: bool = False
    grund: str | None = None
    ausfaelle: int = 0                 # Wie oft der Watchdog selbst gestolpert ist (Diagnose)
    analyse: bool = True               # False = Silent Mode: Meldung nennt Trainingsbilder statt Analyse
    _offen: bool = False               # Störung gemeldet, Entwarnung noch nicht
    _sauber: int = 0                   # saubere Bilder in Folge seit dem letzten Defekt

    @staticmethod
    def _grau(frame: np.ndarray) -> np.ndarray:
        g = frame.mean(axis=2) if frame.ndim == 3 else frame.astype(np.float32)
        h, w = g.shape
        # auf ~160 px Breite verkleinern: schnell auf Pi, robust gegen JPEG-Rauschen
        s = max(1, w // 160)
        return g[::s, ::s].astype(np.float32)

    def _hat_streifen(self, g: np.ndarray) -> bool:
        zeilen_diff = np.abs(np.diff(g, axis=0)).mean(axis=1)  # pro Zeilenpaar
        flach = zeilen_diff < self.streifen_schwelle
        mindest = self.streifen_anteil * len(zeilen_diff)
        # Jedes vertikal flache Band ab Mindesthoehe: Streifen nur, wenn sich
        # die Spalten IM BAND unterscheiden. Ein gleichmaessiges Band (dunkle
        # Decke ausserhalb der IR-Reichweite, ueberstrahlte Wand, Maske) ist
        # kein Defekt – frueher mittelte die Spalten-Pruefung ueber das ganze
        # Bild, und der lebendige Rest liess so ein Band als Streifen gelten.
        start = None
        for i, f in enumerate(list(flach) + [False]):
            if f and start is None:
                start = i
            elif not f and start is not None:
                if i - start >= mindest and g[start:i + 1].std(axis=1).mean() >= 5:
                    return True
                start = None
        return False

    def pruefe(self, frame: np.ndarray, jetzt: float | None = None) -> dict | None:
        if frame is None:
            # Kein Bild ist kein Bildfehler – das meldet der TotmannWaechter.
            return None
        try:
            jetzt = time.time() if jetzt is None else jetzt
            g = self._grau(frame)
            if self._letztes is not None and self._letztes.shape == g.shape \
                    and np.abs(g - self._letztes).mean() < self.diff_schwelle:
                self._gleich += 1
            else:
                self._gleich = 0
            self._letztes = g
            self._streifen = self._streifen + 1 if self._hat_streifen(g) else 0

            grund = None
            if self._gleich >= self.frames_bis_alarm:
                grund = "Bild eingefroren"
            elif self._streifen >= self.frames_bis_alarm:
                grund = "Bild gestört (Streifen)"

            if grund:
                self._sauber = 0
                if not self.defekt:
                    self.defekt, self.grund = True, grund
                    if not self._offen:   # Rückfall in offener Störung: keine neue Meldung
                        self._offen, self._seit = True, jetzt
                        zeit = time.strftime("%d.%m. %H:%M", time.localtime(jetzt))
                        folge = ("Analyse ausgesetzt – bitte Kamera/Bridge prüfen." if self.analyse else
                                 "Es werden vorerst keine Trainingsbilder gespeichert – "
                                 "bitte Kamera und Bildquelle (go2rtc/Bridge) prüfen.")
                        return self._event(f"Kamera {self.kamera}: {grund} seit {zeit}. {folge}")
                return None
            self.defekt, self.grund = False, None
            if self._offen:
                # Sauber zaehlt nur ein Bild, das beide Pruefungen einzeln besteht;
                # ein verdaechtiges (gleich wie das Vorbild, Streifen unter der
                # Schwelle) setzt die Serie zurueck – sonst kaeme beim Flattern
                # die Entwarnung zu frueh.
                self._sauber = self._sauber + 1 if self._gleich == 0 and self._streifen == 0 else 0
                if self._sauber >= self.frames_bis_alarm:
                    dauer = int((jetzt - (self._seit or jetzt)) / 60)
                    self._offen, self._sauber = False, 0
                    return self._event(f"Kamera {self.kamera}: Bild wieder in Ordnung "
                                       f"(Ausfall ca. {dauer} min).")
        except Exception:  # Watchdog darf die Analyse NIE blockieren
            # Fail-open: Ein gestolperter Watchdog darf die Analyse nicht
            # dauerhaft ausgesetzt lassen – also Zustand zurücksetzen.
            self.ausfaelle += 1
            self.defekt, self.grund, self._offen, self._sauber = False, None, False, 0
            self._letztes, self._gleich, self._streifen = None, 0, 0
            if self.ausfaelle <= 3:
                log.exception("Freeze-Watchdog (%s) gestolpert – Analyse läuft weiter",
                              self.kamera)
        return None

    def _event(self, nachricht: str) -> dict:
        return {"typ": "info", "kuhId": None, "kamera": self.kamera,
                "nachricht": nachricht, "konfidenz": None}


def kennzahlen(frame: np.ndarray, wd: FreezeWatchdog | None = None) -> dict:
    """Kennzahlen eines Bildes für die Streifen-Prüfung – nur Zahlen, kein Bild.

    Damit lässt sich am Hof prüfen, warum ein Nachtbild als „Streifen" gilt,
    ohne dass ein Bild den Hof verlässt (Entscheidung des Landwirts,
    19.10.2026). band_anteil: längstes vertikal flaches Band (Anteil der
    Bildhöhe); spalten_streuung: Unterschied der Spalten in diesem Band
    (Prüfgröße, ab 5 = Streifen); spalten_sprung: mittlerer Sprung von Spalte zu
    Spalte im Band (glatter Verlauf klein, Dekoder-Streifen groß)."""
    wd = wd or FreezeWatchdog("diagnose")
    g = wd._grau(frame)
    flach = np.abs(np.diff(g, axis=0)).mean(axis=1) < wd.streifen_schwelle
    besten, start = (0, 0), None
    for i, f in enumerate(list(flach) + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start > besten[1] - besten[0]:
                besten = (start, i)
            start = None
    a, b = besten
    band = g[a:b + 1] if b > a else g[:0]
    return {
        "band_anteil": round((b - a) / max(1, len(flach)), 3),
        "spalten_streuung": round(float(band.std(axis=1).mean()), 2) if b > a else 0.0,
        "spalten_sprung": round(float(np.abs(np.diff(band, axis=1)).mean()), 2) if b > a else 0.0,
        "helligkeit": round(float(g.mean()), 1),
        "streifen": bool(wd._hat_streifen(g)),
    }


def _diagnose(pfade: list[str]) -> int:
    """CLI: python freeze_watchdog.py diagnose <ordner|bilder…> – Kennzahlen je Bild."""
    import cv2  # nur fuer die Diagnose; der Agent braucht es hier nicht

    from pathlib import Path

    dateien: list[Path] = []
    for p in pfade:
        q = Path(p)
        dateien += sorted(q.glob("*.jpg")) if q.is_dir() else [q]
    print("datei;band_anteil;spalten_streuung;spalten_sprung;helligkeit;streifen")
    treffer = 0
    for d in dateien:
        bild = cv2.imread(str(d))
        if bild is None:
            print(f"{d.name};nicht lesbar")
            continue
        k = kennzahlen(bild)
        treffer += k["streifen"]
        print(f"{d.name};{k['band_anteil']};{k['spalten_streuung']};{k['spalten_sprung']};"
              f"{k['helligkeit']};{'ja' if k['streifen'] else 'nein'}")
    print(f"# {len(dateien)} Bilder, davon {treffer} als Streifen eingestuft")
    return 0


def baue_watchdog(cfg: dict, kamera: str, analyse_aktiv: bool) -> FreezeWatchdog | None:
    """Erzeugt den Watchdog einer Kamera aus der config.yaml (Abschnitt
    ``watchdog``). ``frames_bis_alarm`` leer/ungültig -> Silent Mode 5,
    Analyse-Modus 300. ``watchdog.aktiv: false`` schaltet ihn ab (None)."""
    w = (cfg.get("watchdog") or {}) if isinstance(cfg, dict) else {}
    if w.get("aktiv", True) is False:
        return None
    frames = w.get("frames_bis_alarm")
    if isinstance(frames, bool) or not isinstance(frames, int) or frames < 1:
        frames = FRAMES_ANALYSE if analyse_aktiv else FRAMES_SILENT
    return FreezeWatchdog(kamera, frames_bis_alarm=frames, analyse=analyse_aktiv)


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "diagnose":
        sys.exit(_diagnose(sys.argv[2:]))
    print("Aufruf: python freeze_watchdog.py diagnose <ordner|bilder…>")
    sys.exit(2)
