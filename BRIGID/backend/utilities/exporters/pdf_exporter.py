"""
pdf_exporter.py
Export CAD line geometry to a vector PDF using reportlab.

A4 landscape (297 × 210 mm).  Lines are drawn black on white since PDF
is typically viewed / printed on a white background.
"""

from __future__ import annotations
import os
from typing import Any

try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.units import mm
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def export_lines_to_pdf(lines: list[Any], filepath: str) -> tuple[bool, str]:
    """
    Write *lines* (list of Line objects with .x1 .y1 .x2 .y2) to *filepath*.

    Returns (success, error_message).
    """
    if not REPORTLAB_AVAILABLE:
        return False, "reportlab is not installed. Run: pip install reportlab"

    if not lines:
        return False, "Nothing to export — the canvas is empty."

    # Bounding box
    all_pts = []
    for obj in lines:
        all_pts += [(obj.x1, obj.y1), (obj.x2, obj.y2)]
    min_x = min(p[0] for p in all_pts)
    min_y = min(p[1] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    max_y = max(p[1] for p in all_pts)
    w = max(max_x - min_x, 1e-6)
    h = max(max_y - min_y, 1e-6)

    # A4 landscape in points (reportlab uses points, 1 pt = 1/72 inch)
    PAGE_W_MM  = 297.0
    PAGE_H_MM  = 210.0
    MARGIN_MM  = 15.0
    PAGE_W = PAGE_W_MM * mm
    PAGE_H = PAGE_H_MM * mm
    AVAIL_W = (PAGE_W_MM - MARGIN_MM * 2) * mm
    AVAIL_H = (PAGE_H_MM - MARGIN_MM * 2) * mm

    scale    = min(AVAIL_W / w, AVAIL_H / h)
    offset_x = (PAGE_W - w * scale) / 2.0
    offset_y = (PAGE_H - h * scale) / 2.0

    def tx(x: float) -> float:
        return (x - min_x) * scale + offset_x

    def ty(y: float) -> float:
        # reportlab Y-up, CAD Y-up → same direction, just offset
        return (y - min_y) * scale + offset_y

    stroke_width = max(0.5, scale / 80.0)

    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        c = rl_canvas.Canvas(filepath, pagesize=(PAGE_W, PAGE_H))
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(stroke_width)
        c.setLineCap(1)  # round cap

        for obj in lines:
            c.line(tx(obj.x1), ty(obj.y1), tx(obj.x2), ty(obj.y2))

        c.showPage()
        c.save()
        return True, ""
    except Exception as e:
        return False, f"PDF export failed: {e}"
