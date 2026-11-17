#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Konverter: CVAT-Export ("CVAT for images 1.1") -> Ultralytics-YOLO-Pose-Datensatz.

Warum ein eigener Konverter?
  CVATs eingebauter Export "Ultralytics YOLO Pose" berechnet die Box jedes Objekts aus den
  Keypoints (kleinstes umschließendes Rechteck). Mit nur 3 Keypoints (spine_end, tail_base,
  tail_tip) wäre die Kuh-Box ein schmaler Streifen entlang Rücken/Schwanz — unbrauchbar für
  Detektion und ByteTrack. Deshalb wird in CVAT eine echte Box `kuh` (Rechteck) PLUS ein Skelett
  `kuh_pose` gelabelt; dieser Konverter fügt beides zu einem YOLO-Pose-Objekt zusammen.

Klassen / Keypoints (Vertrag mit dem Edge-Agenten, Reihenfolge fest):
  0 kuh, 1 amniotic_sac, 2 calf_legs  —  Keypoints: 0 spine_end, 1 tail_base, 2 tail_tip
  kpt_shape [3, 3], flip_idx [0, 1, 2] (alle Punkte auf der Mittellinie, kein Links/Rechts-Tausch)

Sichtbarkeit (CVAT -> YOLO):
  Punkt "Outside" (nicht sichtbar, Position unbekannt) -> v=0, x=y=0   (Regel: nie raten)
  Punkt "Occluded" (verdeckt, Position eindeutig)       -> v=1
  sonst                                                  -> v=2
  Punkt außerhalb des Bildes                             -> v=0 (sonst verwirft Ultralytics das ganze Bild)

Paarung Box <-> Skelett je Bild:
  1. gleiche CVAT-Gruppe (group_id) gewinnt immer;
  2. liegen alle gelabelten Punkte eines (ungruppierten) Skeletts in ZWEI oder mehr Kuh-Boxen (mit dem
     10-%-Rand wie bei der Zulässigkeit — Vorschlagsboxen schneiden den Schwanz oft knapp ab), ist die
     Zuordnung geometrisch nicht entscheidbar -> FEHLER "gruppieren" (README-Regel: überlappende Kühe in
     CVAT mit G gruppieren). Keine Heuristik rät hier still;
  3. sonst optimale Zuordnung (ungarischer Algorithmus) mit Bewertung je Paar =
     2 x Punkte streng in der Box + 1 x Punkte nur im 10-%-Rand + 0.9 x Spannweite.
  Knappe, aber entscheidbare Fälle werden als Warnung "knappe_paarung" gemeldet.

Geprüft-Markierung: Exporte des Stall-Labelers (B18, erkennbar an <meta><source>stall_labeler) liefern NUR
Bilder mit dem Tag "geprueft" — ungeprüfte (auch leere) Bilder fließen nie als Negativbeispiel ein; ein
Labeler-Export ohne ein einziges geprüftes Bild ist ein Fehler. Andere Exporte (CVAT) mit mindestens einem
"geprueft"-Tag werden genauso behandelt; CVAT-Exporte ohne Tag zählen vollständig (nur fertige Aufgaben exportieren).

Split: ausschließlich aus manifest.csv (Spalte split). Geschnitten wird nach STALLTAG
(12:00–12:00 Uhr Ortszeit, damit jede Nacht vollständig in einem Split liegt). Dateinamen sind UTC.
Train-Bilder im Abstand < --puffer-min zu einem Val-Bild werden verworfen.
Bilder mit defekt_anteil > 0.04 (Dekodier-Streifen) werden nie übernommen.

Abbruch (Exit-Code 2, außer mit --erzwingen), bevor irgendetwas geschrieben wird:
  - Skelett ohne passende Box            - Aufgabe mit Kuh-Boxen, aber ohne ein einziges Skelett
  - unbekannte Keypoint-Namen            - Datenleck (Datei oder Stalltag in train UND val)
  - Quellbild fehlt / Ausgabe existiert schon

Beispiel (auf dem Hof-Rechner):
  python3 cvat_zu_yolo_pose.py --xml ../exporte/*.zip --bilder ../.. \
      --manifest ../../_cvat_v1/manifest.csv --ausgabe ../datensatz_v1 --zip
"""
import argparse
import bisect
import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

KLASSEN = ["kuh", "amniotic_sac", "calf_legs"]
KEYPOINTS = ["spine_end", "tail_base", "tail_tip"]
FLIP_IDX = [0, 1, 2]
SCHWELLE_DEFEKT = 0.04
RAND_TOLERANZ = 0.10
SPANNWEITE_GEWICHT = 0.9
MEHRDEUTIG_ABSTAND = 0.15
MAX_BEISPIELE = 50
ZEITZONE = "Europe/Berlin"
STALLTAG_WECHSEL_STUNDE = 12
HIER = os.path.dirname(os.path.abspath(__file__))
STANDARD_BEILAGEN = [os.path.join(HIER, "abnahme_gates.py"), os.path.join(HIER, "bildqualitaet.py")]
VORSCHLAG_QUELLEN = ("auto", "file")
GEPRUEFT_TAG = "geprueft"


class KonverterFehler(Exception):
    pass


# ----------------------------------------------------------------------------- Zeit
_ZEIT_RE = re.compile(r"(\d{8})-(\d{6})")


def zeitstempel(name):
    """UTC-Zeitpunkt aus dem Dateinamen (auch mit Präfix, z. B. stallwache_20261012-100000.jpg)."""
    m = _ZEIT_RE.search(os.path.basename(name))
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def stalltag(name):
    """Stalltag (ISO-Datum): Ortszeit minus 12 h — eine Nacht gehört komplett zu einem Stalltag."""
    t = zeitstempel(name)
    if t is None:
        return None
    from zoneinfo import ZoneInfo
    lokal = t.astimezone(ZoneInfo(ZEITZONE))
    return (lokal - dt.timedelta(hours=STALLTAG_WECHSEL_STUNDE)).date().isoformat()


# ----------------------------------------------------------------------------- Einlesen
def lies_xml_quellen(pfade):
    """Liefert [(quellname, xml_bytes)] — akzeptiert .xml oder CVAT-Export-ZIPs (annotations.xml)."""
    quellen = []
    for p in pfade:
        if p.lower().endswith(".zip"):
            with zipfile.ZipFile(p) as zf:
                xmls = [n for n in zf.namelist() if n.lower().endswith(".xml")]
                if not xmls:
                    raise KonverterFehler(f"{p}: kein annotations.xml im ZIP")
                for n in xmls:
                    quellen.append((f"{os.path.basename(p)}:{n}", zf.read(n)))
        else:
            with open(p, "rb") as fh:
                quellen.append((os.path.basename(p), fh.read()))
    return quellen


def box_achsenparallel(el):
    x1, y1, x2, y2 = float(el.get("xtl")), float(el.get("ytl")), float(el.get("xbr")), float(el.get("ybr"))
    rot = float(el.get("rotation", "0") or 0)
    if abs(rot) > 1e-6:
        import math
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        hw, hh = (x2 - x1) / 2, (y2 - y1) / 2
        a = math.radians(rot)
        ca, sa = abs(math.cos(a)), abs(math.sin(a))
        ex, ey = hw * ca + hh * sa, hw * sa + hh * ca
        x1, x2, y1, y2 = cx - ex, cx + ex, cy - ey, cy + ey
    return x1, y1, x2, y2


def parse_cvat(quellen, box_label="kuh", pose_label="kuh_pose"):
    """Gibt {bildname: dict(w, h, quelle, aufgabe, boxen[], skelette[], tags[])}, Aufgaben-Statistik, Warnungen zurück.
    Aufgabe = Quelle + task_id (Projekt-Exporte enthalten mehrere Aufgaben in einer Datei)."""
    bilder = {}
    aufgaben = defaultdict(Counter)
    warnungen = defaultdict(list)
    labeler_aufgaben = set()
    for quelle, daten in quellen:
        root = ET.parse(io.BytesIO(daten)).getroot()
        quelle_meta = (root.findtext("meta/source") or "").strip()
        ist_labeler = quelle_meta.startswith("stall_labeler")
        for im in root.iter("image"):
            name = os.path.basename(im.get("name", ""))
            if not name:
                continue
            if name in bilder:
                raise KonverterFehler(f"Bild {name} kommt doppelt vor ({bilder[name]['quelle']} und {quelle}) — "
                                      "je Paket nur den neuesten Export in den Ordner legen.")
            aufgabe = quelle + (f"#task{im.get('task_id')}" if im.get("task_id") else "")
            if ist_labeler:
                labeler_aufgaben.add(aufgabe)
            st = aufgaben[aufgabe]
            eintrag = {"w": int(float(im.get("width"))), "h": int(float(im.get("height"))), "quelle": quelle,
                       "aufgabe": aufgabe, "boxen": [], "skelette": [], "tags": []}
            for el in im:
                lab = el.get("label")
                if el.get("outside", "0") == "1" and el.tag in ("box", "skeleton"):
                    continue   # aus Tracks: Objekt in diesem Bild nicht vorhanden
                if el.tag == "box":
                    if lab not in (box_label, "amniotic_sac", "calf_legs"):
                        warnungen["unbekanntes_label"].append(f"{name}: box '{lab}'")
                        continue
                    klasse = "kuh" if lab == box_label else lab
                    eintrag["boxen"].append({"klasse": klasse, "xyxy": box_achsenparallel(el),
                                             "gruppe": el.get("group_id") or None, "quelle": el.get("source", "manual")})
                    st[f"box_{klasse}"] += 1
                elif el.tag == "skeleton":
                    if lab != pose_label:
                        warnungen["unbekanntes_label"].append(f"{name}: skeleton '{lab}'")
                        continue
                    punkte = {}
                    for p in el.findall("points"):
                        pl = p.get("label")
                        if pl not in KEYPOINTS:
                            raise KonverterFehler(f"{name}: unbekannter Keypoint '{pl}' — erwartet {KEYPOINTS}")
                        koords = p.get("points", "").split(";")[0].split(",")
                        x, y = (float(koords[0]), float(koords[1])) if len(koords) == 2 else (0.0, 0.0)
                        if p.get("outside", "0") == "1":
                            v = 0
                        elif p.get("occluded", "0") == "1":
                            v = 1
                        else:
                            v = 2
                        punkte[pl] = (x, y, v)
                    pts = [punkte.get(k, (0.0, 0.0, 0)) for k in KEYPOINTS]
                    eintrag["skelette"].append({"pts": pts, "gruppe": el.get("group_id") or None})
                    st["skelett"] += 1
                elif el.tag == "tag":
                    eintrag["tags"].append(lab)
                elif el.tag in ("polygon", "polyline", "points", "ellipse", "mask", "cuboid"):
                    warnungen["nicht_unterstuetzte_form"].append(f"{name}: {el.tag} '{lab}'")
            bilder[name] = eintrag
            st["bilder"] += 1
    for a in labeler_aufgaben:
        aufgaben[a]["stall_labeler"] = 1
    return bilder, {k: dict(v) for k, v in aufgaben.items()}, warnungen


# ----------------------------------------------------------------------------- Paarung
def ungarisch(kosten):
    """Minimale Zuordnung (Kuhn-Munkres) für eine quadratische Kostenmatrix. Rückgabe: Spalte je Zeile."""
    n = len(kosten)
    unendlich = float("inf")
    u, v, p, weg = [0.0] * (n + 1), [0.0] * (n + 1), [0] * (n + 1), [0] * (n + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, benutzt = [unendlich] * (n + 1), [False] * (n + 1)
        while True:
            benutzt[j0] = True
            i0, delta, j1 = p[j0], unendlich, 0
            for j in range(1, n + 1):
                if not benutzt[j]:
                    cur = kosten[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], weg[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(n + 1):
                if benutzt[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = weg[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    zeile_zu_spalte = [-1] * n
    for j in range(1, n + 1):
        if p[j]:
            zeile_zu_spalte[p[j] - 1] = j - 1
    return zeile_zu_spalte


def _gelabelt(skelett):
    return [(x, y) for x, y, v in skelett["pts"] if v > 0]


def enthaelt_mit_rand(skelett, box, rand=RAND_TOLERANZ):
    """Alle gelabelten Punkte liegen in der Box (um `rand` x Breite/Höhe erweitert)."""
    x1, y1, x2, y2 = box["xyxy"]
    mx, my = rand * max(x2 - x1, 1e-6), rand * max(y2 - y1, 1e-6)
    pts = _gelabelt(skelett)
    return bool(pts) and all(x1 - mx <= x <= x2 + mx and y1 - my <= y <= y2 + my for x, y in pts)


def bewertung(skelett, box):
    """None wenn unzulässig, sonst 2 x Punkte streng in der Box + 1 x Punkte nur im Rand + 0.9 x Spannweite."""
    gelabelt = _gelabelt(skelett)
    if not gelabelt:
        return None
    x1, y1, x2, y2 = box["xyxy"]
    bw, bh = max(x2 - x1, 1e-6), max(y2 - y1, 1e-6)
    mx, my = RAND_TOLERANZ * bw, RAND_TOLERANZ * bh
    streng = sum(1 for x, y in gelabelt if x1 <= x <= x2 and y1 <= y <= y2)
    drin = sum(1 for x, y in gelabelt if x1 - mx <= x <= x2 + mx and y1 - my <= y <= y2 + my)
    if drin < max(1, len(gelabelt) - 1):
        return None
    xs, ys = [p[0] for p in gelabelt], [p[1] for p in gelabelt]
    spannweite = min(1.0, max((max(xs) - min(xs)) / bw, (max(ys) - min(ys)) / bh))
    return 2 * streng + (drin - streng) + SPANNWEITE_GEWICHT * spannweite


def paare_box_skelett(kuh_boxen, skelette):
    """Rückgabe: (zuordnung, mehrdeutig, ohne_box, knapp) — mehrdeutig/ohne_box sind Fehler, knapp nur Warnung.
    zuordnung {skelett_idx: box_idx} enthält auch für mehrdeutige Skelette einen besten Versuch (nur für --erzwingen)."""
    zuordnung, mehrdeutig, ohne_box, knapp = {}, [], [], []
    benutzt = set()
    for si, s in enumerate(skelette):
        if s["gruppe"]:
            kand = [bi for bi, b in enumerate(kuh_boxen) if b["gruppe"] == s["gruppe"] and bi not in benutzt]
            if len(kand) == 1:
                zuordnung[si] = kand[0]
                benutzt.add(kand[0])
    offene_s = [si for si, s in enumerate(skelette) if si not in zuordnung and any(v > 0 for _, _, v in s["pts"])]
    offene_b = [bi for bi in range(len(kuh_boxen)) if bi not in benutzt]
    werte = {(si, bi): bewertung(skelette[si], kuh_boxen[bi]) for si in offene_s for bi in offene_b}
    if offene_s and offene_b:
        n = len(offene_s) + len(offene_b)
        kosten = [[0.0] * n for _ in range(n)]
        for r, si in enumerate(offene_s):
            for c, bi in enumerate(offene_b):
                w = werte[(si, bi)]
                kosten[r][c] = -w if w is not None else 1e6
        for r, c in enumerate(ungarisch(kosten)):
            if r < len(offene_s) and c < len(offene_b):
                si, bi = offene_s[r], offene_b[c]
                if werte[(si, bi)] is not None:
                    zuordnung[si] = bi
    for si in offene_s:
        if sum(1 for bi in offene_b if enthaelt_mit_rand(skelette[si], kuh_boxen[bi])) >= 2:
            mehrdeutig.append(si)
        if si not in zuordnung:
            if si not in mehrdeutig:
                ohne_box.append(si)
            continue
        eigen = werte[(si, zuordnung[si])]
        if si not in mehrdeutig and any(w is not None and bi != zuordnung[si] and w >= eigen - MEHRDEUTIG_ABSTAND
                                        for (s2, bi), w in werte.items() if s2 == si):
            knapp.append(si)
    return zuordnung, mehrdeutig, ohne_box, knapp


# ----------------------------------------------------------------------------- YOLO-Zeilen
def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def yolo_zeilen(eintrag, zaehler, warnungen, name):
    """Erzeugt die Label-Zeilen eines Bildes. Gibt (zeilen, fehler[]) zurück."""
    w, h = eintrag["w"], eintrag["h"]
    zeilen, fehler = [], []
    kuh_boxen = [b for b in eintrag["boxen"] if b["klasse"] == "kuh"]
    andere = [b for b in eintrag["boxen"] if b["klasse"] != "kuh"]
    zuordnung, mehrdeutig, ohne_box, knapp = paare_box_skelett(kuh_boxen, eintrag["skelette"])
    for si in knapp:
        warnungen["knappe_paarung"].append(f"{name}: Skelett {si + 1}")
    for si in mehrdeutig:
        fehler.append(f"{name}: Skelett {si + 1} liegt in mehreren Kuh-Boxen — in CVAT Box und Skelett gruppieren (G)")
    for si in ohne_box:
        fehler.append(f"{name}: Skelett {si + 1} ohne passende Kuh-Box")
    box_zu_skelett = {bi: si for si, bi in zuordnung.items()}

    def box_norm(xyxy):
        x1, y1, x2, y2 = xyxy
        x1, x2 = _clip(x1, 0, w), _clip(x2, 0, w)
        y1, y2 = _clip(y1, 0, h), _clip(y2, 0, h)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None
        return ((x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h)

    for bi, b in enumerate(kuh_boxen):
        bn = box_norm(b["xyxy"])
        if bn is None:
            warnungen["box_zu_klein"].append(name)
            continue
        kp = []
        if bi in box_zu_skelett:
            zaehler["kuh_mit_skelett"] += 1
            for k, (x, y, v) in zip(KEYPOINTS, eintrag["skelette"][box_zu_skelett[bi]]["pts"]):
                if v > 0 and not (0 <= x <= w and 0 <= y <= h):
                    warnungen["punkt_ausserhalb_bild"].append(f"{name}: {k}")
                    v = 0
                if v == 0:
                    kp += [0.0, 0.0, 0]
                else:
                    kp += [x / w, y / h, v]
                zaehler[f"kp_{k}_v{v}"] += 1
        else:
            zaehler["kuh_ohne_skelett"] += 1
            if b.get("quelle") in VORSCHLAG_QUELLEN:
                zaehler["unbestaetigter_vorschlag"] += 1
                warnungen["vorschlag_ohne_skelett"].append(name)
            kp = [0.0, 0.0, 0] * 3
        zaehler["inst_kuh"] += 1
        zeilen.append(_zeile(0, bn, kp))
    for b in andere:
        bn = box_norm(b["xyxy"])
        if bn is None:
            warnungen["box_zu_klein"].append(name)
            continue
        zaehler[f"inst_{b['klasse']}"] += 1
        zeilen.append(_zeile(KLASSEN.index(b["klasse"]), bn, [0.0, 0.0, 0] * 3))
    return zeilen, fehler


def _zeile(cls, bn, kp):
    teile = [str(cls)] + [f"{v:.6f}" for v in bn]
    for i in range(0, 9, 3):
        x, y, v = kp[i:i + 3]
        teile += [f"{x:.6f}", f"{y:.6f}", str(int(v))]
    return " ".join(teile)


# ----------------------------------------------------------------------------- Split
def lies_manifest(pfad):
    m = {}
    with open(pfad, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m[r["datei"]] = r
    return m


def puffer_ausschluss(train_namen, val_namen, puffer_min):
    if puffer_min <= 0 or not val_namen:
        return set()
    val_t = sorted(t for t in (zeitstempel(n) for n in val_namen) if t)
    raus = set()
    for n in train_namen:
        t = zeitstempel(n)
        if t is None:
            continue
        i = bisect.bisect_left(val_t, t)
        nah = [val_t[j] for j in (i - 1, i) if 0 <= j < len(val_t)]
        if any(abs((t - v).total_seconds()) < puffer_min * 60 for v in nah):
            raus.add(n)
    return raus


# ----------------------------------------------------------------------------- Bilder
def kopiere_bild(quelle, ziel, max_seite, w=0, h=0):
    import cv2
    if max_seite <= 0:
        shutil.copyfile(quelle, ziel)
        return
    # JPEG direkt in halber Auflösung dekodieren, wenn das Ziel ohnehin ≤ halb so groß ist (2–3x schneller)
    flags = cv2.IMREAD_REDUCED_COLOR_2 if max(w, h) >= 2 * max_seite and quelle.lower().endswith((".jpg", ".jpeg")) else cv2.IMREAD_COLOR
    img = cv2.imread(quelle, flags)
    if img is None:
        raise KonverterFehler(f"Bild nicht lesbar: {quelle}")
    hh, ww = img.shape[:2]
    s = max_seite / max(hh, ww)
    if s < 1:
        img = cv2.resize(img, (int(round(ww * s)), int(round(hh * s))), interpolation=cv2.INTER_AREA)
    if not cv2.imwrite(ziel, img, [cv2.IMWRITE_JPEG_QUALITY, 92]):
        raise KonverterFehler(f"Bild nicht schreibbar: {ziel}")


# ----------------------------------------------------------------------------- Hauptablauf
def konvertiere(xml_pfade, bilder_ordner, manifest_pfad, ausgabe, max_seite=1280, puffer_min=60,
                erzwingen=False, box_label="kuh", pose_label="kuh_pose", bilder_kopieren=True, zip_erstellen=False,
                beilagen=None):
    start = time.time()
    if os.path.exists(ausgabe) and os.listdir(ausgabe):
        raise KonverterFehler(f"Ausgabeordner {ausgabe} ist nicht leer — neuen Ordnernamen wählen (Versionen nie überschreiben).")
    zpfad = ausgabe.rstrip("/") + ".zip"
    if zip_erstellen and os.path.exists(zpfad):
        raise KonverterFehler(f"{zpfad} existiert schon — neuen Namen wählen.")
    beilagen = STANDARD_BEILAGEN if beilagen is None else beilagen
    bilder, aufgaben, warnungen = parse_cvat(lies_xml_quellen(xml_pfade), box_label, pose_label)
    manifest = lies_manifest(manifest_pfad)
    fehler = []

    # Geprüft-Markierung: Labeler-Exporte und Aufgaben mit mindestens einem "geprueft"-Tag -> nur geprüfte Bilder
    mit_markierung = {bilder[n]["aufgabe"] for n in bilder if GEPRUEFT_TAG in bilder[n]["tags"]}
    mit_markierung |= {a for a, st in aufgaben.items() if st.get("stall_labeler")}
    for a in sorted(mit_markierung):
        if not any(bilder[n]["aufgabe"] == a and GEPRUEFT_TAG in bilder[n]["tags"] for n in bilder):
            fehler.append(f"{a}: Labeler-Export ohne ein einziges geprüftes Bild — im Stall-Labeler jedes "
                          "angesehene Bild mit Enter abhaken, dann neu exportieren.")

    def wird_genutzt(name):
        e = bilder[name]
        return e["aufgabe"] not in mit_markierung or GEPRUEFT_TAG in e["tags"]

    # Vollständigkeit je Aufgabe (nur genutzte Bilder): Kuh-Boxen, aber kein Skelett -> vermutlich nur Vorannotation
    genutzt_stat = defaultdict(Counter)
    for n, e in bilder.items():
        if wird_genutzt(n):
            genutzt_stat[e["aufgabe"]]["box_kuh"] += sum(1 for b in e["boxen"] if b["klasse"] == "kuh")
            genutzt_stat[e["aufgabe"]]["skelett"] += len(e["skelette"])
    for a, st in genutzt_stat.items():
        if st["box_kuh"] > 0 and st["skelett"] == 0:
            fehler.append(f"{a}: {st['box_kuh']} Kuh-Boxen, aber kein Skelett — Aufgabe noch nicht gelabelt? "
                          "Nur fertig gelabelte Aufgaben exportieren.")

    def tag_von(name):
        return (manifest.get(name) or {}).get("stalltag") or stalltag(name)

    auswahl = {"train": [], "val": []}
    uebersprungen = Counter()
    for name in sorted(bilder):
        if not wird_genutzt(name):
            uebersprungen["ungeprueft"] += 1
            continue
        r = manifest.get(name)
        if r is None:
            uebersprungen["nicht_im_manifest"] += 1
            warnungen["nicht_im_manifest"].append(name)
            continue
        if float(r.get("defekt_anteil") or 0) > SCHWELLE_DEFEKT:
            uebersprungen["defekt"] += 1
            continue
        if r["split"] not in auswahl:
            raise KonverterFehler(f"{name}: unbekannter split '{r['split']}' im Manifest")
        auswahl[r["split"]].append(name)

    raus = puffer_ausschluss(auswahl["train"], auswahl["val"], puffer_min)
    if raus:
        uebersprungen["puffer_zu_val"] += len(raus)
        auswahl["train"] = [n for n in auswahl["train"] if n not in raus]

    # Leck-Prüfung nach Stalltag (eine Nacht nie in beiden Splits)
    gemeinsam = set(auswahl["train"]) & set(auswahl["val"])
    tage = {s: sorted({t for t in (tag_von(n) for n in auswahl[s]) if t}) for s in auswahl}
    if gemeinsam:
        fehler.append(f"Datenleck: {len(gemeinsam)} Dateien in train und val")
    if set(tage["train"]) & set(tage["val"]):
        fehler.append(f"Datenleck: Stalltage in train und val: {sorted(set(tage['train']) & set(tage['val']))}")

    # Beilagen und Quellbilder vorab prüfen (nichts halb schreiben)
    fehlende_beilagen = [b for b in beilagen if not os.path.exists(b)]
    if fehlende_beilagen:
        raise KonverterFehler(f"Beilage fehlt: {fehlende_beilagen}")
    if bilder_kopieren:
        fehlend = [n for s in auswahl for n in auswahl[s] if not os.path.isfile(os.path.join(bilder_ordner, n))]
        if fehlend:
            raise KonverterFehler(f"{len(fehlend)} Quellbilder fehlen in {bilder_ordner}, z. B. {fehlend[:3]}")

    zaehler = {s: Counter() for s in auswahl}
    label_daten = {s: {} for s in auswahl}
    for s in auswahl:
        for name in auswahl[s]:
            zeilen, f = yolo_zeilen(bilder[name], zaehler[s], warnungen, name)
            fehler += f
            label_daten[s][name] = zeilen
            zaehler[s]["bilder"] += 1
            zaehler[s]["bilder_leer"] += 0 if zeilen else 1
            licht = manifest[name].get("licht", "?")
            zaehler[s][f"bilder_{licht}"] += 1
            zaehler[s][f"kuh_{licht}"] += sum(1 for z in zeilen if z.startswith("0 "))
            ans = manifest[name].get("ansicht_grob")
            if ans:
                zaehler[s][f"bilder_ansicht_{ans}"] += 1

    bericht = {
        "erstellt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "aufgaben": aufgaben,
        "aufgaben_mit_geprueft_markierung": sorted(mit_markierung),
        "uebersprungen": dict(uebersprungen),
        "splits": {s: dict(sorted(zaehler[s].items())) for s in zaehler},
        "stalltage": tage,
        "fehler": fehler[:MAX_BEISPIELE],
        "fehler_anzahl": len(fehler),
        "warnungen": {k: {"anzahl": len(v), "beispiele": v[:MAX_BEISPIELE]} for k, v in warnungen.items()},
        "parameter": {"max_seite": max_seite, "puffer_min": puffer_min, "box_label": box_label,
                      "pose_label": pose_label, "erzwungen": bool(erzwingen and fehler)},
    }
    if fehler and not erzwingen:
        raise KonverterFehler("Konvertierung abgebrochen:\n  - " + "\n  - ".join(fehler[:20]) +
                              (f"\n  ... und {len(fehler) - 20} weitere" if len(fehler) > 20 else ""))
    if not auswahl["train"] or not auswahl["val"]:
        raise KonverterFehler(f"Leerer Split (train {len(auswahl['train'])}, val {len(auswahl['val'])}) — "
                              "Training/Validierung nicht möglich.")

    try:
        for s in auswahl:
            os.makedirs(os.path.join(ausgabe, "images", s), exist_ok=True)
            os.makedirs(os.path.join(ausgabe, "labels", s), exist_ok=True)
            for name in auswahl[s]:
                stamm = os.path.splitext(name)[0]
                with open(os.path.join(ausgabe, "labels", s, stamm + ".txt"), "w", encoding="utf-8") as fh:
                    fh.write("\n".join(label_daten[s][name]) + ("\n" if label_daten[s][name] else ""))
                if bilder_kopieren:
                    kopiere_bild(os.path.join(bilder_ordner, name), os.path.join(ausgabe, "images", s, stamm + ".jpg"),
                                 max_seite, bilder[name]["w"], bilder[name]["h"])
    except OSError as e:
        raise KonverterFehler(f"Schreiben/Kopieren fehlgeschlagen: {e}") from e

    with open(os.path.join(ausgabe, "data.yaml"), "w", encoding="utf-8") as fh:
        fh.write(f"# Stallwache YOLO-Pose-Datensatz — erzeugt {bericht['erstellt']} von cvat_zu_yolo_pose.py\n")
        fh.write("# 'path' fehlt absichtlich: Ultralytics nimmt dann den Ordner dieser Datei.\n")
        fh.write("train: images/train\nval: images/val\n")
        fh.write(f"kpt_shape: [{len(KEYPOINTS)}, 3]\nflip_idx: {FLIP_IDX}\n")
        fh.write("names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(KLASSEN)))
        fh.write(f"# Keypoints (Reihenfolge): {', '.join(KEYPOINTS)}\n")
    with open(os.path.join(ausgabe, "konvertierung_bericht.json"), "w", encoding="utf-8") as fh:
        json.dump(bericht, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(ausgabe, "konvertierung_bericht.md"), "w", encoding="utf-8") as fh:
        fh.write(bericht_md(bericht))
    for b in beilagen:
        os.makedirs(os.path.join(ausgabe, "werkzeuge"), exist_ok=True)
        shutil.copyfile(b, os.path.join(ausgabe, "werkzeuge", os.path.basename(b)))
    if zip_erstellen:
        with zipfile.ZipFile(zpfad, "x", zipfile.ZIP_STORED) as zf:
            for wurzel, _, dateien in os.walk(ausgabe):
                for d in sorted(dateien):
                    voll = os.path.join(wurzel, d)
                    zf.write(voll, os.path.relpath(voll, os.path.dirname(ausgabe.rstrip("/"))))
        bericht["zip"] = zpfad
    bericht["dauer_s"] = round(time.time() - start, 1)
    return bericht


def bericht_md(b):
    z = ["# Konvertierungsbericht", "", f"Erstellt: {b['erstellt']}", ""]
    if b.get("stalltage"):
        for s in ("train", "val"):
            t = b["stalltage"].get(s, [])
            z.append(f"- Stalltage {s}: {len(t)} ({', '.join(t[:3])}{' …' if len(t) > 3 else ''})")
        z.append("")
    z += ["| Kennzahl | train | val |", "|---|---:|---:|"]
    schluessel = sorted(set(b["splits"]["train"]) | set(b["splits"]["val"]))
    for k in schluessel:
        z.append(f"| {k} | {b['splits']['train'].get(k, 0)} | {b['splits']['val'].get(k, 0)} |")
    z += ["", "## Übersprungen", ""] + ([f"- {k}: {v}" for k, v in b["uebersprungen"].items()] or ["- keine"])
    z += ["", "## Aufgaben", ""] + [f"- {a}: {st.get('bilder', 0)} Bilder, {st.get('box_kuh', 0)} Kuh-Boxen, "
                                    f"{st.get('skelett', 0)} Skelette" for a, st in b.get("aufgaben", {}).items()]
    z += ["", "## Warnungen", ""]
    for k, v in b["warnungen"].items():
        z.append(f"- **{k}**: {v['anzahl']} (z. B. {', '.join(v['beispiele'][:5])})")
    if b["fehler_anzahl"]:
        z += ["", f"## Fehler ({b['fehler_anzahl']}) — nur mit --erzwingen übernommen", ""] + [f"- {f}" for f in b["fehler"]]
    return "\n".join(z) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml", nargs="+", required=True, help="CVAT-Exporte (annotations.xml oder Export-ZIP), 'CVAT for images 1.1'")
    ap.add_argument("--bilder", required=True, help="Ordner mit den Originalbildern")
    ap.add_argument("--manifest", required=True, help="manifest.csv aus _cvat_v1 (Split, Stalltag, Licht, Defekt)")
    ap.add_argument("--ausgabe", required=True, help="neuer, leerer Zielordner (z. B. datensatz_v1)")
    ap.add_argument("--max-seite", type=int, default=1280, help="längste Bildseite im Datensatz (0 = Original kopieren)")
    ap.add_argument("--puffer-min", type=int, default=60)
    ap.add_argument("--box-label", default="kuh")
    ap.add_argument("--pose-label", default="kuh_pose")
    ap.add_argument("--zip", action="store_true", help="zusätzlich <ausgabe>.zip für Colab erzeugen")
    ap.add_argument("--erzwingen", action="store_true", help="trotz Fehlern schreiben (nur zum Testen!)")
    ap.add_argument("--beilage", nargs="*", default=None,
                    help="Dateien für <ausgabe>/werkzeuge/ (Standard: abnahme_gates.py, bildqualitaet.py aus diesem Ordner)")
    a = ap.parse_args(argv)
    try:
        b = konvertiere(a.xml, a.bilder, a.manifest, a.ausgabe, a.max_seite, a.puffer_min, a.erzwingen,
                        a.box_label, a.pose_label, zip_erstellen=a.zip, beilagen=a.beilage)
    except KonverterFehler as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 2
    print(bericht_md(b))
    print(f"Fertig in {b['dauer_s']} s -> {a.ausgabe}" + (f" (+ {b['zip']})" if b.get("zip") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
