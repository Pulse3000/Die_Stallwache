"""Liest die eingebrannte Sendezeit aus einem Bild (siehe sender.py)."""

import time

B, BITS, BREITE = 16, 40, 1280


def sendezeit_ms(frame) -> int | None:
    """Sendezeit in ms (mod 2^40) aus der obersten Blockzeile, None wenn unlesbar."""
    if frame is None or getattr(frame, "ndim", 0) < 2:
        return None
    grau = frame if frame.ndim == 2 else frame[:, :, 0]
    if grau.shape[1] != BREITE:  # Leser hat skaliert -> auf das Sende-Raster
        import cv2

        grau = cv2.resize(grau, (BREITE, int(grau.shape[0] * BREITE / grau.shape[1])))
    ms = 0
    for i in range(BITS):
        x = 8 + i * (B + 8)
        if grau[8 : B, x + 4 : x + B - 4].mean() > 128:
            ms |= 1 << i
    return ms


def bildalter_s(frame) -> float | None:
    """Alter des Bilds in Sekunden (jetzt - Sendezeit), None wenn unlesbar."""
    ms = sendezeit_ms(frame)
    if ms is None:
        return None
    alter = ((int(time.time() * 1000) % (1 << BITS)) - ms) / 1000.0
    return alter if -1 < alter < 3600 else None
