"""CPU-Kompatibilitaets-Shim fuer aeltere x86-CPUs ohne AVX (z. B. AMD A6-3650).

Problem: Der kompilierte torchvision-NMS-Operator fuehrt dort eine illegale
Instruktion aus (SIGILL). Ultralytics ruft torchvision.ops.nms erst zur
Laufzeit auf, daher kann er durch eine reine NumPy-Variante ersetzt werden
(identisches klassisches IoU-NMS).

Nutzung: vor dem ersten Modell-Aufruf  `import cpu_compat; cpu_compat.anwenden()`.
Auf modernen CPUs ist der Shim harmlos, nur minimal langsamer.
"""
from __future__ import annotations


def _numpy_nms(boxes, scores, iou_threshold=0.45):
    import numpy as np
    import torch

    def _np(x):
        return x.detach().cpu().numpy().astype(np.float32) if isinstance(x, torch.Tensor) \
            else np.asarray(x, dtype=np.float32)

    b, s = _np(boxes), _np(scores)
    if b.size == 0:
        return torch.empty((0,), dtype=torch.long)
    x1, y1, x2, y2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    flaeche = np.maximum(x2 - x1, 0) * np.maximum(y2 - y1, 0)
    reihenfolge = s.argsort()[::-1]
    behalten = []
    while reihenfolge.size > 0:
        i = int(reihenfolge[0])
        behalten.append(i)
        if reihenfolge.size == 1:
            break
        rest = reihenfolge[1:]
        w = np.maximum(np.minimum(x2[i], x2[rest]) - np.maximum(x1[i], x1[rest]), 0)
        h = np.maximum(np.minimum(y2[i], y2[rest]) - np.maximum(y1[i], y1[rest]), 0)
        inter = w * h
        union = flaeche[i] + flaeche[rest] - inter
        iou = np.where(union > 0, inter / union, 0.0)
        reihenfolge = rest[iou <= iou_threshold]
    return torch.tensor(behalten, dtype=torch.long)


def anwenden() -> None:
    try:
        import torchvision
        torchvision.ops.nms = _numpy_nms
    except ImportError:
        pass  # kein torchvision -> nichts zu ersetzen (z. B. reiner Silent Mode)
