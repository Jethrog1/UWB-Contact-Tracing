import math

EPS = 1e-9

class DimensionErrors:
    """
    DimensionErrors: a non-invasive "referee" for dimension clashes.

    Philosophy:
      - Never changes your existing dimensioning rules.
      - It simply snapshots state -> lets the rule run -> validates ALL existing constraints.
      - If ANY old constraint is violated, it rolls back and reports an error.

    Also hosts the "width retry" behavior:
      - Try user selection order (first is base, second moves)
      - If that breaks ANY old constraint -> rollback and try swapped
      - If both break -> rollback and fail
    """

    def __init__(self, app):
        self.app = app

    # -------------------------
    # Snapshot / restore (in-place)
    # -------------------------
    def snap_state_inplace(self):
        import copy
        app = self.app
        return {
            "line_xy": [(ln, ln.x1, ln.y1, ln.x2, ln.y2, getattr(ln, "color", None)) for ln in list(app.lines)],
            "fixed_lengths": {ln: dict(ent) for ln, ent in dict(getattr(app, "fixed_lengths", {})).items()},
            "angle_constraints": copy.deepcopy(list(getattr(app, "angle_constraints", []))),
            "distance_constraints": copy.deepcopy(list(getattr(app, "distance_constraints", []))),
            "_solver_drag_lines": getattr(app, "_solver_drag_lines", set()).copy() if hasattr(app, "_solver_drag_lines") else set(),
        }

    def restore_state_inplace(self, snap):
        import copy
        app = self.app

        try:
            for ln, x1, y1, x2, y2, col in snap["line_xy"]:
                ln.x1, ln.y1, ln.x2, ln.y2 = x1, y1, x2, y2
                if col is not None:
                    ln.color = col
        except Exception:
            pass

        app.fixed_lengths = {ln: dict(ent) for ln, ent in snap["fixed_lengths"].items()}
        app.angle_constraints = copy.deepcopy(list(snap["angle_constraints"]))
        app.distance_constraints = copy.deepcopy(list(snap["distance_constraints"]))
        if hasattr(app, "_solver_drag_lines"):
            app._solver_drag_lines = set(snap.get("_solver_drag_lines", set()))

    # -------------------------
    # Popup helper
    # -------------------------
    def post_error(self, title, msg):
        try:
            import tkinter.messagebox as messagebox
            messagebox.showerror(title, msg)
        except Exception:
            pass

    # -------------------------
    # Constraint validation
    # -------------------------
    def _angle_between_lines_at_vertex(self, A, B, vx, vy):
        def out_vec(ln):
            if abs(ln.x1 - vx) < 1e-6 and abs(ln.y1 - vy) < 1e-6:
                return (ln.x2 - vx, ln.y2 - vy)
            return (ln.x1 - vx, ln.y1 - vy)

        ax, ay = out_vec(A)
        bx, by = out_vec(B)

        la = math.hypot(ax, ay)
        lb = math.hypot(bx, by)
        if la < EPS or lb < EPS:
            return 0.0

        ax, ay = ax / la, ay / la
        bx, by = bx / lb, by / lb
        d = max(-1.0, min(1.0, ax * bx + ay * by))
        return math.degrees(math.acos(d))

    def check_all_constraints_ok(self, except_dist_pair=None, len_tol=1e-3, dist_tol=1e-3, ang_tol=2.0):
        """
        Returns True if ALL constraints are satisfied.

        Tolerances are intentionally relaxed to match legacy behavior:
          - Your solvers often land near-exact (not perfectly exact) due to iterative / float drift.
          - We only want to error on REAL clashes, not tiny numerical noise.

        except_dist_pair:
          - tuple(LineA, LineB) to ignore an *existing* distance constraint between them.
            Important when we are applying/editing that same width dimension.
        """
        app = self.app

        # 1) fixed lengths
        for ln, meta in getattr(app, "fixed_lengths", {}).items():
            try:
                want = float(meta.get("len", 0.0))
            except Exception:
                return False
            if want <= 0:
                continue
            got = ln.length()
            if abs(got - want) > len_tol:
                return False

        # 2) distances
        try:
            from dimension_tool import _closest_points_between_segments
        except Exception:
            _closest_points_between_segments = None

        for ent in getattr(app, "distance_constraints", []):
            a = ent.get("a")
            b = ent.get("b")
            if a is None or b is None:
                continue

            if except_dist_pair is not None:
                x, y = except_dist_pair
                if (a is x and b is y) or (a is y and b is x):
                    continue

            try:
                want = float(ent.get("dist", 0.0))
            except Exception:
                return False

            if _closest_points_between_segments is None:
                return False

            try:
                d0, *_ = _closest_points_between_segments(
                    (a.x1, a.y1), (a.x2, a.y2),
                    (b.x1, b.y1), (b.x2, b.y2),
                )
            except Exception:
                return False

            if abs(float(d0) - want) > dist_tol:
                return False

        # 3) angles
        for ent in getattr(app, "angle_constraints", []):
            a = ent.get("a")
            b = ent.get("b")
            if a is None or b is None:
                continue
            try:
                vx = float(ent.get("vx", 0.0))
                vy = float(ent.get("vy", 0.0))
                want = float(ent.get("deg", 0.0))
            except Exception:
                return False

            got = self._angle_between_lines_at_vertex(a, b, vx, vy)

            # Normalize to smallest equivalent difference (helps around 0/180)
            diff = abs(got - want)
            if diff > 180:
                diff = 360 - diff

            if diff > ang_tol:
                return False

        return True

    # -------------------------
    # Generic "run rule then verify"
    # -------------------------
    def run_rule_with_guard(self, title, msg, rule_fn, except_dist_pair=None):
        """
        rule_fn: callable that performs the change (using your existing logic).
        If it breaks ANY existing constraint, rollback and show error.
        Returns True on success, False on rollback.
        """
        snap = self.snap_state_inplace()
        try:
            rule_fn()
            if not self.check_all_constraints_ok(except_dist_pair=except_dist_pair):
                self.restore_state_inplace(snap)
                self.post_error(title, msg)
                return False
            return True
        except Exception:
            self.restore_state_inplace(snap)
            self.post_error(title, msg)
            return False

    # -------------------------
    # Width/distance apply with retry (selection-order guard)
    # -------------------------
    def apply_distance_with_retry(self, rules, a, b, target_dist, apply_once_fn, closest_fn):
        """
        apply_once_fn(base, move, target_dist) -> (Pa, Pb)
          - does ONE attempt (base fixed, move altered) using your current rules.

        closest_fn(a, b) -> (Pa, Pb)
          - returns closest points between the actual a/b after success.
        """
        target_dist = float(target_dist)

        def attempt(base, move):
            snap = self.snap_state_inplace()
            try:
                apply_once_fn(base, move, target_dist)
                if not self.check_all_constraints_ok(except_dist_pair=(a, b)):
                    self.restore_state_inplace(snap)
                    return None, None
                return closest_fn(a, b)
            except Exception:
                self.restore_state_inplace(snap)
                return None, None

        # try user order first
        Pa, Pb = attempt(a, b)
        if Pa is not None and Pb is not None:
            return Pa, Pb

        # try swapped
        Pa, Pb = attempt(b, a)
        if Pa is not None and Pb is not None:
            return Pa, Pb

        self.post_error(
            "Distance constraint conflict",
            "That width/distance would modify an existing dimension/constraint.\n\nNo changes were applied."
        )
        return None, None


class DimensionRules:
    """
    Centralized "dimension application rules" layer.

    Goal: applying a dimension should behave like precise manual manipulation:
      - protect any preset dimensions/constraints
      - avoid unwanted rotation/drift
      - when possible, drive a closed rectangle by moving its vertices like a user drag would
    """

    def __init__(self, app):
        self.app = app
        self.errors = DimensionErrors(app)

    # -------------------------
    # Public API
    # -------------------------
    def apply_length_dimension(self, ln, target_len):
        """
        Apply a length dimension without breaking existing constraints.

        - Keeps the existing rectangle rule for fully 90°-dimensioned rectangles.
        - Otherwise applies length using a "manual drag" style move:
            * If the line touches any angle constraints, try anchoring one endpoint and
              dragging the other along the line direction (both directions, retry).
            * Fall back to midpoint-resize driver for unconstrained cases.
        - Returns False if it cannot satisfy the new length while keeping all existing
          dimensions/constraints valid.
        """
        if ln is None:
            return False

        try:
            target_len = float(target_len)
        except Exception:
            return False
        if target_len <= 0:
            return False

        app = self.app

        # --- helpers ---
        def snap_state():
            return app._snapshot_state()

        def restore_state(snap):
            app._restore_state(snap)

        def line_has_angle_at_endpoints(L):
            # True if any angle constraint references this line and is anchored at (approximately)
            # either endpoint of the line.
            x1, y1 = L.x1, L.y1
            x2, y2 = L.x2, L.y2
            for ent in getattr(app, "angle_constraints", []):
                try:
                    a = ent.get("a")
                    b = ent.get("b")
                    if (a is not L) and (b is not L):
                        continue
                    vx = float(ent.get("vx"))
                    vy = float(ent.get("vy"))
                    if (vx - x1) * (vx - x1) + (vy - y1) * (vy - y1) <= 1e-6:
                        return True
                    if (vx - x2) * (vx - x2) + (vy - y2) * (vy - y2) <= 1e-6:
                        return True
                except Exception:
                    continue
            return False

        # --- rectangle rule stays exactly as-is ---
        loop = self._find_right_angle_rect_loop(ln)
        if loop:
            snap = snap_state()
            self._rect_set_edge_length(loop, ln, float(target_len))
            if not self._constraints_satisfied():
                restore_state(snap)
                return False
            return True

        # --- non-rectangle: prefer "vertex drag" style if angles are involved ---
        snap = snap_state()

        if line_has_angle_at_endpoints(ln):
            if self._set_line_length_by_drag_endpoint(ln, float(target_len), anchor_end="p1", iterations=18):
                if self._constraints_satisfied():
                    return True
            restore_state(snap)

            snap = snap_state()
            if self._set_line_length_by_drag_endpoint(ln, float(target_len), anchor_end="p2", iterations=18):
                if self._constraints_satisfied():
                    return True
            restore_state(snap)

        # --- fallback: midpoint driver (original behavior) ---
        snap = snap_state()
        self._set_line_length_as_driver(ln, float(target_len), iterations=12)
        if not self._constraints_satisfied():
            restore_state(snap)
            return False

        return True

    def apply_distance_dimension(self, a, b, target_dist):
        """
        Rule v1 (Right-angle rectangle width/height):
        If a and b are opposite sides of the same 90°-dimensioned rectangle loop:
          - lock axis-aligned (no rotation)
          - preserve the other rectangle dimension (prefer fixed length dims if present)
          - set distance between those opposite sides to target_dist
        Otherwise fallback to app._apply_distance_constraint.
        """
        if a is None or b is None:
            return None, None

        def apply_once(base_ln, move_ln, dist):
            loop = self._find_right_angle_rect_loop(base_ln)
            if loop and (move_ln in loop):
                ok = self._rect_set_distance_between_opposites(loop, base_ln, move_ln, float(dist))
                if ok:
                    return self._closest_points_between_lines(a, b)
            return self.app._apply_distance_constraint(base_ln, move_ln, float(dist))

        return self.errors.apply_distance_with_retry(
            self,
            a, b, float(target_dist),
            apply_once_fn=apply_once,
            closest_fn=self._closest_points_between_lines
        )

    def apply_angle_dimension(self, lnA, lnB, vx, vy, target_deg):
        """
        Angle dimension rules (v2 - FIXED TRIANGLE CASE):

        The core principle: if manual vertex manipulation can achieve a configuration,
        the dimension system should also succeed using the same mechanism.

        Strategy:
          1. Try rotating line B with A as driver (standard case)
          2. Try rotating line A with B as driver (swapped)
          3. TRIANGLE RULE: If both legs are fixed-length, identify the opposite edge
             and make it the ONLY drag line, allowing it to absorb all changes
          4. Use increased solver iterations for challenging cases
        """

        app = self.app
        if lnA is None or lnB is None:
            return False

        target_deg = float(target_deg)
        if target_deg <= 0.0 or target_deg >= 180.0:
            return False

        # ---------- helpers (local) ----------
        def snap_state():
            return app._snapshot_state()

        def restore_state(snap):
            app._restore_state(snap)

        def other_endpoint(ln, vx0, vy0):
            if math.hypot(ln.x1 - vx0, ln.y1 - vy0) <= 1e-6:
                return (ln.x2, ln.y2)
            return (ln.x1, ln.y1)

        def angle_between_at_vertex(a, b, vx0, vy0):
            def out_vec(ln):
                if math.hypot(ln.x1 - vx0, ln.y1 - vy0) <= 1e-6:
                    return (ln.x2 - vx0, ln.y2 - vy0)
                return (ln.x1 - vx0, ln.y1 - vy0)

            ax, ay = out_vec(a)
            bx, by = out_vec(b)
            la = math.hypot(ax, ay)
            lb = math.hypot(bx, by)
            if la < 1e-9 or lb < 1e-9:
                return 0.0
            ax, ay = ax / la, ay / la
            bx, by = bx / lb, by / lb
            d = max(-1.0, min(1.0, ax * bx + ay * by))
            return math.degrees(math.acos(d))

        def check_all_constraints_ok(except_pair=None, angle_tol=0.75, len_tol=1e-3, dist_tol=1e-3):
            # except_pair: (lnA, lnB, vx, vy) to exclude the one we're currently applying
            # 1) fixed lengths
            for ln, meta in list(app.fixed_lengths.items()):
                try:
                    want = float(meta.get("len", 0.0))
                    if want <= 0:
                        continue
                    got = ln.length()
                    if abs(got - want) > len_tol:
                        return False
                except Exception:
                    return False

            # 2) distances
            for ent in list(app.distance_constraints):
                try:
                    a = ent["a"]
                    b = ent["b"]
                    want = float(ent["dist"])
                    from dimension_tool import _closest_points_between_segments
                    d0, *_ = _closest_points_between_segments(
                        (a.x1, a.y1), (a.x2, a.y2),
                        (b.x1, b.y1), (b.x2, b.y2),
                    )
                    if abs(d0 - want) > dist_tol:
                        return False
                except Exception:
                    return False

            # 3) angles
            for ent in list(app.angle_constraints):
                try:
                    a = ent["a"]
                    b = ent["b"]
                    ex = float(ent["vx"])
                    ey = float(ent["vy"])
                    want = float(ent["deg"])

                    if except_pair is not None:
                        ea, eb, evx, evy = except_pair
                        same_lines = ((a is ea and b is eb) or (a is eb and b is ea))
                        if same_lines and math.hypot(ex - evx, ey - evy) <= 1e-6:
                            continue

                    got = angle_between_at_vertex(a, b, ex, ey)
                    if abs(got - want) > angle_tol:
                        return False
                except Exception:
                    return False

            return True

        def run_strategy(pre_keep, pre_rotate, active_drag_lines, iterations=18):
            snap = snap_state()
            prev_active = getattr(app, "_solver_drag_lines", set())

            try:
                # 1) One-shot rotate to get close
                app._apply_angle_constraint(pre_keep, pre_rotate, vx, vy, target_deg)

                # 2) Solve with chosen driver set
                app._solver_drag_lines = set(active_drag_lines) if active_drag_lines else set()
                app._solve_constraints(int(iterations))

                # 3) Validate all existing constraints still satisfied
                if not check_all_constraints_ok(except_pair=(lnA, lnB, vx, vy)):
                    restore_state(snap)
                    return False

                return True
            finally:
                app._solver_drag_lines = prev_active

        # ---------- Decide which rule applies ----------

        fixedA = lnA in app.fixed_lengths
        fixedB = lnB in app.fixed_lengths

        # TRIANGLE RULE (FIXED):
        # If both legs are length-constrained, the only way to change the angle
        # is to adjust the opposite edge (the edge connecting the two non-vertex endpoints).
        # This matches what happens during manual vertex dragging.
        if fixedA and fixedB:
            pa = other_endpoint(lnA, vx, vy)
            pb = other_endpoint(lnB, vx, vy)

            def pts_match(p, q, tol=1e-6):
                return math.hypot(p[0] - q[0], p[1] - q[1]) <= tol

            # Find the line connecting the two opposite endpoints
            tri_opposite = None
            for ln in list(app.lines):
                if ln is lnA or ln is lnB:
                    continue
                p1 = (ln.x1, ln.y1)
                p2 = (ln.x2, ln.y2)
                if (pts_match(p1, pa) and pts_match(p2, pb)) or (pts_match(p1, pb) and pts_match(p2, pa)):
                    tri_opposite = ln
                    break

            if tri_opposite is not None:
                # KEY FIX: Use MORE iterations and make ONLY the opposite edge the drag line
                # This allows the solver to find the solution that manual dragging would find
                if run_strategy(lnA, lnB, {tri_opposite}, iterations=30):
                    return True
                # Also try swapped rotation direction
                if run_strategy(lnB, lnA, {tri_opposite}, iterations=30):
                    return True

        # Standard case: try rotating one line while the other is kept
        if run_strategy(lnA, lnB, {lnB}, iterations=22):
            return True
        if run_strategy(lnB, lnA, {lnA}, iterations=22):
            return True

        # Last resort: allow both lines as drag lines (more freedom)
        if run_strategy(lnA, lnB, {lnA, lnB}, iterations=28):
            return True

        return False

    # -------------------------
    # Rectangle detection
    # -------------------------
    def _find_right_angle_rect_loop(self, seed_line):
        loop = self._find_4_cycle_including_line(seed_line)
        if not loop:
            return None

        vmap = self._loop_vertex_incidence(loop)
        if len(vmap) != 4:
            return None
        for _, inc in vmap.items():
            if len(inc) != 2:
                return None

        for vkey, inc in vmap.items():
            vx, vy = vkey
            l1, l2 = inc[0], inc[1]
            if not self._has_angle_constraint_at_vertex(l1, l2, vx, vy, 90.0, deg_tol=0.75):
                return None

        return loop

    def _find_4_cycle_including_line(self, ln):
        app = self.app
        v_to_lines = {}
        for L in app.lines:
            v_to_lines.setdefault(app._vkey(L.x1, L.y1), []).append(L)
            v_to_lines.setdefault(app._vkey(L.x2, L.y2), []).append(L)

        a = app._vkey(ln.x1, ln.y1)
        b = app._vkey(ln.x2, ln.y2)

        for start_v, next_v in ((a, b), (b, a)):
            path = [ln]
            prev = ln
            cur_v = next_v

            ok = True
            for _ in range(3):
                cand = [L for L in v_to_lines.get(cur_v, []) if L is not prev]
                if not cand:
                    ok = False
                    break

                nxt = None
                for L in cand:
                    if L not in path:
                        nxt = L
                        break
                if nxt is None:
                    ok = False
                    break

                path.append(nxt)

                v1 = app._vkey(nxt.x1, nxt.y1)
                v2 = app._vkey(nxt.x2, nxt.y2)
                cur_v = v2 if v1 == cur_v else v1
                prev = nxt

            if not ok:
                continue
            if cur_v != start_v:
                continue
            if len(set(path)) != 4:
                continue

            return path

        return None

    def _loop_vertex_incidence(self, loop):
        app = self.app
        vmap = {}
        for L in loop:
            vmap.setdefault(app._vkey(L.x1, L.y1), []).append(L)
            vmap.setdefault(app._vkey(L.x2, L.y2), []).append(L)
        return vmap

    def _has_angle_constraint_at_vertex(self, l1, l2, vx, vy, target_deg, deg_tol=0.75, vtol=1e-3):
        app = self.app

        def same_lines(ent):
            return (ent.get("a") is l1 and ent.get("b") is l2) or (ent.get("a") is l2 and ent.get("b") is l1)

        for ent in app.angle_constraints:
            try:
                if not same_lines(ent):
                    continue
                if abs(float(ent.get("deg", 0.0)) - float(target_deg)) > deg_tol:
                    continue
                ex = float(ent.get("vx", 1e9))
                ey = float(ent.get("vy", 1e9))
                if math.hypot(ex - vx, ey - vy) <= vtol:
                    return True
                if self._lines_share_vertex_near(l1, l2, vx, vy, tol=vtol):
                    return True
            except Exception:
                pass

        return False

    def _lines_share_vertex_near(self, l1, l2, vx, vy, tol=1e-3):
        pts1 = [(l1.x1, l1.y1), (l1.x2, l1.y2)]
        pts2 = [(l2.x1, l2.y1), (l2.x2, l2.y2)]
        for ax, ay in pts1:
            for bx, by in pts2:
                if math.hypot(ax - bx, ay - by) <= tol and math.hypot(ax - vx, ay - vy) <= tol:
                    return True
        return False

    # -------------------------
    # Rectangle axis lock + preserve dimensions
    # -------------------------
    def _rect_vertices(self, loop):
        pts = []
        seen = set()
        for L in loop:
            for p in ((L.x1, L.y1), (L.x2, L.y2)):
                k = self.app._vkey(p[0], p[1])
                if k in seen:
                    continue
                seen.add(k)
                pts.append((p[0], p[1]))
        return pts

    def _group_by_center(self, pts):
        cx = sum(p[0] for p in pts) / 4.0
        cy = sum(p[1] for p in pts) / 4.0
        out = {}
        for x, y in pts:
            left = x <= cx
            top = y <= cy  # in your world, +Y is down => smaller y is "top"
            if left and top:
                out["TL"] = (x, y)
            elif (not left) and top:
                out["TR"] = (x, y)
            elif (not left) and (not top):
                out["BR"] = (x, y)
            else:
                out["BL"] = (x, y)
        return out, cx, cy

    def _axis_aligned_extents(self, pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        left = min(xs)
        right = max(xs)
        top = min(ys)
        bottom = max(ys)
        cx = (left + right) * 0.5
        cy = (top + bottom) * 0.5
        w = right - left
        h = bottom - top
        return left, right, top, bottom, cx, cy, w, h

    def _is_horizontalish(self, L):
        return abs(L.x2 - L.x1) >= abs(L.y2 - L.y1)

    def _rect_fixed_dims(self, loop):
        """
        Returns (w_fixed, h_fixed) from existing fixed length dimensions on the loop if present.
        """
        app = self.app
        w_vals = []
        h_vals = []
        for L in loop:
            if L in app.fixed_lengths:
                try:
                    val = float(app.fixed_lengths[L].get("len", 0.0))
                except Exception:
                    val = 0.0
                if val <= 0:
                    continue
                if self._is_horizontalish(L):
                    w_vals.append(val)
                else:
                    h_vals.append(val)

        w_fixed = (sum(w_vals) / len(w_vals)) if w_vals else None
        h_fixed = (sum(h_vals) / len(h_vals)) if h_vals else None
        return w_fixed, h_fixed

    def _rect_set_edge_length(self, loop, driver_ln, new_len):
        """
        Driver for length dimensions on a rectangle:
          - if driver is horizontal-ish => width=new_len, height preserved
          - if driver is vertical-ish   => height=new_len, width preserved
        """
        pts = self._rect_vertices(loop)
        if len(pts) != 4:
            return False

        left0, right0, top0, bottom0, cx, cy, w0, h0 = self._axis_aligned_extents(pts)
        if abs(w0) < EPS or abs(h0) < EPS:
            return False

        w_fixed, h_fixed = self._rect_fixed_dims(loop)

        if self._is_horizontalish(driver_ln):
            w1 = float(new_len)
            h1 = float(h_fixed) if (h_fixed is not None) else float(h0)
        else:
            h1 = float(new_len)
            w1 = float(w_fixed) if (w_fixed is not None) else float(w0)

        left1 = cx - w1 * 0.5
        right1 = cx + w1 * 0.5
        top1 = cy - h1 * 0.5
        bottom1 = cy + h1 * 0.5

        corners = {"TL": (left1, top1), "TR": (right1, top1), "BR": (right1, bottom1), "BL": (left1, bottom1)}
        self._apply_rect_corners(loop, corners, iterations=10)
        return True

    def _rect_set_distance_between_opposites(self, loop, a, b, target_dist):
        """
        If a/b are opposite horizontals => set HEIGHT to target_dist.
        If a/b are opposite verticals   => set WIDTH to target_dist.
        Keeps other dimension constant (prefers fixed dims), locks axis, keeps center fixed.
        """
        pts = self._rect_vertices(loop)
        if len(pts) != 4:
            return False

        left0, right0, top0, bottom0, cx, cy, w0, h0 = self._axis_aligned_extents(pts)
        if abs(w0) < EPS or abs(h0) < EPS:
            return False

        w_fixed, h_fixed = self._rect_fixed_dims(loop)

        ah = self._is_horizontalish(a)
        bh = self._is_horizontalish(b)

        if ah != bh:
            return False

        if ah:
            h1 = float(target_dist)
            w1 = float(w_fixed) if (w_fixed is not None) else float(w0)
        else:
            w1 = float(target_dist)
            h1 = float(h_fixed) if (h_fixed is not None) else float(h0)

        left1 = cx - w1 * 0.5
        right1 = cx + w1 * 0.5
        top1 = cy - h1 * 0.5
        bottom1 = cy + h1 * 0.5

        corners = {"TL": (left1, top1), "TR": (right1, top1), "BR": (right1, bottom1), "BL": (left1, bottom1)}
        self._apply_rect_corners(loop, corners, iterations=10)
        return True

    def _apply_rect_corners(self, loop, corners, iterations=10):
        """
        Moves the four rectangle vertices to TL/TR/BR/BL coords.
        Uses weld propagation and then solves constraints with loop lines marked as "drag".
        """
        app = self.app
        pts = self._rect_vertices(loop)
        cls, _, _ = self._group_by_center(pts)

        move_list = []
        for key in ("TL", "TR", "BR", "BL"):
            if key not in cls:
                return False
            ox, oy = cls[key]
            nx, ny = corners[key]
            move_list.append((ox, oy, nx, ny))

        for ox, oy, nx, ny in move_list:
            app._weld_propagate_vertex_move(ox, oy, nx, ny, ignore_line=None)

        corner_pts = list(corners.values())

        def nearest_corner(x, y):
            best = None
            bd = 1e18
            for cx, cy in corner_pts:
                d = (x - cx) * (x - cx) + (y - cy) * (y - cy)
                if d < bd:
                    bd = d
                    best = (cx, cy)
            return best

        for L in loop:
            p1 = nearest_corner(L.x1, L.y1)
            p2 = nearest_corner(L.x2, L.y2)
            L.x1, L.y1 = p1
            L.x2, L.y2 = p2

        prev_active = getattr(app, "_solver_drag_lines", set())
        try:
            app._solver_drag_lines = set(loop)
            app._solve_constraints(int(iterations))
        finally:
            app._solver_drag_lines = prev_active

        return True

    # -------------------------
    # Fallback manipulation-style apply
    # -------------------------
    def _set_line_length_as_driver(self, ln, target_len, iterations=12):
        """
        Original fallback length-apply: resize about midpoint, weld endpoints, then solve with ln as the drag line.
        """
        app = self.app

        dx = ln.x2 - ln.x1
        dy = ln.y2 - ln.y1
        L = math.hypot(dx, dy)
        if L < 1e-9:
            return

        ux, uy = dx / L, dy / L
        mx, my = (ln.x1 + ln.x2) * 0.5, (ln.y1 + ln.y2) * 0.5
        half = float(target_len) * 0.5

        nx1 = mx - ux * half
        ny1 = my - uy * half
        nx2 = mx + ux * half
        ny2 = my + uy * half

        ox1, oy1, ox2, oy2 = ln.x1, ln.y1, ln.x2, ln.y2
        ln.x1, ln.y1, ln.x2, ln.y2 = nx1, ny1, nx2, ny2

        app._weld_propagate_vertex_move(ox1, oy1, nx1, ny1, ignore_line=ln)
        app._weld_propagate_vertex_move(ox2, oy2, nx2, ny2, ignore_line=ln)

        prev_active = getattr(app, "_solver_drag_lines", set())
        try:
            app._solver_drag_lines = {ln}
            app._solve_constraints(int(iterations))
        finally:
            app._solver_drag_lines = prev_active

    def _set_line_length_by_drag_endpoint(self, ln, target_len, anchor_end="p1", iterations=18):
        """
        Manual-drag style length apply:
          - Keep one endpoint fixed (anchor_end) and move the other endpoint along the current line direction
          - Move is applied via the same vertex-ref mechanism used by Manipulate Vertex
          - Solve constraints with the dragged-vertex incident lines marked as drag lines
        """
        app = self.app

        if anchor_end == "p1":
            ax, ay = ln.x1, ln.y1
            mx, my = ln.x2, ln.y2
        else:
            ax, ay = ln.x2, ln.y2
            mx, my = ln.x1, ln.y1

        dx = mx - ax
        dy = my - ay
        L = math.hypot(dx, dy)
        if L < 1e-9:
            return False

        ux, uy = dx / L, dy / L
        nx = ax + ux * float(target_len)
        ny = ay + uy * float(target_len)

        # Move the "dragged" vertex using the same refs the app uses for vertex manipulation
        try:
            refs = app._collect_vertex_refs(mx, my)
        except Exception:
            refs = None

        if not refs:
            # fallback: at least move this one endpoint on ln
            if anchor_end == "p1":
                ln.x2, ln.y2 = nx, ny
            else:
                ln.x1, ln.y1 = nx, ny
        else:
            try:
                app.snap._set_refs_vertex(refs, nx, ny)
            except Exception:
                # fallback to weld propagation if refs path isn't available
                app._weld_propagate_vertex_move(mx, my, nx, ny, ignore_line=None)

        # Build drag line set exactly like Manipulate Vertex (all lines incident to the dragged vertex)
        drag_lines = set()
        if refs:
            try:
                for Lref, _ in refs:
                    drag_lines.add(Lref)
            except Exception:
                drag_lines = {ln}
        else:
            drag_lines = {ln}

        prev_active = getattr(app, "_solver_drag_lines", set())
        try:
            app._solver_drag_lines = set(drag_lines)
            app._solve_constraints(int(iterations))
        finally:
            app._solver_drag_lines = prev_active

        return True

    def _constraints_satisfied(self, len_tol=1e-3, dist_tol=1e-3, angle_tol=0.75):
        """
        Check that all stored constraints/dimensions are currently satisfied.

        - Fixed lengths are enforced to within len_tol.
        - Distance (width) constraints are enforced to within dist_tol.
        - Angle constraints are enforced to within angle_tol (degrees).

        NOTE: This intentionally does NOT care about unconstrained line lengths/angles.
        """
        app = self.app

        # ---- fixed lengths ----
        for ln, meta in list(getattr(app, "fixed_lengths", {}).items()):
            try:
                want = float(meta.get("len", 0.0))
                if want <= 0:
                    continue
                got = ln.length()
                if abs(got - want) > float(len_tol):
                    return False
            except Exception:
                return False

        # ---- distance constraints ----
        try:
            from dimension_tool import _closest_points_between_segments
        except Exception:
            _closest_points_between_segments = None

        for ent in list(getattr(app, "distance_constraints", [])):
            try:
                a = ent["a"]
                b = ent["b"]
                want = float(ent.get("dist", 0.0))
                if _closest_points_between_segments is None:
                    continue
                d0, *_ = _closest_points_between_segments(
                    (a.x1, a.y1), (a.x2, a.y2),
                    (b.x1, b.y1), (b.x2, b.y2)
                )
                if abs(d0 - want) > float(dist_tol):
                    return False
            except Exception:
                return False

        # ---- angle constraints ----
        def out_vec(ln, vx, vy):
            if (ln.x1 - vx) * (ln.x1 - vx) + (ln.y1 - vy) * (ln.y1 - vy) <= 1e-6:
                return (ln.x2 - vx, ln.y2 - vy)
            return (ln.x1 - vx, ln.y1 - vy)

        def angle_between(a, b, vx, vy):
            ax, ay = out_vec(a, vx, vy)
            bx, by = out_vec(b, vx, vy)
            la = math.hypot(ax, ay)
            lb = math.hypot(bx, by)
            if la < 1e-9 or lb < 1e-9:
                return 0.0
            ax /= la
            ay /= la
            bx /= lb
            by /= lb
            d = max(-1.0, min(1.0, ax * bx + ay * by))
            return math.degrees(math.acos(d))

        for ent in list(getattr(app, "angle_constraints", [])):
            try:
                a = ent["a"]
                b = ent["b"]
                vx = float(ent.get("vx"))
                vy = float(ent.get("vy"))
                want = float(ent.get("deg", 0.0))
                got = angle_between(a, b, vx, vy)
                if abs(got - want) > float(angle_tol):
                    return False
            except Exception:
                return False

        return True

    # -------------------------
    # Closest points helper (for width/distance dims)
    # -------------------------
    def _closest_points_between_lines(self, a, b):
        def dot(ax, ay, bx, by):
            return ax * bx + ay * by

        ux, uy = a.x2 - a.x1, a.y2 - a.y1
        vx, vy = b.x2 - b.x1, b.y2 - b.y1
        wx, wy = a.x1 - b.x1, a.y1 - b.y1

        A = dot(ux, uy, ux, uy)
        B = dot(ux, uy, vx, vy)
        C = dot(vx, vy, vx, vy)
        D = dot(ux, uy, wx, wy)
        E = dot(vx, vy, wx, wy)

        Den = A * C - B * B
        sN, sD = 0.0, Den
        tN, tD = 0.0, Den

        if Den < EPS:
            sN = 0.0
            sD = 1.0
            tN = E
            tD = C
        else:
            sN = (B * E - C * D)
            tN = (A * E - B * D)
            if sN < 0.0:
                sN = 0.0
                tN = E
                tD = C
            elif sN > sD:
                sN = sD
                tN = E + B
                tD = C

        if tN < 0.0:
            tN = 0.0
            if -D < 0.0:
                sN = 0.0
            elif -D > A:
                sN = sD
            else:
                sN = -D
                sD = A
        elif tN > tD:
            tN = tD
            if (-D + B) < 0.0:
                sN = 0.0
            elif (-D + B) > A:
                sN = sD
            else:
                sN = (-D + B)
                sD = A

        sc = 0.0 if abs(sN) < EPS else sN / sD
        tc = 0.0 if abs(tN) < EPS else tN / tD

        Px = a.x1 + sc * ux
        Py = a.y1 + sc * uy
        Qx = b.x1 + tc * vx
        Qy = b.y1 + tc * vy

        return (Px, Py), (Qx, Qy)

#123aaaadd1122bbccdd1/1112/2