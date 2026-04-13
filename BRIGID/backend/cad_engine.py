from __future__ import annotations

from typing import Any

from CAD.headless_app import HeadlessCADDocument
from CAD.runtime import KeyEvent, MouseEvent


CTRL_MASK = 0x0004
SHIFT_MASK = 0x0001
BUTTON1_MASK = 0x0100


class CADEngine:
    """
    Thin command bridge over the restored headless CAD document.

    Geometry behavior lives in backend/CAD/*.
    This class only adapts frontend commands into the original Python event flow.
    """

    def __init__(self, canvas_w: int = 800, canvas_h: int = 600):
        self.doc = HeadlessCADDocument(canvas_w=canvas_w, canvas_h=canvas_h)
        self._right_box_active = False

    def to_state_dict(self) -> dict[str, Any]:
        return self.doc.to_state_dict()

    def _mouse_state(self, cmd: dict[str, Any]) -> int:
        state = 0
        if cmd.get("ctrl"):
            state |= CTRL_MASK
        if cmd.get("shift"):
            state |= SHIFT_MASK
        buttons = int(cmd.get("buttons", 0) or 0)
        if buttons & 1:
            state |= BUTTON1_MASK
        return state

    def _mouse_event(self, cmd: dict[str, Any], *, delta: int = 0, num: int | None = None) -> MouseEvent:
        x = float(cmd.get("x", 0.0))
        y = float(cmd.get("y", 0.0))
        return MouseEvent(
            x=x,
            y=y,
            state=self._mouse_state(cmd),
            num=num,
            delta=delta,
            button=int(cmd.get("button", 0) or 0),
            x_root=int(x),
            y_root=int(y),
        )

    def _tk_key(self, key: str) -> str:
        mapping = {
            "Escape": "Escape",
            "Enter": "Return",
            "Delete": "Delete",
            "Backspace": "BackSpace",
            " ": "space",
        }
        return mapping.get(key, key)

    def handle_command(self, cmd: dict[str, Any]) -> dict[str, Any]:
        kind = cmd.get("type", "")
        self.doc.last_error = None

        try:
            if kind == "mouse_down":
                self._handle_mouse_down(cmd)
            elif kind == "mouse_move":
                self._handle_mouse_move(cmd)
            elif kind == "mouse_up":
                self._handle_mouse_up(cmd)
            elif kind == "mouse_leave":
                self.doc.on_canvas_leave()
            elif kind == "double_click":
                self.doc.on_double_click(self._mouse_event(cmd))
            elif kind == "right_click":
                self.doc.on_right_click_menu(self._mouse_event(cmd, num=3))
            elif kind == "wheel":
                delta_y = float(cmd.get("delta", 0.0))
                wheel_delta = 120 if delta_y < 0 else -120
                self.doc.on_mousewheel(self._mouse_event(cmd, delta=wheel_delta))
            elif kind == "key_press":
                self._handle_key_press(cmd)
            elif kind == "tool_change":
                self._set_mode(str(cmd.get("tool", "cursor")))
            elif kind == "viewport_resize":
                self.doc.resize(int(cmd["width"]), int(cmd["height"]))
            elif kind == "dialog_response":
                self.doc.resolve_dialog(str(cmd.get("request_id", "")), cmd.get("value"))
            elif kind == "toggle_flag":
                self._toggle_flag(str(cmd.get("flag", "")), bool(cmd.get("value")))
            elif kind == "angle_snap_set":
                self._set_angle_snap(int(cmd.get("index", 0)), str(cmd.get("value", "")))
            elif kind == "undo":
                self.doc.on_undo()
            elif kind == "redo":
                self.doc.on_redo()
            elif kind == "copy":
                self.doc.on_copy()
            elif kind == "paste":
                self.doc.on_paste()
            elif kind == "delete":
                self.doc.on_delete_key()
            elif kind == "escape":
                self.doc.on_escape()
            elif kind == "zoom_in":
                self.doc.zoom_in()
            elif kind == "zoom_out":
                self.doc.zoom_out()
            elif kind == "zoom_reset":
                self.doc.zoom_reset()
            elif kind == "context_action":
                self.doc.invoke_context_action(str(cmd.get("action", "")))
            elif kind == "trim_value_set":
                self._trim_value_set(int(cmd.get("point", 1)), cmd.get("value"))
            elif kind == "trim_apply":
                if self.doc.trim.active:
                    self.doc.trim._apply_trim()
            elif kind == "context_close":
                self.doc.dropdown.close_menu()
            else:
                self.doc.post_error("CAD Command", f"Unsupported command: {kind}")
        except Exception as exc:
            self.doc.post_error("CAD Engine", str(exc))

        return self.doc.to_state_dict()

    def _handle_mouse_down(self, cmd: dict[str, Any]) -> None:
        button = int(cmd.get("button", 0) or 0)
        if button == 2 and cmd.get("shift"):
            self._right_box_active = True
            self.doc.on_right_down(self._mouse_event(cmd, num=3))
            return
        if button == 0:
            self.doc.on_mouse_down(self._mouse_event(cmd))

    def _handle_mouse_move(self, cmd: dict[str, Any]) -> None:
        buttons = int(cmd.get("buttons", 0) or 0)
        if self._right_box_active:
            self.doc.on_right_drag(self._mouse_event(cmd, num=3))
            return
        if buttons & 1:
            self.doc.on_mouse_drag(self._mouse_event(cmd))
            return
        self.doc.on_mouse_move(self._mouse_event(cmd))

    def _handle_mouse_up(self, cmd: dict[str, Any]) -> None:
        button = int(cmd.get("button", 0) or 0)
        if button == 2 and self._right_box_active:
            self.doc.on_right_up(self._mouse_event(cmd, num=3))
            self._right_box_active = False
            return
        if button == 0:
            self.doc.on_mouse_up(self._mouse_event(cmd))

    def _handle_key_press(self, cmd: dict[str, Any]) -> None:
        key = str(cmd.get("key", ""))
        lower = key.lower()
        ctrl = bool(cmd.get("ctrl"))
        shift = bool(cmd.get("shift"))

        if ctrl and lower == "z" and shift:
            self.doc.on_redo()
            return
        if ctrl and lower == "z":
            self.doc.on_undo()
            return
        if ctrl and lower == "y":
            self.doc.on_redo()
            return
        if ctrl and lower == "c":
            self.doc.on_copy()
            return
        if ctrl and lower == "v":
            self.doc.on_paste()
            return
        if key in {"Delete", "Backspace"}:
            self.doc.on_delete_key()
            return
        if key == "Escape":
            self.doc.on_escape()
            return
        if not ctrl:
            if lower == "l":
                self.doc.set_line_mode()
                return
            if lower == "v":
                self.doc.set_cursor_mode()
                return
            if lower == "n":
                self.doc.set_vertex_mode()
                return
            if lower == "d":
                self.doc.set_dim_mode()
                return

        self.doc.on_key_press(KeyEvent(keysym=self._tk_key(key), state=self._mouse_state(cmd)))

    def _set_mode(self, mode: str) -> None:
        if mode == "cursor":
            self.doc.set_cursor_mode()
        elif mode == "line":
            self.doc.set_line_mode()
        elif mode == "vertex":
            self.doc.set_vertex_mode()
        elif mode == "dim":
            self.doc.set_dim_mode()

    def _toggle_flag(self, flag: str, value: bool) -> None:
        if flag == "manipulate_line":
            self.doc.manipulate_line_var.set(value)
        elif flag == "snap_axis":
            self.doc.snap_axis_var.set(value)
        elif flag == "line_match":
            self.doc.line_match_var.set(value)
        elif flag == "disable_vpoint":
            self.doc.visuals.disable_v_point_var.set(value)
        self.doc._request_redraw()

    def _set_angle_snap(self, index: int, value: str) -> None:
        while len(self.doc.snap_angle_vars) <= index:
            self.doc.snap_angle_vars.append(type(self.doc.snap_angle_vars[0])(""))
        self.doc.snap_angle_vars[index].set(value)
        self.doc._request_redraw()

    def _trim_value_set(self, point: int, value: Any) -> None:
        if not self.doc.trim.active:
            return
        text = "" if value in (None, "") else str(value)
        if point == 1:
            if self.doc.trim.trim1_var is None:
                self.doc.trim.trim1_var = type(self.doc.snap_angle_vars[0])("")
            self.doc.trim.trim1_var.set(text)
            self.doc.trim._on_entry_change(1)
        else:
            if self.doc.trim.trim2_var is None:
                self.doc.trim.trim2_var = type(self.doc.snap_angle_vars[0])("")
            self.doc.trim.trim2_var.set(text)
            self.doc.trim._on_entry_change(2)
