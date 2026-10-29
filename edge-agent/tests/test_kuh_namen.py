#!/usr/bin/env python3
"""Logiktest: Kuh-Namen Stufe 1 (docs/kuh-namen-spezifikation.md, Kriterium 1).

Die Zusagen: Ein Name haengt nur an einer Tracker-Nummer, die der Landwirt
gerade im Bild sieht, und nur bis zum Neustart (nichts auf der Platte). Jeder
Name gehoert hoechstens einer Nummer. Ungueltige Namen (HTML, zu lang, leer)
aendern nichts. Telegram-Befehle zaehlen nur aus dem eingetragenen Chat.
Namen sind reine Anzeige: Alarmtext, Telegram-Kopf, Alarmbild und das JSON
der KI-Kaesten tragen sie, die Kennung kuh_id und der Cooldown nicht.
Ohne cv2/numpy, HTTP gestubbt.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import MAIN_PY, Pruefer, lade_main  # noqa: E402

m, gesendet = lade_main(mit_requests_stub=True)
p = Pruefer("Kuh-Namen")

Kuh = m.KuhBeobachtung
T0 = 1_761_577_200.0


def kuehe(*nummern):
    return [Kuh(n, (0.0, 0.0, 10.0, 10.0), None, None) for n in nummern]


# --- 1. Setzen, umbenennen, verschieben, entfernen --------------------------
n = m.KuhNamen()
p.check("1: ohne Sichtung -> Silent-Text, nichts gesetzt",
        "Silent Mode" in n.setze(12, "Berta", T0) and n.name(12) is None)
n.sehe(kuehe(12, 7, -1), T0)
antwort = n.setze(12, "Berta", T0 + 1)
p.check("1: gesetzt", n.name(12) == "Berta" and antwort.startswith("Kuh #12 heißt jetzt Berta."))
p.check("1: Antwort sagt, wie lange der Name gilt", "bis zum Neustart" in antwort)
p.check("1: Umbenennen", n.setze(12, "Resi", T0 + 2) == "Kuh #12 hieß Berta – jetzt Resi."
        and n.name(12) == "Resi")
p.check("1: Name wandert (hoechstens eine Nummer je Name)",
        n.setze(7, "resi", T0 + 3).startswith("resi war Kuh #12 – jetzt Kuh #7.")
        and n.name(12) is None and n.name(7) == "resi")
p.check("1: Leerraum zusammengefasst", n.setze(12, "  Frau   Holle ", T0 + 4)
        .startswith("Kuh #12 heißt jetzt Frau Holle.") and n.name(12) == "Frau Holle")
p.check("1: Umlaute und ß erlaubt", m.KuhNamen.gueltiger_name("Jürgen-Öße 2.") == "Jürgen-Öße 2.")
p.check("1: entfernen", n.entferne(12) == "Name von Kuh #12 (Frau Holle) entfernt."
        and n.name(12) is None)
p.check("1: entfernen ohne Namen", n.entferne(12) == "Kuh #12 hatte keinen Namen.")

# --- 2. Nur was im Bild ist ------------------------------------------------
p.check("2: unbekannte Nummer -> nichts geaendert",
        n.setze(99, "Zita", T0 + 5) == "Kuh #99 ist gerade nicht im Bild – nichts geändert."
        and n.name(99) is None)
p.check("2: 120 s nach der letzten Sichtung noch erlaubt",
        n.setze(12, "Anni", T0 + 120).startswith("Kuh #12 heißt jetzt Anni"))
p.check("2: danach nicht mehr",
        "nicht im Bild" in n.setze(12, "Anni2", T0 + 121) and n.name(12) == "Anni")

# --- 3. Ungueltige Namen ---------------------------------------------------
for roh, was in (("", "leer"), ("   ", "nur Leerzeichen"), ("<b>Berta</b>", "HTML"),
                 ("Berta\u0007", "Steuerzeichen"), ("A" * 21, "21 Zeichen"),
                 ("-Berta", "beginnt mit Bindestrich"), ("Bé", "Akzent ausserhalb der Liste")):
    vorher = dict(n._namen)
    p.check(f"3: {was} abgelehnt, nichts geaendert",
            n.setze(7, roh, T0 + 10).startswith("Name ungültig") and n._namen == vorher)
p.check("3: genau 20 Zeichen erlaubt", m.KuhNamen.gueltiger_name("A" * 20) == "A" * 20)

# --- 4. Vergessen und Obergrenze --------------------------------------------
v = m.KuhNamen()
v.sehe(kuehe(1, 2), T0)
v.setze(1, "Berta", T0)
v.sehe(kuehe(2), T0 + 24 * 3600)
p.check("4: genau 24 h ungesehen -> noch da", v.name(1) == "Berta")
v.sehe(kuehe(2), T0 + 24 * 3600 + 1)
p.check("4: laenger als 24 h ungesehen -> Nummer samt Name vergessen",
        v.name(1) is None and 1 not in v._gesehen)
p.check("4: gesehene Nummer bleibt", 2 in v._gesehen)
g = m.KuhNamen()
for i in range(250):
    g.sehe(kuehe(i), T0 + i)
p.check("4: hoechstens 200 Eintraege, aelteste zuerst raus",
        len(g._gesehen) == 200 and min(g._gesehen) == 50)

# --- 5. Text ergaenzen ------------------------------------------------------
e = m.KuhNamen()
e.sehe(kuehe(7, 12, 1), T0)
e.setze(7, "Resi", T0)
e.setze(12, "Berta", T0)
aufsprung = "Aufsprungverhalten erkannt (Kuh #7 auf Kuh #12, Dauer 6 s)"
p.check("5: zwei Nummern im Aufsprung-Text",
        e.ergaenze(aufsprung) == "Aufsprungverhalten erkannt (Kuh #7 (Resi) auf Kuh #12 (Berta), Dauer 6 s)")
p.check("5: nie doppelt", e.ergaenze(e.ergaenze(aufsprung)) == e.ergaenze(aufsprung))
e.setze(1, "Anni", T0)
p.check("5: #12 faellt nicht auf #1 zurueck",
        e.ergaenze("Kuh #12 (Berta) und Kuh #1") == "Kuh #12 (Berta) und Kuh #1 (Anni)")
p.check("5: Nummer ohne Namen bleibt", e.ergaenze("Kuh #3 liegt") == "Kuh #3 liegt")
p.check("5: name_zu fuer kuh_id", (e.name_zu("Kuh #12"), e.name_zu("Kuh #3"), e.name_zu(None),
                                   e.name_zu("Kuh #12x")) == ("Berta", None, None, None))
liste = e.liste(T0 + 1)
p.check("5: Liste nennt Namen und Lage", "Kuh #7 Resi – im Bild" in liste and "Kuh #12 Berta" in liste)
e.sehe(kuehe(3), T0 + 1)
p.check("5: Liste nennt Nummern ohne Namen im Bild", "Ohne Namen im Bild: #3" in e.liste(T0 + 2))
p.check("5: leere Liste im Silent Mode", "Silent Mode" in m.KuhNamen().liste(T0))

# --- 6. Telegram-Befehle ----------------------------------------------------
fb = m.FeedbackSchleife({"telegram": {"token": "T", "chat_id": "4711"}})
tn = m.KuhNamen()
tn.sehe(kuehe(12), m.time.time())
fb.namen = tn


def nachricht(uid, text, chat=4711):
    return {"update_id": uid, "message": {"chat": {"id": chat}, "text": text}}


def antworten():
    return [kw["data"]["text"] for url, kw in gesendet if url.endswith("/sendMessage")]


gesendet.clear()
fb.verarbeite([nachricht(100, "/kuh 12 Berta")])
p.check("6: /kuh 12 Berta setzt", tn.name(12) == "Berta")
p.check("6: Antwort per sendMessage an den eingetragenen Chat",
        antworten() and antworten()[0].startswith("Kuh #12 heißt jetzt Berta")
        and gesendet[-1][1]["data"]["chat_id"] == "4711")
p.check("6: Offset fortgeschrieben", fb._offset == 101)
gesendet.clear()
fb.verarbeite([nachricht(101, "/kuh 12 Resi", chat=999)])
p.check("6: fremder Chat ignoriert (keine Aenderung, keine Antwort)",
        tn.name(12) == "Berta" and not gesendet and fb._offset == 102)
fb.verarbeite([nachricht(102, "Guten Morgen"), nachricht(103, "/start")])
p.check("6: Nicht-Befehle bleiben still", not gesendet and fb._offset == 104)
fb.verarbeite([nachricht(104, "/kuh@StallBot #12 Resi")])
p.check("6: /kuh@Bot und #12 verstanden", tn.name(12) == "Resi")
fb.verarbeite([nachricht(105, "/kuh 12 -")])
p.check("6: /kuh 12 - entfernt", tn.name(12) is None)
fb.verarbeite([nachricht(106, "/kuh 12 Anni"), nachricht(107, "/kuh 12")])
p.check("6: /kuh 12 entfernt", tn.name(12) is None)
gesendet.clear()
fb.verarbeite([nachricht(108, "/kuh"), nachricht(109, "/kuh zwoelf Berta"), nachricht(110, "/kuehe")])
a = antworten()
p.check("6: /kuh ohne Nummer -> Hilfe", len(a) == 3 and a[0] == a[1] == m.KuhNamen.HILFE)
p.check("6: /kuehe -> Liste", "Ohne Namen im Bild: #12" in a[2])
gesendet.clear()
fb.verarbeite([nachricht(111, "/kuh 12 <script>")])
p.check("6: ungueltiger Name -> Hinweis, nichts gesetzt",
        tn.name(12) is None and antworten()[0].startswith("Name ungültig"))
aus = m.FeedbackSchleife({"telegram": {"token": "T", "chat_id": "4711"}})
gesendet.clear()
aus.verarbeite([nachricht(1, "/kuh 12 Berta")])
p.check("6: ohne namen (main() nicht verdrahtet) keine Befehle", not gesendet)

# Knopf-Antworten unveraendert
fb2 = m.FeedbackSchleife({"telegram": {"token": "T", "chat_id": "4711",
                                       "fehlalarm_ordner": "/tmp/kuh-namen-test-fb"}})
fb2.namen = m.KuhNamen()
fid = fb2.registriere(m.Alarm("brunstverdacht", "Kuh #12", "x", None, None), [])[
    "inline_keyboard"][0][0]["callback_data"].split(":")[1]
fb2.verarbeite([{"update_id": 1, "callback_query": {"id": "q", "data": f"fb:{fid}:treffer"}}])
p.check("6: Knopf-Antwort zaehlt weiter", fb2.zaehler["treffer"] == 1)

quelle = MAIN_PY.read_text(encoding="utf-8")
p.check("6: beide Abrufwege holen auch Textnachrichten",
        quelle.count("\"allowed_updates\": '[\"callback_query\",\"message\"]'") == 2
        and "'[\"callback_query\"]'" not in quelle)

# Ein kaputter Befehl stoppt nichts
class Kaputt(m.KuhNamen):
    def liste(self, jetzt=None):
        raise RuntimeError("kaputt")


fb.namen = Kaputt()
gesendet.clear()
fb.verarbeite([nachricht(200, "/kuehe")])
p.check("6: Fehler im Befehl -> Hinweis statt Absturz",
        antworten() == ["Befehl nicht verarbeitet (Log prüfen)."] and fb._offset == 201)

# --- 7. Alarm: Namen nur in der Anzeige -------------------------------------
cfg = {"stream": {"kamera": "stallwache"}, "telegram": {"token": "T", "chat_id": "4711"}}
nt = m.Notifier(cfg)
an = m.KuhNamen()
an.sehe(kuehe(7, 12), T0)
an.setze(7, "Resi", T0)
an.setze(12, "Jürgen", T0)
nt.namen = an
tg, db = [], []
nt._tg.auftrag = lambda fn, *args, **kw: tg.append(args)
nt._dashboard = lambda alarm, bilder=None: db.append(alarm)
nt._mqtt = lambda alarm: None
alarm = m.Alarm("brunstverdacht", "Kuh #12",
                "Aufsprungverhalten erkannt (Kuh #7 auf Kuh #12, Dauer 6 s)", None, None)
nt.melde(alarm, None)
gezeigt = tg[0][0]
p.check("7: Telegram-Text mit beiden Namen",
        gezeigt.nachricht == "Aufsprungverhalten erkannt (Kuh #7 (Resi) auf Kuh #12 (Jürgen), Dauer 6 s)")
p.check("7: kuh_id unveraendert, Name daneben", (gezeigt.kuh_id, gezeigt.kuh_name) == ("Kuh #12", "Jürgen"))
p.check("7: Dashboard: nachricht mit Namen, kuhId unveraendert",
        db[0].kuh_id == "Kuh #12" and "(Resi)" in db[0].nachricht)
p.check("7: Original-Alarm unangetastet", alarm.nachricht.endswith("Dauer 6 s)") and alarm.kuh_name is None)
p.check("7: Cooldown-Schluessel ohne Namen", ("Kuh #12", "brunstverdacht") in nt._zuletzt)
nt.melde(alarm, None)
p.check("7: Cooldown greift weiter", len(tg) == 1)
p.check("7: Alarmbild-Beschriftung mit Namen, ohne Umlaute",
        m.Notifier.beschriftung(gezeigt) == "brunstverdacht Kuh #12 (Juergen)")
p.check("7: Beschriftung ohne Namen wie bisher",
        m.Notifier.beschriftung(alarm) == "brunstverdacht Kuh #12")

gesendet.clear()
nt._telegram(gezeigt, None)
p.check("7: Telegram-Kopf nennt den Namen",
        antworten()[0].startswith("⚠️ BRUNSTVERDACHT – Kuh #12 (Jürgen)\n"))


class NamenKaputt(m.KuhNamen):
    def ergaenze(self, text):
        raise RuntimeError("kaputt")


nt2 = m.Notifier(cfg)
nt2.namen = NamenKaputt()
tg2 = []
nt2._tg.auftrag = lambda fn, *args, **kw: tg2.append(args)
nt2._dashboard = lambda alarm, bilder=None: None
nt2._mqtt = lambda alarm: None
nt2.melde(alarm, None)
p.check("7: Fehler bei den Namen kostet nie den Alarm", tg2 and tg2[0][0].nachricht == alarm.nachricht)

# --- 8. JSON der KI-Kaesten -------------------------------------------------
ka = m.KiAnsicht({}, "stallwache", 0.80)
ki_kuehe = [Kuh(12, (0.0, 0.0, 960.0, 540.0), 52.44, None), Kuh(7, (0.0, 0.0, 96.0, 54.0), None, None)]
d = ka.daten(1920, 1080, ki_kuehe, [], T0)
p.check("8: ohne namen kein Feld", all("name" not in k for k in d["kuehe"]))
ka.namen = an
d = ka.daten(1920, 1080, ki_kuehe, [], T0)
p.check("8: Name nur, wo gesetzt",
        d["kuehe"][0] == {"id": 12, "box": [0.0, 0.0, 0.5, 0.5], "winkel": 52.4, "name": "Jürgen"}
        and d["kuehe"][1]["name"] == "Resi")
an.entferne(7)
d = ka.daten(1920, 1080, ki_kuehe, [], T0)
p.check("8: entfernter Name -> Feld fehlt", "name" not in d["kuehe"][1])

# --- 9. Verdrahtung in main(), nichts auf der Platte ------------------------
haupt = quelle[quelle.index("def main() -> None:"):]
p.check("9: main() verdrahtet Notifier, Befehle und KI-Ansicht",
        "notifier.namen = notifier.feedback.namen = ki_ansicht.namen = namen" in haupt)
analyse = haupt.index("kuehe, objekte = engine.analysiere(frame)")
sehen = haupt.index("namen.sehe(kuehe)")
alarme = haupt.index("logik.bewerte(kuehe, objekte)")
p.check("9: Sichtungen nach der Analyse, vor den Alarmen", analyse < sehen < alarme)
klasse = quelle[quelle.index("class KuhNamen:"):quelle.index("class KiAnsicht:")]
p.check("9: KuhNamen schreibt nichts auf die Platte",
        not any(w in klasse for w in ("open(", "write_text", "json.dump", "Path(")))

sys.exit(p.bericht())
