import math

class QtSnapController:
    """
    Port of SnapController for PyQt6. 
    Removes Tkinter variable dependencies and uses native Python types.
    """
    def __init__(self, app):
        self.app = app # app is expected to be CADWidget

    # -------------------------
    # Angle snap
    # -------------------------
    def _get_angle_snap_list(self):
        # In PyQt version, we'll store these as diverse list of floats on the app or hardcode for now
        # Assuming app has .angle_snaps list
        vals = self.app.angle_snaps if hasattr(self.app, "angle_snaps") else []
        
        out = []
        seen = set()
        for d in vals:
            k = round(d, 6)
            if k in seen:
                continue
            seen.add(k)
            out.append(d)
        return out

    def _wrap_pi(self, a):
        return math.atan2(math.sin(a), math.cos(a))

    def _angle_snap_if_close(self, x0, y0, x1, y1):
        angles = self._get_angle_snap_list()
        if not angles:
            return x1, y1, False

        dx = x1 - x0
        dy = y1 - y0
        r = math.hypot(dx, dy)
        if r < 1e-9:
            return x1, y1, False

        a = math.atan2(-dy, dx)
        tol = math.radians(getattr(self.app, "angle_snap_tol_deg", 6.0))

        best_theta = None
        best_err = 1e18

        for deg in angles:
            th = math.radians(deg)
            for cand in (th, th + math.pi):
                err = abs(self._wrap_pi(a - cand))
                if err < best_err:
                    best_err = err
                    best_theta = cand

        if best_theta is None or best_err > tol:
            return x1, y1, False

        return x0 + r * math.cos(best_theta), y0 - r * math.sin(best_theta), True

    def _apply_angle_snap_for_line(self, x_fixed, y_fixed, x_free, y_free):
        ax, ay, snapped = self._angle_snap_if_close(x_fixed, y_fixed, x_free, y_free)
        return (ax, ay) if snapped else (x_free, y_free)

    # -------------------------
    # Snapping helpers
    # -------------------------
    def _find_snap(self, wx, wy, ignore_line=None, ignore_points=None):
        if ignore_points is None:
            ignore_points = set()

        # Clear guides
        self.app.alignment_guides = []
        self.app.parallel_guides = []
        self.app.equal_length_guides = []

        best_ep = None
        best_ep_d = 1e18

        # Collect all endpoints - ensuring we don't snap to "ignore_points"
        # Since _vkey is just a tuple key in original, we key by (x,y)
        all_endpoints = []
        for ln in self.app.lines:
            if ignore_line is not None and ln is ignore_line:
                continue
            p1 = (ln.x1, ln.y1)
            # crude floating point check for ignore
            if not any(math.hypot(p1[0]-ip[0], p1[1]-ip[1]) < 1e-9 for ip in ignore_points):
                all_endpoints.append(p1)
            p2 = (ln.x2, ln.y2)
            if not any(math.hypot(p2[0]-ip[0], p2[1]-ip[1]) < 1e-9 for ip in ignore_points):
                all_endpoints.append(p2)

        # Endpoint snapping
        for p in all_endpoints:
            d = math.hypot(wx - p[0], wy - p[1])
            if d < best_ep_d:
                best_ep_d = d
                best_ep = p

        if best_ep is not None and best_ep_d <= getattr(self.app, "snap_dist_endpoint", 0.20):
            return best_ep[0], best_ep[1], "endpoint"

        # Optional axis alignment snapping
        snap_axis_on = getattr(self.app, "snap_axis_enabled", True)

        if snap_axis_on:
            align_threshold = getattr(self.app, "snap_align_threshold", 0.12)

            best_x_align = None
            best_x_d = 1e18
            best_y_align = None
            best_y_d = 1e18

            for ep in all_endpoints:
                ex, ey = ep

                dx = abs(wx - ex)
                if dx < align_threshold and dx < best_x_d:
                    best_x_d = dx
                    best_x_align = (ex, ep)

                dy = abs(wy - ey)
                if dy < align_threshold and dy < best_y_d:
                    best_y_d = dy
                    best_y_align = (ey, ep)

            final_x = wx
            final_y = wy

            if best_x_align is not None:
                final_x, source_ep_x = best_x_align
                self.app.alignment_guides.append((source_ep_x[0], source_ep_x[1], final_x, wy, 'x'))

            if best_y_align is not None:
                final_y, source_ep_y = best_y_align
                self.app.alignment_guides.append((source_ep_y[0], source_ep_y[1], wx, final_y, 'y'))

            if best_x_align is not None or best_y_align is not None:
                return final_x, final_y, "alignment"

        # Line snapping
        best_p = None
        best_ld = 1e18
        for ln in self.app.lines:
            if ignore_line is not None and ln is ignore_line:
                continue
            px, py, _ = ln.closest_point(wx, wy)
            d = math.hypot(wx - px, wy - py)
            if d < best_ld:
                best_ld = d
                best_p = (px, py)

        if best_p is not None and best_ld <= getattr(self.app, "snap_dist_line", 0.15):
            return best_p[0], best_p[1], "line"

        if best_p is not None and best_ld <= getattr(self.app, "snap_dist_line", 0.15):
            return best_p[0], best_p[1], "line"

        # Grid Snapping (Lowest priority)
        if getattr(self.app, "grid_snap_enabled", False):
            # Get current grid step from app (calculated in paintEvent)
            step = getattr(self.app, "current_grid_step", 1.0)
            if step > 0:
                gx = round(wx / step) * step
                gy = round(wy / step) * step
                
                # Check distance to grid point (snap radius)
                # Let's say snap radius is same as endpoint? or slightly looser?
                # Using screen pixels -> world conversion typically
                # For now use a fixed world distance or dynamic based on zoom?
                # Let's use 10 screen pixels
                threshold = 10.0 / self.app.vp.scale
                if math.hypot(wx - gx, wy - gy) < threshold:
                     return gx, gy, "grid"

        return wx, wy, None

    def get_snap(self, wx, wy, drawing_line=False):
        """
        Main public method to get snap point.
        Updates app state (guides, snap hints) and returns (sx, sy).
        """
        # If global snap is disabled, just return raw coordinates
        if not getattr(self.app, "snap_enabled", True):
             self.app.snap_hint = None
             self.app.alignment_guides = []
             return wx, wy

        ignore_line = None # Future: if dragging a line
        ignore_points = set()

        # First apply standand snapping
        sx, sy, kind = self._find_snap(wx, wy, ignore_line, ignore_points)

        if kind == "endpoint":
            self.app.snap_hint = ("endpoint", sx, sy)
            self.app.alignment_guides = [] # Clear alignment guides if endpoint snapped
            return sx, sy
        
        # If drawing a line, check for axis snapping relative to start
        if drawing_line and self.app.temp_line_start:
            x0, y0 = self.app.temp_line_start
            
            # Angle snap
            ax, ay = self._apply_angle_snap_for_line(x0, y0, sx, sy)
            
            # (Skipping advanced line match logic for initial port, focusing on core)
            
            self.app.snap_hint = None
            return ax, ay

        self.app.snap_hint = None
        return sx, sy
