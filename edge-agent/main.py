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
                "dritte Auge ist blind! Bitte Bridge, WLAN und Kamera pruefen."
            )
        return None


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
        # Eigene Tracker-Konfiguration (z. B. tracker-kuh.yaml mit grossem
        # track_buffer fuer 1 FPS); leer -> Ultralytics-Default.
        self.tracker = (self.cfg.get("tracker") or "").strip() or "bytetrack.yaml"
        self.modell = None
        pfad = (self.cfg.get("pfad") or "").strip()
        if pfad:
            from ultralytics import YOLO  # Import nur bei Bedarf (Silent Mode braucht es nicht)

            log.info("Lade Modell %s (Tracker: %s) …", pfad, self.tracker)
            self.modell = YOLO(pfad)

    @property
    def aktiv(self) -> bool:
        return self.modell is not None

    def analysiere(
        self, frame: np.ndarray
    ) -> tuple[list[KuhBeobachtung], list[ObjektErkennung]]:
        """Ein Frame -> getrackte Kuehe (mit Schwanzwinkel) + Spezialobjekte."""
        ergebnis = self.modell.track(
            frame, persist=True, tracker=self.tracker, verbose=False
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
            import json

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

        self.kamera = cfg["stream"].get("kamera", "stallwache")
        self._zuletzt: dict[tuple[str | None, str], float] = {}
        self.feedback = FeedbackSchleife(cfg)

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
        self._dashboard(alarm)
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
        self._telegram(meldung, None)
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
    ) -> None:
        if not (self.tg_token and self.tg_chat):
            return
        import json

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
            import json

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
    totmann = TotmannWaechter(cfg)

    frame_puffer: deque[np.ndarray] = deque(maxlen=8)  # Verlauf fuer Bildserien

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
