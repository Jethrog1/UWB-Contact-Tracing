import xml.etree.ElementTree as ET
import re

def extract_lines_from_svg(filepath: str):
    """
    Parse an SVG file and extract lines and paths as line segments.
    Returns a tuple (segments, error_msg).
    segments is a list of (x1, y1, x2, y2) in raw SVG coordinates.
    error_msg is a string (or None if success).

    No transforms, filters, or scaling are applied – coordinates are read
    directly from the vector data as written in the SVG file.
    The Y-axis is flipped to convert from SVG screen-space (Y-down) back
    to CAD world-space (Y-up), using the viewBox height.
    """
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except Exception as e:
        return [], f"Failed to parse SVG:\n{e}"

    # Read viewBox to get the canvas height for Y-axis flip
    vb = root.attrib.get("viewBox", "")
    svg_height = None
    if vb:
        parts = vb.replace(",", " ").split()
        if len(parts) == 4:
            try:
                svg_height = float(parts[3])
            except ValueError:
                pass

    # If no viewBox, try height attribute
    if svg_height is None:
        h_str = root.attrib.get("height", "")
        try:
            svg_height = float(re.sub(r"[^0-9.]", "", h_str))
        except (ValueError, TypeError):
            svg_height = None

    # Check for CAD custom metadata to reverse export scaling exactly
    cad_scale = root.attrib.get("data-cad-scale")
    cad_min_x = root.attrib.get("data-cad-min-x")
    cad_min_y = root.attrib.get("data-cad-min-y")
    cad_off_x = root.attrib.get("data-cad-offset-x")
    cad_off_y = root.attrib.get("data-cad-offset-y")
    
    has_cad_meta = all(v is not None for v in (cad_scale, cad_min_x, cad_min_y, cad_off_x, cad_off_y))
    if has_cad_meta:
        try:
            c_scale = float(cad_scale)
            c_mx = float(cad_min_x)
            c_my = float(cad_min_y)
            c_ox = float(cad_off_x)
            c_oy = float(cad_off_y)
            doc_size = 1000.0
            
            def reverse_x(tx): return (tx - c_ox) / c_scale + c_mx
            def reverse_y(ty): return (doc_size - ty - c_oy) / c_scale + c_my
        except ValueError:
            has_cad_meta = False

    def flip_y(y):
        """Invert Y axis from SVG screen-space to CAD world-space."""
        if svg_height is not None:
            return svg_height - y
        return y

    segments = []

    def parse_float(s):
        return float(s)

    def add_segment(x1, y1, x2, y2):
        if has_cad_meta:
            segments.append((reverse_x(x1), reverse_y(y1), reverse_x(x2), reverse_y(y2)))
        else:
            segments.append((x1, flip_y(y1), x2, flip_y(y2)))


    for elem in root.iter():
        tag = elem.tag.split('}')[-1]  # strip namespace

        # --- <line> ---
        if tag == "line":
            try:
                x1 = float(elem.attrib.get("x1", 0))
                y1 = float(elem.attrib.get("y1", 0))
                x2 = float(elem.attrib.get("x2", 0))
                y2 = float(elem.attrib.get("y2", 0))
                add_segment(x1, y1, x2, y2)
            except ValueError:
                pass

        # --- <polyline> / <polygon> ---
        elif tag in ("polyline", "polygon"):
            pts_str = elem.attrib.get("points", "")
            nums = re.findall(r'[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?', pts_str)
            try:
                coords = [float(n) for n in nums]
                points = [(coords[i], coords[i+1]) for i in range(0, len(coords)-1, 2)]
                for i in range(len(points) - 1):
                    add_segment(points[i][0], points[i][1], points[i+1][0], points[i+1][1])
                if tag == "polygon" and len(points) > 2:
                    add_segment(points[-1][0], points[-1][1], points[0][0], points[0][1])
            except (ValueError, IndexError):
                pass

        # --- <rect> ---
        elif tag == "rect":
            # Skip background/fill-only rects (e.g. Google Drawings page canvas).
            # Only import rects that have a visible stroke.
            stroke = (elem.attrib.get("stroke") or "").strip().lower()
            style = elem.attrib.get("style") or ""
            # Also check inline style for stroke
            style_stroke_match = None
            for part in style.split(";"):
                part = part.strip()
                if part.startswith("stroke:"):
                    style_stroke_match = part.split(":", 1)[1].strip().lower()
                    break
            effective_stroke = style_stroke_match if style_stroke_match else stroke
            if not effective_stroke or effective_stroke in ("none", ""):
                continue  # no visible stroke → it's a background element
            try:
                rx = float(elem.attrib.get("x", 0))
                ry = float(elem.attrib.get("y", 0))
                rw = float(elem.attrib.get("width", 0))
                rh = float(elem.attrib.get("height", 0))
                if rw > 0 and rh > 0:
                    add_segment(rx,      ry,      rx + rw, ry)
                    add_segment(rx + rw, ry,      rx + rw, ry + rh)
                    add_segment(rx + rw, ry + rh, rx,      ry + rh)
                    add_segment(rx,      ry + rh, rx,      ry)
            except ValueError:
                pass

        # --- <path> ---
        elif tag == "path":
            d = elem.attrib.get("d", "").strip()
            if not d:
                continue
            _parse_path(d, add_segment)

    return segments, None


def _parse_path(d, add_segment):
    """
    Parse an SVG path 'd' attribute and call add_segment(x1,y1,x2,y2) for
    each straight-line segment found. Handles M, L, H, V, Z (absolute) and
    m, l, h, v, z (relative). Cubic/quadratic beziers (C, c, Q, q, S, s, T, t)
    are skipped as they are not supported.
    """
    # Tokenise: split on command letters, keeping them
    tokens = re.findall(r'([MmLlHhVvZzCcSsQqTtAa])|'
                        r'([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)', d)

    current_cmd = None
    current_pt = (0.0, 0.0)
    first_pt = (0.0, 0.0)      # For Z close
    coords = []

    def flush_coords(cmd, coords, current_pt, first_pt):
        """Process accumulated coordinate pairs for current command."""
        segs = []
        cp = current_pt
        fp = first_pt

        if cmd == 'M':
            while len(coords) >= 2:
                x, y = coords.pop(0), coords.pop(0)
                if cp == current_pt and cp == first_pt:  # very first M
                    cp = (x, y)
                    fp = (x, y)
                else:
                    cp = (x, y)
                # After first M, implicit L
                if cmd == 'M' and cp != (x, y):
                    segs.append((cp[0], cp[1], x, y))
                    cp = (x, y)
            return segs, cp, fp

        if cmd == 'm':
            while len(coords) >= 2:
                dx, dy = coords.pop(0), coords.pop(0)
                new_pt = (cp[0] + dx, cp[1] + dy)
                cp = new_pt
                if fp == current_pt:
                    fp = cp
            return segs, cp, fp

        if cmd in ('L', 'l'):
            while len(coords) >= 2:
                dx, dy = coords.pop(0), coords.pop(0)
                if cmd == 'L':
                    new_pt = (dx, dy)
                else:
                    new_pt = (cp[0] + dx, cp[1] + dy)
                segs.append((cp[0], cp[1], new_pt[0], new_pt[1]))
                cp = new_pt
            return segs, cp, fp

        if cmd in ('H', 'h'):
            while len(coords) >= 1:
                val = coords.pop(0)
                new_pt = (val if cmd == 'H' else cp[0] + val, cp[1])
                segs.append((cp[0], cp[1], new_pt[0], new_pt[1]))
                cp = new_pt
            return segs, cp, fp

        if cmd in ('V', 'v'):
            while len(coords) >= 1:
                val = coords.pop(0)
                new_pt = (cp[0], val if cmd == 'V' else cp[1] + val)
                segs.append((cp[0], cp[1], new_pt[0], new_pt[1]))
                cp = new_pt
            return segs, cp, fp

        return segs, cp, fp

    implicit_next = {'M': 'L', 'm': 'l'}  # after M, implicit is L; after m, l

    i = 0
    while i < len(tokens):
        cmd_tok, val_tok = tokens[i]
        i += 1

        if cmd_tok:
            # Process buffered coords for previous command first
            if current_cmd and coords:
                segs, current_pt, first_pt = flush_coords(current_cmd, coords, current_pt, first_pt)
                for seg in segs:
                    add_segment(*seg)
                coords = []

            if cmd_tok in ('Z', 'z'):
                if current_pt != first_pt:
                    add_segment(current_pt[0], current_pt[1], first_pt[0], first_pt[1])
                current_pt = first_pt
                current_cmd = None
            elif cmd_tok in ('M', 'm'):
                # Read first pair immediately to set start point
                current_cmd = cmd_tok
            elif cmd_tok in ('C', 'c', 'S', 's', 'Q', 'q', 'T', 't', 'A', 'a'):
                # Unsupported curve commands – skip their numeric arguments
                current_cmd = cmd_tok  # will accumulate then discard
            else:
                current_cmd = cmd_tok
        elif val_tok:
            if current_cmd in ('C', 'c', 'S', 's', 'Q', 'q', 'T', 't', 'A', 'a'):
                pass  # discard curve coordinates
            else:
                coords.append(float(val_tok))

            # For move commands, grab the first two numbers as the start point
            if current_cmd in ('M', 'm') and len(coords) == 2:
                dx, dy = coords[0], coords[1]
                if current_cmd == 'M':
                    new_pt = (dx, dy)
                else:
                    new_pt = (current_pt[0] + dx, current_pt[1] + dy)
                current_pt = new_pt
                first_pt = new_pt
                coords = []
                # After M/m, subsequent pairs are implicit L/l
                current_cmd = implicit_next[current_cmd]

            # For line commands, emit when we have a pair
            elif current_cmd in ('L', 'l') and len(coords) == 2:
                dx, dy = coords[0], coords[1]
                if current_cmd == 'L':
                    new_pt = (dx, dy)
                else:
                    new_pt = (current_pt[0] + dx, current_pt[1] + dy)
                add_segment(current_pt[0], current_pt[1], new_pt[0], new_pt[1])
                current_pt = new_pt
                coords = []

            # For H/h, emit when we have one number
            elif current_cmd in ('H', 'h') and len(coords) == 1:
                val = coords[0]
                new_pt = (val if current_cmd == 'H' else current_pt[0] + val, current_pt[1])
                add_segment(current_pt[0], current_pt[1], new_pt[0], new_pt[1])
                current_pt = new_pt
                coords = []

            # For V/v, emit when we have one number
            elif current_cmd in ('V', 'v') and len(coords) == 1:
                val = coords[0]
                new_pt = (current_pt[0], val if current_cmd == 'V' else current_pt[1] + val)
                add_segment(current_pt[0], current_pt[1], new_pt[0], new_pt[1])
                current_pt = new_pt
                coords = []
