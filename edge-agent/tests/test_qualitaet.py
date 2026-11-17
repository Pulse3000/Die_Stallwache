#!/usr/bin/env python3
"""B20-Abnahme: Bildqualitaets-Gate in der Logik (+ Auflagen aus dem Review).

Defektbild veraendert das 30-min-Fenster nicht; Austreibung > 0.80 und
Eskalation laufen auf Defektbildern weiter (Alarmtext weist auf das gestreifte
Bild hin); eine Streifen-Phase beendet die Austreibungs-Episode nicht; ein
Aufsprung uebersteht ein Defektbild, aber hoechstens brunst_min_dauer_s;
Bildstoerungs-Info genau 1x je Episode (erst bei vollem Fenster, Ende nach
10 min darunter), nur Dashboard - kein Telegram; Zaehler im Tagesbericht;
Ausfall-Waechter (blind, Tracker, Analyse) melden 1x je Episode per Telegram
und entwarnen; werte_bild_aus meldet Alarme vor allen Systemmeldungen und
laesst ein Bild bei Pruef-Fehler als intakt durch. Pures Python (Stubs)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main  # noqa: E402

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Bildqualitaets-Gate (B20)")

LOGIK = {"logik": {"winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
                   "override_konfidenz": 0.80, "brunst_min_dauer_s": 4, "eskalation_minuten": 60}}
# Tests mit groben Zeitschritten: ziel_fps passend, sonst deckelt die Uhr-Pause (2 Bildabstaende)
LOGIK_60 = LOGIK | {"stream": {"ziel_fps": 1 / 60}}   # 1 Bild je Minute
LOGIK_10 = LOGIK | {"stream": {"ziel_fps": 0.1}}      # 1 Bild je 10 s
QCFG = {"stream": {"kamera": "stallwache"},
        "qualitaet": {"schwelle_defekt": 0.04, "degradiert_anteil": 0.5, "fenster_min": 10}}
SAC = m.ObjektErkennung("amniotic_sac", 0.86, (10, 10, 50, 50))


def kuh(tid, winkel=60.0, box=(0, 0, 100, 100)):
    return m.KuhBeobachtung(tid, box, winkel, None)


# --- 1) Fenster ------------------------------------------------------------
lg = m.LogicEngine(LOGIK)
for i in range(10):
    lg.bewerte([kuh(7)], [], defekt=False, jetzt=1000 + i)
vorher = list(lg.puffer[7])
for i in range(30):
    lg.bewerte([kuh(7, winkel=80)], [], defekt=True, jetzt=1010 + i)
p.check("30 Defektbilder: 30-min-Fenster von Kuh #7 unveraendert", list(lg.puffer[7]) == vorher)
lg.bewerte([kuh(7)], [], defekt=False, jetzt=1040)
p.check("intaktes Bild zaehlt wieder", len(lg.puffer[7]) == len(vorher) + 1)

lg0, a0 = m.LogicEngine(LOGIK), []
lg1, a1 = m.LogicEngine(LOGIK), []
for i in range(30):
    a0 += lg0.bewerte([kuh(7, winkel=80)], [], defekt=False, jetzt=1000 + i)
    a1 += lg1.bewerte([kuh(7, winkel=80)], [], defekt=True, jetzt=1000 + i)
p.check("Kontrolle: dieselben 80-Grad-Bilder als intakt -> Kalbeverdacht",
        any(a.typ == "kalbeverdacht" for a in a0))
p.check("als Defektbilder -> kein Kalbeverdacht (Streifen-Scheinwinkel bleiben draussen)", a1 == [])

# --- 2) Austreibung + Eskalation auf Defektbildern --------------------------
lg = m.LogicEngine(LOGIK)
a = lg.bewerte([], [SAC], defekt=True, jetzt=5000)
p.check("Fruchtblase 0.86 auf Defektbild -> Sofort-Alarm", [x.typ for x in a] == ["austreibung"])
p.check("Alarmtext auf Defektbild: 'Bild gestreift – bitte Bildserie prüfen.'",
        a[0].nachricht.endswith("Austreibungsphase! Bild gestreift – bitte Bildserie prüfen."))
p.check("intaktes Bild: Alarmtext unveraendert",
        m.LogicEngine(LOGIK).bewerte([], [SAC], jetzt=1.0)[0].nachricht.endswith("– Austreibungsphase!"))
a = lg.bewerte([], [SAC], defekt=True, jetzt=5000 + 3600)
p.check("Eskalation nach 60 min auch auf Defektbild (B3)", sum(x.kuh_id == "Eskalation" for x in a) == 1)
a = lg.bewerte([], [SAC], defekt=True, jetzt=5000 + 3660)
p.check("Eskalation genau 1x je Episode", not any(x.kuh_id == "Eskalation" for x in a)
        and any(x.typ == "austreibung" for x in a))

# Streifen-Phase von 31 min beendet die Episode nicht -> Eskalation nach 60 min
T0 = 20000.0  # echte Zeitstempel sind nie 0 (bewerte nutzt "start or jetzt")
lg = m.LogicEngine(LOGIK_60)
lg.bewerte([], [SAC], jetzt=T0)
for t in range(60, 1900, 60):
    lg.bewerte([], [], defekt=True, jetzt=T0 + t)
lg.bewerte([], [SAC], jetzt=T0 + 1900)
a = lg.bewerte([], [SAC], jetzt=T0 + 3600)
p.check("31 min Streifen ohne Befund: Episode laeuft weiter, Eskalation nach 60 min (nicht 96 min)",
        sum(x.kuh_id == "Eskalation" for x in a) == 1)
lg = m.LogicEngine(LOGIK_60)
lg.bewerte([], [SAC], jetzt=T0)
for t in range(60, 1900, 60):
    lg.bewerte([], [], defekt=False, jetzt=T0 + t)
lg.bewerte([], [SAC], jetzt=T0 + 1900)
a = lg.bewerte([], [SAC], jetzt=T0 + 3600)
p.check("Kontrolle: 31 min INTAKTE Bilder ohne Befund beenden die Episode (keine Eskalation)",
        not any(x.kuh_id == "Eskalation" for x in a))


def nacht(lg, von, bis, schritt, defekt_alle, sac=None):
    """Bilder alle `schritt` s; jedes `defekt_alle`-te gestreift; sac(t) -> Objektliste."""
    alarme = []
    for i, t in enumerate(range(int(von), int(bis), schritt)):
        alarme += lg.bewerte([], sac(t) if sac else [], defekt=(i % defekt_alle == 0), jetzt=float(t))
    return alarme


# ki-wache Sim E: Einzel-Fehlalarm 22:00, 15 % Streifen, echte Fruchtblase ab 03:00
lg = m.LogicEngine(LOGIK_10)
lg.bewerte([], [SAC], jetzt=T0)
nacht(lg, T0 + 10, T0 + 5 * 3600, 10, 7)
a = nacht(lg, T0 + 5 * 3600, T0 + 5 * 3600 + 1800, 10, 7, sac=lambda t: [SAC])
p.check("Sim E: Fehlalarm um 22:00 + 15 % Streifen -> um 03:00 KEINE Sofort-Eskalation",
        not any(x.kuh_id == "Eskalation" for x in a))
a = nacht(lg, T0 + 5 * 3600 + 1800, T0 + 6 * 3600 + 60, 10, 7, sac=lambda t: [SAC])
p.check("Sim E: echte Eskalation 60 min nach Beginn der echten Austreibung",
        sum(x.kuh_id == "Eskalation" for x in a) == 1)

# qa-waechter: Kalbung A eskaliert, 3 h ohne Befund (jedes 20. Bild gestreift), Kalbung B 70 min
lg = m.LogicEngine(LOGIK_10)
a = nacht(lg, T0, T0 + 3601, 10, 20, sac=lambda t: [SAC])
p.check("Kalbung A eskaliert nach 60 min", sum(x.kuh_id == "Eskalation" for x in a) == 1)
nacht(lg, T0 + 3610, T0 + 3610 + 3 * 3600, 10, 20)
b0 = T0 + 3610 + 3 * 3600
a = nacht(lg, b0, b0 + 70 * 60, 10, 20, sac=lambda t: [SAC])
esk = [x for x in a if x.kuh_id == "Eskalation"]
p.check("Kalbung B (70 min ohne Fortschritt) bekommt ihre eigene Eskalation nach 60 min",
        len(esk) == 1 and "seit 60 Minuten" in esk[0].nachricht)

# ki-wache Sim E2: Fehlalarm 22:00, 4 h Stream-Ausfall, erstes Bild danach gestreift, Fruchtblase 15 min spaeter
lg = m.LogicEngine(LOGIK_10)
lg.bewerte([], [SAC], jetzt=T0)
lg.bewerte([], [], defekt=True, jetzt=T0 + 4 * 3600)          # erstes Bild nach dem Ausfall: gestreift
nacht(lg, T0 + 4 * 3600 + 10, T0 + 4 * 3600 + 900, 10, 1000)  # 15 min intakt, ohne Befund
e0 = T0 + 4 * 3600 + 900
a = nacht(lg, e0, e0 + 600, 10, 1000, sac=lambda t: [SAC])
p.check("Sim E2: Stream-Ausfall vor einem Defektbild haelt die Episode nicht offen (keine Fehl-Eskalation)",
        not any(x.kuh_id == "Eskalation" for x in a))
a = nacht(lg, e0 + 600, e0 + 3660, 10, 1000, sac=lambda t: [SAC])
p.check("Sim E2: echte Eskalation 60 min nach Beginn der echten Austreibung",
        sum(x.kuh_id == "Eskalation" for x in a) == 1)

# --- 3) Aufsprung ueber ein Defektbild ----------------------------------------
oben, unten = (0, 0, 100, 100), (0, 40, 100, 140)
paar = [kuh(1, None, oben), kuh(2, None, unten)]
lg = m.LogicEngine(LOGIK)
lg.bewerte(paar, [], jetzt=100)
lg.bewerte([], [], defekt=True, jetzt=102)
a = lg.bewerte(paar, [], jetzt=104)
p.check("Aufsprung ueber ein Defektbild hinweg -> Brunstverdacht nach 4 s",
        any(x.typ == "brunstverdacht" for x in a))
lg = m.LogicEngine(LOGIK)
lg.bewerte(paar, [], jetzt=100)
lg.bewerte([], [], defekt=False, jetzt=102)
a = lg.bewerte(paar, [], jetzt=104)
p.check("Kontrolle: intaktes Bild ohne Paar beendet die Messung (bisheriges Verhalten)",
        not any(x.typ == "brunstverdacht" for x in a))
lg = m.LogicEngine(LOGIK)
lg.bewerte(paar, [], jetzt=100)
for t in range(101, 701):
    lg.bewerte([], [], defekt=True, jetzt=float(t))
a = lg.bewerte(paar, [], jetzt=701)
p.check("10 min Defektbilder zwischen zwei Aufsprung-Bildern -> kein 'Aufsprung 601 s'",
        not any(x.typ == "brunstverdacht" for x in a))
a = lg.bewerte(paar, [], jetzt=705)
p.check("danach zaehlt die Messung neu: Brunstverdacht nach 4 s echter Dauer",
        any(x.typ == "brunstverdacht" and "Dauer 4 s" in x.nachricht for x in a))

# --- 4) Degradations-Episoden -------------------------------------------------
q = m.BildQualitaet(QCFG)
meldungen = []
uhr = [0.0]


def lauf(sekunden, defekt):
    for _ in range(int(sekunden)):
        r = q.zaehle(defekt(int(uhr[0])), uhr[0])
        if r:
            meldungen.append((uhr[0], r))
        uhr[0] += 1.0


lauf(300, lambda s: True)
p.check("vor vollem Fenster (10 min) keine Meldung, auch bei 100 % Defekt", meldungen == [])
lauf(400, lambda s: s % 3 != 0)
p.check("volles Fenster > 50 % -> genau 1 Meldung (bei t = 600 s)",
        len(meldungen) == 1 and meldungen[0][0] == 600.0)
text = meldungen[0][1] if meldungen else ""
p.check("Meldungstext wie spezifiziert",
        text.startswith("Bildstörungen (stallwache): ")
        and text.endswith(" % der Bilder der letzten 10 min gestreift. Fruchtblase/Kälberfüße: "
                          "Jedes Bild wird weiter geprüft, gestreifte Bildteile sind aber nicht "
                          "auswertbar. Wehen-Verdacht nur aus ungestörten Bildern. Bitte Livebild "
                          "und Stall-WLAN prüfen."))
lauf(1200, lambda s: s % 3 != 0)
p.check("anhaltende Degradation (20 min) -> keine zweite Meldung", len(meldungen) == 1 and q.degradiert)
lauf(200, lambda s: False)
lauf(200, lambda s: True)
p.check("kurze Erholung (< 10 min unter 50 %) -> gleiche Episode, keine Meldung",
        len(meldungen) == 1 and q.degradiert)
lauf(1500, lambda s: False)
p.check("10 min ununterbrochen <= 50 % -> Episode beendet", not q.degradiert)
lauf(700, lambda s: True)
p.check("neue Degradation -> zweite Meldung", len(meldungen) == 2)

q3, m3 = m.BildQualitaet(QCFG), []
for t in range(400):
    m3.append(q3.zaehle(True, float(t)))
for t in range(1500, 1900):
    m3.append(q3.zaehle(True, float(t)))
p.check("nach Bildluecke > 10 min erst wieder bei vollem Fenster bewertet", not any(m3))

z = q.tagesbericht()
p.check("Tagesbericht: Quote, Anzahl, Episoden", z is not None and z.startswith("Bildstörungen: ")
        and "% der Bilder (" in z and "Phasen über 50 %: 2×" in z and "(hält an)" in z)
p.check("Tagesbericht setzt die Zaehler zurueck", q.bilder == 0 and q.tagesbericht() is None)

# --- 5) Zustellung: Dashboard ja, Telegram nein; Zeile im Tagesbericht --------
with tempfile.TemporaryDirectory() as d:
    ncfg = {"stream": {"kamera": "stallwache"},
            "telegram": {"token": "TEST", "chat_id": "1", "digest_uhrzeit": "00:00",
                         "feedback_buttons": False},
            "dashboard": {"url": "https://example.invalid/api/events", "token": "t",
                          "puffer_datei": str(Path(d) / "puffer.jsonl")}}
    n = m.Notifier(ncfg)
    gesendet.clear()
    n.status(text)
    p.check("Degradations-Info geht ans Dashboard (typ info)",
            any(u.startswith("https://example.invalid") and kw["json"]["ereignisse"][-1]["typ"] == "info"
                for u, kw in gesendet))
    p.check("Degradations-Info weckt nicht: kein Telegram-Aufruf",
            not any("api.telegram.org" in u for u, _ in gesendet))
    q4 = m.BildQualitaet(QCFG)
    q4.zaehle(True, 0.0)
    q4.zaehle(False, 1.0)
    n.qualitaet = q4
    gesendet.clear()
    n.digest_tick(True)
    bericht = next((kw["data"]["text"] for u, kw in gesendet if u.endswith("/sendMessage")), "")
    p.check("Tagesbericht enthaelt 'Bildstörungen: 50 % der Bilder (1 von 2)'",
            "Bildstörungen: 50 % der Bilder (1 von 2)" in bericht)
    gesendet.clear()
    n._digest_tag = None
    n.digest_tick(False, modus="KI-Wache AUS – Modell nicht geladen (nur Bildersammlung)")
    bericht = next((kw["data"]["text"] for u, kw in gesendet if u.endswith("/sendMessage")), "")
    p.check("Tagesbericht nennt den Ladefehler im Modus (nicht 'Datensammlung' wie normal)",
            "Modus: KI-Wache AUS – Modell nicht geladen (nur Bildersammlung)" in bericht)


# --- 6) werte_bild_aus: Reihenfolge und Fehlerpfad ----------------------------
class FQ:
    def __init__(self, defekt=False, meldung=None, fehler=False):
        self.defekt, self.meldung, self.fehler = defekt, meldung, fehler

    def pruefe(self, frame):
        if self.fehler:
            raise ValueError("Bild kaputt")
        return self.defekt, 0.5

    def zaehle(self, defekt, jetzt=None):
        return self.meldung


class FE:
    tracker_ok = True
    tracker_laufzeitfehler = None

    def analysiere(self, frame, defekt=False):
        self.defekt = defekt
        return [], [SAC]


class FN:
    def __init__(self):
        self.log = []

    def melde(self, alarm, frame, verlauf=None):
        self.log.append(f"melde:{alarm.typ}")

    def status(self, nachricht):
        self.log.append("status:" + nachricht.split(" (")[0])

    def wichtig(self, nachricht, still=False):
        self.log.append(("still:" if still else "wichtig:") + nachricht.split(" (")[0])


fe, fn = FE(), FN()
m.werte_bild_aus("bild", fe, m.LogicEngine(LOGIK), FQ(True, "Bildqualität degradiert"), fn, [], jetzt=10.0)
p.check("werte_bild_aus: Defekt-Flag erreicht Modell und Logik", fe.defekt is True)
p.check("werte_bild_aus: Alarm VOR der Info-Meldung", fn.log == ["melde:austreibung", "status:Bildqualität degradiert"])
fe, fn = FE(), FN()
m.werte_bild_aus("bild", fe, m.LogicEngine(LOGIK), FQ(fehler=True), fn, [], jetzt=10.0)
p.check("Pruef-Fehler: Bild gilt als intakt, Austreibung trotzdem gemeldet",
        fe.defekt is False and fn.log == ["melde:austreibung"])

# --- 7) Ausfall-Waechter (Totmann-Prinzip fuer Teilfunktionen) --------------
w = m.AusfallWaechter(300, "AUS seit {minuten:.0f} min ({kamera})", "WIEDER nach {minuten:.0f} min",
                      jetzt=0.0, kamera="stallwache")
r = [w.tick(t < 10, float(t)) for t in range(0, 310)]
p.check("Ausfall-Waechter: still unter 300 s, Meldung bei 300 s ab letztem guten Tick",
        r[:309] == [None] * 309 and r[309] == "AUS seit 5 min (stallwache)" and w.letzte_art == "meldung")
r = [w.tick(False, float(t)) for t in range(310, 900)]
r += [w.tick(t % 360 == 0, float(t)) for t in range(900, 1800)]   # alle 6 min ein gutes Bild
p.check("einzelne gute Durchlaeufe beenden die Episode nicht (kein Meldungs-Pingpong)", not any(r))
r = [w.tick(True, float(t)) for t in range(1800, 2100)]
ent = [(t, x) for t, x in zip(range(1800, 2100), r) if x]
p.check("Entwarnung erst bei > 50 % guten Durchlaeufen in den letzten 5 min, genau einmal",
        len(ent) == 1 and 1900 < ent[0][0] < 2000 and ent[0][1].startswith("WIEDER nach"))
w = m.AusfallWaechter(300, "AUS {minuten:.0f}", "WIEDER", jetzt=0.0)
w.tick(True, 10.0)
p.check("nach einer Luecke ohne Ticks zaehlt der Ausfall ab dem ersten schlechten Tick",
        w.tick(False, 2000.0) is None and w.tick(False, 2299.0) is None and w.tick(False, 2300.0) == "AUS 5")
p.check("totmann_minuten 0 -> Waechter aus",
        m.baue_waechter({"stream": {"totmann_minuten": 0}})["blind"].tick(False, 99999.0) is None)

WCFG = QCFG | {"stream": {"kamera": "stallwache", "totmann_minuten": 5}}
wa = m.baue_waechter(WCFG, jetzt=0.0)
fe, fn = FE(), FN()
for t in range(0, 301):
    m.werte_bild_aus("bild", fe, m.LogicEngine(LOGIK), FQ(True), fn, [], jetzt=float(t), waechter=wa)
p.check("5 min nur gestreifte Bilder -> genau 1 BLIND-Meldung mit Ton, nach dem Alarm",
        fn.log.count("wichtig:🔴 KI-WACHE BLIND") == 1
        and fn.log[-2:] == ["melde:austreibung", "wichtig:🔴 KI-WACHE BLIND"])
fn.log.clear()
for t in range(301, 3600):  # ki-wache Sim G: faktisch blind, alle 6 min ein "intaktes" Bild
    m.werte_bild_aus("bild", fe, m.LogicEngine(LOGIK), FQ(t % 360 != 0), fn, [], jetzt=float(t), waechter=wa)
p.check("Sim G: blinde Kamera mit vereinzelten intakten Bildern -> keine weiteren Meldungen in 55 min",
        not any(x.startswith(("wichtig:", "still:")) for x in fn.log))
fn.log.clear()
for t in range(3600, 3900):
    m.werte_bild_aus("bild", fe, m.LogicEngine(LOGIK), FQ(False), fn, [], jetzt=float(t), waechter=wa)
p.check("Erholung -> genau eine Entwarnung, still (weckt nicht)",
        [x for x in fn.log if x.startswith(("wichtig:", "still:"))] == ["still:KI-Wache sieht wieder"])

# qa-waechter/ki-wache Sim F: ByteTrack dauerhaft kaputt, zwischendurch Bilder ohne Tracker-Aufruf
wa = m.baue_waechter(WCFG, jetzt=0.0)


class FET(FE):
    def __init__(self):
        self.n = 0

    def analysiere(self, frame, defekt=False):
        self.n += 1
        nicht_gerufen = self.n % 20 == 0       # Defektbild oder keine Kuh: Tracker lief nicht
        self.tracker_ok = None if nicht_gerufen else False
        self.tracker_laufzeitfehler = "RuntimeError: kaputt"
        return [], [SAC]


fe, fn = FET(), FN()
for t in range(0, 3600):
    m.werte_bild_aus("bild", fe, m.LogicEngine(LOGIK), FQ(False), fn, [], jetzt=float(t), waechter=wa)
meld = [x for x in fn.log if "EINGESCHRÄNKT" in x or "vollständig" in x]
p.check("Sim F: Dauerfehler mit Bildern ohne Tracker-Aufruf -> genau 1 Meldung, keine falsche Entwarnung",
        meld == ["status:🟠 KI-WACHE EINGESCHRÄNKT"])
p.check("Weckregel: EINGESCHRÄNKT zur Laufzeit ohne Wach-Modus nur Dashboard (kein Telegram)",
        not any(x.startswith("wichtig:🟠") for x in fn.log))
fe.n, fn.log = 0, []


class FEOK(FE):
    tracker_ok = True


for t in range(3600, 4000):
    m.werte_bild_aus("bild", FEOK(), m.LogicEngine(LOGIK), FQ(False), fn, [], jetzt=float(t), waechter=wa)
p.check("Entwarnung auf demselben Kanal wie die Meldung (Dashboard), nicht per Telegram",
        "status:KI-Wache wieder vollständig" in fn.log and not any(x.startswith("still:KI-Wache wieder") for x in fn.log))
wa = m.baue_waechter(WCFG, jetzt=0.0)
fe, fn = FET(), FN()
lw = m.LogicEngine({"logik": dict(LOGIK["logik"], wach_modus=True)})
for t in range(0, 400):
    m.werte_bild_aus("bild", fe, lw, FQ(False), fn, [], jetzt=float(t), waechter=wa)
p.check("Weckregel: im Wach-Modus weckt EINGESCHRÄNKT per Telegram",
        fn.log.count("wichtig:🟠 KI-WACHE EINGESCHRÄNKT") == 1)

text = m.TEXT_TRACKER_AUS.format(kamera="stallwache", technik="RuntimeError: kaputt")
p.check("Tracker-Text nennt, was weiter laeuft und was AUS ist",
        "Fruchtblase und Kälberfüße werden weiter gemeldet" in text
        and "AUS sind Wehen-Verdacht (Schwanzwinkel) und Brunst" in text)
p.check("Analyse-Waechter-Text: KEINE Alarme, auch nicht bei Fruchtblase",
        "KEINE Alarme, auch nicht bei Fruchtblase oder Kälberfüßen" in m.TEXT_ANALYSE_AUS)

with tempfile.TemporaryDirectory() as d:
    n = m.Notifier({"stream": {"kamera": "stallwache"},
                    "telegram": {"token": "TEST", "chat_id": "1", "feedback_buttons": False},
                    "dashboard": {"puffer_datei": str(Path(d) / "p.jsonl")}})
    gesendet.clear()
    n.wichtig("Entwarnung", still=True)
    n.wichtig("Meldung")
    daten = [kw["data"] for u, kw in gesendet if u.endswith("/sendMessage")]
    p.check("still=True -> Telegram disable_notification, sonst mit Ton",
            daten[0].get("disable_notification") is True and "disable_notification" not in daten[1])

sys.exit(p.bericht())
