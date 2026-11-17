#!/usr/bin/env python3
"""Stallblick Edge-Agent: KI-basierte Brunst- & Kalbeerkennung im Stall.

Laeuft lokal auf beliebiger Hardware (alter Laptop/PC reicht – 1 FPS genuegt,
weil sich Kalbeanzeichen ueber Minuten entwickeln). Liest den Kamerastream
der go2rtc-Bridge (RTSP-Restream, Fallback: Snapshot-Polling), analysiert ihn
mit YOLOv8-Pose (ONNX Runtime, B19) + ByteTrack und alarmiert per Telegram; zusaetzlich meldet er
Ereignisse an das Stallblick-Dashboard (KI-Wache) auf Vercel.

Betriebsmodi:
  * Silent Mode (kein Modell konfiguriert): sammelt nur Trainingsbilder.
  * Analyse-Modus (modell.pfad = best_vN.onnx): volle Erkennungslogik;
    Defektbilder (Dekodier-Streifen) zaehlen nicht fuers Schwanzwinkel-
    Fenster, die Austreibung wird auf jedem Bild geprueft (B20).

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

import base64
import datetime as dt
import json
import logging
import math
import os
import queue
import re
import threading
import time
import types
import urllib.parse
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

class CloudQuelle:
    """Kamerastream ohne Bridge: kurzlebige Tuya-HLS-URLs ueber die Webapp.

    Fuer Kameras, die bereits in der Tuya-Cloud haengen (Futterwache,
    Stallbox), braucht der Silent Mode keine Bridge: Der Agent meldet sich
    an der Webapp an (STALLBLICK_PASSWORT), holt von /api/<kamera>/stream
    die kurzlebige HLS-URL und extrahiert daraus die originale CDN-URL —
    die Proxy-Umleitung der Webapp ist nur fuer Browser-CORS noetig, der
    Agent liest direkt vom CDN (kein Cookie, kein Umweg ueber Vercel).
    Laeuft die URL ab, holt der Reconnect-Pfad automatisch eine frische.
    """

    def __init__(self, cfg: dict):
        st = cfg.get("stream") or {}
        self.basis = (st.get("app_url") or "").strip().rstrip("/")
        self.pfad = (st.get("quelle_api") or "").strip()
        self.passwort = (st.get("app_passwort") or "").strip()
        self.aktiv = bool(self.basis and self.pfad)
        self._session = None

    def hole_url(self) -> str | None:
        """Liefert eine frische Stream-URL oder None (Fehler sind gekapselt)."""
        if not self.aktiv:
            return None
        for versuch in (1, 2):  # 2. Versuch nach abgelaufener Session
            try:
                if self._session is None:
                    self._session = requests.Session()
                    if self.passwort:
                        self._session.post(
                            f"{self.basis}/api/login",
                            json={"passwort": self.passwort},
                            timeout=15,
                        ).raise_for_status()
                r = self._session.get(f"{self.basis}{self.pfad}", timeout=20)
                if r.status_code == 401 and versuch == 1:
                    self._session = None  # Session abgelaufen -> neu anmelden
                    continue
                r.raise_for_status()
                url = str(r.json().get("url") or "")
                return self._entpacke(url) if url else None
            except requests.RequestException as e:
                log.warning("Cloud-Quelle nicht erreichbar: %s", e)
                self._session = None
                return None
        return None

    def _entpacke(self, url: str) -> str | None:
        """Extrahiert die Original-CDN-URL aus der Proxy-URL der Webapp."""
        anfrage = urllib.parse.urlparse(url).query
        original = (urllib.parse.parse_qs(anfrage).get("url") or [""])[0]
        if original.startswith("https://"):
            return original
        if url.startswith("https://"):
            return url  # API lieferte bereits eine absolute Quelle
        log.warning("Cloud-Quelle lieferte unerwartete URL: %s", url[:80])
        return None


class StreamHandler:
    """Liefert Frames mit Ziel-FPS; uebersteht Verbindungsabbrueche."""

    RECONNECT_WARTEZEIT_S = 5
    FEHLER_BIS_FALLBACK = 5

    def __init__(self, cfg: dict):
        self.url: str = (cfg["stream"].get("url") or "").strip()
        self.quelle = CloudQuelle(cfg)
        if not self.url and not self.quelle.aktiv:
            raise SystemExit(
                "stream.url fehlt – entweder Bridge-URL eintragen oder "
                "Cloud-Quelle konfigurieren (stream.app_url + stream.quelle_api)."
            )
        self.fallback_url: str = cfg["stream"].get("fallback_snapshot_url") or ""
        self.frame_intervall = 1.0 / float(cfg["stream"].get("ziel_fps", 1.0))
        self.cap: cv2.VideoCapture | None = None
        self.fehler_in_folge = 0
        self.nutze_fallback = False
        self._letzter_frame_ts = 0.0

    def _verbinde(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        if self.quelle.aktiv:
            # Kurzlebige Cloud-URL bei jedem (Re-)Connect frisch holen.
            neue = self.quelle.hole_url()
            if neue:
                self.url = neue
            elif not self.url:
                return  # noch keine URL bekannt -> naechste Iteration versucht es erneut
        log.info("Verbinde mit Stream: %s", self.url.split("?")[0])
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


class TotmannWaechter:
    """Stream-Totmann-Meldung: „Das dritte Auge ist blind."

    Meldet genau EINE Nachricht pro Ausfall-Episode, wenn der Stream laenger
    als ``stream.totmann_minuten`` kein Bild liefert, und genau eine
    Entwarnung, sobald er zurueck ist. Ohne diese Meldung wuerde Schweigen
    faelschlich „alles ruhig" bedeuten — fuer eine Nachtwache inakzeptabel.
    Laeuft modellunabhaengig, also auch im Silent Mode. 0 = deaktiviert.
    """

    def __init__(self, cfg: dict, jetzt: float | None = None):
        st = cfg.get("stream") or {}
        self.schwelle_s = float(st.get("totmann_minuten", 5)) * 60
        self.letzter_frame = time.time() if jetzt is None else jetzt
        self.ausfall_start: float | None = None
        self.gemeldet = False
        self.letzte_art: str | None = None  # "meldung" | "entwarnung" (Entwarnung geht still raus)

    def tick(self, frame_ok: bool, jetzt: float | None = None) -> str | None:
        """Pro Hauptschleifen-Iteration aufrufen; liefert die zu sendende
        Nachricht oder None."""
        self.letzte_art = None
        if self.schwelle_s <= 0:
            return None
        t = time.time() if jetzt is None else jetzt

        if frame_ok:
            entwarnung = None
            if self.gemeldet and self.ausfall_start is not None:
                dauer_min = (t - self.ausfall_start) / 60
                entwarnung = (
                    f"Kamerastream wieder da (Ausfall {dauer_min:.0f} min) – "
                    "das dritte Auge sieht wieder."
                )
                self.letzte_art = "entwarnung"
            self.letzter_frame = t
            self.ausfall_start = None
            self.gemeldet = False
            return entwarnung

        if self.ausfall_start is None:
            # Ausfall zaehlt ab dem letzten guten Frame, nicht ab jetzt.
            self.ausfall_start = self.letzter_frame
        if not self.gemeldet and t - self.ausfall_start >= self.schwelle_s:
            self.gemeldet = True
            self.letzte_art = "meldung"
            dauer_min = (t - self.ausfall_start) / 60
            return (
                f"Kamerastream seit {dauer_min:.0f} min ausgefallen – das "
                "dritte Auge ist blind! Bitte Bridge, WLAN und Kamera pruefen."
            )
        return None


class AusfallWaechter:
    """Totmann-Prinzip fuer Teilfunktionen der Analyse (B19/B20).

    Meldung genau EINMAL je Episode, sobald ein ununterbrochener Ausfall
    ``schwelle_s`` dauert (gezaehlt ab dem letzten guten Durchlauf; nach einer
    Luecke ohne Durchlaeufe ab dem ersten schlechten). Entwarnung erst, wenn in
    den letzten ``schwelle_s`` mehr als ``erholung_anteil`` der Durchlaeufe gut
    waren - wie die Erholungsregel des Bildqualitaets-Gates (B20). Ein einzelnes
    gutes Bild beendet die Episode nicht (sonst Meldungs-Pingpong die ganze
    Nacht). 0 = aus. ``letzte_art``: "meldung" | "entwarnung" | None.
    """

    def __init__(self, schwelle_s: float, meldung: str, entwarnung: str,
                 jetzt: float | None = None, erholung_anteil: float = 0.5, **felder):
        self.schwelle_s = schwelle_s
        self.meldung, self.entwarnung, self.felder = meldung, entwarnung, felder
        self.erholung_anteil = erholung_anteil
        self.letzter_ok = time.time() if jetzt is None else jetzt
        self.letzter_tick: float | None = None
        self.ausfall_start: float | None = None
        self.gemeldet = False
        self.letzte_art: str | None = None
        self.kanal = "telegram"  # Kanal der letzten Meldung; die Entwarnung nimmt denselben
        self._verlauf: deque[tuple[float, bool]] = deque()

    def tick(self, ok: bool, jetzt: float | None = None, **felder) -> str | None:
        self.letzte_art = None
        if self.schwelle_s <= 0:
            return None
        t = time.time() if jetzt is None else jetzt
        luecke = self.letzter_tick is not None and t - self.letzter_tick > self.schwelle_s
        self.letzter_tick = t
        if luecke:
            self._verlauf.clear()
        self._verlauf.append((t, ok))
        while self._verlauf and self._verlauf[0][0] <= t - self.schwelle_s:
            self._verlauf.popleft()
        if self.gemeldet:
            if ok:
                self.letzter_ok = t
                gut = sum(1 for _, o in self._verlauf if o) / len(self._verlauf)
                if gut > self.erholung_anteil:
                    text = self.entwarnung.format(minuten=(t - self.ausfall_start) / 60, **self.felder)
                    self.gemeldet, self.ausfall_start, self.letzte_art = False, None, "entwarnung"
                    return text
            return None
        if ok:
            self.letzter_ok, self.ausfall_start = t, None
            return None
        if self.ausfall_start is None:
            self.ausfall_start = t if luecke else self.letzter_ok
        if t - self.ausfall_start >= self.schwelle_s:
            self.gemeldet, self.letzte_art = True, "meldung"
            return self.meldung.format(minuten=(t - self.ausfall_start) / 60, **self.felder, **felder)
        return None


# Meldungen an den Landwirt (Telegram ueber Notifier.wichtig). Wortlaut:
# docs/onnx-laufzeit-spezifikation.md (Vorschlaege des Agenten ki-wache).
TEXT_MODELL_AUS = (
    "🔴 KI-WACHE AUS ({kamera}): Es gibt KEINE Alarme – auch nicht bei Fruchtblase oder "
    "Kälberfüßen. Grund: {grund}. Bis zur Behebung Abkalbekandidatinnen selbst kontrollieren. "
    "Behebung: {schritt} Technik: {technik}"
)
TEXT_TRACKER_AUS = (
    "🟠 KI-WACHE EINGESCHRÄNKT ({kamera}): Fruchtblase und Kälberfüße werden weiter gemeldet. "
    "AUS sind Wehen-Verdacht (Schwanzwinkel) und Brunst, weil die Kuh-Wiedererkennung fehlt. "
    "Ein Alarm kommt erst, wenn Fruchtblase oder Füße zu sehen sind – Abkalbekandidatinnen wie "
    "ohne Vorwarnung kontrollieren. Behebung: Agent-Image prüfen (ultralytics), neu starten. "
    "Technik: {technik}"
)
TEXT_TRACKER_WIEDER = (
    "KI-Wache wieder vollständig ({kamera}): Kuh-Wiedererkennung arbeitet wieder "
    "(nach {minuten:.0f} min)."
)
TEXT_ANALYSE_AUS = (
    "🔴 KI-WACHE AUS ({kamera}): Die Bildauswertung schlägt seit {minuten:.0f} min fehl – es gibt "
    "KEINE Alarme, auch nicht bei Fruchtblase oder Kälberfüßen. Bis zur Behebung "
    "Abkalbekandidatinnen selbst kontrollieren. Behebung: Protokoll prüfen "
    "(docker logs stallblick-agent), Agent neu starten."
)
TEXT_ANALYSE_WIEDER = (
    "KI-Wache wertet wieder aus ({kamera}): Bildauswertung nach {minuten:.0f} min wieder in Ordnung."
)
TEXT_BLIND = (
    "🔴 KI-WACHE BLIND ({kamera}): Seit {minuten:.0f} min nur gestreifte Bilder – Fruchtblase "
    "und Kälberfüße sind so nicht sicher erkennbar. Bitte Abkalbekandidatinnen selbst "
    "kontrollieren und Kamera/WLAN prüfen. Entwarnung kommt automatisch."
)
TEXT_BLIND_WIEDER = "KI-Wache sieht wieder ({kamera}): Bilder nach {minuten:.0f} min wieder ungestört."


def baue_waechter(cfg: dict, jetzt: float | None = None) -> dict:
    """Analyse-, Tracker- und Blind-Waechter. Keine neuen Zahlen: Frist =
    stream.totmann_minuten (wie beim Stream-Ausfall), Erholung =
    qualitaet.degradiert_anteil (wie beim Bildqualitaets-Gate)."""
    st = cfg.get("stream") or {}
    schwelle = float(st.get("totmann_minuten", 5)) * 60
    erholung = float((cfg.get("qualitaet") or {}).get("degradiert_anteil", 0.5))
    kamera = st.get("kamera", "stallwache")
    return {
        name: AusfallWaechter(schwelle, meldung, entwarnung, jetzt, erholung, kamera=kamera)
        for name, meldung, entwarnung in (
            ("analyse", TEXT_ANALYSE_AUS, TEXT_ANALYSE_WIEDER),
            ("tracker", TEXT_TRACKER_AUS, TEXT_TRACKER_WIEDER),
            ("blind", TEXT_BLIND, TEXT_BLIND_WIEDER),
        )
    }


# --------------------------------------------------------------------------
# KI-Inferenz (B19: YOLOv8-Pose als ONNX + ByteTrack) – optional, sonst Silent Mode
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


# Vorverarbeitung und Dekodierung WOERTLICH aus
# aufnahmen/_training_v1/werkzeuge/abnahme_gates.py (OnnxModell, dekodiere_pose):
# Die Abnahme-Gates gelten nur bei identischer Dekodierung (B19). Aenderungen nur
# an beiden Stellen zugleich - tests/test_onnx_adapter.py vergleicht Quelltext
# und Ergebnisse.
AUSTREIBUNG = (1, 2)


def dekodiere_pose(aus, n_kpts, konf, iou_nms, links, oben, r, w, h, mehrfach_klassen=AUSTREIBUNG):
    """Rohausgabe (4 + nc + 3*n_kpts, N) eines YOLOv8-Pose-ONNX -> Liste von Objekten (normierte Koordinaten).
    Scores und Keypoint-Sichtbarkeit sind im Export bereits sigmoid-aktiviert. Klassen in `mehrfach_klassen`
    werden zusätzlich unabhängig vom argmax ausgewertet (Recall der Austreibung vor allem anderen)."""
    import cv2
    import numpy as np
    nc = aus.shape[0] - 4 - 3 * n_kpts
    if nc < 1:
        raise ValueError(f"Modellausgabe {aus.shape} passt nicht zu {n_kpts} Keypoints")
    scores = aus[4:4 + nc]
    argmax = scores.argmax(0)
    kand_anker, kand_cls, kand_conf = [], [], []
    for j in np.where(scores[argmax, np.arange(scores.shape[1])] >= konf)[0]:
        kand_anker.append(int(j)); kand_cls.append(int(argmax[j])); kand_conf.append(float(scores[argmax[j], j]))
    for c in mehrfach_klassen:
        if c < nc:
            for j in np.where((scores[c] >= konf) & (argmax != c))[0]:
                kand_anker.append(int(j)); kand_cls.append(int(c)); kand_conf.append(float(scores[c, j]))
    if not kand_anker:
        return []
    a = np.array(kand_anker)
    cx, cy, bw, bh = aus[0, a], aus[1, a], aus[2, a], aus[3, a]
    x1 = np.clip((cx - bw / 2 - links) / r, 0, w)
    y1 = np.clip((cy - bh / 2 - oben) / r, 0, h)
    x2 = np.clip((cx + bw / 2 - links) / r, 0, w)
    y2 = np.clip((cy + bh / 2 - oben) / r, 0, h)
    boxen = [[float(p), float(q), float(s - p), float(t - q)] for p, q, s, t in zip(x1, y1, x2, y2)]
    keep = cv2.dnn.NMSBoxesBatched(boxen, kand_conf, kand_cls, konf, iou_nms)
    kp_roh = aus[4 + nc:, :]
    ergebnis = []
    for k in np.array(keep).reshape(-1):
        k = int(k)
        j = kand_anker[k]
        kp = [(float((kp_roh[3 * i, j] - links) / r / w), float((kp_roh[3 * i + 1, j] - oben) / r / h),
               float(kp_roh[3 * i + 2, j])) for i in range(n_kpts)]
        ergebnis.append({"cls": kand_cls[k], "conf": kand_conf[k],
                         "xyxy": (float(x1[k] / w), float(y1[k] / h), float(x2[k] / w), float(y2[k] / h)), "kpts": kp})
    return ergebnis


class OnnxModell:
    """YOLOv8-Pose als ONNX (statisch, quadratisch), ONNX Runtime CPU. Vorverarbeitung = Agent auf dem Hof:
    quadratische Letterbox (Rand 114), RGB, /255."""

    def __init__(self, pfad, n_kpts=3, threads=0, konf=0.25, iou_nms=0.7):
        import onnxruntime as ort
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(pfad, so, providers=["CPUExecutionProvider"])
        inp = self.sess.get_inputs()[0]
        self.eingang, self.groesse = inp.name, int(inp.shape[2])
        self.n_kpts, self.konf, self.iou_nms = n_kpts, konf, iou_nms

    def __call__(self, img):
        import cv2
        import numpy as np
        h, w = img.shape[:2]
        s = self.groesse
        r = min(s / h, s / w)
        nh, nw = int(round(h * r)), int(round(w * r))
        oben, links = (s - nh) // 2, (s - nw) // 2
        lw = np.full((s, s, 3), 114, np.uint8)
        lw[oben:oben + nh, links:links + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x = np.ascontiguousarray(lw[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0)
        aus = self.sess.run(None, {self.eingang: x})[0][0]
        return dekodiere_pose(aus, self.n_kpts, self.konf, self.iou_nms, links, oben, r, w, h)


def verfuegbare_kerne(cgroup: str = "/sys/fs/cgroup", proc_cgroup: str = "/proc/self/cgroup") -> int:
    """Kerne, die dieser Prozess wirklich bekommt: CPU-Affinitaet und
    cgroup-Quote (Docker ``cpus: 1`` -> 1, systemd ``CPUQuota=100%`` -> 1).
    Im Container saehe ONNX Runtime sonst alle Kerne des Rechners und startete
    mehr Threads, als die Quote hergibt - das drosselt, statt zu beschleunigen.
    Bruchteile werden abgerundet (``cpus: 1.5`` -> 1, Hitzeschutz der alten APU)."""
    try:
        n = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        n = os.cpu_count() or 1
    wurzel = Path(cgroup)
    orte = [wurzel]
    try:  # cgroup v2: eigene Gruppe, z. B. "0::/system.slice/stallblick-agent.service"
        for zeile in Path(proc_cgroup).read_text(encoding="ascii").splitlines():
            if zeile.startswith("0::") and zeile[3:].strip().strip("/"):
                orte.insert(0, wurzel / zeile[3:].strip().strip("/"))
    except OSError:
        pass
    quoten = []
    for ort in orte:  # cgroup v2: "<quota|max> <period>"
        try:
            teile = (ort / "cpu.max").read_text(encoding="ascii").split()
            if teile[0] != "max":
                quoten.append(int(teile[0]) / int(teile[1]))
        except (OSError, ValueError, IndexError, ZeroDivisionError):
            continue
    if not quoten:
        for unter in ("cpu", "cpu,cpuacct"):  # cgroup v1
            try:
                q = int((wurzel / unter / "cpu.cfs_quota_us").read_text(encoding="ascii"))
                periode = int((wurzel / unter / "cpu.cfs_period_us").read_text(encoding="ascii"))
            except (OSError, ValueError):
                continue
            if q > 0 and periode > 0:
                quoten.append(q / periode)
            break
    if quoten:
        n = min(n, max(1, int(min(quoten))))
    return max(1, n)


class KuhTracker:
    """ByteTrack (Ultralytics ``BYTETracker``) nur fuer die Klasse kuh (B19).

    Rein gehen Pixel-xyxy + Konfidenz der Kuh-Detektionen, raus kommt je
    Detektion die Track-ID (-1, solange der Track nicht bestaetigt ist).
    Fruchtblase und Kaelberfuesse laufen nie hier durch: Mehrfach-Label-Boxen
    wuerden Phantom-IDs und Klassenwechsel erzeugen. Wie Ultralytics 8.3
    ``model.track``: frame_rate 30, d. h. ``track_buffer`` zaehlt Bilder (bei
    1 FPS Sekunden, siehe tracker-kuh.yaml).
    """

    def __init__(self, tracker_yaml: str):
        # Import nur im Analyse-Modus; braucht keine Faltung (B19).
        from ultralytics.engine.results import Boxes
        from ultralytics.trackers.byte_tracker import BYTETracker

        try:
            from ultralytics.utils import IterableSimpleNamespace as Namensraum
        except ImportError:  # aeltere/neuere Ultralytics: Attributzugriff reicht
            Namensraum = types.SimpleNamespace

        pfad = self._finde(tracker_yaml)
        with open(pfad, encoding="utf-8") as f:
            werte = yaml.safe_load(f) or {}
        typ = werte.get("tracker_type", "bytetrack")
        if typ != "bytetrack":
            raise ValueError(f"tracker_type {typ!r} wird nicht unterstuetzt (nur bytetrack)")
        self.pfad = str(pfad)
        self._boxes = Boxes
        args = Namensraum(**werte)
        # 8.3 (Agent-Image): BYTETracker(args, frame_rate) mit
        # max_time_lost = frame_rate / 30 * track_buffer; 8.4: BYTETracker(args)
        # mit max_frames_lost = track_buffer. Beide: 90 Bilder bei track_buffer 90.
        import inspect

        if "frame_rate" in inspect.signature(BYTETracker.__init__).parameters:
            self._tracker = BYTETracker(args=args, frame_rate=30)
        else:
            self._tracker = BYTETracker(args=args)

    @property
    def gedaechtnis(self) -> int | None:
        """Wie viele Bilder ein verlorener Track ueberlebt (versionsunabhaengig)."""
        for name in ("max_time_lost", "max_frames_lost"):
            if hasattr(self._tracker, name):
                return int(getattr(self._tracker, name))
        return None

    @staticmethod
    def _finde(name: str) -> Path:
        for kandidat in (Path(name), Path(__file__).resolve().parent / name):
            if kandidat.is_file():
                return kandidat
        from ultralytics.utils.checks import check_yaml  # mitgelieferte bytetrack.yaml

        return Path(check_yaml(name))

    def update(self, boxen: list, konfidenzen: list, bildform: tuple) -> list[int]:
        """boxen: [(x1, y1, x2, y2)] in Pixeln, bildform: (h, w). Liefert je
        Detektion die Track-ID oder -1."""
        ids = [-1] * len(boxen)
        if not boxen:
            return ids
        daten = np.array([[*b, c, 0.0] for b, c in zip(boxen, konfidenzen)], dtype=np.float32)
        spuren = np.asarray(self._tracker.update(self._boxes(daten, tuple(bildform[:2]))))
        if spuren.size:
            # Zeilen [x1, y1, x2, y2, track_id, score, cls, idx]; idx zeigt
            # auf die Eingabe-Detektion (auch in Ultralytics 8.4 so).
            for zeile in spuren.reshape(-1, spuren.shape[-1]):
                idx = int(zeile[-1])
                if 0 <= idx < len(ids):
                    ids[idx] = int(zeile[4])
        return ids


class InferenceEngine:
    """YOLOv8-Pose als ONNX (B19); ohne Modellpfad bleibt sie inaktiv (Silent Mode).

    ONNX Runtime auf der CPU mit Vorverarbeitung und Dekodierung der
    Abnahme-Gates (``OnnxModell``). Fruchtblase und Kaelberfuesse gehen aus
    JEDEM Bild ungetrackt an die Austreibungslogik - auch aus Defektbildern
    und wenn der Tracker fehlt. ByteTrack bekommt nur Kuh-Boxen.

    Zwei Schwellen: Die Logik (Schwanzwinkel, Brunst, Austreibung) sieht nur
    Objekte ab ``konfidenz_min`` (0.25, wie die Gates). ByteTrack bekommt
    Kuh-Boxen schon ab ``tracker_konfidenz_min`` (0.10, wie Ultralytics
    ``model.track``), damit seine zweite Stufe nachts schwach erkannte Kuehe
    haelt - jede neue ID startet das 30-min-Fenster neu. Dekodierung ab 0.10
    plus Filter >= 0.25 ergibt exakt die Objekte der Dekodierung ab 0.25 (NMS
    haengt nur von hoeher bewerteten Boxen ab; tests/test_onnx_adapter.py).

    Ladefehler stoppen den Agenten nicht: Er bleibt im Silent Mode, ``fehler``
    (Technik), ``fehler_grund`` und ``fehler_schritt`` (fuer den Landwirt)
    nennen den Grund; main() meldet ihn per Telegram.
    """

    def __init__(self, cfg: dict, tracker="auto", modell=None):
        self.cfg = cfg["modell"]
        self.kp = self.cfg["keypoints"]
        self.klassen = {int(v): k for k, v in self.cfg["klassen"].items()}
        # Eigene Tracker-Konfiguration (z. B. tracker-kuh.yaml mit grossem
        # track_buffer fuer 1 FPS); leer -> Ultralytics-Default.
        self.tracker = (self.cfg.get("tracker") or "").strip() or "bytetrack.yaml"
        self.konf = float(self.cfg.get("konfidenz_min", 0.25))
        self.tracker_konf = min(self.konf, float(self.cfg.get("tracker_konfidenz_min", 0.10)))
        self.iou_nms = float(self.cfg.get("nms_iou", 0.7))
        self.sichtbar_min = float(self.cfg.get("keypoint_sichtbar_min", 0.5))
        kl = self.cfg["klassen"]
        self.kuh_klasse = int(kl.get("kuh", 0))
        self.austreibung = {int(kl[n]) for n in ("amniotic_sac", "calf_legs") if n in kl}
        automatisch = isinstance(tracker, str) and tracker == "auto"
        self.kuh_tracker = None if automatisch else tracker
        self.modell = modell
        self.threads = 0
        self.fehler: str | None = None            # Modell nicht geladen -> Silent Mode
        self.fehler_grund: str | None = None
        self.fehler_schritt: str | None = None
        self.tracker_fehler: str | None = None    # Tracker beim Start nicht ladbar
        self.tracker_ok: bool | None = None       # letzter Tracker-Schritt: None = nicht aufgerufen
        self.tracker_laufzeitfehler: str | None = None
        self.beobachtungen = 0                    # Kuh-Beobachtungen auf intakten Bildern
        self.messbar = 0                          # davon mit Schwanzwinkel (Tagesbericht)
        pfad = (self.cfg.get("pfad") or "").strip()
        if pfad and self.modell is None:
            self._lade(pfad)
        if self.modell is not None and automatisch:
            try:
                self.kuh_tracker = KuhTracker(self.tracker)
                log.info("ByteTrack nur fuer Kuehe: %s", self.kuh_tracker.pfad)
            except Exception as e:  # noqa: BLE001 - ohne Tracker bleibt die Austreibung aktiv
                self.tracker_fehler = f"{type(e).__name__}: {e}"
                log.error(
                    "ByteTrack nicht verfuegbar (%s) – keine Kuh-IDs, Austreibung bleibt aktiv.",
                    self.tracker_fehler,
                )

    def _fehlschlag(self, technik: str, grund: str, schritt: str) -> None:
        self.fehler, self.fehler_grund, self.fehler_schritt = technik, grund, schritt
        log.error("Modell nicht geladen: %s", technik)

    def _lade(self, pfad: str) -> None:
        if not pfad.lower().endswith(".onnx"):
            return self._fehlschlag(
                f"modell.pfad {pfad!r} ist keine .onnx-Datei (B19: PyTorch bricht auf diesem "
                "Rechner bei jeder Faltung ab, die Abnahme-Gates gelten nur fuer die ONNX-Dekodierung)",
                "Modelldatei ist kein ONNX (.pt o. ä.), dieser Rechner braucht .onnx",
                "In config.yaml modell.pfad auf modelle/best_vN.onnx setzen, Agent neu starten.",
            )
        if not Path(pfad).is_file():
            return self._fehlschlag(
                f"Datei {pfad} fehlt",
                f"Modelldatei {pfad} nicht gefunden",
                "Datei nach edge-agent/modelle kopieren oder Pfad korrigieren, Agent neu starten.",
            )
        allgemein = (
            "Modell lässt sich nicht laden oder ausführen",
            "Protokoll prüfen (docker logs stallblick-agent), Agent neu starten.",
        )
        try:
            n = int(self.cfg.get("threads") or 0) or verfuegbare_kerne()
            log.info("Lade Modell %s (ONNX Runtime, %d Thread(s), Tracker: %s) …", pfad, n, self.tracker)
            modell = OnnxModell(
                pfad, n_kpts=len(self.kp), threads=n, konf=self.tracker_konf, iou_nms=self.iou_nms
            )
            form = list(modell.sess.get_outputs()[0].shape)
        except Exception as e:  # noqa: BLE001 - kaputtes Modell darf den Agenten nicht stoppen
            return self._fehlschlag(f"Modell {pfad} nicht ladbar ({type(e).__name__}: {e})", *allgemein)
        soll = 4 + len(self.klassen) + 3 * len(self.kp)
        if len(form) == 3 and isinstance(form[1], int) and form[1] != soll:
            return self._fehlschlag(
                f"Modellausgabe {form} passt nicht zum Label-Vertrag ({len(self.klassen)} Klassen, "
                f"{len(self.kp)} Keypoints -> {soll} Zeilen)",
                "Modell passt nicht zu Klassen/Keypoints der Konfiguration",
                "Das richtige best_vN.onnx aus dem Training eintragen, Agent neu starten.",
            )
        try:
            # Probe-Inferenz: Eingangsform, Datentyp und Laufzeit muessen VOR dem
            # ersten echten Bild stimmen - sonst waere die Austreibung blind,
            # waehrend Totmann und Dashboard Normalbetrieb zeigen.
            modell(np.full((360, 640, 3), 114, np.uint8))
        except Exception as e:  # noqa: BLE001
            return self._fehlschlag(
                f"Modell {pfad} laedt, laeuft aber nicht ({type(e).__name__}: {e})", *allgemein
            )
        self.modell, self.threads = modell, n

    @property
    def aktiv(self) -> bool:
        return self.modell is not None

    def modus_text(self, waechter: dict | None = None) -> str:
        """Betriebsmodus fuer den Tagesbericht - nie wie Normalbetrieb, wenn er
        keiner ist (auch nicht bei laufenden Ausfall-Episoden der Waechter)."""
        if self.fehler:
            return "KI-Wache AUS – Modell nicht geladen (nur Bildersammlung)"
        if not self.aktiv:
            return "Datensammlung – noch kein Modell, keine Alarme"
        w = waechter or {}
        if "analyse" in w and w["analyse"].gemeldet:
            return "KI-Wache AUS – Bildauswertung schlägt fehl"
        if "blind" in w and w["blind"].gemeldet:
            return "blind – nur gestreifte Bilder, Fruchtblase/Kälberfüße nicht sicher erkennbar"
        if self.kuh_tracker is None or ("tracker" in w and w["tracker"].gemeldet):
            return "eingeschränkt – nur Fruchtblase/Kälberfüße"
        return "Analyse"

    def tagesbericht(self) -> str | None:
        """Anteil der Kuh-Beobachtungen mit messbarem Schwanzwinkel (B19:
        unsichtbare Punkte ergeben keinen Winkel - faellt der Anteil, fehlt
        dem 30-min-Fenster Evidenz). Setzt die Zaehler zurueck."""
        if not self.beobachtungen:
            return None
        zeile = (
            f"Schwanzwinkel messbar: {self.messbar / self.beobachtungen * 100:.0f} % der "
            f"Kuh-Beobachtungen ({self.messbar} von {self.beobachtungen})"
        )
        self.beobachtungen = self.messbar = 0
        return zeile

    def analysiere(
        self, frame: np.ndarray, defekt: bool = False
    ) -> tuple[list[KuhBeobachtung], list[ObjektErkennung]]:
        """Ein Frame -> Kuehe (Track-ID, Schwanzwinkel) + Austreibungsobjekte.

        defekt (B20): Defektbild schreibt den Tracker nicht fort (verschmierte
        Boxen wuerden IDs verschieben); die Austreibungsobjekte kommen trotzdem.
        """
        h, w = frame.shape[:2]
        objekte: list[ObjektErkennung] = []
        boxen, konfidenzen, punkte_liste = [], [], []
        for o in self.modell(frame):
            x1, y1, x2, y2 = o["xyxy"]
            box = (x1 * w, y1 * h, x2 * w, y2 * h)
            if o["cls"] in self.austreibung:
                if o["conf"] >= self.konf:  # Logik ab Gate-Schwelle (wie abnahme_gates)
                    objekte.append(ObjektErkennung(self.klassen[o["cls"]], o["conf"], box))
            elif o["cls"] == self.kuh_klasse:
                boxen.append(box)
                konfidenzen.append(o["conf"])
                # Unsichtbare Punkte (Sichtbarkeit < Schwelle) -> NaN -> kein Winkel.
                punkte_liste.append(np.array(
                    [[x * w, y * h] if v >= self.sichtbar_min else [np.nan, np.nan]
                     for x, y, v in o["kpts"]],
                    dtype=np.float64,
                ))
        ids = [-1] * len(boxen)
        self.tracker_ok = None  # Defektbild/keine Kuh: kein Beleg fuer oder gegen den Tracker
        if boxen and not defekt and self.kuh_tracker is not None:
            try:
                ids = self.kuh_tracker.update(boxen, konfidenzen, (h, w))
                self.tracker_ok = True
            except Exception as e:  # noqa: BLE001 - Tracker-Fehler kostet nie die Austreibung
                self.tracker_ok = False
                self.tracker_laufzeitfehler = f"{type(e).__name__}: {e}"
                log.exception("ByteTrack-Fehler – Bild ohne Kuh-IDs ausgewertet")
        kuehe = [
            KuhBeobachtung(tid, box, self._schwanzwinkel(punkte), punkte)
            for tid, box, punkte, c in zip(ids, boxen, punkte_liste, konfidenzen)
            if c >= self.konf  # Kuehe 0.10-0.25 nur fuer den Tracker
        ]
        if not defekt:
            self.beobachtungen += len(kuehe)
            self.messbar += sum(k.winkel_grad is not None for k in kuehe)
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
    # letztes auswertbares Bild fuer die Brunst (Ueberbrueckung von Luecken)
    brunst_zuletzt: float | None = None
    # Zeitpunkt des vorigen Bildes (Uhr der Austreibungs-Episode auf Defektbildern)
    letztes_bild: float | None = None

    def __post_init__(self):
        lg = self.cfg["logik"]
        self.winkel_schwelle = float(lg["winkel_schwelle_grad"])
        self.fenster_s = float(lg["fenster_minuten"]) * 60
        self.anteil_schwelle = float(lg["anteil_schwelle"])
        self.override_konf = float(lg["override_konfidenz"])
        self.brunst_dauer = float(lg["brunst_min_dauer_s"])
        self.eskalation_s = float(lg.get("eskalation_minuten", 60)) * 60
        self.ziel_fps = max(1e-6, float((self.cfg.get("stream") or {}).get("ziel_fps", 1.0)))
        self.min_stichprobe = 20  # so viele Frames noetig, bevor der Filter urteilt
        # Wach-Modus (kurz vor Kalbetermin): empfindlichere Schwellen nur dann,
        # wenn der Landwirt ihn bewusst scharfschaltet.
        if lg.get("wach_modus"):
            self.anteil_schwelle *= 0.5
            self.brunst_dauer = max(2.0, self.brunst_dauer * 0.5)
            self.min_stichprobe = 10
            log.info("Wach-Modus aktiv: gesenkte Alarm-Schwellen.")

    def bewerte(
        self,
        kuehe: list[KuhBeobachtung],
        objekte: list[ObjektErkennung],
        defekt: bool = False,
        jetzt: float | None = None,
    ) -> list[Alarm]:
        """defekt (B20): Ein Defektbild liefert keine Kuh-Information - kein
        Beitrag zum Schwanzwinkel-Fenster, Aufsprung-Paare eingefroren.
        Austreibung und Eskalation werden IMMER ausgewertet."""
        jetzt = time.time() if jetzt is None else jetzt
        alarme: list[Alarm] = []
        abstand = 0.0 if self.letztes_bild is None else max(0.0, jetzt - self.letztes_bild)
        self.letztes_bild = jetzt
        # Hoechstens 2 Bildabstaende: Ein Stream-Ausfall vor dem Defektbild ist
        # keine "Defekt-Zeit" (den Ausfall meldet der Totmann); die 30-min-Frist
        # laeuft danach wie bisher, gleich ob das erste Bild gestreift ist.
        abstand = min(abstand, 2.0 / self.ziel_fps)

        # B20: Ein Defektbild ist kein Beleg fuer "nichts mehr zu sehen". Die Uhr
        # der Austreibungs-Episode haelt fuer seine Zeit an - nur intakte Minuten
        # zaehlen fuer die 30-min-Frist (sonst kaeme die Eskalation nach einer
        # Streifen-Phase zu spaet). Anhalten, nicht neu starten: sonst endete die
        # Episode nachts nie und eine zweite Kalbung bekaeme eine falsche oder gar
        # keine Eskalation (Befund qa-waechter/ki-wache 10.11.).
        if defekt and self.austreibung_zuletzt is not None:
            self.austreibung_zuletzt = min(jetzt, self.austreibung_zuletzt + abstand)

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
                        f"erkannt (Konfidenz {o.konfidenz:.0%}) – Austreibungsphase!"
                        # B20: unterdrueckt nichts, hilft nur bei der Bildpruefung
                        + (" Bild gestreift – bitte Bildserie prüfen." if defekt else ""),
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

        # 2) Statistischer Zeitfilter pro Kuh (Schwanzwinkel). Defektbilder
        #    zaehlen nicht (B20): verschmierte Bereiche ergaeben falsche Winkel.
        for kuh in ([] if defekt else kuehe):
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

        # 3) Brunst: Aufsprung = zwei Boxen ueberlappen, eine deutlich oberhalb.
        #    Defektbild (B20): Paare weder fortschreiben noch zuruecksetzen.
        if not defekt:
            # Luecke ohne auswertbares Bild (Defektbilder, Stream-Ausfall,
            # Auswertefehler) hoechstens brunst_min_dauer_s ueberbruecken, sonst
            # laufende Messungen beenden ("Aufsprung 601 s" aus zwei Einzelbildern).
            if self.brunst_zuletzt is not None and jetzt - self.brunst_zuletzt > self.brunst_dauer:
                self.brunst_paare = {p: t for p, t in self.brunst_paare.items() if t > jetzt}
            self.brunst_zuletzt = jetzt
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
# Bildqualitaets-Gate (B20): Dekodier-Streifen nach Paketverlust
# --------------------------------------------------------------------------

# defekt_anteil WOERTLICH aus aufnahmen/_training_v1/werkzeuge/bildqualitaet.py
# (dort an 36 Stichproben kalibriert); Waechtertest: tests/test_qualitaet_bild.py.
ZELLE = 40


def defekt_anteil(bild):
    """bild: BGR- oder Graustufenbild beliebiger Größe. Rückgabe: Anteil verschmierter Zellen (0..1)."""
    if bild.ndim == 3:
        bild = cv2.cvtColor(bild, cv2.COLOR_BGR2GRAY)
    if bild.shape[1] != 640:
        bild = cv2.resize(bild, (640, int(round(bild.shape[0] * 640 / bild.shape[1]))), interpolation=cv2.INTER_AREA)
    g = bild.astype(np.float32)
    h_, w_ = g.shape
    vd = np.abs(np.diff(g, axis=0))[:, :-1]
    hd = np.abs(np.diff(g, axis=1))[:-1, :]
    ny, nx = (h_ - 1) // ZELLE, (w_ - 1) // ZELLE
    if ny == 0 or nx == 0:
        return 0.0
    v = vd[:ny * ZELLE, :nx * ZELLE].reshape(ny, ZELLE, nx, ZELLE).mean((1, 3))
    h = hd[:ny * ZELLE, :nx * ZELLE].reshape(ny, ZELLE, nx, ZELLE).mean((1, 3))
    return float(((v / (h + 0.5) < 0.35) & (h > 0.8)).mean())


class BildQualitaet:
    """Bildqualitaets-Gate (B20).

    Ein Defektbild (defekt_anteil > schwelle_defekt) zaehlt nicht fuer das
    Schwanzwinkel-Fenster; die Austreibungs-Erkennung laeuft auf ihm weiter,
    kein Bild wird fuer die Austreibung verworfen. Sind ueber ``fenster_min``
    mehr als ``degradiert_anteil`` der Bilder defekt, liefert ``zaehle`` genau
    EINE Info-Meldung je Episode (Dashboard + MQTT + Tagesbericht, kein
    Telegram-Weckruf, B12). Bewertet wird erst bei vollem Fenster; die Episode
    endet nach ``fenster_min`` ununterbrochen darunter. Eine Bildluecke laenger
    als das Fenster (Stream-Ausfall, meldet der Totmann) fuellt es neu.
    """

    def __init__(self, cfg: dict):
        q = cfg.get("qualitaet") or {}
        self.schwelle = float(q.get("schwelle_defekt", 0.04))
        self.degradiert_anteil = float(q.get("degradiert_anteil", 0.5))
        self.fenster_s = float(q.get("fenster_min", 10)) * 60
        self.kamera = (cfg.get("stream") or {}).get("kamera", "stallwache")
        self._fenster: deque[tuple[float, bool]] = deque()
        self._defekte_im_fenster = 0
        self._seit: float | None = None      # Beginn der laufenden Beobachtung
        self._zuletzt: float | None = None
        self._darunter_seit: float | None = None
        self.degradiert = False
        # Zaehler fuer den Tagesbericht (werden dort zurueckgesetzt)
        self.bilder = 0
        self.defekte = 0
        self.episoden = 0

    def pruefe(self, frame: np.ndarray) -> tuple[bool, float]:
        """(defekt, defekt_anteil) fuer ein BGR-Bild."""
        anteil = defekt_anteil(frame)
        return anteil > self.schwelle, anteil

    def zaehle(self, defekt: bool, jetzt: float | None = None) -> str | None:
        """Pro ausgewertetem Bild aufrufen; liefert die Info-Meldung (1x je
        Episode) oder None."""
        t = time.time() if jetzt is None else jetzt
        if self._zuletzt is not None and t - self._zuletzt > self.fenster_s:
            self._fenster.clear()
            self._defekte_im_fenster = 0
            self._seit = None
        self._zuletzt = t
        if self._seit is None:
            self._seit = t
        self._fenster.append((t, defekt))
        self._defekte_im_fenster += int(defekt)
        self.bilder += 1
        self.defekte += int(defekt)
        while self._fenster and self._fenster[0][0] <= t - self.fenster_s:
            self._defekte_im_fenster -= int(self._fenster.popleft()[1])
        if t - self._seit < self.fenster_s:
            return None  # Fenster noch nicht voll
        anteil = self._defekte_im_fenster / len(self._fenster)
        if anteil > self.degradiert_anteil:
            self._darunter_seit = None
            if not self.degradiert:
                self.degradiert = True
                self.episoden += 1
                return (
                    f"Bildstörungen ({self.kamera}): {anteil * 100:.0f} % der Bilder der letzten "
                    f"{self.fenster_s / 60:.0f} min gestreift. Fruchtblase/Kälberfüße: Jedes Bild "
                    "wird weiter geprüft, gestreifte Bildteile sind aber nicht auswertbar. "
                    "Wehen-Verdacht nur aus ungestörten Bildern. Bitte Livebild und Stall-WLAN prüfen."
                )
        elif self.degradiert:
            if self._darunter_seit is None:
                self._darunter_seit = t
            elif t - self._darunter_seit >= self.fenster_s:
                self.degradiert = False
                self._darunter_seit = None
        return None

    def tagesbericht(self) -> str | None:
        """Zeile fuer den Tagesbericht; setzt die Zaehler zurueck."""
        if not self.bilder:
            return None
        zeile = (
            f"Bildstörungen: {self.defekte / self.bilder * 100:.0f} % der Bilder "
            f"({self.defekte} von {self.bilder})"
        )
        if self.episoden:
            zeile += f" · Phasen über {self.degradiert_anteil * 100:.0f} %: {self.episoden}×"
        if self.degradiert:
            zeile += " (hält an)"
        self.bilder = self.defekte = self.episoden = 0
        return zeile


# --------------------------------------------------------------------------
# Datensatz-Archiv: Zweitkopie der Trainingsbilder in der Cloud
# --------------------------------------------------------------------------

class DatensatzArchiv:
    """Spiegelt Trainings- und Fehlalarmbilder in Google Cloud Storage.

    Das Problem: Silent-Mode-Aufnahmen und die per Feedback markierten Hard
    Negatives liegen ausschliesslich auf der Platte des Stallrechners — meist
    ein ausgemusterter Laptop ohne Backup. Geht sie kaputt, ist die gesamte
    Datengrundlage des eigenen Modells verloren, oft die Sammelarbeit mehrerer
    Wochen. Diese Klasse legt eine zweite Kopie ueber die Webapp ab
    (``POST /api/datensatz`` -> GCS); GCP-Zugangsdaten bleiben in Vercel, der
    Agent nutzt nur seinen ohnehin vorhandenen Ingest-Token.

    Der Upload laeuft in einem Hintergrund-Thread mit begrenzter Warteschlange.
    Das ist kein Selbstzweck: Ein blockierender POST (30 s Timeout bei zickigem
    Stall-WLAN) wuerde die 1-FPS-Analyseschleife anhalten — und damit im
    schlimmsten Fall eine Austreibung verpassen. Die Schleife darf niemals auf
    das Netz warten. Laeuft die Warteschlange voll, werden Bilder verworfen
    statt gestaut: Die lokale Kopie existiert ohnehin, das Archiv ist die
    Zweitkopie und nie der einzige Ablageort.
    """

    WARTESCHLANGE_MAX = 32
    TIMEOUT_S = 30

    def __init__(self, cfg: dict):
        db = cfg.get("dashboard") or {}
        self.token = (db.get("token") or "").strip()
        url = (db.get("archiv_url") or "").strip()
        if not url:
            # Bequemer Default: dieselbe App, anderer Pfad.
            basis = (db.get("url") or "").strip()
            url = basis.replace("/api/events", "/api/datensatz") if basis else ""
        self.url = url
        self.aktiv = bool(db.get("archiv", False)) and bool(self.url and self.token)
        self.kamera = (cfg.get("stream") or {}).get("kamera", "stallwache")
        self._queue: "queue.Queue[tuple[str, list[bytes]]]" = queue.Queue(
            maxsize=self.WARTESCHLANGE_MAX
        )
        self._verworfen = 0
        if self.aktiv:
            threading.Thread(target=self._arbeite, daemon=True).start()
            log.info("Datensatz-Archiv aktiv: %s", self.url)

    def sichere(self, art: str, bilder: list[bytes]) -> None:
        """Reiht Bilder zum Upload ein. Kehrt sofort zurueck (nie blockierend)."""
        if not (self.aktiv and bilder):
            return
        try:
            self._queue.put_nowait((art, bilder))
        except queue.Full:
            self._verworfen += 1
            log.warning(
                "Datensatz-Archiv ueberlastet – Bild nur lokal gespeichert "
                "(%d verworfen)",
                self._verworfen,
            )

    def _arbeite(self) -> None:
        while True:
            art, bilder = self._queue.get()
            try:
                requests.post(
                    self.url,
                    json={
                        "art": art,
                        "kamera": self.kamera,
                        "bilder": [
                            base64.b64encode(b).decode("ascii") for b in bilder
                        ],
                    },
                    headers={"x-ingest-token": self.token},
                    timeout=self.TIMEOUT_S,
                ).raise_for_status()
            except requests.RequestException as e:
                # Kein Wiederholungsversuch: Die lokale Kopie ist die
                # massgebliche: das Archiv darf nie zum Stau werden.
                log.error("Datensatz-Archiv nicht erreichbar: %s", e)
            except Exception:  # noqa: BLE001 – der Worker darf nie sterben
                log.exception("Datensatz-Archiv: unerwarteter Fehler")
            finally:
                self._queue.task_done()


# --------------------------------------------------------------------------
# Alarmierung: Telegram + Stallblick-Dashboard (Vercel)
# --------------------------------------------------------------------------

class FeedbackSchleife:
    """Ein-Tipp-Feedback: Inline-Buttons „Treffer/Fehlalarm" unter jedem Alarm.

    Kein Wettbewerber laesst den Landwirt das Modell verbessern — Stallblick
    besitzt als einziges System die offene Kette Kamera -> Modell -> Training.
    Ein Tipp auf „Fehlalarm" legt die UNANNOTIERTE Bildserie des Alarms als
    Hard Negatives in ``telegram.fehlalarm_ordner`` ab (fuers Nachtraining,
    Skill fehlalarm-triage); die Urteile erscheinen im Tagesbericht.
    Telegram-Ausfaelle duerfen die Analyse nie blockieren.
    """

    MAX_OFFEN = 20         # nur die juengsten Alarme bleiben abstimmbar (RAM)
    POLL_INTERVALL_S = 10  # getUpdates-Kurz-Poll; blockiert die 1-FPS-Schleife nicht

    def __init__(self, cfg: dict):
        tg = cfg.get("telegram") or {}
        self.token = (tg.get("token") or "").strip()
        self.chat = str(tg.get("chat_id") or "").strip()
        self.aktiv = bool(tg.get("feedback_buttons", True)) and bool(
            self.token and self.chat
        )
        self.ordner = Path(tg.get("fehlalarm_ordner") or "./aufnahmen/fehlalarme")
        self.zaehler: dict[str, int] = {"treffer": 0, "fehlalarm": 0}
        self._offen: dict[str, tuple[str, list[bytes]]] = {}
        self._reihenfolge: deque[str] = deque()
        self._naechste_id = 0
        self._offset = 0
        self._letzter_poll = 0.0
        # Wird von main() gesetzt, sobald das Archiv steht. Bewusst optional:
        # Ohne Archiv laeuft die Feedback-Schleife unveraendert weiter.
        self.archiv: DatensatzArchiv | None = None

    def registriere(self, alarm: Alarm, bilder: list[bytes]) -> dict | None:
        """Merkt die (unannotierten) Alarm-Bilder fuer spaeteres Feedback und
        liefert das Telegram-reply_markup — oder None, wenn Feedback aus ist."""
        if not self.aktiv or alarm.typ == "info":
            return None
        fid = str(self._naechste_id)
        self._naechste_id += 1
        self._offen[fid] = (alarm.typ, [b for b in bilder if b])
        self._reihenfolge.append(fid)
        while len(self._reihenfolge) > self.MAX_OFFEN:
            self._offen.pop(self._reihenfolge.popleft(), None)
        return {
            "inline_keyboard": [[
                {"text": "✅ Treffer", "callback_data": f"fb:{fid}:treffer"},
                {"text": "❌ Fehlalarm", "callback_data": f"fb:{fid}:fehlalarm"},
            ]]
        }

    def tick(self, jetzt: float | None = None) -> None:
        """Pro Hauptschleifen-Iteration aufrufen: holt alle POLL_INTERVALL_S
        die Button-Antworten ab (Kurz-Poll ohne Warten). Der Bot darf dafuer
        keinen Telegram-Webhook nutzen (getUpdates und Webhook schliessen
        sich aus)."""
        if not self.aktiv:
            return
        t = time.time() if jetzt is None else jetzt
        if t - self._letzter_poll < self.POLL_INTERVALL_S:
            return
        self._letzter_poll = t
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{self.token}/getUpdates",
                params={
                    "offset": self._offset,
                    "timeout": 0,
                    "allowed_updates": '["callback_query"]',
                },
                timeout=10,
            )
            r.raise_for_status()
            self.verarbeite(r.json().get("result") or [])
        except requests.RequestException as e:
            log.warning("Feedback-Abruf fehlgeschlagen: %s", e)

    def verarbeite(self, updates: list[dict]) -> None:
        for u in updates:
            self._offset = max(self._offset, int(u.get("update_id", 0)) + 1)
            cq = u.get("callback_query")
            if not cq:
                continue
            teile = str(cq.get("data") or "").split(":")
            antwort = "Danke!"
            if len(teile) == 3 and teile[0] == "fb" and teile[2] in self.zaehler:
                fid, urteil = teile[1], teile[2]
                self.zaehler[urteil] += 1
                eintrag = self._offen.pop(fid, None)
                if urteil == "fehlalarm":
                    anzahl = self._speichere(fid, eintrag)
                    antwort = (
                        f"Danke – {anzahl} Bild(er) fürs Nachtraining gespeichert."
                        if anzahl
                        else "Danke – notiert (Bilder lagen nicht mehr vor)."
                    )
                self._entferne_buttons(cq)
            self._antworte(cq, antwort)

    def _speichere(self, fid: str, eintrag: tuple[str, list[bytes]] | None) -> int:
        if not eintrag:
            return 0
        typ, bilder = eintrag
        ordner = self.ordner / time.strftime("%Y-%m-%d")
        ordner.mkdir(parents=True, exist_ok=True)
        for i, b in enumerate(bilder):
            (ordner / f"{typ}-{fid}-{i}.jpg").write_bytes(b)
        log.info("Fehlalarm-Feedback: %d Bild(er) -> %s", len(bilder), ordner)
        # Zweitkopie in die Cloud – Hard Negatives sind die wertvollsten
        # Trainingsbilder ueberhaupt (echte Szenen aus genau diesem Stall,
        # bei denen das Modell nachweislich falsch lag).
        if self.archiv:
            self.archiv.sichere("fehlalarm", bilder)
        return len(bilder)

    def _antworte(self, cq: dict, text: str) -> None:
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/answerCallbackQuery",
                data={"callback_query_id": cq.get("id"), "text": text},
                timeout=10,
            )
        except requests.RequestException:
            pass  # rein kosmetisch, naechster Poll laeuft trotzdem

    def _entferne_buttons(self, cq: dict) -> None:
        """Buttons nach dem Votum entfernen (verhindert Doppel-Votes)."""
        msg = cq.get("message") or {}
        if not msg.get("message_id"):
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/editMessageReplyMarkup",
                data={
                    "chat_id": (msg.get("chat") or {}).get("id", self.chat),
                    "message_id": msg["message_id"],
                    "reply_markup": json.dumps({"inline_keyboard": []}),
                },
                timeout=10,
            )
        except requests.RequestException:
            pass  # Doppel-Votes waeren harmlos (zweites speichert nichts mehr)


class Notifier:
    """Versendet Alarme; Cooldown pro (Kuh, Typ) verhindert Spam."""

    def __init__(self, cfg: dict):
        tg = cfg.get("telegram") or {}
        self.tg_token = (tg.get("token") or "").strip()
        self.tg_chat = str(tg.get("chat_id") or "").strip()
        self.cooldown_s = float(tg.get("cooldown_minuten", 15)) * 60
        self.bildserie = max(1, int(tg.get("bildserie_frames", 4)))
        self.digest_uhrzeit = (tg.get("digest_uhrzeit") or "").strip()
        self._digest_tag: str | None = None
        self._start_ts = time.time()
        self._zaehler: dict[str, int] = defaultdict(int)

        db = cfg.get("dashboard") or {}
        self.db_url = (db.get("url") or "").strip()
        self.db_token = (db.get("token") or "").strip()
        # Alarmbilder ans Dashboard mitschicken (die App zeigt sie als Serie).
        # Auf 0 setzen, wenn die Uplink-Leitung zu schmal ist.
        self.db_bilder = max(0, int(db.get("bilder", 3)))
        self._puffer_datei = Path(db.get("puffer_datei") or "alarm-puffer.jsonl")
        # Offline-Puffer: was nicht rausging, wird beim naechsten Kontakt
        # nachgeliefert. Begrenzt, damit eine lange Stoerung den Speicher
        # nicht sprengt.
        self._puffer: deque[dict] = deque(maxlen=int(db.get("puffer_max", 200)))
        self._puffer_laden()

        self.kamera = cfg["stream"].get("kamera", "stallwache")
        self._zuletzt: dict[tuple[str | None, str], float] = {}
        self.feedback = FeedbackSchleife(cfg)
        # Bildqualitaets-Gate (B20), von main() gesetzt: liefert die Zeile fuer
        # den Tagesbericht. Im Silent Mode zaehlt es nichts -> keine Zeile.
        self.qualitaet: BildQualitaet | None = None
        self.engine: InferenceEngine | None = None   # Messbarkeit des Schwanzwinkels (B19)

        # Optionaler MQTT-Zusatzausgang (Home Assistant & Co.); Ausfall darf
        # den Alarmweg nie beeintraechtigen.
        mq = cfg.get("mqtt") or {}
        self._mqtt_client = None
        self._mqtt_topic = (mq.get("basis_topic") or "stallblick").strip("/")
        host = (mq.get("host") or "").strip()
        if host:
            try:
                import paho.mqtt.client as mqtt_mod

                client = mqtt_mod.Client(
                    mqtt_mod.CallbackAPIVersion.VERSION2,
                    client_id=f"stallblick-{self.kamera}",
                )
                if mq.get("username"):
                    client.username_pw_set(mq["username"], mq.get("password") or "")
                client.connect_async(host, int(mq.get("port", 1883)))
                client.loop_start()  # reconnectet selbststaendig
                self._mqtt_client = client
                log.info("MQTT-Ausgang aktiv: %s -> %s/#", host, self._mqtt_topic)
            except Exception as e:  # noqa: BLE001
                log.error("MQTT deaktiviert (Initialisierung fehlgeschlagen): %s", e)

    def melde(
        self,
        alarm: Alarm,
        frame: np.ndarray | None,
        verlauf: list[np.ndarray] | None = None,
    ) -> None:
        """verlauf: die letzten Frames vor dem Alarm (aeltester zuerst) fuer
        die Bildserie – macht Fehlalarme am Handy sofort erkennbar."""
        schluessel = (alarm.kuh_id, alarm.typ)
        jetzt = time.time()
        if jetzt - self._zuletzt.get(schluessel, 0) < self.cooldown_s:
            return
        self._zuletzt[schluessel] = jetzt
        self._zaehler[alarm.typ] += 1
        log.warning("ALARM [%s] %s: %s", alarm.typ, alarm.kuh_id or "-", alarm.nachricht)

        bild = self._annotiere(frame, alarm) if frame is not None else None
        serie: list[bytes] = []
        if bild and verlauf and self.bildserie > 1:
            for f in verlauf[-(self.bildserie - 1) :]:
                ok, jpg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    serie.append(jpg.tobytes())

        # Fuers Feedback nur UNANNOTIERTE Bilder vormerken (die Serie plus das
        # rohe Alarmbild) — eingezeichnete Boxen wuerden das Nachtraining
        # vergiften.
        roh = list(serie)
        if frame is not None:
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                roh.append(jpg.tobytes())
        markup = self.feedback.registriere(alarm, roh)

        self._telegram(alarm, bild, serie, markup)
        self._dashboard(alarm, self._dashboard_bilder(serie, bild))
        self._mqtt(alarm)

    def status(self, nachricht: str) -> None:
        """Info-Meldung nur ans Dashboard (kein Telegram-Weckruf)."""
        log.info(nachricht)
        meldung = Alarm("info", None, nachricht, None, None)
        self._dashboard(meldung)
        self._mqtt(meldung)

    def wichtig(self, nachricht: str, still: bool = False) -> None:
        """Systemmeldung, die den Landwirt aktiv erreichen soll (Telegram +
        Dashboard + MQTT). Fuer Totmann-/Entwarnungsmeldungen — bewusst ohne
        Cooldown: der TotmannWaechter stellt Einmaligkeit pro Episode sicher."""
        log.warning(nachricht)
        meldung = Alarm("info", None, nachricht, None, None)
        self._telegram(meldung, None, still=still)
        self._dashboard(meldung)
        self._mqtt(meldung)

    def digest_tick(self, analyse_aktiv: bool, modus: str | None = None) -> None:
        """Sendet einmal taeglich (digest_uhrzeit) einen kompakten Tagesbericht."""
        if not (self.digest_uhrzeit and self.tg_token and self.tg_chat):
            return
        heute = time.strftime("%Y-%m-%d")
        if self._digest_tag == heute or time.strftime("%H:%M") < self.digest_uhrzeit:
            return
        self._digest_tag = heute
        stunden = (time.time() - self._start_ts) / 3600
        z = self._zaehler
        text = (
            "📋 Stallblick-Tagesbericht\n"
            f"Modus: {modus or ('Analyse' if analyse_aktiv else 'Silent Mode (Datensammlung)')}\n"
            f"Kalbeverdacht: {z['kalbeverdacht']} · Austreibung: {z['austreibung']} · "
            f"Brunstverdacht: {z['brunstverdacht']}\n"
            f"Agent läuft seit {stunden:.1f} h · Kamera: {self.kamera}"
        )
        fb = self.feedback.zaehler
        if fb["treffer"] or fb["fehlalarm"]:
            text += f"\nFeedback: ✅ {fb['treffer']} Treffer · ❌ {fb['fehlalarm']} Fehlalarm"
            fb["treffer"] = fb["fehlalarm"] = 0
        for quelle in (self.qualitaet, self.engine):  # B20 Bildstoerungen, B19 Messbarkeit
            zeile = quelle.tagesbericht() if quelle is not None else None
            if zeile:
                text += f"\n{zeile}"
        self._zaehler.clear()
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={"chat_id": self.tg_chat, "text": text},
                timeout=20,
            ).raise_for_status()
        except requests.RequestException as e:
            log.error("Digest-Versand fehlgeschlagen: %s", e)

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

    def _telegram(
        self,
        alarm: Alarm,
        bild: bytes | None,
        serie: list[bytes] | None = None,
        markup: dict | None = None,
        still: bool = False,
    ) -> None:
        if not (self.tg_token and self.tg_chat):
            return
        markup_json = json.dumps(markup) if markup else None
        leise = {"disable_notification": True} if still else {}  # Entwarnungen wecken nicht
        text = f"⚠️ {alarm.typ.upper()}"
        if alarm.kuh_id:
            text += f" – {alarm.kuh_id}"
        text += f"\n{alarm.nachricht}\nKamera: {self.kamera}"
        try:
            if bild and serie:
                # Album: Verlaufsbilder + annotiertes Alarmbild (Caption am ersten)
                fotos = serie + [bild]
                media = [
                    {
                        "type": "photo",
                        "media": f"attach://foto{i}",
                        **({"caption": text} if i == 0 else {}),
                    }
                    for i in range(len(fotos))
                ]
                r = requests.post(
                    f"https://api.telegram.org/bot{self.tg_token}/sendMediaGroup",
                    data={"chat_id": self.tg_chat, "media": json.dumps(media)},
                    files={
                        f"foto{i}": (f"foto{i}.jpg", f, "image/jpeg")
                        for i, f in enumerate(fotos)
                    },
                    timeout=30,
                )
                r.raise_for_status()
                if markup_json:
                    # sendMediaGroup kann keine Buttons tragen -> stille
                    # Folgenachricht (kein zweiter Weckton) als Antwort aufs Album.
                    erste = (r.json().get("result") or [{}])[0].get("message_id")
                    requests.post(
                        f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                        data={
                            "chat_id": self.tg_chat,
                            "text": "War dieser Alarm korrekt?",
                            "reply_markup": markup_json,
                            "disable_notification": True,
                            **({"reply_to_message_id": erste} if erste else {}),
                        },
                        timeout=20,
                    ).raise_for_status()
            elif bild:
                requests.post(
                    f"https://api.telegram.org/bot{self.tg_token}/sendPhoto",
                    data={
                        "chat_id": self.tg_chat,
                        "caption": text,
                        **({"reply_markup": markup_json} if markup_json else {}),
                    },
                    files={"photo": ("alarm.jpg", bild, "image/jpeg")},
                    timeout=20,
                ).raise_for_status()
            else:
                requests.post(
                    f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                    data={
                        "chat_id": self.tg_chat,
                        "text": text,
                        **({"reply_markup": markup_json} if markup_json else {}),
                        **leise,
                    },
                    timeout=20,
                ).raise_for_status()
        except requests.RequestException as e:
            log.error("Telegram-Versand fehlgeschlagen: %s", e)

    def _mqtt(self, alarm: Alarm) -> None:
        if self._mqtt_client is None:
            return
        try:
            self._mqtt_client.publish(
                f"{self._mqtt_topic}/{self.kamera}/{alarm.typ}",
                json.dumps(
                    {
                        "typ": alarm.typ,
                        "kuhId": alarm.kuh_id,
                        "kamera": self.kamera,
                        "nachricht": alarm.nachricht,
                        "konfidenz": alarm.konfidenz,
                        "zeit": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as e:  # noqa: BLE001
            log.error("MQTT-Publish fehlgeschlagen: %s", e)

    def _dashboard_bilder(
        self,
        serie: list[bytes],
        alarmbild: bytes | None,
    ) -> list[bytes]:
        """Waehlt die Bilder fuer die App aus: erst die Frames vor dem Alarm,
        zuletzt das annotierte Alarmbild.

        Bewusst die annotierte Fassung — anders als beim Fehlalarm-Feedback,
        wo eingezeichnete Boxen das Nachtraining vergiften wuerden. Hier
        schaut ein Mensch drauf, und der will nachts um drei sofort sehen,
        worauf das Modell reagiert hat.
        """
        if not self.db_bilder:
            return []
        bilder = [*serie, alarmbild] if alarmbild else list(serie)
        # Die juengsten Bilder sind die aussagekraeftigsten.
        return bilder[-self.db_bilder :]

    # ------------------------------------------------------------------
    # Dashboard-Meldung mit Offline-Puffer
    #
    # Der Stall ist der Ort mit dem schlechtesten Empfang des Betriebs. Faellt
    # die Leitung aus, darf ein Kalbealarm nicht einfach verschwinden: er
    # wandert in einen Puffer auf der Platte und geht beim naechsten Kontakt
    # als Stapel raus (POST /api/events mit {"ereignisse": [...]}).
    # ------------------------------------------------------------------

    def _puffer_laden(self) -> None:
        """Liest den Puffer eines vorherigen Laufs (Stromausfall, Neustart)."""
        if not self._puffer_datei.exists():
            return
        try:
            for zeile in self._puffer_datei.read_text("utf-8").splitlines():
                zeile = zeile.strip()
                if zeile:
                    self._puffer.append(json.loads(zeile))
            log.info("Offline-Puffer geladen: %d Ereignis(se)", len(self._puffer))
        except (OSError, ValueError) as e:
            log.error("Offline-Puffer nicht lesbar (wird verworfen): %s", e)
            self._puffer.clear()

    def _puffer_sichern(self) -> None:
        """Schreibt den Puffer atomar zurueck (erst temporaer, dann ersetzen)."""
        try:
            if not self._puffer:
                self._puffer_datei.unlink(missing_ok=True)
                return
            tmp = self._puffer_datei.with_suffix(".tmp")
            tmp.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in self._puffer),
                "utf-8",
            )
            tmp.replace(self._puffer_datei)
        except OSError as e:
            log.error("Offline-Puffer nicht schreibbar: %s", e)

    def _dashboard(
        self,
        alarm: Alarm,
        bilder: list[bytes] | None = None,
    ) -> None:
        if not (self.db_url and self.db_token):
            return

        ereignis: dict = {
            "typ": alarm.typ,
            "kuhId": alarm.kuh_id,
            "kamera": self.kamera,
            "nachricht": alarm.nachricht,
            "konfidenz": alarm.konfidenz,
            # Eigener Zeitstempel: bei Nachlieferung waere die Eingangszeit
            # des Servers falsch — die Kalbung war um 03:12, nicht um 07:40.
            "zeit": dt.datetime.now(dt.timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
        }
        if bilder and self.db_bilder:
            # Von hinten schneiden: das letzte Bild ist das annotierte
            # Alarmbild und damit das wichtigste der Serie.
            ereignis["bilder"] = [
                base64.b64encode(b).decode("ascii") for b in bilder[-self.db_bilder :]
            ]

        # Alles, was noch aussteht, geht in derselben Verbindung mit raus.
        stapel = list(self._puffer) + [ereignis]
        try:
            requests.post(
                self.db_url,
                json={"ereignisse": stapel},
                headers={"x-ingest-token": self.db_token},
                timeout=30,
            ).raise_for_status()
        except requests.RequestException as e:
            self._puffer.append(ereignis)
            self._puffer_sichern()
            log.error(
                "Dashboard-Meldung fehlgeschlagen (%d im Puffer): %s",
                len(self._puffer),
                e,
            )
            return

        if self._puffer:
            log.info("Offline-Puffer nachgeliefert: %d Ereignis(se)", len(self._puffer))
            self._puffer.clear()
            self._puffer_sichern()


# --------------------------------------------------------------------------
# Hauptschleife
# --------------------------------------------------------------------------

def silent_dateiname(kamera: str, zeit: float) -> str:
    """B21: ``<kamera>_<YYYYmmdd-HHMMSS>.jpg`` in UTC - unabhaengig von der
    Zeitzone des Rechners (Container: UTC, systemd-Dienst: Ortszeit). Der
    Kameraname wird auf a-z0-9 reduziert und beginnt mit einem Buchstaben;
    so lesen ihn cvat_zu_yolo_pose.py, abnahme_gates.py, stall_sichtung.py
    und datensatz_inventur.py."""
    name = re.sub(r"[^a-z0-9]", "", str(kamera or "").lower())
    if not name[:1].isalpha():
        name = "kamera" + name
    return f"{name}_{time.strftime('%Y%m%d-%H%M%S', time.gmtime(zeit))}.jpg"


def werte_bild_aus(frame, engine, logik, qualitaet, notifier, verlauf, jetzt=None, waechter=None) -> list:
    """Ein Bild im Analyse-Modus auswerten (B19/B20).

    Reihenfolge ist Absicht: Qualitaet -> Modell -> Logik -> Alarme -> erst
    danach Waechter-, System- und Info-Meldungen (ein haengender Versand oder
    ein Fehler darin darf keinen Alarm kosten oder verzoegern). Ein Fehler in
    der Qualitaetspruefung laesst das Bild als intakt durch - die Austreibung
    haengt nie an diesem Filter.

    ``waechter`` (baue_waechter), Weckregel (B12-Auslegung, B20-Ergaenzung):
    "blind" (nur gestreifte Bilder) weckt per Telegram; "tracker" (ByteTrack-
    Laufzeitfehler, nur wenn er wirklich lief) weckt nur im Wach-Modus, sonst
    Dashboard + Tagesbericht - die Austreibung laeuft ja weiter. Entwarnungen
    gehen still raus.
    """
    try:
        defekt, _ = qualitaet.pruefe(frame)
        info = qualitaet.zaehle(defekt, jetzt)
    except Exception:  # noqa: BLE001
        log.exception("Bildqualitaets-Pruefung fehlgeschlagen – Bild gilt als intakt")
        defekt, info = False, None
    kuehe, objekte = engine.analysiere(frame, defekt=defekt)
    alarme = logik.bewerte(kuehe, objekte, defekt=defekt, jetzt=jetzt)
    for alarm in alarme:
        notifier.melde(alarm, frame, verlauf=verlauf)
    if waechter:
        wach = bool((logik.cfg.get("logik") or {}).get("wach_modus"))
        for name, ok, felder in (
            ("blind", not defekt, {}),
            ("tracker", engine.tracker_ok, {"technik": engine.tracker_laufzeitfehler or ""}),
        ):
            if name not in waechter or ok is None:
                continue  # Tracker nicht aufgerufen: kein Beleg, kein Tick
            try:
                w = waechter[name]
                text = w.tick(ok, jetzt, **felder)
                if not text:
                    continue
                if w.letzte_art == "meldung":
                    w.kanal = "dashboard" if name == "tracker" and not wach else "telegram"
                if w.kanal == "dashboard":
                    notifier.status(text)  # Entwarnung auf demselben Kanal wie die Meldung
                else:
                    notifier.wichtig(text, still=w.letzte_art == "entwarnung")
            except Exception:  # noqa: BLE001
                log.exception("Waechter %s fehlgeschlagen", name)
    if info:
        notifier.status(info)
    return alarme


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
    totmann = TotmannWaechter(cfg)
    # Zweitkopie der Trainingsbilder in der Cloud (dashboard.archiv). Die
    # Feedback-Schleife bekommt dieselbe Instanz, damit nur ein Worker-Thread
    # laeuft und Silent-Mode-Bilder wie Hard Negatives denselben Weg nehmen.
    archiv = DatensatzArchiv(cfg)
    notifier.feedback.archiv = archiv
    # Bildqualitaets-Gate (B20) - zaehlt nur im Analyse-Modus.
    qualitaet = BildQualitaet(cfg)
    notifier.qualitaet = qualitaet
    notifier.engine = engine
    waechter = baue_waechter(cfg)  # Analyse-, Tracker- und Blind-Waechter
    kamera = (cfg.get("stream") or {}).get("kamera", "stallwache")

    frame_puffer: deque[np.ndarray] = deque(maxlen=8)  # Verlauf fuer Bildserien

    if engine.fehler:
        # Nie still: Ein Modell, das nicht laedt, saehe sonst aus wie eine
        # ruhige Nacht (Totmann-Prinzip). Einmal je Start, danach im Tagesbericht.
        notifier.wichtig(TEXT_MODELL_AUS.format(
            kamera=kamera, grund=engine.fehler_grund, schritt=engine.fehler_schritt,
            technik=engine.fehler,
        ))
    if engine.aktiv:
        if engine.tracker_fehler:
            notifier.status("Edge-Agent gestartet – eingeschränkt: nur Fruchtblase/Kälberfüße")
            notifier.wichtig(TEXT_TRACKER_AUS.format(kamera=kamera, technik=engine.tracker_fehler))
        else:
            notifier.status("Edge-Agent gestartet – Analyse-Modus aktiv")
    else:
        notifier.status(
            "Edge-Agent gestartet – KEINE Überwachung (Modell nicht geladen), nur Datensammlung"
            if engine.fehler else "Edge-Agent gestartet (Silent Mode – Datensammlung)"
        )
        ordner = Path(cfg["silent_mode"]["ordner"])
        ordner.mkdir(parents=True, exist_ok=True)
        intervall = float(cfg["silent_mode"]["intervall_sekunden"])
        letzte_aufnahme = 0.0

    while True:
        try:
            frame = stream.naechster_frame()
            notifier.digest_tick(engine.aktiv, modus=engine.modus_text(waechter))
            notifier.feedback.tick()
            totmann_meldung = totmann.tick(frame is not None)
            if totmann_meldung:
                notifier.wichtig(totmann_meldung, still=totmann.letzte_art == "entwarnung")
            if frame is None:
                continue

            if not engine.aktiv:
                # Silent Mode: regelmaessig Trainingsbilder sichern.
                if time.time() - letzte_aufnahme >= intervall:
                    letzte_aufnahme = time.time()
                    # B21: <kamera>_<UTC>.jpg - Kamera und Stalltag stehen im Namen.
                    name = ordner / silent_dateiname(kamera, letzte_aufnahme)
                    cv2.imwrite(str(name), frame)
                    log.info("Trainingsbild gespeichert: %s", name)
                    if archiv.aktiv:
                        # Fuer den Upload neu kodieren statt die Datei zu
                        # lesen: spart einen Plattenzugriff und haelt die
                        # Cloud-Kopie unabhaengig vom lokalen Schreibergebnis.
                        ok, jpg = cv2.imencode(
                            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                        )
                        if ok:
                            archiv.sichere("silent", [jpg.tobytes()])
                continue

            frame_puffer.append(frame)
            try:
                werte_bild_aus(frame, engine, logik, qualitaet, notifier,
                               list(frame_puffer)[:-1], waechter=waechter)
                analyse_ok = True
            except Exception:  # noqa: BLE001 - der Analyse-Waechter meldet Dauerfehler
                log.exception("Bildauswertung fehlgeschlagen")
                analyse_ok = False
            text = waechter["analyse"].tick(analyse_ok)
            if text:
                notifier.wichtig(text, still=waechter["analyse"].letzte_art == "entwarnung")
            if not analyse_ok:
                time.sleep(5)

        except KeyboardInterrupt:
            log.info("Beendet.")
            return
        except Exception:  # noqa: BLE001 – 24/7-Betrieb darf nie abstuerzen
            log.exception("Unerwarteter Fehler – laufe weiter")
            time.sleep(5)


if __name__ == "__main__":
    main()
