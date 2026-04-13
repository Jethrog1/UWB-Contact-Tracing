"""
cad_engine.py — Headless CAD geometry engine
=============================================
Pure-Python version of the 2DLCAD FloorPlanCAD logic.
All Tkinter dependencies removed; state is exposed as a plain dict
that serialises directly to the TypeScript CADState interface.

Dialog replacement: when the engine needs a float from the user it
emits a pending_dialog entry in the state dict.  The WebSocket server
delivers that to the client, which pops a modal and calls
handle_command({ type: "dialog_response", request_id, value }).
"""

import math
import uuid
from copy import deepcopy
from typing import Optional

EPS = 1e-9


# ══════════════════════════════════════════════════════════════════
# Core geometry types
# ══════════════════════════════════════════════════════════════════

class Viewport:
    __slots__ = ("scale", "offx", "offy")

    def __init__(self):
        self.scale = 60.0
        self.offx  = 0.0
        self.offy  = 0.0

    def world_to_screen(self, x, y):
        return x * self.scale + self.offx, y * self.scale + self.offy

    def screen_to_world(self, sx, sy):
        return (sx - self.offx) / self.scale, (sy - self.offy) / self.scale

    @staticmethod
    def zoom_at_vp(vp, factor, anchor_sx, anchor_sy):
        wx, wy   = vp.screen_to_world(anchor_sx, anchor_sy)
        vp.scale = max(1.0, min(10000.0, vp.scale * float(factor)))
        vp.offx  = anchor_sx - wx * vp.scale
        vp.offy  = anchor_sy - wy * vp.scale

    def to_dict(self):
        return {"scale": self.scale, "offx": self.offx, "offy": self.offy}


class Line:
    __slots__ = ("id", "x1", "y1", "x2", "y2", "color")

    def __init__(self, x1, y1, x2, y2, color="#4A9EFF", line_id=None):
        self.id    = line_id or str(uuid.uuid4())
        self.x1    = float(x1)
        self.y1    = float(y1)
        self.x2    = float(x2)
        self.y2    = float(y2)
        self.color = color

    def length(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def distance_to_point(self, px, py):
        dx = self.x2 - self.x1;  dy = self.y2 - self.y1
        if abs(dx) < EPS and abs(dy) < EPS:
            return math.hypot(px - self.x1, py - self.y1)
        t = ((px - self.x1) * dx + (py - self.y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        return math.hypot(px - self.x1 - t * dx, py - self.y1 - t * dy)

    def closest_point(self, px, py):
        dx = self.x2 - self.x1;  dy = self.y2 - self.y1
        if abs(dx) < EPS and abs(dy) < EPS:
            return self.x1, self.y1, 0.0
        t = ((px - self.x1) * dx + (py - self.y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        return self.x1 + t * dx, self.y1 + t * dy, t

    def to_dict(self):
        return {
            "id": self.id, "x1": self.x1, "y1": self.y1,
            "x2": self.x2, "y2": self.y2, "color": self.color,
        }


# ══════════════════════════════════════════════════════════════════
# CAD Engine
# ══════════════════════════════════════════════════════════════════

class CADEngine:
    """
    Headless geometry state machine.
    All public entry-points are handle_command(dict) → state_dict.
    """

    def __init__(self, canvas_w: int = 800, canvas_h: int = 600):
        self.vp = Viewport()
        self._canvas_w = canvas_w
        self._canvas_h = canvas_h

        # Geometry
        self.lines: list[Line] = []
        # fixed_lengths keyed by line.id
        self.fixed_lengths: dict[str, dict] = {}        # {id: {"len":float, "label":[x,y]}}
        self.angle_constraints: list[dict] = []
        self.distance_constraints: list[dict] = []

        # Selection / hover  (store ids, not object refs)
        self.selected_id: Optional[str] = None
        self.multi_selected_ids: set[str] = set()
        self.hovered_id: Optional[str] = None

        # Tool state
        self.tool_mode: str = "cursor"
        self.drawing_line: bool = False
        self.temp_line_start: Optional[tuple] = None
        self.paste_active: bool = False
        self.rotate_active: bool = False
        self.trim_active: bool = False

        # Cursor / snapping
        self.cursor_world: tuple = (0.0, 0.0)
        self.cursor_world_snapped: tuple = (0.0, 0.0)
        self.snap_hint: Optional[dict] = None
        self.alignment_guides: list = []
        self.parallel_guides: list = []
        self.equal_length_guides: list = []

        # Vertex mode
        self._vertex_hover: Optional[tuple] = None
        self._vertex_drag_active: bool = False
        self._vertex_drag_refs: list = []
        self._vertex_drag_start_mouse: tuple = (0.0, 0.0)
        self._vertex_drag_start_pos: tuple = (0.0, 0.0)
        self._vertex_temp: bool = False

        # Line drag
        self._dragging_line: Optional[Line] = None
        self._dragging_point: Optional[str] = None
        self._drag_offset: tuple = (0.0, 0.0)

        # Group drag
        self._group_drag_active: bool = False
        self._group_drag_start: tuple = (0.0, 0.0)
        self._group_drag_snapshot: list = []

        # Pan
        self._pan_active: bool = False
        self._pan_last: tuple = (0, 0)

        # Feature flags
        self.manipulate_line: bool = False
        self.snap_axis: bool = False
        self.line_match: bool = False
        self.disable_vpoint: bool = False

        # Angle snap
        self.angle_snap_values: list[str] = ["", "", "", ""]
        self.angle_snap_tol_deg: float = 6.0

        # Tolerances
        self.snap_dist_endpoint: float = 0.20
        self.snap_dist_line: float = 0.15
        self.snap_align_threshold: float = 0.12
        self.snap_axis_distance: float = 0.35
        self.snap_axis_intersection_tol: float = 0.55
        self.snap_equal_len_tol: float = 0.20
        self.hit_threshold: float = 0.15

        # Dimension tool state
        self._dim_first_line: Optional[Line] = None
        self._dim_first_kind: Optional[str] = None  # "line_a"
        self._dim_awaiting: Optional[str] = None    # "length"|"angle"|"distance"

        # Copy/paste clipboard
        self._clipboard: list[dict] = []

        # Undo/redo
        self._undo_stack: list = []
        self._redo_stack: list = []

        # Pending dialog
        self.pending_dialog: Optional[dict] = None
        self._pending_dialog_context: Optional[dict] = None

        # Last error message
        self.last_error: Optional[str] = None

        # Solver drag context
        self._solver_drag_lines: set = set()

        self._initialize_view()

    def _initialize_view(self):
        # Center on origin
        self.vp.offx = self._canvas_w / 2.0
        self.vp.offy = self._canvas_h / 2.0

    # ──────────────────────────────────────────────────────────────
    # Public dispatch
    # ──────────────────────────────────────────────────────────────

    def handle_command(self, cmd: dict) -> dict:
        t = cmd.get("type", "")
        try:
            if   t == "mouse_down":      self._on_mouse_down(cmd)
            elif t == "mouse_move":      self._on_mouse_move(cmd)
            elif t == "mouse_up":        self._on_mouse_up(cmd)
            elif t == "double_click":    self._on_double_click(cmd)
            elif t == "right_click":     self._on_right_click(cmd)
            elif t == "wheel":           self._on_wheel(cmd)
            elif t == "key_press":       self._on_key_press(cmd)
            elif t == "tool_change":     self._set_mode(cmd["tool"])
            elif t == "viewport_resize": self._on_resize(cmd)
            elif t == "dialog_response": self._on_dialog_response(cmd)
            elif t == "toggle_flag":     self._toggle_flag(cmd)
            elif t == "angle_snap_set":  self._set_angle_snap(cmd)
            elif t == "undo":            self._undo()
            elif t == "redo":            self._redo()
            elif t == "copy":            self._copy()
            elif t == "paste":           self._paste()
            elif t == "delete":          self._delete()
            elif t == "escape":          self._escape()
            elif t == "zoom_in":         self._zoom_in()
            elif t == "zoom_out":        self._zoom_out()
            elif t == "zoom_reset":      self._zoom_reset()
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
        return self.to_state_dict()

    # ──────────────────────────────────────────────────────────────
    # State serialisation
    # ──────────────────────────────────────────────────────────────

    def to_state_dict(self) -> dict:
        def guide_to_dict(g):
            return {"x1": g[0], "y1": g[1], "x2": g[2], "y2": g[3], "type": g[4]}

        snap = None
        if self.snap_hint:
            snap = {"kind": self.snap_hint[0], "x": self.snap_hint[1], "y": self.snap_hint[2]}

        # Build fixed_lengths with string ids
        fixed_lengths_out = {}
        for lid, meta in self.fixed_lengths.items():
            fixed_lengths_out[lid] = {
                "len": meta["len"],
                "label": meta.get("label"),
            }

        # Build angle constraints (convert line refs to ids)
        angle_out = []
        for i, ac in enumerate(self.angle_constraints):
            angle_out.append({
                "idx": i,
                "line_a_id": ac["a"].id,
                "line_b_id": ac["b"].id,
                "vx": ac["vx"], "vy": ac["vy"],
                "deg": ac["deg"],
                "side": ac.get("side", 1),
                "off": ac.get("off", 30),
            })

        dist_out = []
        for i, dc in enumerate(self.distance_constraints):
            dist_out.append({
                "idx": i,
                "line_a_id": dc["a"].id,
                "line_b_id": dc["b"].id,
                "dist": dc["dist"],
                "Pa": list(dc["Pa"]) if dc.get("Pa") else None,
                "Pb": list(dc["Pb"]) if dc.get("Pb") else None,
                "label": list(dc["label"]) if dc.get("label") else None,
            })

        state: dict = {
            # Geometry
            "lines": [ln.to_dict() for ln in self.lines],
            "fixed_lengths": fixed_lengths_out,
            "angle_constraints": angle_out,
            "distance_constraints": dist_out,

            # Selection / hover
            "selected_id": self.selected_id,
            "multi_selected_ids": list(self.multi_selected_ids),
            "hovered_id": self.hovered_id,

            # Tool state
            "tool_mode": self.tool_mode,
            "drawing_line": self.drawing_line,
            "temp_line_start": list(self.temp_line_start) if self.temp_line_start else None,
            "paste_active": self.paste_active,
            "rotate_active": self.rotate_active,
            "trim_active": self.trim_active,
            "vertex_hover": list(self._vertex_hover) if self._vertex_hover else None,

            # Cursor / snapping
            "cursor_world": list(self.cursor_world),
            "cursor_world_snapped": list(self.cursor_world_snapped),
            "snap_hint": snap,
            "alignment_guides": [guide_to_dict(g) for g in self.alignment_guides],
            "parallel_guides": self.parallel_guides,
            "equal_length_guides": self.equal_length_guides,

            # Viewport
            "vp": self.vp.to_dict(),

            # Feature flags
            "manipulate_line": self.manipulate_line,
            "snap_axis": self.snap_axis,
            "line_match": self.line_match,
            "disable_vpoint": self.disable_vpoint,

            # Angle snap
            "angle_snap_values": list(self.angle_snap_values),

            # Dimension selection (for copy/paste)
            "selected_dim_kinds": [],
        }

        if self.pending_dialog:
            state["pending_dialog"] = self.pending_dialog

        if self.last_error:
            state["last_error"] = self.last_error

        return state

    # ──────────────────────────────────────────────────────────────
    # Undo / Redo
    # ──────────────────────────────────────────────────────────────

    def _snapshot(self):
        """Return a lightweight serialisable snapshot of mutable geometry."""
        return {
            "lines": [(ln.id, ln.x1, ln.y1, ln.x2, ln.y2, ln.color) for ln in self.lines],
            "fixed_lengths": {
                lid: {"len": m["len"], "label": m.get("label")}
                for lid, m in self.fixed_lengths.items()
            },
            # angle/distance constraints reference Line objects by id — re-resolve on restore
            "angle_constraints": [
                {**{k: v for k, v in ac.items() if k not in ("a", "b")},
                 "a_id": ac["a"].id, "b_id": ac["b"].id}
                for ac in self.angle_constraints
            ],
            "distance_constraints": [
                {**{k: v for k, v in dc.items() if k not in ("a", "b")},
                 "a_id": dc["a"].id, "b_id": dc["b"].id}
                for dc in self.distance_constraints
            ],
        }

    def _restore_snapshot(self, snap):
        # Rebuild lines
        id_map: dict[str, Line] = {}
        new_lines = []
        for lid, x1, y1, x2, y2, color in snap["lines"]:
            ln = Line(x1, y1, x2, y2, color, line_id=lid)
            new_lines.append(ln)
            id_map[lid] = ln
        self.lines = new_lines

        # Prune selection/hover if lines disappeared
        if self.selected_id not in id_map:
            self.selected_id = None
        self.multi_selected_ids = {i for i in self.multi_selected_ids if i in id_map}
        if self.hovered_id not in id_map:
            self.hovered_id = None
        if self._dragging_line and self._dragging_line.id not in id_map:
            self._dragging_line = None

        # Fixed lengths
        self.fixed_lengths = {}
        for lid, meta in snap["fixed_lengths"].items():
            if lid in id_map:
                self.fixed_lengths[lid] = meta

        # Angle constraints
        self.angle_constraints = []
        for ac in snap["angle_constraints"]:
            a = id_map.get(ac["a_id"])
            b = id_map.get(ac["b_id"])
            if a and b:
                entry = {k: v for k, v in ac.items() if k not in ("a_id", "b_id")}
                entry["a"] = a;  entry["b"] = b
                self.angle_constraints.append(entry)

        # Distance constraints
        self.distance_constraints = []
        for dc in snap["distance_constraints"]:
            a = id_map.get(dc["a_id"])
            b = id_map.get(dc["b_id"])
            if a and b:
                entry = {k: v for k, v in dc.items() if k not in ("a_id", "b_id")}
                entry["a"] = a;  entry["b"] = b
                self.distance_constraints.append(entry)

    def _push_undo(self):
        self._undo_stack.append(self._snapshot())
        self._redo_stack.clear()
        if len(self._undo_stack) > 80:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self._restore_snapshot(self._undo_stack.pop())

    def _redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self._restore_snapshot(self._redo_stack.pop())

    # ──────────────────────────────────────────────────────────────
    # Lookup helpers
    # ──────────────────────────────────────────────────────────────

    def _line_by_id(self, lid: str) -> Optional[Line]:
        for ln in self.lines:
            if ln.id == lid:
                return ln
        return None

    def _vkey(self, x, y):
        return (round(x, 6), round(y, 6))

    def _update_zoom_tolerances(self):
        s = max(1.0, self.vp.scale)
        self.snap_dist_endpoint  = max(0.05, 8.0  / s)
        self.snap_dist_line      = max(0.04, 6.0  / s)
        self.hit_threshold       = max(0.05, 10.0 / s)
        self.snap_align_threshold = max(0.04, 8.0 / s)

    # ──────────────────────────────────────────────────────────────
    # Snapping
    # ──────────────────────────────────────────────────────────────

    def _get_angle_snap_list(self):
        vals = []
        for s in self.angle_snap_values:
            s = (s or "").strip()
            if not s:
                continue
            try:
                d = float(s)
            except ValueError:
                continue
            vals.append(d % 360.0)
        out = []
        seen: set = set()
        for d in vals:
            k = round(d, 6)
            if k not in seen:
                seen.add(k)
                out.append(d)
        return out

    def _wrap_pi(self, a):
        return math.atan2(math.sin(a), math.cos(a))

    def _angle_snap_if_close(self, x0, y0, x1, y1):
        angles = self._get_angle_snap_list()
        if not angles:
            return x1, y1, False
        dx = x1 - x0;  dy = y1 - y0
        r = math.hypot(dx, dy)
        if r < 1e-9:
            return x1, y1, False
        a = math.atan2(-dy, dx)
        tol = math.radians(self.angle_snap_tol_deg)
        best_theta = None;  best_err = 1e18
        for deg in angles:
            th = math.radians(deg)
            for cand in (th, th + math.pi):
                err = abs(self._wrap_pi(a - cand))
                if err < best_err:
                    best_err = err;  best_theta = cand
        if best_theta is None or best_err > tol:
            return x1, y1, False
        return x0 + r * math.cos(best_theta), y0 - r * math.sin(best_theta), True

    def _find_snap(self, wx, wy, ignore_line=None, ignore_points=None):
        if ignore_points is None:
            ignore_points = set()

        self.alignment_guides = []
        self.parallel_guides  = []
        self.equal_length_guides = []

        # Endpoint snap
        best_ep = None;  best_ep_d = 1e18
        all_endpoints = []
        for ln in self.lines:
            if ignore_line is not None and ln is ignore_line:
                continue
            for px, py in ((ln.x1, ln.y1), (ln.x2, ln.y2)):
                if self._vkey(px, py) not in ignore_points:
                    all_endpoints.append((px, py))
                    d = math.hypot(wx - px, wy - py)
                    if d < best_ep_d:
                        best_ep_d = d;  best_ep = (px, py)

        if best_ep and best_ep_d <= self.snap_dist_endpoint:
            return best_ep[0], best_ep[1], "endpoint"

        # Axis alignment snap
        if self.snap_axis:
            best_x_align = None;  best_x_d = 1e18
            best_y_align = None;  best_y_d = 1e18
            thr = self.snap_align_threshold
            for ep in all_endpoints:
                ex, ey = ep
                if abs(wx - ex) < thr and abs(wx - ex) < best_x_d:
                    best_x_d = abs(wx - ex);  best_x_align = (ex, ep)
                if abs(wy - ey) < thr and abs(wy - ey) < best_y_d:
                    best_y_d = abs(wy - ey);  best_y_align = (ey, ep)
            if best_x_align or best_y_align:
                fx = best_x_align[0] if best_x_align else wx
                fy = best_y_align[0] if best_y_align else wy
                if best_x_align:
                    sep = best_x_align[1]
                    self.alignment_guides.append((sep[0], sep[1], fx, wy, "x"))
                if best_y_align:
                    sep = best_y_align[1]
                    self.alignment_guides.append((sep[0], sep[1], wx, fy, "y"))
                return fx, fy, "alignment"

        # Line snap
        best_p = None;  best_ld = 1e18
        for ln in self.lines:
            if ignore_line is not None and ln is ignore_line:
                continue
            px, py, _ = ln.closest_point(wx, wy)
            d = math.hypot(wx - px, wy - py)
            if d < best_ld:
                best_ld = d;  best_p = (px, py)

        if best_p and best_ld <= self.snap_dist_line:
            return best_p[0], best_p[1], "line"

        return wx, wy, None

    def _apply_snap_for_cursor(self, wx, wy, ignore_line=None, ignore_points=None):
        sx, sy, kind = self._find_snap(wx, wy, ignore_line=ignore_line, ignore_points=ignore_points)
        if kind == "endpoint":
            if self.drawing_line and self.temp_line_start:
                ax, ay, snapped = self._angle_snap_if_close(
                    self.temp_line_start[0], self.temp_line_start[1], sx, sy)
                if snapped:
                    sx, sy = ax, ay
            self.cursor_world_snapped = (sx, sy)
            self.snap_hint = ("endpoint", sx, sy)
        elif kind == "line":
            self.cursor_world_snapped = (sx, sy)
            self.snap_hint = ("line", sx, sy)
        elif kind == "alignment":
            self.cursor_world_snapped = (sx, sy)
            self.snap_hint = None
        else:
            # angle snap on free cursor
            if self.drawing_line and self.temp_line_start:
                ax, ay, snapped = self._angle_snap_if_close(
                    self.temp_line_start[0], self.temp_line_start[1], wx, wy)
                if snapped:
                    wx, wy = ax, ay
            self.cursor_world_snapped = (wx, wy)
            self.snap_hint = None
        return self.cursor_world_snapped

    # ──────────────────────────────────────────────────────────────
    # Vertex helpers
    # ──────────────────────────────────────────────────────────────

    def _find_vertex_near(self, wx, wy):
        """Return (vx, vy) of closest vertex within snap distance, or None."""
        best = None;  best_d = 1e18
        for ln in self.lines:
            for px, py in ((ln.x1, ln.y1), (ln.x2, ln.y2)):
                d = math.hypot(wx - px, wy - py)
                if d < best_d:
                    best_d = d;  best = (px, py)
        if best and best_d <= self.snap_dist_endpoint * 1.5:
            return best
        return None

    def _collect_vertex_refs(self, vx, vy):
        """Return list of (Line, "start"|"end") for all endpoints at (vx,vy)."""
        refs = []
        for ln in self.lines:
            if math.hypot(ln.x1 - vx, ln.y1 - vy) < EPS * 1000:
                refs.append((ln, "start"))
            elif math.hypot(ln.x2 - vx, ln.y2 - vy) < EPS * 1000:
                refs.append((ln, "end"))
        return refs

    def _set_refs_vertex(self, refs, x, y):
        for ln, which in refs:
            if which == "start":
                ln.x1 = x;  ln.y1 = y
            else:
                ln.x2 = x;  ln.y2 = y

    def _vertex_candidate_positions(self, raw_x, raw_y):
        sx, sy, kind = self._find_snap(raw_x, raw_y)
        if kind == "endpoint":
            return sx, sy
        ax, ay, snapped = self._angle_snap_if_close(
            self._vertex_drag_start_pos[0], self._vertex_drag_start_pos[1], raw_x, raw_y)
        if snapped:
            return ax, ay
        return raw_x, raw_y

    def _weld_propagate_vertex_move(self, old_x, old_y, new_x, new_y, ignore_line=None):
        """Move all other endpoints coincident with (old_x, old_y) to (new_x, new_y)."""
        tol = EPS * 1000
        for ln in self.lines:
            if ignore_line is not None and ln is ignore_line:
                continue
            if math.hypot(ln.x1 - old_x, ln.y1 - old_y) < tol:
                ln.x1 = new_x;  ln.y1 = new_y
            if math.hypot(ln.x2 - old_x, ln.y2 - old_y) < tol:
                ln.x2 = new_x;  ln.y2 = new_y

    def _is_protected_vertex(self, vx, vy):
        """Returns True if vertex is shared by 3+ lines."""
        count = 0
        for ln in self.lines:
            if math.hypot(ln.x1 - vx, ln.y1 - vy) < EPS * 1000:
                count += 1
            if math.hypot(ln.x2 - vx, ln.y2 - vy) < EPS * 1000:
                count += 1
            if count >= 3:
                return True
        return False

    # ──────────────────────────────────────────────────────────────
    # Tool mode
    # ──────────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self.tool_mode = mode
        if mode != "line":
            self.drawing_line = False
            self.temp_line_start = None
        self.alignment_guides = []
        self.parallel_guides  = []
        self.equal_length_guides = []
        self._vertex_temp  = False
        self._vertex_drag_active = False
        self._vertex_hover = None
        self._vertex_drag_refs = []
        if mode == "vertex":
            self._dragging_line   = None
            self._dragging_point  = None
            self._pan_active      = False
            self.selected_id      = None
            self.hovered_id       = None
        if mode != "dim":
            self._dim_first_line  = None
            self._dim_first_kind  = None
            self._dim_awaiting    = None

    # ──────────────────────────────────────────────────────────────
    # Prune
    # ──────────────────────────────────────────────────────────────

    def _prune_zero_lines(self):
        keep = {ln for ln in self.lines if ln.length() > 1e-6}
        self.lines = [ln for ln in self.lines if ln in keep]
        dead = {ln.id for ln in self.lines if ln not in keep}
        if self.selected_id in dead:
            self.selected_id = None
        self.multi_selected_ids -= dead
        if self.hovered_id in dead:
            self.hovered_id = None

    # ──────────────────────────────────────────────────────────────
    # Simple constraint solver (rigid enforcement, iterative)
    # ──────────────────────────────────────────────────────────────

    def _solve_constraints(self, iters=3):
        drag_ids = {ln.id for ln in self._solver_drag_lines}

        for _ in range(iters):
            # Fixed length
            for lid, meta in self.fixed_lengths.items():
                ln = self._line_by_id(lid)
                if not ln:
                    continue
                L = float(meta["len"])
                dx = ln.x2 - ln.x1;  dy = ln.y2 - ln.y1
                d = math.hypot(dx, dy)
                if d < 1e-9:
                    continue
                ux, uy = dx / d, dy / d
                mid_x = (ln.x1 + ln.x2) / 2
                mid_y = (ln.y1 + ln.y2) / 2
                locked = ln.id in drag_ids
                if locked:
                    # Fix the other end
                    ln.x2 = ln.x1 + ux * L
                    ln.y2 = ln.y1 + uy * L
                else:
                    # Symmetric
                    ln.x1 = mid_x - ux * L / 2;  ln.y1 = mid_y - uy * L / 2
                    ln.x2 = mid_x + ux * L / 2;  ln.y2 = mid_y + uy * L / 2
                # Update label
                if meta.get("label") is None:
                    meta["label"] = [
                        (ln.x1 + ln.x2) / 2,
                        (ln.y1 + ln.y2) / 2 - 0.3
                    ]

    # ──────────────────────────────────────────────────────────────
    # Mouse events
    # ──────────────────────────────────────────────────────────────

    def _on_mouse_down(self, cmd: dict):
        sx, sy = cmd["x"], cmd["y"]
        ctrl   = bool(cmd.get("ctrl", False))
        shift  = bool(cmd.get("shift", False))
        button = cmd.get("button", 0)

        if button != 0:
            return

        wx, wy = self.vp.screen_to_world(sx, sy)
        self.cursor_world = (wx, wy)

        # ── Dim tool ────────────────────────────────────────────
        if self.tool_mode == "dim":
            self._dim_on_mouse_down(wx, wy)
            return

        # ── Shift + cursor = temp vertex manipulate ──────────────
        if self.tool_mode == "cursor" and shift:
            hit = self._find_vertex_near(wx, wy)
            if hit:
                vx, vy = hit
                refs = self._collect_vertex_refs(vx, vy)
                if refs:
                    self._push_undo()
                    self._vertex_temp = True
                    self.tool_mode = "vertex"
                    self._vertex_drag_active = True
                    self._vertex_drag_refs = refs
                    self._vertex_drag_start_mouse = (wx, wy)
                    self._vertex_drag_start_pos   = (vx, vy)
                    self._vertex_hover = (vx, vy)
                    self.snap_hint = ("endpoint", vx, vy)
                    return

        # ── Vertex mode ──────────────────────────────────────────
        if self.tool_mode == "vertex":
            hit = self._find_vertex_near(wx, wy)
            if hit is None:
                return
            vx, vy = hit
            refs = self._collect_vertex_refs(vx, vy)
            if not refs:
                return
            self._push_undo()
            self._vertex_drag_active = True
            self._vertex_drag_refs = refs
            self._vertex_drag_start_mouse = (wx, wy)
            self._vertex_drag_start_pos   = (vx, vy)
            self._vertex_hover = (vx, vy)
            self.snap_hint = ("endpoint", vx, vy)
            return

        # ── Line tool ────────────────────────────────────────────
        if self.tool_mode == "line":
            self._apply_snap_for_cursor(wx, wy)
            sx2, sy2 = self.cursor_world_snapped
            if not self.drawing_line:
                self.drawing_line = True
                self.temp_line_start = (sx2, sy2)
            else:
                x1, y1 = self.temp_line_start
                x2, y2 = sx2, sy2
                if math.hypot(x2 - x1, y2 - y1) > 1e-6:
                    self._push_undo()
                    new_ln = Line(x1, y1, x2, y2)
                    self.lines.append(new_ln)
                    # Chain: start next line from this endpoint
                    self.temp_line_start = (x2, y2)
            return

        # ── Cursor mode ──────────────────────────────────────────
        if self.tool_mode == "cursor":
            ht = self.hit_threshold

            # Ctrl+click: toggle multi-select
            if ctrl:
                hit_ln = self._hit_test(wx, wy)
                if hit_ln:
                    if hit_ln.id in self.multi_selected_ids:
                        self.multi_selected_ids.discard(hit_ln.id)
                    else:
                        self.multi_selected_ids.add(hit_ln.id)
                    if not self.multi_selected_ids:
                        self.selected_id = None
                return

            # Group drag check
            if self.multi_selected_ids:
                for lid in self.multi_selected_ids:
                    ln = self._line_by_id(lid)
                    if ln and ln.distance_to_point(wx, wy) < ht:
                        self._push_undo()
                        self._group_drag_active = True
                        self._group_drag_start = (wx, wy)
                        multi_lines = [self._line_by_id(i) for i in self.multi_selected_ids]
                        self._group_drag_snapshot = [
                            (l, l.x1, l.y1, l.x2, l.y2) for l in multi_lines if l
                        ]
                        return

            # Hit test
            hit_ln, hit_kind = self._hit_test_with_kind(wx, wy)

            if hit_ln:
                if hit_kind in ("start", "end"):
                    vx = hit_ln.x1 if hit_kind == "start" else hit_ln.x2
                    vy = hit_ln.y1 if hit_kind == "start" else hit_ln.y2
                    if (not self.manipulate_line) or self._is_protected_vertex(vx, vy):
                        refs = self._collect_vertex_refs(vx, vy)
                        if refs and len(refs) > 1:
                            self._push_undo()
                            self._vertex_temp = True
                            self.tool_mode = "vertex"
                            self._vertex_drag_active = True
                            self._vertex_drag_refs = refs
                            self._vertex_drag_start_mouse = (wx, wy)
                            self._vertex_drag_start_pos   = (vx, vy)
                            self._vertex_hover = (vx, vy)
                            self.snap_hint = ("endpoint", vx, vy)
                            return

                self._push_undo()
                self.multi_selected_ids.clear()
                self.selected_id = hit_ln.id
                self._dragging_line  = hit_ln
                self._dragging_point = hit_kind
                if hit_kind == "body":
                    self._drag_offset = (wx - hit_ln.x1, wy - hit_ln.y1)
                return

            # Empty click: clear + start pan
            self.selected_id = None
            self.multi_selected_ids.clear()
            self._pan_active = True
            self._pan_last   = (sx, sy)

    def _on_mouse_move(self, cmd: dict):
        sx, sy = cmd["x"], cmd["y"]
        wx, wy = self.vp.screen_to_world(sx, sy)
        self.cursor_world = (wx, wy)
        self._apply_snap_for_cursor(wx, wy)

        # Dim tool cursor feedback
        if self.tool_mode == "dim":
            self.hovered_id = None
            return

        # Group drag
        if self._group_drag_active and self._group_drag_snapshot:
            dx = wx - self._group_drag_start[0]
            dy = wy - self._group_drag_start[1]
            for ln, ox1, oy1, ox2, oy2 in self._group_drag_snapshot:
                ln.x1 = ox1 + dx;  ln.y1 = oy1 + dy
                ln.x2 = ox2 + dx;  ln.y2 = oy2 + dy
            self._solver_drag_lines = {ln for (ln, *_) in self._group_drag_snapshot}
            self._solve_constraints(3)
            return

        # Vertex drag
        if self.tool_mode == "vertex" and self._vertex_drag_active and self._vertex_drag_refs:
            cx, cy = self._vertex_candidate_positions(wx, wy)
            ox, oy = self._vertex_drag_start_pos
            self._set_refs_vertex(self._vertex_drag_refs, cx, cy)
            self._vertex_hover = (cx, cy)
            self.snap_hint = ("endpoint", cx, cy)
            self._weld_propagate_vertex_move(ox, oy, cx, cy, ignore_line=None)
            ox = cx;  oy = cy  # update origin for continuous propagation
            self._vertex_drag_start_pos = (cx, cy)
            self._solver_drag_lines = {ln for (ln, _) in self._vertex_drag_refs}
            self._solve_constraints(4)
            return

        # Pan
        if self._pan_active:
            dx = sx - self._pan_last[0]
            dy = sy - self._pan_last[1]
            self._pan_last = (sx, sy)
            self.vp.offx += dx;  self.vp.offy += dy
            return

        # Line drag
        if self.tool_mode == "cursor" and self._dragging_line and self._dragging_point:
            ln = self._dragging_line
            ox1, oy1, ox2, oy2 = ln.x1, ln.y1, ln.x2, ln.y2

            if self._dragging_point == "body":
                dx = wx - (ln.x1 + self._drag_offset[0])
                dy = wy - (ln.y1 + self._drag_offset[1])
                ln.x1 += dx;  ln.y1 += dy
                ln.x2 += dx;  ln.y2 += dy
                if not self.manipulate_line:
                    self._weld_propagate_vertex_move(ox1, oy1, ln.x1, ln.y1, ignore_line=ln)
                    self._weld_propagate_vertex_move(ox2, oy2, ln.x2, ln.y2, ignore_line=ln)
            elif self._dragging_point in ("start", "end"):
                other_x = ln.x2 if self._dragging_point == "start" else ln.x1
                other_y = ln.y2 if self._dragging_point == "start" else ln.y1
                vx_old  = ox1 if self._dragging_point == "start" else ox2
                vy_old  = oy1 if self._dragging_point == "start" else oy2

                ignore_pts = {self._vkey(other_x, other_y)}
                tx, ty, kind = self._find_snap(wx, wy, ignore_line=ln, ignore_points=ignore_pts)
                if kind == "endpoint":
                    self.snap_hint = ("endpoint", tx, ty)
                    if ln.id not in self.fixed_lengths:
                        wx, wy = tx, ty
                else:
                    self.snap_hint = None
                    wx, wy = tx, ty  # line/alignment snap still applies

                # Fixed-length enforcement
                if ln.id in self.fixed_lengths:
                    L = float(self.fixed_lengths[ln.id]["len"])
                    ddx = wx - other_x;  ddy = wy - other_y
                    d = math.hypot(ddx, ddy)
                    if d > 1e-9:
                        wx = other_x + ddx / d * L
                        wy = other_y + ddy / d * L

                if self._dragging_point == "start":
                    ln.x1, ln.y1 = wx, wy
                else:
                    ln.x2, ln.y2 = wx, wy

                if not self.manipulate_line:
                    self._weld_propagate_vertex_move(vx_old, vy_old, wx, wy, ignore_line=ln)

            self._solver_drag_lines = {ln}
            self._solve_constraints(5)
            return

        # Hover highlight
        if self.tool_mode == "cursor":
            hit = self._hit_test(wx, wy)
            self.hovered_id = hit.id if hit else None

    def _on_mouse_up(self, cmd: dict):
        if self._group_drag_active or self._dragging_line or self._vertex_drag_active:
            self._solve_constraints(8)

        self._solver_drag_lines.clear()
        self._group_drag_active = False
        self._group_drag_snapshot = []
        self._dragging_line  = None
        self._dragging_point = None

        if self.tool_mode == "vertex" and self._vertex_temp:
            self.tool_mode = "cursor"
            self._vertex_temp = False

        self._vertex_drag_active = False
        self._vertex_drag_refs   = []
        self._vertex_hover       = None
        self.snap_hint           = None
        self._pan_active         = False

    def _on_double_click(self, cmd: dict):
        sx, sy = cmd["x"], cmd["y"]
        wx, wy = self.vp.screen_to_world(sx, sy)

        if self.tool_mode == "line":
            # End chain
            self.drawing_line     = False
            self.temp_line_start  = None
            self._set_mode("cursor")
            return

        # Dim on double-click: fix length on selected line
        if self.tool_mode == "cursor" and self.selected_id:
            ln = self._line_by_id(self.selected_id)
            if ln:
                self._request_float_dialog(
                    title="Fix Length",
                    label=f"Enter fixed length for line:",
                    initial=round(ln.length(), 4),
                    context={"kind": "fix_length", "line_id": ln.id},
                )

    def _on_right_click(self, cmd: dict):
        # Right-click cancels current action or clears selection
        sx, sy = cmd["x"], cmd["y"]
        wx, wy = self.vp.screen_to_world(sx, sy)
        if self.drawing_line:
            self.drawing_line    = False
            self.temp_line_start = None
            return
        if self.selected_id:
            # Right-click on nothing: clear selection
            hit = self._hit_test(wx, wy)
            if not hit:
                self.selected_id = None
                self.multi_selected_ids.clear()

    def _on_wheel(self, cmd: dict):
        sx, sy, delta = cmd["x"], cmd["y"], cmd["delta"]
        factor = 1.1 if delta < 0 else (1 / 1.1)
        Viewport.zoom_at_vp(self.vp, factor, sx, sy)
        self._update_zoom_tolerances()

    def _on_key_press(self, cmd: dict):
        key  = cmd.get("key", "")
        ctrl = cmd.get("ctrl", False)
        # Shortcuts not already handled by CADModule.tsx key handler
        if key == "l" and not ctrl:
            self._set_mode("line")
        elif key == "v" and not ctrl:
            self._set_mode("cursor")
        elif key == "n" and not ctrl:
            self._set_mode("vertex")
        elif key == "d" and not ctrl:
            self._set_mode("dim")

    def _on_resize(self, cmd: dict):
        old_cx = self._canvas_w / 2.0
        old_cy = self._canvas_h / 2.0
        self._canvas_w = cmd["width"]
        self._canvas_h = cmd["height"]
        new_cx = self._canvas_w / 2.0
        new_cy = self._canvas_h / 2.0
        self.vp.offx += new_cx - old_cx
        self.vp.offy += new_cy - old_cy

    # ──────────────────────────────────────────────────────────────
    # Dimension tool
    # ──────────────────────────────────────────────────────────────

    def _dim_on_mouse_down(self, wx, wy):
        hit = self._hit_test(wx, wy)
        if not hit:
            return

        if self._dim_first_line is None:
            # First click: pick first line
            self._dim_first_line = hit
            self.selected_id     = hit.id
        else:
            ln_a = self._dim_first_line
            ln_b = hit

            if ln_a is ln_b:
                # Same line: fix its length
                self._request_float_dialog(
                    title="Fix Length",
                    label=f"Enter fixed length:",
                    initial=round(ln_a.length(), 4),
                    context={"kind": "fix_length", "line_id": ln_a.id},
                )
            else:
                # Two different lines: offer angle or distance
                # Detect shared vertex
                vx, vy = self._shared_vertex(ln_a, ln_b)
                if vx is not None:
                    # Angle constraint
                    deg = self._angle_between(ln_a, ln_b, vx, vy)
                    self._request_float_dialog(
                        title="Angle Constraint",
                        label=f"Measured angle: {deg:.2f}°\nEnter target angle:",
                        initial=round(deg, 2),
                        context={"kind": "angle", "a_id": ln_a.id, "b_id": ln_b.id,
                                 "vx": vx, "vy": vy},
                    )
                else:
                    # Distance constraint
                    Pa, Pb, dist = self._closest_pts_between(ln_a, ln_b)
                    self._request_float_dialog(
                        title="Distance Constraint",
                        label=f"Measured distance: {dist:.4f}\nEnter target distance:",
                        initial=round(dist, 4),
                        context={"kind": "distance", "a_id": ln_a.id, "b_id": ln_b.id,
                                 "Pa": list(Pa), "Pb": list(Pb)},
                    )

            self._dim_first_line = None
            self.selected_id     = None

    def _shared_vertex(self, la, lb):
        for ax, ay in ((la.x1, la.y1), (la.x2, la.y2)):
            for bx, by in ((lb.x1, lb.y1), (lb.x2, lb.y2)):
                if math.hypot(ax - bx, ay - by) < EPS * 1000:
                    return ax, ay
        return None, None

    def _angle_between(self, la, lb, vx, vy):
        def out_vec(ln):
            if math.hypot(ln.x1 - vx, ln.y1 - vy) < EPS * 100:
                return ln.x2 - vx, ln.y2 - vy
            return ln.x1 - vx, ln.y1 - vy
        ax, ay = out_vec(la)
        bx, by = out_vec(lb)
        ma = math.hypot(ax, ay);  mb = math.hypot(bx, by)
        if ma < EPS or mb < EPS:
            return 0.0
        dot = (ax * bx + ay * by) / (ma * mb)
        return math.degrees(math.acos(max(-1.0, min(1.0, dot))))

    def _closest_pts_between(self, la, lb):
        best_d = 1e18;  best_Pa = None;  best_Pb = None
        for p in ((la.x1, la.y1), (la.x2, la.y2)):
            qx, qy, _ = lb.closest_point(p[0], p[1])
            d = math.hypot(p[0] - qx, p[1] - qy)
            if d < best_d:
                best_d = d;  best_Pa = p;  best_Pb = (qx, qy)
        for p in ((lb.x1, lb.y1), (lb.x2, lb.y2)):
            qx, qy, _ = la.closest_point(p[0], p[1])
            d = math.hypot(p[0] - qx, p[1] - qy)
            if d < best_d:
                best_d = d;  best_Pa = (qx, qy);  best_Pb = p
        return best_Pa, best_Pb, best_d

    # ──────────────────────────────────────────────────────────────
    # Dialog
    # ──────────────────────────────────────────────────────────────

    def _request_float_dialog(self, title: str, label: str, initial: float, context: dict):
        request_id = str(uuid.uuid4())
        self.pending_dialog = {
            "kind": "prompt_float",
            "title": title,
            "label": label,
            "initial": initial,
            "request_id": request_id,
        }
        self._pending_dialog_context = {**context, "request_id": request_id}

    def _on_dialog_response(self, cmd: dict):
        rid   = cmd.get("request_id")
        value = cmd.get("value")   # None means cancelled

        if not self._pending_dialog_context or self._pending_dialog_context.get("request_id") != rid:
            self.pending_dialog = None
            self._pending_dialog_context = None
            return

        ctx = self._pending_dialog_context
        self.pending_dialog = None
        self._pending_dialog_context = None

        if value is None:
            return   # user cancelled

        value = float(value)
        kind = ctx.get("kind")

        if kind == "fix_length":
            lid = ctx["line_id"]
            ln  = self._line_by_id(lid)
            if ln and value > 0:
                self._push_undo()
                self.fixed_lengths[lid] = {"len": value, "label": None}
                self._solve_constraints(5)

        elif kind == "angle":
            la = self._line_by_id(ctx["a_id"])
            lb = self._line_by_id(ctx["b_id"])
            if la and lb and 0 < value < 360:
                self._push_undo()
                self.angle_constraints.append({
                    "a": la, "b": lb,
                    "vx": ctx["vx"], "vy": ctx["vy"],
                    "deg": value, "side": 1, "off": 30,
                })

        elif kind == "distance":
            la = self._line_by_id(ctx["a_id"])
            lb = self._line_by_id(ctx["b_id"])
            if la and lb and value >= 0:
                self._push_undo()
                Pa = tuple(ctx["Pa"])
                Pb = tuple(ctx["Pb"])
                mid_x = (Pa[0] + Pb[0]) / 2
                mid_y = (Pa[1] + Pb[1]) / 2 - 0.3
                self.distance_constraints.append({
                    "a": la, "b": lb, "dist": value,
                    "Pa": Pa, "Pb": Pb,
                    "label": (mid_x, mid_y),
                })

    # ──────────────────────────────────────────────────────────────
    # Copy / Paste
    # ──────────────────────────────────────────────────────────────

    def _copy(self):
        selected = (
            list(self.multi_selected_ids)
            if self.multi_selected_ids
            else ([self.selected_id] if self.selected_id else [])
        )
        self._clipboard = []
        for lid in selected:
            ln = self._line_by_id(lid)
            if ln:
                self._clipboard.append({"x1": ln.x1, "y1": ln.y1,
                                         "x2": ln.x2, "y2": ln.y2,
                                         "color": ln.color})

    def _paste(self):
        if not self._clipboard:
            return
        self._push_undo()
        offset = 0.5
        new_ids = []
        for d in self._clipboard:
            ln = Line(d["x1"] + offset, d["y1"] + offset,
                      d["x2"] + offset, d["y2"] + offset, d["color"])
            self.lines.append(ln)
            new_ids.append(ln.id)
        self.multi_selected_ids = set(new_ids)
        self.selected_id = new_ids[0] if new_ids else None

    # ──────────────────────────────────────────────────────────────
    # Delete
    # ──────────────────────────────────────────────────────────────

    def _delete(self):
        dead = set()
        if self.multi_selected_ids:
            dead = set(self.multi_selected_ids)
        elif self.selected_id:
            dead = {self.selected_id}

        if not dead:
            return

        self._push_undo()
        dead_lines = {self._line_by_id(lid) for lid in dead} - {None}

        self.angle_constraints     = [c for c in self.angle_constraints     if c["a"] not in dead_lines and c["b"] not in dead_lines]
        self.distance_constraints  = [c for c in self.distance_constraints  if c["a"] not in dead_lines and c["b"] not in dead_lines]
        for ln in dead_lines:
            self.fixed_lengths.pop(ln.id, None)

        self.lines = [ln for ln in self.lines if ln not in dead_lines]
        self.selected_id = None
        self.multi_selected_ids.clear()
        self._prune_zero_lines()

    # ──────────────────────────────────────────────────────────────
    # Escape
    # ──────────────────────────────────────────────────────────────

    def _escape(self):
        self.drawing_line     = False
        self.temp_line_start  = None
        self._vertex_drag_active = False
        self._vertex_drag_refs   = []
        self._vertex_hover       = None
        self._dragging_line      = None
        self._dragging_point     = None
        self._pan_active         = False
        self.snap_hint           = None
        self.selected_id         = None
        self.multi_selected_ids.clear()
        self.alignment_guides    = []
        self.parallel_guides     = []
        self.equal_length_guides = []
        self.hovered_id          = None
        self._dim_first_line     = None
        self._dim_awaiting       = None
        self.pending_dialog      = None
        self._pending_dialog_context = None
        self._set_mode("cursor")

    # ──────────────────────────────────────────────────────────────
    # Zoom
    # ──────────────────────────────────────────────────────────────

    def _zoom_in(self):
        cx = self._canvas_w / 2.0;  cy = self._canvas_h / 2.0
        Viewport.zoom_at_vp(self.vp, 1.25, cx, cy)
        self._update_zoom_tolerances()

    def _zoom_out(self):
        cx = self._canvas_w / 2.0;  cy = self._canvas_h / 2.0
        Viewport.zoom_at_vp(self.vp, 0.8, cx, cy)
        self._update_zoom_tolerances()

    def _zoom_reset(self):
        self.vp.scale = 60.0
        self.vp.offx  = self._canvas_w / 2.0
        self.vp.offy  = self._canvas_h / 2.0
        self._update_zoom_tolerances()

    # ──────────────────────────────────────────────────────────────
    # Flags
    # ──────────────────────────────────────────────────────────────

    def _toggle_flag(self, cmd: dict):
        flag  = cmd["flag"]
        value = bool(cmd["value"])
        if flag == "manipulate_line":
            self.manipulate_line = value
        elif flag == "snap_axis":
            self.snap_axis = value
        elif flag == "line_match":
            self.line_match = value
        elif flag == "disable_vpoint":
            self.disable_vpoint = value

    def _set_angle_snap(self, cmd: dict):
        idx = int(cmd["index"])
        val = str(cmd["value"])
        while len(self.angle_snap_values) <= idx:
            self.angle_snap_values.append("")
        self.angle_snap_values[idx] = val

    # ──────────────────────────────────────────────────────────────
    # Hit testing
    # ──────────────────────────────────────────────────────────────

    def _hit_test(self, wx, wy) -> Optional[Line]:
        ht = self.hit_threshold
        for ln in self.lines:
            if math.hypot(wx - ln.x1, wy - ln.y1) < ht:
                return ln
            if math.hypot(wx - ln.x2, wy - ln.y2) < ht:
                return ln
        for ln in self.lines:
            if ln.distance_to_point(wx, wy) < ht:
                return ln
        return None

    def _hit_test_with_kind(self, wx, wy):
        ht = self.hit_threshold
        for ln in self.lines:
            if math.hypot(wx - ln.x1, wy - ln.y1) < ht:
                return ln, "start"
            if math.hypot(wx - ln.x2, wy - ln.y2) < ht:
                return ln, "end"
        for ln in self.lines:
            if ln.distance_to_point(wx, wy) < ht:
                return ln, "body"
        return None, None
