
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
    if not REPORTLAB_AVAILABLE:
        return False, "reportlab is not installed. Run: pip install reportlab"

    if not lines:
        return False, "Nothing to export — the canvas is empty."

    all_pts = []
    for obj in lines:
        all_pts += [(obj.x1, obj.y1), (obj.x2, obj.y2)]
    min_x = min(p[0] for p in all_pts)
    min_y = min(p[1] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    max_y = max(p[1] for p in all_pts)
    w = max(max_x - min_x, 1e-6)
    h = max(max_y - min_y, 1e-6)

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

        return (y - min_y) * scale + offset_y

    stroke_width = max(0.5, scale / 80.0)

    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        c = rl_canvas.Canvas(filepath, pagesize=(PAGE_W, PAGE_H))
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(stroke_width)
        c.setLineCap(1)             

        for obj in lines:
            c.line(tx(obj.x1), ty(obj.y1), tx(obj.x2), ty(obj.y2))

        c.showPage()
        c.save()
        return True, ""
    except Exception as e:
        return False, f"PDF export failed: {e}"
