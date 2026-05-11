import math

from .runtime import notify_error, simpledialog

EPS = 1e-9

def _unit_fmt(v):
    av = abs(v)
    if av < 1e-6:
        return "0"
    if av < 10:
        return f"{v:.2f}".rstrip("0").rstrip(".")
    if av < 100:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{v:.0f}"

def _dot(ax, ay, bx, by):
    return ax * bx + ay * by

def _len(ax, ay):
    return math.hypot(ax, ay)

def _norm(ax, ay):
    L = math.hypot(ax, ay)
    if L < EPS:
        return 0.0, 0.0, 0.0
    return ax / L, ay / L, L

def _clamp(x, a, b):
    return a if x < a else (b if x > b else x)

def _closest_points_between_segments(p1, p2, q1, q2):

    ux, uy = p2[0] - p1[0], p2[1] - p1[1]
    vx, vy = q2[0] - q1[0], q2[1] - q1[1]
    wx, wy = p1[0] - q1[0], p1[1] - q1[1]

    a = _dot(ux, uy, ux, uy)
    b = _dot(ux, uy, vx, vy)
    c = _dot(vx, vy, vx, vy)
    d = _dot(ux, uy, wx, wy)
    e = _dot(vx, vy, wx, wy)

    D = a * c - b * b
    sN, sD = 0.0, D
    tN, tD = 0.0, D

    if D < EPS:
        sN = 0.0
        sD = 1.0
        tN = e
        tD = c
    else:
        sN = (b * e - c * d)
        tN = (a * e - b * d)
        if sN < 0.0:
            sN = 0.0
            tN = e
            tD = c
        elif sN > sD:
            sN = sD
            tN = e + b
            tD = c

    if tN < 0.0:
        tN = 0.0
        if -d < 0.0:
            sN = 0.0
        elif -d > a:
            sN = sD
        else:
            sN = -d
            sD = a
    elif tN > tD:
        tN = tD
        if (-d + b) < 0.0:
            sN = 0.0
        elif (-d + b) > a:
            sN = sD
        else:
            sN = (-d + b)
            sD = a

    sc = 0.0 if abs(sN) < EPS else sN / sD
    tc = 0.0 if abs(tN) < EPS else tN / tD

    Px = p1[0] + sc * ux
    Py = p1[1] + sc * uy
    Qx = q1[0] + tc * vx
    Qy = q1[1] + tc * vy

    return math.hypot(Px - Qx, Py - Qy), Px, Py, Qx, Qy

class DimensionTool:
    def __init__(self, app):
        self.app = app
        self.state = "idle"
        self.line1 = None
        self.line2 = None
        self.shared_vertex = None
        self.preview_label_pos = None

        self._multi_selected_dims = set()                            

    def activate(self):
        self.cancel()

    def cancel(self):
        self.state = "idle"
        self.line1 = None
        self.line2 = None
        self.shared_vertex = None
        self.preview_label_pos = None
        self.app.hovered_line = None
        self.app._request_redraw()

        self._hover_kind = None                          
        self._hover_id = None                                          
        self._drag_kind = None
        self._drag_id = None
        self._drag_active = False

        self._selected_kind = None
        self._selected_id = None

    def _hit_test_line(self, wx, wy, threshold=0.15, ignore=None):
        if threshold == 0.15:
            threshold = getattr(self.app, "hit_threshold", 0.15)

        best = None
        best_d = 1e18
        for ln in self.app.lines:
            if ignore is not None and ln is ignore:
                continue
            d = ln.distance_to_point(wx, wy)
            if d < threshold and d < best_d:
                best_d = d
                best = ln
        return best

    def _shared_vertex_of(self, L1, L2):
        def eq(p, q):
            return math.hypot(p[0] - q[0], p[1] - q[1]) < 1e-6
        A1 = (L1.x1, L1.y1); A2 = (L1.x2, L1.y2)
        B1 = (L2.x1, L2.y1); B2 = (L2.x2, L2.y2)
        for p in (A1, A2):
            if eq(p, B1) or eq(p, B2):
                return p
        return None

    def on_mouse_down(self, e):
        wx, wy = self.app.vp.screen_to_world(e.x, e.y)

        if self.state == "idle":
            ln = self._hit_test_line(wx, wy)
            if ln is None:
                return
            self.line1 = ln
            self.state = "pending_line"
            self.preview_label_pos = (wx, wy)
            self.app.hovered_line = None
            self.app._request_redraw()
            return

        if self.state == "pending_line":
            ln2 = self._hit_test_line(wx, wy, ignore=self.line1)
            if ln2 is None:
                self._finalize_length()
                return

            self.line2 = ln2
            self.shared_vertex = self._shared_vertex_of(self.line1, self.line2)
            self.state = "pending_pair"
            self.preview_label_pos = (wx, wy)
            self.app.hovered_line = None
            self.app._request_redraw()
            return

        if self.state == "pending_pair":
            if self.shared_vertex is not None:
                self._finalize_angle()
            else:
                self._finalize_distance()
            return

    def on_mouse_move(self, e):
        wx, wy = self.app.vp.screen_to_world(e.x, e.y)
        self.preview_label_pos = (wx, wy)

        if self.state == "idle":
            self.app.hovered_line = self._hit_test_line(wx, wy)
        elif self.state == "pending_line":
            self.app.hovered_line = self._hit_test_line(wx, wy, ignore=self.line1)
        else:
            self.app.hovered_line = None

        self.app._request_redraw()

    def on_escape(self):
        self.cancel()

    def _prompt_float(self, title, prompt, initial):
        try:
            val = simpledialog.askfloat(title, prompt, initialvalue=float(initial), parent=self.app.root)
            return None if val is None else float(val)
        except Exception:
            return None

    def _request_float_async(self, title, prompt, initial, on_resolve):
        if hasattr(self.app, "request_float_dialog"):
            self.app.request_float_dialog(title, prompt, initial, on_resolve)
            return True
        return False

    def _out_vec(self, ln, vx, vy):
        if math.hypot(ln.x1 - vx, ln.y1 - vy) < 1e-6:
            return (ln.x2 - vx, ln.y2 - vy)
        return (ln.x1 - vx, ln.y1 - vy)

    def _angle_between_lines_at_vertex(self, A, B, vx, vy):
        ax, ay = self._out_vec(A, vx, vy)
        bx, by = self._out_vec(B, vx, vy)
        ax, ay, la = _norm(ax, ay)
        bx, by, lb = _norm(bx, by)
        if la < 1e-9 or lb < 1e-9:
            return 0.0
        c = _clamp(_dot(ax, ay, bx, by), -1.0, 1.0)
        return math.degrees(math.acos(c))

    def _angle_side_choice(self, vx, vy, ax, ay, bx, by, label_pos):

        lx, ly = label_pos
        cx, cy = lx - vx, ly - vy
        cx, cy, _ = _norm(cx, cy)

        ix, iy, il = _norm(ax + bx, ay + by)

        ex, ey, el = _norm(ax - bx, ay - by)
        if il < 1e-9 and el < 1e-9:
            return 1, ax, ay            

        s1 = _dot(cx, cy, ix, iy) if il > 1e-9 else -1e9
        s2 = _dot(cx, cy, ex, ey) if el > 1e-9 else -1e9
        if s1 >= s2:
            return 1, ix, iy                 
        return -1, ex, ey                    

    def _finalize_length(self):
        if self.line1 is None:
            self.cancel()
            return

        ln = self.line1
        cur = max(ln.length(), 0.0)
        label_pos = self.preview_label_pos or ((ln.x1 + ln.x2) / 2, (ln.y1 + ln.y2) / 2)

        def apply_value(val):
            if val is None or val <= 0:
                self.cancel()
                self.app._request_tree_update()
                self.app._request_redraw()
                return

            self.app._push_undo()

            if ln in self.app.fixed_lengths:
                self.app.fixed_lengths[ln]["len"] = float(val)
                self.app.fixed_lengths[ln]["label"] = label_pos
            else:
                self.app.fixed_lengths[ln] = {"len": float(val), "label": label_pos}

            ok = True
            try:
                ok = bool(self.app.apply_length_dimension(ln, float(val)))
            except Exception:
                ok = False

            if not ok:
                try:
                    self.app.on_undo()
                except Exception:
                    pass
                notify_error(
                    self.app,
                    "Length constraint conflict",
                    "That length would modify an existing dimension/constraint.\n\nNo changes were applied.",
                )
                self.cancel()
                self.app._request_tree_update()
                self.app._request_redraw()
                return

            self.cancel()
            self.app._request_tree_update()
            self.app._request_redraw()

        if self._request_float_async("Set Length", "Enter length:", cur, apply_value):
            return

        apply_value(self._prompt_float("Set Length", "Enter length:", cur))

    def _finalize_angle(self):
        if self.line1 is None or self.line2 is None or self.shared_vertex is None:
            self.cancel()
            return

        vx, vy = self.shared_vertex
        base = self._angle_between_lines_at_vertex(self.line1, self.line2, vx, vy)
        base = max(1.0, min(179.0, base))

        ax, ay = self._out_vec(self.line1, vx, vy)
        bx, by = self._out_vec(self.line2, vx, vy)
        ax, ay, _ = _norm(ax, ay)
        bx, by, _ = _norm(bx, by)
        side, bdx, bdy = self._angle_side_choice(vx, vy, ax, ay, bx, by, self.preview_label_pos or (vx, vy))

        lp = self.preview_label_pos or (vx, vy)
        off = (lp[0] - vx) * bdx + (lp[1] - vy) * bdy
        if off < 0.25:
            off = 0.75

        meta = {"side": side, "off": float(off)}

        def apply_value(val):
            if val is None or val <= 0 or val >= 180:
                self.cancel()
                self.app._request_tree_update()
                self.app._request_redraw()
                return

            self.app._push_undo()

            self.app._add_or_update_angle(self.line1, self.line2, vx, vy, float(val), meta)

            ok = bool(self.app.apply_angle_dimension(self.line1, self.line2, vx, vy, float(val)))
            if not ok:
                try:
                    self.app.on_undo()
                except Exception:
                    pass
                notify_error(
                    self.app,
                    "Angle constraint conflict",
                    "That angle would modify an existing dimension/constraint.\n\nNo changes were applied.",
                )
                self.cancel()
                self.app._request_tree_update()
                self.app._request_redraw()
                return

            self.cancel()
            self.app._request_tree_update()
            self.app._request_redraw()

        if self._request_float_async("Set Angle (deg)", "Enter angle at shared vertex:", base, apply_value):
            return

        apply_value(self._prompt_float("Set Angle (deg)", "Enter angle at shared vertex:", base))

    def _finalize_distance(self):
        if self.line1 is None or self.line2 is None:
            self.cancel()
            return

        a = self.line1
        b = self.line2

        d0, px, py, qx, qy = _closest_points_between_segments(
            (a.x1, a.y1), (a.x2, a.y2),
            (b.x1, b.y1), (b.x2, b.y2)
        )

        def apply_value(val):
            if val is None or val < 0:
                self.cancel()
                self.app._request_tree_update()
                self.app._request_redraw()
                return

            self.app._push_undo()

            Pa, Pb = self.app.apply_distance_dimension(a, b, float(val))
            if Pa is None or Pb is None:
                try:
                    self.app.on_undo()
                except Exception:
                    pass
                self.cancel()
                self.app._request_tree_update()
                self.app._request_redraw()
                return

            self.app._add_or_update_distance(
                a, b, float(val),
                Pa, Pb,
                self.preview_label_pos or ((Pa[0] + Pb[0]) / 2, (Pa[1] + Pb[1]) / 2)
            )

            self.cancel()
            self.app._request_tree_update()
            self.app._request_redraw()

        if self._request_float_async("Set Distance", "Enter distance between lines:", max(d0, 0.0), apply_value):
            return

        apply_value(self._prompt_float("Set Distance", "Enter distance between lines:", max(d0, 0.0)))

    def _w2s(self, x, y):
        return self.app.vp.world_to_screen(x, y)

    def _dash(self):
        return (4, 3)

    def _arrow(self, canvas, x1, y1, x2, y2):
        vx, vy = x2 - x1, y2 - y1
        L = max(math.hypot(vx, vy), 1e-6)
        ux, uy = vx / L, vy / L
        size = 7
        lx = x2 - ux * size - uy * size * 0.6
        ly = y2 - uy * size + ux * size * 0.6
        rx = x2 - ux * size + uy * size * 0.6
        ry = y2 - uy * size - ux * size * 0.6
        canvas.create_polygon(x2, y2, lx, ly, rx, ry, fill="#E8E8E8", outline="")

    def draw_overlay(self, canvas):

        for ln, meta in self.app.fixed_lengths.items():
            hl = ((self._hover_kind == "len" and self._hover_id is ln) or
                  (self._selected_kind == "len" and self._selected_id is ln) or
                  ('len', ln) in self._multi_selected_dims)
            self._draw_length_dim(canvas, ln, meta.get("label", None), live=False, highlight=hl)

        for i, ent in enumerate(self.app.angle_constraints):
            hl = ((self._hover_kind == "ang" and self._hover_id == i) or
                  (self._selected_kind == "ang" and self._selected_id == i) or
                  ('ang', i) in self._multi_selected_dims)
            a = ent["a"];
            b = ent["b"];
            vx, vy = ent["vx"], ent["vy"]
            self._draw_angle_dim(canvas, a, b, (vx, vy), None, live=False, ent=ent, highlight=hl)

        for i, ent in enumerate(self.app.distance_constraints):
            hl = ((self._hover_kind == "dist" and self._hover_id == i) or
                  (self._selected_kind == "dist" and self._selected_id == i) or
                  ('dist', i) in self._multi_selected_dims)
            self._draw_distance_dim(canvas, ent["a"], ent["b"], ent.get("label", None), live=False, ent=ent,
                                    highlight=hl)

        if self.state == "pending_line" and self.line1:
            self._draw_length_dim(canvas, self.line1, self.preview_label_pos, live=True)
        elif self.state == "pending_pair" and self.line1 and self.line2:
            if self.shared_vertex is not None:
                self._draw_angle_dim(canvas, self.line1, self.line2, self.shared_vertex, self.preview_label_pos,
                                     live=True)
            else:
                self._draw_distance_dim(canvas, self.line1, self.line2, self.preview_label_pos, live=True)

    def _draw_length_dim(self, canvas, ln, label_pos, live=False, highlight=False):
        x1, y1, x2, y2 = ln.x1, ln.y1, ln.x2, ln.y2
        dx, dy = x2 - x1, y2 - y1
        ux, uy, L = _norm(dx, dy)
        if L < 1e-9: return
        nx, ny = -uy, ux

        ox, oy = label_pos or ((x1 + x2) / 2, (y1 + y2) / 2)
        off = (ox - x1) * nx + (oy - y1) * ny

        pA = (x1 + nx * off, y1 + ny * off)
        pB = (x2 + nx * off, y2 + ny * off)

        sx1, sy1 = self._w2s(x1, y1)
        sx2, sy2 = self._w2s(x2, y2)
        spA = self._w2s(*pA);
        spB = self._w2s(*pB)

        canvas.create_line(sx1, sy1, spA[0], spA[1], fill="#B0B0B0", dash=self._dash())
        canvas.create_line(sx2, sy2, spB[0], spB[1], fill="#B0B0B0", dash=self._dash())

        main_col = "#FFD21F" if (highlight and not live) else "#E8E8E8"
        txt_col = "white" if (highlight and not live) else ("white" if live else "cyan")

        canvas.create_line(spA[0], spA[1], spB[0], spB[1], fill=main_col, width=2)

        self._arrow(canvas, spB[0], spB[1], spA[0], spA[1])
        self._arrow(canvas, spA[0], spA[1], spB[0], spB[1])

        mx = (spA[0] + spB[0]) / 2
        my = (spA[1] + spB[1]) / 2
        shown = L if live else self.app.fixed_lengths.get(ln, {}).get("len", L)
        canvas.create_text(mx, my - 12, text=_unit_fmt(shown), fill=txt_col, font=("Segoe UI", 10, "bold"))

    def _draw_angle_dim(self, canvas, a, b, v, label_pos, live=False, ent=None, highlight=False):
        vx, vy = v
        svx, svy = self._w2s(vx, vy)

        ax, ay = self._out_vec(a, vx, vy)
        bx, by = self._out_vec(b, vx, vy)
        ax, ay, _ = _norm(ax, ay)
        bx, by, _ = _norm(bx, by)

        if ent is None:
            side, bdx, bdy = self._angle_side_choice(vx, vy, ax, ay, bx, by, label_pos or (vx, vy))
            lp = label_pos or (vx, vy)
            off = (lp[0] - vx) * bdx + (lp[1] - vy) * bdy
            if off < 0.25: off = 0.75
        else:
            side = ent.get("side", 1)
            if side >= 0:
                bdx, bdy, bl = _norm(ax + bx, ay + by)
                if bl < 1e-9: bdx, bdy, _ = _norm(ax, ay)
            else:
                bdx, bdy, bl = _norm(ax - bx, ay - by)
                if bl < 1e-9: bdx, bdy, _ = _norm(ax, ay)
            off = float(ent.get("off", 0.75))

        lx, ly = vx + bdx * off, vy + bdy * off
        slx, sly = self._w2s(lx, ly)

        R = max(28, int(math.hypot(slx - svx, sly - svy)))

        sa_x, sa_y = self._w2s(vx + ax, vy + ay)
        sb_x, sb_y = self._w2s(vx + bx, vy + by)
        sax, say = sa_x - svx, sa_y - svy
        sbx, sby = sb_x - svx, sb_y - svy
        th1 = math.degrees(math.atan2(say, sax)) % 360.0
        th2 = math.degrees(math.atan2(sby, sbx)) % 360.0

        d = (th2 - th1 + 540) % 360 - 180
        mid = (th1 + d / 2) % 360.0
        midx = svx + R * math.cos(math.radians(mid))
        midy = svy + R * math.sin(math.radians(mid))
        alt = (mid + 180) % 360.0
        axm = svx + R * math.cos(math.radians(alt))
        aym = svy + R * math.sin(math.radians(alt))
        if (slx - axm) ** 2 + (sly - aym) ** 2 < (slx - midx) ** 2 + (sly - midy) ** 2:
            th1, th2 = th2, th1
            d = (th2 - th1 + 540) % 360 - 180
            mid = (th1 + d / 2) % 360.0

        e1x = svx + R * math.cos(math.radians(th1))
        e1y = svy + R * math.sin(math.radians(th1))
        e2x = svx + R * math.cos(math.radians(th2))
        e2y = svy + R * math.sin(math.radians(th2))

        canvas.create_line(svx, svy, e1x, e1y, fill="#B0B0B0", dash=self._dash())
        canvas.create_line(svx, svy, e2x, e2y, fill="#B0B0B0", dash=self._dash())

        main_col = "#FFD21F" if (highlight and not live) else "#E8E8E8"
        txt_col = "white" if (highlight and not live) else ("white" if live else "cyan")

        steps = max(22, int(abs(d) / 4))
        pts = []
        for i in range(steps + 1):
            t = th1 + d * (i / steps)
            px = svx + R * math.cos(math.radians(t))
            py = svy + R * math.sin(math.radians(t))
            pts.extend((px, py))
        canvas.create_line(*pts, fill=main_col, width=2, smooth=True)

        lpx = svx + (R + 14) * math.cos(math.radians(mid))
        lpy = svy + (R + 14) * math.sin(math.radians(mid))
        val = self._angle_between_lines_at_vertex(a, b, vx, vy) if live else (ent.get("deg") if ent else None)
        if val is None:
            val = self._angle_between_lines_at_vertex(a, b, vx, vy)
        canvas.create_text(lpx, lpy, text=f"{_unit_fmt(val)}°", fill=txt_col, font=("Segoe UI", 10, "bold"))

    def _draw_distance_dim(self, canvas, a, b, label_pos, live=False, ent=None, highlight=False):
        d0, px, py, qx, qy = _closest_points_between_segments(
            (a.x1, a.y1), (a.x2, a.y2), (b.x1, b.y1), (b.x2, b.y2)
        )

        ux, uy, ul = _norm(a.x2 - a.x1, a.y2 - a.y1)
        if ul < 1e-9:
            ux, uy, ul = _norm(b.x2 - b.x1, b.y2 - b.y1)
            if ul < 1e-9:
                nx, ny, _ = _norm(qx - px, qy - py)
                ux, uy = -ny, nx
        nx, ny = -uy, ux

        mx0, my0 = (px + qx) / 2, (py + qy) / 2
        ox, oy = label_pos or (mx0, my0)
        slide = (ox - mx0) * ux + (oy - my0) * uy

        pA = (px + ux * slide, py + uy * slide)
        pB = (qx + ux * slide, qy + uy * slide)

        spA = self._w2s(*pA);
        spB = self._w2s(*pB)

        ta = ((pA[0] - a.x1) * (a.x2 - a.x1) + (pA[1] - a.y1) * (a.y2 - a.y1)) / max(
            (a.x2 - a.x1) ** 2 + (a.y2 - a.y1) ** 2, 1e-9)
        if ta < -0.01 or ta > 1.01:
            ta_clamped = max(0.0, min(1.0, ta))
            wa = (a.x1 + ta_clamped * (a.x2 - a.x1), a.y1 + ta_clamped * (a.y2 - a.y1))
            sw_a = self._w2s(*wa)
            canvas.create_line(sw_a[0], sw_a[1], spA[0], spA[1], fill="#B0B0B0", dash=self._dash())

        tb = ((pB[0] - b.x1) * (b.x2 - b.x1) + (pB[1] - b.y1) * (b.y2 - b.y1)) / max(
            (b.x2 - b.x1) ** 2 + (b.y2 - b.y1) ** 2, 1e-9)
        if tb < -0.01 or tb > 1.01:
            tb_clamped = max(0.0, min(1.0, tb))
            wb = (b.x1 + tb_clamped * (b.x2 - b.x1), b.y1 + tb_clamped * (b.y2 - b.y1))
            sw_b = self._w2s(*wb)
            canvas.create_line(sw_b[0], sw_b[1], spB[0], spB[1], fill="#B0B0B0", dash=self._dash())

        main_col = "#FFD21F" if (highlight and not live) else "#E8E8E8"
        txt_col = "white" if (highlight and not live) else ("white" if live else "cyan")

        canvas.create_line(spA[0], spA[1], spB[0], spB[1], fill=main_col, width=2)
        self._arrow(canvas, spA[0], spA[1], spB[0], spB[1])
        self._arrow(canvas, spB[0], spB[1], spA[0], spA[1])

        mx = (spA[0] + spB[0]) / 2
        my = (spA[1] + spB[1]) / 2
        shown = d0
        if not live and ent is not None:
            shown = ent.get("dist", d0)
        canvas.create_text(mx, my - 12, text=_unit_fmt(shown), fill=txt_col, font=("Segoe UI", 10, "bold"))

    def _draw_persisted_lengths(self, canvas):
        for ln, meta in self.app.fixed_lengths.items():
            self._draw_length_dim(canvas, ln, meta.get("label", None), live=False)

    def _draw_persisted_angles(self, canvas):
        for ent in self.app.angle_constraints:
            a = ent["a"]; b = ent["b"]
            vx, vy = ent["vx"], ent["vy"]
            self._draw_angle_dim(canvas, a, b, (vx, vy), None, live=False, ent=ent)

    def _draw_persisted_distances(self, canvas):
        for ent in self.app.distance_constraints:
            a = ent["a"]; b = ent["b"]
            self._draw_distance_dim(canvas, a, b, ent.get("label", None), live=False, ent=ent)

    def _pt_to_screen(self, p):
        return self._w2s(p[0], p[1])

    def _near_screen_pt(self, sx, sy, px, py, r=10):
        return (sx - px) ** 2 + (sy - py) ** 2 <= r * r

    def _near_screen_seg(self, px, py, x1, y1, x2, y2, tol=8):

        vx, vy = x2 - x1, y2 - y1
        L2 = max(vx * vx + vy * vy, 1e-9)
        t = max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / L2))
        qx, qy = x1 + t * vx, y1 + t * vy
        return (px - qx) ** 2 + (py - qy) ** 2 <= tol * tol

    def _length_dim_screen_geom(self, ln, label_pos):

        x1, y1, x2, y2 = ln.x1, ln.y1, ln.y2, ln.y2
        dx, dy = ln.x2 - ln.x1, ln.y2 - ln.y1
        ux, uy, L = _norm(dx, dy)
        if L < 1e-9:
            return None
        nx, ny = -uy, ux
        ox, oy = label_pos or ((ln.x1 + ln.x2) / 2, (ln.y1 + ln.y2) / 2)
        off = (ox - ln.x1) * nx + (oy - ln.y1) * ny
        pA = (ln.x1 + nx * off, ln.y1 + ny * off)
        pB = (ln.x2 + nx * off, ln.y2 + ny * off)
        spA = self._w2s(*pA);
        spB = self._w2s(*pB)
        mx = (spA[0] + spB[0]) / 2;
        my = (spA[1] + spB[1]) / 2
        return spA, spB, mx, my

    def _distance_dim_screen_geom(self, ent):
        a, b = ent["a"], ent["b"]

        d0, px, py, qx, qy = _closest_points_between_segments((a.x1, a.y1), (a.x2, a.y2), (b.x1, b.y1), (b.x2, b.y2))
        ux, uy, ul = _norm(a.x2 - a.x1, a.y2 - a.y1)
        if ul < 1e-9:
            ux, uy, ul = _norm(b.x2 - b.x1, b.y2 - b.y1)
            if ul < 1e-9:
                nx, ny, _ = _norm(qx - px, qy - py)
                ux, uy = -ny, nx
        mx0, my0 = (px + qx) / 2, (py + qy) / 2
        lp = ent.get("label", (mx0, my0))
        slide = (lp[0] - mx0) * ux + (lp[1] - my0) * uy
        pA = (px + ux * slide, py + uy * slide)
        pB = (qx + ux * slide, qy + uy * slide)
        spA = self._w2s(*pA);
        spB = self._w2s(*pB)
        mx = (spA[0] + spB[0]) / 2;
        my = (spA[1] + spB[1]) / 2
        return spA, spB, mx, my

    def _angle_label_world(self, ent):
        a, b = ent["a"], ent["b"];
        vx, vy = ent["vx"], ent["vy"]
        ax, ay = self._out_vec(a, vx, vy);
        bx, by = self._out_vec(b, vx, vy)
        ax, ay, _ = _norm(ax, ay);
        bx, by, _ = _norm(bx, by)
        side = ent.get("side", 1)
        if side >= 0:
            bdx, bdy, bl = _norm(ax + bx, ay + by)
            if bl < 1e-9: bdx, bdy, _ = _norm(ax, ay)
        else:
            bdx, bdy, bl = _norm(ax - bx, ay - by)
            if bl < 1e-9: bdx, bdy, _ = _norm(ax, ay)
        off = float(ent.get("off", 0.75))
        return (vx + bdx * off, vy + bdy * off)

    def _hit_test_all_dims(self, ex, ey):

        for ln, meta in self.app.fixed_lengths.items():
            g = self._length_dim_screen_geom(ln, meta.get("label"))
            if not g: continue
            spA, spB, mx, my = g
            if self._near_screen_seg(ex, ey, spA[0], spA[1], spB[0], spB[1], tol=8) or self._near_screen_pt(ex, ey, mx,
                                                                                                            my, r=10):
                return "len", ln

        for idx, ent in enumerate(self.app.distance_constraints):
            spA, spB, mx, my = self._distance_dim_screen_geom(ent)
            if self._near_screen_seg(ex, ey, spA[0], spA[1], spB[0], spB[1], tol=8) or self._near_screen_pt(ex, ey, mx,
                                                                                                            my, r=10):
                return "dist", idx

        for idx, ent in enumerate(self.app.angle_constraints):
            lx, ly = self._angle_label_world(ent)
            slx, sly = self._w2s(lx, ly)
            if self._near_screen_pt(ex, ey, slx, sly, r=12):
                return "ang", idx
        return None, None

    def pre_handle_mouse_move(self, e):
        ex, ey = e.x, e.y
        kind, ident = self._hit_test_all_dims(ex, ey)
        self._hover_kind, self._hover_id = kind, ident

        if self._drag_active:
            self._apply_drag_update(e)
            self.app._request_redraw()
            return True

        self.app._request_redraw()
        return False

    def pre_handle_mouse_down(self, e):
        ex, ey = e.x, e.y
        ctrl = bool(e.state & 0x0004)                               

        kind, ident = self._hit_test_all_dims(ex, ey)

        if kind is None:
            if not ctrl:

                self._selected_kind = None
                self._selected_id = None
                self._multi_selected_dims.clear()
                self.app._request_redraw()
            return False

        if ctrl:
            key = (kind, ident)
            if key in self._multi_selected_dims:
                self._multi_selected_dims.remove(key)
            else:
                self._multi_selected_dims.add(key)

            self._selected_kind = kind
            self._selected_id = ident

            self._drag_active = False
            self._drag_kind = None
            self._drag_id = None
            self.app._request_redraw()
            return True

        self._multi_selected_dims.clear()
        self._multi_selected_dims.add((kind, ident))

        self._selected_kind = kind
        self._selected_id = ident

        self._drag_kind, self._drag_id = kind, ident
        self._drag_active = True
        self.app._push_undo()
        self.app._request_redraw()
        return True

    def pre_handle_mouse_drag(self, e):
        if not self._drag_active:
            return False
        self._apply_drag_update(e)
        self.app._request_redraw()
        return True

    def pre_handle_mouse_up(self, e):
        if not self._drag_active:
            return False
        self._drag_active = False
        self._drag_kind = None
        self._drag_id = None
        self.app._request_tree_update()
        self.app._request_redraw()
        return True

    def _apply_drag_update(self, e):
        wx, wy = self.app.vp.screen_to_world(e.x, e.y)
        if self._drag_kind == "len" and self._drag_id is not None:
            ln = self._drag_id

            dx, dy = ln.x2 - ln.x1, ln.y2 - ln.y1
            ux, uy, L = _norm(dx, dy)
            if L < 1e-9: return
            nx, ny = -uy, ux

            off = (wx - ln.x1) * nx + (wy - ln.y1) * ny
            mx = (ln.x1 + ln.x2) / 2;
            my = (ln.y1 + ln.y2) / 2
            new_label = (mx + 0 * ux + 0 * uy + nx * (off - ((mx - ln.x1) * nx + (my - ln.y1) * ny)),
                         my + 0 * ux + 0 * uy + ny * (off - ((mx - ln.x1) * nx + (my - ln.y1) * ny)))
            self.app.fixed_lengths[ln]["label"] = new_label

        elif self._drag_kind == "dist" and self._drag_id is not None:
            ent = self.app.distance_constraints[self._drag_id]

            a, b = ent["a"], ent["b"]
            d0, px, py, qx, qy = _closest_points_between_segments((a.x1, a.y1), (a.x2, a.y2), (b.x1, b.y1),
                                                                  (b.x2, b.y2))
            ux, uy, ul = _norm(a.x2 - a.x1, a.y2 - a.y1)
            if ul < 1e-9:
                ux, uy, ul = _norm(b.x2 - b.x1, b.y2 - b.y1)
                if ul < 1e-9:
                    nx, ny, _ = _norm(qx - px, qy - py)
                    ux, uy = -ny, nx
            mx0, my0 = (px + qx) / 2, (py + qy) / 2
            slide = (wx - mx0) * ux + (wy - my0) * uy
            ent["label"] = (mx0 + ux * slide, my0 + uy * slide)

        elif self._drag_kind == "ang" and self._drag_id is not None:
            ent = self.app.angle_constraints[self._drag_id]
            a, b, vx, vy = ent["a"], ent["b"], ent["vx"], ent["vy"]
            ax, ay = self._out_vec(a, vx, vy);
            bx, by = self._out_vec(b, vx, vy)
            ax, ay, _ = _norm(ax, ay);
            bx, by, _ = _norm(bx, by)

            side, bdx, bdy = self._angle_side_choice(vx, vy, ax, ay, bx, by, (wx, wy))
            off = (wx - vx) * bdx + (wy - vy) * bdy
            if off < 0.25: off = 0.75
            ent["side"] = side
            ent["off"] = float(off)

    def pre_handle_double_click(self, e):
        ex, ey = e.x, e.y
        kind, ident = self._hit_test_all_dims(ex, ey)

        if kind is None:
            return False

        self.app._push_undo()

        if kind == "len" and ident is not None:
            ln = ident
            cur = self.app.fixed_lengths.get(ln, {}).get("len", ln.length())
            def apply_value(val):
                if val is None or val <= 0:
                    self.app._request_tree_update()
                    self.app._request_redraw()
                    return
                self.app.fixed_lengths[ln]["len"] = float(val)

                ok = True
                try:
                    ok = bool(self.app.apply_length_dimension(ln, float(val)))
                except Exception:
                    ok = False

                if not ok:
                    try:
                        self.app.on_undo()
                    except Exception:
                        pass
                    notify_error(
                        self.app,
                        "Length constraint conflict",
                        "That length would modify an existing dimension/constraint.\n\nNo changes were applied.",
                    )
                self.app._request_tree_update()
                self.app._request_redraw()

            if self._request_float_async("Edit Length", "Enter length:", cur, apply_value):
                return True

            apply_value(self._prompt_float("Edit Length", "Enter length:", cur))

        elif kind == "ang" and isinstance(ident, int):
            if 0 <= ident < len(self.app.angle_constraints):
                ent = self.app.angle_constraints[ident]
                cur = ent.get("deg", 90.0)
                def apply_value(val):
                    if val is None or not (0 < val < 180):
                        self.app._request_tree_update()
                        self.app._request_redraw()
                        return
                    old = float(ent.get("deg", 90.0))
                    new = float(val)

                    ent["deg"] = new

                    ok = None

                    if hasattr(self.app, "apply_angle_dimension"):
                        try:
                            ok = self.app.apply_angle_dimension(ent["a"], ent["b"], ent["vx"], ent["vy"], new)
                        except Exception:
                            ok = False
                    elif hasattr(self.app, "dimension_rules") and hasattr(self.app.dimension_rules, "apply_angle_dimension"):
                        try:
                            ok = self.app.dimension_rules.apply_angle_dimension(
                                ent["a"], ent["b"], ent["vx"], ent["vy"], new
                            )
                        except Exception:
                            ok = False
                    else:
                        self.app._apply_angle_constraint(ent["a"], ent["b"], ent["vx"], ent["vy"], new)
                        ok = True

                    if ok is False:
                        ent["deg"] = old
                        try:
                            self.app.on_undo()
                        except Exception:
                            pass
                        notify_error(
                            self.app,
                            "Angle edit failed",
                            "That angle change conflicts with existing constraints/dimensions.",
                        )

                    self.app._request_tree_update()
                    self.app._request_redraw()

                if self._request_float_async("Edit Angle", "Enter angle (degrees):", cur, apply_value):
                    return True

                apply_value(self._prompt_float("Edit Angle", "Enter angle (degrees):", cur))

        elif kind == "dist" and isinstance(ident, int):
            if 0 <= ident < len(self.app.distance_constraints):
                ent = self.app.distance_constraints[ident]
                cur = ent.get("dist", 0.0)
                def apply_value(val):
                    if val is None or val < 0:
                        self.app._request_tree_update()
                        self.app._request_redraw()
                        return
                    ent["dist"] = float(val)
                    Pa, Pb = self.app.apply_distance_dimension(ent["a"], ent["b"], float(val))

                    ent["Pa"] = Pa
                    ent["Pb"] = Pb
                    self.app._request_tree_update()
                    self.app._request_redraw()

                if self._request_float_async("Edit Distance", "Enter distance:", cur, apply_value):
                    return True

                apply_value(self._prompt_float("Edit Distance", "Enter distance:", cur))

        return True

    def delete_selected_dimension(self):
        if not hasattr(self, '_selected_kind') or self._selected_kind is None:
            return False

        kind = self._selected_kind
        ident = self._selected_id

        self.app._push_undo()

        if kind == "len" and ident is not None:
            self.app.fixed_lengths.pop(ident, None)

        elif kind == "ang" and isinstance(ident, int):
            if 0 <= ident < len(self.app.angle_constraints):
                self.app.angle_constraints.pop(ident)

        elif kind == "dist" and isinstance(ident, int):
            if 0 <= ident < len(self.app.distance_constraints):
                self.app.distance_constraints.pop(ident)

        self._selected_kind = None
        self._selected_id = None
        self._hover_kind = None
        self._hover_id = None

        self.app._request_tree_update()
        self.app._request_redraw()
        return True

    def _get_selected_dimensions(self):
        return self._multi_selected_dims.copy()

    def clear_dimension_selection(self):
        self._multi_selected_dims.clear()
        self._selected_kind = None
        self._selected_id = None

