from __future__ import annotations

import math
import time
import uuid
from typing import Any, Callable

from . import copy_paste, dimension_rules, dimension_tool, features, main_cad, rotate, snap, trim
from .runtime import (
    BooleanVar,
    HeadlessButton,
    HeadlessLabel,
    HeadlessRoot,
    HeadlessTree,
    RecordingCanvas,
    StringVar,
)


class HeadlessDropdown:
    def __init__(self, app: "HeadlessCADDocument"):
        self.app = app
        self.active = False
        self.anchor_x = 0
        self.anchor_y = 0
        self.zoom_display_label = HeadlessLabel(text="100%")
        self.model: dict[str, Any] | None = None

    def open_menu(self, screen_x: float, screen_y: float) -> None:
        self.active = True
        self.anchor_x = screen_x
        self.anchor_y = screen_y
        self.model = self.app.build_context_menu(screen_x, screen_y)

    def close_menu(self) -> None:
        self.active = False
        self.model = None


class HeadlessCADDocument(main_cad.FloorPlanCAD):
    def __init__(self, canvas_w: int = 800, canvas_h: int = 600):
        self.root = HeadlessRoot()
        self.canvas = RecordingCanvas(width=canvas_w, height=canvas_h)
        self.tree = HeadlessTree()
        self.status_label = HeadlessLabel(text="")
        self.zoom_display = HeadlessLabel(text="100%")
        self.cursor_btn = HeadlessButton()
        self.line_btn = HeadlessButton()
        self.vertex_btn = HeadlessButton()
        self.dim_btn = HeadlessButton()
        self.rotate_btn = HeadlessButton()
        self.trim_btn = HeadlessButton()

        self.vp = main_cad.Viewport()
        self.lines: list[main_cad.Line] = []

        self.fixed_lengths: dict[main_cad.Line, dict[str, Any]] = {}
        self.angle_constraints: list[dict[str, Any]] = []
        self.distance_constraints: list[dict[str, Any]] = []

        self.tool_mode = "cursor"
        self.drawing_line = False
        self.temp_line_start = None

        self.selected_line = None
        self.multi_selected: set[main_cad.Line] = set()
        self.hovered_line = None

        self.dragging_line = None
        self.dragging_point = None
        self.drag_offset = (0.0, 0.0)

        self._solver_drag_lines = set()

        self._pan_active = False
        self._pan_last = (0, 0)

        self.snap_dist_endpoint = 0.20
        self.snap_dist_line = 0.15
        self.cursor_world = (0.0, 0.0)
        self.cursor_world_valid = False
        self.cursor_world_snapped = (0.0, 0.0)
        self.snap_hint = None

        self._group_drag_active = False
        self._group_drag_start = (0.0, 0.0)
        self._group_drag_snapshot = []

        self._box_active = False
        self._box_s0 = (0, 0)
        self._box_s1 = (0, 0)

        self._vertex_temp = False
        self._vertex_drag_active = False
        self._vertex_hover = None
        self._vertex_drag_refs = []
        self._vertex_drag_start_mouse = (0.0, 0.0)
        self._vertex_drag_start_pos = (0.0, 0.0)

        self.manipulate_line_var = BooleanVar(False)
        self._weld_body_refs = None

        self.alignment_guides = []
        self.parallel_guides = []
        self.equal_length_guides = []
        self.line_match_var = BooleanVar(False)
        self.snap_axis_var = BooleanVar(True)

        self._redraw_pending = False
        self._tree_pending = False

        self.angle_snap_tol_deg = 6.0
        self.snap_angle_vars = [StringVar(""), StringVar(""), StringVar(""), StringVar("")]

        self.visuals = features.VisualSettings(self)
        self.zoom = features.ZoomController(self)

        self._undo_stack = []
        self._redo_stack = []

        self.dimension_tool = dimension_tool.DimensionTool(self)
        self.copy_paste = copy_paste.CopyPasteManager(self)
        self.snap = snap.SnapController(self)
        self.dimension_rules = dimension_rules.DimensionRules(self)
        self.rotate = rotate.RotateManager(self)
        self.trim = trim.TrimManager(self)
        self.dropdown = HeadlessDropdown(self)

        self._tree_iid_to_line = {}
        self._tree_dim_iids = set()
        self._line_ids: dict[main_cad.Line, str] = {}

        self.pending_dialog: dict[str, Any] | None = None
        self._pending_dialog_handler: Callable[[float | None], None] | None = None
        self.last_error: str | None = None
        self.last_notice: dict[str, str] | None = None

        self._scene: list[dict[str, Any]] = []
        self._last_flush_ts = time.time()

        self._initialize_view()
        self.set_cursor_mode()
        self._request_tree_update()
        self._request_redraw()
        self.flush()

    def _request_redraw(self):
        self._redraw_pending = True

    def _request_tree_update(self):
        self._tree_pending = True

    def resize(self, width: int, height: int) -> None:
        old_cx = self.canvas.winfo_width() * 0.5
        old_cy = self.canvas.winfo_height() * 0.5
        self.canvas.set_size(width, height)
        new_cx = width * 0.5
        new_cy = height * 0.5
        self.vp.offx += new_cx - old_cx
        self.vp.offy += new_cy - old_cy
        self._request_redraw()

    def post_error(self, title: str, message: str) -> None:
        self.last_error = message if not title else f"{title}: {message}"
        self.last_notice = {"kind": "error", "title": title, "message": message}

    def post_info(self, title: str, message: str) -> None:
        self.last_notice = {"kind": "info", "title": title, "message": message}

    def clear_messages(self) -> None:
        self.last_error = None
        self.last_notice = None

    def request_float_dialog(
        self,
        title: str,
        label: str,
        initial: float,
        handler: Callable[[float | None], None],
    ) -> None:
        request_id = str(uuid.uuid4())
        self.pending_dialog = {
            "kind": "prompt_float",
            "title": title,
            "label": label,
            "initial": float(initial),
            "request_id": request_id,
        }
        self._pending_dialog_handler = handler
        self._request_redraw()

    def resolve_dialog(self, request_id: str, value: float | None) -> None:
        pending = self.pending_dialog
        handler = self._pending_dialog_handler
        self.pending_dialog = None
        self._pending_dialog_handler = None
        if pending is None or pending.get("request_id") != request_id or handler is None:
            return
        handler(None if value is None else float(value))

    def invoke_context_action(self, action_id: str) -> None:
        if action_id == "zoom_in":
            self.zoom_in()
        elif action_id == "zoom_out":
            self.zoom_out()
        elif action_id == "zoom_reset":
            self.zoom_reset()
        elif action_id == "copy":
            self.on_copy()
        elif action_id == "paste":
            self.on_paste()
        elif action_id == "rotate":
            self.activate_rotate()
        elif action_id == "trim":
            self.activate_trim()
        elif action_id == "toggle_manipulate_line":
            self.manipulate_line_var.set(not bool(self.manipulate_line_var.get()))
        elif action_id == "toggle_snap_axis":
            self.snap_axis_var.set(not bool(self.snap_axis_var.get()))
        elif action_id == "toggle_line_match":
            self.line_match_var.set(not bool(self.line_match_var.get()))
        elif action_id == "toggle_disable_vpoint":
            self.visuals.disable_v_point_var.set(not bool(self.visuals.disable_v_point_var.get()))
        self.dropdown.close_menu()
        self._request_redraw()

    def build_context_menu(self, screen_x: float, screen_y: float) -> dict[str, Any]:
        selected_count = len(self.multi_selected) or (1 if self.selected_line is not None else 0)
        clipboard_ready = bool(getattr(self.copy_paste, "clipboard", None))
        can_trim = selected_count == 1
        return {
            "x": screen_x,
            "y": screen_y,
            "sections": [
                {
                    "title": "Zoom Settings",
                    "items": [
                        {"id": "zoom_out", "label": "Zoom Out", "kind": "action"},
                        {"id": "zoom_in", "label": "Zoom In", "kind": "action"},
                        {"id": "zoom_reset", "label": f"Reset View ({self.zoom_percent()}%)", "kind": "action"},
                    ],
                },
                {
                    "title": "Clipboard",
                    "items": [
                        {"id": "copy", "label": "Copy", "kind": "action", "disabled": selected_count == 0},
                        {"id": "paste", "label": "Paste", "kind": "action", "disabled": not clipboard_ready},
                    ],
                },
                {
                    "title": "Line Settings",
                    "items": [
                        {
                            "id": "toggle_manipulate_line",
                            "label": "Manipulate Line",
                            "kind": "toggle",
                            "checked": bool(self.manipulate_line_var.get()),
                        },
                        {
                            "id": "toggle_snap_axis",
                            "label": "Snap Axis",
                            "kind": "toggle",
                            "checked": bool(self.snap_axis_var.get()),
                        },
                        {
                            "id": "toggle_line_match",
                            "label": "Line Match",
                            "kind": "toggle",
                            "checked": bool(self.line_match_var.get()),
                        },
                        {
                            "id": "toggle_disable_vpoint",
                            "label": "Disable V Point",
                            "kind": "toggle",
                            "checked": bool(self.visuals.disable_v_point_var.get()),
                        },
                    ],
                },
                {
                    "title": "Config Settings",
                    "items": [
                        {"id": "rotate", "label": "Rotate", "kind": "action", "disabled": selected_count == 0},
                        {"id": "trim", "label": "Trim", "kind": "action", "disabled": not can_trim},
                    ],
                },
            ],
        }

    def zoom_percent(self) -> int:
        return int(self.vp.scale / 60.0 * 100)

    def _refresh_line_ids(self) -> None:
        active: set[main_cad.Line] = set(self.lines)
        active.update(self.fixed_lengths.keys())
        for ent in self.angle_constraints:
            active.add(ent["a"])
            active.add(ent["b"])
        for ent in self.distance_constraints:
            active.add(ent["a"])
            active.add(ent["b"])
        old_map = self._line_ids
        self._line_ids = {line: old_map.get(line, str(uuid.uuid4())) for line in active}

    def line_id(self, line: main_cad.Line | None) -> str | None:
        if line is None:
            return None
        self._refresh_line_ids()
        return self._line_ids.get(line)

    def flush(self) -> None:
        if self.trim.active:
            now = time.time()
            dt = now - self._last_flush_ts
            self._last_flush_ts = now
            self.trim.animation_offset += max(0.0, dt * 60.0 * 0.5)
            self._redraw_pending = True
        else:
            self._last_flush_ts = time.time()

        if self._tree_pending:
            self._update_feature_tree()
            self._tree_pending = False

        if self._redraw_pending:
            self.canvas.delete("all")
            super().redraw()
            self._scene = list(self.canvas.primitives)
            self._redraw_pending = False

    def serialize_dim_key(self, kind: str, ident: Any) -> str:
        if kind == "len":
            return f"len:{self.line_id(ident)}"
        return f"{kind}:{ident}"

    def serialize_feature_tree(self) -> list[dict[str, Any]]:
        return self.tree.export()

    def serialize_trim_state(self) -> dict[str, Any]:
        return {
            "active": bool(self.trim.active),
            "selected_line_id": self.line_id(self.trim.selected_line),
            "line_length": float(getattr(self.trim, "line_length", 0.0) or 0.0),
            "trim_point_1": self.trim.trim_point_1,
            "trim_point_2": self.trim.trim_point_2,
            "selecting_point": self.trim.selecting_point,
            "hover_position": self.trim.hover_position,
            "cursor_near_line": bool(self.trim.cursor_near_line),
            "trim1_text": self.trim.trim1_var.get() if self.trim.trim1_var else "",
            "trim2_text": self.trim.trim2_var.get() if self.trim.trim2_var else "",
            "distance_text": self.trim.distance_label.cget("text") if self.trim.distance_label else "",
        }

    def serialize_rotate_state(self) -> dict[str, Any]:
        return {
            "active": bool(self.rotate.active),
            "state": self.rotate.state,
            "pivot_point": list(self.rotate.pivot_point) if self.rotate.pivot_point is not None else None,
            "axis_point": list(self.rotate.axis_point) if self.rotate.axis_point is not None else None,
            "current_angle_deg": math.degrees(getattr(self.rotate, "current_angle", 0.0)),
            "selected_line_ids": [self.line_id(line) for line in getattr(self.rotate, "selected_lines", [])],
        }

    def to_state_dict(self) -> dict[str, Any]:
        self.flush()
        self._refresh_line_ids()

        fixed_lengths_out = {}
        for line, meta in self.fixed_lengths.items():
            line_id = self.line_id(line)
            if line_id is None:
                continue
            fixed_lengths_out[line_id] = {
                "len": float(meta.get("len", line.length())),
                "label": list(meta.get("label")) if meta.get("label") else None,
            }

        angle_out = []
        for idx, ent in enumerate(self.angle_constraints):
            angle_out.append(
                {
                    "idx": idx,
                    "line_a_id": self.line_id(ent["a"]),
                    "line_b_id": self.line_id(ent["b"]),
                    "vx": float(ent["vx"]),
                    "vy": float(ent["vy"]),
                    "deg": float(ent["deg"]),
                    "side": int(ent.get("side", 1)),
                    "off": float(ent.get("off", 0.75)),
                }
            )

        distance_out = []
        for idx, ent in enumerate(self.distance_constraints):
            distance_out.append(
                {
                    "idx": idx,
                    "line_a_id": self.line_id(ent["a"]),
                    "line_b_id": self.line_id(ent["b"]),
                    "dist": float(ent["dist"]),
                    "Pa": list(ent.get("Pa")) if ent.get("Pa") else None,
                    "Pb": list(ent.get("Pb")) if ent.get("Pb") else None,
                    "label": list(ent.get("label")) if ent.get("label") else None,
                }
            )

        selected_dims = sorted(
            self.serialize_dim_key(kind, ident)
            for kind, ident in self.dimension_tool._get_selected_dimensions()
        )
        if getattr(self.dimension_tool, "_selected_kind", None) is not None:
            selected_dims.append(
                self.serialize_dim_key(self.dimension_tool._selected_kind, self.dimension_tool._selected_id)
            )

        state = {
            "lines": [
                {
                    "id": self.line_id(line),
                    "x1": float(line.x1),
                    "y1": float(line.y1),
                    "x2": float(line.x2),
                    "y2": float(line.y2),
                    "color": line.color,
                }
                for line in self.lines
            ],
            "fixed_lengths": fixed_lengths_out,
            "angle_constraints": angle_out,
            "distance_constraints": distance_out,
            "selected_id": self.line_id(self.selected_line),
            "multi_selected_ids": [self.line_id(line) for line in self.multi_selected],
            "hovered_id": self.line_id(self.hovered_line),
            "tool_mode": self.tool_mode,
            "drawing_line": bool(self.drawing_line),
            "temp_line_start": list(self.temp_line_start) if self.temp_line_start else None,
            "paste_active": bool(self.copy_paste.paste_active),
            "rotate_active": bool(self.rotate.active),
            "trim_active": bool(self.trim.active),
            "vertex_hover": list(self._vertex_hover) if self._vertex_hover else None,
            "cursor_world": list(self.cursor_world),
            "cursor_world_snapped": list(self.cursor_world_snapped),
            "snap_hint": (
                {"kind": self.snap_hint[0], "x": self.snap_hint[1], "y": self.snap_hint[2]}
                if self.snap_hint
                else None
            ),
            "alignment_guides": [
                {"x1": g[0], "y1": g[1], "x2": g[2], "y2": g[3], "type": g[4]}
                for g in self.alignment_guides
            ],
            "parallel_guides": [
                {
                    "x1": guide[0],
                    "y1": guide[1],
                    "x2": guide[2],
                    "y2": guide[3],
                    "line_id": self.line_id(guide[4]) if len(guide) > 4 else None,
                }
                for guide in self.parallel_guides
            ],
            "equal_length_guides": [
                {
                    "x1": guide[0],
                    "y1": guide[1],
                    "x2": guide[2],
                    "y2": guide[3],
                    "line_id": self.line_id(guide[4]) if len(guide) > 4 else None,
                }
                for guide in self.equal_length_guides
            ],
            "vp": {"scale": self.vp.scale, "offx": self.vp.offx, "offy": self.vp.offy},
            "manipulate_line": bool(self.manipulate_line_var.get()),
            "snap_axis": bool(self.snap_axis_var.get()),
            "line_match": bool(self.line_match_var.get()),
            "disable_vpoint": bool(self.visuals.disable_v_point_var.get()),
            "angle_snap_values": [str(var.get() or "") for var in self.snap_angle_vars],
            "selected_dim_kinds": selected_dims,
            "feature_tree": self.serialize_feature_tree(),
            "render_primitives": self._scene,
            "context_menu": self.dropdown.model if self.dropdown.active else None,
            "trim_state": self.serialize_trim_state(),
            "rotate_state": self.serialize_rotate_state(),
            "clipboard": {
                "has_data": bool(getattr(self.copy_paste, "clipboard", None)),
                "line_count": len(getattr(self.copy_paste, "clipboard", {}).get("lines", []))
                if getattr(self.copy_paste, "clipboard", None)
                else 0,
            },
        }

        if self.pending_dialog:
            state["pending_dialog"] = self.pending_dialog
        if self.last_error:
            state["last_error"] = self.last_error
        if self.last_notice:
            state["last_notice"] = self.last_notice

        return state

