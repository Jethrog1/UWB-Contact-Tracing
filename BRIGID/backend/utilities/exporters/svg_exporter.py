"""
svg_exporter.py
Export CAD line geometry to an SVG file.

The SVG embeds CAD metadata attributes so the file can be re-imported with
perfect coordinate roundtrip fidelity.
"""

from __future__ import annotations
import os
from typing import Any


def export_lines_to_svg(lines: list[Any], filepath: str) -> tuple[bool, str]:
    """
    Write *lines* (list of Line objects with .x1 .y1 .x2 .y2 .color) to *filepath*.

    Returns (success, error_message).
    """
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

    DOC_SIZE  = 1000.0
    MARGIN    = 50.0
    AVAILABLE = DOC_SIZE - MARGIN * 2

    scale    = min(AVAILABLE / w, AVAILABLE / h)
    offset_x = (DOC_SIZE - w * scale) / 2.0
    offset_y = (DOC_SIZE - h * scale) / 2.0

    def tx(x: float) -> float:
        return (x - min_x) * scale + offset_x

    def ty(y: float) -> float:
        # CAD Y-up → SVG Y-down, then centre
        return DOC_SIZE - (y - min_y) * scale - offset_y

    stroke_width = max(1.0, scale / 2.0)

    svg_elements: list[str] = []
    for obj in lines:
        color = getattr(obj, 'color', '#4a9eff') or '#4a9eff'
        svg_elements.append(
            f'  <line x1="{tx(obj.x1):.3f}" y1="{ty(obj.y1):.3f}" '
            f'x2="{tx(obj.x2):.3f}" y2="{ty(obj.y2):.3f}" '
            f'stroke="{color}" stroke-width="{stroke_width:.2f}" stroke-linecap="round"/>'
        )

    # Background matches CAD dark theme so the SVG looks right when opened standalone
    svg = "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="100%" height="100%" '
        f'viewBox="0 0 {DOC_SIZE:.0f} {DOC_SIZE:.0f}" '
        f'data-cad-min-x="{min_x}" data-cad-min-y="{min_y}" '
        f'data-cad-scale="{scale}" '
        f'data-cad-offset-x="{offset_x}" data-cad-offset-y="{offset_y}">',
        f'  <rect width="100%" height="100%" fill="#090d15"/>',
        *svg_elements,
        '</svg>',
    ])

    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(svg)
        return True, ""
    except OSError as e:
        return False, f"Write failed: {e}"
