
import math

try:
    import fitz           
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

def _pdf_to_world(x, y, offset_x, offset_y, scale):
    wx = (x - offset_x) * scale
    wy = -(y - offset_y) * scale
    return wx, wy

def extract_lines_from_pdf(filepath: str, target_world_size: float = 50.0, curve_segments: int = 8):
    if not FITZ_AVAILABLE:
        return [], "PyMuPDF is not installed. Run: pip install pymupdf"

    try:
        doc = fitz.open(filepath)
    except Exception as e:
        return [], f"Could not open PDF: {e}"

    raw: list[tuple[float, float, float, float]] = []

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_w = page.rect.width
        page_h = page.rect.height

        try:
            paths = page.get_drawings()
        except Exception:
            continue

        for path in paths:
            items = path.get("items", [])
            if not items:
                continue

            path_bbox = path.get("rect")
            if path_bbox is not None:
                EPS_BG = 2.0
                if (abs(path_bbox.x0) < EPS_BG and abs(path_bbox.y0) < EPS_BG and
                        abs(path_bbox.x1 - page_w) < EPS_BG and abs(path_bbox.y1 - page_h) < EPS_BG):
                    continue

            has_moveto = any(it[0] == "m" for it in items)
            has_rect   = any(it[0] == "re" for it in items)
            close_path = path.get("closePath") or False

            if has_rect:
                for item in items:
                    if item[0] == "re":
                        r = item[1]
                        raw.extend([
                            (r.x0, r.y0, r.x1, r.y0),
                            (r.x1, r.y0, r.x1, r.y1),
                            (r.x1, r.y1, r.x0, r.y1),
                            (r.x0, r.y1, r.x0, r.y0),
                        ])
                continue

            if not has_moveto:
                pts = [item[1] for item in items if item[0] == "l"]
                if len(pts) == 1:
                    p = pts[0]
                    rect = path["rect"]
                    cx = (rect.x0 + rect.x1) / 2.0
                    cy = (rect.y0 + rect.y1) / 2.0
                    raw.append((cx - (p.x - cx), cy - (p.y - cy), p.x, p.y))
                elif len(pts) >= 2:
                    for i in range(len(pts) - 1):
                        a, b = pts[i], pts[i + 1]
                        raw.append((a.x, a.y, b.x, b.y))
                    if len(pts) >= 3:
                        last, first = pts[-1], pts[0]
                        if math.hypot(last.x - first.x, last.y - first.y) > 1e-4:
                            raw.append((last.x, last.y, first.x, first.y))
                continue

            current_pt = None
            first_pt   = None

            for item in items:
                kind = item[0]
                if kind == "m":
                    current_pt = item[1]
                    first_pt   = item[1]
                elif kind == "l":
                    if current_pt is not None:
                        p1, p2 = current_pt, item[1]
                        raw.append((p1.x, p1.y, p2.x, p2.y))
                        current_pt = p2
                elif kind == "c":
                    if current_pt is not None:
                        p0 = current_pt
                        p1, p2, p3 = item[1], item[2], item[3]
                        pts2 = _cubic_bezier_points(p0, p1, p2, p3, curve_segments)
                        for i in range(len(pts2) - 1):
                            a, b = pts2[i], pts2[i + 1]
                            raw.append((a[0], a[1], b[0], b[1]))
                        current_pt = p3
                elif kind == "qu":
                    qpts = item[1]
                    if len(qpts) >= 4:
                        for i in range(4):
                            a = qpts[i]; b = qpts[(i + 1) % 4]
                            raw.append((a.x, a.y, b.x, b.y))

            if close_path and current_pt is not None and first_pt is not None:
                if math.hypot(current_pt.x - first_pt.x, current_pt.y - first_pt.y) > 1e-4:
                    raw.append((current_pt.x, current_pt.y, first_pt.x, first_pt.y))

    doc.close()

    if not raw:
        return [], "No vector line data found in this PDF. The file may be a scanned image."

    EPS = 1e-4
    raw = [s for s in raw if math.hypot(s[2] - s[0], s[3] - s[1]) > EPS]

    if not raw:
        return [], "All segments at same point — nothing to import."

    xs = [s[0] for s in raw] + [s[2] for s in raw]
    ys = [s[1] for s in raw] + [s[3] for s in raw]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    bbox_size = max(max_x - min_x, max_y - min_y)

    if bbox_size < EPS:
        return [], "All segments at same point — nothing to import."

    scale = target_world_size / bbox_size

    world: list[tuple[float, float, float, float]] = []
    for x1, y1, x2, y2 in raw:
        wx1, wy1 = _pdf_to_world(x1, y1, min_x, min_y, scale)
        wx2, wy2 = _pdf_to_world(x2, y2, min_x, min_y, scale)
        world.append((wx1, wy1, wx2, wy2))

    return world, None

def _cubic_bezier_points(p0, p1, p2, p3, n):
    pts = []
    for i in range(n + 1):
        t = i / n; mt = 1.0 - t
        x = mt**3*p0.x + 3*mt**2*t*p1.x + 3*mt*t**2*p2.x + t**3*p3.x
        y = mt**3*p0.y + 3*mt**2*t*p1.y + 3*mt*t**2*p2.y + t**3*p3.y
        pts.append((x, y))
    return pts
