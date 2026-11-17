#!/usr/bin/env python3
"""B21-Abnahme: Konsistenz des Label-Vertrags (CVAT, YAML, Edge-Konfig).

Eine vertauschte Keypoint-Reihenfolge rechnet den Schwanzwinkel still aus
falschen Punkten. Geprueft: CVAT-Schema v2 im Repo (Box kuh, Skelett kuh_pose
mit spine_end, tail_base, tail_tip; amniotic_sac, calf_legs; Tag geprueft),
identische Trainingskopie, Konverter/Gates (Klassen, Keypoints, flip_idx) und
die Edge-Konfig (Indizes 0-2). Pures Python."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hilfe import Pruefer  # noqa: E402

p = Pruefer("Label-Vertrag (B21)")
AGENT = Path(__file__).resolve().parent.parent
REPO = AGENT.parent
TRAINING = AGENT / "aufnahmen" / "_training_v1"
KLASSEN = ["kuh", "amniotic_sac", "calf_legs"]
KEYPOINTS = ["spine_end", "tail_base", "tail_tip"]

schema = json.loads((REPO / "cvat_labels_stallwache_v2.json").read_text(encoding="utf-8"))
typen = {l["name"]: l["type"] for l in schema}
p.check("CVAT v2: kuh ist Box", typen.get("kuh") == "rectangle")
skelett = next((l for l in schema if l["type"] == "skeleton"), None)
p.check("CVAT v2: Skelett heisst kuh_pose", skelett is not None and skelett["name"] == "kuh_pose")
p.check("CVAT v2: Skelettpunkte in Vertragsreihenfolge",
        skelett is not None and [s["name"] for s in skelett["sublabels"]] == KEYPOINTS)
p.check("CVAT v2: Fruchtblase und Kaelberfuesse als Box",
        typen.get("amniotic_sac") == "rectangle" and typen.get("calf_legs") == "rectangle")
p.check("CVAT v2: Tag geprueft vorhanden", typen.get("geprueft") == "tag")
p.check("CVAT v2: Klassenreihenfolge ohne Hilfslabels = YOLO-Klassen",
        [l["name"] for l in schema if l["type"] == "rectangle"] == KLASSEN)
p.check("keine Verhaltensklasse 'kalbt'", "kalbt" not in typen)

kopie = TRAINING / "cvat_labels_stallwache_v2.json"
if kopie.is_file():
    p.check("Trainingskopie identisch mit dem Repo-Schema",
            json.loads(kopie.read_text(encoding="utf-8")) == schema)
else:
    print("HINWEIS: Trainingskopie fehlt (nur am Hof-Rechner)")


def liste(quelle: str, name: str):
    treffer = re.search(rf"^{name} = (\[[^\]]*\])", quelle, re.M)
    return json.loads(treffer.group(1).replace("'", '"')) if treffer else None


konv = TRAINING / "werkzeuge" / "cvat_zu_yolo_pose.py"
if konv.is_file():
    q = konv.read_text(encoding="utf-8")
    p.check("Konverter: Klassen", liste(q, "KLASSEN") == KLASSEN)
    p.check("Konverter: Keypoints", liste(q, "KEYPOINTS") == KEYPOINTS)
    p.check("Konverter: flip_idx [0, 1, 2] (Mittellinie, kein Spiegeltausch)", liste(q, "FLIP_IDX") == [0, 1, 2])
    p.check("Konverter: data.yaml mit kpt_shape aus KEYPOINTS",
            'kpt_shape: [{len(KEYPOINTS)}, 3]' in q)
gates = TRAINING / "werkzeuge" / "abnahme_gates.py"
if gates.is_file():
    p.check("Gates: Klassen", liste(gates.read_text(encoding="utf-8"), "KLASSEN") == KLASSEN)


def block(text: str, name: str) -> dict:
    """Liest modell.<name> (Schluessel: Index) aus der YAML-Konfig ohne PyYAML."""
    m = re.search(rf"^modell:\n(?:.*\n)*?  {name}:\n((?:    \w+: *\d+.*\n)+)", text, re.M)
    return {k: int(v) for k, v in re.findall(r"^    (\w+): *(\d+)", m.group(1), re.M)} if m else {}


for datei in ("config.example.yaml", "config.yaml"):
    pfad = AGENT / datei
    if not pfad.is_file():
        continue
    text = pfad.read_text(encoding="utf-8")
    kl, kp = block(text, "klassen"), block(text, "keypoints")
    p.check(f"{datei}: Klassen-Indizes kuh 0, amniotic_sac 1, calf_legs 2",
            kl == {n: i for i, n in enumerate(KLASSEN)})
    p.check(f"{datei}: Keypoint-Indizes spine_end 0, tail_base 1, tail_tip 2",
            kp == {n: i for i, n in enumerate(KEYPOINTS)})

sys.exit(p.bericht())
