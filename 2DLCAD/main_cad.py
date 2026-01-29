import tkinter as tk
from tkinter import ttk, simpledialog
import math

from dimension_tool import DimensionTool  # NEW
from copy_paste import CopyPasteManager
from dimension_rules import DimensionRules

from rotate import RotateManager
from trim import TrimManager

import features
import snap

EPS = 1e-9

##############################################################################
# TODO #                                                                 #####
# mess around with program                                               #####
# set up github                                                          #####
# add splines, dimensionless                                             #####   
# curves, width and angle dimensions                                     #####
# Function to save floor plan                                            #####
# Improve UI for 2DLCAD                                                  #####
# Program to designate rooms, tags, etc                                  #####
# import floor plan function pdf, recognize rooms                        #####
# Homepage, UI, select floor plan, select wristband (give names, etc)    #####
    # floor plan on left side                                            #####
    # right side have sailors info                                       #####
##############################################################################

class Viewport:
    def __init__(self):
        self.scale = 60.0
        self.offx = 0.0
        self.offy = 0.0

    def world_to_screen(self, x, y):
        return x * self.scale + self.offx, y * self.scale + self.offy

    def screen_to_world(self, sx, sy):
        return (sx - self.offx) / self.scale, (sy - self.offy) / self.scale

    def zoom_at(self, factor, anchor_sx, anchor_sy):
        from features import ZoomController
        return ZoomController.zoom_at_vp(self, factor, anchor_sx, anchor_sy)


class Line:
    __slots__ = ("x1", "y1", "x2", "y2", "color")

    def __init__(self, x1, y1, x2, y2, color="#4A9EFF"):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color

    def length(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def distance_to_point(self, px, py):
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        if abs(dx) < EPS and abs(dy) < EPS:
            return math.hypot(px - self.x1, py - self.y1)
        t = ((px - self.x1) * dx + (py - self.y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proj_x = self.x1 + t * dx
        proj_y = self.y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def closest_point(self, px, py):
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        if abs(dx) < EPS and abs(dy) < EPS:
            return self.x1, self.y1, 0.0
        t = ((px - self.x1) * dx + (py - self.y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proj_x = self.x1 + t * dx
        proj_y = self.y1 + t * dy
        return proj_x, proj_y, t


# -------------------------------------------------------------------------
# RIGHT-CLICK DROPDOWN MENU
# -------------------------------------------------------------------------
class DropdownMenu:
    """
    Right-click context menu that appears at cursor position.
    Provides quick access to zoom controls and other common actions.
    """

    def __init__(self, app):
        self.app = app
        self.active = False
        self.menu_frame = None
        self.anchor_x = 0
        self.anchor_y = 0

        # Menu dimensions / style
        self.menu_width = 130
        self.menu_bg = "#2E2E2E"
        self.menu_fg = "white"
        self.hover_bg = "#404040"
        self.divider_bg = "#555555"

        self.zoom_display_label = None

    def open_menu(self, screen_x, screen_y):
        if self.active:
            self.close_menu()
            return

        self.active = True
        self.anchor_x = screen_x
        self.anchor_y = screen_y

        self.menu_frame = tk.Frame(
            self.app.canvas,
            bg=self.menu_bg,
            relief="flat",
            borderwidth=0,
            highlightthickness=0
        )

        # Zoom section
        self._add_section_header("Zoom Settings")
        self._add_zoom_controls()

        # Divider
        self._add_divider()

        # Copy / Paste
        self._add_copy_paste_controls()

        # Divider
        self._add_divider()

        # Line Settings section
        self._add_section_header("Line Settings")
        self._add_toggle_controls()

        # Divider
        self._add_divider()

        # Config Settings
        self._add_section_header("Config Settings")

        # Rotate button (NEW POSITION)
        self._add_rotate_control()

        # Trim button
        self._add_trim_control()

        self.menu_frame.place(x=screen_x, y=screen_y, width=self.menu_width)
        self.menu_frame.lift()

    def close_menu(self):
        if self.menu_frame:
            self.menu_frame.destroy()
            self.menu_frame = None
        self.zoom_display_label = None
        self.active = False

    def _add_section_header(self, text):
        header = tk.Label(
            self.menu_frame,
            text=text,
            bg=self.menu_bg,
            fg="white",
            font=("Segoe UI", 9),
            anchor="w",
            padx=8
        )
        header.pack(fill="x", pady=(6, 4))

    def _add_divider(self):
        divider = tk.Frame(
            self.menu_frame,
            bg=self.divider_bg,
            height=1
        )
        divider.pack(fill="x", padx=8, pady=(4, 4))

    def _style_button(self, btn):
        btn.configure(
            bg=self.hover_bg,
            fg="white",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            cursor="hand2",
            activebackground="white",
            activeforeground="#7A7A7A"
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=self.hover_bg))
        btn.bind("<Leave>", lambda e: btn.config(bg=self.hover_bg, fg="white"))

    def _style_check(self, chk):
        chk.configure(
            bg=self.menu_bg,
            fg="white",
            selectcolor=self.menu_bg,
            activebackground="white",
            activeforeground="#7A7A7A",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            anchor="w",
            padx=8,
            cursor="hand2"
        )

    def _add_zoom_controls(self):
        zoom_container = tk.Frame(self.menu_frame, bg=self.menu_bg)
        zoom_container.pack(fill="x", padx=6, pady=(0, 6))

        zoom_out_btn = tk.Button(
            zoom_container,
            text="-",
            command=self._on_zoom_out,
            width=2,
            font=("Segoe UI", 10)
        )
        self._style_button(zoom_out_btn)
        zoom_out_btn.pack(side="left", padx=(0, 3))

        zoom_display = tk.Label(
            zoom_container,
            text=f"{int(self.app.vp.scale / 60.0 * 100)}%",
            bg=self.menu_bg,
            fg="white",
            width=5,
            anchor="center",
            font=("Segoe UI", 9)
        )
        zoom_display.pack(side="left", padx=(0, 3))
        self.zoom_display_label = zoom_display

        zoom_in_btn = tk.Button(
            zoom_container,
            text="+",
            command=self._on_zoom_in,
            width=2,
            font=("Segoe UI", 10)
        )
        self._style_button(zoom_in_btn)
        zoom_in_btn.pack(side="left", padx=(0, 6))

        reset_btn = tk.Button(
            zoom_container,
            text="Reset",
            command=self._on_zoom_reset,
            font=("Segoe UI", 9),
            padx=6
        )
        self._style_button(reset_btn)
        reset_btn.pack(side="left")

    def _add_copy_paste_controls(self):
        row = tk.Frame(self.menu_frame, bg=self.menu_bg)
        row.pack(fill="x", padx=6, pady=(6, 6))

        copy_btn = tk.Button(
            row,
            text="Copy",
            command=self._on_copy,
            font=("Segoe UI", 9),
            padx=8
        )
        self._style_button(copy_btn)
        copy_btn.pack(side="left", padx=(0, 6))

        paste_btn = tk.Button(
            row,
            text="Paste",
            command=self._on_paste,
            font=("Segoe UI", 9),
            padx=8
        )
        self._style_button(paste_btn)
        paste_btn.pack(side="left")

    def _add_toggle_controls(self):
        box = tk.Frame(self.menu_frame, bg=self.menu_bg)
        box.pack(fill="x", pady=(0, 6))

        chk1 = tk.Checkbutton(
            box,
            text="Manipulate Line",
            variable=self.app.manipulate_line_var,
            onvalue=True,
            offvalue=False,
            font=("Segoe UI", 9)
        )
        self._style_check(chk1)
        chk1.pack(fill="x")

        chk2 = tk.Checkbutton(
            box,
            text="Snap Axis",
            variable=self.app.snap_axis_var,
            onvalue=True,
            offvalue=False,
            font=("Segoe UI", 9)
        )
        self._style_check(chk2)
        chk2.pack(fill="x")

        chk3 = tk.Checkbutton(
            box,
            text="Line Match",
            variable=self.app.line_match_var,
            onvalue=True,
            offvalue=False,
            font=("Segoe UI", 9)
        )
        self._style_check(chk3)
        chk3.pack(fill="x")

        # Visuals
        chk4 = tk.Checkbutton(
            box,
            text="Disable V.Point",
            variable=self.app.visuals.disable_v_point_var,
            onvalue=True,
            offvalue=False,
            command=self.app._request_redraw,
            font=("Segoe UI", 9)
        )
        self._style_check(chk4)
        chk4.pack(fill="x")

    def _on_zoom_in(self):
        self.app.zoom_in()
        self._update_menu_zoom_display()

    def _on_zoom_out(self):
        self.app.zoom_out()
        self._update_menu_zoom_display()

    def _on_zoom_reset(self):
        self.app.zoom_reset()
        self._update_menu_zoom_display()

    def _on_copy(self):
        try:
            self.app.copy_paste.copy_selection()
        finally:
            self.close_menu()

    def _on_paste(self):
        try:
            self.app.copy_paste.paste()
        finally:
            self.close_menu()

    def _update_menu_zoom_display(self):
        if self.active and self.zoom_display_label:
            self.zoom_display_label.config(
                text=f"{int(self.app.vp.scale / 60.0 * 100)}%"
            )

    def _add_rotate_control(self):
        """Add rotate button below line settings."""
        row = tk.Frame(self.menu_frame, bg=self.menu_bg)
        row.pack(fill="x", padx=6, pady=(1, 6))

        rotate_btn = tk.Button(
            row,
            text="Rotate",
            command=self._on_rotate,
            font=("Segoe UI", 9),
            padx=8
        )
        self._style_button(rotate_btn)
        rotate_btn.pack(side="left", padx=(1, 6))

    def _add_trim_control(self):
        """Add trim button below line settings."""
        row = tk.Frame(self.menu_frame, bg=self.menu_bg)
        row.pack(fill="x", padx=6, pady=(0, 6))

        # NEW: Trim button
        trim_btn = tk.Button(
            row,
            text="Trim",
            command=self._on_trim,
            font=("Segoe UI", 9),
            padx=8
        )
        self._style_button(trim_btn)
        trim_btn.pack(side="left")

    def _on_rotate(self):
        try:
            self.app.activate_rotate()
        finally:
            self.close_menu()

    def _on_trim(self):
        try:
            self.app.activate_trim()
        finally:
            self.close_menu()



class FloorPlanCAD:
    def __init__(self, root):
        self.root = root
        self.root.title("Floor Plan CAD (v2)")

        # Window setup
        self._setup_window()
        self._setup_style()

        # Model
        self.vp = Viewport()
        self.lines = []

        # Constraints / dimensions (NEW)
        self.fixed_lengths = {}  # { Line: {"len":float, "label":(x,y)} }
        self.angle_constraints = []  # list of dicts:...":Line,"b":Line,"vx":float,"vy":float,"deg":float,"label":(x,y)}
        self.distance_constraints = []  # list of dicts:...:Line,"b":Line,"dist":float,"Pa":(x,y),"Pb":(x,y),"label":(x,y)}

        # Tool state
        self.tool_mode = "cursor"

        # Drawing state (line tool)
        self.drawing_line = False
        self.temp_line_start = None

        # Selection
        self.selected_line = None
        self.multi_selected = set()

        # Dragging state
        self.dragging_line = None
        self.dragging_point = None  # "start" / "end" / "body"
        self.drag_offset = (0.0, 0.0)

        # Solver context (which lines are currently being dragged)
        self._solver_drag_lines = set()

        # Panning
        self._pan_active = False
        self._pan_last = (0, 0)

        # Snapping
        self.snap_dist_endpoint = 0.20
        self.snap_dist_line = 0.15
        self.cursor_world = (0.0, 0.0)
        self.cursor_world_valid = False
        self.cursor_world_snapped = (0.0, 0.0)
        self.snap_hint = None  # ("endpoint", x,y) or ("line", x,y)

        # Group drag
        self._group_drag_active = False
        self._group_drag_start = (0.0, 0.0)
        self._group_drag_snapshot = []

        # Box (marquee) selection state
        self._box_active = False
        self._box_start = None
        self._box_end = None

        # Vertex manipulation
        self._vertex_temp = False
        self._vertex_drag_active = False
        self._vertex_hover = None
        self._vertex_drag_refs = []
        self._vertex_drag_start_mouse = (0.0, 0.0)
        self._vertex_drag_start_pos = (0.0, 0.0)

        # Connection behavior
        self.manipulate_line_var = tk.BooleanVar(value=False)  # when True, shared vertices can be broken by dragging
        self._weld_body_refs = None  # {'start':[(ln,'start'/'end'),...], 'end':[...]} captured on body-drag start

        # Line Match feature
        self.alignment_guides = []  # list of (x1, y1, x2, y2, 'type') where type is 'x' or 'y'
        self.parallel_guides = []  # list of (x1, y1, x2, y2, 'source_line') for parallel snapping
        self.equal_length_guides = []  # list of guide data for equal length visualization
        self.line_match_var = tk.BooleanVar(value=False)  # Line Match feature toggle

        # Smooth scheduling
        self._redraw_pending = False
        self._tree_pending = False

        # Angle snap UI
        self.angle_snap_tol_deg = 6.0
        self.snap_angle_vars = [tk.StringVar(value=""), tk.StringVar(value=""), tk.StringVar(value="")]

        # Visual Settings (moved up)
        from features import VisualSettings, ZoomController
        self.visuals = VisualSettings(self)
        self.zoom = ZoomController(self)
        
        # UI building
        self._build_ui()
        self._bind_events()

        self.root.after(0, self._initialize_view)
        self._request_redraw()

        self._undo_stack = []
        self._redo_stack = []

        # Dimension tool (NEW)
        self.dimension_tool = DimensionTool(self)

        # Start in cursor mode
        self.set_cursor_mode()

        # Copy/paste manager (NEW)
        self.copy_paste = CopyPasteManager(self)

        # Zoom controls (initialized above)
        # self.zoom = features.ZoomController(self)
        
        # Visual Settings (initialized above)
        # self.visuals = features.VisualSettings(self)

        # Snap controls
        self.snap = snap.SnapController(self)

        # Snap controls
        self.snap = snap.SnapController(self)

        # RIGHT-CLICK DROPDOWN MENU (NEW)
        self.dropdown = DropdownMenu(self)

        # Constraints / dimensions (NEW)
        self.fixed_lengths = {}
        self.angle_constraints = []
        self.distance_constraints = []

        self.dimension_rules = DimensionRules(self)

        # Rotate manager (NEW)
        self.rotate = RotateManager(self)

        # Trim manager (NEW)
        self.trim = TrimManager(self)

    # -------------------------
    # Window setup
    # -------------------------
    def _setup_window(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = int(sw * 0.85)
        h = int(sh * 0.85)
        x = (sw - w) // 2
        y = (sh - h) // 2 - 50

        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(int(sw * 0.55), int(sh * 0.55))
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

    def _setup_style(self):
        try:
            dpi = self.root.winfo_fpixels("1i")
            self.root.tk.call("tk", "scaling", max(1.0, min(2.0, dpi / 96.0)))
        except:
            pass

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except:
            pass

        style.configure("Treeview", background="#1A1A1A", fieldbackground="#1A1A1A", foreground="white")
        style.configure("Treeview.Heading", background="#2A2A2A", foreground="white")
        style.map("Treeview", background=[("selected", "#404040")], foreground=[("selected", "white")])

    # -------------------------
    # UI building
    # -------------------------
    def _build_ui(self):
        self.topbar = tk.Frame(self.root, bg="#2A2A2A")
        self.topbar.grid(row=0, column=0, sticky="nsew")

        self.main_area = ttk.Frame(self.root)
        self.main_area.grid(row=1, column=0, sticky="nsew")
        self.main_area.grid_rowconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(1, weight=1)

        self.bottombar = tk.Frame(self.root, bg="#2A2A2A")
        self.bottombar.grid(row=2, column=0, sticky="nsew")

        self._build_topbar()
        self._build_canvas_and_sidebar()
        self._build_bottombar()

    def _build_topbar(self):
        right = tk.Frame(self.topbar, bg="#2A2A2A")
        right.pack(side="right", padx=10, pady=6)

        self.cursor_btn = tk.Button(
            right, text="Cursor", command=self.set_cursor_mode,
            bg="#606060", fg="white", relief="flat",
            padx=10, pady=5, cursor="hand2"
        )
        self.cursor_btn.pack(side="left", padx=(0, 10))

        self.line_btn = tk.Button(
            right, text="Lines", command=self.set_line_mode,
            bg="#404040", fg="white", relief="flat",
            padx=10, pady=5, cursor="hand2"
        )
        self.line_btn.pack(side="left", padx=(0, 10))

        self.vertex_btn = tk.Button(
            right, text="Manipulate Vertex", command=self.set_vertex_mode,
            bg="#404040", fg="white", relief="flat",
            padx=10, pady=5, cursor="hand2"
        )
        self.vertex_btn.pack(side="left", padx=(0, 10))

        self.dim_btn = tk.Button(
            right, text="Dimension", command=self.set_dim_mode,
            bg="#404040", fg="white", relief="flat",
            padx=10, pady=5, cursor="hand2"
        )
        self.dim_btn.pack(side="left", padx=(0, 10))

        # Rotate button
        self.rotate_btn = tk.Button(
            right, text="Rotate", command=self.activate_rotate,
            bg="#404040", fg="white", relief="flat",
            padx=10, pady=5, cursor="hand2"
        )
        self.rotate_btn.pack(side="left", padx=(0, 10))

        # NEW: Trim button
        self.trim_btn = tk.Button(
            right, text="Trim", command=self.activate_trim,
            bg="#404040", fg="white", relief="flat",
            padx=10, pady=5, cursor="hand2"
        )
        self.trim_btn.pack(side="left", padx=(0, 12))

        self.manipulate_line_chk = tk.Checkbutton(
            right,
            text="Manipulate Line",
            variable=self.manipulate_line_var,
            onvalue=True,
            offvalue=False,
            bg="#2A2A2A",
            fg="white",
            selectcolor="#2A2A2A",
            activebackground="#2A2A2A",
            activeforeground="white",
            relief="flat",
            highlightthickness=0
        )
        self.manipulate_line_chk.pack(side="left", padx=(0, 15))

        if not hasattr(self, "snap_axis_var"):
            self.snap_axis_var = tk.BooleanVar(value=True)

        self.snap_axis_chk = tk.Checkbutton(
            right,
            text="Snap Axis",
            variable=self.snap_axis_var,
            onvalue=True,
            offvalue=False,
            bg="#2A2A2A",
            fg="white",
            selectcolor="#2A2A2A",
            activebackground="#2A2A2A",
            activeforeground="white",
            relief="flat",
            highlightthickness=0
        )
        self.snap_axis_chk.pack(side="left", padx=(0, 15))

        self.line_match_chk = tk.Checkbutton(
            right,
            text="Line Match",
            variable=self.line_match_var,
            onvalue=True,
            offvalue=False,
            bg="#2A2A2A",
            fg="white",
            selectcolor="#2A2A2A",
            activebackground="#2A2A2A",
            activeforeground="white",
            relief="flat",
            highlightthickness=0
        )
        self.line_match_chk.pack(side="left", padx=(0, 15))

        # NEW: Disable V.Point checkbox
        self.disable_v_point_chk = tk.Checkbutton(
            right,
            text="Disable V.Point",
            variable=self.visuals.disable_v_point_var,
            onvalue=True,
            offvalue=False,
            bg="#2A2A2A",
            fg="white",
            selectcolor="#2A2A2A",
            activebackground="#2A2A2A",
            activeforeground="white",
            relief="flat",
            highlightthickness=0,
            command=self._request_redraw
        )
        self.disable_v_point_chk.pack(side="left", padx=(0, 15))

        zoom_frame = tk.Frame(right, bg="#2A2A2A")
        zoom_frame.pack(side="left")

        tk.Label(zoom_frame, text="Zoom:", bg="#2A2A2A", fg="white").pack(side="left", padx=(0, 5))

        tk.Button(
            zoom_frame, text="-", command=self.zoom_out,
            bg="#404040", fg="white", relief="flat",
            width=3, cursor="hand2"
        ).pack(side="left", padx=2)

        self.zoom_display = tk.Label(
            zoom_frame, text="100%", bg="#2A2A2A",
            fg="white", width=8, anchor="center"
        )
        self.zoom_display.pack(side="left", padx=5)

        tk.Button(
            zoom_frame, text="+", command=self.zoom_in,
            bg="#404040", fg="white", relief="flat",
            width=3, cursor="hand2"
        ).pack(side="left", padx=2)

        tk.Button(
            zoom_frame, text="Reset", command=self.zoom_reset,
            bg="#404040", fg="white", relief="flat",
            padx=8, cursor="hand2"
        ).pack(side="left", padx=(10, 0))

    def _build_canvas_and_sidebar(self):
        tk.Frame(self.main_area, width=18, bg="#2A2A2A").grid(row=0, column=0, sticky="ns")

        content = tk.Frame(self.main_area, bg="#101214")
        content.grid(row=0, column=1, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        canvas_wrap = tk.Frame(content, bg="#101214")
        canvas_wrap.grid(row=0, column=0, sticky="nsew")

        self.canvas = tk.Canvas(canvas_wrap, bg="#101214", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.angle_snap_box = tk.Frame(canvas_wrap, bg="#2A2A2A")
        self.angle_snap_box.place(relx=0.0, rely=1.0, x=12, y=-12, anchor="sw")

        tk.Label(self.angle_snap_box, text="Angle Snap (deg):", bg="#2A2A2A", fg="white").pack(
            side="left", padx=(10, 8), pady=8
        )

        self.snap_angle_entries = []
        for v in self.snap_angle_vars:
            ent = tk.Entry(
                self.angle_snap_box, textvariable=v, width=5,
                bg="#1A1A1A", fg="white", insertbackground="white", relief="flat"
            )
            ent.pack(side="left", padx=4, pady=8)
            self.snap_angle_entries.append(ent)

        sidebar = tk.Frame(content, bg="#2A2A2A", width=320)
        sidebar.grid(row=0, column=1, sticky="ns")
        sidebar.grid_propagate(False)

        tk.Label(
            sidebar, text="FeatureManager", bg="#2A2A2A", fg="white",
            font=("Segoe UI", 11, "bold")
        ).pack(pady=(10, 5), padx=10, anchor="w")

        tree_frame = tk.Frame(sidebar, bg="#2A2A2A")
        tree_frame.pack(fill="both", expand=True, padx=6, pady=6)

        self.tree = ttk.Treeview(tree_frame, show="tree")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    def _build_bottombar(self):
        self.status_label = tk.Label(
            self.bottombar, text="", anchor="e",
            bg="#2A2A2A", fg="white"
        )
        self.status_label.pack(side="right", padx=10, pady=6)

    # -------------------------
    # Events
    # -------------------------
    def _bind_events(self):
        self.canvas.bind("<Configure>", lambda e: self._request_redraw())
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-4>", self.on_mousewheel_linux)
        self.canvas.bind("<Button-5>", self.on_mousewheel_linux)

        # NEW: when the cursor leaves the canvas, kill any snap/trace visuals
        self.canvas.bind("<Leave>", self.on_canvas_leave)

        # NEW: Double-click event
        self.canvas.bind("<Double-Button-1>", self.on_double_click)

        # RIGHT-CLICK: Open dropdown menu (NEW)
        self.canvas.bind("<ButtonPress-3>", self.on_right_click_menu)

        # ORIGINAL right-drag handlers moved to Shift+Right for box select
        self.canvas.bind("<Shift-ButtonPress-3>", self.on_right_down)
        self.canvas.bind("<Shift-B3-Motion>", self.on_right_drag)
        self.canvas.bind("<Shift-ButtonRelease-3>", self.on_right_up)

        self.root.bind("<Delete>", self.on_delete_key)
        self.root.bind("<BackSpace>", self.on_delete_key)
        self.root.bind("<Escape>", self.on_escape)

        # Global undo/redo
        self.root.bind_all("<Control-z>", self.on_undo, add="+")
        self.root.bind_all("<Control-Z>", self.on_undo, add="+")
        self.root.bind_all("<Control-y>", self.on_redo, add="+")
        self.root.bind_all("<Control-Y>", self.on_redo, add="+")
        self.root.bind_all("<Control-Shift-Z>", self.on_redo, add="+")

        # NEW: Copy/Paste bindings
        self.root.bind_all("<Control-c>", self.on_copy, add="+")
        self.root.bind_all("<Control-C>", self.on_copy, add="+")
        self.root.bind_all("<Control-v>", self.on_paste, add="+")
        self.root.bind_all("<Control-V>", self.on_paste, add="+")

        # For Trim Stuff
        self.root.bind("<KeyPress>", self.on_key_press, add="+")

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

    def _initialize_view(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.vp.offx = w * 0.5
        self.vp.offy = h * 0.5
        self._update_zoom_display()
        self._request_tree_update()
        self._request_redraw()

    # -------------------------
    # Smooth scheduling
    # -------------------------
    def _request_redraw(self):
        if self._redraw_pending:
            return
        self._redraw_pending = True
        self.root.after_idle(self._do_redraw)

    def _do_redraw(self):
        self._redraw_pending = False
        self.redraw()

    def _request_tree_update(self):
        if self._tree_pending:
            return
        self._tree_pending = True
        self.root.after_idle(self._do_tree_update)

    def _do_tree_update(self):
        self._tree_pending = False
        self._update_feature_tree()

    # -------------------------
    # Tool modes
    # -------------------------
    def _set_mode(self, mode):
        self.tool_mode = mode
        self.drawing_line = False
        self.temp_line_start = None
        self.snap_hint = None

        # NEW: when switching modes, kill any snap/trace visuals
        self.cursor_world_valid = False
        self.alignment_guides = []
        self.parallel_guides = []
        self.equal_length_guides = []

        self._vertex_temp = False
        self._vertex_drag_active = False
        self._vertex_hover = None
        self._vertex_drag_refs = []

        if mode == "vertex":
            self.dragging_line = None
            self.dragging_point = None
            self._pan_active = False
            self.selected_line = None
            self.hovered_line = None

        self.cursor_btn.config(bg="#606060" if mode == "cursor" else "#404040")
        self.line_btn.config(bg="#606060" if mode == "line" else "#404040")
        self.vertex_btn.config(bg="#606060" if mode == "vertex" else "#404040")
        self.dim_btn.config(bg="#606060" if mode == "dim" else "#404040")

        if mode == "cursor":
            self.root.config(cursor="arrow")
        elif mode == "line":
            self.root.config(cursor="cross")
        elif mode == "vertex":
            self.root.config(cursor="hand2")
        else:  # dim
            self.root.config(cursor="crosshair")  # NEW: distinct crosshair
            self.dimension_tool.activate()

        if mode != "dim":
            self.dimension_tool.cancel()

        self._request_redraw()

    def set_cursor_mode(self):
        self._set_mode("cursor")

    def set_line_mode(self):
        self._set_mode("line")

    def set_vertex_mode(self):
        self._set_mode("vertex")

    def set_dim_mode(self):
        self._set_mode("dim")

    # -------------------------
    # ESC behavior
    # -------------------------
    def on_escape(self, e=None):
        # Cancel trim if active
        if self.trim.active:
            self.trim.cancel()
            return

        # Cancel rotate if active
        if self.rotate.active:
            self.rotate.cancel()
            return

        # Cancel paste if active
        if self.copy_paste.paste_active:
            self.copy_paste.cancel_paste()
            return

        if self.tool_mode == "dim":
            self.dimension_tool.on_escape()
            self.set_cursor_mode()
            return

        self.drawing_line = False
        self.temp_line_start = None

        self._vertex_drag_active = False
        self._vertex_drag_refs = []
        self._vertex_hover = None

        self.dragging_line = None
        self.dragging_point = None
        self._pan_active = False

        self.snap_hint = None
        self.selected_line = None
        self.multi_selected.clear()

        self.dimension_tool._selected_kind = None
        self.dimension_tool._selected_id = None
        self.dimension_tool._multi_selected_dims.clear()

        # NEW: clear ALL snap/trace visuals on ESC
        self.cursor_world_valid = False
        self.alignment_guides = []
        self.parallel_guides = []
        self.equal_length_guides = []

        self.hovered_line = None
        self.set_cursor_mode()

    def on_key_press(self, e):
        """Global key press handler for special modes."""
        # Trim mode intercept
        if self.trim.active:
            if self.trim.on_key_press(e):
                return "break"
        return None

    # -------------------------
    # Selection / deletion
    # -------------------------
    def _set_selected_line(self, ln):
        if self.tool_mode == "vertex":
            return
        self.selected_line = ln
        self._request_redraw()

    def _delete_selected_line(self):
        if self.selected_line is None:
            return
        try:
            # also purge constraints involving this line
            self.fixed_lengths.pop(self.selected_line, None)
            self.angle_constraints = [c for c in self.angle_constraints if c["a"] is not self.selected_line and c["b"] is not self.selected_line]
            self.distance_constraints = [c for c in self.distance_constraints if c["a"] is not self.selected_line and c["b"] is not self.selected_line]
            self.lines.remove(self.selected_line)
        except:
            pass
        self.selected_line = None
        self._prune_zero_lines()
        self._request_tree_update()
        self._request_redraw()

    def _delete_selected_dimension_from_tree(self):
        # if the selected Tree item is a dimension, remove it
        sel = self.tree.selection()
        if not sel:
            return False
        iid = sel[0]
        if iid not in self._tree_dim_iids:
            return False

        # We stored the removal lambda on the iid's "values"
        payload = self.tree.item(iid, "values")
        if payload and len(payload) == 1:
            key = payload[0]
            # key looks like "len:<id>", "ang:<index>", "dist:<index>"
            kind, ident = key.split(":", 1)
            if kind == "len":
                target = None
                for ln in self.lines:
                    if id(ln) == int(ident):
                        target = ln
                        break
                if target is not None:
                    self.fixed_lengths.pop(target, None)
            elif kind == "ang":
                idx = int(ident)
                if 0 <= idx < len(self.angle_constraints):
                    self.angle_constraints.pop(idx)
            elif kind == "dist":
                idx = int(ident)
                if 0 <= idx < len(self.distance_constraints):
                    self.distance_constraints.pop(idx)
            self._request_tree_update()
            self._request_redraw()
            return True
        return False

    def on_delete_key(self, e=None):
        if self._delete_selected_dimension_from_tree():
            return
        if self.tool_mode == "vertex":
            return
        if self.multi_selected:
            self._push_undo()
            dead = set(self.multi_selected)
            # purge constraints that touch any deleted line
            self.angle_constraints = [c for c in self.angle_constraints if c["a"] not in dead and c["b"] not in dead]
            self.distance_constraints = [c for c in self.distance_constraints if c["a"] not in dead and c["b"] not in dead]
            for ln in list(dead):
                self.fixed_lengths.pop(ln, None)
            self.lines = [ln for ln in self.lines if ln not in dead]
            self.multi_selected.clear()
            self.selected_line = None
            self._prune_zero_lines()
            self._request_tree_update()
            self._request_redraw()
            return
        self._delete_selected_line()

    def on_tree_select(self, e=None):
        if self.tool_mode == "vertex":
            return
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        ln = None
        cur = iid
        while cur:
            if cur in self._tree_iid_to_line:
                ln = self._tree_iid_to_line[cur]
                break
            cur = self.tree.parent(cur)
            if cur == "":
                break
        if ln is not None:
            self._set_selected_line(ln)

    # -------------------------
    # Geometry helpers
    # -------------------------
    def _vkey(self, x, y):
        return (round(x, 6), round(y, 6))

    def _angle_at_vertex_deg(self, l1, l2, vx, vy):
        def out_vec(ln):
            if math.hypot(ln.x1 - vx, ln.y1 - vy) < 1e-6:
                return (ln.x2 - vx, ln.y2 - vy)
            return (ln.x1 - vx, ln.y1 - vy)
        a = out_vec(l1)
        b = out_vec(l2)
        ma = math.hypot(a[0], a[1])
        mb = math.hypot(b[0], b[1])
        if ma < 1e-9 or mb < 1e-9:
            return None
        dot = (a[0] * b[0] + a[1] * b[1]) / (ma * mb)
        dot = max(-1.0, min(1.0, dot))
        return math.degrees(math.acos(dot))

    def _prune_zero_lines(self):
        keep = [ln for ln in self.lines if ln.length() > 1e-6]
        self.lines = keep
        if self.selected_line is not None and self.selected_line not in self.lines:
            self.selected_line = None

    # -------------------------
    # Snapping helpers
    # -------------------------
    def _find_snap(self, wx, wy, ignore_line=None, ignore_points=None):
        return self.snap._find_snap(wx, wy, ignore_line=ignore_line, ignore_points=ignore_points)

    def _apply_snap_for_cursor(self, wx, wy, ignore_line=None, ignore_points=None):
        return self.snap._apply_snap_for_cursor(wx, wy, ignore_line=ignore_line, ignore_points=ignore_points)

    # -------------------------
    # Vertex helpers
    # -------------------------
    def _find_vertex_near(self, wx, wy):
        return self.snap._find_vertex_near(wx, wy)

    def _collect_vertex_refs(self, vx, vy):
        return self.snap._collect_vertex_refs(vx, vy)

    def _set_refs_vertex(self, refs, x, y):
        return self.snap._set_refs_vertex(refs, x, y)

    def _vertex_candidate_positions(self, raw_x, raw_y):
        return self.snap._vertex_candidate_positions(raw_x, raw_y)

    # -------------------------
    # Mouse handling
    # -------------------------
    def _line_is_locked(self, ln):
        # We no longer "lock" lines to prevent dragging.
        # Constraints are enforced by solving after motion.
        return False

    def on_mouse_down(self, e):
        # Trim intercept (highest priority)
        if self.trim.active:
            self.trim.on_mouse_down(e)
            return

        # Rotate intercept
        if self.rotate.active:
            self.rotate.on_mouse_down(e)
            return

        # Close dropdown menu if open (left-click anywhere closes it)
        if self.dropdown.active:
            self.dropdown.close_menu()
            return

        # Copy/paste intercept
        if self.copy_paste.paste_active:
            self.copy_paste.on_mouse_down(e)
            return

        wx, wy = self.vp.screen_to_world(e.x, e.y)
        ctrl = bool(e.state & 0x0004)

        # DIM pre-capture: allow grabbing persisted dimensions in both Cursor & Dim modes
        if self.tool_mode in ("cursor", "dim"):
            if self.dimension_tool.pre_handle_mouse_down(e):
                return

        if self.tool_mode == "dim":
            self.dimension_tool.on_mouse_down(e)
            return

        # SHIFT + LMB temp vertex manipulate (unchanged)
        if self.tool_mode == "cursor" and (e.state & 0x0001):
            hit = self._find_vertex_near(wx, wy)
            if hit is not None:
                vx, vy = hit
                if self._is_protected_vertex(vx, vy):
                    return
                refs = self._collect_vertex_refs(vx, vy)
                if refs:
                    self._push_undo()
                    self._vertex_temp = True
                    self.tool_mode = "vertex"
                    self._vertex_drag_active = True
                    self._vertex_drag_refs = refs
                    self._vertex_drag_start_mouse = (wx, wy)
                    self._vertex_drag_start_pos = (vx, vy)
                    self._vertex_hover = (vx, vy)
                    self.snap_hint = ("endpoint", vx, vy)
                    self._request_redraw()
                    return

        if self.tool_mode == "vertex":
            hit = self._find_vertex_near(wx, wy)
            if hit is None:
                return
            vx, vy = hit
            refs = self._collect_vertex_refs(vx, vy)
            if not refs:
                return
            self._push_undo()
            self._vertex_drag_active = True
            self._vertex_drag_refs = refs
            self._vertex_drag_start_mouse = (wx, wy)
            self._vertex_drag_start_pos = (vx, vy)
            self._vertex_hover = (vx, vy)
            self.snap_hint = ("endpoint", vx, vy)
            self._request_redraw()
            return

        if self.tool_mode == "line":
            self._apply_snap_for_cursor(wx, wy)
            sx, sy = self.cursor_world_snapped
            if not self.drawing_line:
                self.drawing_line = True
                self.temp_line_start = (sx, sy)
                self._request_redraw()
            else:
                x1, y1 = self.temp_line_start
                x2, y2 = sx, sy
                if math.hypot(x2 - x1, y2 - y1) > 1e-6:
                    self._push_undo()
                    self.lines.append(Line(x1, y1, x2, y2))
                self.drawing_line = False
                self.temp_line_start = None
                self._request_tree_update()
                self._request_redraw()
            return

        # Cursor mode selection/drag logic
        if self.tool_mode == "cursor":
            hit_threshold = getattr(self, "hit_threshold", 0.15)

            # If Ctrl is held, don't start group drag
            if (not ctrl) and self.multi_selected:
                for ln in list(self.multi_selected):
                    if ln.distance_to_point(wx, wy) < hit_threshold:
                        self._push_undo()
                        self._group_drag_active = True
                        self._group_drag_start = (wx, wy)
                        self._group_drag_snapshot = [(l, l.x1, l.y1, l.x2, l.y2) for l in self.multi_selected]
                        return

            hit_line = None
            hit_kind = None
            for ln in self.lines:
                if math.hypot(wx - ln.x1, wy - ln.y1) < hit_threshold:
                    hit_line = ln
                    hit_kind = "start"
                    break
                if math.hypot(wx - ln.x2, wy - ln.y2) < hit_threshold:
                    hit_line = ln
                    hit_kind = "end"
                    break
            if hit_line is None:
                for ln in self.lines:
                    if ln.distance_to_point(wx, wy) < hit_threshold:
                        hit_line = ln
                        hit_kind = "body"
                        break

            # Ctrl+click toggles line multi-select (and does NOT pan)
            if ctrl:
                if hit_line is None:
                    return
                if hit_line in self.multi_selected:
                    self.multi_selected.remove(hit_line)
                else:
                    self.multi_selected.add(hit_line)
                if not self.multi_selected:
                    self.selected_line = None
                self._request_redraw()
                return

            # Normal click on a line: select + drag
            if hit_line is not None:
                if hit_kind in ("start", "end"):
                    vx, vy = (hit_line.x1, hit_line.y1) if hit_kind == "start" else (hit_line.x2, hit_line.y2)
                    if (not self.manipulate_line_var.get()) or self._is_protected_vertex(vx, vy):
                        refs = self._collect_vertex_refs(vx, vy)
                        if refs and len(refs) > 1:
                            self._push_undo()
                            self._vertex_temp = True
                            self.tool_mode = "vertex"
                            self._vertex_drag_active = True
                            self._vertex_drag_refs = refs
                            self._vertex_drag_start_mouse = (wx, wy)
                            self._vertex_drag_start_pos = (vx, vy)
                            self._vertex_hover = (vx, vy)
                            self.snap_hint = ("endpoint", vx, vy)
                            self._request_redraw()
                            return

                self._push_undo()
                self.multi_selected.clear()
                self._set_selected_line(hit_line)
                self.dragging_line = hit_line
                self.dragging_point = hit_kind
                if hit_kind == "body":
                    self.drag_offset = (wx - hit_line.x1, wy - hit_line.y1)
                return

            # Empty click (normal): clear selection + START PAN
            self.selected_line = None
            self.multi_selected.clear()

            # also clear dim highlights on normal empty click
            self.dimension_tool._selected_kind = None
            self.dimension_tool._selected_id = None
            self.dimension_tool._multi_selected_dims.clear()

            self._pan_active = True
            self._pan_last = (e.x, e.y)
            self._request_redraw()
            return

    def on_mouse_drag(self, e):
        # Copy/paste intercept
        if self.copy_paste.paste_active:
            self.copy_paste.on_mouse_drag(e)
            return

        # Dimension dragging has priority
        if self.tool_mode in ("cursor", "dim"):
            if self.dimension_tool.pre_handle_mouse_drag(e):
                return

        if self.tool_mode == "dim":
            return  # dim tool itself doesn't drag geometry here

        wx, wy = self.vp.screen_to_world(e.x, e.y)
        self.cursor_world = (wx, wy)

        # Group move
        if self.tool_mode == "cursor" and self._group_drag_active and self._group_drag_snapshot:
            dx = wx - self._group_drag_start[0]
            dy = wy - self._group_drag_start[1]
            for ln, x1, y1, x2, y2 in self._group_drag_snapshot:
                ox1, oy1, ox2, oy2 = ln.x1, ln.y1, ln.x2, ln.y2
                ln.x1 = x1 + dx;
                ln.y1 = y1 + dy
                ln.x2 = x2 + dx;
                ln.y2 = y2 + dy
                if (not self.manipulate_line_var.get()) or self._is_protected_vertex(ox1, oy1):
                    self._weld_propagate_vertex_move(ox1, oy1, ln.x1, ln.y1, ignore_line=ln)
                if (not self.manipulate_line_var.get()) or self._is_protected_vertex(ox2, oy2):
                    self._weld_propagate_vertex_move(ox2, oy2, ln.x2, ln.y2, ignore_line=ln)

            self._solver_drag_lines = {ln for (ln, *_rest) in self._group_drag_snapshot}
            self._solve_constraints(3)
            self._request_tree_update()
            self._request_redraw()
            return

        # Vertex drag
        if self.tool_mode == "vertex" and self._vertex_drag_active and self._vertex_drag_refs:
            rawx, rawy = wx, wy
            cx, cy = self._vertex_candidate_positions(rawx, rawy)
            ox, oy = self._vertex_drag_start_pos
            self._set_refs_vertex(self._vertex_drag_refs, cx, cy)
            self._vertex_hover = (cx, cy)
            self.snap_hint = ("endpoint", cx, cy)
            self._weld_propagate_vertex_move(ox, oy, cx, cy, ignore_line=None)
            self._solver_drag_lines = {ln for (ln, _which) in self._vertex_drag_refs}
            self._solve_constraints(4)
            self._request_tree_update()
            self._request_redraw()
            return

        # Pan
        if self._pan_active:
            dx = e.x - self._pan_last[0]
            dy = e.y - self._pan_last[1]
            self._pan_last = (e.x, e.y)
            self.vp.offx += dx;
            self.vp.offy += dy
            self._request_redraw()
            return

        # Line drag in cursor mode
        if self.tool_mode == "cursor" and self.dragging_line is not None and self.dragging_point is not None:
            ln = self.dragging_line
            ox1, oy1, ox2, oy2 = ln.x1, ln.y1, ln.x2, ln.y2
            if self.dragging_point == "body":
                dx = wx - (ln.x1 + self.drag_offset[0])
                dy = wy - (ln.y1 + self.drag_offset[1])
                ln.x1 += dx;
                ln.y1 += dy;
                ln.x2 += dx;
                ln.y2 += dy
                if (not self.manipulate_line_var.get()) or self._is_protected_vertex(ox1, oy1):
                    self._weld_propagate_vertex_move(ox1, oy1, ln.x1, ln.y1, ignore_line=ln)
                if (not self.manipulate_line_var.get()) or self._is_protected_vertex(ox2, oy2):
                    self._weld_propagate_vertex_move(ox2, oy2, ln.x2, ln.y2, ignore_line=ln)
            elif self.dragging_point in ("start", "end"):
                # (existing endpoint drag logic unchanged)
                if self.dragging_point == "start":
                    vx_old, vy_old = ox1, oy1;
                    otherx, othery = ox2, oy2;
                    targetx, targety = wx, wy
                else:
                    vx_old, vy_old = ox2, oy2;
                    otherx, othery = ox1, oy1;
                    targetx, targety = wx, wy
                weld_required = (not self.manipulate_line_var.get()) or self._is_protected_vertex(vx_old, vy_old)
                ignore_pts = {self._vkey(otherx, othery)}
                sx, sy, skind = self._find_snap(targetx, targety, ignore_line=ln, ignore_points=ignore_pts)
                if skind == "endpoint":
                    self.snap_hint = ("endpoint", sx, sy)
                    if ln not in self.fixed_lengths:
                        targetx, targety = sx, sy
                else:
                    self.snap_hint = None
                    if self.manipulate_line_var.get():
                        targetx, targety = self._apply_line_match_snap(otherx, othery, targetx, targety, ignore_line=ln)
                if ln in self.fixed_lengths:
                    L = float(self.fixed_lengths[ln]["len"])
                    dx = targetx - otherx;
                    dy = targety - othery
                    d = math.hypot(dx, dy)
                    if d < 1e-9: return
                    ux, uy = dx / d, dy / d
                    targetx = otherx + ux * L;
                    targety = othery + uy * L
                if self.dragging_point == "start":
                    ln.x1, ln.y1 = targetx, targety
                else:
                    ln.x2, ln.y2 = targetx, targety
                if weld_required:
                    self._weld_propagate_vertex_move(vx_old, vy_old, targetx, targety, ignore_line=ln)
            self._solver_drag_lines = {ln}
            self._solve_constraints(5)
            self._request_tree_update()
            self._request_redraw()
            return

    def on_mouse_up(self, e):
        # Copy/paste intercept
        if self.copy_paste.paste_active:
            self.copy_paste.on_mouse_up(e)
            return

        # Finish dimension drag first
        if self.tool_mode in ("cursor", "dim"):
            if self.dimension_tool.pre_handle_mouse_up(e):
                return

        if self.tool_mode == "dim":
            return

        if self._group_drag_active or self.dragging_line or self._vertex_drag_active:
            self._solve_constraints(8)

        self._solver_drag_lines.clear()
        self._group_drag_active = False
        self._group_drag_snapshot = []
        self.dragging_line = None
        self.dragging_point = None

        if self.tool_mode == "vertex" and self._vertex_temp:
            self.tool_mode = "cursor"
            self._vertex_temp = False

        self._vertex_drag_active = False
        self._vertex_drag_refs = []
        self._vertex_hover = None
        self.snap_hint = None
        self._pan_active = False

        self._prune_zero_lines()
        self._request_tree_update()
        self._request_redraw()

    def on_mouse_move(self, e):
        # Trim intercept
        if self.trim.active:
            self.trim.on_mouse_move(e)
            return

        # Rotate intercept
        if self.rotate.active:
            self.rotate.on_mouse_move(e)
            return

        wx, wy = self.vp.screen_to_world(e.x, e.y)
        self.cursor_world = (wx, wy)
        self.cursor_world_valid = True

        # DIM hover in both Cursor + Dim tools
        if self.tool_mode in ("cursor", "dim"):
            consumed = self.dimension_tool.pre_handle_mouse_move(e)

        if self.tool_mode == "dim":
            self.dimension_tool.on_mouse_move(e)
            return

        if self.tool_mode == "line":
            self._apply_snap_for_cursor(wx, wy)
            self._request_redraw()
            return

        if self.tool_mode == "vertex":
            if not self._vertex_drag_active:
                hit = self._find_vertex_near(wx, wy)
                self._vertex_hover = hit
                self.snap_hint = ("endpoint", hit[0], hit[1]) if hit is not None else None
                self._request_redraw()
            return

        if self.tool_mode == "cursor":
            if not self.dragging_line:
                self.hovered_line = None
                hit_threshold = getattr(self, "hit_threshold", 0.15)
                for ln in self.lines:
                    if ln.distance_to_point(wx, wy) < hit_threshold:
                        self.hovered_line = ln
                        break
                self.snap_hint = None
                self._request_redraw()

    # -------------------------
    # FeatureManager
    # -------------------------
    def _update_feature_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._tree_iid_to_line = {}
        self._tree_dim_iids = set()
        if not self.lines:
            return

        line_to_idx = {ln: i + 1 for i, ln in enumerate(self.lines)}

        vert_to_lines = {}
        for ln in self.lines:
            k1 = self._vkey(ln.x1, ln.y1)
            k2 = self._vkey(ln.x2, ln.y2)
            vert_to_lines.setdefault(k1, []).append(ln)
            vert_to_lines.setdefault(k2, []).append(ln)

        # Build tree
        for i, ln in enumerate(self.lines, start=1):
            parent = self.tree.insert("", "end", text=f"Line{i}", open=True)
            self._tree_iid_to_line[parent] = ln

            self.tree.insert(parent, "end", text=f"Size: {ln.length():.3f} units")
            self.tree.insert(parent, "end", text=f"Start Vertex: ({ln.x1:.3f}, {ln.y1:.3f})")
            self.tree.insert(parent, "end", text=f"End Vertex:   ({ln.x2:.3f}, {ln.y2:.3f})")

            # Length constraint (if any)
            if ln in self.fixed_lengths:
                p = self.tree.insert(parent, "end", text=f"Length = {self.fixed_lengths[ln]['len']:.3f}", open=False, values=(f"len:{id(ln)}",))
                self._tree_dim_iids.add(p)

            # Angles connected to this line
            angles_parent = None
            for idx, ent in enumerate(self.angle_constraints):
                if ent["a"] is ln or ent["b"] is ln:
                    if angles_parent is None:
                        angles_parent = self.tree.insert(parent, "end", text="Angles", open=True)
                    other = ent["b"] if ent["a"] is ln else ent["a"]
                    j = line_to_idx.get(other, "?")
                    q = self.tree.insert(angles_parent, "end", text=f"With Line{j}: {ent['deg']:.1f}°", values=(f"ang:{idx}",))
                    self._tree_dim_iids.add(q)

            # Distances involving this line
            dparent = None
            for idx, ent in enumerate(self.distance_constraints):
                if ent["a"] is ln or ent["b"] is ln:
                    if dparent is None:
                        dparent = self.tree.insert(parent, "end", text="Distances", open=True)
                    other = ent["b"] if ent["a"] is ln else ent["a"]
                    j = line_to_idx.get(other, "?")
                    q = self.tree.insert(dparent, "end", text=f"To Line{j}: {ent['dist']:.3f}", values=(f"dist:{idx}",))
                    self._tree_dim_iids.add(q)

    # -------------------------
    # Zoom controls
    # -------------------------
    def zoom_in(self):
        return self.zoom.zoom_in()

    def zoom_out(self):
        return self.zoom.zoom_out()

    def zoom_reset(self):
        return self.zoom.zoom_reset()

    def _update_zoom_display(self):
        return self.zoom._update_zoom_display()

    def on_mousewheel(self, e):
        return self.zoom.on_mousewheel(e)

    def on_mousewheel_linux(self, e):
        return self.zoom.on_mousewheel_linux(e)

    # -------------------------
    # Drawing
    # -------------------------
    def redraw(self):
        self.canvas.delete("all")
        self.draw_axes()
        self.draw_origin_marker()
        self.draw_lines()

        if self.drawing_line and self.temp_line_start:
            self.draw_temp_line()

        self.draw_alignment_guides()

        # Snap / vertex highlight circle
        if self.tool_mode == "vertex":
            if self._vertex_hover is not None:
                self.draw_snap_circle(self._vertex_hover[0], self._vertex_hover[1])
            elif self.snap_hint and self.snap_hint[0] == "endpoint":
                _, x, y = self.snap_hint
                self.draw_snap_circle(x, y)
        else:
            if self.snap_hint and self.snap_hint[0] == "endpoint":
                _, x, y = self.snap_hint
                self.draw_snap_circle(x, y)

        # Dimension overlays (preview + persisted)
        self.dimension_tool.draw_overlay(self.canvas)

        # Rotate overlay
        self.rotate.draw_overlay(self.canvas)

        # Trim overlay (NEW)
        self.trim.draw_overlay(self.canvas)

        # Copy/paste preview
        self.copy_paste.draw_preview(self.canvas)

        if self.tool_mode == "cursor" and self._box_active:
            x0, y0 = self._box_s0
            x1, y1 = self._box_s1
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#FFFFFF", width=1, dash=(3, 3))

        self._update_status()

    def _update_status(self):
        wx, wy = self.cursor_world
        self.status_label.config(text=f"X: {wx:.3f}   Y: {wy:.3f}     Zoom: {self.vp.scale:.1f} px/unit")

    def draw_axes(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        x0, y0 = self.vp.screen_to_world(0, 0)
        x1, y1 = self.vp.screen_to_world(w, h)

        sx0, sy0 = self.vp.world_to_screen(x0, 0.0)
        sx1, sy1 = self.vp.world_to_screen(x1, 0.0)
        tx0, ty0 = self.vp.world_to_screen(0.0, y0)
        tx1, ty1 = self.vp.world_to_screen(0.0, y1)

        self.canvas.create_line(sx0, sy0, sx1, sy1, fill="#000000", width=2)
        self.canvas.create_line(tx0, ty0, tx1, ty1, fill="#000000", width=2)

        step = self.nice_grid_step()
        tick_px = 6

        start = math.floor(min(x0, x1) / step) * step
        end = math.ceil(max(x0, x1) / step) * step
        x = start
        while x <= end + EPS:
            sx, sy = self.vp.world_to_screen(x, 0.0)
            self.canvas.create_line(sx, sy - tick_px, sx, sy + tick_px, fill="#000000", width=1)
            if abs(x) > EPS:
                self.canvas.create_text(sx, sy + 18, text=self.fmt(x), fill="#CCCCCC", font=("Segoe UI", 9))
            x += step

        start = math.floor(min(y0, y1) / step) * step
        end = math.ceil(max(y0, y1) / step) * step
        y = start
        while y <= end + EPS:
            sx, sy = self.vp.world_to_screen(0.0, y)
            self.canvas.create_line(sx - tick_px, sy, sx + tick_px, sy, fill="#000000", width=1)
            if abs(y) > EPS:
                self.canvas.create_text(sx + 10, sy, text=self.fmt(y), fill="#CCCCCC", font=("Segoe UI", 9), anchor="w")
            y += step

    def draw_origin_marker(self):
        sx, sy = self.vp.world_to_screen(0.0, 0.0)
        r = 5
        self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, fill="#FFFFFF", outline="")

    def draw_lines(self):
        for ln in self.lines:
            sx1, sy1 = self.vp.world_to_screen(ln.x1, ln.y1)
            sx2, sy2 = self.vp.world_to_screen(ln.x2, ln.y2)

            if self.tool_mode == "cursor" and ln in self.multi_selected:
                color = "#FF5C5C"
            elif self.tool_mode != "vertex" and ln is self.selected_line:
                color = "#FF5C5C"
            elif self.tool_mode == "dim" and ln == self.hovered_line:
                color = "#FF5C5C"  # NEW: hover highlight in dimension tool
            elif self.tool_mode == "cursor" and ln == self.hovered_line:
                color = "#FF5C5C"
            else:
                color = ln.color

            self.canvas.create_line(sx1, sy1, sx2, sy2, fill=color, width=2)

            r = 4
            
            # Start Vertex
            show_start = True
            if self.visuals.disable_v_point_var.get():
                is_dragging_start = False
                if self._vertex_drag_active:
                     # check if (ln, 'start') is in refs
                     for dln, dside in self._vertex_drag_refs:
                         if dln is ln and dside == "start":
                             is_dragging_start = True
                             break
                # Also check simple drag (Cursor tool single line drag)
                if self.dragging_line is ln and self.dragging_point == "start":
                    is_dragging_start = True
                
                if not is_dragging_start:
                    # Check distance to cursor
                    cwx, cwy = self.cursor_world
                    dist = math.hypot(ln.x1 - cwx, ln.y1 - cwy)
                    if dist > self.hit_threshold:
                        show_start = False
            
            if show_start:
                self.canvas.create_oval(sx1 - r, sy1 - r, sx1 + r, sy1 + r, fill=color, outline="white")

            # End Vertex
            show_end = True
            if self.visuals.disable_v_point_var.get():
                is_dragging_end = False
                if self._vertex_drag_active:
                     # check if (ln, 'end') is in refs
                     for dln, dside in self._vertex_drag_refs:
                         if dln is ln and dside == "end":
                             is_dragging_end = True
                             break
                # Also check simple drag (Cursor tool single line drag)
                if self.dragging_line is ln and self.dragging_point == "end":
                    is_dragging_end = True

                if not is_dragging_end:
                    # Check distance to cursor
                    cwx, cwy = self.cursor_world
                    dist = math.hypot(ln.x2 - cwx, ln.y2 - cwy)
                    if dist > self.hit_threshold:
                        show_end = False

            if show_end:
                self.canvas.create_oval(sx2 - r, sy2 - r, sx2 + r, sy2 + r, fill=color, outline="white")

    def draw_temp_line(self):
        sx1, sy1 = self.vp.world_to_screen(self.temp_line_start[0], self.temp_line_start[1])
        wx, wy = self.cursor_world_snapped if self.tool_mode == "line" else self.cursor_world
        sx2, sy2 = self.vp.world_to_screen(wx, wy)
        self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#888888", width=2, dash=(5, 5))
        r = 4
        self.canvas.create_oval(sx1 - r, sy1 - r, sx1 + r, sy1 + r, fill="#888888", outline="white")

    def draw_snap_circle(self, wx, wy):
        sx, sy = self.vp.world_to_screen(wx, wy)
        r = 10
        self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, outline="#FFFFFF", width=2)

    def nice_grid_step(self):
        raw = 90.0 / max(self.vp.scale, EPS)
        if raw <= 0:
            return 1.0
        p = 10 ** math.floor(math.log10(raw))
        candidates = [p, 2 * p, 5 * p, 10 * p]
        return min(candidates, key=lambda c: abs(c - raw))

    def fmt(self, v):
        av = abs(v)
        if av < 1e-6:
            return "0"
        if av < 10:
            return f"{v:.2f}".rstrip("0").rstrip(".")
        if av < 100:
            return f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{v:.0f}"

    # -------------------------
    # Box select
    # -------------------------
    def _point_in_rect(self, x, y, x0, y0, x1, y1):
        xmin, xmax = (x0, x1) if x0 <= x1 else (x1, x0)
        ymin, ymax = (y0, y1) if y0 <= y1 else (y1, y0)
        return (xmin - 1e-12) <= x <= (xmax + 1e-12) and (ymin - 1e-12) <= y <= (ymax + 1e-12)

    def _seg_intersects_rect(self, xA, yA, xB, yB, x0, y0, x1, y1):
        xmin, xmax = (x0, x1) if x0 <= x1 else (x1, x0)
        ymin, ymax = (y0, y1) if y0 <= y1 else (y1, y0)

        if self._point_in_rect(xA, yA, xmin, ymin, xmax, ymax) or self._point_in_rect(xB, yB, xmin, ymin, xmax, ymax):
            return True

        dx = xB - xA
        dy = yB - yA
        p = [-dx, dx, -dy, dy]
        q = [xA - xmin, xmax - xA, yA - ymin, ymax - yA]

        u1, u2 = 0.0, 1.0
        for pi, qi in zip(p, q):
            if abs(pi) < 1e-12:
                if qi < 0:
                    return False
            else:
                t = qi / pi
                if pi < 0:
                    u1 = max(u1, t)
                else:
                    u2 = min(u2, t)
                if u1 > u2:
                    return False
        return True

    def _select_lines_in_world_rect(self, x0, y0, x1, y1):
        """Select lines and dimensions in world rectangle."""
        self.multi_selected.clear()
        self.dimension_tool._multi_selected_dims.clear()

        # Select lines
        for ln in self.lines:
            if self._seg_intersects_rect(ln.x1, ln.y1, ln.x2, ln.y2, x0, y0, x1, y1):
                self.multi_selected.add(ln)

        if self.multi_selected:
            self.selected_line = None

        # Also select dimensions that are inside the box
        xmin, xmax = (x0, x1) if x0 <= x1 else (x1, x0)
        ymin, ymax = (y0, y1) if y0 <= y1 else (y1, y0)

        def point_in_box(px, py):
            return xmin <= px <= xmax and ymin <= py <= ymax

        # Check length dimensions
        for ln, meta in self.fixed_lengths.items():
            label = meta.get('label', ((ln.x1 + ln.x2) / 2, (ln.y1 + ln.y2) / 2))
            if point_in_box(label[0], label[1]):
                self.dimension_tool._multi_selected_dims.add(('len', ln))

        # Check angle dimensions
        for idx, ent in enumerate(self.angle_constraints):
            lx, ly = self.dimension_tool._angle_label_world(ent)
            if point_in_box(lx, ly):
                self.dimension_tool._multi_selected_dims.add(('ang', idx))

        # Check distance dimensions
        for idx, ent in enumerate(self.distance_constraints):
            label = ent.get('label', None)
            if label and point_in_box(label[0], label[1]):
                self.dimension_tool._multi_selected_dims.add(('dist', idx))

    def on_right_down(self, e):
        if self.tool_mode != "cursor":
            return
        self._box_active = True
        self._box_s0 = (e.x, e.y)
        self._box_s1 = (e.x, e.y)
        self._request_redraw()

    def on_right_drag(self, e):
        if not self._box_active or self.tool_mode != "cursor":
            return
        self._box_s1 = (e.x, e.y)
        self._request_redraw()

    def on_right_up(self, e):
        if not self._box_active or self.tool_mode != "cursor":
            self._box_active = False
            return

        self._box_s1 = (e.x, e.y)
        sx0, sy0 = self._box_s0
        sx1, sy1 = self._box_s1

        wx0, wy0 = self.vp.screen_to_world(sx0, sy0)
        wx1, wy1 = self.vp.screen_to_world(sx1, sy1)

        self._select_lines_in_world_rect(wx0, wy0, wx1, wy1)

        self._box_active = False
        self._request_redraw()

    # -------------------------
    # Angle snap
    # -------------------------
    def _get_angle_snap_list(self):
        return self.snap._get_angle_snap_list()

    def _wrap_pi(self, a):
        return math.atan2(math.sin(a), math.cos(a))

    def _angle_snap_if_close(self, x0, y0, x1, y1):
        return self.snap._angle_snap_if_close(x0, y0, x1, y1)

    def _apply_angle_snap_for_line(self, x_fixed, y_fixed, x_free, y_free):
        return self.snap._apply_angle_snap_for_line(x_fixed, y_fixed, x_free, y_free)

    # -------------------------
    # Constraint writers (called by DimensionTool)
    # -------------------------
    def _add_or_update_angle(self, a, b, vx, vy, deg, meta):
        # meta is dict: {"side": +/-1, "off": float}
        def same(ent):
            return ((ent["a"] is a and ent["b"] is b) or (ent["a"] is b and ent["b"] is a)) and abs(
                ent["vx"] - vx) < 1e-6 and abs(ent["vy"] - vy) < 1e-6

        for ent in self.angle_constraints:
            if same(ent):
                ent["deg"] = float(deg)
                if isinstance(meta, dict):
                    ent["side"] = int(meta.get("side", ent.get("side", 1)))
                    ent["off"] = float(meta.get("off", ent.get("off", 0.75)))
                return

        ent = {"a": a, "b": b, "vx": vx, "vy": vy, "deg": float(deg)}
        if isinstance(meta, dict):
            ent["side"] = int(meta.get("side", 1))
            ent["off"] = float(meta.get("off", 0.75))
        else:
            ent["side"] = 1
            ent["off"] = 0.75
        self.angle_constraints.append(ent)

    def _add_or_update_distance(self, a, b, dist, Pa, Pb, label_pos):
        def same(ent):
            return (ent["a"] is a and ent["b"] is b) or (ent["a"] is b and ent["b"] is a)
        for ent in self.distance_constraints:
            if same(ent):
                ent["dist"] = dist
                ent["Pa"] = Pa
                ent["Pb"] = Pb
                ent["label"] = label_pos
                return
        self.distance_constraints.append({"a": a, "b": b, "dist": dist, "Pa": Pa, "Pb": Pb, "label": label_pos})

    # -------------------------
    # Undo / Redo
    # -------------------------
    def _snapshot_state(self):
        # Snapshot lines + constraints in a way that survives Line object recreation.
        # We store constraints by line INDEX (not object identity).
        line_data = [(ln.x1, ln.y1, ln.x2, ln.y2, ln.color) for ln in self.lines]

        idx = {ln: i for i, ln in enumerate(self.lines)}

        fixed_lengths = []
        for ln, ent in self.fixed_lengths.items():
            if ln in idx and isinstance(ent, dict):
                fixed_lengths.append({
                    "i": idx[ln],
                    "len": float(ent.get("len", ln.length())),
                    "label": ent.get("label", None),
                })

        angle_constraints = []
        for ent in self.angle_constraints:
            a = ent.get("a");
            b = ent.get("b")
            if a in idx and b in idx:
                angle_constraints.append({
                    "ia": idx[a],
                    "ib": idx[b],
                    "vx": float(ent.get("vx", 0.0)),
                    "vy": float(ent.get("vy", 0.0)),
                    "deg": float(ent.get("deg", 0.0)),
                    "side": int(ent.get("side", 1)),
                    "off": float(ent.get("off", 0.75)),
                })

        distance_constraints = []
        for ent in self.distance_constraints:
            a = ent.get("a");
            b = ent.get("b")
            if a in idx and b in idx:
                distance_constraints.append({
                    "ia": idx[a],
                    "ib": idx[b],
                    "dist": float(ent.get("dist", 0.0)),
                    "Pa": ent.get("Pa", None),
                    "Pb": ent.get("Pb", None),
                    "label": ent.get("label", None),
                })

        return {
            "lines": line_data,
            "fixed_lengths": fixed_lengths,
            "angle_constraints": angle_constraints,
            "distance_constraints": distance_constraints,
        }

    def _restore_state(self, snap):
        # Backward compatibility: if old snapshots exist (list of tuples), treat as lines-only.
        if isinstance(snap, list):
            snap = {"lines": snap, "fixed_lengths": [], "angle_constraints": [], "distance_constraints": []}

        line_data = snap.get("lines", [])
        self.lines = [Line(x1, y1, x2, y2, color) for (x1, y1, x2, y2, color) in line_data]

        # Rebuild constraints using the new Line objects by index.
        self.fixed_lengths = {}
        for ent in snap.get("fixed_lengths", []):
            i = ent.get("i", None)
            if isinstance(i, int) and 0 <= i < len(self.lines):
                ln = self.lines[i]
                self.fixed_lengths[ln] = {
                    "len": float(ent.get("len", ln.length())),
                    "label": ent.get("label", None),
                }

        self.angle_constraints = []
        for ent in snap.get("angle_constraints", []):
            ia = ent.get("ia", None)
            ib = ent.get("ib", None)
            if isinstance(ia, int) and isinstance(ib, int) and 0 <= ia < len(self.lines) and 0 <= ib < len(self.lines):
                self.angle_constraints.append({
                    "a": self.lines[ia],
                    "b": self.lines[ib],
                    "vx": float(ent.get("vx", 0.0)),
                    "vy": float(ent.get("vy", 0.0)),
                    "deg": float(ent.get("deg", 0.0)),
                    "side": int(ent.get("side", 1)),
                    "off": float(ent.get("off", 0.75)),
                })

        self.distance_constraints = []
        for ent in snap.get("distance_constraints", []):
            ia = ent.get("ia", None)
            ib = ent.get("ib", None)
            if isinstance(ia, int) and isinstance(ib, int) and 0 <= ia < len(self.lines) and 0 <= ib < len(self.lines):
                self.distance_constraints.append({
                    "a": self.lines[ia],
                    "b": self.lines[ib],
                    "dist": float(ent.get("dist", 0.0)),
                    "Pa": ent.get("Pa", None),
                    "Pb": ent.get("Pb", None),
                    "label": ent.get("label", None),
                })

        # Clear UI/drag transient state (same as before)
        self.selected_line = None
        self.hovered_line = None
        self.multi_selected.clear()
        self.dragging_line = None
        self.dragging_point = None
        self._group_drag_active = False
        self._group_drag_snapshot = []
        self._vertex_drag_active = False
        self._vertex_drag_refs = []
        self._vertex_hover = None
        self._vertex_temp = False
        self._pan_active = False
        self._box_active = False
        self.snap_hint = None

        # If DimensionTool is mid-state, cancel it (prevents stale refs after undo/redo)
        try:
            if hasattr(self, "dim_tool") and self.dim_tool is not None:
                self.dim_tool.cancel()
        except Exception:
            pass

        self._request_tree_update()
        self._request_redraw()

    def _push_undo(self):
        if not hasattr(self, "_undo_stack"):
            self._undo_stack = []
            self._redo_stack = []
        self._undo_stack.append(self._snapshot_state())
        if len(self._undo_stack) > 200:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _push_redo(self):
        if not hasattr(self, "_redo_stack"):
            self._undo_stack = []
            self._redo_stack = []
        self._redo_stack.append(self._snapshot_state())
        if len(self._redo_stack) > 200:
            self._redo_stack.pop(0)

    def on_undo(self, e=None):
        if not self._undo_stack:
            return "break"
        self._redo_stack.append(self._snapshot_state())
        snap = self._undo_stack.pop()
        self._restore_state(snap)
        return "break"

    def on_redo(self, e=None):
        if not self._redo_stack:
            return "break"
        self._undo_stack.append(self._snapshot_state())
        snap = self._redo_stack.pop()
        self._restore_state(snap)
        return "break"

    def on_copy(self, e=None):
        """Handle Ctrl+C copy."""
        if self.copy_paste.copy_selection():
            print("Copied selection to clipboard")
        return "break"

    def on_paste(self, e=None):
        """Handle Ctrl+V paste."""
        if self.copy_paste.paste():
            print("Paste mode active - click to place or drag to reposition")
        return "break"

    def _apply_length_constraint(self, ln, new_len):
        ox1, oy1, ox2, oy2 = ln.x1, ln.y1, ln.x2, ln.y2

        dx = ln.x2 - ln.x1
        dy = ln.y2 - ln.y1
        L = math.hypot(dx, dy)
        if L < 1e-9:
            return

        ux, uy = dx / L, dy / L
        mx, my = (ln.x1 + ln.x2) / 2, (ln.y1 + ln.y2) / 2
        half = new_len / 2.0

        nx1 = mx - ux * half
        ny1 = my - uy * half
        nx2 = mx + ux * half
        ny2 = my + uy * half

        ln.x1, ln.y1, ln.x2, ln.y2 = nx1, ny1, nx2, ny2

        # NEW: propagate welded endpoints so connected shapes (triangle/rectangle) do not break
        self._weld_propagate_vertex_move(ox1, oy1, nx1, ny1, ignore_line=ln)
        self._weld_propagate_vertex_move(ox2, oy2, nx2, ny2, ignore_line=ln)

    def _apply_angle_constraint(self, lnA, lnB, vx, vy, target_deg):
        # Rotate lnB about shared vertex to make angle(A,B) = target_deg, preserving lnB length.

        def out_vec(ln):
            if math.hypot(ln.x1 - vx, ln.y1 - vy) < 1e-6:
                return (ln.x2 - vx, ln.y2 - vy), "end"
            return (ln.x1 - vx, ln.y1 - vy), "start"

        (ax, ay), _ = out_vec(lnA)
        (bx, by), whichB = out_vec(lnB)

        la = math.hypot(ax, ay)
        lb = math.hypot(bx, by)
        if la < 1e-9 or lb < 1e-9:
            return

        ax, ay = ax / la, ay / la
        bx, by = bx / lb, by / lb

        angA = math.atan2(ay, ax)
        angB = math.atan2(by, bx)
        cur = (angB - angA + math.pi) % (2 * math.pi) - math.pi

        t = math.radians(target_deg)
        cand1 = (t - cur + math.pi) % (2 * math.pi) - math.pi
        cand2 = (-t - cur + math.pi) % (2 * math.pi) - math.pi
        rot = cand1 if abs(cand1) <= abs(cand2) else cand2

        c = math.cos(rot)
        s = math.sin(rot)
        nbx = bx * c - by * s
        nby = bx * s + by * c

        # capture old endpoints so we can weld-propagate after
        ox1, oy1, ox2, oy2 = lnB.x1, lnB.y1, lnB.x2, lnB.y2

        if whichB == "end":
            # lnB.x1,y1 is the vertex end
            nvx0, nvy0 = vx, vy
            nfx, nfy = vx + nbx * lb, vy + nby * lb  # far end

            lnB.x1, lnB.y1 = nvx0, nvy0
            lnB.x2, lnB.y2 = nfx, nfy

            # propagate BOTH: vertex end + far end
            self._weld_propagate_vertex_move(ox1, oy1, nvx0, nvy0, ignore_line=lnB)
            self._weld_propagate_vertex_move(ox2, oy2, nfx, nfy, ignore_line=lnB)
        else:
            # lnB.x2,y2 is the vertex end
            nvx0, nvy0 = vx, vy
            nfx, nfy = vx + nbx * lb, vy + nby * lb  # far end

            lnB.x2, lnB.y2 = nvx0, nvy0
            lnB.x1, lnB.y1 = nfx, nfy

            self._weld_propagate_vertex_move(ox2, oy2, nvx0, nvy0, ignore_line=lnB)
            self._weld_propagate_vertex_move(ox1, oy1, nfx, nfy, ignore_line=lnB)

    def _apply_distance_constraint(self, lnA, lnB, target_dist):
        # Move lnB rigidly along the shortest-segment normal so distance(A,B)=target_dist.
        from dimension_tool import _closest_points_between_segments

        ox1, oy1, ox2, oy2 = lnB.x1, lnB.y1, lnB.x2, lnB.y2

        d0, px, py, qx, qy = _closest_points_between_segments(
            (lnA.x1, lnA.y1), (lnA.x2, lnA.y2),
            (lnB.x1, lnB.y1), (lnB.x2, lnB.y2)
        )

        vx, vy = (qx - px), (qy - py)
        vL = math.hypot(vx, vy)
        if vL < 1e-9:
            dx = lnB.x2 - lnB.x1
            dy = lnB.y2 - lnB.y1
            L = math.hypot(dx, dy)
            if L < 1e-9:
                return (px, py), (qx, qy)
            nx, ny = -dy / L, dx / L
        else:
            nx, ny = vx / vL, vy / vL

        delta = target_dist - d0
        lnB.x1 += nx * delta
        lnB.y1 += ny * delta
        lnB.x2 += nx * delta
        lnB.y2 += ny * delta

        # NEW: propagate welded endpoints so connected shapes do not break
        self._weld_propagate_vertex_move(ox1, oy1, lnB.x1, lnB.y1, ignore_line=lnB)
        self._weld_propagate_vertex_move(ox2, oy2, lnB.x2, lnB.y2, ignore_line=lnB)

        d1, px, py, qx, qy = _closest_points_between_segments(
            (lnA.x1, lnA.y1), (lnA.x2, lnA.y2),
            (lnB.x1, lnB.y1), (lnB.x2, lnB.y2)
        )
        return (px, py), (qx, qy)

    def _weld_propagate_vertex_move(self, oldx, oldy, newx, newy, ignore_line=None, tol=1e-6):
        if math.hypot(newx - oldx, newy - oldy) < tol:
            return

        # If an angle constraint was anchored at this vertex, move the anchor too
        for ent in self.angle_constraints:
            if math.hypot(ent["vx"] - oldx, ent["vy"] - oldy) < tol:
                ent["vx"] = newx
                ent["vy"] = newy

        for ln in self.lines:
            if ignore_line is not None and ln is ignore_line:
                continue

            if math.hypot(ln.x1 - oldx, ln.y1 - oldy) < tol:
                ln.x1 = newx
                ln.y1 = newy

            if math.hypot(ln.x2 - oldx, ln.y2 - oldy) < tol:
                ln.x2 = newx
                ln.y2 = newy

    def _is_protected_vertex(self, vx, vy, tol=1e-6):
        # A vertex is "protected" if an angle constraint is defined at that vertex.
        for ent in self.angle_constraints:
            if math.hypot(ent["vx"] - vx, ent["vy"] - vy) < tol:
                return True
        return False

    def _solve_constraints(self, iterations=6):
        """
        Iterative constraint relaxation with improved convergence.

        Angle constraints now dynamically track shared vertices
        during solving, preventing "snap back" behavior.
        """
        for iter_num in range(max(1, int(iterations))):
            # Fixed lengths
            for ln, meta in list(self.fixed_lengths.items()):
                try:
                    self._apply_length_constraint(ln, float(meta["len"]))
                except Exception:
                    pass

            # Angles (with dynamic vertex tracking)
            for ent in list(self.angle_constraints):
                try:
                    lnA = ent["a"]
                    lnB = ent["b"]
                    vx0, vy0 = float(ent["vx"]), float(ent["vy"])

                    # Find currently shared (or nearly-shared) endpoint between lnA and lnB
                    a_pts = [(lnA.x1, lnA.y1, "a1"), (lnA.x2, lnA.y2, "a2")]
                    b_pts = [(lnB.x1, lnB.y1, "b1"), (lnB.x2, lnB.y2, "b2")]

                    best = None
                    best_d = 1e18
                    for ax, ay, atag in a_pts:
                        for bx, by, btag in b_pts:
                            d = math.hypot(ax - bx, ay - by)
                            if d < best_d:
                                best_d = d
                                best = (ax, ay, atag, bx, by, btag)

                    # If endpoints are welded, use that as the constraint vertex
                    if best and best_d <= max(1e-6, self.snap_dist_endpoint * 1.5):
                        ax, ay, atag, bx, by, btag = best
                        vx = 0.5 * (ax + bx)
                        vy = 0.5 * (ay + by)

                        # Weld the endpoints together
                        if atag == "a1":
                            lnA.x1, lnA.y1 = vx, vy
                        else:
                            lnA.x2, lnA.y2 = vx, vy
                        if btag == "b1":
                            lnB.x1, lnB.y1 = vx, vy
                        else:
                            lnB.x2, lnB.y2 = vx, vy

                        # Update stored vertex position
                        ent["vx"], ent["vy"] = vx, vy
                    else:
                        # Fallback: use stored vertex
                        vx, vy = vx0, vy0
                        # Snap any endpoints that are close to stored vertex
                        if math.hypot(lnA.x1 - vx, lnA.y1 - vy) < 1e-6:
                            lnA.x1, lnA.y1 = vx, vy
                        if math.hypot(lnA.x2 - vx, lnA.y2 - vy) < 1e-6:
                            lnA.x2, lnA.y2 = vx, vy
                        if math.hypot(lnB.x1 - vx, lnB.y1 - vy) < 1e-6:
                            lnB.x1, lnB.y1 = vx, vy
                        if math.hypot(lnB.x2 - vx, lnB.y2 - vy) < 1e-6:
                            lnB.x2, lnB.y2 = vx, vy

                    # Determine which line to rotate (prefer non-dragged line)
                    rotate_ln = lnB
                    keep_ln = lnA
                    try:
                        active = getattr(self, "_solver_drag_lines", set())
                        if (lnB in active) and (lnA not in active):
                            rotate_ln = lnA
                            keep_ln = lnB
                    except Exception:
                        pass

                    self._apply_angle_constraint(keep_ln, rotate_ln, vx, vy, float(ent["deg"]))
                except Exception:
                    pass

            # Distances
            for ent in list(self.distance_constraints):
                try:
                    lnA = ent["a"]
                    lnB = ent["b"]
                    target = float(ent["dist"])
                    P, Q = self._apply_distance_constraint(lnA, lnB, target)
                    ent["P"] = P
                    ent["Q"] = Q
                except Exception:
                    pass

    def draw_alignment_guides(self):
        """Draw dotted alignment + Line Match guides (axis guide drawn correctly to the snapped endpoint)."""
        # Standard alignment guides
        for guide in self.alignment_guides:
            x1, y1, x2, y2, guide_type = guide
            sx1, sy1 = self.vp.world_to_screen(x1, y1)
            sx2, sy2 = self.vp.world_to_screen(x2, y2)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#B0B0B0", width=1, dash=(4, 3))

        if not self.line_match_var.get():
            return

        # --------
        # Slope axis guide (FIXED):
        # Draw from the closest point on the reference segment to the snapped endpoint (on the axis).
        # This works even if only the endpoint is aligned (start point off-axis).
        # --------
        for guide in self.parallel_guides:
            x_start, y_start, x_end, y_end, ref_line = guide

            dx = ref_line.x2 - ref_line.x1
            dy = ref_line.y2 - ref_line.y1
            L = math.hypot(dx, dy)
            if L < 1e-9:
                continue

            ux = dx / L
            uy = dy / L
            ox, oy = ref_line.x1, ref_line.y1

            def s_of(px, py):
                return (px - ox) * ux + (py - oy) * uy

            # Reference segment interval
            sA = s_of(ref_line.x1, ref_line.y1)
            sB = s_of(ref_line.x2, ref_line.y2)
            r0, r1 = (sA, sB) if sA <= sB else (sB, sA)

            # ONLY use the snapped endpoint of the new line (this is on the axis)
            sE = s_of(x_end, y_end)

            # Closest point on ref segment to that endpoint (clamp)
            sC = min(r1, max(r0, sE))

            # If the endpoint is actually within the segment, line would be tiny / pointless
            if abs(sE - sC) < 1e-9:
                continue

            gx1 = ox + sC * ux
            gy1 = oy + sC * uy
            gx2 = ox + sE * ux
            gy2 = oy + sE * uy

            sx1, sy1 = self.vp.world_to_screen(gx1, gy1)
            sx2, sy2 = self.vp.world_to_screen(gx2, gy2)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#FFD700", width=1, dash=(4, 3))

        # --------
        # Equal length indicators (unchanged)
        # --------
        for guide in self.equal_length_guides:
            x1, y1, x2, y2, ref_line = guide

            sx1, sy1 = self.vp.world_to_screen(x1, y1)
            sx2, sy2 = self.vp.world_to_screen(x2, y2)

            rx1, ry1 = self.vp.world_to_screen(ref_line.x1, ref_line.y1)
            rx2, ry2 = self.vp.world_to_screen(ref_line.x2, ref_line.y2)

            dx = x2 - x1
            dy = y2 - y1
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue

            px = -dy / length
            py = dx / length
            offset = 0.4

            wx1_start = x1 + px * offset
            wy1_start = y1 + py * offset
            wx1_end = x2 + px * offset
            wy1_end = y2 + py * offset

            wx2_start = ref_line.x1 + px * offset
            wy2_start = ref_line.y1 + py * offset
            wx2_end = ref_line.x2 + px * offset
            wy2_end = ref_line.y2 + py * offset

            sw1_x1, sw1_y1 = self.vp.world_to_screen(wx1_start, wy1_start)
            sw1_x2, sw1_y2 = self.vp.world_to_screen(wx1_end, wy1_end)
            sw2_x1, sw2_y1 = self.vp.world_to_screen(wx2_start, wy2_start)
            sw2_x2, sw2_y2 = self.vp.world_to_screen(wx2_end, wy2_end)

            self.canvas.create_line(sx1, sy1, sw1_x1, sw1_y1, fill="#B0B0B0", width=1, dash=(4, 3))
            self.canvas.create_line(sx2, sy2, sw1_x2, sw1_y2, fill="#B0B0B0", width=1, dash=(4, 3))
            self.canvas.create_line(rx1, ry1, sw2_x1, sw2_y1, fill="#B0B0B0", width=1, dash=(4, 3))
            self.canvas.create_line(rx2, ry2, sw2_x2, sw2_y2, fill="#B0B0B0", width=1, dash=(4, 3))

            self.canvas.create_line(sw1_x1, sw1_y1, sw1_x2, sw1_y2, fill="white", width=2)
            self.canvas.create_line(sw2_x1, sw2_y1, sw2_x2, sw2_y2, fill="white", width=2)

    # Line Match (parallel/equal-length) (delegates)
    def _apply_line_match_snap(self, x0, y0, wx, wy, ignore_line=None):
        return self.snap._apply_line_match_snap(x0, y0, wx, wy, ignore_line=ignore_line)

    # Back-compat wrapper used by existing code paths (if any)
    def _apply_parallel_and_equal_length_snap(self, x0, y0, wx, wy):
        """Line Match snapping for line drawing mode (wrapper for compatibility)."""
        return self.snap._apply_line_match_snap(x0, y0, wx, wy, ignore_line=None)

    def on_double_click(self, e):
        """Handle double-click for editing dimensions."""
        if self.tool_mode in ("cursor", "dim"):
            if self.dimension_tool.pre_handle_double_click(e):
                return

    def on_delete_key(self, e=None):
        # First try to delete a highlighted dimension
        if self.tool_mode in ("cursor", "dim"):
            if self.dimension_tool.delete_selected_dimension():
                return

        # Then try to delete from tree selection
        if self._delete_selected_dimension_from_tree():
            return

        # Then handle line deletion
        if self.tool_mode == "vertex":
            return
        if self.multi_selected:
            self._push_undo()
            dead = set(self.multi_selected)
            # purge constraints that touch any deleted line
            self.angle_constraints = [c for c in self.angle_constraints if c["a"] not in dead and c["b"] not in dead]
            self.distance_constraints = [c for c in self.distance_constraints if
                                         c["a"] not in dead and c["b"] not in dead]
            for ln in list(dead):
                self.fixed_lengths.pop(ln, None)
            self.lines = [ln for ln in self.lines if ln not in dead]
            self.multi_selected.clear()
            self.selected_line = None
            self._prune_zero_lines()
            self._request_tree_update()
            self._request_redraw()
            return
        self._delete_selected_line()

    def on_right_click_menu(self, e):
        """Handle right-click to open context menu (NEW)."""
        # If dropdown is already open, close it
        if self.dropdown.active:
            self.dropdown.close_menu()
        else:
            self.dropdown.open_menu(e.x, e.y)

    def apply_length_dimension(self, ln, target_len):
        return self.dimension_rules.apply_length_dimension(ln, target_len)

    def apply_distance_dimension(self, a, b, target_dist):
        return self.dimension_rules.apply_distance_dimension(a, b, target_dist)

    def apply_angle_dimension(self, lnA, lnB, vx, vy, target_deg):
        return self.dimension_rules.apply_angle_dimension(lnA, lnB, vx, vy, target_deg)

    def activate_rotate(self):
        """Activate rotation mode."""
        self.rotate.activate()

    def activate_trim(self):
        """Activate trim mode."""
        self.trim.activate()







    def on_canvas_leave(self, e=None):
        # Cursor is no longer in the drawing plane
        self.cursor_world_valid = False
        self.snap_hint = None

        # Clear ALL tracing visuals (Snap Axis + Line Match)
        self.alignment_guides = []
        self.parallel_guides = []
        self.equal_length_guides = []

        self._request_redraw()

if __name__ == "__main__":
    root = tk.Tk()
    app = FloorPlanCAD(root)
    root.mainloop()

#123aaaadd1122bbccdd1/1