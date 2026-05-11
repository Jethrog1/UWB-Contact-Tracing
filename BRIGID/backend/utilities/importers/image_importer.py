
from __future__ import annotations

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

def extract_lines_from_image(filepath: str, target_world_size: float = 50.0):
    if not CV2_AVAILABLE:
        return [], "opencv-python is not installed. Run: pip install opencv-python"

    img = cv2.imread(filepath)
    if img is None:
        return [], f"Could not load image: {filepath}"

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, 40, 120, apertureSize=3)

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=float(np.pi) / 180.0,
        threshold=50,
        minLineLength=max(10, min(w, h) // 30),
        maxLineGap=max(4, min(w, h) // 100),
    )

    if lines is None or len(lines) == 0:
        return [], (
            "No line segments detected. The image may be a photograph or too low-contrast. "
            "Try a clean vector-style floor plan exported as PNG."
        )

    raw: list[tuple[float, float, float, float]] = [
        (float(x1), float(y1), float(x2), float(y2))
        for x1, y1, x2, y2 in lines[:, 0]
    ]

    bbox_size = max(w, h, 1)
    scale = target_world_size / bbox_size

    world = [
        (x1 * scale, (h - y1) * scale, x2 * scale, (h - y2) * scale)
        for x1, y1, x2, y2 in raw
    ]

    return world, None
