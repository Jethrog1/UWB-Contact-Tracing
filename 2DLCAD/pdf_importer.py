"""
pdf_importer.py
Imports vector line geometry from a PDF file using PyMuPDF (fitz).

Only straight line segments are extracted (lineto commands).
Curves are approximated by their control-point endpoints (rough).
Coordinates are normalized so the geometry fits within a 20x20 world unit bbox.
"""

import math

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False


def _flatten_rect(rect):
    """Return (x0, y0, x1, y1) from a fitz.Rect."""
    return rect.x0, rect.y0, rect.x1, rect.y1


def _pdf_to_world(x, y, page_height, offset_x, offset_y, scale):
    """Convert PDF coordinates (origin bottom-left) to world coordinates."""
    # PDF y increases upward; screen y increases downward.
    # We flip y so shapes appear right-side-up in the CAD canvas.
    wx = (x - offset_x) * scale
    wy = -(y - offset_y) * scale   # flip y
    return wx, wy


def extract_lines_from_pdf(filepath, target_world_size=50.0, curve_segments=8):
    """
    Parse a PDF file and extract straight line segments.

    Parameters
    ----------
    filepath : str
        Path to the PDF file.
    target_world_size : float
        The imported geometry will be scaled so its bounding box fits within
        this size (in world units). Default is 20 units (≈ a 20 m floor plan).
    curve_segments : int
        Number of line segments used to approximate each Bezier curve.

    Returns
    -------
    segments : list of (x1, y1, x2, y2)
        Line segment coordinates in world space.
    error : str or None
        Error message if something went wrong, else None.
    """
    if not FITZ_AVAILABLE:
        return [], "PyMuPDF is not installed. Run: pip install pymupdf"

    try:
        doc = fitz.open(filepath)
    except Exception as e:
        return [], f"Could not open PDF: {e}"

    raw_segments = []  # list of (x1, y1, x2, y2) in PDF points

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_height = page.rect.height  # needed for y-flip
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

            # ── Filter 1: skip the full-page background rectangle ──────────
            # Google Drawings always puts a filled rect the exact size of the
            # page as the first path (the slide background).  We detect it by
            # checking whether the path bbox is (approximately) the page size.
            path_bbox = path.get("rect")
            if path_bbox is not None:
                EPS_BG = 2.0  # pts tolerance
                if (abs(path_bbox.x0) < EPS_BG and
                        abs(path_bbox.y0) < EPS_BG and
                        abs(path_bbox.x1 - page_w) < EPS_BG and
                        abs(path_bbox.y1 - page_h) < EPS_BG):
                    continue  # this is the slide background — skip it

            # ── Categorise items ──────────────────────────────────────────
            has_moveto = any(it[0] == "m" for it in items)
            has_rect   = any(it[0] == "re" for it in items)
            close_path = path.get("closePath") or False

            # ── Rect shortcut ─────────────────────────────────────────────
            if has_rect:
                for item in items:
                    if item[0] == "re":
                        rect = item[1]
                        x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
                        raw_segments.extend([
                            (x0, y0, x1, y0),
                            (x1, y0, x1, y1),
                            (x1, y1, x0, y1),
                            (x0, y1, x0, y0),
                        ])
                # Don't process "l" items — they would duplicate the rect edges
                continue

            # ── Polygon / polyline path (may have no "m" at all) ──────────
            # Google Drawings exports triangles/polygons as a sequence of
            # bare "l" lineto items where each point IS a vertex (no preceding
            # moveto).  We collect all "l" points in order, then:
            #   • emit edges between consecutive points
            #   • if the path is closed (or just has >2 bare points), close it
            if not has_moveto:
                pts = [item[1] for item in items if item[0] == "l"]
                
                # Case 1: A single bare 'lineto' in a path (e.g., boat.pdf).
                # The bounding box defines the line. One end is 'p', the other end
                # must be the opposite corner of the bounding box.
                if len(pts) == 1:
                    p = pts[0]
                    rect = path["rect"]
                    # If 'p' is at the bottom-right, start is top-left, etc.
                    # We can find the start point by checking which corner is furthest from 'p'
                    # or simply by mirroring 'p' across the center of the bounding box.
                    cx = (rect.x0 + rect.x1) / 2.0
                    cy = (rect.y0 + rect.y1) / 2.0
                    start_x = cx - (p.x - cx)
                    start_y = cy - (p.y - cy)
                    raw_segments.append((start_x, start_y, p.x, p.y))
                    
                # Case 2: Sequence of bare 'lineto' vertices forming a polygon
                elif len(pts) >= 2:
                    for i in range(len(pts) - 1):
                        a, b = pts[i], pts[i + 1]
                        raw_segments.append((a.x, a.y, b.x, b.y))
                    # Close the polygon back to the first vertex
                    if len(pts) >= 3:
                        last, first = pts[-1], pts[0]
                        if math.hypot(last.x - first.x, last.y - first.y) > 1e-4:
                            raw_segments.append((last.x, last.y, first.x, first.y))
                continue

            # ── Normal path with moveto commands ─────────────────────────
            current_pt = None
            first_pt   = None

            for item in items:
                kind = item[0]

                if kind == "m":
                    current_pt = item[1]
                    first_pt   = item[1]

                elif kind == "l":
                    if current_pt is not None:
                        p1 = current_pt
                        p2 = item[1]
                        raw_segments.append((p1.x, p1.y, p2.x, p2.y))
                        current_pt = p2

                elif kind == "c":  # cubic Bezier
                    if current_pt is not None:
                        p0 = current_pt
                        p1, p2, p3 = item[1], item[2], item[3]
                        pts = _cubic_bezier_points(p0, p1, p2, p3, curve_segments)
                        for i in range(len(pts) - 1):
                            a, b = pts[i], pts[i + 1]
                            raw_segments.append((a[0], a[1], b[0], b[1]))
                        current_pt = p3

                elif kind == "qu":  # quad
                    qpts = item[1]
                    if len(qpts) >= 4:
                        for i in range(4):
                            a = qpts[i]
                            b = qpts[(i + 1) % 4]
                            raw_segments.append((a.x, a.y, b.x, b.y))

            # Close the sub-path if flagged
            if close_path and current_pt is not None and first_pt is not None:
                if math.hypot(current_pt.x - first_pt.x, current_pt.y - first_pt.y) > 1e-4:
                    raw_segments.append(
                        (current_pt.x, current_pt.y, first_pt.x, first_pt.y)
                    )

    doc.close()

    if not raw_segments:
        return [], "No vector line data found in this PDF. The file may be a scanned image."

    # --- Remove near-zero-length segments ---
    EPS = 1e-4
    raw_segments = [s for s in raw_segments
                    if math.hypot(s[2] - s[0], s[3] - s[1]) > EPS]

    # --- Compute bounding box (in PDF coordinates) ---
    xs = [s[0] for s in raw_segments] + [s[2] for s in raw_segments]
    ys = [s[1] for s in raw_segments] + [s[3] for s in raw_segments]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    width = max_x - min_x
    height = max_y - min_y
    bbox_size = max(width, height)

    if bbox_size < EPS:
        return [], "All segments at same point — nothing to import."

    scale = target_world_size / bbox_size

    # --- Convert to world coordinates ---
    world_segments = []
    for x1, y1, x2, y2 in raw_segments:
        wx1, wy1 = _pdf_to_world(x1, y1, 0, min_x, min_y, scale)
        wx2, wy2 = _pdf_to_world(x2, y2, 0, min_x, min_y, scale)
        world_segments.append((wx1, wy1, wx2, wy2))

    return world_segments, None


def _cubic_bezier_points(p0, p1, p2, p3, n):
    """Sample n+1 points along a cubic Bezier curve."""
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1.0 - t
        x = mt**3 * p0.x + 3*mt**2*t * p1.x + 3*mt*t**2 * p2.x + t**3 * p3.x
        y = mt**3 * p0.y + 3*mt**2*t * p1.y + 3*mt*t**2 * p2.y + t**3 * p3.y
        pts.append((x, y))
    return pts
