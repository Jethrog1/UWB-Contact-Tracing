# snap.py
import math

class SnapController:
    """
    Centralizes all snapping helpers. Methods mirror the original
    functions from main_cad.py to preserve behavior and minimize diffs.
    """
    def __init__(self, app):
        self.app = app

    # -------------------------
    # Angle snap
    # -------------------------
    def _get_angle_snap_list(self):
        vals = []
        for sv in self.app.snap_angle_vars:
            s = (sv.get() or "").strip()
            if not s:
                continue
            try:
                d = float(s)
            except:
                continue
            vals.append(d % 360.0)

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

        # Clear guides (line match guides are re-added later)
        self.app.alignment_guides = []
        self.app.parallel_guides = []
        self.app.equal_length_guides = []

        best_ep = None
        best_ep_d = 1e18

        # Collect all endpoints
        all_endpoints = []
        for ln in self.app.lines:
            if ignore_line is not None and ln is ignore_line:
                continue
            p1 = (ln.x1, ln.y1)
            if self.app._vkey(*p1) not in ignore_points:
                all_endpoints.append(p1)
            p2 = (ln.x2, ln.y2)
            if self.app._vkey(*p2) not in ignore_points:
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
        snap_axis_on = bool(getattr(self.app, "snap_axis_var", None).get()) if hasattr(self.app,
                                                                                       "snap_axis_var") else False

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

        return wx, wy, None

    def _apply_line_match_snap(self, x0, y0, wx, wy, ignore_line=None):
        """
        Line Match snapping core (parallel axis snap + equal-length check + guide generation).
        This was previously _apply_line_match_snap on the app; logic preserved.
        """

        # HARD GATE: if Line Match toggle is OFF, do nothing (prevents hidden snapping in manipulate-line mode)
        if hasattr(self.app, "line_match_var") and not bool(self.app.line_match_var.get()):
            self.app.parallel_guides = []
            self.app.equal_length_guides = []
            return wx, wy

        axis_snap_distance = getattr(self.app, "snap_axis_distance", 0.35)
        intersection_tol = getattr(self.app, "snap_axis_intersection_tol", 0.55)
        equal_len_tol = getattr(self.app, "snap_equal_len_tol", 0.20)

        active_lines = []
        for ln in self.app.lines:
            if ignore_line is not None and ln is ignore_line:
                continue

            dx = ln.x2 - ln.x1
            dy = ln.y2 - ln.y1
            L = (dx * dx + dy * dy) ** 0.5
            if L < 1e-9:
                continue

            ux = dx / L
            uy = dy / L

            # Project (wx, wy) onto infinite line defined by ln
            px = wx - ln.x1
            py = wy - ln.y1
            proj_t = px * ux + py * uy
            closest_x = ln.x1 + proj_t * ux
            closest_y = ln.y1 + proj_t * uy

            perp = ((wx - closest_x) ** 2 + (wy - closest_y) ** 2) ** 0.5
            if perp <= axis_snap_distance:
                active_lines.append((ln, ux, uy, closest_x, closest_y))

        result_x, result_y = wx, wy

        # If multiple candidates, try to snap to intersection of their axes
        if len(active_lines) >= 2:
            best = None
            best_d = 1e18
            sx, sy = wx, wy

            for i in range(len(active_lines)):
                ln1, ux1, uy1, _, _ = active_lines[i]
                for j in range(i + 1, len(active_lines)):
                    ln2, ux2, uy2, _, _ = active_lines[j]
                    det = ux1 * (-uy2) - (-ux2) * uy1
                    if abs(det) < 1e-9:
                        continue  # parallel axes

                    rhsx = ln2.x1 - ln1.x1
                    rhsy = ln2.y1 - ln1.y1
                    t = (rhsx * (-uy2) - (-ux2) * rhsy) / det

                    ix = ln1.x1 + t * ux1
                    iy = ln1.y1 + t * uy1
                    d = ((sx - ix) ** 2 + (sy - iy) ** 2) ** 0.5
                    if d < best_d:
                        best_d = d
                        best = (ix, iy)

            if best is not None and best_d <= intersection_tol:
                result_x, result_y = best
                self.app.parallel_guides = [(result_x, result_y, result_x, result_y, item[0]) for item in active_lines]
                self.app.equal_length_guides = []
                return result_x, result_y

        # Else: snap to the closest single axis
        if active_lines:
            ln1, ux1, uy1, cx, cy = min(
                active_lines,
                key=lambda item: ((wx - item[3]) ** 2 + (wy - item[4]) ** 2) ** 0.5
            )
            result_x, result_y = cx, cy

            # Equal-length check relative to THAT axis, if the start (x0,y0) is also on the primary axis
            start_px = x0 - ln1.x1
            start_py = y0 - ln1.y1
            start_perp = abs(start_px * uy1 - start_py * ux1)

            if start_perp <= axis_snap_distance:
                ref_len = ln1.length()
                if ref_len > 1e-9:
                    cur_len = ((result_x - x0) ** 2 + (result_y - y0) ** 2) ** 0.5
                    if abs(cur_len - ref_len) <= equal_len_tol:
                        dot = (result_x - x0) * ux1 + (result_y - y0) * uy1
                        sgn = -1.0 if dot < 0 else 1.0
                        result_x = x0 + sgn * ref_len * ux1
                        result_y = y0 + sgn * ref_len * uy1
                        self.app.equal_length_guides = [(x0, y0, result_x, result_y, ln1)]

            # Store guides for visualization
            self.app.parallel_guides = [(x0, y0, result_x, result_y, ln) for ln, *_ in active_lines]
            return result_x, result_y

        # No axis candidates; clear guides
        self.app.parallel_guides = []
        self.app.equal_length_guides = []
        return result_x, result_y
    def _apply_snap_for_cursor(self, wx, wy, ignore_line=None, ignore_points=None):
        # First apply standard snapping (endpoints, alignment, lines)
        sx, sy, kind = self._find_snap(wx, wy, ignore_line=ignore_line, ignore_points=ignore_points)

        if kind == "endpoint":
            self.app.cursor_world_snapped = (sx, sy)
            self.app.snap_hint = ("endpoint", sx, sy)
            # Clear guides if we snapped to a hard geometry point
            self.app.parallel_guides = []
            self.app.equal_length_guides = []
            return

        # If drawing a line, check for axis snapping (start point exists)
        if self.app.temp_line_start:
            x0, y0 = self.app.temp_line_start

            # First apply angle snap
            ax, ay = self._apply_angle_snap_for_line(x0, y0, sx, sy)

            # Then apply slope axis snap ONLY if line match is enabled
            if self.app.line_match_var.get():
                px, py = self._apply_line_match_snap(x0, y0, ax, ay, ignore_line=None)
            else:
                px, py = ax, ay
                # Clear guides when line match is off
                self.app.parallel_guides = []
                self.app.equal_length_guides = []

            self.app.cursor_world_snapped = (px, py)
            self.app.snap_hint = None
            return

        # When NOT drawing (just hovering cursor), check slope axes ONLY if enabled
        else:
            self.app.parallel_guides = []
            self.app.equal_length_guides = []

            if self.app.line_match_var.get():
                axis_snap_distance = 0.35
                intersection_tol = 0.55  # Tolerance to snap to a calculated intersection

                candidates = []

                # 1. Gather all lines where cursor is close to infinite slope axis
                for ln in self.app.lines:
                    dx_ln = ln.x2 - ln.x1
                    dy_ln = ln.y2 - ln.y1
                    len_ln = math.hypot(dx_ln, dy_ln)

                    if len_ln < 1e-9:
                        continue

                    ux_ln = dx_ln / len_ln
                    uy_ln = dy_ln / len_ln

                    # Calculate perpendicular distance from cursor to the infinite line
                    px = sx - ln.x1
                    py = sy - ln.y1

                    # Project cursor onto axis to get closest point
                    proj_t = px * ux_ln + py * uy_ln
                    closest_x = ln.x1 + proj_t * ux_ln
                    closest_y = ln.y1 + proj_t * uy_ln

                    perp_dist = math.hypot(sx - closest_x, sy - closest_y)

                    if perp_dist < axis_snap_distance:
                        candidates.append((perp_dist, ln, ux_ln, uy_ln, closest_x, closest_y))

                if candidates:
                    # Sort by distance to the axis
                    candidates.sort(key=lambda x: x[0])

                    best_snap = None
                    active_guides = []

                    # 2. Check for Intersection between top candidates
                    if len(candidates) >= 2:
                        # Check pairs for valid intersection near cursor
                        for i in range(len(candidates)):
                            if best_snap: break
                            for j in range(i + 1, len(candidates)):
                                _, ln1, ux1, uy1, _, _ = candidates[i]
                                _, ln2, ux2, uy2, _, _ = candidates[j]

                                det = ux1 * (-uy2) - (-ux2) * uy1
                                if abs(det) < 1e-9: continue  # Lines are parallel

                                # Solve intersection
                                rhsx = ln2.x1 - ln1.x1
                                rhsy = ln2.y1 - ln1.y1
                                t = (rhsx * (-uy2) - (-ux2) * rhsy) / det

                                ix = ln1.x1 + t * ux1
                                iy = ln1.y1 + t * uy1

                                # Only snap if intersection is actually near the cursor
                                if math.hypot(sx - ix, sy - iy) < intersection_tol:
                                    best_snap = (ix, iy)
                                    active_guides = [ln1, ln2]
                                    break

                    # 3. Fallback to single closest axis if no intersection found
                    if not best_snap:
                        _, ln, _, _, cx, cy = candidates[0]
                        best_snap = (cx, cy)
                        active_guides = [ln]

                    # Apply snap
                    self.app.cursor_world_snapped = best_snap

                    # Generate guides for visualization
                    gx, gy = best_snap
                    self.app.parallel_guides = [(gx, gy, gx, gy, ln) for ln in active_guides]

                    self.app.snap_hint = None
                    return

        self.app.cursor_world_snapped = (sx, sy)
        self.app.snap_hint = None

    # -------------------------
    # Vertex helpers
    # -------------------------
    def _find_vertex_near(self, wx, wy):
        best = None
        best_d = 1e18
        for ln in self.app.lines:
            d1 = math.hypot(wx - ln.x1, wy - ln.y1)
            if d1 < best_d:
                best_d = d1
                best = (ln.x1, ln.y1)
            d2 = math.hypot(wx - ln.x2, wy - ln.y2)
            if d2 < best_d:
                best_d = d2
                best = (ln.x2, ln.y2)
        if best is None or best_d > self.app.snap_dist_endpoint:
            return None
        return best

    def _collect_vertex_refs(self, vx, vy):
        refs = []
        for ln in self.app.lines:
            if math.hypot(ln.x1 - vx, ln.y1 - vy) < 1e-6:
                refs.append((ln, "start"))
            if math.hypot(ln.x2 - vx, ln.y2 - vy) < 1e-6:
                refs.append((ln, "end"))
        return refs

    def _set_refs_vertex(self, refs, x, y):
        for ln, which in refs:
            if which == "start":
                ln.x1 = x
                ln.y1 = y
            else:
                ln.x2 = x
                ln.y2 = y

    def _vertex_candidate_positions(self, raw_x, raw_y):
        if not self.app._vertex_drag_refs:
            return raw_x, raw_y
        best = (raw_x, raw_y)
        best_d = 1e18
        for ln, which in self.app._vertex_drag_refs:
            ox, oy = (ln.x2, ln.y2) if which == "start" else (ln.x1, ln.y1)
            cx, cy = self._apply_angle_snap_for_line(ox, oy, raw_x, raw_y)
            d = (raw_x - cx) ** 2 + (raw_y - cy) ** 2
            if d < best_d:
                best_d = d
                best = (cx, cy)
        return best

#123aaaadd1122bbccdd1/1