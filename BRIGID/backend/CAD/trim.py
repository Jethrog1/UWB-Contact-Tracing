import math

from .runtime import notify_error, notify_info, tk


class TrimManager:
    """Manages trimming/cutting lines at specified positions."""

    def __init__(self, app):
        self.app = app

        # Trim state
        self.active = False
        self.selected_line = None
        self.line_length = 0.0

        # Trim points (as distance along line from start, 0 to line_length)
        self.trim_point_1 = None  # float or None
        self.trim_point_2 = None  # float or None
        self.selecting_point = 1  # 1 or 2 (which point we're currently placing)

        # Hover state
        self.hover_position = None  # float or None (distance along line)
        self.cursor_near_line = False

        # Dragging trim points
        self.dragging_point = None  # 1, 2, or None
        self.drag_start_mouse = None

        # UI
        self.menu_frame = None
        self.trim1_var = None
        self.trim2_var = None
        self.distance_label = None
        self.line_info_label = None
        self.trim1_entry = None
        self.trim2_entry = None

        # Saved colors
        self._saved_line_color = None

        # Animation (for continuous sliding dash effect)
        self.animation_offset = 0.0

    def activate(self):
        """Start trim mode - user must have a single line selected."""
        # Check for single line selection
        if self.app.multi_selected:
            if len(self.app.multi_selected) != 1:
                notify_info(self.app, "Trim", "Please select exactly one line to trim.")
                return False
            self.selected_line = list(self.app.multi_selected)[0]
        elif self.app.selected_line is not None:
            self.selected_line = self.app.selected_line
        else:
            notify_info(self.app, "Trim", "Please select a line to trim first.")
            return False

        # Check if line has any dimensions - DISALLOW trimming
        if self._line_has_dimensions(self.selected_line):
            notify_error(
                self.app,
                "Trim",
                "Cannot trim a line with dimensions.\nPlease remove all dimensions from this line first.",
            )
            return False

        # Calculate line length
        self.line_length = self.selected_line.length()
        if self.line_length < 1e-6:
            notify_info(self.app, "Trim", "Selected line is too short to trim.")
            return False

        # Save state for undo
        self.app._push_undo()

        # Save original line color and make it gray
        self._saved_line_color = getattr(self.selected_line, "color", "#4A9EFF")
        self.selected_line.color = "#888888"

        # Clear app selection visuals
        try:
            self.app.multi_selected.clear()
        except:
            self.app.multi_selected = set()
        self.app.selected_line = None

        # Initialize trim state
        self.active = True
        self.trim_point_1 = None
        self.trim_point_2 = None
        self.selecting_point = 1
        self.hover_position = None
        self.cursor_near_line = False
        self.dragging_point = None
        self.drag_start_mouse = None
        self.animation_offset = 0.0

        # New: track button state + store binding ids
        self._button1_down = False
        self._bind_b1_motion = None
        self._bind_btn_release = None

        # Build UI
        self._build_trim_menu()

        # New: bind reliable hold-drag + release while Trim is active
        try:
            self._bind_b1_motion = self.app.root.bind_all("<B1-Motion>", self.on_mouse_move, add="+")
            self._bind_btn_release = self.app.root.bind_all("<ButtonRelease-1>", self.on_mouse_up, add="+")
        except:
            self._bind_b1_motion = None
            self._bind_btn_release = None

        # Start animation
        self._animate()

        self.app._request_redraw()
        return True

    def _line_has_dimensions(self, line):
        """Check if line has any dimensions attached."""
        # Check length dimension
        if line in self.app.fixed_lengths:
            return True

        # Check angle dimensions
        for ent in self.app.angle_constraints:
            if ent.get('a') is line or ent.get('b') is line:
                return True

        # Check distance dimensions
        for ent in self.app.distance_constraints:
            if ent.get('a') is line or ent.get('b') is line:
                return True

        return False

    def cancel(self):
        """Cancel trim mode and restore original state."""
        # Unbind trim-only global bindings
        try:
            if getattr(self, "_bind_b1_motion", None) is not None:
                self.app.root.unbind_all("<B1-Motion>")
            if getattr(self, "_bind_btn_release", None) is not None:
                self.app.root.unbind_all("<ButtonRelease-1>")
        except:
            pass
        self._bind_b1_motion = None
        self._bind_btn_release = None

        # Restore cursor
        try:
            self.app.canvas.config(cursor="")
        except:
            pass

        # Restore line color
        if self.selected_line is not None and self._saved_line_color is not None:
            try:
                self.selected_line.color = self._saved_line_color
            except:
                pass

        # Destroy UI
        if self.menu_frame is not None:
            try:
                self.menu_frame.destroy()
            except:
                pass
            self.menu_frame = None

        # Clear state
        self.active = False
        self.selected_line = None
        self.line_length = 0.0
        self.trim_point_1 = None
        self.trim_point_2 = None
        self.selecting_point = 1
        self.hover_position = None
        self.cursor_near_line = False
        self.dragging_point = None
        self.drag_start_mouse = None
        self._saved_line_color = None
        self.animation_offset = 0.0
        self._button1_down = False

        self.app._request_redraw()

    def _build_trim_menu(self):
        """Build the floating trim settings menu."""
        menu_bg = "#1A1A1A"
        menu_fg = "white"

        # Create frame in top-right corner (lower and narrower)
        self.menu_frame = tk.Frame(
            self.app.canvas,
            bg=menu_bg,
            relief="flat",
            borderwidth=1,
            highlightthickness=1,
            highlightbackground="#555555"
        )

        # Title
        title = tk.Label(
            self.menu_frame,
            text="Trim Settings:",
            bg=menu_bg,
            fg=menu_fg,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=10,
            pady=8
        )
        title.pack(fill="x")

        # Line info
        line_num = self.app.lines.index(self.selected_line) + 1 if self.selected_line in self.app.lines else "?"
        self.line_info_label = tk.Label(
            self.menu_frame,
            text=f"Line {line_num} | Length: {self.line_length:.3f}",
            bg=menu_bg,
            fg="#AAAAAA",
            font=("Segoe UI", 9),
            anchor="w",
            padx=10,
            pady=4
        )
        self.line_info_label.pack(fill="x")

        # Divider
        tk.Frame(self.menu_frame, bg="#555555", height=1).pack(fill="x", padx=8, pady=6)

        # Trim point 1
        trim1_frame = tk.Frame(self.menu_frame, bg=menu_bg)
        trim1_frame.pack(fill="x", padx=10, pady=4)

        tk.Label(
            trim1_frame,
            text="Trim Point 1:",
            bg=menu_bg,
            fg=menu_fg,
            font=("Segoe UI", 9),
            anchor="w"
        ).pack(side="left")

        self.trim1_var = tk.StringVar(value="")
        self.trim1_entry = tk.Entry(
            trim1_frame,
            textvariable=self.trim1_var,
            width=8,
            bg="#2A2A2A",
            fg="white",
            insertbackground="white",
            relief="flat",
            font=("Segoe UI", 9)
        )
        self.trim1_entry.pack(side="right", padx=(10, 0))
        self.trim1_entry.bind("<Return>", lambda e: self._on_entry_submit(1))
        self.trim1_entry.bind("<FocusIn>", lambda e: self._on_entry_focus(1))
        self.trim1_entry.bind("<KeyRelease>", lambda e: self._on_entry_change(1))

        # Trim point 2
        trim2_frame = tk.Frame(self.menu_frame, bg=menu_bg)
        trim2_frame.pack(fill="x", padx=10, pady=4)

        tk.Label(
            trim2_frame,
            text="Trim Point 2:",
            bg=menu_bg,
            fg=menu_fg,
            font=("Segoe UI", 9),
            anchor="w"
        ).pack(side="left")

        self.trim2_var = tk.StringVar(value="")
        self.trim2_entry = tk.Entry(
            trim2_frame,
            textvariable=self.trim2_var,
            width=8,
            bg="#2A2A2A",
            fg="white",
            insertbackground="white",
            relief="flat",
            font=("Segoe UI", 9)
        )
        self.trim2_entry.pack(side="right", padx=(10, 0))
        self.trim2_entry.bind("<Return>", lambda e: self._on_entry_submit(2))
        self.trim2_entry.bind("<FocusIn>", lambda e: self._on_entry_focus(2))
        self.trim2_entry.bind("<KeyRelease>", lambda e: self._on_entry_change(2))

        # Divider
        tk.Frame(self.menu_frame, bg="#555555", height=1).pack(fill="x", padx=8, pady=6)

        # Distance display
        distance_frame = tk.Frame(self.menu_frame, bg=menu_bg)
        distance_frame.pack(fill="x", padx=10, pady=4)

        tk.Label(
            distance_frame,
            text="Trim Distance:",
            bg=menu_bg,
            fg=menu_fg,
            font=("Segoe UI", 9),
            anchor="w"
        ).pack(side="left")

        self.distance_label = tk.Label(
            distance_frame,
            text="--",
            bg=menu_bg,
            fg="#FF5C5C",
            font=("Segoe UI", 10, "bold"),
            anchor="e"
        )
        self.distance_label.pack(side="right")

        # Divider
        tk.Frame(self.menu_frame, bg="#555555", height=1).pack(fill="x", padx=8, pady=6)

        # Apply button
        apply_btn = tk.Button(
            self.menu_frame,
            text="Apply (Enter)",
            command=self._apply_trim,
            bg="#404040",
            fg="white",
            relief="flat",
            font=("Segoe UI", 9),
            padx=10,
            pady=6,
            cursor="hand2",
            activebackground="#606060",
            activeforeground="white"
        )
        apply_btn.pack(fill="x", padx=10, pady=(4, 10))

        # Position in top-right corner (lower and narrower)
        self.menu_frame.place(relx=1.0, rely=0.0, x=-20, y=20, anchor="ne", width=200)
        self.menu_frame.lift()

    def _on_entry_focus(self, point_num):
        """Handle when user clicks into an entry field."""
        self.selecting_point = point_num

    def _on_entry_submit(self, point_num):
        """Handle when user presses Enter in an entry field."""
        var = self.trim1_var if point_num == 1 else self.trim2_var
        text = var.get().strip()

        if not text:
            return

        try:
            value = float(text)
        except:
            var.set("")
            return

        # Clamp to valid range
        value = max(0.0, min(self.line_length, value))

        if point_num == 1:
            self.trim_point_1 = value
            self.trim1_var.set(f"{value:.3f}")
            if self.trim_point_2 is None:
                self.selecting_point = 2
        else:
            self.trim_point_2 = value
            self.trim2_var.set(f"{value:.3f}")

        self._update_distance_display()
        self.app._request_redraw()

    def _update_distance_display(self):
        """Update the distance label between trim points."""
        if self.trim_point_1 is not None and self.trim_point_2 is not None:
            dist = abs(self.trim_point_2 - self.trim_point_1)
            self.distance_label.config(text=f"{dist:.3f}")
        else:
            self.distance_label.config(text="--")

    def on_mouse_move(self, e):
        """Handle mouse movement in trim mode."""
        if not self.active or self.selected_line is None:
            return False

        wx, wy = self.app.vp.screen_to_world(e.x, e.y)

        # Unfocus entry fields if clicking on canvas
        self._try_unfocus_entries(e)

        BUTTON1_MASK = 0x0100  # Tk Button1Mask

        # ------------------------------------------------------------
        # Dragging: ONLY while button-1 is physically down
        # Cursor: glove while dragging
        # ------------------------------------------------------------
        if self.dragging_point is not None:
            if not (e.state & BUTTON1_MASK):
                self.dragging_point = None
                self.drag_start_mouse = None
                try:
                    self.app.canvas.config(cursor="")
                except:
                    pass
                self.app._request_redraw()
                return True

            self._update_dragging_point(wx, wy)
            try:
                self.app.canvas.config(cursor="hand2")  # glove during drag
            except:
                pass
            self.app._request_redraw()
            return True

        # ------------------------------------------------------------
        # If both points exist: allow hover glove over trim markers
        # Otherwise keep normal cursor and do hover-placement logic
        # ------------------------------------------------------------
        if self.trim_point_1 is not None and self.trim_point_2 is not None:
            hovering = False
            if self._is_near_trim_point(wx, wy, self.trim_point_1, threshold=0.25):
                hovering = True
            elif self._is_near_trim_point(wx, wy, self.trim_point_2, threshold=0.25):
                hovering = True

            try:
                self.app.canvas.config(cursor="hand2" if hovering else "")
            except:
                pass

            self.cursor_near_line = False
            self.hover_position = None
            self.app._request_redraw()
            return True

        # ------------------------------------------------------------
        # Not both points set yet: normal cursor + hover placement
        # ------------------------------------------------------------
        try:
            self.app.canvas.config(cursor="")  # normal while placing points
        except:
            pass

        ln = self.selected_line
        dx = ln.x2 - ln.x1
        dy = ln.y2 - ln.y1
        L = math.hypot(dx, dy)

        if L < 1e-9:
            self.cursor_near_line = False
            self.hover_position = None
            self.app._request_redraw()
            return True

        px = wx - ln.x1
        py = wy - ln.y1
        t = (px * dx + py * dy) / (L * L)
        t = max(0.0, min(1.0, t))

        proj_x = ln.x1 + t * dx
        proj_y = ln.y1 + t * dy

        dist_to_line = math.hypot(wx - proj_x, wy - proj_y)
        threshold = 0.3

        if dist_to_line < threshold:
            self.cursor_near_line = True
            self.hover_position = t * L

            if self.selecting_point == 1 and self.trim_point_1 is None:
                self.trim1_var.set(f"{self.hover_position:.3f}")
            elif self.selecting_point == 2 and self.trim_point_2 is None:
                self.trim2_var.set(f"{self.hover_position:.3f}")

            self._update_distance_display()
        else:
            self.cursor_near_line = False
            self.hover_position = None

        self.app._request_redraw()
        return True

    def on_mouse_down(self, e):
        """Handle mouse click in trim mode."""
        if not self.active or self.selected_line is None:
            return False

        # --- NEW: if a right-click menu is open, left-click should close it ---
        try:
            # This closes any posted Tk menu globally
            self.app.root.tk.call("tk::MenuUnpost")
        except:
            pass

        self._button1_down = True

        wx, wy = self.app.vp.screen_to_world(e.x, e.y)

        # Unfocus entries
        self._try_unfocus_entries(e)

        # If both points exist: allow dragging by clicking near a point
        if self.trim_point_1 is not None and self.trim_point_2 is not None:
            if self._is_near_trim_point(wx, wy, self.trim_point_1, threshold=0.25):
                self.dragging_point = 1
                self.drag_start_mouse = (wx, wy)
                try:
                    self.app.canvas.config(cursor="hand2")
                except:
                    pass
                return True

            if self._is_near_trim_point(wx, wy, self.trim_point_2, threshold=0.25):
                self.dragging_point = 2
                self.drag_start_mouse = (wx, wy)
                try:
                    self.app.canvas.config(cursor="hand2")
                except:
                    pass
                return True

        # Otherwise: normal point placement behavior
        try:
            self.app.canvas.config(cursor="")
        except:
            pass

        if self.cursor_near_line and self.hover_position is not None:
            if self.selecting_point == 1 and self.trim_point_1 is None:
                self.trim_point_1 = self.hover_position
                self.trim1_var.set(f"{self.trim_point_1:.3f}")
                self.selecting_point = 2
            elif self.selecting_point == 2 and self.trim_point_2 is None:
                self.trim_point_2 = self.hover_position
                self.trim2_var.set(f"{self.trim_point_2:.3f}")

            self._update_distance_display()
            self.app._request_redraw()
            return True

        return True

    def on_mouse_up(self, e):
        """Handle mouse release in trim mode."""
        if not self.active:
            return False

        self._button1_down = False

        if self.dragging_point is not None:
            self.dragging_point = None
            self.drag_start_mouse = None

        # Cursor: glove ONLY if hovering a trim marker, else normal
        try:
            wx, wy = self.app.vp.screen_to_world(e.x, e.y)
            hovering = False
            if self.trim_point_1 is not None and self.trim_point_2 is not None:
                if self._is_near_trim_point(wx, wy, self.trim_point_1, threshold=0.25):
                    hovering = True
                elif self._is_near_trim_point(wx, wy, self.trim_point_2, threshold=0.25):
                    hovering = True
            self.app.canvas.config(cursor="hand2" if hovering else "")
        except:
            try:
                self.app.canvas.config(cursor="")
            except:
                pass

        self.app._request_redraw()
        return True

    def _is_near_trim_point(self, wx, wy, trim_pos, threshold=0.2):
        """Check if cursor is near a trim point position."""
        if self.selected_line is None or trim_pos is None:
            return False

        ln = self.selected_line
        L = self.line_length

        if L < 1e-9:
            return False

        t = trim_pos / L
        px = ln.x1 + t * (ln.x2 - ln.x1)
        py = ln.y1 + t * (ln.y2 - ln.y1)

        return math.hypot(wx - px, wy - py) < threshold

    def _update_dragging_point(self, wx, wy):
        """Update trim point position while dragging."""
        if self.selected_line is None or self.dragging_point is None or self.drag_start_mouse is None:
            return

        ln = self.selected_line
        dx = ln.x2 - ln.x1
        dy = ln.y2 - ln.y1
        L = math.hypot(dx, dy)

        if L < 1e-9:
            return

        # Project cursor onto line
        px = wx - ln.x1
        py = wy - ln.y1
        t = (px * dx + py * dy) / (L * L)
        t = max(0.0, min(1.0, t))

        new_pos = t * L

        if self.dragging_point == 1:
            self.trim_point_1 = new_pos
            self.trim1_var.set(f"{new_pos:.3f}")
        else:
            self.trim_point_2 = new_pos
            self.trim2_var.set(f"{new_pos:.3f}")

        self._update_distance_display()

    def on_key_press(self, e):
        """Handle keyboard input in trim mode."""
        if not self.active:
            return False

        if e.keysym == "Escape":
            self.cancel()
            return True

        if e.keysym == "Return":
            self._apply_trim()
            return True

        return False

    def _apply_trim(self):
        """Apply the trim operation and create new geometry."""
        if self.trim_point_1 is None or self.trim_point_2 is None:
            return

        if abs(self.trim_point_1 - self.trim_point_2) < 1e-6:
            notify_info(self.app, "Trim", "Trim points are too close together.")
            return

        ln = self.selected_line
        if ln is None:
            return

        L = float(self.line_length or 0.0)
        if L < 1e-9:
            return

        # Sort trim points and convert to [0..1]
        t1 = min(self.trim_point_1, self.trim_point_2) / L
        t2 = max(self.trim_point_1, self.trim_point_2) / L

        # Clamp just in case
        t1 = max(0.0, min(1.0, t1))
        t2 = max(0.0, min(1.0, t2))

        # Points along the line
        dx = ln.x2 - ln.x1
        dy = ln.y2 - ln.y1

        p1_x = ln.x1 + t1 * dx
        p1_y = ln.y1 + t1 * dy
        p2_x = ln.x1 + t2 * dx
        p2_y = ln.y1 + t2 * dy

        eps = 1e-6

        # Always remove the original line from the model (trim modifies it)
        try:
            if ln in self.app.lines:
                self.app.lines.remove(ln)
        except:
            pass

        new_lines = []
        from .main_cad import Line

        # --- NEW: if trim covers the entire line -> delete only (no replacement geometry) ---
        if t1 <= eps and t2 >= 1.0 - eps:
            # Delete the line completely
            new_lines = []

        # Case 1: Trim from start (keep only after t2)
        elif t1 <= eps:
            # keep (p2 -> end)
            if math.hypot(ln.x2 - p2_x, ln.y2 - p2_y) > eps:
                new_lines.append(Line(p2_x, p2_y, ln.x2, ln.y2, self._saved_line_color))

        # Case 2: Trim from end (keep only before t1)
        elif t2 >= 1.0 - eps:
            # keep (start -> p1)
            if math.hypot(p1_x - ln.x1, p1_y - ln.y1) > eps:
                new_lines.append(Line(ln.x1, ln.y1, p1_x, p1_y, self._saved_line_color))

        # Case 3: Trim in middle (create two lines)
        else:
            if math.hypot(p1_x - ln.x1, p1_y - ln.y1) > eps:
                new_lines.append(Line(ln.x1, ln.y1, p1_x, p1_y, self._saved_line_color))
            if math.hypot(ln.x2 - p2_x, ln.y2 - p2_y) > eps:
                new_lines.append(Line(p2_x, p2_y, ln.x2, ln.y2, self._saved_line_color))

        # Add new lines to model
        for nl in new_lines:
            try:
                self.app.lines.append(nl)
            except:
                pass

        # Select new lines (or clear selection if we deleted)
        try:
            self.app.multi_selected = set(new_lines) if new_lines else set()
        except:
            self.app.multi_selected = set()
        self.app.selected_line = None

        # Clean up
        self.cancel()
        self.app._request_tree_update()
        self.app._request_redraw()

    def _animate(self):
        """Animate scrolling dotted indicator (LED-sign style)."""
        if not self.active:
            return

        # This is a PHASE in pixels (screen space). We use it to "scroll" dots.
        self.animation_offset += 0.5
        if self.animation_offset > 1e9:
            self.animation_offset = 0.0

        self.app._request_redraw()

        if self.active:
            self.app.root.after(16, self._animate)  # ~60fps smooth

    def draw_overlay(self, canvas):
        """Draw trim visualization overlay."""
        if not self.active or self.selected_line is None:
            return

        ln = self.selected_line
        L = self.line_length
        if L < 1e-9:
            return

        dx = ln.x2 - ln.x1
        dy = ln.y2 - ln.y1
        ux = dx / L
        uy = dy / L
        nx = -uy
        ny = ux

        def _draw_scrolling_dots(sp1, sp2, color="#888888", width=2):
            # Draw many tiny segments in screen-space with a scrolling phase.
            x1, y1 = sp1
            x2, y2 = sp2
            vx = x2 - x1
            vy = y2 - y1
            seg_len = math.hypot(vx, vy)
            if seg_len < 2:
                return

            # Unit direction (screen space)
            ux_s = vx / seg_len
            uy_s = vy / seg_len

            # "Dot" styling in pixels
            dot_len = 3.0
            gap_len = 6.0
            period = dot_len + gap_len

            # phase scrolls forward; modulo keeps it stable
            phase = self.animation_offset % period

            # Start a little before so it looks continuous
            s = -phase
            while s < seg_len:
                a = max(0.0, s)
                b = min(seg_len, s + dot_len)
                if b > 0.0 and b > a:
                    ax = x1 + ux_s * a
                    ay = y1 + uy_s * a
                    bx = x1 + ux_s * b
                    by = y1 + uy_s * b
                    canvas.create_line(ax, ay, bx, by, fill=color, width=width)
                s += period

        # ------------------------------------------------------------
        # Hover indicator (gray scrolling dotted line)
        # ------------------------------------------------------------
        if self.cursor_near_line and self.hover_position is not None and self.dragging_point is None:
            if not (self.trim_point_1 is not None and self.trim_point_2 is not None):
                t = self.hover_position / L
                px = ln.x1 + t * dx
                py = ln.y1 + t * dy

                offset = 0.15
                p1x = px + nx * offset
                p1y = py + ny * offset
                p2x = px - nx * offset
                p2y = py - ny * offset

                sp1 = self.app.vp.world_to_screen(p1x, p1y)
                sp2 = self.app.vp.world_to_screen(p2x, p2y)

                _draw_scrolling_dots(sp1, sp2, color="#888888", width=2)

        # ------------------------------------------------------------
        # Fixed trim points (white perpendicular markers)
        # ------------------------------------------------------------
        if self.trim_point_1 is not None:
            t = self.trim_point_1 / L
            px = ln.x1 + t * dx
            py = ln.y1 + t * dy

            offset = 0.15
            p1x = px + nx * offset
            p1y = py + ny * offset
            p2x = px - nx * offset
            p2y = py - ny * offset

            sp1 = self.app.vp.world_to_screen(p1x, p1y)
            sp2 = self.app.vp.world_to_screen(p2x, p2y)
            canvas.create_line(sp1[0], sp1[1], sp2[0], sp2[1], fill="#FFFFFF", width=2)

        if self.trim_point_2 is not None:
            t = self.trim_point_2 / L
            px = ln.x1 + t * dx
            py = ln.y1 + t * dy

            offset = 0.15
            p1x = px + nx * offset
            p1y = py + ny * offset
            p2x = px - nx * offset
            p2y = py - ny * offset

            sp1 = self.app.vp.world_to_screen(p1x, p1y)
            sp2 = self.app.vp.world_to_screen(p2x, p2y)
            canvas.create_line(sp1[0], sp1[1], sp2[0], sp2[1], fill="#FFFFFF", width=2)

        # ------------------------------------------------------------
        # Red segment between trim points (or point1 -> hover)
        # ------------------------------------------------------------
        if self.trim_point_1 is not None:
            if self.trim_point_2 is not None:
                t2_pos = self.trim_point_2
            elif self.hover_position is not None and self.selecting_point == 2:
                t2_pos = self.hover_position
            else:
                t2_pos = None

            if t2_pos is not None:
                t1 = self.trim_point_1 / L
                t2 = t2_pos / L

                p1x = ln.x1 + t1 * dx
                p1y = ln.y1 + t1 * dy
                p2x = ln.x1 + t2 * dx
                p2y = ln.y1 + t2 * dy

                sp1 = self.app.vp.world_to_screen(p1x, p1y)
                sp2 = self.app.vp.world_to_screen(p2x, p2y)
                canvas.create_line(sp1[0], sp1[1], sp2[0], sp2[1], fill="#FF5C5C", width=4)

    def _on_entry_change(self, point_num):
        """Handle when user types in entry field (validates and sets trim point)."""
        var = self.trim1_var if point_num == 1 else self.trim2_var
        text = var.get().strip()

        if not text:
            # Clear the trim point if field is empty
            if point_num == 1:
                self.trim_point_1 = None
            else:
                self.trim_point_2 = None
            self._update_distance_display()
            self.app._request_redraw()
            return

        try:
            value = float(text)
        except:
            return

        # Clamp to valid range
        value = max(0.0, min(self.line_length, value))

        if point_num == 1:
            self.trim_point_1 = value
        else:
            self.trim_point_2 = value

        self._update_distance_display()
        self.app._request_redraw()

    def _try_unfocus_entries(self, e):
        """Check if clicking outside entry fields and unfocus them."""
        if self.trim1_entry is None or self.trim2_entry is None:
            return

        # Get widget under mouse
        try:
            widget = self.app.root.winfo_containing(e.x_root, e.y_root)
            if widget not in (self.trim1_entry, self.trim2_entry):
                self.app.canvas.focus_set()
        except:
            pass

#123aaaadd1122bbccdd1/1
