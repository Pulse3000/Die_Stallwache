#!/usr/bin/env python3
"""Stallblick Edge-Agent: KI-basierte Brunst- & Kalbeerkennung im Stall.

Laeuft lokal auf beliebiger Hardware (alter Laptop/PC reicht – 1 FPS genuegt,
weil sich Kalbeanzeichen ueber Minuten entwickeln). Liest den Kamerastream
der go2rtc-Bridge (RTSP-Restream, Fallback: Snapshot-Polling), analysiert ihn
mit YOLO-Pose + ByteTrack und alarmiert per Telegram; zusaetzlich meldet er
Ereignisse an das Stallblick-Dashboard (KI-Wache) auf Vercel.

Betriebsmodi:
  * Silent Mode (kein Modell konfiguriert): sammelt nur Trainingsbilder.
  * Analyse-Modus (modell.pfad gesetzt): volle Erkennungslogik.

Erkennungslogik (siehe config.yaml):
  1. Kalbeverdacht:  Schwanzwinkel > 45 Grad in > 20 % der Frames eines
     rollierenden 30-Minuten-Fensters (filtert Koten/Fliegenabwehr).
  2. Austreibung:    Fruchtblase (amniotic_sac) oder Kaelberfuesse (calf_legs)
     mit Konfidenz > 0.8 -> Sofort-Alarm, Zeitfilter wird uebersprungen.
  3. Brunstverdacht: Aufsprungverhalten (zwei Kuh-Boxen ueberlappen, eine
     deutlich oberhalb) ueber mehrere Sekunden.

Start:  cp config.example.yaml config.yaml && python3 main.py
"""

from __future__ import annotations

import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import requests
import yaml

log = logging.getLogger("stallblick-agent")


# --------------------------------------------------------------------------
# Konfiguration
# --------------------------------------------------------------------------

def lade_konfig(pfad: str = "config.yaml") -> dict:
    p = Path(pfad)
    if not p.exists():
        raise SystemExit(
            f"{pfad} fehlt – bitte anlegen:  cp config.example.yaml config.yaml"
        )
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------
# Videoquelle: RTSP bevorzugt, Snapshot-Polling als Fallback
# --------------------------------------------------------------------------

class StreamHandler:
    """Liefert Frames mit Ziel-FPS; uebersteht Verbindungsabbrueche."""

    RECONNECT_WARTEZEIT_S = 5
    FEHLER_BIS_FALLBACK = 5

    def __init__(self, cfg: dict):
        self.url: str = cfg["stream"]["url"]
        self.fallback_url: str = cfg["stream"].get("fallback_snapshot_url") or ""
        self.frame_intervall = 1.0 / float(cfg["stream"].get("ziel_fps", 1.0))
        self.cap: cv2.VideoCapture | None = None
        self.fehler_in_folge = 0
        self.nutze_fallback = False
        self._letzter_frame_ts = 0.0

    def _verbinde(self) -> None:
        if self.cap is not None:
            self.cap.release()
        log.info("Verbinde mit Stream: %s", self.url)
        self.cap = cv2.VideoCapture(self.url)
        # Kleiner Puffer -> immer moeglichst aktuelles Bild.
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _frame_rtsp(self) -> np.ndarray | None:
        if self.cap is None or not self.cap.isOpened():
            self._verbinde()
        if self.cap is None or not self.cap.isOpened():
            return None
        ok, frame = self.cap.read()
        return frame if ok else None

    def _frame_snapshot(self) -> np.ndarray | None:
        try:
            r = requests.get(self.fallback_url, timeout=10)
            r.raise_for_status()
            buf = np.frombuffer(r.content, dtype=np.uint8)
            return cv2.imdecode(buf, cv2.IMREAD_COLOR)
        except requests.RequestException as e:
            log.warning("Snapshot-Fallback fehlgeschlagen: %s", e)
            return None

    def naechster_frame(self) -> np.ndarray | None:
        """Blockiert bis zum naechsten Frame gemaess Ziel-FPS (oder None bei Fehler)."""
        wartezeit = self._letzter_frame_ts + self.frame_intervall - time.time()
        if wartezeit > 0:
            time.sleep(wartezeit)
        self._letzter_frame_ts = time.time()

        frame = (
            self._frame_snapshot() if self.nutze_fallback else self._frame_rtsp()
        )
        if frame is None:
            self.fehler_in_folge += 1
            if (
                not self.nutze_fallback
                and self.fallback_url
                and self.fehler_in_folge >= self.FEHLER_BIS_FALLBACK
            ):
                log.warning("RTSP instabil – wechsle auf Snapshot-Polling.")
                self.nutze_fallback = True
            elif not self.nutze_fallback:
                time.sleep(self.RECONNECT_WARTEZEIT_S)
                self._verbinde()
            return None

        if self.fehler_in_folge:
            log.info("Stream wieder stabil.")
        self.fehler_in_folge = 0
        return frame


# --------------------------------------------------------------------------
# KI-Inferenz (YOLO-Pose + ByteTrack) – optional, sonst Silent Mode
# --------------------------------------------------------------------------

@dataclass
class KuhBeobachtung:
    track_id: int
    box: tuple[float, float, float, float]  # x1, y1, x2, y2
    winkel_grad: float | None               # Schwanzwinkel, falls Keypoints ok
    keypoints: np.ndarray | None


@dataclass
class ObjektErkennung:
    klasse: str        # "amniotic_sac" | "calf_legs"
    konfidenz: float
    box: tuple[float, float, float, float]


class InferenceEngine:
    """Kapselt Ultralytics-YOLO; ohne Modellpfad bleibt sie inaktiv."""

    def __init__(self, cfg: dict):
        self.cfg = cfg["modell"]
        self.kp = self.cfg["keypoints"]
        self.klassen = {int(v): k for k, v in self.cfg["klassen"].items()}
        self.modell = None
        pfad = (self.cfg.get("pfad") or "").strip()
        if pfad:
            from ultralytics import YOLO  # Import nur bei Bedarf (Silent Mode braucht es nicht)

            log.info("Lade Modell %s …", pfad)
            self.modell = YOLO(pfad)

    @property
    def aktiv(self) -> bool:
        return self.modell is not None

    def analysiere(
        self, frame: np.ndarray
    ) -> tuple[list[KuhBeobachtung], list[ObjektErkennung]]:
        """Ein Frame -> getrackte Kuehe (mit Schwanzwinkel) + Spezialobjekte."""
        ergebnis = self.modell.track(
            frame, persist=True, tracker="bytetrack.yaml", verbose=False
        )[0]

        kuehe: list[KuhBeobachtung] = []
        objekte: list[ObjektErkennung] = []
        boxen = ergebnis.boxes
        if boxen is None:
            return kuehe, objekte

        kps = getattr(ergebnis, "keypoints", None)
        for i in range(len(boxen)):
            klass_idx = int(boxen.cls[i])
            konf = float(boxen.conf[i])
            box = tuple(float(v) for v in boxen.xyxy[i])
            name = self.klassen.get(klass_idx, f"klasse_{klass_idx}")

            if name in ("amniotic_sac", "calf_legs"):
                objekte.append(ObjektErkennung(name, konf, box))
                continue

            track_id = int(boxen.id[i]) if boxen.id is not None else -1
            punkte = None
            winkel = None
            if kps is not None and i < len(kps.xy):
                punkte = kps.xy[i].cpu().numpy()
                winkel = self._schwanzwinkel(punkte)
            kuehe.append(KuhBeobachtung(track_id, box, winkel, punkte))
        return kuehe, objekte

    def _schwanzwinkel(self, punkte: np.ndarray) -> float | None:
        """Winkel zwischen Rueckenlinie und Schwanz in Grad (0 = anliegend)."""
        try:
            spine = punkte[self.kp["spine_end"]]
            basis = punkte[self.kp["tail_base"]]
            spitze = punkte[self.kp["tail_tip"]]
        except (IndexError, KeyError):
            return None
        if not (np.all(np.isfinite(spine)) and np.all(np.isfinite(basis)) and np.all(np.isfinite(spitze))):
            return None
        ruecken = basis - spine     # Vektor entlang der Rueckenlinie
        schwanz = spitze - basis    # Vektor des Schwanzes
        if np.linalg.norm(ruecken) < 1 or np.linalg.norm(schwanz) < 1:
            return None
        kreuz = ruecken[0] * schwanz[1] - ruecken[1] * schwanz[0]
        punktprod = float(np.dot(ruecken, schwanz))
        return abs(math.degrees(math.atan2(kreuz, punktprod)))


# --------------------------------------------------------------------------
# Entscheidungslogik: Zeitfilter, Override, Brunst-Heuristik
# --------------------------------------------------------------------------

@dataclass
class Alarm:
    typ: str            # kalbeverdacht | austreibung | brunstverdacht
    kuh_id: str | None
    nachricht: str
    konfidenz: float | None
    box: tuple[float, float, float, float] | None


@dataclass
class LogicEngine:
    cfg: dict
    # pro Track-ID: deque von (zeitstempel, winkel_ueber_schwelle)
    puffer: dict[int, deque] = field(default_factory=lambda: defaultdict(deque))
    # laufende Aufsprung-Kandidaten: (id_oben, id_unten) -> startzeit
    brunst_paare: dict[tuple[int, int], float] = field(default_factory=dict)
    # Beginn der Austreibungsphase (erste Fruchtblasen-/Fuesse-Erkennung)
    austreibung_start: float | None = None
    austreibung_zuletzt: float | None = None
    eskaliert: bool = False

    def __post_init__(self):
        lg = self.cfg["logik"]
        self.winkel_schwelle = float(lg["winkel_schwelle_grad"])
        self.fenster_s = float(lg["fenster_minuten"]) * 60
        self.anteil_schwelle = float(lg["anteil_schwelle"])
        self.override_konf = float(lg["override_konfidenz"])
        self.brunst_dauer = float(lg["brunst_min_dauer_s"])
        self.eskalation_s = float(lg.get("eskalation_minuten", 60)) * 60
        self.min_stichprobe = 20  # so viele Frames noetig, bevor der Filter urteilt

    def bewerte(
        self, kuehe: list[KuhBeobachtung], objekte: list[ObjektErkennung]
    ) -> list[Alarm]:
        jetzt = time.time()
        alarme: list[Alarm] = []

        # 1) Harter Override: Fruchtblase / Kaelberfuesse
        for o in objekte:
            if o.konfidenz >= self.override_konf:
                self.austreibung_start = self.austreibung_start or jetzt
                self.austreibung_zuletzt = jetzt
                alarme.append(
                    Alarm(
                        "austreibung",
                        None,
                        f"{'Fruchtblase' if o.klasse == 'amniotic_sac' else 'Kälberfüße'} "
                        f"erkannt (Konfidenz {o.konfidenz:.0%}) – Austreibungsphase!",
                        o.konfidenz,
                        o.box,
                    )
                )
                # Eskalation (Komplikationsverdacht): Austreibung laeuft, aber
                # nach eskalation_minuten sind immer noch Fruchtblase/Fuesse
                # sichtbar -> Geburt macht keinen Fortschritt, Kontrolle noetig.
                if (
                    not self.eskaliert
                    and jetzt - self.austreibung_start >= self.eskalation_s
                ):
                    self.eskaliert = True
                    alarme.append(
                        Alarm(
                            "austreibung",
                            "Eskalation",
                            f"⚠️ KEIN GEBURTSFORTSCHRITT: Austreibungsphase läuft "
                            f"seit {(jetzt - self.austreibung_start) / 60:.0f} Minuten, "
                            f"{'Fruchtblase' if o.klasse == 'amniotic_sac' else 'Kälberfüße'} "
                            "weiterhin sichtbar – bitte sofort kontrollieren!",
                            o.konfidenz,
                            o.box,
                        )
                    )

        # Austreibungs-Episode beenden, wenn 30 min keine Erkennung mehr kam
        # (Geburt abgeschlossen) -> naechste Kalbung startet frisch.
        if (
            self.austreibung_zuletzt is not None
            and jetzt - self.austreibung_zuletzt > 1800
        ):
            self.austreibung_start = None
            self.austreibung_zuletzt = None
            self.eskaliert = False

        # 2) Statistischer Zeitfilter pro Kuh (Schwanzwinkel)
        for kuh in kuehe:
            if kuh.track_id < 0 or kuh.winkel_grad is None:
                continue
            p = self.puffer[kuh.track_id]
            p.append((jetzt, kuh.winkel_grad > self.winkel_schwelle))
            while p and p[0][0] < jetzt - self.fenster_s:
                p.popleft()
            if len(p) >= self.min_stichprobe:
                anteil = sum(1 for _, ueber in p if ueber) / len(p)
                if anteil > self.anteil_schwelle:
                    alarme.append(
                        Alarm(
                            "kalbeverdacht",
                            f"Kuh #{kuh.track_id}",
                            f"Schwanzwinkel > {self.winkel_schwelle:.0f}° in "
                            f"{anteil:.0%} der Frames der letzten "
                            f"{self.fenster_s / 60:.0f} Minuten",
                            None,
                            kuh.box,
                        )
                    )
                    p.clear()  # Fenster neu aufbauen, Cooldown uebernimmt der Notifier

        # 3) Brunst: Aufsprung = zwei Boxen ueberlappen, eine deutlich oberhalb
        alarme.extend(self._brunst(kuehe, jetzt))
        return alarme

    def _brunst(self, kuehe: list[KuhBeobachtung], jetzt: float) -> list[Alarm]:
        alarme: list[Alarm] = []
        aktive: set[tuple[int, int]] = set()
        for a in kuehe:
            for b in kuehe:
                if a.track_id >= b.track_id or a.track_id < 0 or b.track_id < 0:
                    continue
                oben, unten = (a, b) if a.box[1] < b.box[1] else (b, a)
                if self._iou(a.box, b.box) < 0.15:
                    continue
                # "Oben" muss deutlich hoeher ansetzen -> Aufsprung statt Nebeneinander
                if unten.box[1] - oben.box[1] < 0.2 * (unten.box[3] - unten.box[1]):
                    continue
                paar = (oben.track_id, unten.track_id)
                aktive.add(paar)
                start = self.brunst_paare.setdefault(paar, jetzt)
                if jetzt - start >= self.brunst_dauer:
                    alarme.append(
                        Alarm(
                            "brunstverdacht",
                            f"Kuh #{unten.track_id}",
                            f"Aufsprungverhalten erkannt (Kuh #{oben.track_id} auf "
                            f"Kuh #{unten.track_id}, Dauer {jetzt - start:.0f} s) – "
                            "Duldung deutet auf Brunst hin",
                            None,
                            unten.box,
                        )
                    )
                    self.brunst_paare[paar] = jetzt + 3600  # Paar fuer 1 h stumm
        # Beendete Paare vergessen
        for paar in list(self.brunst_paare):
            if paar not in aktive and self.brunst_paare[paar] <= jetzt:
                del self.brunst_paare[paar]
        return alarme

    @staticmethod
    def _iou(a: tuple, b: tuple) -> float:
        x1, y1 = max(a[0], b[0]), max(a[1], b[1])
        x2, y2 = min(a[2], b[2]), min(a[3], b[3])
        schnitt = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        fl_a = (a[2] - a[0]) * (a[3] - a[1])
        fl_b = (b[2] - b[0]) * (b[3] - b[1])
        return schnitt / (fl_a + fl_b - schnitt) if schnitt else 0.0


# --------------------------------------------------------------------------
# Alarmierung: Telegram + Stallblick-Dashboard (Vercel)
# --------------------------------------------------------------------------

class Notifier:
    """Versendet Alarme; Cooldown pro (Kuh, Typ) verhindert Spam."""

    def __init__(self, cfg: dict):
        tg = cfg.get("telegram") or {}
        self.tg_token = (tg.get("token") or "").strip()
        self.tg_chat = str(tg.get("chat_id") or "").strip()
        self.cooldown_s = float(tg.get("cooldown_minuten", 15)) * 60

        db = cfg.get("dashboard") or {}
        self.db_url = (db.get("url") or "").strip()
        self.db_token = (db.get("token") or "").strip()

        self.kamera = cfg["stream"].get("kamera", "stallwache")
        self._zuletzt: dict[tuple[str | None, str], float] = {}

    def melde(self, alarm: Alarm, frame: np.ndarray | None) -> None:
        schluessel = (alarm.kuh_id, alarm.typ)
        jetzt = time.time()
        if jetzt - self._zuletzt.get(schluessel, 0) < self.cooldown_s:
            return
        self._zuletzt[schluessel] = jetzt
        log.warning("ALARM [%s] %s: %s", alarm.typ, alarm.kuh_id or "-", alarm.nachricht)

        bild = self._annotiere(frame, alarm) if frame is not None else None
        self._telegram(alarm, bild)
        self._dashboard(alarm)

    def status(self, nachricht: str) -> None:
        """Info-Meldung nur ans Dashboard (kein Telegram-Weckruf)."""
        log.info(nachricht)
        self._dashboard(Alarm("info", None, nachricht, None, None))

    @staticmethod
    def _annotiere(frame: np.ndarray, alarm: Alarm) -> bytes:
        bild = frame.copy()
        if alarm.box:
            x1, y1, x2, y2 = (int(v) for v in alarm.box)
            cv2.rectangle(bild, (x1, y1), (x2, y2), (0, 0, 255), 3)
            cv2.putText(
                bild,
                f"{alarm.typ}{' ' + alarm.kuh_id if alarm.kuh_id else ''}",
                (x1, max(24, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )
        ok, jpg = cv2.imencode(".jpg", bild, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpg.tobytes() if ok else b""

    def _telegram(self, alarm: Alarm, bild: bytes | None) -> None:
        if not (self.tg_token and self.tg_chat):
            return
        text = f"⚠️ {alarm.typ.upper()}"
        if alarm.kuh_id:
            text += f" – {alarm.kuh_id}"
        text += f"\n{alarm.nachricht}\nKamera: {self.kamera}"
        try:
            if bild:
                requests.post(
                    f"https://api.telegram.org/bot{self.tg_token}/sendPhoto",
                    data={"chat_id": self.tg_chat, "caption": text},
                    files={"photo": ("alarm.jpg", bild, "image/jpeg")},
                    timeout=20,
                ).raise_for_status()
            else:
                requests.post(
                    f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                    data={"chat_id": self.tg_chat, "text": text},
                    timeout=20,
                ).raise_for_status()
        except requests.RequestException as e:
            log.error("Telegram-Versand fehlgeschlagen: %s", e)

    def _dashboard(self, alarm: Alarm) -> None:
        if not (self.db_url and self.db_token):
            return
        try:
            requests.post(
                self.db_url,
                json={
                    "typ": alarm.typ,
                    "kuhId": alarm.kuh_id,
                    "kamera": self.kamera,
                    "nachricht": alarm.nachricht,
                    "konfidenz": alarm.konfidenz,
                },
                headers={"x-ingest-token": self.db_token},
                timeout=15,
            ).raise_for_status()
        except requests.RequestException as e:
            log.error("Dashboard-Meldung fehlgeschlagen: %s", e)


# --------------------------------------------------------------------------
# Hauptschleife
# --------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = lade_konfig()
    stream = StreamHandler(cfg)
    engine = InferenceEngine(cfg)
    logik = LogicEngine(cfg)
    notifier = Notifier(cfg)

    if engine.aktiv:
        notifier.status("Edge-Agent gestartet – Analyse-Modus aktiv")
    else:
        notifier.status("Edge-Agent gestartet (Silent Mode – Datensammlung)")
        ordner = Path(cfg["silent_mode"]["ordner"])
        ordner.mkdir(parents=True, exist_ok=True)
        intervall = float(cfg["silent_mode"]["intervall_sekunden"])
        letzte_aufnahme = 0.0

    while True:
        try:
            frame = stream.naechster_frame()
            if frame is None:
                continue

            if not engine.aktiv:
                # Silent Mode: regelmaessig Trainingsbilder sichern.
                if time.time() - letzte_aufnahme >= intervall:
                    letzte_aufnahme = time.time()
                    name = ordner / f"{time.strftime('%Y%m%d-%H%M%S')}.jpg"
                    cv2.imwrite(str(name), frame)
                    log.info("Trainingsbild gespeichert: %s", name)
                continue

            kuehe, objekte = engine.analysiere(frame)
            for alarm in logik.bewerte(kuehe, objekte):
                notifier.melde(alarm, frame)

        except KeyboardInterrupt:
            log.info("Beendet.")
            return
        except Exception:  # noqa: BLE001 – 24/7-Betrieb darf nie abstuerzen
            log.exception("Unerwarteter Fehler – laufe weiter")
            time.sleep(5)


if __name__ == "__main__":
    main()
