#!/usr/bin/env python3
"""Logiktests Brunst-Plausibilitaet: ein Kalb bei der Mutter ist kein Aufsprung.

Befund ki-wache (27.10.2026): Das Modell kennt keine Klasse Kalb. Ein Kalb
unter oder neben der Mutter wird als `kuh` erkannt und ueberlappt mit IoU
0,21-0,37. IoU, Hoehenversatz und 4 s Mindestdauer liessen das als Aufsprung
durch: Brunstverdacht jede Nacht, solange das Kalb in der Bucht liegt.
Abnahmekriterien A1-A7 aus docs/brunst-plausibilitaet-spezifikation.md §7.
"""

import math
import sys
import time as echte_zeit
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer, lade_main

m, _ = lade_main()
p = Pruefer("Brunst-Plausibilitaet")

UHR = [100_000.0]
m.time = types.SimpleNamespace(
    **{k: getattr(echte_zeit, k) for k in dir(echte_zeit) if not k.startswith("_")}
)
m.time.time = lambda: UHR[0]

LOGIK = {
    "winkel_schwelle_grad": 45, "fenster_minuten": 30, "anteil_schwelle": 0.20,
    "override_konfidenz": 0.80, "brunst_min_dauer_s": 4, "eskalation_minuten": 60,
}


def logik(**werte):
    return m.LogicEngine({"logik": dict(LOGIK, **werte), "telegram": {"cooldown_minuten": 15}})


def kuh(tid, box):
    return m.KuhBeobachtung(tid, box, None, None)


def lauf(lg, kuehe, sekunden, objekte=()):
    """1 FPS: dieselben Boxen `sekunden` Bilder lang; alle Alarme."""
    alarme = []
    for _ in range(sekunden):
        alarme += lg.bewerte(list(kuehe), list(objekte))
        UHR[0] += 1
    return alarme


def brunst(alarme):
    return [a for a in alarme if a.typ == "brunstverdacht"]


# Mutter steht (400 x 300), Kalb liegt in ihrer Box unter dem Bauch. Ganz
# enthalten -> IoU = Flaechenverhaeltnis; die drei Werte decken den Befund ab.
MUTTER = (100.0, 100.0, 500.0, 400.0)
KAELBER = {
    0.21: (190.0, 280.0, 400.0, 400.0),
    0.29: (180.0, 220.0, 412.0, 370.0),
    0.37: (150.0, 250.0, 446.0, 400.0),
}
# Echter Aufsprung, gleich grosse Boxen: Kuh #3 springt von hinten auf Kuh #4.
AUFSPRINGER = (100.0, 50.0, 500.0, 350.0)
BESPRUNGEN = (300.0, 150.0, 700.0, 450.0)

# --- A1: Kalb liegt unter der Mutter -> kein Brunstverdacht -----------------

for iou_soll, kalb in KAELBER.items():
    iou = m.LogicEngine._iou(MUTTER, kalb)
    p.check(f"A1: Kalb-Box mit IoU {iou:.2f} ~ Befund {iou_soll}", abs(iou - iou_soll) < 0.005)
    alarme = lauf(logik(), [kuh(1, MUTTER), kuh(2, kalb)], 120)
    p.check(f"A1: Kalb unter der Mutter (IoU {iou_soll}), 2 min -> kein Brunstverdacht",
            brunst(alarme) == [])

# Gegenprobe = der Befund: ohne Flaechenpruefung meldete der Agent Brunst
alarme = lauf(logik(brunst_min_flaechenverhaeltnis=0), [kuh(1, MUTTER), kuh(2, KAELBER[0.29])], 10)
p.check("A1: Gegenprobe ohne Flaechenpruefung (0 = aus): Brunstverdacht wie bisher",
        [a.kuh_id for a in brunst(alarme)] == ["Kuh #2"])

# --- A2: echter Aufsprung, gleich grosse Boxen -> weiterhin Alarm ----------

p.check("A2: Aufsprung-Boxen gleich gross",
        m.LogicEngine._flaechenverhaeltnis(AUFSPRINGER, BESPRUNGEN) == 1.0)
lg = logik()
paar = [kuh(3, AUFSPRINGER), kuh(4, BESPRUNGEN)]
vorher = brunst(lauf(lg, paar, 4))
p.check("A2: vor 4 s kein Alarm (Mindestdauer unveraendert)", vorher == [])
alarme = brunst(lauf(lg, paar, 30))
p.check("A2: echter Aufsprung -> genau ein Brunstverdacht", len(alarme) == 1)
p.check("A2: Alarm fuer die besprungene (untere) Kuh, ihre Box",
        bool(alarme) and alarme[0].kuh_id == "Kuh #4" and alarme[0].box == BESPRUNGEN)
p.check(
    "A2: Alarmtext unveraendert",
    bool(alarme) and alarme[0].nachricht
    == "Aufsprungverhalten erkannt (Kuh #3 auf Kuh #4, Dauer 4 s) – Duldung deutet auf Brunst hin",
)
p.check("A2: regelbasiert -> Konfidenz None, durch Cooldown", bool(alarme)
        and alarme[0].konfidenz is None and alarme[0].sofort is False)

# Kalb im selben Bild stoert den echten Aufsprung nicht
lg = logik()
alarme = brunst(lauf(lg, [kuh(3, AUFSPRINGER), kuh(4, BESPRUNGEN), kuh(5, KAELBER[0.37])], 10))
p.check("A2: Aufsprung mit Kalb daneben -> nur das Kuh-Paar meldet",
        [a.kuh_id for a in alarme] == ["Kuh #4"])

# --- A3: Grenzwerte des Flaechenverhaeltnisses -----------------------------

lg = logik()
GROSS = (0.0, 0.0, 1000.0, 100.0)
genau = (0.0, 55.0, 1000.0, 100.0)    # 45 % der Flaeche, ganz enthalten
knapp = (0.0, 55.1, 1000.0, 100.0)    # 44,9 %
p.check("A3: Verhaeltnis genau 0.45 -> Aufsprung-Lage", lg._aufsprung_lage(kuh(1, GROSS), kuh(2, genau)) is not None)
p.check("A3: Verhaeltnis 0.449 -> keine Aufsprung-Lage", lg._aufsprung_lage(kuh(1, GROSS), kuh(2, knapp)) is None)
p.check("A3: Verhaeltnis symmetrisch (kleinere/groessere)",
        m.LogicEngine._flaechenverhaeltnis(GROSS, genau) == m.LogicEngine._flaechenverhaeltnis(genau, GROSS))
p.check("A3: entartete Box -> 0 statt Division durch null",
        m.LogicEngine._flaechenverhaeltnis((5, 5, 5, 5), (5, 5, 5, 5)) == 0.0)
lage = lg._aufsprung_lage(kuh(4, BESPRUNGEN), kuh(3, AUFSPRINGER))
p.check("A3: oben/unten unabhaengig von der Reihenfolge",
        lage is not None and (lage[0].track_id, lage[1].track_id) == (3, 4))

# --- A4: Konfiguration ------------------------------------------------------

lg = logik()
p.check("A4: fehlende Schluessel -> Defaults 0.15 / 0.20 / 0.45",
        (lg.brunst_min_iou, lg.brunst_min_versatz, lg.brunst_min_flaeche) == (0.15, 0.20, 0.45))
lg = logik(brunst_min_iou=None, brunst_min_hoehenversatz=None, brunst_min_flaechenverhaeltnis=None)
p.check("A4: leere YAML-Werte -> Defaults",
        (lg.brunst_min_iou, lg.brunst_min_versatz, lg.brunst_min_flaeche) == (0.15, 0.20, 0.45))
p.check("A4: 0 bleibt 0 (Pruefung aus)", logik(brunst_min_flaechenverhaeltnis=0).brunst_min_flaeche == 0.0)
p.check("A4: Werte als Text (YAML-Zitat) werden Zahlen",
        logik(brunst_min_flaechenverhaeltnis="0.5").brunst_min_flaeche == 0.5)

# Bisher fest verdrahtet, jetzt Config: Defaults verhalten sich wie vorher
lg = logik()
oben = kuh(1, (0.0, 0.0, 100.0, 100.0))
p.check("A4: IoU genau 0.15 reicht (wie bisher >= 0.15)",
        abs(m.LogicEngine._iou(oben.box, (0.0, 0.0, 100.0, 15.0)) - 0.15) < 1e-12)
p.check("A4: Versatz genau 20 % der unteren Boxhoehe reicht (wie bisher)",
        lg._aufsprung_lage(kuh(1, (0, 0, 100, 120)), kuh(2, (0, 20, 100, 120))) is not None)
p.check("A4: Versatz knapp unter 20 % -> kein Aufsprung (wie bisher)",
        lg._aufsprung_lage(kuh(1, (0, 0, 100, 120)), kuh(2, (0, 19.9, 100, 120))) is None)
p.check("A4: brunst_min_iou aus der Config wirkt (0.5 > IoU 0.2)",
        logik(brunst_min_iou=0.5)._aufsprung_lage(*paar) is None)
p.check("A4: brunst_min_hoehenversatz aus der Config wirkt (0.5 > 100/300)",
        logik(brunst_min_hoehenversatz=0.5)._aufsprung_lage(*paar) is None)

# --- A5: Austreibung unberuehrt (Recall 100 %) -----------------------------

BLASE = m.ObjektErkennung("amniotic_sac", 0.91, (300.0, 300.0, 340.0, 340.0))
FUESSE = m.ObjektErkennung("calf_legs", 0.86, (300.0, 300.0, 340.0, 340.0))
for name, werte in (("Default", {}), ("strengste Flaechenpruefung 1.0", {"brunst_min_flaechenverhaeltnis": 1.0})):
    lg = logik(**werte)
    erste = lg.bewerte([kuh(1, MUTTER), kuh(2, KAELBER[0.37])], [BLASE])
    UHR[0] += 1
    p.check(f"A5 ({name}): Fruchtblase bei Mutter + Kalb -> Austreibung im ersten Bild",
            [(a.typ, a.sofort) for a in erste] == [("austreibung", True)])
lg = logik()
erste = lg.bewerte([kuh(1, MUTTER), kuh(2, KAELBER[0.21])], [FUESSE])
UHR[0] += 1
p.check("A5: Kaelberfuesse neben einem Kalb-Paar -> Austreibung",
        [a.typ for a in erste] == ["austreibung"])

# --- A6: Wach-Modus aendert die Flaechenpruefung nicht ---------------------

lg = logik(wach_modus=True)
p.check("A6: Wach-Modus halbiert nur die Mindestdauer (4 -> 2 s)",
        lg.brunst_dauer == 2.0 and lg.brunst_min_flaeche == 0.45)
p.check("A6: Wach-Modus, Kalb unter der Mutter -> kein Brunstverdacht",
        brunst(lauf(lg, [kuh(1, MUTTER), kuh(2, KAELBER[0.37])], 60)) == [])
p.check("A6: Wach-Modus, echter Aufsprung -> Alarm nach 2 s",
        len(brunst(lauf(logik(wach_modus=True), paar, 3))) == 1)

# --- A7: Geometrie-Simulation ----------------------------------------------
# Lochkamera ueber dem Stall, Tiere als Punktwolken (x = Koerperachse, Kopf
# bei +x; z = Hoehe in m), Box = Huelle der Projektion. Ausgewertet wird
# genau _aufsprung_lage des Agenten. Ein Quader-Modell ohne Verdeckung und
# ohne Detektor-Rauschen: Es begruendet die Defaults, ersetzt aber nicht die
# Abnahme am Geraet (Spezifikation §7, G1-G3).


def kamera(abstand, hoehe, f=1000.0):
    """Kamera bei (0, -abstand, hoehe), Blick auf (0, 0, 0.8); v nach unten."""
    fy, fz = abstand, 0.8 - hoehe
    n = math.hypot(fy, fz)
    fy, fz = fy / n, fz / n

    def bild(x, y, z):
        py, pz = y + abstand, z - hoehe
        t = py * fy + pz * fz
        return f * x / t, f * (py * fz - pz * fy) / t

    return bild


def quader(laenge, breite, hoehe, z0=0.0):
    return [(x, y, z) for x in (-laenge / 2, laenge / 2)
            for y in (-breite / 2, breite / 2) for z in (z0, z0 + hoehe)]


# Stehende Kuh: Rumpf, Beine, Kopf und Hals vorgestreckt (Nase bei +1,75 m)
KUH = (quader(2.4, 0.7, 1.0, 0.5) + quader(2.0, 0.6, 0.5)
       + [(1.4, y, z) for y in (-0.2, 0.2) for z in (1.0, 1.55)]
       + [(1.75, y, z) for y in (-0.15, 0.15) for z in (1.0, 1.35)])
KALB_LIEGT = quader(0.9, 0.45, 0.5)
KALB_STEHT = quader(0.9, 0.35, 0.8) + [(0.55, 0.0, 0.85)]


def kuh_liegt(kopf_hoch):
    return quader(2.2, 1.2, 0.85) + [(1.3, y, z) for y in (-0.2, 0.2) for z in (0.4, 1.1 if kopf_hoch else 0.7)]


def aufspringer(neigung):
    """Hinterhufe bei x = 0, Ruecken steigt nach +x, Vorderbeine haengen seitlich."""
    a = math.radians(neigung)
    xw, zw = 0.1 + 1.6 * math.cos(a), 1.45 + 1.6 * math.sin(a)  # Widerrist
    pkt = [(0.0, y, 0.0) for y in (-0.3, 0.3)]
    pkt += [(x, y, z) for x, z0 in ((0.1, 1.45), (xw, zw))
            for y in (-0.35, 0.35) for z in (z0, z0 - 0.9)]
    pkt += [(xw + 0.5, y, zw + 0.1) for y in (-0.2, 0.2)]  # Kopf
    pkt += [(xw + 0.2, y, 1.0) for y in (-0.45, 0.45)]     # Vorderbeine
    return pkt


def platziere(punkte, s=1.0, dx=0.0, dy=0.0, az=0.0, welt=(0.0, 0.0)):
    """Skalieren, im Koerper verschieben, um az drehen, in der Welt verschieben."""
    c, si = math.cos(az), math.sin(az)
    aus = []
    for x, y, z in punkte:
        x, y, z = x * s + dx, y * s + dy, z * s
        aus.append((x * c - y * si + welt[0], x * si + y * c + welt[1], z))
    return aus


def box(bild, punkte):
    uv = [bild(*q) for q in punkte]
    return (min(u for u, _ in uv), min(v for _, v in uv), max(u for u, _ in uv), max(v for _, v in uv))


# (Abstand, Hoehe) in m; die beiden ersten haengen nah am Geschehen.
STANDORTE = ((3, 2.2), (4, 3.5), (5, 2.5), (6, 3.5), (8, 4.0), (10, 3.0))
KAMERAS = [kamera(d, h) for d, h in STANDORTE]
KAMERAS_AB_5M = [kamera(d, h) for d, h in STANDORTE if d >= 5]
WINKEL = [math.radians(w) for w in range(0, 360, 15)]


def aufspruenge(s_oben, s_unten, kameras=KAMERAS):
    for bild in kameras:
        for az in WINKEL:
            for neigung in (25, 35, 45):
                besprungen = platziere(KUH, s_unten, az=az)
                springer = platziere(aufspringer(neigung), s_oben, dx=-1.2 * s_unten - 0.6 * s_oben, az=az)
                yield box(bild, springer), box(bild, besprungen)


def kalb_bei_mutter(kameras=KAMERAS):
    """Kalb liegt/steht unter, neben oder bis 2 m vor der Mutter (Richtung Kamera)."""
    for bild in kameras:
        for az in WINKEL:
            mutter = box(bild, platziere(KUH, az=az))
            for vor in (0.0, 0.5, 1.0, 1.5, 2.0):
                for seit in (-1.0, -0.5, 0.0, 0.5, 1.0):
                    for kalb in (KALB_LIEGT, KALB_STEHT):
                        yield mutter, box(bild, platziere(kalb, az=az, welt=(seit, -vor)))


def liegende_neben_stehender():
    for bild in KAMERAS:
        for az in WINKEL:
            steht = box(bild, platziere(KUH, az=az))
            for dy in (0.9, -0.9, 1.2, -1.2):
                for dx in (0.0, 0.8, -0.8):
                    for kopf_hoch in (True, False):
                        yield steht, box(bild, platziere(kuh_liegt(kopf_hoch), dx=dx, dy=dy, az=az))


ALT, NEU = logik(brunst_min_flaechenverhaeltnis=0), logik()


def zaehle(faelle):
    """(Faelle mit Aufsprung-Lage nach alter Regel, davon nach neuer Regel)."""
    alt = neu = 0
    for a, b in faelle:
        ka, kb = kuh(1, a), kuh(2, b)
        if ALT._aufsprung_lage(ka, kb) is not None:
            alt += 1
            neu += NEU._aufsprung_lage(ka, kb) is not None
    return alt, neu


ergebnis = {
    "Kalb bei der Mutter": zaehle(kalb_bei_mutter()),
    "Kuh auf Kuh": zaehle(aufspruenge(1.0, 1.0)),
    "Faerse (0.85) auf Kuh": zaehle(aufspruenge(0.85, 1.0)),
    "Kuh auf Faerse (0.85)": zaehle(aufspruenge(1.0, 0.85)),
    "Jungrind (0.75) auf Kuh": zaehle(aufspruenge(0.75, 1.0)),
    "Kuh auf Jungrind (0.75)": zaehle(aufspruenge(1.0, 0.75)),
    "liegende Kuh neben stehender": zaehle(liegende_neben_stehender()),
}
print("A7 Simulation (Aufsprung-Lage je Bild):  alte Regel -> mit Flaechenverhaeltnis >= 0.45")
for name, (alt, neu) in ergebnis.items():
    print(f"     {name:30} {alt:5} -> {neu:5}  ({100 * neu / alt:5.1f} % bleiben)")


def anteil(name):
    alt, neu = ergebnis[name]
    return neu / alt


p.check("A7: Befund im Modell nachgestellt (alte Regel sieht im Kalb einen Aufsprung)",
        ergebnis["Kalb bei der Mutter"][0] >= 1000)
p.check("A7: Kalb bei der Mutter -> >= 99 % unterdrueckt", anteil("Kalb bei der Mutter") <= 0.01)
p.check("A7: Kuh auf Kuh -> >= 90 % bleiben", anteil("Kuh auf Kuh") >= 0.90)
p.check("A7: Faerse/Kuh -> >= 75 % bleiben (Preis, Spezifikation Risiko 1)",
        min(anteil("Faerse (0.85) auf Kuh"), anteil("Kuh auf Faerse (0.85)")) >= 0.75)
fern_alt, fern_neu = zaehle(aufspruenge(1.0, 1.0, KAMERAS_AB_5M))
kalb_alt, kalb_neu = zaehle(kalb_bei_mutter(KAMERAS_AB_5M))
print(f"     ab 5 m Abstand: Kuh auf Kuh {fern_alt} -> {fern_neu}, Kalb {kalb_alt} -> {kalb_neu}")
p.check("A7: Kamera ab 5 m -> kein Aufsprung verloren, kein Kalb-Rest (Verluste nur nah)",
        fern_neu == fern_alt > 0 and kalb_neu == 0 < kalb_alt)
p.check("A7: liegende Kuh neben stehender bleibt offen (Stufe 2, nicht durch Stufe 1 geloest)",
        anteil("liegende Kuh neben stehender") >= 0.5)

# --- A7b: verworfene Pruefungen (Spezifikation §1, Widerspruch) ------------
# Seitenverhaeltnis B/H der unteren Box (liegend = flach) und Obergrenze des
# Hoehenversatzes (Kalb reicht der Mutter nur bis zum Bauch). Gemessen an den
# Paaren, die die alte Regel als Aufsprung-Lage sieht.


def kennzahlen(faelle):
    bh, versatz = [], []
    for a, b in faelle:
        lage = ALT._aufsprung_lage(kuh(1, a), kuh(2, b))
        if lage is None:
            continue
        o, u = lage[0].box, lage[1].box
        bh.append((u[2] - u[0]) / (u[3] - u[1]))
        versatz.append((u[1] - o[1]) / (o[3] - o[1]))
    return bh, versatz


bh_auf, vs_auf = kennzahlen(aufspruenge(1.0, 1.0))
bh_lieg, _ = kennzahlen(liegende_neben_stehender())
_, vs_kalb = kennzahlen(kalb_bei_mutter())
print(f"     B/H untere Box: Aufsprung bis {max(bh_auf):.2f}, liegende Kuh bis {max(bh_lieg):.2f}")
print(f"     Hoehenversatz/obere Boxhoehe: Aufsprung {min(vs_auf):.2f}-{max(vs_auf):.2f}, "
      f"Kalb {min(vs_kalb):.2f}-{max(vs_kalb):.2f}")
p.check("A7b: Seitenverhaeltnis trennt nicht (stehende Besprungene ueber 1.9 = Festliege-Liegeschwelle)",
        max(bh_auf) > 1.9)
p.check("A7b: Hoehen-Obergrenze trennt nicht (Kalb und Aufsprung ueberlappen)",
        min(vs_kalb) < max(vs_auf))

sys.exit(p.bericht())
