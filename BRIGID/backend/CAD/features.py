
from .runtime import tk

class VisualSettings:
    def __init__(self, app):
        self.app = app

        self.disable_v_point_var = tk.BooleanVar(value=False)

class ZoomController:

    def __init__(self, app):
        self.app = app                                                           
        self._update_zoom_adaptive_tolerances()

    @staticmethod
    def zoom_at_vp(vp, factor, anchor_sx, anchor_sy):
        wx, wy = vp.screen_to_world(anchor_sx, anchor_sy)
        vp.scale = max(1.0, min(10000.0, vp.scale * float(factor)))
        vp.offx = anchor_sx - wx * vp.scale
        vp.offy = anchor_sy - wy * vp.scale

    def zoom_at(self, factor, anchor_sx, anchor_sy):
        self.zoom_at_vp(self.app.vp, factor, anchor_sx, anchor_sy)
        self._update_zoom_display()                           
        self.app._request_redraw()

    def _update_zoom_display(self):
        zoom_text = f"{int(self.app.vp.scale / 60.0 * 100)}%"

        if getattr(self.app, "zoom_display", None) is not None:
            self.app.zoom_display.config(text=zoom_text)

        if hasattr(self.app, "dropdown") and self.app.dropdown.active:
            if self.app.dropdown.zoom_display_label:
                self.app.dropdown.zoom_display_label.config(text=zoom_text)

        self._update_zoom_adaptive_tolerances()

    def zoom_in(self):
        w = self.app.canvas.winfo_width()
        h = self.app.canvas.winfo_height()
        self.zoom_at_vp(self.app.vp, 1.25, w * 0.5, h * 0.5)
        self._update_zoom_display()                           
        self.app._request_redraw()

    def zoom_out(self):
        w = self.app.canvas.winfo_width()
        h = self.app.canvas.winfo_height()
        self.zoom_at_vp(self.app.vp, 0.8, w * 0.5, h * 0.5)
        self._update_zoom_display()                           
        self.app._request_redraw()

    def zoom_reset(self):
        w = self.app.canvas.winfo_width()
        h = self.app.canvas.winfo_height()
        wx, wy = self.app.vp.screen_to_world(w * 0.5, h * 0.5)
        self.app.vp.scale = 60.0
        self.app.vp.offx = w * 0.5 - wx * self.app.vp.scale
        self.app.vp.offy = h * 0.5 - wy * self.app.vp.scale
        self._update_zoom_display()                           
        self.app._request_redraw()

    def on_mousewheel(self, e):
        if getattr(e, "delta", 0) == 0:
            return
        self.zoom_at_vp(self.app.vp, 1.1 if e.delta > 0 else 1 / 1.1, e.x, e.y)
        self._update_zoom_display()                           
        self.app._request_redraw()

    def on_mousewheel_linux(self, e):
        self.zoom_at_vp(self.app.vp, 1.1 if e.num == 4 else 1 / 1.1, e.x, e.y)
        self._update_zoom_display()                           
        self.app._request_redraw()

    def _update_zoom_adaptive_tolerances(self):
        try:
            s = float(getattr(self.app.vp, "scale", 60.0))
            if s <= 1e-9:
                s = 60.0
        except:
            s = 60.0

        def px_to_world(px):
            try:
                return float(px) / s
            except:
                return 0.15

        endpoint_px = getattr(self.app, "endpoint_px", 10)

        line_snap_px = getattr(self.app, "line_snap_px", 9)

        hit_px = getattr(self.app, "hit_px", 9)

        align_px = getattr(self.app, "align_px", 8)

        axis_px = getattr(self.app, "line_match_axis_px", 12)
        axis_intersection_px = getattr(self.app, "line_match_intersection_px", 16)

        equal_len_px = getattr(self.app, "equal_len_px", 14)

        self.app.snap_dist_endpoint = px_to_world(endpoint_px)
        self.app.snap_dist_line = px_to_world(line_snap_px)

        self.app.hit_threshold = px_to_world(hit_px)

        self.app.snap_align_threshold = px_to_world(align_px)
        self.app.snap_axis_distance = px_to_world(axis_px)
        self.app.snap_axis_intersection_tol = px_to_world(axis_intersection_px)
        self.app.snap_equal_len_tol = px_to_world(equal_len_px)

