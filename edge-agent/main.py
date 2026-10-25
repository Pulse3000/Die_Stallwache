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
     Takt je Episode statt Cooldown: Erinnerung alle 15 min, solange
     sichtbar; Eskalation nach 60 min (docs/austreibung-episoden-
     spezifikation.md).
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
import sys
import threading
import time
import urllib.parse
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

# FFmpeg-Meldungen erst ab „fatal" ausgeben: Manche Kameras haengen
# Zusatzdaten an jedes Bild („SEI type 764 size 272 truncated at 256"), der
# Decoder meldet das auf Fehlerstufe — im Stall mehrmals pro Sekunde. Das
# fuellt das rotierende Docker-Log in Minuten und verdraengt die eigenen
# Meldungen des Agenten. Echte Ausfaelle sieht der Agent selbst (read()
# liefert kein Bild -> Reconnect, Totmann). Ueberschreibbar per Umgebung,
# z. B. OPENCV_FFMPEG_LOGLEVEL=16 zur Fehlersuche (README „Ruhiges Log").
# Leer zaehlt als nicht gesetzt (docker-compose.yml reicht die Variable durch,
# `VAR= docker compose up` ergaebe sonst Loglevel 0).
# Muss vor dem ersten VideoCapture gesetzt sein.
if not os.environ.get("OPENCV_FFMPEG_LOGLEVEL", "").strip():
    os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "8"

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
import yaml  # noqa: E402

# Geschwistermodul freeze_watchdog.py auch dann finden, wenn main.py per runpy
# (Docker) oder aus dem Testlader geladen wird.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from freeze_watchdog import FreezeWatchdog, baue_watchdog  # noqa: E402
import alte_cpu  # noqa: E402

log = logging.getLogger("stallblick-agent")


class GeheimFilter(logging.Filter):
    """Schwaerzt Geheimnisse (Telegram-Bot-Token) in jeder Logzeile des Agenten.

    requests nennt in Fehlermeldungen die URL, bei Telegram samt Token
    (/bot<TOKEN>/getUpdates) – solange Telegram nicht erreichbar ist, alle
    10 s. Im Container bleibt das Log ueber `docker logs` lesbar (Befund
    qa-waechter). Gilt auch fuer Tracebacks aus log.exception.
    """

    def __init__(self) -> None:
        super().__init__()
        self.geheim: set[str] = set()

    def merke(self, wert: str) -> None:
        if wert and len(wert) >= 8:
            self.geheim.add(wert)

    def _schwaerze(self, text: str) -> str:
        for wert in tuple(self.geheim):  # merke() darf parallel laufen
            text = text.replace(wert, "***")
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if self.geheim:
            try:
                nachricht = record.getMessage()
            except Exception:  # noqa: BLE001
                # Fehlerhafter Aufruf (Platzhalter passen nicht): wie ohne
                # Filter an logging weiterreichen, das meldet "Logging error"
                # – nie an der Aufrufstelle werfen (Befund qa-waechter H1).
                return True
            record.msg, record.args = self._schwaerze(nachricht), None
            if record.exc_info:
                record.exc_text = self._schwaerze(
                    logging.Formatter().formatException(record.exc_info)
                )
        return True


GEHEIM = GeheimFilter()
log.addFilter(GEHEIM)


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


def trenne_zugangsdaten(url: str) -> tuple[str, tuple[str, str] | None]:
    """Zieht Benutzer/Passwort aus einer URL (http://user:pass@host/…).

    Die go2rtc-Schnittstelle kann einen Login haben
    (docs/fernzugriff-spezifikation.md). Die Zugangsdaten gehen dann nur als
    Basic-Auth an requests; in Logs und Fehlermeldungen steht die URL ohne sie.
    """
    if not url:
        return "", None
    teile = urllib.parse.urlsplit(url)
    if teile.username is None:
        return url, None
    host = teile.hostname or ""
    if ":" in host:
        host = f"[{host}]"  # IPv6
    if teile.port:
        host = f"{host}:{teile.port}"
    ohne = urllib.parse.urlunsplit(
        (teile.scheme, host, teile.path, teile.query, teile.fragment)
    )
    return ohne, (
        urllib.parse.unquote(teile.username),
        urllib.parse.unquote(teile.password or ""),
    )


# Schemata eines Livestreams. Alles ohne Schema ist eine Datei (Replay,
# Fehlalarm-Budget) und wird Bild fuer Bild gelesen
# (docs/bildfrische-spezifikation.md, R1).
LIVE_SCHEMATA = ("rtsp", "rtsps", "rtmp", "rtmps", "http", "https", "udp", "tcp", "srt")


def ist_livequelle(url: str) -> bool:
    return urllib.parse.urlsplit(url or "").scheme.lower() in LIVE_SCHEMATA


def oeffne_capture(url: str):
    """VideoCapture mit begrenzten Timeouts fuer Oeffnen und Lesen (R4).

    Kennt die OpenCV-Version die Parameter nicht, gilt ihr Standard (30 s).
    """
    params: list[int] = []
    for name in ("CAP_PROP_OPEN_TIMEOUT_MSEC", "CAP_PROP_READ_TIMEOUT_MSEC"):
        prop = getattr(cv2, name, None)
        if prop is not None:
            params += [prop, Bildgreifer.TIMEOUT_MS]
    if params:
        return cv2.VideoCapture(url, getattr(cv2, "CAP_ANY", 0), params)
    return cv2.VideoCapture(url)


class Bildgreifer:
    """Liest einen Livestream im Hintergrund mit und haelt nur das juengste Bild.

    OpenCV dekodiert der Reihe nach: Wer 1 Bild/s aus einem 25-fps-Stream
    liest, bekommt das naechste Bild im Puffer, nicht das aktuelle. Gemessen
    war nach 227 s ein 113 s altes Bild, und die analysierten Bilder lagen im
    Video 40 ms statt 1 s auseinander — das 30-Minuten-Fenster sah 72 s
    Video (docs/bildfrische-spezifikation.md). Deshalb ruft dieser Thread
    fortlaufend grab() auf und nur auf Abruf retrieve() (Farbumwandlung).
    Nur er beruehrt die VideoCapture; Verbindungsaufbau und Backoff laufen
    hier, die Analyseschleife wartet nie darauf.
    """

    FRISCH_S = 5.0            # letzter grab() aelter -> kein Bild (R3)
    UEBERGABE_S = 2.0         # so lange wartet ein Abruf hoechstens
    TIMEOUT_MS = 10_000       # Oeffnen/Lesen (R4)
    BACKOFF_S = (5, 10, 20, 30)  # Reconnect (R5), letzter Wert = Deckel
    # Rueckstand gegenueber der Stream-Uhr (R9): Rechner dekodiert langsamer,
    # als die Kamera sendet. Geurteilt wird ueber das Minimum eines Fensters:
    # HLS liefert stossweise je Segment, der Rueckstand faellt dort nach jedem
    # Segment auf ~0; ein echter Rueckstand faellt nie. Minimum ab WARNUNG ins
    # Log, ab NEU neu verbinden (das verwirft den Rueckstand).
    RUECKSTAND_WARNUNG_S = 5.0
    RUECKSTAND_NEU_S = 10.0
    RUECKSTAND_FENSTER_S = 15.0

    def __init__(self, oeffne, name: str = "bildgreifer"):
        # oeffne() -> geoeffnete VideoCapture oder None; laeuft im Thread.
        self._oeffne = oeffne
        self._letzter_grab: float | None = None
        self._bedingung = threading.Condition()
        self._auftrag = 0         # zuletzt erteilter Abruf
        self._antwort_nr = 0      # zuletzt beantworteter Abruf
        self._abgeholt = 0        # zuletzt abgeholte Antwort
        self._antwort = None
        self._antwort_zeit = 0.0  # grab()-Zeit des Antwortbilds
        self._stopp = threading.Event()
        self._basis: tuple[float, float] | None = None  # (Uhrzeit, Stream-ms)
        self._letzte_pos = 0.0
        self._fenster_start: float | None = None
        self._fenster_min = 0.0
        self._warnung_zuletzt: float | None = None
        self._neu_log_zuletzt: float | None = None
        self._neu_seit_log = 0
        self._traceback_zuletzt: float | None = None
        self.fehlversuche = 0
        self._thread = threading.Thread(target=self._arbeite, name=name, daemon=True)
        self._thread.start()

    @property
    def frisch(self) -> bool:
        t = self._letzter_grab
        return t is not None and time.time() - t <= self.FRISCH_S

    def hole(self) -> np.ndarray | None:
        """Juengstes Bild (nach dem Abruf gegriffen) oder None.

        Nur ein Aufrufer (Hauptschleife). Ein Auftrag bleibt stehen, bis der
        Greifer ihn beantwortet: HLS (Cloud-Quelle) liefert Bilder stossweise
        je Segment, die Antwort kommt dann oft erst nach dem Warten. Der
        naechste Abruf holt sie ab, solange sie frisch ist. Ohne das bekam
        die Analyse ab ~8 s Segmentdauer kein einziges Bild (Befund ki-wache).
        """
        with self._bedingung:
            if self._antwort_nr > self._abgeholt:
                self._abgeholt = self._antwort_nr
                if (
                    self._antwort is not None
                    and time.time() - self._antwort_zeit <= self.FRISCH_S
                ):
                    return self._antwort
            if self._auftrag <= self._antwort_nr:
                self._auftrag += 1
            nr = self._auftrag
            if not self.frisch:
                return None  # Auftrag bleibt stehen
            if not self._bedingung.wait_for(
                lambda: self._antwort_nr >= nr, timeout=self.UEBERGABE_S
            ):
                return None
            self._abgeholt = self._antwort_nr
            return self._antwort

    def stopp(self) -> None:
        self._stopp.set()

    def _arbeite(self) -> None:
        cap = None
        while not self._stopp.is_set():
            try:
                if cap is None:
                    cap = self._oeffne()
                    self._basis, self._letzte_pos = None, 0.0
                    self._fenster_start = None
                    if cap is None or not cap.isOpened():
                        cap = self._schliesse(cap)
                        self._warte()
                        continue
                if not cap.grab():
                    cap = self._schliesse(cap)
                    self._warte()
                    continue
                jetzt = time.time()
                self._letzter_grab = jetzt
                if self.fehlversuche:
                    log.info("Stream verbunden, Bildgreifer laeuft.")
                    self.fehlversuche = 0
                if self._zu_weit_zurueck(cap, jetzt):
                    cap = self._schliesse(cap)
                    continue
                if self._auftrag > self._antwort_nr:
                    nr = self._auftrag
                    ok, bild = cap.retrieve()
                    with self._bedingung:
                        self._antwort, self._antwort_nr = (bild if ok else None), nr
                        self._antwort_zeit = jetzt
                        self._bedingung.notify_all()
            except Exception:  # noqa: BLE001 – der Greifer endet nie von selbst (R8)
                jetzt = time.time()
                if self._traceback_zuletzt is None or jetzt - self._traceback_zuletzt >= 3600:
                    self._traceback_zuletzt = jetzt
                    log.exception("Bildgreifer gestoert – verbinde neu")
                cap = self._schliesse(cap)
                self._warte()
        self._schliesse(cap)

    def _zu_weit_zurueck(self, cap, jetzt: float) -> bool:
        """Rueckstand des Greifers aus Uhrzeit gegen Stream-Zeitstempel (R9).

        Nur bei steigenden Zeitstempeln; Basis ist der Punkt mit dem
        kleinsten Rueckstand. Geurteilt wird am Ende jedes Fensters ueber
        dessen Minimum. Quellen ohne Zeitstempel pruefen nie.
        """
        try:
            pos = float(cap.get(cv2.CAP_PROP_POS_MSEC))
        except Exception:  # noqa: BLE001 – Quelle ohne Zeitstempel
            return False
        if pos <= self._letzte_pos:
            if pos < self._letzte_pos:
                self._basis = None  # Zeitstempel springt zurueck
            self._letzte_pos = pos
            return False
        self._letzte_pos = pos
        if self._basis is None:
            self._basis = (jetzt, pos)
        rueckstand = (jetzt - self._basis[0]) - (pos - self._basis[1]) / 1000
        if rueckstand < 0:
            self._basis = (jetzt, pos)
            rueckstand = 0.0
        if self._fenster_start is None:
            self._fenster_start, self._fenster_min = jetzt, rueckstand
            return False
        self._fenster_min = min(self._fenster_min, rueckstand)
        if jetzt - self._fenster_start < self.RUECKSTAND_FENSTER_S:
            return False
        minimum = self._fenster_min
        self._fenster_start, self._fenster_min = jetzt, rueckstand
        if minimum >= self.RUECKSTAND_NEU_S:
            # Bei Dauerueberlast regelmaessig: hoechstens eine Zeile pro Stunde.
            self._neu_seit_log += 1
            if self._neu_log_zuletzt is None or jetzt - self._neu_log_zuletzt >= 3600:
                log.warning(
                    "Bildgreifer %.0f s hinter dem Stream – verbinde neu (%d-mal seit "
                    "der letzten Meldung). Rechner zu langsam fuer diesen Stream? "
                    "Substream verwenden.", minimum, self._neu_seit_log,
                )
                self._neu_log_zuletzt, self._neu_seit_log = jetzt, 0
            return True
        if minimum >= self.RUECKSTAND_WARNUNG_S and (
            self._warnung_zuletzt is None or jetzt - self._warnung_zuletzt >= 3600
        ):
            self._warnung_zuletzt = jetzt
            log.warning(
                "Bildgreifer %.0f s hinter dem Stream – Rechner zu langsam fuer "
                "diesen Stream? Substream verwenden.", minimum,
            )
        return False

    def _warte(self) -> None:
        s = self.BACKOFF_S[min(self.fehlversuche, len(self.BACKOFF_S) - 1)]
        self.fehlversuche += 1
        log.warning("Stream nicht erreichbar – naechster Versuch in %d s.", s)
        self._stopp.wait(s)

    def _schliesse(self, cap) -> None:
        # Ohne Verbindung kommt kein Bild mehr: nicht frisch, Abruf ohne Warten.
        self._letzter_grab = None
        if cap is not None:
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass
        return None


class StreamHandler:
    """Liefert Frames im Takt von ziel_fps; uebersteht Verbindungsabbrueche.

    Livestream: Der Bildgreifer haelt das juengste Bild bereit, ein Abruf
    blockiert hoechstens Bildgreifer.UEBERGABE_S. Datei: Bild fuer Bild der
    Reihe nach (docs/bildfrische-spezifikation.md).
    """

    RECONNECT_WARTEZEIT_S = 5   # nur Datei; Livestream: Bildgreifer.BACKOFF_S
    FEHLER_BIS_FALLBACK = 5

    def __init__(self, cfg: dict):
        self.url: str = (cfg["stream"].get("url") or "").strip()
        self.quelle = CloudQuelle(cfg)
        if not self.url and not self.quelle.aktiv:
            raise SystemExit(
                "stream.url fehlt – entweder Bridge-URL eintragen oder "
                "Cloud-Quelle konfigurieren (stream.app_url + stream.quelle_api)."
            )
        self.fallback_url, self.fallback_auth = trenne_zugangsdaten(
            (cfg["stream"].get("fallback_snapshot_url") or "").strip()
        )
        self.frame_intervall = 1.0 / float(cfg["stream"].get("ziel_fps", 1.0))
        self.live = self.quelle.aktiv or ist_livequelle(self.url)
        # Startet beim ersten Abruf (der Konstruktor bleibt ohne Nebenwirkung).
        self.greifer: Bildgreifer | None = None
        self.cap: cv2.VideoCapture | None = None   # nur Datei
        self.fehler_in_folge = 0
        self.nutze_fallback = False
        self._letzter_frame_ts = 0.0

    def _oeffne_live(self):
        """Laeuft im Greifer-Thread: Cloud-URL holen, Capture oeffnen."""
        if self.quelle.aktiv:
            # Kurzlebige Cloud-URL bei jedem (Re-)Connect frisch holen.
            neue = self.quelle.hole_url()
            if neue:
                self.url = neue
            elif not self.url:
                return None  # noch keine URL bekannt -> Backoff, neuer Versuch
        # Ohne Zugangsdaten und Query (Cloud-URLs tragen Signaturen) ins Log.
        log.info("Verbinde mit Stream: %s", trenne_zugangsdaten(self.url)[0].split("?")[0])
        return oeffne_capture(self.url)

    def _verbinde(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        log.info("Oeffne Datei: %s", self.url)
        self.cap = cv2.VideoCapture(self.url)

    def _frame_datei(self) -> np.ndarray | None:
        if self.cap is None or not self.cap.isOpened():
            self._verbinde()
        if self.cap is None or not self.cap.isOpened():
            return None
        ok, frame = self.cap.read()
        return frame if ok else None

    def _frame_snapshot(self) -> np.ndarray | None:
        try:
            r = requests.get(self.fallback_url, timeout=10, auth=self.fallback_auth)
            r.raise_for_status()
            buf = np.frombuffer(r.content, dtype=np.uint8)
            return cv2.imdecode(buf, cv2.IMREAD_COLOR)
        except requests.RequestException as e:
            log.warning("Snapshot-Fallback fehlgeschlagen: %s", e)
            return None

    def naechster_frame(self) -> np.ndarray | None:
        """Wartet bis zum naechsten Takt gemaess Ziel-FPS; Frame oder None."""
        wartezeit = self._letzter_frame_ts + self.frame_intervall - time.time()
        if wartezeit > 0:
            time.sleep(wartezeit)
        self._letzter_frame_ts = time.time()
        if self.live:
            return self._frame_live()

        frame = (
            self._frame_snapshot() if self.nutze_fallback else self._frame_datei()
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

    def _frame_live(self) -> np.ndarray | None:
        """Frisches Livebild; nach FEHLER_BIS_FALLBACK Abrufen ohne eines das
        Snapshot-Polling, bis der Livestream wieder frisch ist (R6)."""
        if self.greifer is None:
            self.greifer = Bildgreifer(self._oeffne_live)
        frame = self.greifer.hole()
        if frame is not None:
            if self.nutze_fallback:
                log.info("Livestream wieder frisch – zurueck vom Snapshot-Polling.")
                self.nutze_fallback = False
            elif self.fehler_in_folge:
                log.info("Stream wieder stabil.")
            self.fehler_in_folge = 0
            return frame
        self.fehler_in_folge += 1
        if self.fallback_url and self.fehler_in_folge >= self.FEHLER_BIS_FALLBACK:
            if not self.nutze_fallback:
                log.warning("RTSP instabil – wechsle auf Snapshot-Polling.")
                self.nutze_fallback = True
            return self._frame_snapshot()
        return None


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

    def tick(self, frame_ok: bool, jetzt: float | None = None) -> str | None:
        """Pro Hauptschleifen-Iteration aufrufen; liefert die zu sendende
        Nachricht oder None."""
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
            self.letzter_frame = t
            self.ausfall_start = None
            self.gemeldet = False
            return entwarnung

        if self.ausfall_start is None:
            # Ausfall zaehlt ab dem letzten guten Frame, nicht ab jetzt.
            self.ausfall_start = self.letzter_frame
        if not self.gemeldet and t - self.ausfall_start >= self.schwelle_s:
            self.gemeldet = True
            dauer_min = (t - self.ausfall_start) / 60
            return (
                f"Kamerastream seit {dauer_min:.0f} min ausgefallen – das "
                "dritte Auge ist blind! Bitte Bridge, WLAN und Kamera prüfen."
            )
        return None


class Lebenszeichen:
    """Meldet der App regelmaessig: Agent lebt, Modus, Kamera liefert Bild.

    Ohne dieses Signal kann die Statusabfrage (GET /api/stall-status) nie
    „OK" sagen — eine ruhige Nacht und ein toter Agent saehen gleich aus.
    Vertrag: docs/statusabfrage-spezifikation.md (leerer Stapel plus Feld
    ``lebenszeichen``, abwaertskompatibel).

    Versand im eigenen Daemon-Thread mit kurzem Timeout: ein toter Uplink
    darf die Analyseschleife nie aufhalten. Haengt ein Versand noch, faellt
    der naechste aus, statt Threads aufzustauen. Den Offline-Puffer der
    Alarme fasst er bewusst nicht an (gehoert dem Hauptthread).

    Im Silent Mode dazu der Bildbestand dieser Kamera (Anzahl, davon in
    den letzten 24 h, juengstes Bild), damit der Tagesreport den Fortschritt
    der Datensammlung belegen kann (Spezifikation Abschnitt 9). Gezaehlt
    wird im Sende-Thread, nie in der Hauptschleife, und nur im Silent Mode:
    Haengt der Ordner (USB-Platte, NFS), haelt das den Versand auf, und ein
    verspaetetes „Bild da" darf im Analyse-Modus kein falsches OK tragen.
    """

    TIMEOUT_S = 10
    # Zustandswechsel (Bild weg/da, Modus) frueher melden, aber nicht oefter
    # als alle 30 s — ein flackernder Stream soll die Leitung nicht fluten.
    WECHSEL_MIN_ABSTAND_S = 30

    def __init__(self, cfg: dict):
        db = cfg.get("dashboard") or {}
        self.url = (db.get("url") or "").strip()
        self.token = (db.get("token") or "").strip()
        self.intervall_s = float(db.get("lebenszeichen_minuten", 5) or 0) * 60
        self.kamera = (cfg.get("stream") or {}).get("kamera", "stallwache")
        ordner = (cfg.get("silent_mode") or {}).get("ordner")
        self.ordner = Path(ordner) if ordner else None
        self._zuletzt: float | None = None
        self._zustand: tuple[str, bool] | None = None
        self._thread: threading.Thread | None = None
        self.fehler_in_folge = 0

    @property
    def aktiv(self) -> bool:
        return bool(self.url and self.token and self.intervall_s > 0)

    def tick(self, analyse_aktiv: bool, bild_ok: bool, jetzt: float | None = None) -> bool:
        """Pro Hauptschleifen-Iteration aufrufen. True = Versand gestartet.
        Wirft nie."""
        try:
            if not self.aktiv:
                return False
            t = time.time() if jetzt is None else jetzt
            zustand = ("analyse" if analyse_aktiv else "silent", bool(bild_ok))
            if self._zuletzt is not None:
                seit = t - self._zuletzt
                faellig = seit >= self.intervall_s or (
                    zustand != self._zustand and seit >= self.WECHSEL_MIN_ABSTAND_S
                )
                if not faellig:
                    return False
            if self._thread is not None and self._thread.is_alive():
                return False  # voriger Versand haengt noch (Timeout laeuft)
            self._zuletzt, self._zustand = t, zustand
            nutzlast = {
                "ereignisse": [],
                "lebenszeichen": {
                    "kamera": self.kamera,
                    "modus": zustand[0],
                    "bild": zustand[1],
                },
            }
            self._thread = threading.Thread(
                target=self._sende, args=(nutzlast,), name="lebenszeichen", daemon=True
            )
            self._thread.start()
            return True
        except Exception:  # noqa: BLE001 – darf die Hauptschleife nie stoeren
            log.exception("Lebenszeichen konnte nicht gestartet werden")
            return False

    def bildbestand(self, jetzt: float | None = None) -> dict | None:
        """Silent-Mode-Bilder DIESER Kamera (``<kamera>_JJJJMMTT-HHMMSS.jpg``,
        nicht rekursiv). Die Zeiten stammen aus dem Dateinamen, ohne stat.
        None, wenn der Ordner fehlt oder nicht lesbar ist. Wirft nie."""
        if self.ordner is None:
            return None
        t = time.time() if jetzt is None else jetzt
        praefix = trainingsbild_praefix(self.kamera) + "_"
        grenze_24h = time.strftime("%Y%m%d-%H%M%S", time.localtime(t - 86400))
        anzahl = juenger = 0
        zuletzt = ""
        try:
            with os.scandir(self.ordner) as eintraege:
                for e in eintraege:
                    name = e.name
                    if not (name.startswith(praefix) and name.lower().endswith(".jpg")):
                        continue
                    stempel = name[len(praefix):-4]
                    if not _TRAININGSBILD_ZEIT.fullmatch(stempel) or not e.is_file():
                        continue
                    anzahl += 1
                    # Festes Format -> Textvergleich = Zeitvergleich (Ortszeit)
                    if stempel >= grenze_24h:
                        juenger += 1
                    zuletzt = max(zuletzt, stempel)
        except Exception:  # noqa: BLE001 – Zaehlen darf den Versand nie stoeren
            return None
        bestand: dict = {"trainingsbilder": anzahl, "trainingsbilder_24h": juenger}
        if zuletzt:
            try:
                epoche = time.mktime(time.strptime(zuletzt, "%Y%m%d-%H%M%S"))
                bestand["trainingsbild_zuletzt"] = (
                    dt.datetime.fromtimestamp(epoche, dt.timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                )
            except (ValueError, OverflowError):
                pass
        return bestand

    def _sende(self, nutzlast: dict) -> None:
        lz = nutzlast["lebenszeichen"]
        if lz.get("modus") == "silent" and self.ordner is not None:
            bestand = self.bildbestand()
            # Ausdruecklich null: Ordner weg/unlesbar -> Datensammlung steht.
            # Ein fehlendes Feld hiesse dagegen „alter Agent".
            lz.update(bestand if bestand is not None else {"trainingsbilder": None})
        try:
            requests.post(
                self.url,
                json=nutzlast,
                headers={"x-ingest-token": self.token},
                timeout=self.TIMEOUT_S,
            ).raise_for_status()
        except Exception as e:  # noqa: BLE001
            self.fehler_in_folge += 1
            if self.fehler_in_folge == 1:  # nur den Beginn einer Stoerung loggen
                log.warning("Lebenszeichen an die App nicht zugestellt: %s", e)
            return
        if self.fehler_in_folge:
            log.info(
                "Lebenszeichen wieder zugestellt (nach %d Fehlversuchen)",
                self.fehler_in_folge,
            )
        self.fehler_in_folge = 0


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


# Objektklassen des Austreibungs-Overrides (kein Zeitfilter, kein Tracking).
OBJEKT_KLASSEN = ("amniotic_sac", "calf_legs")


# Keypoints unter dieser Konfidenz gelten als verdeckt. Das ist die
# Sichtbarkeitsgrenze von Ultralytics (setzt solche Punkte auf (0, 0)),
# kein Fach-Schwellenwert – deshalb bewusst nicht konfigurierbar.
KEYPOINT_SICHTBAR_AB = 0.5


def schwanzwinkel_grad(spine, basis, spitze) -> float | None:
    """Winkel zwischen Rueckenlinie und Schwanz in Grad (0 = anliegend).

    Reine Mathematik ohne numpy: Agent, Abnahme-Skript
    (training/abnahme.py) und Tests rechnen mit genau dieser Formel.
    Punkte sind (x, y)-Paare; None bei unbrauchbarer Geometrie.
    """
    try:
        sx, sy = float(spine[0]), float(spine[1])
        bx, by = float(basis[0]), float(basis[1])
        tx, ty = float(spitze[0]), float(spitze[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not all(math.isfinite(v) for v in (sx, sy, bx, by, tx, ty)):
        return None
    rx, ry = bx - sx, by - sy   # Vektor entlang der Rueckenlinie
    wx, wy = tx - bx, ty - by   # Vektor des Schwanzes
    if math.hypot(rx, ry) < 1 or math.hypot(wx, wy) < 1:
        return None
    return abs(math.degrees(math.atan2(rx * wy - ry * wx, rx * wx + ry * wy)))


class InferenceEngine:
    """Kapselt Ultralytics-YOLO; ohne Modellpfad bleibt sie inaktiv."""

    def __init__(self, cfg: dict):
        self.cfg = cfg["modell"]
        self.kp = self.cfg["keypoints"]
        self.klassen = {int(v): k for k, v in self.cfg["klassen"].items()}
        # Nur diese Klassen sind Tiere (Tracking, Schwanzwinkel, Brunst).
        # Bisher galt jede Box als Kuh, die nicht Fruchtblase/Fuesse war: Mit
        # einem allgemeinen Modell haette ein Mensch hinter einer Kuh einen
        # Brunstverdacht ausgeloest (docs/ein-edge-agent-spezifikation.md, U2).
        self.tier_klassen = set(self.cfg.get("tier_klassen") or ["kuh"])
        # Klassenfilter fuer den Tracker: Tiere + Fruchtblase/Fuesse. Andere
        # Boxen (Mensch, Fahrzeug) stehlen sonst Track-IDs. Unbekannte Namen
        # -> kein Filter (Standardmodell: alle drei Klassen, also unveraendert).
        bekannt = {k: v for v, k in self.klassen.items()}
        filter_namen = self.tier_klassen | set(OBJEKT_KLASSEN)
        self.klassen_filter: list[int] | None = sorted(
            bekannt[n] for n in filter_namen if n in bekannt
        ) or None
        if not self.tier_klassen & set(bekannt):
            log.warning(
                "modell.tier_klassen %s kommt in modell.klassen nicht vor – "
                "es wird keine Kuh erkannt.", sorted(self.tier_klassen),
            )
        # Eigene Tracker-Konfiguration (z. B. tracker-kuh.yaml mit grossem
        # track_buffer fuer 1 FPS); leer -> Ultralytics-Default.
        self.tracker = (self.cfg.get("tracker") or "").strip() or "bytetrack.yaml"
        self.modell = None
        # Fruchtblase/Kaelberfuesse des aktuellen Frames, VOR dem Tracker
        # abgegriffen (_merke_objekte). None = Callback lief nicht.
        self._roh_objekte: list[ObjektErkennung] | None = None
        self._merke_fehler = 0          # aufeinanderfolgende Fehlschlaege
        self._merke_traceback: float | None = None  # letzter voller Traceback
        pfad = (self.cfg.get("pfad") or "").strip()
        if pfad:
            if alte_cpu.alte_cpu_aktiv(self.cfg.get("alte_cpu", "auto")):
                # Vor dem ersten Import von ultralytics (U1).
                log.info("Alte CPU ohne AVX: %s.", ", ".join(alte_cpu.aktiviere()))
            from ultralytics import YOLO  # Import nur bei Bedarf (Silent Mode braucht es nicht)

            log.info("Lade Modell %s (Tracker: %s) …", pfad, self.tracker)
            self.modell = YOLO(pfad)
            # Vor dem ersten track() registrieren: Ultralytics haengt seine
            # Tracker-Callbacks erst dann an, dieser laeuft also davor.
            self.modell.add_callback("on_predict_postprocess_end", self._merke_objekte)

    @property
    def aktiv(self) -> bool:
        return self.modell is not None

    def _merke_objekte(self, predictor) -> None:
        """Fruchtblase/Kaelberfuesse aus den Erkennungen VOR dem Tracker.

        Ultralytics kuerzt nach dem Tracking die Ergebnisse auf bestaetigte
        Tracks, sobald eine Kuh getrackt wird. Ein neues Objekt ist im
        ersten Bild nur unbestaetigt und faellt weg; flackernde Erkennungen
        kommen nie an. Die Austreibung hat bewusst keinen Zeitfilter
        (Recall 100 %) — jede einzelne Erkennung muss die Logik erreichen.
        """
        objekte: list[ObjektErkennung] = []
        try:
            boxen = predictor.results[0].boxes
            for i in range(len(boxen) if boxen is not None else 0):
                name = self.klassen.get(int(boxen.cls[i]))
                if name in OBJEKT_KLASSEN:
                    objekte.append(ObjektErkennung(
                        name, float(boxen.conf[i]), tuple(float(v) for v in boxen.xyxy[i])
                    ))
        except Exception:  # noqa: BLE001 – Rueckfall auf das Tracker-Ergebnis
            # Bei 1 FPS waere ein Traceback je Bild bis zu 86.400/Tag auf der
            # Karte: hoechstens einer pro Stunde, dazwischen ein Zaehler.
            self._merke_fehler += 1
            jetzt = time.time()
            if self._merke_traceback is None or jetzt - self._merke_traceback >= 3600:
                self._merke_traceback = jetzt
                log.exception("Objekte vor dem Tracker nicht lesbar – nutze Tracker-Ergebnis")
            elif self._merke_fehler % 3600 == 0:
                log.error("Objekte vor dem Tracker weiter nicht lesbar (%d Bilder in Folge)",
                          self._merke_fehler)
            return
        self._merke_fehler = 0
        self._roh_objekte = objekte

    def analysiere(
        self, frame: np.ndarray
    ) -> tuple[list[KuhBeobachtung], list[ObjektErkennung]]:
        """Ein Frame -> getrackte Kuehe (mit Schwanzwinkel) + Spezialobjekte."""
        self._roh_objekte = None
        ergebnis = self.modell.track(
            frame, persist=True, tracker=self.tracker, verbose=False,
            classes=self.klassen_filter,
        )[0]
        roh = self._roh_objekte

        kuehe: list[KuhBeobachtung] = []
        objekte: list[ObjektErkennung] = []
        boxen = ergebnis.boxes
        if boxen is None:
            return kuehe, roh if roh is not None else objekte

        kps = getattr(ergebnis, "keypoints", None)
        for i in range(len(boxen)):
            klass_idx = int(boxen.cls[i])
            konf = float(boxen.conf[i])
            box = tuple(float(v) for v in boxen.xyxy[i])
            name = self.klassen.get(klass_idx, f"klasse_{klass_idx}")

            if name in OBJEKT_KLASSEN:
                if roh is None:
                    objekte.append(ObjektErkennung(name, konf, box))
                continue
            if name not in self.tier_klassen:
                continue

            track_id = int(boxen.id[i]) if boxen.id is not None else -1
            punkte = None
            winkel = None
            if kps is not None and i < len(kps.xy):
                punkte = kps.xy[i].cpu().numpy()
                konf_kp = getattr(kps, "conf", None)
                winkel = self._schwanzwinkel(
                    punkte, konf_kp[i].cpu().numpy() if konf_kp is not None else None
                )
            kuehe.append(KuhBeobachtung(track_id, box, winkel, punkte))
        return kuehe, roh if roh is not None else objekte

    def _schwanzwinkel(self, punkte, konf=None) -> float | None:
        """Schwanzwinkel nur aus sichtbaren Keypoints, sonst None.

        Ultralytics meldet verdeckte Keypoints (Konfidenz < 0.5) als (0, 0).
        Ungeprueft entstuende aus einem verdeckten Schwanz ein Phantomwinkel
        gegen die Bildecke (oft > 45°), der ins 30-Minuten-Fenster zaehlt.
        None heisst: dieser Frame zaehlt fuer die Kuh nicht mit.
        """
        try:
            idx = (self.kp["spine_end"], self.kp["tail_base"], self.kp["tail_tip"])
            spine, basis, spitze = (punkte[i] for i in idx)
            if konf is not None and any(float(konf[i]) < KEYPOINT_SICHTBAR_AB for i in idx):
                return None
            if any(float(p[0]) == 0.0 and float(p[1]) == 0.0 for p in (spine, basis, spitze)):
                return None
        except (IndexError, KeyError, TypeError, ValueError):
            return None
        return schwanzwinkel_grad(spine, basis, spitze)


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
    # True = Takt bestimmt die LogicEngine, der Notifier-Cooldown gilt nicht
    # (Austreibung, Eskalation).
    sofort: bool = False
    # Austreibungs-Episode, zu der die Meldung gehoert (Fehlalarm-Feedback).
    episode: int | None = None


# Austreibungs-Episode endet, wenn ein Bild OHNE Erkennung kommt und die
# letzte Erkennung laenger als das her ist (Geburt abgeschlossen oder
# Fehlerkennung vorbei). Nach einem Stream-Ausfall entscheidet also das erste
# Bild: Zeigt es Blase/Fuesse, laeuft die Episode weiter (ggf. sofort
# Eskalation), sonst endet sie. Bewusst so belassen — beide moeglichen
# Fehler gehen in Recall-Richtung (docs/austreibung-episoden-spezifikation.md,
# Regel 4).
EPISODE_ENDE_S = 1800
# Nach einem „Fehlalarm"-Votum meldet die naechste Erkennung sofort neu —
# aber nur, wenn das Objekt mindestens so lange weg war. Verhindert die
# Schleife Dauer-Fehlerkennung -> Tipp -> Sofortmeldung -> Tipp ...
NEUMELDUNG_LUECKE_S = 60


@dataclass
class LogicEngine:
    cfg: dict
    # pro Track-ID: deque von (zeitstempel, winkel_ueber_schwelle)
    puffer: dict[int, deque] = field(default_factory=lambda: defaultdict(deque))
    # laufende Aufsprung-Kandidaten: (id_oben, id_unten) -> startzeit
    brunst_paare: dict[tuple[int, int], float] = field(default_factory=dict)
    # Kalbeverdacht-Serien je Track-ID: [erste Meldung, letzte Meldung,
    # letzte zugestellte Meldung, groesste Luecke seit dieser]. Nach einer
    # Meldung beginnt das Fenster neu (p.clear()); ohne Serie saehe jede
    # Folgemeldung wie eine frische Kurzbeobachtung aus.
    serien: dict[int, list[float]] = field(default_factory=dict)
    # Letztes auswertbares Bild je Track-ID (fuer die Luecken der Serie).
    zuletzt_bild: dict[int, float] = field(default_factory=dict)
    # Austreibungs-Episode (docs/austreibung-episoden-spezifikation.md):
    # Beginn (erste Fruchtblasen-/Fuesse-Erkennung), letzte Erkennung,
    # letzte Meldung (Beginn/Erinnerung/Eskalation), laufende Nummer.
    austreibung_start: float | None = None
    austreibung_zuletzt: float | None = None
    austreibung_gemeldet: float | None = None
    episode_nr: int = 0
    eskaliert: bool = False
    # Landwirt hat eine Meldung dieser Episode als Fehlalarm markiert.
    neu_nach_fehlalarm: bool = False

    def __post_init__(self):
        lg = self.cfg["logik"]
        self.winkel_schwelle = float(lg["winkel_schwelle_grad"])
        self.fenster_s = float(lg["fenster_minuten"]) * 60
        self.anteil_schwelle = float(lg["anteil_schwelle"])
        self.override_konf = float(lg["override_konfidenz"])
        self.brunst_dauer = float(lg["brunst_min_dauer_s"])
        self.eskalation_s = float(lg.get("eskalation_minuten", 60)) * 60
        # Erinnerungstakt der Austreibung; leer = bisheriger Cooldown, damit
        # sich fuer bestehende Konfigurationen nichts aendert.
        erinnerung = lg.get("austreibung_erinnerung_minuten") or (
            (self.cfg.get("telegram") or {}).get("cooldown_minuten", 15)
        )
        self.erinnerung_s = max(1.0, float(erinnerung)) * 60
        # Derselbe Wert wie Notifier.cooldown_s: Nur jede cooldown-te
        # Kalbeverdacht-Meldung je Kuh erreicht den Landwirt. Der Text einer
        # Folgemeldung muss sich auf die letzte ZUGESTELLTE Meldung beziehen
        # (setzt cooldown <= Fenster voraus, Default 15 <= 30 min).
        self.cooldown_s = float((self.cfg.get("telegram") or {}).get("cooldown_minuten", 15)) * 60
        self.min_stichprobe = 20  # so viele Frames noetig, bevor der Filter urteilt
        # Wach-Modus (kurz vor Kalbetermin): empfindlichere Schwellen nur dann,
        # wenn der Landwirt ihn bewusst scharfschaltet.
        if lg.get("wach_modus"):
            self.anteil_schwelle *= 0.5
            self.brunst_dauer = max(2.0, self.brunst_dauer * 0.5)
            self.min_stichprobe = 10
            log.info("Wach-Modus aktiv: gesenkte Alarm-Schwellen.")

    def bewerte(
        self, kuehe: list[KuhBeobachtung], objekte: list[ObjektErkennung]
    ) -> list[Alarm]:
        jetzt = time.time()
        alarme: list[Alarm] = []

        # 1) Harter Override: Fruchtblase / Kaelberfuesse. Den Takt bestimmt
        # allein die Episode, nicht der Notifier-Cooldown.
        treffer = [o for o in objekte if o.konfidenz >= self.override_konf]
        if treffer:
            # Blase und Fuesse im selben Bild = eine Meldung.
            alarme.extend(self._austreibung(max(treffer, key=lambda o: o.konfidenz), jetzt))
        elif (
            self.austreibung_zuletzt is not None
            and jetzt - self.austreibung_zuletzt > EPISODE_ENDE_S
        ):
            self._beende_episode()

        # 2) Statistischer Zeitfilter pro Kuh (Schwanzwinkel)
        for kuh in kuehe:
            if kuh.track_id < 0 or kuh.winkel_grad is None:
                continue
            p = self.puffer[kuh.track_id]
            p.append((jetzt, kuh.winkel_grad > self.winkel_schwelle))
            vorher = self.zuletzt_bild.get(kuh.track_id)
            self.zuletzt_bild[kuh.track_id] = jetzt
            serie = self.serien.get(kuh.track_id)
            if serie is not None and vorher is not None:
                serie[3] = max(serie[3], jetzt - vorher)
            while p and p[0][0] < jetzt - self.fenster_s:
                p.popleft()
            if len(p) >= self.min_stichprobe:
                anteil = sum(1 for _, ueber in p if ueber) / len(p)
                if anteil > self.anteil_schwelle:
                    alarme.append(
                        Alarm(
                            "kalbeverdacht",
                            f"Kuh #{kuh.track_id}",
                            self._kalbe_text(kuh.track_id, p, anteil, jetzt),
                            None,
                            kuh.box,
                        )
                    )
                    p.clear()  # Fenster neu aufbauen, Cooldown uebernimmt der Notifier

        # Fenster verschwundener IDs freigeben (ID-Wechsel, Kuh weg). Ihr
        # Inhalt waere bei Rueckkehr ohnehin aelter als das Fenster;
        # ohne Freigabe waechst der Speicher mit jedem ID-Wechsel.
        for tid in [t for t, q in self.puffer.items() if not q or q[-1][0] < jetzt - self.fenster_s]:
            del self.puffer[tid]
        for tid in [t for t, s in self.serien.items() if jetzt - s[1] > self.fenster_s]:
            del self.serien[tid]
        for tid in [t for t, z in self.zuletzt_bild.items() if jetzt - z > self.fenster_s]:
            del self.zuletzt_bild[tid]

        # 3) Brunst: Aufsprung = zwei Boxen ueberlappen, eine deutlich oberhalb
        alarme.extend(self._brunst(kuehe, jetzt))
        return alarme

    @staticmethod
    def _dauer(sekunden: float) -> str:
        """Abgerundet: nie mehr Beobachtung behaupten als belegt."""
        sekunden = max(0.0, sekunden)
        if sekunden < 120:
            return f"{int(sekunden)} s"
        minuten = int(sekunden // 60)
        if minuten < 120:
            return f"{minuten} min"
        return f"{minuten // 60} h {minuten % 60} min"

    def _kalbe_text(self, tid: int, p: deque, anteil: float, jetzt: float) -> str:
        """Kalbeverdacht mit Beleg: Anteil, Bildzahl und beobachtete Spanne.

        Erste Meldung einer Serie: kurze Spanne (neue Nummer, Neustart,
        Schwanz lange verdeckt) sagt der Text und bittet um Pruefung am
        Bild. Folgemeldung (letzte Meldung dieser Nummer juenger als das
        Fenster): nennt die Dauer der Serie, nie den Kurztext.
        """
        ueber = sum(1 for _, u in p if u)
        serie = self.serien.get(tid)
        if serie is not None and jetzt - serie[1] <= self.fenster_s:
            # Groesste Luecke ohne auswertbares Bild seit der letzten
            # ZUGESTELLTEN Meldung (dazwischen liegende schluckt der Cooldown).
            # Nur ohne Luecke ist "weiterhin … immer wieder" belegt.
            luecke = serie[3]
            seit = self._dauer(jetzt - serie[0])
            serie[1] = jetzt
            if jetzt - serie[2] >= self.cooldown_s:  # diese Meldung kommt an
                serie[2], serie[3] = jetzt, 0.0
            if luecke < self.fenster_s / 6:
                return (
                    f"Schwanz weiterhin über {self.winkel_schwelle:.0f}° angehoben: seit "
                    f"{seit} immer wieder auffällig (zuletzt {ueber} von {len(p)} Bildern "
                    f"in {self._dauer(jetzt - p[0][0])}). Bitte auf Wehenzeichen achten."
                )
            return (
                f"Schwanz erneut über {self.winkel_schwelle:.0f}° angehoben ({ueber} von "
                f"{len(p)} auswertbaren Bildern). Erste Meldung vor {seit}, dazwischen "
                f"{self._dauer(luecke)} kein auswertbares Bild. Bitte am Bild prüfen, "
                "ob Wehenzeichen vorliegen."
            )
        self.serien[tid] = [jetzt, jetzt, jetzt, 0.0]
        spanne_s = max(0.0, jetzt - p[0][0])
        spanne = self._dauer(spanne_s)
        kopf = (
            f"Schwanz in {anteil * 100:.0f} % der auswertbaren Bilder über "
            f"{self.winkel_schwelle:.0f}° angehoben ({ueber} von {len(p)} Bildern, "
        )
        if spanne_s >= self.fenster_s / 2:
            return (
                f"{kopf}beobachtet in den letzten {spanne}). "
                "Bitte in der nächsten halben Stunde auf Wehenzeichen achten."
            )
        return (
            f"{kopf}beobachtet erst seit {spanne} – neue Nummer, Neustart oder "
            "Schwanz lange verdeckt). Bitte am Bild prüfen, ob nur Koten oder "
            "Fliegenabwehr vorlag."
        )

    def _austreibung(self, o: ObjektErkennung, jetzt: float) -> list[Alarm]:
        """Austreibungs-Takt: Sofort-Meldung bei Episodenbeginn, Erinnerung
        im Takt, Eskalation einmal pro Episode, Neumeldung nach Fehlalarm."""
        objekt = "Fruchtblase" if o.klasse == "amniotic_sac" else "Kälberfüße"
        letzte_erkennung = self.austreibung_zuletzt
        self.austreibung_zuletzt = jetzt

        def meldung(kuh_id: str | None, text: str) -> Alarm:
            self.austreibung_gemeldet = jetzt
            return Alarm(
                "austreibung", kuh_id, text, o.konfidenz, o.box,
                sofort=True, episode=self.episode_nr,
            )

        if letzte_erkennung is None:
            self.episode_nr += 1
            self.austreibung_start = jetzt
            self.eskaliert = False
            self.neu_nach_fehlalarm = False
            return [meldung(None, f"{objekt} erkannt (Konfidenz {o.konfidenz:.0%}) – Austreibungsphase!")]

        # Eskalation (Komplikationsverdacht): Austreibung laeuft, aber nach
        # eskalation_minuten sind immer noch Fruchtblase/Fuesse sichtbar ->
        # Geburt macht keinen Fortschritt, Kontrolle noetig. Ersetzt im selben
        # Bild die Erinnerung. Ein Fehlalarm-Votum verschiebt sie nie.
        dauer_s = jetzt - self.austreibung_start
        if not self.eskaliert and dauer_s >= self.eskalation_s:
            self.eskaliert = True
            return [meldung(
                "Eskalation",
                f"⚠️ KEIN GEBURTSFORTSCHRITT: Austreibungsphase läuft "
                f"seit {dauer_s / 60:.0f} Minuten, {objekt} "
                "weiterhin sichtbar – bitte sofort kontrollieren!",
            )]

        if self.neu_nach_fehlalarm and jetzt - letzte_erkennung >= NEUMELDUNG_LUECKE_S:
            self.neu_nach_fehlalarm = False
            return [meldung(
                None,
                f"{objekt} erneut erkannt (Konfidenz {o.konfidenz:.0%}) – die vorige "
                "Meldung wurde als Fehlalarm markiert, bitte prüfen!",
            )]

        if jetzt - self.austreibung_gemeldet >= self.erinnerung_s:
            return [meldung(
                None,
                f"Austreibung läuft weiter seit {dauer_s / 60:.0f} min – {objekt} "
                f"weiterhin sichtbar (Konfidenz {o.konfidenz:.0%}).",
            )]
        return []

    def _beende_episode(self) -> None:
        self.austreibung_start = None
        self.austreibung_zuletzt = None
        self.austreibung_gemeldet = None
        self.eskaliert = False
        self.neu_nach_fehlalarm = False

    def fehlalarm_gemeldet(self, typ: str, episode: int | None) -> None:
        """Rueckmeldung „❌ Fehlalarm" aus der Feedback-Schleife. Betrifft nur
        eine Meldung der LAUFENDEN Austreibungs-Episode: Die naechste
        Erkennung nach einer Pause meldet dann sofort neu (Fall: echte
        Austreibung kurz nach einem Fehlalarm). Erinnerung und Eskalation
        laufen unveraendert weiter — ein versehentlicher Tipp macht nie
        stiller als ohne Feedback."""
        if (
            typ == "austreibung"
            and episode is not None
            and episode == self.episode_nr
            and self.austreibung_zuletzt is not None
        ):
            self.neu_nach_fehlalarm = True
            log.info("Austreibungs-Episode %d als Fehlalarm markiert", episode)

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

class Versandkanal:
    """Ein Versand-Thread mit begrenzter Warteschlange (Spezifikation
    docs/versand-entkopplung-spezifikation.md).

    Die Analyseschleife darf nie auf das Netz warten: Ein haengender POST
    (WLAN verschluckt Pakete, Timeout laeuft voll aus) hielt sonst pro Alarm
    bis zu 80 s die Bildauswertung an. Auftraege werden hier nur eingereiht;
    der Thread arbeitet sie in Reihenfolge ab. Laeuft die Warteschlange
    ueber, faellt zuerst der aelteste NICHT dringende Auftrag heraus — eine
    Austreibung (prio=True) wird nie zugunsten von Routine verdraengt. Ein
    Fehler in einem Auftrag beendet den Thread nie.
    """

    def __init__(self, name: str, max_auftraege: int):
        self.name = name
        self.max_auftraege = max(1, int(max_auftraege))
        self.verworfen = 0
        self._auftraege: deque[tuple] = deque()  # (prio, fn, args, kwargs)
        self._offen = 0  # eingereiht + laufend
        self._cv = threading.Condition()
        threading.Thread(
            target=self._arbeite, name=f"versand-{name}", daemon=True
        ).start()

    def auftrag(self, fn, *args, prio: bool = False, **kwargs) -> None:
        """Reiht einen Auftrag ein. Kehrt sofort zurueck, wirft nie.

        Dringende Auftraege (prio=True) ueberholen wartende Routine-Auftraege
        (untereinander bleibt die Reihenfolge). Bei Ueberlauf faellt der
        aelteste Routine-Auftrag heraus; warten nur dringende, wird ein neuer
        Routine-Auftrag selbst verworfen — ein dringender nie fuer Routine."""
        with self._cv:
            if len(self._auftraege) >= self.max_auftraege:
                opfer = next(
                    (i for i, a in enumerate(self._auftraege) if not a[0]), None
                )
                self.verworfen += 1
                if opfer is None and not prio:
                    log.warning(
                        "Versand %s ueberlastet – neuer Routine-Auftrag verworfen (%d)",
                        self.name,
                        self.verworfen,
                    )
                    return
                if opfer is None:
                    opfer = 0  # nur dringende: der aelteste dringende weicht
                war_dringend = self._auftraege[opfer][0]
                del self._auftraege[opfer]
                self._offen -= 1
                log.warning(
                    "Versand %s ueberlastet – aeltester %sAuftrag verworfen (%d)",
                    self.name,
                    "DRINGENDER " if war_dringend else "",
                    self.verworfen,
                )
            eintrag = (prio, fn, args, kwargs)
            if prio:
                vor = next(
                    (i for i, a in enumerate(self._auftraege) if not a[0]),
                    len(self._auftraege),
                )
                self._auftraege.insert(vor, eintrag)
            else:
                self._auftraege.append(eintrag)
            self._offen += 1
            self._cv.notify_all()

    def _arbeite(self) -> None:
        while True:
            with self._cv:
                while not self._auftraege:
                    self._cv.wait()
                _, fn, args, kwargs = self._auftraege.popleft()
            try:
                fn(*args, **kwargs)
            except Exception:  # noqa: BLE001 – der Worker darf nie sterben
                log.exception("Versand %s: Auftrag fehlgeschlagen", self.name)
            finally:
                with self._cv:
                    self._offen -= 1
                    self._cv.notify_all()

    def warte(self, timeout: float = 5.0) -> bool:
        """Wartet, bis alle Auftraege erledigt sind (Tests, Diagnose)."""
        with self._cv:
            return self._cv.wait_for(lambda: self._offen == 0, timeout)


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
    MAX_ABGESTIMMT = 200   # gemerkte, bereits gezaehlte Feedback-IDs (RAM)
    POLL_INTERVALL_S = 10  # getUpdates-Kurz-Poll
    # Haengt ein Abruf laenger (oder fiel er aus der Warteschlange), wird die
    # Sperre freigegeben — sonst waere das Feedback bis zum Neustart taub.
    ABRUF_SPERRE_MAX_S = 120

    def __init__(self, cfg: dict, kanal: Versandkanal | None = None):
        # Mit Kanal laufen Abruf und Antworten im Versand-Thread; ohne Kanal
        # (Tests, Einzelbetrieb) synchron wie bisher.
        self._kanal = kanal
        self._eingang: queue.Queue = queue.Queue()
        self._abruf_seit: float | None = None
        tg = cfg.get("telegram") or {}
        self.token = (tg.get("token") or "").strip()
        GEHEIM.merke(self.token)
        self.chat = str(tg.get("chat_id") or "").strip()
        self.aktiv = bool(tg.get("feedback_buttons", True)) and bool(
            self.token and self.chat
        )
        self.ordner = Path(tg.get("fehlalarm_ordner") or "./aufnahmen/fehlalarme")
        self.zaehler: dict[str, int] = {"treffer": 0, "fehlalarm": 0}
        self._offen: dict[str, tuple[str, list[bytes]]] = {}
        # Feedback-IDs, deren erstes Votum schon gezaehlt ist (geordnet,
        # aelteste zuerst). Getrennt von _offen: dort fehlt auch, was die
        # RAM-Grenze verdraengt hat — ein Votum darauf ist echt und zaehlt.
        self._abgestimmt: dict[str, None] = {}
        # Austreibungs-Episode je Feedback-ID (nur Austreibungs-Alarme).
        self._episode: dict[str, int] = {}
        self._reihenfolge: deque[str] = deque()
        self._naechste_id = 0
        self._offset = 0
        self._letzter_poll = 0.0
        # Wird von main() gesetzt, sobald das Archiv steht. Bewusst optional:
        # Ohne Archiv laeuft die Feedback-Schleife unveraendert weiter.
        self.archiv: DatensatzArchiv | None = None
        # Von main() gesetzt: (typ, episode) eines als Fehlalarm markierten
        # Alarms an die LogicEngine (Austreibungs-Takt).
        self.bei_fehlalarm = None

    def registriere(self, alarm: Alarm, bilder: list[bytes]) -> dict | None:
        """Merkt die (unannotierten) Alarm-Bilder fuer spaeteres Feedback und
        liefert das Telegram-reply_markup — oder None, wenn Feedback aus ist."""
        if not self.aktiv or alarm.typ == "info":
            return None
        fid = str(self._naechste_id)
        self._naechste_id += 1
        # Nach einem Neustart kann ein Votum auf eine Alt-Nachricht diese ID
        # schon belegt haben; der neue Alarm beginnt unabgestimmt.
        self._abgestimmt.pop(fid, None)
        self._offen[fid] = (alarm.typ, [b for b in bilder if b])
        if alarm.episode is not None:
            self._episode[fid] = alarm.episode
        self._reihenfolge.append(fid)
        while len(self._reihenfolge) > self.MAX_OFFEN:
            alt = self._reihenfolge.popleft()
            self._offen.pop(alt, None)
            self._episode.pop(alt, None)
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
        sich aus).

        Mit Kanal blockiert tick() nie: Der Abruf laeuft im Versand-Thread,
        VERARBEITET wird hier im Hauptthread (bei_fehlalarm greift in die
        LogicEngine). Hoechstens ein Abruf gleichzeitig — der naechste erst,
        wenn das Ergebnis des vorigen verarbeitet ist."""
        if not self.aktiv:
            return
        t = time.time() if jetzt is None else jetzt
        if self._kanal is not None:
            self._tick_entkoppelt(t)
            return
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

    def _tick_entkoppelt(self, t: float) -> None:
        while True:
            try:
                updates = self._eingang.get_nowait()
            except queue.Empty:
                break
            self._abruf_seit = None
            self.verarbeite(updates)
        if self._abruf_seit is not None:
            if t - self._abruf_seit < self.ABRUF_SPERRE_MAX_S:
                return
            log.warning("Feedback-Abruf haengt – Sperre freigegeben")
            self._abruf_seit = None
        if t - self._letzter_poll < self.POLL_INTERVALL_S:
            return
        self._letzter_poll = t
        self._abruf_seit = t
        self._kanal.auftrag(self._abrufen, self._offset)

    def _abrufen(self, offset: int) -> None:
        """Laeuft im Versand-Thread. Legt IMMER ein Ergebnis ab (notfalls
        leer), damit die Sperre im Hauptthread wieder frei wird."""
        ergebnis: list[dict] = []
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{self.token}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 0,
                    "allowed_updates": '["callback_query"]',
                },
                timeout=10,
            )
            r.raise_for_status()
            ergebnis = r.json().get("result") or []
        except requests.RequestException as e:
            log.warning("Feedback-Abruf fehlgeschlagen: %s", e)
        except Exception:  # noqa: BLE001
            log.exception("Feedback-Abruf: unerwarteter Fehler")
        finally:
            self._eingang.put(ergebnis)

    def _netz(self, fn, *args) -> None:
        """Netz- oder Plattenaufruf ueber den Kanal (nicht blockierend) oder
        direkt (ohne Kanal, wie bisher)."""
        if self._kanal is not None:
            self._kanal.auftrag(fn, *args)
        else:
            fn(*args)

    def verarbeite(self, updates: list[dict]) -> None:
        for u in updates:
            update_id = int(u.get("update_id", 0))
            if update_id < self._offset:
                continue  # schon verarbeitet (z. B. Abruf nach Sperren-Freigabe)
            self._offset = update_id + 1
            cq = u.get("callback_query")
            if not cq:
                continue
            teile = str(cq.get("data") or "").split(":")
            antwort = "Danke!"
            if len(teile) == 3 and teile[0] == "fb" and teile[2] in self.zaehler:
                fid, urteil = teile[1], teile[2]
                if fid not in self._abgestimmt:
                    # Nur das erste Votum je Alarm zaehlt — ein Doppel-Tipp
                    # kommt mit neuer update_id und wuerde den Tagesbericht
                    # verfaelschen.
                    self.zaehler[urteil] += 1
                    self._abgestimmt[fid] = None
                    if len(self._abgestimmt) > self.MAX_ABGESTIMMT:
                        del self._abgestimmt[next(iter(self._abgestimmt))]
                eintrag = self._offen.pop(fid, None)
                episode = self._episode.pop(fid, None)
                if urteil == "fehlalarm" and eintrag and self.bei_fehlalarm is not None:
                    try:
                        self.bei_fehlalarm(eintrag[0], episode)
                    except Exception:  # noqa: BLE001 – Feedback laeuft weiter
                        log.exception("Fehlalarm-Rueckmeldung an die Logik gescheitert")
                if eintrag is not None:
                    # Nur beim ersten Votum — ein Doppel-Tipp erzeugt keine
                    # weiteren Telegram-Auftraege.
                    self._netz(self._entferne_buttons, cq)
                if urteil == "fehlalarm":
                    # Schreiben im Hintergrund — die Platte (SD-Karte) darf die
                    # Analyse so wenig aufhalten wie das Netz. Geantwortet wird
                    # erst danach und nur mit dem, was wirklich auf der Platte ist.
                    self._netz(self._speichere_und_antworte, cq, fid, eintrag)
                    continue
            self._netz(self._antworte, cq, antwort)

    def _speichere_und_antworte(
        self, cq: dict, fid: str, eintrag: tuple[str, list[bytes]] | None
    ) -> None:
        try:
            anzahl = self._speichere(fid, eintrag)
        except Exception:  # noqa: BLE001 – volle/defekte Platte stoppt nichts
            log.exception("Fehlalarm-Bilder konnten nicht gespeichert werden")
            text = "Danke – notiert. Bilder konnten NICHT gespeichert werden (Log prüfen)."
        else:
            text = (
                f"Danke – {anzahl} Bild(er) fürs Nachtraining gespeichert."
                if anzahl
                else "Danke – notiert (Bilder lagen nicht mehr vor)."
            )
        self._antworte(cq, text)

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
    """Versendet Alarme; Cooldown pro (Kuh, Typ) verhindert Spam bei Kalbe-
    und Brunstverdacht. Austreibung/Eskalation (``alarm.sofort``) takten in
    der LogicEngine und gehen immer raus.

    Kein Netzzugriff im Hauptthread: Telegram und Dashboard haben je einen
    eigenen Versand-Thread (docs/versand-entkopplung-spezifikation.md).
    Ein haengendes Telegram haelt die App-Meldung (und damit den Push) nicht
    auf, und umgekehrt."""

    TELEGRAM_WARTESCHLANGE_MAX = 50
    # Steht etwas im Offline-Puffer, wird erneut gesendet — auch ohne neuen
    # Alarm (vorher erst mit dem naechsten Alarm, in einer ruhigen Nacht also
    # gar nicht). Nach Fehlschlaegen verdoppelt sich der Abstand bis
    # NACHLIEFER_MAX_S; ein neues Ereignis loest immer sofort einen Versuch aus.
    NACHLIEFER_INTERVALL_S = 60
    NACHLIEFER_MAX_S = 900
    # Server-Grenzen: /api/events nimmt hoechstens 100 Ereignisse je Stapel,
    # Vercel hoechstens 4,5 MB je Anfrage. Mit Abstand darunter bleiben —
    # ein zu grosser Rueckstau blockierte sonst App und Push dauerhaft.
    MAX_STAPEL = 50
    MAX_STAPEL_BYTES = 3_000_000

    def __init__(self, cfg: dict):
        tg = cfg.get("telegram") or {}
        self.tg_token = (tg.get("token") or "").strip()
        GEHEIM.merke(self.tg_token)
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
        puffer_max = int(db.get("puffer_max", 200))
        if puffer_max < 1:
            # 0 haette jedes Ereignis schon beim Einreihen verworfen — App und
            # Push waeren still, ohne dass es jemand merkt.
            log.warning(
                "dashboard.puffer_max=%d ist zu klein – verwende 1", puffer_max
            )
            puffer_max = 1
        self._puffer: deque[dict] = deque(maxlen=puffer_max)
        # Outbox: Der Hauptthread haengt nur an (unter Lock). Der Dashboard-
        # Thread sendet und entfernt; ein eigener Sicherungs-Thread schreibt
        # die Pufferdatei (genau ein Schreiber, nie durch das Netz
        # aufgehalten). _version zaehlt jede Aenderung, damit die Datei nur bei
        # Bedarf neu geschrieben wird (bis ~80 MB bei vollem Puffer).
        self._puffer_lock = threading.Lock()
        self._puffer_version = 0
        self._puffer_gesichert = 0
        self._db_fehler_in_folge = 0
        self._db_letzter_fehler = ""
        self._puffer_laden()

        self.kamera = cfg["stream"].get("kamera", "stallwache")
        self._zuletzt: dict[tuple[str | None, str], float] = {}
        # Alarme und Feedback getrennt: Button-Antworten koennen Alarme in der
        # Warteschlange nie verdraengen.
        self._tg = Versandkanal("telegram", self.TELEGRAM_WARTESCHLANGE_MAX)
        self._tg_feedback = Versandkanal("telegram-feedback", 50)
        self._outbox_signal: queue.Queue = queue.Queue()
        self._sicherung_signal = threading.Event()
        if self.db_url and self.db_token:
            threading.Thread(
                target=self._sicherung_arbeite, name="puffer-sicherung", daemon=True
            ).start()
            threading.Thread(
                target=self._outbox_arbeite, name="versand-dashboard", daemon=True
            ).start()
            if self._puffer:
                # Puffer aus dem vorigen Lauf sofort nachliefern, nicht erst
                # nach NACHLIEFER_INTERVALL_S.
                self._outbox_signal.put(None)
        self.feedback = FeedbackSchleife(cfg, kanal=self._tg_feedback)

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
        if not alarm.sofort and jetzt - self._zuletzt.get(schluessel, 0) < self.cooldown_s:
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

        # Nur einreihen — gesendet wird in den Versand-Threads.
        self._tg.auftrag(self._telegram, alarm, bild, serie, markup, prio=alarm.sofort)
        self._dashboard(alarm, self._dashboard_bilder(serie, bild))
        self._mqtt(alarm)

    def status(self, nachricht: str) -> None:
        """Info-Meldung nur ans Dashboard (kein Telegram-Weckruf)."""
        log.info(nachricht)
        meldung = Alarm("info", None, nachricht, None, None)
        self._dashboard(meldung)
        self._mqtt(meldung)

    def wichtig(self, nachricht: str) -> None:
        """Systemmeldung, die den Landwirt aktiv erreichen soll (Telegram +
        Dashboard + MQTT). Fuer Totmann-/Entwarnungsmeldungen — bewusst ohne
        Cooldown: der TotmannWaechter stellt Einmaligkeit pro Episode sicher."""
        log.warning(nachricht)
        meldung = Alarm("info", None, nachricht, None, None)
        self._tg.auftrag(self._telegram, meldung, None, prio=True)
        self._dashboard(meldung)
        self._mqtt(meldung)

    def digest_tick(self, analyse_aktiv: bool) -> None:
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
            f"Modus: {'Analyse' if analyse_aktiv else 'Silent Mode (Datensammlung)'}\n"
            f"Kalbeverdacht: {z['kalbeverdacht']} · Austreibung: {z['austreibung']} · "
            f"Brunstverdacht: {z['brunstverdacht']}\n"
            f"Agent läuft seit {stunden:.1f} h · Kamera: {self.kamera}"
        )
        fb = self.feedback.zaehler
        if fb["treffer"] or fb["fehlalarm"]:
            text += f"\nFeedback: ✅ {fb['treffer']} Treffer · ❌ {fb['fehlalarm']} Fehlalarm"
            fb["treffer"] = fb["fehlalarm"] = 0
        self._zaehler.clear()
        self._tg.auftrag(self._digest_senden, text)

    def _digest_senden(self, text: str) -> None:
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data={"chat_id": self.tg_chat, "text": text},
                timeout=20,
            ).raise_for_status()
        except requests.RequestException as e:
            log.error("Digest-Versand fehlgeschlagen: %s", e)

    def warte(self, timeout: float = 5.0) -> bool:
        """Wartet, bis Telegram- und Dashboard-Versand nichts mehr offen
        haben und die Outbox gesichert ist (Tests, Diagnose). Die Analyse ruft
        das nie auf."""
        ende = time.monotonic() + timeout
        ok = self._tg.warte(timeout) and self._tg_feedback.warte(
            max(0.0, ende - time.monotonic())
        )
        while self._outbox_signal.unfinished_tasks or (
            self.db_url and self.db_token and self._puffer_gesichert != self._puffer_version
        ):
            if time.monotonic() > ende:
                return False
            time.sleep(0.01)
        return ok

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
    ) -> None:
        if not (self.tg_token and self.tg_chat):
            return
        markup_json = json.dumps(markup) if markup else None
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
    # Dashboard-Meldung mit Offline-Puffer (Outbox)
    #
    # Der Stall ist der Ort mit dem schlechtesten Empfang des Betriebs. Faellt
    # die Leitung aus, darf ein Kalbealarm nicht einfach verschwinden: Jedes
    # Ereignis kommt zuerst in die Outbox, der Dashboard-Thread sichert sie
    # auf die Platte und sendet alles Ausstehende als Stapel
    # (POST /api/events mit {"ereignisse": [...]}) — beim naechsten Ereignis
    # und spaetestens alle NACHLIEFER_INTERVALL_S.
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

    def _puffer_sichern(self, eintraege: list[dict], version: int) -> None:
        """Schreibt den Puffer atomar zurueck (erst temporaer, dann ersetzen).
        Nur aus dem Sicherungs-Thread aufrufen (ein Schreiber)."""
        if version == self._puffer_gesichert:
            return
        try:
            if not eintraege:
                self._puffer_datei.unlink(missing_ok=True)
            else:
                tmp = self._puffer_datei.with_suffix(".tmp")
                tmp.write_text(
                    "\n".join(json.dumps(e, ensure_ascii=False) for e in eintraege),
                    "utf-8",
                )
                tmp.replace(self._puffer_datei)
            self._puffer_gesichert = version
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

        # In die Outbox; senden und entfernen macht der Dashboard-Thread,
        # sichern der Sicherungs-Thread. Der Hauptthread fasst weder Netz noch
        # Pufferdatei an.
        verdraengt = None
        with self._puffer_lock:
            if len(self._puffer) == self._puffer.maxlen:
                verdraengt = self._puffer[0]
            self._puffer.append(ereignis)
            self._puffer_version += 1
        if verdraengt is not None:
            log.warning(
                "Offline-Puffer voll – aeltestes Ereignis verworfen: %s %s",
                verdraengt.get("typ"),
                verdraengt.get("zeit"),
            )
        self._sicherung_signal.set()
        self._outbox_signal.put(None)

    def _sicherung_arbeite(self) -> None:
        """Sicherungs-Thread: schreibt die Outbox bei jeder Aenderung auf die
        Platte. Eigener Thread, damit ein haengender POST die Sicherung eines
        neuen Alarms nie aufhaelt."""
        while True:
            self._sicherung_signal.wait()
            self._sicherung_signal.clear()
            try:
                with self._puffer_lock:
                    eintraege = list(self._puffer)
                    version = self._puffer_version
                self._puffer_sichern(eintraege, version)
            except Exception:  # noqa: BLE001 – der Worker darf nie sterben
                log.exception("Puffer-Sicherung: unerwarteter Fehler")

    def _wartezeit(self) -> float:
        """Abstand bis zum naechsten Nachlieferungsversuch: 60 s, nach
        Fehlschlaegen verdoppelt bis NACHLIEFER_MAX_S."""
        stufe = max(0, self._db_fehler_in_folge - 1)
        return min(
            float(self.NACHLIEFER_MAX_S),
            self.NACHLIEFER_INTERVALL_S * (2 ** min(stufe, 16)),
        )

    def _outbox_arbeite(self) -> None:
        """Dashboard-Thread: sendet bei jedem neuen Ereignis und — solange
        etwas aussteht — im Nachlieferungstakt."""
        while True:
            try:
                self._outbox_signal.get(timeout=self._wartezeit())
                signal = True
            except queue.Empty:
                signal = False
            try:
                self._nachliefern()
            except Exception:  # noqa: BLE001 – der Worker darf nie sterben
                log.exception("Dashboard-Versand: unerwarteter Fehler")
            finally:
                if signal:
                    self._outbox_signal.task_done()

    @staticmethod
    def _ist_app_ablehnung(r) -> bool:
        """400 mit der JSON-Antwort der App ({fehler} bzw. {ergebnisse}) —
        nicht die eines Proxys oder Captive-Portals."""
        try:
            koerper = r.json()
        except Exception:  # noqa: BLE001 – HTML, leer, kaputt
            return False
        return isinstance(koerper, dict) and (
            "fehler" in koerper or "ergebnisse" in koerper
        )

    def _sende_stapel(self, teil: list[dict]) -> str:
        """Ein POST. Ergebnis:
        "ok";
        "zu_gross" (413: Anfrage zu gross — teilen bzw. ohne Bilder senden);
        "abgelehnt" (400 von der App selbst: so nie annehmbar);
        "fehler" (Netz, 401, 5xx, fremde 400: spaeter erneut, nichts verwerfen).
        """
        try:
            r = requests.post(
                self.db_url,
                json={"ereignisse": teil},
                headers={"x-ingest-token": self.db_token},
                timeout=30,
            )
        except requests.RequestException as e:
            self._db_letzter_fehler = str(e)
            return "fehler"
        try:
            status = int(getattr(r, "status_code", 200) or 200)
        except (TypeError, ValueError):
            status = 200
        if status == 413:
            return "zu_gross"
        if status == 400 and self._ist_app_ablehnung(r):
            return "abgelehnt"
        try:
            r.raise_for_status()
        except requests.RequestException as e:
            self._db_letzter_fehler = str(e)
            return "fehler"
        return "ok"

    def _entferne(self, teil: list[dict]) -> None:
        """Entfernt genau diese Eintraege (Objekt-Identitaet, nicht Position)."""
        weg = {id(e) for e in teil}
        with self._puffer_lock:
            rest = [e for e in self._puffer if id(e) not in weg]
            self._puffer = deque(rest, maxlen=self._puffer.maxlen)
            self._puffer_version += 1
        self._sicherung_signal.set()

    def _teilstapel(self, reihe: list[dict], max_anzahl: int) -> list[dict]:
        """Nimmt vorn aus der Reihe, was unter Anzahl- und Byte-Grenze passt
        (mindestens ein Eintrag)."""
        teil: list[dict] = []
        groesse = 0
        for e in reihe[:max_anzahl]:
            n = len(json.dumps(e, ensure_ascii=False))
            if teil and groesse + n > self.MAX_STAPEL_BYTES:
                break
            teil.append(e)
            groesse += n
        return teil

    def _nachliefern(self) -> bool:
        """Sendet alles Ausstehende in Teilstapeln.

        - Vor JEDEM Teilstapel wird die Outbox neu gelesen und Austreibung/
          Eskalation vorgezogen: Ein frischer Alarm wartet hoechstens auf den
          gerade laufenden Teilstapel, nie auf den ganzen Rueckstau.
        - Nach Fehlschlaegen erst mit EINEM Ereignis tasten, statt jedes Mal
          den Rueckstau ueber den schwachen Uplink zu schieben.
        - 413 (zu gross): einzeln senden, ein einzelner Eintrag notfalls ohne
          Bilder. 400 der App selbst: einzeln; ein einzeln abgelehnter Eintrag
          geht ohne Bilder raus oder wird verworfen und protokolliert — er
          blockiert nie die Schlange. Fremde 400 (Proxy) gelten als Fehler:
          nichts wird verworfen.
        - Entfernt wird nur, was angenommen wurde (Objekt-Identitaet).
        """
        tasten = self._db_fehler_in_folge > 0
        einzeln: set[int] = set()
        geliefert = 0
        while True:
            with self._puffer_lock:
                stapel = list(self._puffer)
            if not stapel:
                break
            reihe = [e for e in stapel if e.get("typ") == "austreibung"] + [
                e for e in stapel if e.get("typ") != "austreibung"
            ]
            max_anzahl = 1 if (tasten or id(reihe[0]) in einzeln) else self.MAX_STAPEL
            teil = self._teilstapel(reihe, max_anzahl)
            ergebnis = self._sende_stapel(teil)
            if ergebnis in ("abgelehnt", "zu_gross") and len(teil) > 1:
                einzeln.update(id(e) for e in teil)
                continue
            if ergebnis in ("abgelehnt", "zu_gross"):
                e = teil[0]
                grund = ergebnis
                if e.get("bilder"):
                    ohne = {k: v for k, v in e.items() if k != "bilder"}
                    ergebnis = self._sende_stapel([ohne])
                    if ergebnis == "ok":
                        log.warning(
                            "Ereignis ohne Bilder nachgeliefert (mit Bildern %s): %s %s",
                            grund,
                            e.get("typ"),
                            e.get("zeit"),
                        )
                if ergebnis == "abgelehnt":
                    log.error(
                        "Ereignis von der App dauerhaft abgelehnt – verworfen, damit es "
                        "die Nachlieferung nicht blockiert: %s %s %s",
                        e.get("typ"),
                        e.get("zeit"),
                        str(e.get("nachricht", ""))[:80],
                    )
                    self._entferne(teil)
                    continue
                if ergebnis == "zu_gross":
                    # Selbst ohne Bilder zu gross: kann nur von aussen kommen
                    # (Proxy) — nichts verwerfen, spaeter erneut.
                    ergebnis = "fehler"
            if ergebnis == "ok":
                self._entferne(teil)
                geliefert += len(teil)
                tasten = False
                if self._db_fehler_in_folge:
                    log.info("Dashboard wieder erreichbar – Offline-Puffer wird nachgeliefert")
                self._db_fehler_in_folge = 0
                continue
            # "fehler": spaeter erneut (Backoff), nichts entfernen.
            self._db_fehler_in_folge += 1
            if self._db_fehler_in_folge == 1 or self._db_fehler_in_folge % 10 == 0:
                log.error(
                    "Dashboard-Meldung fehlgeschlagen (%d im Puffer, neuer Versuch "
                    "in %d s): %s",
                    len(stapel),
                    self._wartezeit(),
                    self._db_letzter_fehler,
                )
            return False
        if geliefert > 1:
            log.info("Offline-Puffer nachgeliefert: %d Ereignis(se)", geliefert)
        return True


# --------------------------------------------------------------------------
# Kamerabild-Pruefung (Freeze-Watchdog)
# --------------------------------------------------------------------------

def pruefe_kamerabild(
    wd: FreezeWatchdog | None, frame: np.ndarray, notifier: "Notifier"
) -> bool:
    """Schickt einen Frame durch den Freeze-Watchdog (eingefroren / Streifen).

    Bei einem Ereignis geht genau EINE Meldung raus (Telegram + Dashboard
    + MQTT ueber ``Notifier.wichtig``); Einmaligkeit pro Episode stellt der
    Watchdog selbst sicher. Rueckgabe True = Kamera defekt -> Aufrufer
    speichert keine Trainingsbilder und analysiert nicht. Ein Fehler im
    Watchdog oder beim Melden blockiert die Analyse nie (-> False).
    """
    if wd is None:
        return False
    try:
        ereignis = wd.pruefe(frame)
        defekt = bool(wd.defekt)
    except Exception:  # noqa: BLE001 – Watchdog darf die Analyse nie blockieren
        log.exception("Freeze-Watchdog gestoert – Analyse laeuft weiter")
        return False
    if ereignis:
        try:
            notifier.wichtig(ereignis["nachricht"])
        except Exception:  # noqa: BLE001
            log.exception("Watchdog-Meldung konnte nicht gesendet werden")
    return defekt


_TRAININGSBILD_ZEIT = re.compile(r"\d{8}-\d{6}")


def trainingsbild_praefix(kamera: str) -> str:
    """Kamera-Teil des Dateinamens, so bereinigt wie in trainingsbild_name."""
    return "".join(c if c.isalnum() or c == "-" else "-" for c in kamera) or "kamera"


def trainingsbild_name(kamera: str, zeit: float | None = None) -> str:
    """Dateiname eines Silent-Mode-Bilds: <kamera>_<JJJJMMTT-HHMMSS>.jpg.

    Die Kamera steht im Namen, weil Bilder mehrerer Agent-Instanzen im selben
    Datensatz landen. Die Zeit steht im Namen, weil der Split nach Tagen
    (training/datensatz.py) sie daraus liest.
    """
    return f"{trainingsbild_praefix(kamera)}_{time.strftime('%Y%m%d-%H%M%S', time.localtime(zeit))}.jpg"


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
    totmann = TotmannWaechter(cfg)
    lebenszeichen = Lebenszeichen(cfg)
    # „Bild da" fuer das Lebenszeichen: letzter Frame juenger als 2 min und
    # kein Defekt laut Freeze-Watchdog.
    letztes_bild: float | None = None
    # Zweitkopie der Trainingsbilder in der Cloud (dashboard.archiv). Die
    # Feedback-Schleife bekommt dieselbe Instanz, damit nur ein Worker-Thread
    # laeuft und Silent-Mode-Bilder wie Hard Negatives denselben Weg nehmen.
    archiv = DatensatzArchiv(cfg)
    notifier.feedback.archiv = archiv
    # „❌ Fehlalarm" auf eine Austreibung -> naechste Erkennung meldet sofort.
    notifier.feedback.bei_fehlalarm = logik.fehlalarm_gemeldet

    frame_puffer: deque[np.ndarray] = deque(maxlen=8)  # Verlauf fuer Bildserien

    # Freeze-Watchdog je Kamera dieser Agent-Instanz (stream.kamera, z. B.
    # stallwache oder futterwache – die Futterwache laeuft als eigene
    # Instanz mit eigener config.yaml und bekommt so ihren eigenen Watchdog).
    wd = baue_watchdog(cfg, notifier.kamera, engine.aktiv)
    if wd:
        log.info(
            "Freeze-Watchdog aktiv (%s): Alarm nach %d %s",
            wd.kamera,
            wd.frames_bis_alarm,
            "Frames" if engine.aktiv else "Trainingsbildern",
        )

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
            notifier.digest_tick(engine.aktiv)
            notifier.feedback.tick()
            totmann_meldung = totmann.tick(frame is not None)
            if totmann_meldung:
                notifier.wichtig(totmann_meldung)
            if frame is not None:
                letztes_bild = time.time()
            lebenszeichen.tick(
                engine.aktiv,
                letztes_bild is not None
                and time.time() - letztes_bild < 120
                and not (wd is not None and wd.defekt),
            )
            if frame is None:
                continue

            if not engine.aktiv:
                # Silent Mode: regelmaessig Trainingsbilder sichern.
                if time.time() - letzte_aufnahme >= intervall:
                    letzte_aufnahme = time.time()
                    # Geprueft wird jedes Bild, das gespeichert wuerde: so
                    # entspricht „5 Bilder" 5 x Aufnahmeintervall (nicht 5 s).
                    # Defekte Kamera -> kein Trainingsbild (Muell im Datensatz).
                    if pruefe_kamerabild(wd, frame, notifier):
                        continue
                    name = ordner / trainingsbild_name(notifier.kamera)
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

            # Jeder Frame durch den Watchdog; defekte Kamera -> keine Analyse
            # (ein eingefrorenes Bild wuerde sonst alte Befunde „weiterzaehlen").
            if pruefe_kamerabild(wd, frame, notifier):
                continue

            frame_puffer.append(frame)
            kuehe, objekte = engine.analysiere(frame)
            for alarm in logik.bewerte(kuehe, objekte):
                notifier.melde(alarm, frame, verlauf=list(frame_puffer)[:-1])

        except KeyboardInterrupt:
            log.info("Beendet.")
            return
        except Exception:  # noqa: BLE001 – 24/7-Betrieb darf nie abstuerzen
            log.exception("Unerwarteter Fehler – laufe weiter")
            time.sleep(5)


if __name__ == "__main__":
    main()
