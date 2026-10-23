"""Analyse-Modus auf alter CPU ohne AVX (z. B. AMD A6-3650 auf stallwache-lela).

Gerätewissen aus kuhwatch, dort im Dauerbetrieb erprobt
(docs/ein-edge-agent-spezifikation.md, U1):

* oneDNN (mkldnn) in torch aus: dessen JIT setzt AVX voraus.
* ``torchvision.ops.nms`` durch eine NumPy-NMS ersetzen. Der kompilierte
  Operator fuehrt auf der A6-3650 eine illegale Instruktion aus (SIGILL).
  Ultralytics ruft ihn erst zur Laufzeit ueber das Modul auf, deshalb
  genuegt das Ersetzen des Attributs. Ergebnis wie klassisches IoU-NMS.

Ein ONNX-Modell (``modell.pfad`` auf ``.onnx``) laeuft ueber onnxruntime.
Der Silent Mode laedt kein torch und braucht nichts hiervon.
"""

from __future__ import annotations

from pathlib import Path


def hat_avx(cpuinfo: str | None = None) -> bool | None:
    """True/False aus den CPU-Flags; None, wenn unbekannt (kein Linux)."""
    if cpuinfo is None:
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    for zeile in cpuinfo.splitlines():
        if zeile.startswith("flags") and ":" in zeile:
            return "avx" in zeile.split(":", 1)[1].split()
    return None


def alte_cpu_aktiv(einstellung, cpuinfo: str | None = None) -> bool:
    """modell.alte_cpu: true/false erzwingen; auto (Default) = CPU ohne AVX."""
    wert = str(einstellung if einstellung is not None else "auto").strip().lower()
    if wert in ("true", "ja", "1"):
        return True
    if wert in ("false", "nein", "0"):
        return False
    return hat_avx(cpuinfo) is False


def numpy_nms(boxes, scores, iou_threshold: float = 0.45):
    """IoU-NMS in NumPy mit der Signatur von torchvision.ops.nms."""
    import numpy as np
    import torch

    if isinstance(boxes, torch.Tensor):
        boxes = boxes.detach().cpu().numpy()
    if isinstance(scores, torch.Tensor):
        scores = scores.detach().cpu().numpy()
    return torch.tensor(nms_indizes(np.asarray(boxes, dtype=np.float32),
                                    np.asarray(scores, dtype=np.float32),
                                    iou_threshold), dtype=torch.long)


def nms_indizes(boxes, scores, iou_threshold: float) -> list[int]:
    """Kern der NMS auf NumPy-Arrays (ohne torch, fuer Tests)."""
    import numpy as np

    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    flaechen = np.maximum(x2 - x1, 0) * np.maximum(y2 - y1, 0)
    reihenfolge = scores.argsort()[::-1]
    behalten: list[int] = []
    while reihenfolge.size > 0:
        i = int(reihenfolge[0])
        behalten.append(i)
        rest = reihenfolge[1:]
        if rest.size == 0:
            break
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        schnitt = np.maximum(xx2 - xx1, 0) * np.maximum(yy2 - yy1, 0)
        vereinigung = flaechen[i] + flaechen[rest] - schnitt
        iou = np.where(vereinigung > 0, schnitt / np.where(vereinigung > 0, vereinigung, 1), 0.0)
        reihenfolge = rest[iou <= iou_threshold]
    return behalten


def aktiviere() -> list[str]:
    """Setzt beide Schalter vor dem Laden des Modells; liefert, was gesetzt wurde."""
    erledigt: list[str] = []
    import torch

    if hasattr(torch.backends, "mkldnn"):
        torch.backends.mkldnn.enabled = False
        erledigt.append("oneDNN aus")
    import torchvision

    torchvision.ops.nms = numpy_nms
    erledigt.append("NumPy-NMS")
    return erledigt
