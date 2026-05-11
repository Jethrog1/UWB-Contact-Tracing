
import math

from .runtime import notify_info

class RotateManager:

    def __init__(self, app):
        self.app = app

        self.active = False
        self.state = "idle"                                                   

        self.selected_lines = []
        self.selected_dimensions = {}

        self.pivot_point = None                    
        self.axis_point = None                             

        self.preview_lines = []
        self.preview_dimensions = {}
        self.current_angle = 0.0

        self.original_state = None

    def activate(self):
        if not self.app.multi_selected and self.app.selected_line is None:
            notify_info(self.app, "Rotate", "Please select lines to rotate first.")
            return False

        self.selected_lines = list(self.app.multi_selected) if self.app.multi_selected else [self.app.selected_line]
        self._snapshot_dimensions()

        self.app._push_undo()

        self._saved_app_multi_selected = list(self.app.multi_selected)
        self._saved_app_selected_line = self.app.selected_line

        try:
            self.app.multi_selected.clear()
        except:
            self.app.multi_selected = set()
        self.app.selected_line = None

        self._saved_line_colors = {}
        for ln in self.selected_lines:
            try:
                self._saved_line_colors[ln] = getattr(ln, "color", "#4A9EFF")
                ln.color = "#888888"
            except:
                pass

        self.active = True
        self.state = "select_pivot"
        self.pivot_point = None
        self.axis_point = None
        self.current_angle = 0.0
        self.hover_vertex = None
        self.cursor_screen = (0, 0)

        try:
            self.app.root.config(cursor="none")
        except:
            pass

        self.app._request_redraw()
        return True

    def cancel(self):

        try:
            if hasattr(self, "_saved_line_colors") and self._saved_line_colors:
                for ln, col in self._saved_line_colors.items():
                    try:
                        ln.color = col
                    except:
                        pass
        except:
            pass

        try:
            if hasattr(self, "_saved_app_multi_selected"):
                try:
                    self.app.multi_selected.clear()
                except:
                    self.app.multi_selected = set()
                for ln in getattr(self, "_saved_app_multi_selected", []):
                    try:
                        self.app.multi_selected.add(ln)
                    except:
                        pass
            if hasattr(self, "_saved_app_selected_line"):
                self.app.selected_line = getattr(self, "_saved_app_selected_line", None)
        except:
            pass

        self.active = False
        self.state = "idle"
        self.pivot_point = None
        self.axis_point = None
        self.preview_lines = []
        self.preview_dimensions = {}
        self.selected_lines = []
        self.selected_dimensions = {}
        self.hover_vertex = None
        self.cursor_screen = (0, 0)

        try:
            self.app.root.config(cursor="arrow")
        except:
            pass

        self.app._request_redraw()

    def _snapshot_dimensions(self):
        self.selected_dimensions = {
            'fixed_lengths': [],
            'angle_constraints': [],
            'distance_constraints': []
        }

        selected_set = set(self.selected_lines)

        for ln, meta in self.app.fixed_lengths.items():
            if ln in selected_set:
                self.selected_dimensions['fixed_lengths'].append((ln, dict(meta)))

        for idx, ent in enumerate(self.app.angle_constraints):
            if ent['a'] in selected_set and ent['b'] in selected_set:
                self.selected_dimensions['angle_constraints'].append((idx, dict(ent)))

        for idx, ent in enumerate(self.app.distance_constraints):
            if ent['a'] in selected_set and ent['b'] in selected_set:
                self.selected_dimensions['distance_constraints'].append((idx, dict(ent)))

    def _find_vertex_near(self, wx, wy, threshold=0.2):
        if threshold == 0.2:
            threshold = getattr(self.app, "snap_dist_endpoint", 0.2)

        best = None
        best_d = 1e18

        for ln in self.selected_lines:
            d1 = math.hypot(wx - ln.x1, wy - ln.y1)
            if d1 < best_d:
                best_d = d1
                best = (ln.x1, ln.y1)

            d2 = math.hypot(wx - ln.x2, wy - ln.y2)
            if d2 < best_d:
                best_d = d2
                best = (ln.x2, ln.y2)

        if best is None or best_d > threshold:
            return None
        return best

    def on_mouse_down(self, e):
        if not self.active:
            return False

        wx, wy = self.app.vp.screen_to_world(e.x, e.y)

        if self.state == "select_pivot":

            vertex = self._find_vertex_near(wx, wy)
            if vertex is None:
                return True                                   

            self.pivot_point = vertex
            self.state = "select_axis"
            self.app.root.config(cursor="tcross")                                     
            self.app._request_redraw()
            return True

        elif self.state == "select_axis":

            vertex = self._find_vertex_near(wx, wy)
            if vertex is None:
                return True

            if math.hypot(vertex[0] - self.pivot_point[0], vertex[1] - self.pivot_point[1]) < 1e-6:
                return True                      

            self.axis_point = vertex
            self.state = "rotating"
            self._update_preview(wx, wy)
            self.app._request_redraw()
            return True

        elif self.state == "rotating":

            self._commit_rotation()
            return True

        return False

    def on_mouse_move(self, e):
        if not self.active:
            return False

        wx, wy = self.app.vp.screen_to_world(e.x, e.y)
        self.app.cursor_world = (wx, wy)
        self.app.cursor_world_valid = True
        self.cursor_screen = (e.x, e.y)

        if self.state in ("select_pivot", "select_axis"):
            self.hover_vertex = self._find_vertex_near(wx, wy)

        if self.state == "rotating":
            self._update_preview(wx, wy)
            self.app._request_redraw()
            return True

        self.app._request_redraw()
        return False

    def _update_preview(self, cursor_x, cursor_y):
        if self.pivot_point is None or self.axis_point is None:
            return

        px, py = self.pivot_point
        ax, ay = self.axis_point

        axis_dx = ax - px
        axis_dy = ay - py
        axis_angle = math.atan2(axis_dy, axis_dx)

        cursor_dx = cursor_x - px
        cursor_dy = cursor_y - py
        cursor_angle = math.atan2(cursor_dy, cursor_dx)

        self.current_angle = cursor_angle - axis_angle

        angle_snapped = self._apply_angle_snap(self.current_angle)
        if angle_snapped is not None:
            self.current_angle = angle_snapped

        self.preview_lines = []
        cos_a = math.cos(self.current_angle)
        sin_a = math.sin(self.current_angle)

        for ln in self.selected_lines:

            rx1 = ln.x1 - px
            ry1 = ln.y1 - py
            rx2 = ln.x2 - px
            ry2 = ln.y2 - py

            nx1 = px + rx1 * cos_a - ry1 * sin_a
            ny1 = py + rx1 * sin_a + ry1 * cos_a
            nx2 = px + rx2 * cos_a - ry2 * sin_a
            ny2 = py + rx2 * sin_a + ry2 * cos_a

            from .main_cad import Line
            self.preview_lines.append(Line(nx1, ny1, nx2, ny2, "#888888"))

    def _commit_rotation(self):
        if self.pivot_point is None or self.current_angle == 0.0:
            self.cancel()
            return

        px, py = self.pivot_point
        cos_a = math.cos(self.current_angle)
        sin_a = math.sin(self.current_angle)

        for ln in self.selected_lines:
            rx1 = ln.x1 - px
            ry1 = ln.y1 - py
            rx2 = ln.x2 - px
            ry2 = ln.y2 - py

            ln.x1 = px + rx1 * cos_a - ry1 * sin_a
            ln.y1 = py + rx1 * sin_a + ry1 * cos_a
            ln.x2 = px + rx2 * cos_a - ry2 * sin_a
            ln.y2 = py + rx2 * sin_a + ry2 * cos_a

        self._rotate_dimension_metadata(px, py, cos_a, sin_a)

        self.cancel()
        self.app._request_tree_update()
        self.app._request_redraw()

    def _rotate_dimension_metadata(self, px, py, cos_a, sin_a):

        for ln, original_meta in self.selected_dimensions['fixed_lengths']:
            if ln in self.app.fixed_lengths:
                label = self.app.fixed_lengths[ln].get('label')
                if label:
                    lx, ly = label
                    rx = lx - px
                    ry = ly - py
                    self.app.fixed_lengths[ln]['label'] = (
                        px + rx * cos_a - ry * sin_a,
                        py + rx * sin_a + ry * cos_a
                    )

        for idx, original_ent in self.selected_dimensions['angle_constraints']:
            if 0 <= idx < len(self.app.angle_constraints):
                ent = self.app.angle_constraints[idx]
                vx, vy = ent['vx'], ent['vy']
                rx = vx - px
                ry = vy - py
                ent['vx'] = px + rx * cos_a - ry * sin_a
                ent['vy'] = py + rx * sin_a + ry * cos_a

        for idx, original_ent in self.selected_dimensions['distance_constraints']:
            if 0 <= idx < len(self.app.distance_constraints):
                ent = self.app.distance_constraints[idx]

                label = ent.get('label')
                if label:
                    lx, ly = label
                    rx = lx - px
                    ry = ly - py
                    ent['label'] = (
                        px + rx * cos_a - ry * sin_a,
                        py + rx * sin_a + ry * cos_a
                    )

                Pa = ent.get('Pa')
                if Pa:
                    pax, pay = Pa
                    rx = pax - px
                    ry = pay - py
                    ent['Pa'] = (
                        px + rx * cos_a - ry * sin_a,
                        py + rx * sin_a + ry * cos_a
                    )

                Pb = ent.get('Pb')
                if Pb:
                    pbx, pby = Pb
                    rx = pbx - px
                    ry = pby - py
                    ent['Pb'] = (
                        px + rx * cos_a - ry * sin_a,
                        py + rx * sin_a + ry * cos_a
                    )

    def draw_overlay(self, canvas):
        if not self.active:
            return

        if self.state == "rotating":
            for ln in self.preview_lines:
                sx1, sy1 = self.app.vp.world_to_screen(ln.x1, ln.y1)
                sx2, sy2 = self.app.vp.world_to_screen(ln.x2, ln.y2)
                canvas.create_line(sx1, sy1, sx2, sy2, fill="#888888", width=2, dash=(4, 4))

        if self.pivot_point is not None:
            px, py = self.pivot_point
            sx, sy = self.app.vp.world_to_screen(px, py)
            r = 4
            canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill="#FF0000", outline="", width=0)

        if self.state == "select_axis" and self.pivot_point is not None:
            px, py = self.pivot_point
            spx, spy = self.app.vp.world_to_screen(px, py)

            cx, cy = self.app.cursor_world
            scx, scy = self.app.vp.world_to_screen(cx, cy)
            canvas.create_line(spx, spy, scx, scy, fill="#888888", width=2, dash=(6, 4))

        if self.state == "rotating" and self.pivot_point is not None and self.axis_point is not None:
            px, py = self.pivot_point
            ax, ay = self.axis_point

            is_snapped = (self._apply_angle_snap(self.current_angle) is not None)
            faint_blue = "#2A4A66"
            line_color = "#FFFFFF" if is_snapped else faint_blue

            rx = ax - px
            ry = ay - py
            cos_a = math.cos(self.current_angle)
            sin_a = math.sin(self.current_angle)

            new_ax = px + rx * cos_a - ry * sin_a
            new_ay = py + rx * sin_a + ry * cos_a

            axis_len = math.hypot(rx, ry)
            extension = max(axis_len * 3, 10.0)

            dir_x = new_ax - px
            dir_y = new_ay - py
            line_len = math.hypot(dir_x, dir_y)
            if line_len > 1e-9:
                ux = dir_x / line_len
                uy = dir_y / line_len

                end1_x = px - ux * extension
                end1_y = py - uy * extension
                end2_x = px + ux * extension
                end2_y = py + uy * extension

                se1x, se1y = self.app.vp.world_to_screen(end1_x, end1_y)
                se2x, se2y = self.app.vp.world_to_screen(end2_x, end2_y)

                canvas.create_line(se1x, se1y, se2x, se2y, fill=line_color, width=2, dash=(8, 4))

                abs_ang = math.atan2(new_ay - py, new_ax - px)
                abs_deg = (math.degrees(abs_ang) % 360.0)
                if abs_deg >= 180.0:
                    abs_deg -= 180.0

                spx, spy = self.app.vp.world_to_screen(px, py)
                sax, say = self.app.vp.world_to_screen(new_ax, new_ay)
                dxs = sax - spx
                dys = say - spy

                scr_ang = math.degrees(math.atan2(dys, dxs))

                mx = 0.5 * (spx + sax)
                my = 0.5 * (spy + say)

                nlen = math.hypot(dxs, dys)
                if nlen < 1e-9:
                    ox, oy = 0.0, -18.0
                else:
                    nx = -dys / nlen
                    ny = dxs / nlen
                    ox, oy = nx * 18.0, ny * 18.0

                if scr_ang > 90.0 or scr_ang < -90.0:
                    ox, oy = -ox, -oy

                label = f"{abs_deg:.1f}°"
                canvas.create_text(
                    mx + ox, my + oy,
                    text=label,
                    fill=line_color,
                    font=("Arial", 16, "bold"),
                    angle=0
                )

        if self.hover_vertex is not None and self.state in ("select_pivot", "select_axis"):
            if self.state == "select_axis" and self.pivot_point is not None:
                if math.hypot(self.hover_vertex[0] - self.pivot_point[0],
                              self.hover_vertex[1] - self.pivot_point[1]) < 1e-6:
                    pass
                else:
                    vx, vy = self.hover_vertex
                    sx, sy = self.app.vp.world_to_screen(vx, vy)
                    r = 10
                    canvas.create_oval(sx - r, sy - r, sx + r, sy + r, outline="#00FF00", width=2)
            else:
                vx, vy = self.hover_vertex
                sx, sy = self.app.vp.world_to_screen(vx, vy)
                r = 10
                ring = "#FF0000" if self.state == "select_pivot" else "#00FF00"
                canvas.create_oval(sx - r, sy - r, sx + r, sy + r, outline=ring, width=2)

        cx, cy = getattr(self, "cursor_screen", (0, 0))
        s = 8
        canvas.create_line(cx - s, cy, cx + s, cy, fill="#FFFFFF", width=2)
        canvas.create_line(cx, cy - s, cx, cy + s, fill="#FFFFFF", width=2)

    def _apply_angle_snap(self, angle_rad):
        snap_angles = self.app.snap._get_angle_snap_list()
        if not snap_angles:
            return None

        if self.pivot_point is None or self.axis_point is None:
            return None

        px, py = self.pivot_point
        ax, ay = self.axis_point

        base_ang = math.atan2(ay - py, ax - px)

        abs_ang = base_ang + angle_rad

        tol_deg = getattr(self.app, "angle_snap_tol_deg", 6.0)
        tol = math.radians(tol_deg)

        def wrap_pi(a):
            return math.atan2(math.sin(a), math.cos(a))

        best_abs = None
        best_err = 1e18

        for target_deg in snap_angles:
            t = math.radians(target_deg % 360.0)
            for cand in (t, t + math.pi):                                         
                err = abs(wrap_pi(abs_ang - cand))
                if err < best_err:
                    best_err = err
                    best_abs = cand

        if best_abs is None or best_err > tol:
            return None

        snapped_rot = best_abs - base_ang

        two_pi = 2.0 * math.pi
        while snapped_rot - angle_rad > math.pi:
            snapped_rot -= two_pi
        while snapped_rot - angle_rad < -math.pi:
            snapped_rot += two_pi

        return snapped_rot

