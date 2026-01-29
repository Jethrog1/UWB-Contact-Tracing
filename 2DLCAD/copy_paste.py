import math
import tkinter as tk


class CopyPasteManager:
    """Manages copying and pasting lines with their associated dimensions."""

    def __init__(self, app):
        self.app = app
        self.clipboard = None  # Will store copied data

        # Paste preview state
        self.paste_active = False
        self.paste_lines = []  # Temporary line objects for preview
        self.paste_dimensions = {}  # Store dimension metadata for preview
        self.paste_offset = (0.5, 0.5)  # Initial offset from original
        self.paste_rotation = 0.0  # Current rotation angle in radians

        # Original geometry (for rotation calculations)
        self.original_center = None
        self.original_lines = []  # Store original relative positions

        # Bounding box and interaction
        self.bbox_min = None
        self.bbox_max = None
        self.bbox_center = None
        self.bbox_padding = 0.3  # Padding around content

        # Stable paste box (center stays fixed; size chosen once on paste)
        self._bbox_local_min = None
        self._bbox_local_max = None
        self._bbox_local_min_lines = None
        self._bbox_local_max_lines = None
        self._bbox_local_min_all = None
        self._bbox_local_max_all = None
        self._bbox_world_corners = None

        # Dragging state
        self.dragging_paste = False
        self.drag_start = None

        # Rotation handle
        self.rotating = False
        self.rotation_handle_pos = None
        self.rotation_start_angle = 0.0

    def copy_selection(self):
        """Copy selection following hard rules:
        - Paste is ONLY possible if at least one LINE is selected.
        - Dimensions are copied ONLY when their required lines are also selected.
          * length: requires its line selected AND the length-dim selected
          * distance: requires BOTH lines selected AND the dist-dim selected
          * angle: requires BOTH lines selected AND the ang-dim selected
        - Every Ctrl+C fully renews the clipboard (no stale carryover).
        """
        # Always renew clipboard (prevents stale paste when copying only a dimension)
        self.clipboard = None

        # Gather lines to copy (only lines can enable paste)
        lines_to_copy = set()
        if getattr(self.app, "multi_selected", None):
            if self.app.multi_selected:
                lines_to_copy = set(self.app.multi_selected)
        if not lines_to_copy and getattr(self.app, "selected_line", None) is not None:
            lines_to_copy = {self.app.selected_line}

        if not lines_to_copy:
            # Dimension-only selection intentionally cannot be pasted
            return False

        # Build fresh clipboard data
        line_list = list(lines_to_copy)
        line_to_idx = {ln: i for i, ln in enumerate(line_list)}

        self.clipboard = {
            'lines': [],
            'fixed_lengths': [],
            'angle_constraints': [],
            'distance_constraints': []
        }

        # Copy line geometry
        for ln in line_list:
            self.clipboard['lines'].append({
                'x1': ln.x1, 'y1': ln.y1,
                'x2': ln.x2, 'y2': ln.y2,
                'color': getattr(ln, "color", "#4A9EFF")
            })

        # Selected dims (can be empty)
        selected_dims = getattr(self.app.dimension_tool, "_multi_selected_dims", set())

        # -------------------------
        # Length constraints (ONLY if its line is selected AND dim is selected)
        # -------------------------
        for ln, meta in getattr(self.app, "fixed_lengths", {}).items():
            if ln in lines_to_copy and ('len', ln) in selected_dims:
                self.clipboard['fixed_lengths'].append({
                    'line_idx': line_to_idx[ln],
                    'len': float(meta.get('len', ln.length())),
                    'label': meta.get('label', None)
                })

        # -------------------------
        # Angle constraints (ONLY if BOTH lines are selected AND dim is selected)
        # NOTE: if user selects only one line + angle dim, we copy ONLY the line(s).
        # -------------------------
        for idx, ent in enumerate(getattr(self.app, "angle_constraints", [])):
            a, b = ent.get('a'), ent.get('b')
            if a in lines_to_copy and b in lines_to_copy and ('ang', idx) in selected_dims:
                self.clipboard['angle_constraints'].append({
                    'line_a_idx': line_to_idx[a],
                    'line_b_idx': line_to_idx[b],
                    'vx': float(ent['vx']),
                    'vy': float(ent['vy']),
                    'deg': float(ent['deg']),
                    'side': int(ent.get('side', 1)),
                    'off': float(ent.get('off', 0.75))
                })

        # -------------------------
        # Distance constraints (ONLY if BOTH lines are selected AND dim is selected)
        # NOTE: if user selects one line + distance dim, we copy ONLY the line.
        # -------------------------
        for idx, ent in enumerate(getattr(self.app, "distance_constraints", [])):
            a, b = ent.get('a'), ent.get('b')
            if a in lines_to_copy and b in lines_to_copy and ('dist', idx) in selected_dims:
                self.clipboard['distance_constraints'].append({
                    'line_a_idx': line_to_idx[a],
                    'line_b_idx': line_to_idx[b],
                    'dist': float(ent['dist']),
                    'Pa': ent.get('Pa', None),
                    'Pb': ent.get('Pb', None),
                    'label': ent.get('label', None)
                })

        return True

    def paste(self):
        """Initiate paste preview mode."""
        if self.clipboard is None or not self.clipboard['lines']:
            return False

        # Calculate original center
        all_x = [ld['x1'] for ld in self.clipboard['lines']] + [ld['x2'] for ld in self.clipboard['lines']]
        all_y = [ld['y1'] for ld in self.clipboard['lines']] + [ld['y2'] for ld in self.clipboard['lines']]
        orig_cx = sum(all_x) / len(all_x)
        orig_cy = sum(all_y) / len(all_y)
        self.original_center = (orig_cx, orig_cy)

        # If we know the cursor position, paste centered at cursor.
        # If cursor is on top of the original copied material, paste slightly offset.
        # If cursor isn't known/valid, paste slightly offset from original.
        cursor_ok = bool(getattr(self.app, "cursor_world_valid", False))
        if cursor_ok and getattr(self.app, "cursor_world", None) is not None:
            cx, cy = self.app.cursor_world
            minx, maxx = min(all_x), max(all_x)
            miny, maxy = min(all_y), max(all_y)
            pad = 0.05
            on_original = (minx - pad <= cx <= maxx + pad) and (miny - pad <= cy <= maxy + pad)
            if on_original:
                new_cx = orig_cx + self.paste_offset[0]
                new_cy = orig_cy + self.paste_offset[1]
            else:
                new_cx, new_cy = cx, cy
        else:
            new_cx = orig_cx + self.paste_offset[0]
            new_cy = orig_cy + self.paste_offset[1]

        # Store original lines relative to center
        self.original_lines = []
        for ln_data in self.clipboard['lines']:
            self.original_lines.append({
                'x1': ln_data['x1'] - orig_cx,
                'y1': ln_data['y1'] - orig_cy,
                'x2': ln_data['x2'] - orig_cx,
                'y2': ln_data['y2'] - orig_cy,
                'color': ln_data['color']
            })

        # Create temporary Line objects for preview (with offset)
        from main_cad import Line
        self.paste_lines = []

        for ln_rel in self.original_lines:
            ln = Line(
                new_cx + ln_rel['x1'],
                new_cy + ln_rel['y1'],
                new_cx + ln_rel['x2'],
                new_cy + ln_rel['y2'],
                ln_rel['color']
            )
            self.paste_lines.append(ln)

        # Store dimension metadata for preview drawing
        self.paste_dimensions = {
            'fixed_lengths': self.clipboard['fixed_lengths'][:],
            'angle_constraints': self.clipboard['angle_constraints'][:],
            'distance_constraints': self.clipboard['distance_constraints'][:]
        }

        # Stable center for paste box (do NOT recompute from geometry)
        self.bbox_center = (new_cx, new_cy)

        # Compute local bbox once (lines-only vs all-entities)
        self._compute_local_bbox()
        # Enter paste mode (so bbox/handle update runs)
        self.paste_active = True

        # Reset rotation
        self.paste_rotation = 0.0

        # Calculate bounding box
        self._update_bbox()

        # Clear current selection (including dimensions)
        self.app.multi_selected.clear()
        self.app.selected_line = None
        self.app.dimension_tool._selected_kind = None
        self.app.dimension_tool._selected_id = None
        self.app.dimension_tool._multi_selected_dims.clear()

        self.paste_rotation = 0.0
        self.app._request_redraw()

        return True


    def _compute_local_bbox(self):
        """Compute local-space bbox around pasted entities (relative to original_center).

        Computes:
          - lines-only bbox (endpoints)
          - all-entities bbox (lines + dimension anchors/labels)

        If all-entities bbox area is >= 300% of lines-only bbox area, we use the
        lines-only bbox to avoid a giant paste box from far-away labels.
        """
        if not self.original_lines or self.original_center is None:
            self._bbox_local_min = None
            self._bbox_local_max = None
            self._bbox_local_min_lines = None
            self._bbox_local_max_lines = None
            self._bbox_local_min_all = None
            self._bbox_local_max_all = None
            return

        orig_cx, orig_cy = self.original_center

        # Lines-only points (already relative)
        pts_lines = []
        for ln_rel in self.original_lines:
            pts_lines.append((ln_rel['x1'], ln_rel['y1']))
            pts_lines.append((ln_rel['x2'], ln_rel['y2']))
        if not pts_lines:
            pts_lines = [(0.0, 0.0)]

        min_x_l = min(p[0] for p in pts_lines) - self.bbox_padding
        max_x_l = max(p[0] for p in pts_lines) + self.bbox_padding
        min_y_l = min(p[1] for p in pts_lines) - self.bbox_padding
        max_y_l = max(p[1] for p in pts_lines) + self.bbox_padding

        self._bbox_local_min_lines = (min_x_l, min_y_l)
        self._bbox_local_max_lines = (max_x_l, max_y_l)

        # All-entities points
        pts_all = list(pts_lines)

        # length labels
        for lc in self.paste_dimensions.get('fixed_lengths', []):
            lab = lc.get('label', None)
            if isinstance(lab, (tuple, list)) and len(lab) == 2:
                lx, ly = lab
                pts_all.append((lx - orig_cx, ly - orig_cy))

        # angle vertices (+ small offset point to cover arc space)
        for ac in self.paste_dimensions.get('angle_constraints', []):
            vx = ac.get('vx', None)
            vy = ac.get('vy', None)
            if vx is not None and vy is not None:
                pts_all.append((vx - orig_cx, vy - orig_cy))
                off = float(ac.get('off', 0.75))
                pts_all.append((vx - orig_cx + off, vy - orig_cy))

        # distance labels and closest points (if any)
        for dc in self.paste_dimensions.get('distance_constraints', []):
            lab = dc.get('label', None)
            if isinstance(lab, (tuple, list)) and len(lab) == 2:
                lx, ly = lab
                pts_all.append((lx - orig_cx, ly - orig_cy))
            Pa = dc.get('Pa', None)
            Pb = dc.get('Pb', None)
            if isinstance(Pa, (tuple, list)) and len(Pa) == 2:
                pts_all.append((Pa[0] - orig_cx, Pa[1] - orig_cy))
            if isinstance(Pb, (tuple, list)) and len(Pb) == 2:
                pts_all.append((Pb[0] - orig_cx, Pb[1] - orig_cy))

        if not pts_all:
            pts_all = [(0.0, 0.0)]

        min_x_a = min(p[0] for p in pts_all) - self.bbox_padding
        max_x_a = max(p[0] for p in pts_all) + self.bbox_padding
        min_y_a = min(p[1] for p in pts_all) - self.bbox_padding
        max_y_a = max(p[1] for p in pts_all) + self.bbox_padding

        self._bbox_local_min_all = (min_x_a, min_y_a)
        self._bbox_local_max_all = (max_x_a, max_y_a)

        area_lines = max(1e-12, (max_x_l - min_x_l) * (max_y_l - min_y_l))
        area_all = max(1e-12, (max_x_a - min_x_a) * (max_y_a - min_y_a))

        if area_all >= 5.0 * area_lines:
            self._bbox_local_min = self._bbox_local_min_lines
            self._bbox_local_max = self._bbox_local_max_lines
        else:
            self._bbox_local_min = self._bbox_local_min_all
            self._bbox_local_max = self._bbox_local_max_all

    def _update_bbox(self):
        """Update bbox for preview.

        - Uses a stable bbox_center (set on paste + moved on drag)
        - Uses a stable local bbox size chosen in _compute_local_bbox()
        - Produces rotated corners for drawing and an AABB for hit testing
        """
        if not self.paste_active or not self.bbox_center:
            return

        # Ensure we have a local bbox choice
        if self._bbox_local_min is None or self._bbox_local_max is None:
            # fallback: lines-only from current preview geometry (keeps old behavior)
            all_x = []
            all_y = []
            for ln in self.paste_lines:
                all_x.extend([ln.x1, ln.x2])
                all_y.extend([ln.y1, ln.y2])
            if not all_x or not all_y:
                return
            min_x = min(all_x) - self.bbox_padding
            max_x = max(all_x) + self.bbox_padding
            min_y = min(all_y) - self.bbox_padding
            max_y = max(all_y) + self.bbox_padding

            self.bbox_min = (min_x, min_y)
            self.bbox_max = (max_x, max_y)
            self._bbox_world_corners = None

            handle_offset = 0.25
            self.rotation_handle_pos = ((min_x + max_x) * 0.5, min_y - handle_offset)
            return

        cx, cy = self.bbox_center
        min_x, min_y = self._bbox_local_min
        max_x, max_y = self._bbox_local_max

        cos_a = math.cos(self.paste_rotation)
        sin_a = math.sin(self.paste_rotation)

        def local_to_world(px, py):
            return (
                cx + px * cos_a - py * sin_a,
                cy + px * sin_a + py * cos_a
            )

        # Rotated corners in world space
        c0 = local_to_world(min_x, min_y)
        c1 = local_to_world(max_x, min_y)
        c2 = local_to_world(max_x, max_y)
        c3 = local_to_world(min_x, max_y)
        self._bbox_world_corners = (c0, c1, c2, c3)

        # AABB for hit testing
        xs = [c0[0], c1[0], c2[0], c3[0]]
        ys = [c0[1], c1[1], c2[1], c3[1]]
        self.bbox_min = (min(xs), min(ys))
        self.bbox_max = (max(xs), max(ys))

        # Rotation handle: local top edge center, then offset outward in local -y
        handle_offset = 0.25
        top_cx = (min_x + max_x) * 0.5
        top_y = min_y
        hx, hy = local_to_world(top_cx, top_y - handle_offset)
        self.rotation_handle_pos = (hx, hy)

    def commit_paste(self):
        """Finalize the paste operation, adding lines to the actual model."""
        if not self.paste_active or not self.paste_lines:
            return

        self.app._push_undo()

        # Create line index mapping for new lines
        new_lines = []
        for pln in self.paste_lines:
            from main_cad import Line
            ln = Line(pln.x1, pln.y1, pln.x2, pln.y2, pln.color)
            new_lines.append(ln)
            self.app.lines.append(ln)

        # Calculate how the center moved and rotated
        curr_cx, curr_cy = self.bbox_center

        # Apply constraints to new lines with proper transformations
        for lc in self.clipboard['fixed_lengths']:
            idx = lc['line_idx']
            if 0 <= idx < len(new_lines):
                ln = new_lines[idx]
                # Transform label position
                orig_label = lc.get('label', None)
                if orig_label:
                    # Apply rotation and translation to label
                    lx, ly = orig_label
                    orig_cx, orig_cy = self.original_center
                    rel_lx = lx - orig_cx
                    rel_ly = ly - orig_cy

                    # Rotate
                    cos_a = math.cos(self.paste_rotation)
                    sin_a = math.sin(self.paste_rotation)
                    rot_lx = rel_lx * cos_a - rel_ly * sin_a
                    rot_ly = rel_lx * sin_a + rel_ly * cos_a

                    # Translate
                    new_label = (curr_cx + rot_lx, curr_cy + rot_ly)
                else:
                    new_label = ((ln.x1 + ln.x2) / 2, (ln.y1 + ln.y2) / 2)

                self.app.fixed_lengths[ln] = {
                    'len': float(lc['len']),
                    'label': new_label
                }

        for ac in self.clipboard['angle_constraints']:
            ia = ac['line_a_idx']
            ib = ac['line_b_idx']
            if 0 <= ia < len(new_lines) and 0 <= ib < len(new_lines):
                # Transform vertex position
                orig_cx, orig_cy = self.original_center
                vx, vy = ac['vx'], ac['vy']
                rel_vx = vx - orig_cx
                rel_vy = vy - orig_cy

                # Rotate
                cos_a = math.cos(self.paste_rotation)
                sin_a = math.sin(self.paste_rotation)
                rot_vx = rel_vx * cos_a - rel_vy * sin_a
                rot_vy = rel_vx * sin_a + rel_vy * cos_a

                # Translate
                new_vx = curr_cx + rot_vx
                new_vy = curr_cy + rot_vy

                self.app.angle_constraints.append({
                    'a': new_lines[ia],
                    'b': new_lines[ib],
                    'vx': new_vx,
                    'vy': new_vy,
                    'deg': float(ac['deg']),
                    'side': int(ac.get('side', 1)),
                    'off': float(ac.get('off', 0.75))
                })

        for dc in self.clipboard['distance_constraints']:
            ia = dc['line_a_idx']
            ib = dc['line_b_idx']
            if 0 <= ia < len(new_lines) and 0 <= ib < len(new_lines):
                # Transform label position if it exists
                orig_label = dc.get('label', None)
                if orig_label:
                    orig_cx, orig_cy = self.original_center
                    lx, ly = orig_label
                    rel_lx = lx - orig_cx
                    rel_ly = ly - orig_cy

                    # Rotate
                    cos_a = math.cos(self.paste_rotation)
                    sin_a = math.sin(self.paste_rotation)
                    rot_lx = rel_lx * cos_a - rel_ly * sin_a
                    rot_ly = rel_lx * sin_a + rel_ly * cos_a

                    # Translate
                    new_label = (curr_cx + rot_lx, curr_cy + rot_ly)
                else:
                    new_label = None

                self.app.distance_constraints.append({
                    'a': new_lines[ia],
                    'b': new_lines[ib],
                    'dist': float(dc['dist']),
                    'Pa': dc.get('Pa', None),
                    'Pb': dc.get('Pb', None),
                    'label': new_label
                })

        # Highlight newly pasted lines
        self.app.multi_selected = set(new_lines)

        # Clean up paste state
        self.cancel_paste()

        self.app._request_tree_update()
        self.app._request_redraw()

    def cancel_paste(self):
        """Cancel paste preview mode."""
        self.paste_active = False
        self.paste_lines = []
        self.paste_dimensions = {}
        self.original_lines = []
        self.original_center = None
        self.dragging_paste = False
        self.rotating = False

        self.bbox_min = None
        self.bbox_max = None
        self.bbox_center = None
        self.rotation_handle_pos = None
        self.paste_rotation = 0.0

        self._bbox_local_min = None
        self._bbox_local_max = None
        self._bbox_local_min_lines = None
        self._bbox_local_max_lines = None
        self._bbox_local_min_all = None
        self._bbox_local_max_all = None
        self._bbox_world_corners = None

        self.app._request_redraw()

    def on_mouse_down(self, e):
        """Handle mouse down in paste preview mode."""
        if not self.paste_active:
            return False

        wx, wy = self.app.vp.screen_to_world(e.x, e.y)

        # Check if clicking rotation handle
        if self.rotation_handle_pos:
            hx, hy = self.rotation_handle_pos
            if math.hypot(wx - hx, wy - hy) < 0.2:
                self.rotating = True
                self.rotation_start_angle = math.atan2(
                    wy - self.bbox_center[1],
                    wx - self.bbox_center[0]
                )
                return True

        # Check if clicking inside bounding box
        if self.bbox_min and self.bbox_max:
            if (self.bbox_min[0] <= wx <= self.bbox_max[0] and
                    self.bbox_min[1] <= wy <= self.bbox_max[1]):
                self.dragging_paste = True
                self.drag_start = (wx, wy)
                return True

        # Clicking outside - commit paste
        self.commit_paste()
        return True

    def on_mouse_drag(self, e):
        """Handle mouse drag in paste preview mode."""
        if not self.paste_active:
            return False

        wx, wy = self.app.vp.screen_to_world(e.x, e.y)

        if self.rotating and self.bbox_center:
            # Calculate rotation delta
            current_angle = math.atan2(
                wy - self.bbox_center[1],
                wx - self.bbox_center[0]
            )
            delta_angle = current_angle - self.rotation_start_angle
            self.paste_rotation += delta_angle
            self.rotation_start_angle = current_angle

            # Rebuild lines from original relative positions with current rotation
            curr_cx, curr_cy = self.bbox_center
            cos_a = math.cos(self.paste_rotation)
            sin_a = math.sin(self.paste_rotation)

            for i, ln_rel in enumerate(self.original_lines):
                # Rotate relative positions
                rx1 = ln_rel['x1'] * cos_a - ln_rel['y1'] * sin_a
                ry1 = ln_rel['x1'] * sin_a + ln_rel['y1'] * cos_a
                rx2 = ln_rel['x2'] * cos_a - ln_rel['y2'] * sin_a
                ry2 = ln_rel['x2'] * sin_a + ln_rel['y2'] * cos_a

                # Translate to current center
                self.paste_lines[i].x1 = curr_cx + rx1
                self.paste_lines[i].y1 = curr_cy + ry1
                self.paste_lines[i].x2 = curr_cx + rx2
                self.paste_lines[i].y2 = curr_cy + ry2

            self._update_bbox()
            self.app._request_redraw()
            return True

        elif self.dragging_paste and self.drag_start:
            # Calculate translation delta
            dx = wx - self.drag_start[0]
            dy = wy - self.drag_start[1]

            # Rebuild lines from original with current rotation + new translation
            new_cx = self.bbox_center[0] + dx
            new_cy = self.bbox_center[1] + dy
            self.bbox_center = (new_cx, new_cy)

            cos_a = math.cos(self.paste_rotation)
            sin_a = math.sin(self.paste_rotation)

            for i, ln_rel in enumerate(self.original_lines):
                # Rotate relative positions
                rx1 = ln_rel['x1'] * cos_a - ln_rel['y1'] * sin_a
                ry1 = ln_rel['x1'] * sin_a + ln_rel['y1'] * cos_a
                rx2 = ln_rel['x2'] * cos_a - ln_rel['y2'] * sin_a
                ry2 = ln_rel['x2'] * sin_a + ln_rel['y2'] * cos_a

                # Translate
                self.paste_lines[i].x1 = new_cx + rx1
                self.paste_lines[i].y1 = new_cy + ry1
                self.paste_lines[i].x2 = new_cx + rx2
                self.paste_lines[i].y2 = new_cy + ry2

            self.drag_start = (wx, wy)
            self._update_bbox()
            self.app._request_redraw()
            return True

        return False

    def on_mouse_up(self, e):
        """Handle mouse up in paste preview mode."""
        if not self.paste_active:
            return False

        if self.rotating or self.dragging_paste:
            self.rotating = False
            self.dragging_paste = False
            self.app._request_redraw()
            return True

        return False

    def draw_preview(self, canvas):
        """Draw paste preview with bounding box, rotation handle, and dimensions."""
        if not self.paste_active or not self.paste_lines:
            return

        # Draw preview lines in HIGHLIGHTED style (red)
        for ln in self.paste_lines:
            sx1, sy1 = self.app.vp.world_to_screen(ln.x1, ln.y1)
            sx2, sy2 = self.app.vp.world_to_screen(ln.x2, ln.y2)

            color = "#FF5C5C"
            canvas.create_line(sx1, sy1, sx2, sy2, fill=color, width=2)

            r = 4
            canvas.create_oval(sx1 - r, sy1 - r, sx1 + r, sy1 + r, fill=color, outline="white")
            canvas.create_oval(sx2 - r, sy2 - r, sx2 + r, sy2 + r, fill=color, outline="white")

        # Draw dimensions for paste preview
        self._draw_paste_dimensions(canvas)

        # Draw bounding box (rotated if available)
        if self._bbox_world_corners:
            pts = []
            for (wx, wy) in self._bbox_world_corners:
                sx, sy = self.app.vp.world_to_screen(wx, wy)
                pts.extend([sx, sy])
            canvas.create_polygon(
                pts,
                outline="#888888",
                width=1,
                dash=(4, 3),
                fill=""
            )
        elif self.bbox_min and self.bbox_max:
            bx1, by1 = self.app.vp.world_to_screen(self.bbox_min[0], self.bbox_min[1])
            bx2, by2 = self.app.vp.world_to_screen(self.bbox_max[0], self.bbox_max[1])
            canvas.create_rectangle(bx1, by1, bx2, by2, outline="#888888", width=1, dash=(4, 3))

        # Draw rotation handle (yellow dot) + connector to top-center of box
        if self.rotation_handle_pos:
            hx, hy = self.app.vp.world_to_screen(*self.rotation_handle_pos)
            r = 4
            canvas.create_oval(hx - r, hy - r, hx + r, hy + r, fill="#FFD700", outline="white", width=1)

            if self.bbox_center and self._bbox_local_min and self._bbox_local_max:
                cx, cy = self.bbox_center
                min_x, min_y = self._bbox_local_min
                max_x, max_y = self._bbox_local_max
                cos_a = math.cos(self.paste_rotation)
                sin_a = math.sin(self.paste_rotation)

                # local top edge center
                top_cx = (min_x + max_x) * 0.5
                top_y = min_y

                wx = cx + top_cx * cos_a - top_y * sin_a
                wy = cy + top_cx * sin_a + top_y * cos_a

                tsx, tsy = self.app.vp.world_to_screen(wx, wy)
                canvas.create_line(tsx, tsy, hx, hy, fill="#888888", width=1, dash=(4, 3))

    def _draw_paste_dimensions(self, canvas):
        """Draw dimensions for the paste preview."""
        if not self.paste_dimensions:
            return

        # Calculate transformation for dimensions
        curr_cx, curr_cy = self.bbox_center
        orig_cx, orig_cy = self.original_center
        cos_a = math.cos(self.paste_rotation)
        sin_a = math.sin(self.paste_rotation)

        # Draw length dimensions
        for lc in self.paste_dimensions['fixed_lengths']:
            idx = lc['line_idx']
            if 0 <= idx < len(self.paste_lines):
                ln = self.paste_lines[idx]

                # Transform label position
                orig_label = lc.get('label', None)
                if orig_label:
                    lx, ly = orig_label
                    rel_lx = lx - orig_cx
                    rel_ly = ly - orig_cy
                    rot_lx = rel_lx * cos_a - rel_ly * sin_a
                    rot_ly = rel_lx * sin_a + rel_ly * cos_a
                    label = (curr_cx + rot_lx, curr_cy + rot_ly)
                else:
                    label = ((ln.x1 + ln.x2) / 2, (ln.y1 + ln.y2) / 2)

                self.app.dimension_tool._draw_length_dim(
                    canvas, ln, label, live=False, highlight=True
                )

        # Draw angle dimensions
        for ac in self.paste_dimensions['angle_constraints']:
            ia = ac['line_a_idx']
            ib = ac['line_b_idx']
            if 0 <= ia < len(self.paste_lines) and 0 <= ib < len(self.paste_lines):
                a = self.paste_lines[ia]
                b = self.paste_lines[ib]

                # Transform vertex position
                vx, vy = ac['vx'], ac['vy']
                rel_vx = vx - orig_cx
                rel_vy = vy - orig_cy
                rot_vx = rel_vx * cos_a - rel_vy * sin_a
                rot_vy = rel_vx * sin_a + rel_vy * cos_a
                new_vx = curr_cx + rot_vx
                new_vy = curr_cy + rot_vy

                ent = {
                    'a': a, 'b': b,
                    'vx': new_vx, 'vy': new_vy,
                    'deg': ac['deg'],
                    'side': ac.get('side', 1),
                    'off': ac.get('off', 0.75)
                }
                self.app.dimension_tool._draw_angle_dim(
                    canvas, a, b, (new_vx, new_vy), None, live=False, ent=ent, highlight=True
                )

        # Draw distance dimensions
        for dc in self.paste_dimensions['distance_constraints']:
            ia = dc['line_a_idx']
            ib = dc['line_b_idx']
            if 0 <= ia < len(self.paste_lines) and 0 <= ib < len(self.paste_lines):
                a = self.paste_lines[ia]
                b = self.paste_lines[ib]

                # Transform label if it exists
                orig_label = dc.get('label', None)
                if orig_label:
                    lx, ly = orig_label
                    rel_lx = lx - orig_cx
                    rel_ly = ly - orig_cy
                    rot_lx = rel_lx * cos_a - rel_ly * sin_a
                    rot_ly = rel_lx * sin_a + rel_ly * cos_a
                    label = (curr_cx + rot_lx, curr_cy + rot_ly)
                else:
                    label = None

                ent = {
                    'a': a, 'b': b,
                    'dist': dc['dist'],
                    'Pa': dc.get('Pa', None),
                    'Pb': dc.get('Pb', None),
                    'label': label
                }
                self.app.dimension_tool._draw_distance_dim(
                    canvas, a, b, label, live=False, ent=ent, highlight=True
                )

#123aaaadd1122bbccdd1/1