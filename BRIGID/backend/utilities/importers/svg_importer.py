"""
svg_importer.py
Parse SVG files and return styled line segments for the BRIGID CAD engine.
Pure Python — no Qt dependency.
"""

import xml.etree.ElementTree as ET
import re
from typing import Optional

NON_WALL_STROKE = "#8e949c"


def _normalize_stroke_color(value: Optional[str]) -> str:
    if not value:
        return ""
    stroke = value.strip().lower()
    if not stroke or stroke == "none":
        return ""
    if stroke.startswith("#"):
        if len(stroke) == 4:
            return "#" + "".join(ch * 2 for ch in stroke[1:])
        return stroke
    m = re.match(r"rgb\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)\s*\)", stroke)
    if m:
        r, g, b = (max(0, min(255, int(x))) for x in m.groups())
        return f"#{r:02x}{g:02x}{b:02x}"
    return stroke


def _effective_stroke(elem) -> str:
    stroke = _normalize_stroke_color(elem.attrib.get("stroke"))
    if stroke:
        return stroke
    style = elem.attrib.get("style") or ""
    for part in style.split(";"):
        part = part.strip()
        if part.startswith("stroke:"):
            return _normalize_stroke_color(part.split(":", 1)[1])
    return ""


def extract_styled_segments_from_svg(filepath: str):
    """
    Returns (entries, error) where each entry is:
      {"segment": (x1, y1, x2, y2), "color": "#rrggbb", "role": "wall"|"non_wall"}
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except Exception as e:
        return [], f"Failed to parse SVG: {e}"

    # Determine SVG height for Y-flip
    vb = root.attrib.get("viewBox", "")
    svg_height = None
    if vb:
        parts = vb.replace(",", " ").split()
        if len(parts) == 4:
            try:
                svg_height = float(parts[3])
            except ValueError:
                pass
    if svg_height is None:
        h_str = root.attrib.get("height", "")
        try:
            svg_height = float(re.sub(r"[^0-9.]", "", h_str))
        except (ValueError, TypeError):
            svg_height = None

    # Check for embedded CAD metadata for perfect roundtrip
    cad_scale = root.attrib.get("data-cad-scale")
    cad_min_x = root.attrib.get("data-cad-min-x")
    cad_min_y = root.attrib.get("data-cad-min-y")
    cad_off_x = root.attrib.get("data-cad-offset-x")
    cad_off_y = root.attrib.get("data-cad-offset-y")

    has_cad_meta = all(v is not None for v in (cad_scale, cad_min_x, cad_min_y, cad_off_x, cad_off_y))
    reverse_x = reverse_y = None
    if has_cad_meta:
        try:
            c_scale = float(cad_scale)
            c_mx = float(cad_min_x)
            c_my = float(cad_min_y)
            c_ox = float(cad_off_x)
            c_oy = float(cad_off_y)
            doc_size = 1000.0

            def reverse_x(tx, _s=c_scale, _mx=c_mx, _ox=c_ox):
                return (tx - _ox) / _s + _mx

            def reverse_y(ty, _s=c_scale, _my=c_my, _oy=c_oy, _d=doc_size):
                return (_d - ty - _oy) / _s + _my
        except ValueError:
            has_cad_meta = False

    def flip_y(y):
        return (svg_height - y) if svg_height is not None else y

    entries = []

    def add_segment(x1, y1, x2, y2, color):
        role = "non_wall" if _normalize_stroke_color(color) == NON_WALL_STROKE else "wall"
        if has_cad_meta:
            seg = (reverse_x(x1), reverse_y(y1), reverse_x(x2), reverse_y(y2))
        else:
            seg = (x1, flip_y(y1), x2, flip_y(y2))
        entries.append({
            "segment": seg,
            "color": _normalize_stroke_color(color) or "#4a9eff",
            "role": role,
        })

    for elem in root.iter():
        tag = elem.tag.split('}')[-1]
        stroke = _effective_stroke(elem)

        if tag == "line":
            try:
                x1 = float(elem.attrib.get("x1", 0))
                y1 = float(elem.attrib.get("y1", 0))
                x2 = float(elem.attrib.get("x2", 0))
                y2 = float(elem.attrib.get("y2", 0))
                add_segment(x1, y1, x2, y2, stroke)
            except ValueError:
                pass

        elif tag in ("polyline", "polygon"):
            pts_str = elem.attrib.get("points", "")
            nums = re.findall(r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', pts_str)
            try:
                coords = [float(n) for n in nums]
                points = [(coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)]
                for i in range(len(points) - 1):
                    add_segment(points[i][0], points[i][1], points[i+1][0], points[i+1][1], stroke)
                if tag == "polygon" and len(points) > 2:
                    add_segment(points[-1][0], points[-1][1], points[0][0], points[0][1], stroke)
            except (ValueError, IndexError):
                pass

        elif tag == "rect":
            if not stroke:
                continue
            try:
                rx = float(elem.attrib.get("x", 0))
                ry = float(elem.attrib.get("y", 0))
                rw = float(elem.attrib.get("width", 0))
                rh = float(elem.attrib.get("height", 0))
                if rw > 0 and rh > 0:
                    add_segment(rx, ry, rx + rw, ry, stroke)
                    add_segment(rx + rw, ry, rx + rw, ry + rh, stroke)
                    add_segment(rx + rw, ry + rh, rx, ry + rh, stroke)
                    add_segment(rx, ry + rh, rx, ry, stroke)
            except ValueError:
                pass

        elif tag == "path":
            d = elem.attrib.get("d", "").strip()
            if d:
                _parse_path(d, lambda x1, y1, x2, y2: add_segment(x1, y1, x2, y2, stroke))

    if not entries:
        return [], "No line geometry found in SVG."

    return entries, None


def extract_lines_from_svg(filepath: str):
    """Simplified: returns (segments, error) without color metadata."""
    entries, error = extract_styled_segments_from_svg(filepath)
    return [e["segment"] for e in entries], error


def _parse_path(d: str, add_segment):
    tokens = re.findall(
        r'([MmLlHhVvZzCcSsQqTtAa])|'
        r'([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)', d)

    current_cmd = None
    current_pt = (0.0, 0.0)
    first_pt = (0.0, 0.0)
    coords: list[float] = []
    implicit_next = {'M': 'L', 'm': 'l'}

    i = 0
    while i < len(tokens):
        cmd_tok, val_tok = tokens[i]
        i += 1

        if cmd_tok:
            if current_cmd and coords:
                segs, current_pt, first_pt = _flush(current_cmd, coords, current_pt, first_pt)
                for seg in segs:
                    add_segment(*seg)
                coords = []

            if cmd_tok in ('Z', 'z'):
                if current_pt != first_pt:
                    add_segment(current_pt[0], current_pt[1], first_pt[0], first_pt[1])
                current_pt = first_pt
                current_cmd = None
            else:
                current_cmd = cmd_tok

        elif val_tok:
            if current_cmd in ('C', 'c', 'S', 's', 'Q', 'q', 'T', 't', 'A', 'a'):
                pass  # skip curve args
            else:
                coords.append(float(val_tok))

            if current_cmd in ('M', 'm') and len(coords) == 2:
                dx, dy = coords
                new_pt = (dx, dy) if current_cmd == 'M' else (current_pt[0]+dx, current_pt[1]+dy)
                current_pt = first_pt = new_pt
                coords = []
                current_cmd = implicit_next[current_cmd]

            elif current_cmd in ('L', 'l') and len(coords) == 2:
                dx, dy = coords
                new_pt = (dx, dy) if current_cmd == 'L' else (current_pt[0]+dx, current_pt[1]+dy)
                add_segment(current_pt[0], current_pt[1], new_pt[0], new_pt[1])
                current_pt = new_pt; coords = []

            elif current_cmd in ('H', 'h') and len(coords) == 1:
                val = coords[0]
                new_pt = (val if current_cmd == 'H' else current_pt[0]+val, current_pt[1])
                add_segment(current_pt[0], current_pt[1], new_pt[0], new_pt[1])
                current_pt = new_pt; coords = []

            elif current_cmd in ('V', 'v') and len(coords) == 1:
                val = coords[0]
                new_pt = (current_pt[0], val if current_cmd == 'V' else current_pt[1]+val)
                add_segment(current_pt[0], current_pt[1], new_pt[0], new_pt[1])
                current_pt = new_pt; coords = []

    # Flush any trailing coords
    if current_cmd and coords:
        segs, _, _ = _flush(current_cmd, coords, current_pt, first_pt)
        for seg in segs:
            add_segment(*seg)


def _flush(cmd, coords, cp, fp):
    segs = []
    if cmd in ('L', 'l'):
        while len(coords) >= 2:
            dx, dy = coords.pop(0), coords.pop(0)
            np_ = (dx, dy) if cmd == 'L' else (cp[0]+dx, cp[1]+dy)
            segs.append((cp[0], cp[1], np_[0], np_[1])); cp = np_
    elif cmd in ('H', 'h'):
        while coords:
            val = coords.pop(0)
            np_ = (val if cmd == 'H' else cp[0]+val, cp[1])
            segs.append((cp[0], cp[1], np_[0], np_[1])); cp = np_
    elif cmd in ('V', 'v'):
        while coords:
            val = coords.pop(0)
            np_ = (cp[0], val if cmd == 'V' else cp[1]+val)
            segs.append((cp[0], cp[1], np_[0], np_[1])); cp = np_
    return segs, cp, fp
