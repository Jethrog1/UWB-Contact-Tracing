"""
map_canvas.py – RTLS Dashboard Map Canvas
==========================================
Custom QWidget canvas that displays a floor plan using the same 2D coordinate
system and Viewport transform as the CAD program (cad_core.Viewport).

SVG files are imported as raw vector line segments via svg_importer so they
render at the exact same scale/orientation as in the CAD canvas.
PDF / raster files are loaded as a background pixmap at high resolution.

Controls:
  - Middle-click drag  : pan
  - Left-click drag    : pan (PAN mode)
  - Scroll wheel       : zoom in/out (anchored to cursor)
  - F key              : fit geometry in view
  - Ctrl+scroll        : zoom (alternate binding)
"""

from __future__ import annotations
import os, sys, math
from typing import List, Optional, Tuple

from PyQt6.QtWidgets import QWidget, QApplication, QMenu, QInputDialog
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QBrush, QPixmap, QImage, QPainterPath,
    QWheelEvent, QMouseEvent
)
from PyQt6.QtCore import Qt, QPointF, QRectF, pyqtSignal

# ── Reuse the CAD viewport so the coordinate maths are identical ──────────────
sys.path.insert(0, os.path.dirname(__file__))
from cad_core import Viewport
from room_data import segments_match


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
ZOOM_MIN         = 0.1      # min scale (zoomed way out)
ZOOM_MAX         = 6000.0   # max scale (~3x more than before)
BG_COLOR         = QColor("#141414")
LINE_COLOR       = QColor("#4A9EFF")   # same default as CAD
SELECT_COLOR     = QColor("#FF8C00")   # highlight (orange)
SELECT_HIT_PX   = 8        # pixels tolerance for selection hit-test
RASTER_BG_ALPHA  = 255

# ──────────────────────────────────────────────────────────────────────────────
# Interaction modes (kept for compatibility with rtls_dashboard.py)
# ──────────────────────────────────────────────────────────────────────────────
class MapMode:
    PAN       = "pan"
    SELECT    = "select"    # click lines to select / deselect
    PICK_ROOM = "pick_room"
    CALIBRATE = "calibrate"
    PLACE     = "place"
    ZONE      = "zone"


# ──────────────────────────────────────────────────────────────────────────────
# MapCanvas
# ──────────────────────────────────────────────────────────────────────────────
class MapCanvas(QWidget):
    """
    2D floor-plan canvas for the RTLS dashboard.

    Renders vector geometry (from SVG) using the same Viewport transform as
    the CAD program, so scale/orientation are identical.  Raster / PDF content
    is rendered as a background pixmap.
    """

    # Signals
    calibration_click = pyqtSignal(QPointF)
    anchor_placed     = pyqtSignal(QPointF)
    no_image_warning  = pyqtSignal()
    selection_changed = pyqtSignal(object)  # emits the selected index set
    room_designated   = pyqtSignal(str, list)  # emits (room_name, list_of_segments)
    map_double_clicked = pyqtSignal(float, float)
    mode_change_requested = pyqtSignal(str)
    status_message_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.room_lookup = None

        # ── Viewport (same as CAD) ─────────────────────────────────────────
        self.vp = Viewport()

        # ── Content ───────────────────────────────────────────────────────
        # Vector segments: list of (x1, y1, x2, y2) in world space
        self._segments: List[Tuple[float, float, float, float]] = []
        # Optional raster background pixmap (for PDF/raster files)
        self._bg_pixmap: Optional[QPixmap] = None
        # Scale factor used when the pixmap was rendered (pixels-per-world-unit)
        self._bg_scale: float = 1.0

        # ── Interaction state ─────────────────────────────────────────────
        self.mode = MapMode.PAN
        self._pan_active = False
        self._pan_last   = QPointF()
        # Sub-segment selection: list of (x1,y1,x2,y2) computed from intersections
        self._selected_subsegments: List[Tuple[float,float,float,float]] = []
        self.highlighted_room = None

        self._content_loaded = False

    # ──────────────────────────────────────────────────────────────────────────
    # Public API (mirrors old MapCanvas)
    # ──────────────────────────────────────────────────────────────────────────

    def has_image(self) -> bool:
        return self._content_loaded

    def load_image(self, path: str) -> bool:
        """Delegate to the appropriate loader based on extension."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".svg":
            return self.load_svg(path)
        elif ext == ".pdf":
            return self.load_pdf(path)
        else:
            return self._load_raster(path)

    def load_svg(self, path: str) -> bool:
        """
        Import an SVG as raw vector line segments using svg_importer.
        Coordinates match the CAD world-space exactly (same Y-flip correction
        is applied in svg_importer).
        """
        try:
            from svg_importer import extract_lines_from_svg
            segments, err = extract_lines_from_svg(path)
        except Exception as e:
            return False

        if err:
            return False

        self._segments = segments
        self._bg_pixmap = None
        self._content_loaded = bool(segments)

        if self._content_loaded:
            self._auto_fit_after_load()
        self.update()
        return self._content_loaded

    def load_pdf(self, path: str, page: int = 0, dpi: int = 300) -> bool:
        """
        Render a PDF page to a high-res pixmap and display it as background.
        Uses 300 DPI for crisp rendering.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return False

        try:
            doc = fitz.open(path)
            if page >= len(doc):
                page = 0
            pg  = doc[page]
            mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
            pix = pg.get_pixmap(matrix=mat, alpha=False)
            img = QImage(pix.samples, pix.width, pix.height,
                         pix.stride, QImage.Format.Format_RGB888)
            self._bg_pixmap = QPixmap.fromImage(img)

            # Treat pixmap as world-space: 1 pixel = 1/dpi_scale world unit
            # We store the pixmap at its natural resolution; the viewport scale
            # maps world→screen.  Set bg_scale so that 1 world-unit corresponds
            # to 1 PDF point (1/72 inch) — convenient reference.
            self._bg_scale = dpi / 72.0   # pixels per world unit
            self._segments = []
            self._content_loaded = True
            self._auto_fit_after_load()
            self.update()
            return True
        except Exception:
            return False

    def _load_raster(self, path: str) -> bool:
        """Load a PNG/JPG/BMP raster image as background."""
        pix = QPixmap(path)
        if pix.isNull():
            return False
        self._bg_pixmap = pix
        self._bg_scale  = 1.0
        self._segments  = []
        self._content_loaded = True
        self._auto_fit_after_load()
        self.update()
        return True

    # ──────────────────────────────────────────────────────────────────────────
    # Viewport helpers
    # ──────────────────────────────────────────────────────────────────────────

    def fit_in_view(self):
        """Fit all content (vector or raster) into the visible widget area."""
        if not self._content_loaded:
            return

        W, H = self.width(), self.height()
        if W < 10 or H < 10:
            return

        if self._segments:
            xs = [s[0] for s in self._segments] + [s[2] for s in self._segments]
            ys = [s[1] for s in self._segments] + [s[3] for s in self._segments]
        elif self._bg_pixmap:
            pw = self._bg_pixmap.width()  / self._bg_scale
            ph = self._bg_pixmap.height() / self._bg_scale
            xs = [0.0, pw]
            ys = [0.0, ph]
        else:
            return

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1e-3)
        span_y = max(max_y - min_y, 1e-3)

        MARGIN = 0.05  # 5 % padding
        scale  = min((W * (1 - MARGIN * 2)) / span_x,
                     (H * (1 - MARGIN * 2)) / span_y)
        scale  = max(ZOOM_MIN, min(ZOOM_MAX, scale))

        cx_w = (min_x + max_x) / 2
        cy_w = (min_y + max_y) / 2

        # world_to_screen: sx = x*scale + offx,  sy = -y*scale + offy
        # We want (cx_w, cy_w) → (W/2, H/2)
        self.vp.scale = scale
        self.vp.offx  = W / 2 - cx_w * scale
        self.vp.offy  = H / 2 + cy_w * scale

        self.update()

    def _auto_fit_after_load(self):
        """Fit after a short delay so the widget has been resized first."""
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self.fit_in_view)

    def zoom_by(self, factor: float):
        """Zoom around the centre of the widget."""
        cx, cy = self.width() / 2, self.height() / 2
        new_scale = self.vp.scale * factor
        new_scale = max(ZOOM_MIN, min(ZOOM_MAX, new_scale))
        if new_scale != self.vp.scale:
            self.vp.zoom_at(new_scale / self.vp.scale, cx, cy)
        self.update()

    def set_mode(self, mode: str):
        self.mode = mode
        cursors = {
            MapMode.PAN:       Qt.CursorShape.OpenHandCursor,
            MapMode.SELECT:    Qt.CursorShape.ArrowCursor,
            MapMode.PICK_ROOM: Qt.CursorShape.CrossCursor,
            MapMode.CALIBRATE: Qt.CursorShape.CrossCursor,
            MapMode.PLACE:     Qt.CursorShape.CrossCursor,
        }
        self.setCursor(cursors.get(mode, Qt.CursorShape.ArrowCursor))

    def get_selected_segments(self):
        """Return list of selected sub-segment (x1,y1,x2,y2) tuples."""
        return list(self._selected_subsegments)

    def clear_selection(self):
        """Deselect all sub-segments."""
        self._selected_subsegments.clear()
        self.selection_changed.emit(self._selected_subsegments)
        self.update()

    def _reset_interaction_state(self):
        self._pan_active = False
        self.releaseMouse()
        self.set_mode(self.mode)

    # ── Hit-testing & sub-segment helpers ─────────────────────────────────────────

    @staticmethod
    def _dist_point_to_segment(px, py, x1, y1, x2, y2) -> float:
        """Shortest distance from point to segment."""
        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-12:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    @staticmethod
    def _intersect_t_on_A(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2):
        """
        Return the t-parameter on segment A where it intersects segment B,
        or None if there is no intersection.

        Uses a generous EPS to handle SVG coordinate rounding (coordinates
        are often rounded to 2-3 decimal places, creating tiny gaps at
        T-junctions that would otherwise be missed).
        """
        dax = ax2 - ax1;  day = ay2 - ay1
        dbx = bx2 - bx1;  dby = by2 - by1
        denom = dax * dby - day * dbx
        if abs(denom) < 1e-12:
            return None  # parallel / collinear
        dx = bx1 - ax1;  dy = by1 - ay1
        t = (dx * dby - dy * dbx) / denom
        s = (dx * day - dy * dax) / denom
        # Generous EPS: SVG coordinates often rounded to 2-3 decimal places,
        # leaving tiny gaps at T-junctions.
        EPS = 1e-4
        if -EPS <= t <= 1 + EPS and -EPS <= s <= 1 + EPS:
            return max(0.0, min(1.0, t))
        return None

    @staticmethod
    def _project_t_on_A(ax1, ay1, ax2, ay2, px, py):
        """
        Return the t-parameter on segment A for the closest point to (px, py),
        clamped to [0,1].  Used to snap near-endpoint touches onto segment A.
        """
        dx, dy = ax2 - ax1, ay2 - ay1
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-12:
            return 0.0
        return max(0.0, min(1.0, ((px - ax1) * dx + (py - ay1) * dy) / seg_len_sq))

    def _hit_test_segment(self, sx: float, sy: float) -> int:
        """
        Given screen position (sx, sy), return the index of the nearest segment
        within SELECT_HIT_PX pixels, or -1 if none.
        """
        best_idx = -1
        best_d   = SELECT_HIT_PX + 1
        wx, wy   = self.vp.screen_to_world(sx, sy)
        hit_world = SELECT_HIT_PX / self.vp.scale
        for i, (x1, y1, x2, y2) in enumerate(self._segments):
            d = self._dist_point_to_segment(wx, wy, x1, y1, x2, y2)
            if d < hit_world and d < best_d:
                best_d   = d
                best_idx = i
        return best_idx

    def _compute_subsegment(self, seg_idx: int, wx: float, wy: float
                            ) -> Tuple[float, float, float, float]:
        """
        Given a clicked world position (wx, wy) on segment seg_idx, return
        the sub-segment bounded by the nearest intersecting lines on either side.

        Algorithm:
          1. Find t-value of click along the segment (0=start, 1=end).
          2. Find all t-values where other segments cross this one.
          3. Add t=0 and t=1 as hard breaks.
          4. Sort and deduplicate break points.
          5. Pick the interval [t_left, t_right] that contains t_click.
          6. Return interpolated endpoints.
        """
        x1, y1, x2, y2 = self._segments[seg_idx]
        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq < 1e-12:
            return (x1, y1, x2, y2)  # degenerate segment

        t_click = max(0.0, min(1.0,
            ((wx - x1) * dx + (wy - y1) * dy) / seg_len_sq))

        deduped = self._segment_breaks(seg_idx)

        # Find the interval that brackets t_click
        t_left, t_right = 0.0, 1.0
        for i in range(len(deduped) - 1):
            if deduped[i] <= t_click <= deduped[i + 1]:
                t_left  = deduped[i]
                t_right = deduped[i + 1]
                break

        # Interpolate to world coordinates
        return (
            x1 + t_left  * dx,  y1 + t_left  * dy,
            x1 + t_right * dx,  y1 + t_right * dy,
        )

    def _segment_breaks(self, seg_idx: int) -> List[float]:
        """Return sorted t breakpoints for a segment split by intersections."""
        x1, y1, x2, y2 = self._segments[seg_idx]
        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-12:
            return [0.0, 1.0]

        seg_len = math.sqrt(seg_len_sq)
        snap_world = max(seg_len * 2e-3, 0.01)
        breaks = [0.0, 1.0]
        for j, (bx1, by1, bx2, by2) in enumerate(self._segments):
            if j == seg_idx:
                continue
            t = self._intersect_t_on_A(x1, y1, x2, y2, bx1, by1, bx2, by2)
            if t is not None:
                breaks.append(t)
                continue
            for px, py in ((bx1, by1), (bx2, by2)):
                d = self._dist_point_to_segment(px, py, x1, y1, x2, y2)
                if d < snap_world:
                    t_snap = self._project_t_on_A(x1, y1, x2, y2, px, py)
                    if snap_world / seg_len < t_snap < 1 - snap_world / seg_len:
                        breaks.append(t_snap)

        breaks.sort()
        deduped = [breaks[0]]
        for t in breaks[1:]:
            if abs(t - deduped[-1]) > 1e-9:
                deduped.append(t)
        return deduped

    def _all_atomic_subsegments(self) -> List[Tuple[float, float, float, float]]:
        """Split all imported segments at intersections and return unique pieces."""
        unique = []
        seen = set()

        def norm(seg):
            ax, ay, bx, by = seg
            p1 = (round(ax, 4), round(ay, 4))
            p2 = (round(bx, 4), round(by, 4))
            return (p1, p2) if p1 <= p2 else (p2, p1)

        for seg_idx, (x1, y1, x2, y2) in enumerate(self._segments):
            dx, dy = x2 - x1, y2 - y1
            breaks = self._segment_breaks(seg_idx)
            for i in range(len(breaks) - 1):
                t0, t1 = breaks[i], breaks[i + 1]
                if t1 - t0 <= 1e-9:
                    continue
                seg = (
                    x1 + t0 * dx, y1 + t0 * dy,
                    x1 + t1 * dx, y1 + t1 * dy,
                )
                if math.hypot(seg[2] - seg[0], seg[3] - seg[1]) < 1e-6:
                    continue
                key = norm(seg)
                if key in seen:
                    continue
                seen.add(key)
                unique.append(seg)
        return unique

    @staticmethod
    def _polygon_area(points: List[Tuple[float, float]]) -> float:
        area = 0.0
        for i in range(len(points)):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % len(points)]
            area += x1 * y2 - x2 * y1
        return area / 2.0

    @staticmethod
    def _point_in_polygon(px: float, py: float, poly: List[Tuple[float, float]]) -> bool:
        inside = False
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            if ((y1 > py) != (y2 > py)):
                x_cross = (x2 - x1) * (py - y1) / ((y2 - y1) or 1e-12) + x1
                if px < x_cross:
                    inside = not inside
        return inside

    def _detect_room_boundary(self, wx: float, wy: float) -> Optional[List[Tuple[float, float, float, float]]]:
        """Find the smallest closed face containing the clicked point."""
        atomic = self._all_atomic_subsegments()
        if len(atomic) < 3:
            return None

        vertex_ids = {}
        vertex_points = []
        edges = []

        def get_vid(x, y):
            key = (round(x, 4), round(y, 4))
            vid = vertex_ids.get(key)
            if vid is None:
                vid = len(vertex_points)
                vertex_ids[key] = vid
                vertex_points.append((x, y))
            return vid

        for seg in atomic:
            v1 = get_vid(seg[0], seg[1])
            v2 = get_vid(seg[2], seg[3])
            if v1 != v2:
                edges.append((v1, v2, seg))

        if len(edges) < 3:
            return None

        halfedges = []
        outgoing = {i: [] for i in range(len(vertex_points))}
        for edge_idx, (u, v, seg) in enumerate(edges):
            ux, uy = vertex_points[u]
            vx, vy = vertex_points[v]
            a_uv = math.atan2(vy - uy, vx - ux)
            a_vu = math.atan2(uy - vy, ux - vx)
            i1 = len(halfedges)
            halfedges.append({"origin": u, "dest": v, "rev": i1 + 1, "next": None, "seg": seg})
            i2 = len(halfedges)
            halfedges.append({"origin": v, "dest": u, "rev": i1, "next": None, "seg": seg})
            outgoing[u].append((a_uv, i1))
            outgoing[v].append((a_vu, i2))

        for vid, items in outgoing.items():
            items.sort(key=lambda item: item[0])
            outgoing[vid] = items

        pos_in_outgoing = {}
        for vid, items in outgoing.items():
            for idx, (_, hedge_idx) in enumerate(items):
                pos_in_outgoing[hedge_idx] = idx

        for hedge_idx, hedge in enumerate(halfedges):
            dest = hedge["dest"]
            rev_idx = hedge["rev"]
            out = outgoing[dest]
            if not out:
                continue
            rev_pos = pos_in_outgoing[rev_idx]
            next_idx = out[(rev_pos - 1) % len(out)][1]
            hedge["next"] = next_idx

        best_cycle = None
        best_area = None
        visited = set()

        for start_idx in range(len(halfedges)):
            if start_idx in visited:
                continue
            cycle = []
            seen_local = {}
            cur = start_idx
            while cur is not None and cur not in seen_local:
                seen_local[cur] = len(cycle)
                cycle.append(cur)
                cur = halfedges[cur]["next"]
            if cur is None or cur not in seen_local:
                continue
            loop = cycle[seen_local[cur]:]
            for idx in loop:
                visited.add(idx)
            points = [vertex_points[halfedges[idx]["origin"]] for idx in loop]
            if len(points) < 3:
                continue
            area = self._polygon_area(points)
            if abs(area) < 1e-4:
                continue
            if not self._point_in_polygon(wx, wy, points):
                continue
            if best_area is None or abs(area) < best_area:
                best_area = abs(area)
                best_cycle = loop

        if not best_cycle:
            return None

        boundary = []
        seen_seg = set()
        for idx in best_cycle:
            seg = halfedges[idx]["seg"]
            key = (
                round(min(seg[0], seg[2]), 4),
                round(min(seg[1], seg[3]), 4),
                round(max(seg[0], seg[2]), 4),
                round(max(seg[1], seg[3]), 4),
            )
            if key not in seen_seg:
                seen_seg.add(key)
                boundary.append(seg)
        return boundary

    @staticmethod
    def _subseg_equal(a, b, eps=1e-6) -> bool:
        """True if two sub-segments have the same endpoints within tolerance."""
        return (abs(a[0]-b[0]) < eps and abs(a[1]-b[1]) < eps and
                abs(a[2]-b[2]) < eps and abs(a[3]-b[3]) < eps)

    def _matching_existing_room(self, segments: List[Tuple[float, float, float, float]]):
        if not callable(self.room_lookup):
            return None
        for room in self.room_lookup():
            if segments_match(room.segments, segments):
                return room
        return None

    # Compatibility stubs
    def add_item(self, item, z: float = 30):    pass
    def remove_item(self, item):                 pass
    def clear_layer(self, z_min, z_max):         pass
    def scene_pos_of_click(self, ev: QMouseEvent) -> QPointF:
        return QPointF(ev.position())

    # ──────────────────────────────────────────────────────────────────────────
    # Painting
    # ──────────────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.fillRect(self.rect(), BG_COLOR)

        if not self._content_loaded:
            p.setPen(QColor("#555555"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Load a floor plan  (Load Image / Load Vector)")
            p.end()
            return

        vp = self.vp

        # ── Raster background ──────────────────────────────────────────────
        if self._bg_pixmap:
            pw_world = self._bg_pixmap.width()  / self._bg_scale
            ph_world = self._bg_pixmap.height() / self._bg_scale

            # Y-up CAD space: pixel top-left (row 0) = world (0, ph_world),
            # pixel bottom-right = world (pw_world, 0)
            sx0, sy0 = vp.world_to_screen(0,        ph_world)
            sx1, sy1 = vp.world_to_screen(pw_world, 0)

            dst = QRectF(min(sx0, sx1), min(sy0, sy1),
                         abs(sx1 - sx0), abs(sy1 - sy0))
            p.drawPixmap(dst.toRect(), self._bg_pixmap)

        # ── Vector segments: full pass (blue) ──────────────────────────────
        if self._segments:
            pen = QPen(LINE_COLOR)
            pen.setWidthF(1.5)
            pen.setCosmetic(True)
            p.setPen(pen)
            for x1, y1, x2, y2 in self._segments:
                sx1_s, sy1_s = vp.world_to_screen(x1, y1)
                sx2_s, sy2_s = vp.world_to_screen(x2, y2)
                p.drawLine(int(sx1_s), int(sy1_s), int(sx2_s), int(sy2_s))

        # ── Highlighted Room: Overlay (thick blue filled or lined) ───────────
        if hasattr(self, 'highlighted_room') and self.highlighted_room:
            # Draw a translucent blue overlay over the highlighted room
            brush = QBrush(QColor(74, 158, 255, 60))  # translucent blue
            r_pen = QPen(QColor(74, 158, 255))
            r_pen.setWidthF(2.0)
            r_pen.setCosmetic(True)
            p.setPen(r_pen)
            
            room_poly_local = self.highlighted_room.get_local_polygon()
            room_path_screen = QPainterPath()
            if not room_poly_local.isEmpty():
                first_pt = True
                for i in range(room_poly_local.count()):
                    pt = room_poly_local.at(i)
                    # Convert local to world, then world to screen
                    wx = pt.x() + self.highlighted_room.min_x
                    wy = pt.y() + self.highlighted_room.min_y
                    sx, sy = vp.world_to_screen(wx, wy)
                    if first_pt:
                        room_path_screen.moveTo(sx, sy)
                        first_pt = False
                    else:
                        room_path_screen.lineTo(sx, sy)
                room_path_screen.closeSubpath()
                p.fillPath(room_path_screen, brush)
                p.drawPath(room_path_screen)

        # ── Selected sub-segments: overlay (orange, thicker) ────────────────
        if self._selected_subsegments:
            sel_pen = QPen(SELECT_COLOR)
            sel_pen.setWidthF(3.5)
            sel_pen.setCosmetic(True)
            p.setPen(sel_pen)
            for x1, y1, x2, y2 in self._selected_subsegments:
                sx1_s, sy1_s = vp.world_to_screen(x1, y1)
                sx2_s, sy2_s = vp.world_to_screen(x2, y2)
                p.drawLine(int(sx1_s), int(sy1_s), int(sx2_s), int(sy2_s))

        p.end()

    # ──────────────────────────────────────────────────────────────────────────
    # Mouse events
    # ──────────────────────────────────────────────────────────────────────────
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            wx, wy = self.vp.screen_to_world(event.position().x(), event.position().y())
            self.map_double_clicked.emit(wx, wy)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and
            self.mode == MapMode.PAN
        ):
            self._pan_active = True
            self._pan_last   = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        sp = event.position()

        if self.mode == MapMode.SELECT:
            if event.button() == Qt.MouseButton.LeftButton:
                # Compute the sub-segment bounded by intersecting lines and toggle it
                idx = self._hit_test_segment(sp.x(), sp.y())
                if idx >= 0:
                    wx, wy = self.vp.screen_to_world(sp.x(), sp.y())
                    subseg = self._compute_subsegment(idx, wx, wy)
                    # Toggle: deselect if already present, else add
                    for i, ss in enumerate(self._selected_subsegments):
                        if self._subseg_equal(ss, subseg):
                            self._selected_subsegments.pop(i)
                            self.selection_changed.emit(self._selected_subsegments)
                            self.update()
                            event.accept()
                            return
                    self._selected_subsegments.append(subseg)
                    self.selection_changed.emit(self._selected_subsegments)
                    self.update()
                event.accept()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                if self._selected_subsegments:
                    existing_room = self._matching_existing_room(self._selected_subsegments)
                    if existing_room is not None:
                        current_mode = self.mode
                        self._reset_interaction_state()
                        self.clear_selection()
                        self.status_message_requested.emit(
                            f"Room already defined: {existing_room.name}"
                        )
                        self.mode_change_requested.emit(current_mode)
                        event.accept()
                        return
                    menu = QMenu(self)
                    act_designate = menu.addAction("Designate Room from Selection")
                    
                    # Show menu at cursor position
                    global_pos = event.globalPosition().toPoint()
                    self._reset_interaction_state()
                    action = menu.exec(global_pos)
                    
                    if action == act_designate:
                        name, ok = QInputDialog.getText(
                            self, "Designate Room", "Enter room name/ID:"
                        )
                        if ok and name.strip():
                            # Emits a copy of the selected subsegments
                            self.room_designated.emit(name.strip(), list(self._selected_subsegments))
                            self.clear_selection()
                event.accept()
                return
        elif self.mode == MapMode.PICK_ROOM:
            if event.button() == Qt.MouseButton.LeftButton:
                wx, wy = self.vp.screen_to_world(sp.x(), sp.y())
                if callable(self.room_lookup):
                    for room in self.room_lookup():
                        lx, ly = room.world_to_local(wx, wy)
                        if room.contains_local_point(lx, ly):
                            current_mode = self.mode
                            self._reset_interaction_state()
                            self.status_message_requested.emit(
                                f"Room already defined: {room.name}"
                            )
                            self.mode_change_requested.emit(current_mode)
                            event.accept()
                            return
                boundary = self._detect_room_boundary(wx, wy)
                if not boundary:
                    self._reset_interaction_state()
                    self.status_message_requested.emit(
                        "Could not find a closed room boundary at that point"
                    )
                    event.accept()
                    return
                existing_room = self._matching_existing_room(boundary)
                if existing_room is not None:
                    current_mode = self.mode
                    self._reset_interaction_state()
                    self.status_message_requested.emit(
                        f"Room already defined: {existing_room.name}"
                    )
                    self.mode_change_requested.emit(current_mode)
                    event.accept()
                    return
                self._selected_subsegments = list(boundary)
                self.selection_changed.emit(self._selected_subsegments)
                self.update()
                name, ok = QInputDialog.getText(
                    self, "Designate Room", "Enter room name/ID:"
                )
                if ok and name.strip():
                    self.room_designated.emit(name.strip(), list(self._selected_subsegments))
                self.clear_selection()
                event.accept()
                return

        elif self.mode == MapMode.CALIBRATE:
            if not self.has_image():
                self.no_image_warning.emit()
            else:
                self.calibration_click.emit(sp)
        elif self.mode == MapMode.PLACE:
            if not self.has_image():
                self.no_image_warning.emit()
            else:
                self.anchor_placed.emit(sp)
        
        event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._pan_active:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            self.vp.offx += delta.x()
            self.vp.offy += delta.y()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._pan_active and event.button() in (
            Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton
        ):
            self._pan_active = False
            self.set_mode(self.mode)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ──────────────────────────────────────────────────────────────────────────
    # Scroll / zoom
    # ──────────────────────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent):
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else (1 / 1.15)
        pos = event.position()
        new_scale = self.vp.scale * factor
        new_scale = max(ZOOM_MIN, min(ZOOM_MAX, new_scale))
        if new_scale != self.vp.scale:
            self.vp.zoom_at(new_scale / self.vp.scale, pos.x(), pos.y())
        self.update()
        event.accept()

    # ──────────────────────────────────────────────────────────────────────────
    # Keyboard
    # ──────────────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F:
            self.fit_in_view()
        elif event.key() == Qt.Key.Key_Plus:
            self.zoom_by(1.2)
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom_by(1 / 1.2)
        elif event.key() == Qt.Key.Key_Escape:
            self.clear_selection()
        else:
            super().keyPressEvent(event)

    # ──────────────────────────────────────────────────────────────────────────
    # Resize
    # ──────────────────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-fit when the widget is first shown (vp still at default)
        if self._content_loaded and self.vp.scale == 60.0:
            self.fit_in_view()
