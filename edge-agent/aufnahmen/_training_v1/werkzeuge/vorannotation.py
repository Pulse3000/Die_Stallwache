#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vorannotation für CVAT: schlägt Rechtecke der Klasse `kuh` vor.

Grundsätze
- Läuft lokal auf dem Hof-Rechner (Prinzip 2: keine Bilder verlassen den Hof).
- Detektor: COCO-vortrainiertes YOLOv8 als ONNX-Datei, ausgeführt mit ONNX Runtime (CPU).
  Auf dem AMD A6-3650 (kein SSE4.1/AVX) scheitert PyTorch-Conv mit Standardeinstellung
  ("could not create a primitive"); ONNX Runtime läuft dort (gemessen 2026-11-01).
- Übernommen werden nur Tierklassen (cow, horse, sheep, dog, bear, ...), weil Kühe im
  IR-Bild vom COCO-Modell oft als anderes Tier erkannt werden. Personen werden nie
  übernommen; Tier-Boxen, die mit einer stärkeren Personen-Box zusammenfallen, entfallen.
- Keypoints werden bewusst NICHT vorgeschlagen: geratene Punkte (v. a. tail_tip) würden
  beim Korrigieren stehen bleiben (Ankereffekt) und die Regel "nie raten" unterlaufen.
- Fortsetzbar: Rohergebnisse je Bild in <arbeitsordner>/erkennungen.jsonl (Score ≥ 0.10 gespeichert).
  XML-Dateien werden für jede vollständige Aufgabe bei jedem Lauf neu geschrieben — eine andere
  Schwelle (--conf) oder eine neue Aufteilung der Aufgaben braucht keine Neuberechnung.

Ausgabe
  <ausgabe>/<task>_vorannotation.xml  — Format "CVAT for images 1.1", nur Rechtecke `kuh`.
  Import in CVAT: Task öffnen -> Actions -> Upload annotations -> Format "CVAT 1.1".

Beispiele
  python3 vorannotation.py --onnx yolov8s.onnx --tasks ../_cvat_v1 --bilder .. \
      --arbeitsordner ~/work/vorannotation --ausgabe ../_cvat_v1/vorannotation --max-sekunden 160
  python3 vorannotation.py ... --probe 12 --probe-bild probe.jpg   (Sichtprüfung, schreibt nichts sonst)
"""
import argparse
import json
import os
import random
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

import cv2
import numpy as np

# COCO-Klassenindizes (YOLOv8-COCO-Export, 80 Klassen)
COCO_PERSON = 0
COCO_TIERE = {16: "dog", 17: "horse", 18: "sheep", 19: "cow", 20: "elephant",
              21: "bear", 22: "zebra", 23: "giraffe"}
ROH_MIN_SCORE = 0.10      # so viel wird im Cache gespeichert
PERSON_MIN_SCORE = 0.40   # Personen-Boxen ab diesem Score unterdrücken Tier-Boxen
PERSON_IOU = 0.60


def lade_tasks(task_ordner):
    """Liest die Task-Zuordnung aus den CVAT-Upload-ZIPs (Dateiname -> Task)."""
    tasks = {}
    for name in sorted(os.listdir(task_ordner)):
        if name.endswith(".zip") and not name.endswith(".part"):
            with zipfile.ZipFile(os.path.join(task_ordner, name)) as zf:
                tasks[name[:-4]] = sorted(n for n in zf.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png")))
    if not tasks:
        sys.exit(f"Keine Task-ZIPs in {task_ordner} gefunden.")
    return tasks


def letterbox(img, groesse):
    h, w = img.shape[:2]
    r = min(groesse / h, groesse / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    oben, links = (groesse - nh) // 2, (groesse - nw) // 2
    leinwand = np.full((groesse, groesse, 3), 114, np.uint8)
    leinwand[oben:oben + nh, links:links + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x = leinwand[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(x), r, links, oben


def iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    fa = (a[2] - a[0]) * (a[3] - a[1])
    fb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (fa + fb - inter + 1e-9)


def nms(boxen, scores, schwelle_iou):
    if not boxen:
        return []
    xywh = [[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])] for b in boxen]
    idx = cv2.dnn.NMSBoxes(xywh, [float(s) for s in scores], 0.0, schwelle_iou)
    return [int(i) for i in np.array(idx).reshape(-1)]


def erkenne(sess, eingang, img, groesse, schwelle_iou):
    """Gibt Tier-Boxen [x1, y1, x2, y2, score, coco_klasse] in Originalpixeln zurück."""
    h, w = img.shape[:2]
    x, r, links, oben = letterbox(img, groesse)
    aus = sess.run(None, {eingang: x})[0][0]          # (84, N): cx, cy, w, h, 80 Klassen-Scores
    if aus.shape[0] != 84:
        raise ValueError(f"Unerwartete Modellausgabe {aus.shape} — erwartet wird ein COCO-Detektionsmodell (84 x N).")
    roh = aus[:4].T
    scores = aus[4:].T
    tier_idx = np.array(sorted(COCO_TIERE))

    def zu_pixeln(sel):
        cx, cy, bw, bh = roh[sel, 0], roh[sel, 1], roh[sel, 2], roh[sel, 3]
        x1 = np.clip((cx - bw / 2 - links) / r, 0, w)
        y1 = np.clip((cy - bh / 2 - oben) / r, 0, h)
        x2 = np.clip((cx + bw / 2 - links) / r, 0, w)
        y2 = np.clip((cy + bh / 2 - oben) / r, 0, h)
        return np.stack([x1, y1, x2, y2], 1)

    # Tiere
    t_scores = scores[:, tier_idx]
    t_best = t_scores.argmax(1)
    t_score = t_scores[np.arange(len(t_scores)), t_best]
    sel = np.where(t_score >= ROH_MIN_SCORE)[0]
    tiere = []
    if len(sel):
        bx = zu_pixeln(sel)
        keep = nms(bx.tolist(), t_score[sel].tolist(), schwelle_iou)
        for k in keep:
            x1, y1, x2, y2 = bx[k]
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            tiere.append([round(float(x1), 1), round(float(y1), 1), round(float(x2), 1), round(float(y2), 1),
                          round(float(t_score[sel][k]), 4), int(tier_idx[t_best[sel][k]])])
    # Personen (nur zur Unterdrückung)
    p_score = scores[:, COCO_PERSON]
    psel = np.where(p_score >= PERSON_MIN_SCORE)[0]
    personen = []
    if len(psel):
        pbx = zu_pixeln(psel)
        for k in nms(pbx.tolist(), p_score[psel].tolist(), schwelle_iou):
            personen.append((pbx[k].tolist(), float(p_score[psel][k])))
    ergebnis = []
    for t in tiere:
        if any(iou(t[:4], pb) > PERSON_IOU and ps > t[4] for pb, ps in personen):
            continue
        ergebnis.append(t)
    return ergebnis


def schreibe_xml(task, eintraege, pfad, schwelle, modell=""):
    root = ET.Element("annotations")
    root.append(ET.Comment(f" Vorannotation Stallwache: {modell}, Score >= {schwelle:.2f}, nur Vorschläge, "
                           f"{time.strftime('%Y-%m-%d %H:%M')} "))
    ET.SubElement(root, "version").text = "1.1"
    meta = ET.SubElement(root, "meta")
    t = ET.SubElement(meta, "task")
    ET.SubElement(t, "name").text = task
    ET.SubElement(t, "size").text = str(len(eintraege))
    ET.SubElement(t, "mode").text = "annotation"
    ET.SubElement(meta, "dumped").text = time.strftime("%Y-%m-%d %H:%M:%S")
    anzahl = 0
    for i, e in enumerate(sorted(eintraege, key=lambda e: e["f"])):
        im = ET.SubElement(root, "image", id=str(i), name=e["f"], width=str(e["w"]), height=str(e["h"]))
        for x1, y1, x2, y2, s, _ in e["boxen"]:
            if s < schwelle:
                continue
            ET.SubElement(im, "box", label="kuh", source="auto", occluded="0",
                          xtl=f"{x1:.2f}", ytl=f"{y1:.2f}", xbr=f"{x2:.2f}", ybr=f"{y2:.2f}", z_order="0")
            anzahl += 1
    tmp = pfad + ".part"
    ET.ElementTree(root).write(tmp, encoding="utf-8", xml_declaration=True)
    os.replace(tmp, pfad)
    return anzahl


def lade_cache(pfad, eintraege=None):
    eintraege = {} if eintraege is None else eintraege
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as fh:
            for zeile in fh:
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    e = json.loads(zeile)
                except json.JSONDecodeError:
                    continue   # abgebrochene letzte Zeile
                eintraege[e["f"]] = e
    return eintraege


def probe(args, sess, eingang, tasks):
    alle = sorted({f for fl in tasks.values() for f in fl})
    random.Random(args.seed).shuffle(alle)
    auswahl = alle[:args.probe]
    kacheln = []
    for f in auswahl:
        img = cv2.imread(os.path.join(args.bilder, f))
        t0 = time.time()
        boxen = erkenne(sess, eingang, img, args.imgsz, args.iou)
        dt = time.time() - t0
        for x1, y1, x2, y2, s, c in boxen:
            if s < args.conf:
                farbe = (0, 165, 255)   # unter Schwelle: orange (nur Info)
            else:
                farbe = (0, 255, 0)
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), farbe, 6)
            cv2.putText(img, f"{COCO_TIERE[c]} {s:.2f}", (int(x1) + 8, int(y1) + 60), cv2.FONT_HERSHEY_SIMPLEX, 2.0, farbe, 5)
        cv2.putText(img, f, (20, img.shape[0] - 30), cv2.FONT_HERSHEY_SIMPLEX, 2.2, (255, 255, 255), 6)
        kacheln.append(cv2.resize(img, (640, 360), interpolation=cv2.INTER_AREA))
        print(f"{f}: {sum(1 for b in boxen if b[4] >= args.conf)} Boxen ≥ {args.conf} ({len(boxen)} roh), {dt:.2f}s", flush=True)
    spalten = 4
    while len(kacheln) % spalten:
        kacheln.append(np.zeros_like(kacheln[0]))
    zeilen = [np.hstack(kacheln[i:i + spalten]) for i in range(0, len(kacheln), spalten)]
    cv2.imwrite(args.probe_bild, np.vstack(zeilen), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("Probe-Bild:", args.probe_bild)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--onnx", required=True, help="COCO-Detektor als ONNX (z. B. yolov8s.onnx, statisch 640)")
    ap.add_argument("--tasks", required=True, help="Ordner mit den CVAT-Upload-ZIPs (train_01.zip ...)")
    ap.add_argument("--bilder", required=True, help="Ordner mit den Originalbildern (aufnahmen)")
    ap.add_argument("--arbeitsordner", default=os.path.expanduser("~/work/vorannotation"))
    ap.add_argument("--ausgabe", help="Zielordner für <task>_vorannotation.xml")
    ap.add_argument("--conf", type=float, default=0.20, help="Mindest-Score für die XML-Datei (Standard 0.20)")
    ap.add_argument("--iou", type=float, default=0.50)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--max-sekunden", type=float, default=0, help="nach dieser Zeit sauber anhalten (0 = unbegrenzt)")
    ap.add_argument("--nur-tasks", nargs="*", help="nur diese Tasks bearbeiten (z. B. train_01 val_01)")
    ap.add_argument("--probe", type=int, default=0, help="Sichtprüfung: N zufällige Bilder als Kachelbild")
    ap.add_argument("--probe-bild", default="probe.jpg")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = args.threads
    sess = ort.InferenceSession(args.onnx, so, providers=["CPUExecutionProvider"])
    eingang = sess.get_inputs()[0].name
    tasks = lade_tasks(args.tasks)

    if args.probe:
        probe(args, sess, eingang, tasks)
        return

    if not args.ausgabe:
        sys.exit("--ausgabe fehlt")
    os.makedirs(args.arbeitsordner, exist_ok=True)
    os.makedirs(args.ausgabe, exist_ok=True)
    cache_pfad = os.path.join(args.arbeitsordner, "erkennungen.jsonl")
    fertig = lade_cache(cache_pfad)
    # Übernahme älterer Zwischenstände (<task>.jsonl aus früheren Versionen dieses Skripts)
    alt = {}
    for n in sorted(os.listdir(args.arbeitsordner)):
        if n.endswith(".jsonl") and n != "erkennungen.jsonl":
            lade_cache(os.path.join(args.arbeitsordner, n), alt)
    neu = [e for f, e in alt.items() if f not in fertig]
    if neu:
        with open(cache_pfad, "a", encoding="utf-8") as fh:
            for e in neu:
                fh.write(json.dumps(e) + "\n")
                fertig[e["f"]] = e
        print(f"{len(neu)} Ergebnisse aus älteren Zwischenständen übernommen", flush=True)
    start = time.time()
    reihenfolge = args.nur_tasks or list(tasks)
    angehalten = False
    with open(cache_pfad, "a", encoding="utf-8") as fh:
        for task in reihenfolge:
            dateien = tasks[task]
            for f in dateien:
                if f in fertig:
                    continue
                if args.max_sekunden and time.time() - start > args.max_sekunden:
                    angehalten = True
                    break
                img = cv2.imread(os.path.join(args.bilder, f))
                if img is None:
                    print(f"WARNUNG: {f} nicht lesbar — übersprungen", flush=True)
                    e = {"f": f, "w": 0, "h": 0, "boxen": [], "fehler": "unlesbar"}
                else:
                    e = {"f": f, "w": img.shape[1], "h": img.shape[0],
                         "boxen": erkenne(sess, eingang, img, args.imgsz, args.iou)}
                fh.write(json.dumps(e) + "\n")
                fh.flush()
                fertig[f] = e
            if angehalten:
                print(f"ZEIT: angehalten in {task} ({sum(1 for f in dateien if f in fertig)}/{len(dateien)})", flush=True)
                break
    for task in reihenfolge:
        dateien = tasks[task]
        if not all(f in fertig for f in dateien):
            continue
        gueltig = [fertig[f] for f in dateien if fertig[f].get("w")]
        xml_pfad = os.path.join(args.ausgabe, f"{task}_vorannotation.xml")
        n = schreibe_xml(task, gueltig, xml_pfad, args.conf, os.path.basename(args.onnx))
        mit = sum(1 for e in gueltig if any(b[4] >= args.conf for b in e["boxen"]))
        print(f"FERTIG {task}: {len(gueltig)} Bilder, {mit} mit Kuh-Vorschlag, {n} Boxen -> {xml_pfad}", flush=True)
    if angehalten:
        return
    print("ALLE TASKS FERTIG", flush=True)


if __name__ == "__main__":
    main()
