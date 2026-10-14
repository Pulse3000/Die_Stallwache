#!/usr/bin/env python3
"""Logiktests Austreibungs-Takt je Episode (statt Kamera-Cooldown).

Abnahmekriterien 1–15 aus docs/austreibung-episoden-spezifikation.md. Die
Zusage dahinter: Eine Austreibung wird nie durch einen pauschalen Cooldown
verzoegert, eine laufende Geburt meldet sich im Takt, bis sie vorbei ist,
und ein „❌ Fehlalarm" macht nie stiller als ohne Feedback. Uhr und HTTP
sind gestubbt — es geht nie ein echter Request raus.
"""

import sys
import time as echte_zeit
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Austreibungs-Episoden")

# Steuerbare Uhr fuer LogicEngine und Notifier (bewerte() liest time.time()).
UHR = [100_000.0]
m.time = types.SimpleNamespace(
    **{k: getattr(echte_zeit, k) for k in dir(echte_zeit) if not k.startswith("_")}
)
m.time.time = lambda: UHR[0]

MIN = 60.0


def logik(**lg):
    cfg = {
        "logik": {
            "winkel_schwelle_grad": 45,
            "fenster_minuten": 30,
            "anteil_schwelle": 0.20,
            "override_konfidenz": 0.80,
            "brunst_min_dauer_s": 4,
            "eskalation_minuten": 60,
            **lg,
        },
        "telegram": {"cooldown_minuten": 15},
    }
    return m.LogicEngine(cfg)


def blase(k=0.87):
    return m.ObjektErkennung("amniotic_sac", k, (10, 10, 50, 50))


def fuesse(k=0.91):
    return m.ObjektErkennung("calf_legs", k, (12, 12, 40, 40))


def bild(l, objekte, um_s):
    """Ein Frame zur absoluten Zeit (Sekunden ab Testbeginn)."""
    UHR[0] = 100_000.0 + um_s
    return [a for a in l.bewerte([], objekte) if a.typ == "austreibung"]


def laufe(l, von_s, bis_s, objekte=None, schritt=1.0):
    """Erkennung in jedem Frame von..bis (1 FPS) — liefert alle Meldungen."""
    meldungen = []
    t = von_s
    while t <= bis_s:
        meldungen += bild(l, [blase()] if objekte is None else objekte, t)
        t += schritt
    return meldungen


# --- 1./2. Beginn: genau eine Sofort-Meldung, Folgebilder still -----------
l = logik()
erste = bild(l, [blase()], 0)
p.check("1: erste Erkennung -> eine Meldung", len(erste) == 1)
p.check("1: sofort=True (Notifier-Cooldown gilt nicht)", erste[0].sofort is True)
p.check("1: Text unveraendert", erste[0].nachricht == "Fruchtblase erkannt (Konfidenz 87 %) – Austreibungsphase!"
        or erste[0].nachricht == "Fruchtblase erkannt (Konfidenz 87%) – Austreibungsphase!")
p.check("1: Episode 1, ohne Kuh-ID", erste[0].episode == 1 and erste[0].kuh_id is None)
p.check("2: Folgebilder bis 14:59 min still", laufe(l, 1, 15 * MIN - 1) == [])

# --- 3. Erinnerung nach 15 min ---------------------------------------------
erinnerung = bild(l, [fuesse()], 15 * MIN)
p.check("3: Erinnerung nach 15 min", len(erinnerung) == 1)
p.check("3: Text 'laeuft weiter seit 15 min'",
        "läuft weiter seit 15 min" in erinnerung[0].nachricht and "Kälberfüße" in erinnerung[0].nachricht)
p.check("3: Erinnerung sofort=True, gleiche Episode",
        erinnerung[0].sofort and erinnerung[0].episode == 1)
p.check("3: danach wieder Takt", laufe(l, 15 * MIN + 1, 30 * MIN - 1, schritt=10) == [])

# --- 4. Blase und Fuesse im selben Bild = eine Meldung ---------------------
l4 = logik()
beide = bild(l4, [blase(0.85), fuesse(0.93)], 0)
p.check("4: zwei Objekte -> eine Meldung", len(beide) == 1)
p.check("4: hoechste Konfidenz gewinnt", beide[0].konfidenz == 0.93 and "Kälberfüße" in beide[0].nachricht)

# --- 5. Eskalation genau einmal, ersetzt im selben Bild die Erinnerung ----
l5 = logik()
alle = laufe(l5, 0, 100 * MIN, schritt=30)
eskalationen = [a for a in alle if a.kuh_id == "Eskalation"]
p.check("5: genau eine Eskalation", len(eskalationen) == 1)
p.check("5: Eskalation bei 60 min", "seit 60 Minuten" in eskalationen[0].nachricht)
p.check("5: Eskalation sofort=True", eskalationen[0].sofort is True)
bei_60 = [a for a in alle if "läuft weiter seit 60 min" in a.nachricht]
p.check("5: keine Erinnerung im Eskalationsbild", bei_60 == [])
takt = [a for a in alle if a.kuh_id is None]
# Beginn + Erinnerungen bei 15/30/45, Eskalation 60, Erinnerungen 75/90
p.check("5: Takt Beginn+15/30/45, Eskalation, 75/90", len(takt) == 6)

# --- 6. 30 min ohne Erkennung -> neue Episode, sofort, Uhr neu -------------
l6 = logik()
bild(l6, [blase()], 0)
genau_30 = bild(l6, [blase()], 30 * MIN)   # Pause genau 30 min: Grenze inklusive
p.check("6: 30 min Pause noch dieselbe Episode (Erinnerung, kein Neubeginn)",
        l6.episode_nr == 1 and len(genau_30) == 1 and "läuft weiter seit 30 min" in genau_30[0].nachricht)
p.check("6: Folgebilder ohne Erkennung still", laufe(l6, 30 * MIN + 1, 61 * MIN, objekte=[], schritt=60) == [])
neu = bild(l6, [blase()], 61 * MIN)
p.check("6: nach > 30 min Pause neue Episode, sofort", len(neu) == 1 and neu[0].episode == 2)
p.check("6: Text 'erkannt', nicht 'laeuft weiter'", "Austreibungsphase!" in neu[0].nachricht)
p.check("6: Eskalations-Uhr neu", l6.austreibung_start == UHR[0] and not l6.eskaliert)

# --- 7. Fall (c): Stream 90 min weg, dann Erkennung ------------------------
l7 = logik()
laufe(l7, 0, 20 * MIN, schritt=60)            # alte Episode laeuft 20 min
nach_ausfall = bild(l7, [blase()], 110 * MIN)  # kein bewerte() dazwischen
p.check("7: nach Stream-Ausfall Episodenbeginn", len(nach_ausfall) == 1 and nach_ausfall[0].episode == 2)
p.check("7: KEINE falsche Eskalation", all(a.kuh_id != "Eskalation" for a in nach_ausfall))

# --- 8. Fall (b): Fehlalarm, Pause >= 60 s, echte Austreibung -> sofort ----
l8 = logik()
fa = bild(l8, [blase()], 0)                    # 02:00 Fehlalarm
l8.fehlalarm_gemeldet("austreibung", fa[0].episode)
p.check("8: Fehlerkennung vorbei, 9 min Ruhe -> still", laufe(l8, 60, 10 * MIN, objekte=[], schritt=30) == [])
echt = bild(l8, [fuesse()], 10 * MIN)          # 02:10 echte Austreibung
p.check("8: echte Erkennung nach Fehlalarm -> sofort", len(echt) == 1)
p.check("8: Text 'erneut erkannt'", "erneut erkannt" in echt[0].nachricht)
p.check("8: danach wieder Takt (keine Dauermeldung)", laufe(l8, 10 * MIN + 1, 24 * MIN, schritt=5) == [])
p.check("8: Erinnerung 15 min nach der Neumeldung", len(bild(l8, [fuesse()], 25 * MIN)) == 1)

# --- 9. Fehlalarm, Objekt bleibt ohne Pause -> nur normaler Takt ----------
l9 = logik()
bild(l9, [blase()], 0)
l9.fehlalarm_gemeldet("austreibung", 1)
dauer = laufe(l9, 1, 20 * MIN, schritt=5)     # Luecke immer 5 s < 60 s
p.check("9: keine Sofort-Meldung ohne Pause", all("erneut erkannt" not in a.nachricht for a in dauer))
p.check("9: Erinnerung im normalen Takt (genau eine bis 20 min)", len(dauer) == 1)

# --- 10. Fehlalarm verschiebt die Eskalation nicht -------------------------
l10 = logik()
bild(l10, [blase()], 0)
l10.fehlalarm_gemeldet("austreibung", 1)
bild(l10, [blase()], 30 * MIN)                 # Neumeldung (Pause >= 60 s)
esk = [a for a in laufe(l10, 31 * MIN, 61 * MIN, schritt=30) if a.kuh_id == "Eskalation"]
p.check("10: Eskalation weiter 60 min nach ERSTER Erkennung", len(esk) == 1 and "seit 60 Minuten" in esk[0].nachricht)

# --- 11. Votum zu alter Episode / anderem Typ wirkungslos ------------------
l11 = logik()
bild(l11, [blase()], 0)
l11.fehlalarm_gemeldet("austreibung", 99)
l11.fehlalarm_gemeldet("kalbeverdacht", 1)
l11.fehlalarm_gemeldet("austreibung", None)
p.check("11: fremde Episode/Typ setzen nichts", l11.neu_nach_fehlalarm is False)
l11b = logik()
l11b.fehlalarm_gemeldet("austreibung", 0)      # keine laufende Episode
p.check("11: ohne laufende Episode wirkungslos", l11b.neu_nach_fehlalarm is False)

# --- 12. Notifier: sofort umgeht den Cooldown, Verdacht nicht --------------
gemeldet = []


class Zaehl(m.Notifier):
    def _telegram(self, alarm, *a, **kw):
        gemeldet.append(alarm.typ)

    def _dashboard(self, *a, **kw):
        pass

    def _mqtt(self, *a, **kw):
        pass


n = Zaehl({"stream": {"kamera": "stallwache"}, "telegram": {"cooldown_minuten": 15}, "dashboard": {}})
UHR[0] = 200_000.0
for i in range(3):
    n.melde(m.Alarm("austreibung", None, "A", 0.9, None, sofort=True, episode=1), None)
    n.melde(m.Alarm("kalbeverdacht", "Kuh #42", "K", None, None), None)
    UHR[0] += 60
p.check("12: Austreibung 3x binnen 3 min gemeldet", gemeldet.count("austreibung") == 3)
p.check("12: Kalbeverdacht bleibt im Cooldown (1x)", gemeldet.count("kalbeverdacht") == 1)

# --- 13. Feedback reicht (typ, episode) weiter, Fehler bricht nichts ab ----
fb = m.FeedbackSchleife({"telegram": {"token": "T", "chat_id": "C", "fehlalarm_ordner": str(Path("/tmp") / "lela-fb-test")}})
rueck = []
fb.bei_fehlalarm = lambda typ, ep: rueck.append((typ, ep))
mk = fb.registriere(m.Alarm("austreibung", None, "A", 0.9, None, sofort=True, episode=7), [])
fid = mk["inline_keyboard"][0][1]["callback_data"].split(":")[1]
fb.verarbeite([{"update_id": 1, "callback_query": {"id": "c1", "data": f"fb:{fid}:fehlalarm"}}])
p.check("13: Rueckmeldung (austreibung, 7)", rueck == [("austreibung", 7)])
mk = fb.registriere(m.Alarm("brunstverdacht", "Kuh #5", "B", None, None), [])
fid = mk["inline_keyboard"][0][1]["callback_data"].split(":")[1]
fb.verarbeite([{"update_id": 2, "callback_query": {"id": "c2", "data": f"fb:{fid}:fehlalarm"}}])
p.check("13: Verdacht ohne Episode -> (brunstverdacht, None)", rueck[-1] == ("brunstverdacht", None))
mk = fb.registriere(m.Alarm("austreibung", None, "A", 0.9, None, episode=8), [])
fid = mk["inline_keyboard"][0][0]["callback_data"].split(":")[1]
fb.verarbeite([{"update_id": 3, "callback_query": {"id": "c3", "data": f"fb:{fid}:treffer"}}])
p.check("13: Treffer meldet nichts zurueck", len(rueck) == 2)


def wirft(typ, ep):
    raise RuntimeError("Logik kaputt")


fb.bei_fehlalarm = wirft
mk = fb.registriere(m.Alarm("austreibung", None, "A", 0.9, None, episode=9), [])
fid = mk["inline_keyboard"][0][1]["callback_data"].split(":")[1]
ok = True
try:
    fb.verarbeite([{"update_id": 4, "callback_query": {"id": "c4", "data": f"fb:{fid}:fehlalarm"}}])
except Exception:  # noqa: BLE001
    ok = False
p.check("13: Fehler in der Rueckmeldung bricht Feedback nicht ab", ok and fb._offset == 5)
for _ in range(fb.MAX_OFFEN + 5):
    fb.registriere(m.Alarm("austreibung", None, "A", 0.9, None, episode=1), [])
p.check("13: Episoden-Merker RAM-begrenzt", len(fb._episode) <= fb.MAX_OFFEN)

# --- 14. Erinnerungstakt konfigurierbar ------------------------------------
p.check("14: leer -> telegram.cooldown_minuten", logik().erinnerung_s == 15 * MIN)
p.check("14: eigener Wert", logik(austreibung_erinnerung_minuten=10).erinnerung_s == 10 * MIN)
p.check("14: 0 -> Rueckfall auf Cooldown (nie Dauerfeuer)", logik(austreibung_erinnerung_minuten=0).erinnerung_s == 15 * MIN)
p.check("14: unter 1 min -> 1 min", logik(austreibung_erinnerung_minuten=0.2).erinnerung_s == 1 * MIN)

# --- 15. Kalbeverdacht unveraendert (Zeitfilter, kein sofort) --------------
l15 = logik()
kuh = m.KuhBeobachtung(42, (0, 0, 100, 100), 60.0, None)
verdacht = []
for i in range(25):
    UHR[0] = 300_000.0 + i
    verdacht += l15.bewerte([kuh], [])
p.check("15: Kalbeverdacht nach Mindeststichprobe", len(verdacht) == 1 and verdacht[0].typ == "kalbeverdacht")
p.check("15: Kalbeverdacht nicht sofort (Cooldown gilt)", verdacht[0].sofort is False)

sys.exit(p.bericht())
