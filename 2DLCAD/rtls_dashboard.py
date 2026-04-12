"""
rtls_dashboard.py – RTLS Ship Floor Plan Dashboard
===================================================
Main application window for the UWB RTLS position tracking dashboard.

Features (Phase 1 – this file):
  • Load floor plan image (PNG / JPG / BMP / TIFF / PDF)
  • Pan & zoom the map
  • Toolbar with mode controls
  • Status bar with image info and cursor coordinates

Future phases will add:
  • Calibration (coord_transform.py)
  • Anchor / tag overlays (overlay_items.py)
  • Serial RTLS client (rtls_client.py)
"""

from __future__ import annotations
import sys
import os
import tempfile
import time

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QLabel, QWidget,
    QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy,
    QSplitter, QListWidget, QListWidgetItem, QInputDialog,
    QToolButton, QButtonGroup, QStackedWidget, QFrame, QMenu,
    QComboBox, QSlider
)
from PyQt6.QtGui import QAction, QIcon, QFont, QColor, QPalette, QPixmap
from PyQt6.QtCore import Qt, QPointF, QEvent, QTimer, pyqtSignal

from map_canvas import MapCanvas, MapMode
from room_data import Room, Anchor, segments_match
from utils.font_utils import get_default_font_family
from room_profiles import (
    load_floorplan_manifest,
    load_project_package,
    manifest_path_for_svg,
    PROJECT_EXTENSION,
    save_floorplan_manifest,
    save_project_package,
)
from workspace_switcher import WorkspaceSwitcher


# ──────────────────────────────────────────────────────────────────────────────
# Style
# ──────────────────────────────────────────────────────────────────────────────
UI_FONT_FAMILY = get_default_font_family()

DARK_STYLESHEET = (
f"""
QMainWindow, QWidget {{
    background-color: #12121f;
    color: #e0e0f0;
    font-family: "{UI_FONT_FAMILY}";
    font-size: 13px;
}}
"""
"""
QToolBar {
    background-color: #1a1a2e;
    border-bottom: 1px solid #2d2d5e;
    spacing: 6px;
    padding: 4px 8px;
}
QToolBar QToolButton {
    background: transparent;
    color: #c0c0e0;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 10px;
    min-width: 80px;
}
QToolBar QToolButton:hover {
    background-color: #2d2d5e;
    border-color: #5555aa;
}
QToolBar QToolButton:checked {
    background-color: #3a3a7a;
    border-color: #7777dd;
    color: #ffffff;
}
QToolButton#zoom_label_button {
    color: #cfd6ff;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 8px 12px;
    min-width: 0px;
    font-size: 12px;
    font-weight: 700;
}
QToolButton#zoom_label_button:hover {
    background-color: #2d2d5e;
    border-color: #5555aa;
}
QToolButton#zoom_label_button:pressed {
    background-color: #242447;
    border-color: #6d8cff;
}
QToolButton#zoom_step_button {
    color: #f4f5ff;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 0px;
    min-width: 30px;
    min-height: 18px;
    font-size: 12px;
    font-weight: 700;
}
QToolButton#zoom_step_button:hover {
    background-color: #2d2d5e;
    border-color: #5555aa;
}
QToolButton#zoom_step_button:pressed {
    background-color: #242447;
    border-color: #6d8cff;
}
QToolBar::separator {
    background: #2d2d5e;
    width: 1px;
    margin: 4px 6px;
}
QStatusBar {
    background-color: #1a1a2e;
    color: #8888bb;
    border-top: 1px solid #2d2d5e;
    font-size: 11px;
}
QLabel#title_label {
    color: #aaaaff;
    font-size: 15px;
    font-weight: bold;
    padding: 0 12px;
}
"""
)

FEATURE_PANEL_STYLE = """
QWidget#feature_panel {
    background-color: #1a1a2e;
    border-left: 1px solid #2d2d5e;
}
QLabel#feature_header {
    font-size: 14px;
    font-weight: bold;
    color: #c0c0e0;
    padding: 5px;
}
QListWidget {
    background-color: #12121f;
    border: 1px solid #2d2d5e;
    border-radius: 4px;
    color: #e0e0f0;
    outline: none;
}
QListWidget::item {
    padding: 8px;
    border-bottom: 1px solid #1a1a2e;
}
QListWidget::item:selected {
    background-color: #3a3a7a;
    color: #ffffff;
}
QPushButton {
    background-color: #2d2d5e;
    color: #e0e0f0;
    border: none;
    border-radius: 4px;
    padding: 6px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3a3a7a;
}
QPushButton:pressed {
    background-color: #5555aa;
}
QSplitter::handle {
    background-color: #3a3a7a;
    width: 4px;
    border-left: 1px solid #1a1a2e;
    border-right: 1px solid #1a1a2e;
}
"""

NOTICE_BANNER_STYLE = """
QLabel#notice_banner {
    background-color: #4a3114;
    color: #ffe7b3;
    border-bottom: 1px solid #8a5b1a;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 600;
}
"""

ANCHOR_HEADER_STYLE = """
QWidget#anchor_header {
    background-color: #171726;
    border-bottom: 1px solid #2d2d5e;
}
QFrame#primary_bar {
    background-color: #12121f;
    border-bottom: 1px solid #242447;
}
QFrame#context_bar {
    background-color: #1a1a2e;
}
QLabel#anchor_header_title {
    color: #f4f5ff;
    font-size: 16px;
    font-weight: bold;
}
QLabel#anchor_header_subtitle {
    color: #8f93c7;
    font-size: 10px;
}
QToolButton#category_button {
    color: #d8dbff;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 600;
}
QToolButton#zoom_label_button {
    color: #d8dbff;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 8px 12px;
    font-size: 12px;
    font-weight: 700;
}
QToolButton#zoom_label_button:hover {
    background-color: #23234a;
    border-color: #3c3c78;
}
QToolButton#zoom_step_button {
    color: #f4f5ff;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 0px;
    min-width: 30px;
    min-height: 18px;
    font-size: 12px;
    font-weight: 700;
}
QToolButton#zoom_step_button:hover {
    background-color: #23234a;
    border-color: #6d8cff;
}
QToolButton#zoom_step_button:pressed {
    background-color: #1c1c34;
    border-color: #6d8cff;
}
QFrame#toolbar_divider {
    background-color: #2d2d5e;
    min-width: 1px;
    max-width: 1px;
}
QToolButton#category_button:hover {
    background-color: #23234a;
    border-color: #3c3c78;
}
QToolButton#category_button:checked {
    background-color: #3556d8;
    border-color: #6d8cff;
    color: #ffffff;
}
QFrame#context_group {
    background-color: #20203a;
    border: 1px solid #30305c;
    border-radius: 8px;
}
QLabel#context_group_title {
    color: #aeb6ff;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1px;
}
QToolButton#context_action {
    background-color: #2b2b4a;
    color: #f4f5ff;
    border: 1px solid #3a3a66;
    border-radius: 7px;
    padding: 4px 10px;
    min-width: 80px;
    min-height: 30px;
    font-size: 11px;
    font-weight: 600;
}
QToolButton#context_action:checked {
    background-color: #3556d8;
    border-color: #6d8cff;
    color: #ffffff;
}
QToolButton#context_action:hover {
    background-color: #3a3a66;
    border-color: #6d8cff;
}
QToolButton#context_action:pressed {
    background-color: #23234a;
}
QToolButton#home_button {
    background-color: #2b2b4a;
    color: white;
    border: 1px solid #3a3a66;
    border-radius: 8px;
    padding: 8px 12px;
    font-weight: bold;
}
QToolButton#home_button:hover {
    background-color: #3a3a66;
    border-color: #6d8cff;
}
"""


class ContextActionButton(QToolButton):
    def __init__(self, label: str, callback=None, tooltip: str = "", parent=None, checkable: bool = False):
        super().__init__(parent)
        self.setObjectName("context_action")
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.setText(label)
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        if callback is not None:
            self.clicked.connect(callback)


class ZoomCluster(QWidget):
    def __init__(self, parent=None, label: str = "Zoom"):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.label_btn = QToolButton()
        self.label_btn.setObjectName("zoom_label_button")
        self.label_btn.setText(label)
        self.label_btn.setCursor(Qt.CursorShape.ArrowCursor)
        layout.addWidget(self.label_btn)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(3)
        self.plus_btn = QToolButton()
        self.plus_btn.setObjectName("zoom_step_button")
        self.plus_btn.setText("+")
        self.minus_btn = QToolButton()
        self.minus_btn.setObjectName("zoom_step_button")
        self.minus_btn.setText("-")
        col.addWidget(self.plus_btn)
        col.addWidget(self.minus_btn)
        layout.addLayout(col)


class ContextGroup(QFrame):
    def __init__(self, title: str, actions: list[QToolButton], parent=None):
        super().__init__(parent)
        self.setObjectName("context_group")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("context_group_title")
        layout.addWidget(title_lbl)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(6)
        for action in actions:
            actions_row.addWidget(action)
        layout.addLayout(actions_row)


class AnchorMapperHeader(QWidget):
    category_changed = pyqtSignal(str)
    home_clicked = pyqtSignal()

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setObjectName("anchor_header")
        self.setStyleSheet(ANCHOR_HEADER_STYLE)
        self._category_buttons = {}
        self._category_indices = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        primary = QFrame()
        primary.setObjectName("primary_bar")
        primary_layout = QHBoxLayout(primary)
        primary_layout.setContentsMargins(16, 10, 16, 10)
        primary_layout.setSpacing(10)

        home_btn = QToolButton()
        home_btn.setObjectName("home_button")
        home_btn.setText("🏠 Home")
        home_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        home_btn.clicked.connect(self.home_clicked.emit)
        primary_layout.addWidget(home_btn)

        title_wrap = QVBoxLayout()
        title_wrap.setContentsMargins(0, 0, 0, 0)
        title_wrap.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("anchor_header_title")
        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setObjectName("anchor_header_subtitle")
        title_wrap.addWidget(title_lbl)
        title_wrap.addWidget(subtitle_lbl)
        primary_layout.addLayout(title_wrap)
        primary_layout.addSpacing(18)

        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(True)
        for name in ("File", "Tools"):
            btn = QToolButton()
            btn.setObjectName("category_button")
            btn.setCheckable(True)
            btn.setText(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self.set_category(n))
            self.category_group.addButton(btn)
            self._category_buttons[name] = btn
            primary_layout.addWidget(btn)

        divider = QFrame()
        divider.setObjectName("toolbar_divider")
        primary_layout.addWidget(divider)

        self.fit_btn = QToolButton()
        self.fit_btn.setObjectName("category_button")
        self.fit_btn.setText("⊡ Fit View")
        self.fit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        primary_layout.addWidget(self.fit_btn)

        self.zoom_cluster = ZoomCluster()
        primary_layout.addWidget(self.zoom_cluster)

        primary_layout.addStretch()
        outer.addWidget(primary)

        context = QFrame()
        context.setObjectName("context_bar")
        context_layout = QVBoxLayout(context)
        context_layout.setContentsMargins(16, 4, 16, 4)
        context_layout.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        context_layout.addWidget(self.stack)
        outer.addWidget(context)

    def add_category_page(self, name: str, page: QWidget):
        self._category_indices[name] = self.stack.addWidget(page)

    def set_category(self, name: str):
        if name not in self._category_indices:
            return
        self._category_buttons[name].setChecked(True)
        self.stack.setCurrentIndex(self._category_indices[name])
        self._sync_context_height()
        self.category_changed.emit(name)

    def _sync_context_height(self):
        page = self.stack.currentWidget()
        if page is None:
            return
        target = page.sizeHint().height()
        self.stack.setFixedHeight(target)


# ──────────────────────────────────────────────────────────────────────────────
# RTLSDashboard
# ──────────────────────────────────────────────────────────────────────────────
class RTLSDashboard(QMainWindow):
    # Emitted when the user clicks the Home button (used when embedded in main_qt)
    go_home = pyqtSignal()
    workspace_requested = pyqtSignal(str)

    MODE_ANCHOR_MAPPER = "anchor_mapper"
    MODE_RTLS = "rtls"

    def __init__(self, app_mode: str = MODE_ANCHOR_MAPPER):
        super().__init__()
        self.app_mode = app_mode
        title = "Anchor Mapper – Ship Floor Plan Tracker"
        if self.app_mode == self.MODE_RTLS:
            title = "RTLS Dashboard – Ship Floor Plan Tracker"
        self.setWindowTitle(title)
        self.resize(1400, 900)
        self.setStyleSheet(DARK_STYLESHEET)

        # ── State ─────────────────────────────────────────────────────────
        self._rooms: list[Room] = []
        self._loaded_vector_path: str | None = None
        self._loaded_project_path: str | None = None
        self._project_tempdir: tempfile.TemporaryDirectory | None = None
        self._global_serial_thread = None
        self._live_tags_world: dict[str, tuple[float, float]] = {}
        self._active_tags_world: dict[str, tuple[float, float]] = {}
        self._using_mock_rtls = False
        self._mock_room: Room | None = None
        self._rtls_history: list[tuple[float, dict[str, tuple[float, float]]]] = []
        self._history_max_frames = 1200
        self._history_follow_live = True
        self._history_playing = False
        self._history_index = -1
        self._history_slider_dragging = False
        self._history_step = 1

        # ── Central Layout ────────────────────────────────────────────────
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.setCentralWidget(central)

        self._notice_banner = QLabel("", self)
        self._notice_banner.setObjectName("notice_banner")
        self._notice_banner.setStyleSheet(NOTICE_BANNER_STYLE)
        self._notice_banner.hide()
        central_layout.addWidget(self._notice_banner)

        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._notice_banner.hide)

        self._history_capture_timer = QTimer(self)
        self._history_capture_timer.setInterval(250)
        self._history_capture_timer.timeout.connect(self._capture_rtls_history_frame)
        self._history_capture_timer.start()

        self._history_play_timer = QTimer(self)
        self._history_play_timer.setInterval(180)
        self._history_play_timer.timeout.connect(self._advance_history_playback)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        central_layout.addWidget(self.splitter, 1)

        # ── Map canvas (left panel) ───────────────────────────────────────
        self._canvas = MapCanvas(self.splitter)
        self._canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._canvas.room_lookup = lambda: self._rooms
        self._canvas.history_lookup = self._current_heatmap_frames
        self._canvas.no_image_warning.connect(self._on_no_image)
        self._canvas.room_designated.connect(self._on_room_designated)
        self._canvas.mode_change_requested.connect(self._set_mode)
        self._canvas.status_message_requested.connect(self._show_status)
        self._canvas.status_message_requested.connect(self._show_notice)
        self.splitter.addWidget(self._canvas)

        # ── Feature Manager (right panel) ─────────────────────────────────
        self._feature_panel = self._build_feature_panel()
        self.splitter.addWidget(self._feature_panel)

        # Give the feature panel a minimum size, but make default smaller
        self.splitter.setSizes([1100, 300])
        self._feature_panel.setMinimumWidth(200)

        # ── Top Controls ──────────────────────────────────────────────────
        if self.app_mode == self.MODE_ANCHOR_MAPPER:
            self._build_anchor_mapper_header()
        else:
            self._build_toolbar()

        # ── Status bar ────────────────────────────────────────────────────
        self._build_statusbar()

        # ── Track mouse position on canvas ────────────────────────────────
        self._canvas.setMouseTracking(True)
        self._canvas.installEventFilter(self)

        # ── Welcome hint ─────────────────────────────────────────────────
        if self.app_mode == self.MODE_RTLS:
            self._show_status("Load an RTLS project to restore rooms, anchors, and live tracking settings")
        else:
            self._show_status("Load an SVG floor plan to define rooms, place anchors, and save room data")

        current_key = "anchor_mapper" if self.app_mode == self.MODE_ANCHOR_MAPPER else "rtls_dashboard"
        self._workspace_switcher = WorkspaceSwitcher(
            central,
            [
                ("cad", "Launch 2DLCAD"),
                ("anchor_mapper", "Anchor Mapper"),
                ("tag_profiler", "Tag Profiler"),
                ("rtls_dashboard", "RTLS Dashboard"),
            ],
            current_key=current_key,
            top_offset=0,
        )
        self._workspace_switcher.workspace_requested.connect(self.workspace_requested.emit)

    # ──────────────────────────────────────────────────────────────────────────
    # Toolbar
    # ──────────────────────────────────────────────────────────────────────────
    def _build_anchor_mapper_header(self):
        header = AnchorMapperHeader(
            "⚓ Anchor Mapper",
            "Organize project files, rooms, and anchors.",
            self,
        )
        header.home_clicked.connect(self.go_home.emit)
        header.category_changed.connect(self._on_anchor_category_changed)
        header.fit_btn.clicked.connect(self._canvas.fit_in_view)
        header.zoom_cluster.plus_btn.clicked.connect(lambda: self._canvas.zoom_by(1.25))
        header.zoom_cluster.minus_btn.clicked.connect(lambda: self._canvas.zoom_by(0.8))

        file_page = self._build_context_page([
            ("Import", [
                ("Load SVG", self._load_vector, "Load an SVG floor plan"),
                ("Load Room Data", self._load_room_data, "Load saved room and anchor data"),
            ]),
            ("Export", [
                ("Save Room Data", self._save_room_data, "Save room and anchor data to JSON"),
                ("Save Project", self._save_project, "Bundle SVG and room data into one project file"),
            ]),
        ])
        header.add_category_page("File", file_page)

        self._tool_buttons = {}
        tools_page = self._build_context_page([
            ("Selection", [
                ("Select", lambda: self._toggle_tool_mode(MapMode.SELECT), "Manually select boundary segments", True),
                ("Smart Select", lambda: self._toggle_tool_mode(MapMode.PICK_ROOM), "Click inside a room to auto-select its boundary", True),
            ]),
        ], track_tools=True)
        header.add_category_page("Tools", tools_page)

        header.set_category("File")
        self.setMenuWidget(header)
        self._anchor_header = header
        self._mode_actions = []
        self._canvas.set_mode(MapMode.PAN)
        self._canvas.selection_changed.connect(self._on_selection_changed)

    def _build_context_page(self, sections: list[tuple[str, list[tuple]]], track_tools: bool = False) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        for title, actions in sections:
            buttons = []
            for action in actions:
                label, callback, tooltip = action[:3]
                checkable = bool(action[3]) if len(action) > 3 else False
                btn = ContextActionButton(label, None if (track_tools and checkable) else callback, tooltip, checkable=checkable)
                buttons.append(btn)
                if track_tools and checkable:
                    self._tool_buttons[label] = btn
                    mode = MapMode.SELECT if label == "Select" else MapMode.PICK_ROOM
                    btn.clicked.connect(lambda checked, m=mode: self._on_tool_button_clicked(m, checked))
            layout.addWidget(ContextGroup(title, buttons))
        return page

    def _on_anchor_category_changed(self, name: str):
        self._show_status(f"{name} tools ready")

    def _toggle_tool_mode(self, mode: str):
        if self._canvas.mode == mode:
            self._set_mode(MapMode.PAN)
        else:
            self._set_mode(mode)

    def _on_tool_button_clicked(self, mode: str, checked: bool):
        if checked:
            self._set_mode(mode)
        else:
            self._set_mode(MapMode.PAN)

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar", self)
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # Back Home Button
        act_home = QAction("🏠  Home", self)
        act_home.setToolTip("Back to Home Screen")
        act_home.triggered.connect(self.go_home.emit)
        tb.addAction(act_home)
        tb.addSeparator()

        # Title label
        heading = "⚓ Anchor Mapper"
        if self.app_mode == self.MODE_RTLS:
            heading = "⚓ RTLS Dashboard"
        title = QLabel(heading, self)
        title.setObjectName("title_label")
        tb.addWidget(title)
        tb.addSeparator()

        # Load Image
        act_img = QAction("🖼  Load Image", self)
        act_img.setToolTip("Load a PNG / JPG / BMP floor plan image")
        act_img.triggered.connect(self._load_image)
        tb.addAction(act_img)

        if self.app_mode == self.MODE_RTLS:
            act_project = QAction("📦  Load Project", self)
            act_project.setToolTip("Load a packaged floor plan project with room data")
            act_project.triggered.connect(self._load_project)
            tb.addAction(act_project)

            act_load_room_data = QAction("🧩  Load Room Data", self)
            act_load_room_data.setToolTip("Load room/anchor data from a JSON manifest")
            act_load_room_data.triggered.connect(self._load_room_data)
            tb.addAction(act_load_room_data)
        else:
            act_vector = QAction("📄  Load SVG", self)
            act_vector.setToolTip("Load an SVG floor plan")
            act_vector.triggered.connect(self._load_vector)
            tb.addAction(act_vector)

            act_save_room_data = QAction("💾  Save Room Data", self)
            act_save_room_data.setToolTip("Save all room/anchor data to a JSON manifest")
            act_save_room_data.triggered.connect(self._save_room_data)
            tb.addAction(act_save_room_data)

            act_save_project = QAction("📦  Save Project", self)
            act_save_project.setToolTip("Save the SVG and room data into one project file")
            act_save_project.triggered.connect(self._save_project)
            tb.addAction(act_save_project)

        tb.addSeparator()

        # Fit view
        act_fit = QAction("⊡  Fit View", self)
        act_fit.setToolTip("Fit the entire floor plan in view  (F)")
        act_fit.setShortcut("F")
        act_fit.triggered.connect(self._canvas.fit_in_view)
        tb.addAction(act_fit)

        zoom_widget = ZoomCluster(label="Zoom")
        zoom_widget.plus_btn.setToolTip("Zoom In")
        zoom_widget.minus_btn.setToolTip("Zoom Out")
        zoom_widget.plus_btn.clicked.connect(lambda: self._canvas.zoom_by(1.25))
        zoom_widget.minus_btn.clicked.connect(lambda: self._canvas.zoom_by(0.8))
        tb.addWidget(zoom_widget)

        tb.addSeparator()

        # Mode: Pan
        self._act_pan = QAction("✋  Pan", self)
        self._act_pan.setCheckable(True)
        self._act_pan.setChecked(True)
        self._act_pan.triggered.connect(lambda: self._set_mode(MapMode.PAN))
        tb.addAction(self._act_pan)

        self._mode_actions = [self._act_pan]
        if self.app_mode == self.MODE_ANCHOR_MAPPER:
            # Mode: Select
            self._act_select = QAction("🖍  Select", self)
            self._act_select.setCheckable(True)
            self._act_select.setChecked(False)
            self._act_select.setToolTip("Click lines to select / deselect them  (Esc = clear)")
            self._act_select.triggered.connect(lambda: self._set_mode(MapMode.SELECT))
            tb.addAction(self._act_select)
            self._mode_actions.append(self._act_select)

            self._act_pick_room = QAction("🏠  Pick Room", self)
            self._act_pick_room.setCheckable(True)
            self._act_pick_room.setChecked(False)
            self._act_pick_room.setToolTip("Click inside a closed room to auto-select its boundary")
            self._act_pick_room.triggered.connect(lambda: self._set_mode(MapMode.PICK_ROOM))
            tb.addAction(self._act_pick_room)
            self._mode_actions.append(self._act_pick_room)
        self._canvas.set_mode(MapMode.PAN)
        self._canvas.selection_changed.connect(self._on_selection_changed)

    def _set_mode(self, mode: str):
        for act in getattr(self, "_mode_actions", []):
            act.setChecked(False)
        if hasattr(self, "_act_pan") and mode == MapMode.PAN:
            self._act_pan.setChecked(True)
        elif mode == MapMode.SELECT and hasattr(self, "_act_select"):
            self._act_select.setChecked(True)
        elif mode == MapMode.PICK_ROOM and hasattr(self, "_act_pick_room"):
            self._act_pick_room.setChecked(True)
        if hasattr(self, "_tool_buttons"):
            for label, button in self._tool_buttons.items():
                expected_mode = MapMode.SELECT if label == "Select" else MapMode.PICK_ROOM
                button.setChecked(mode == expected_mode)
        self._canvas.set_mode(mode)
        labels = {
            MapMode.PAN: "Cursor mode",
            MapMode.SELECT: "Manual selection mode",
            MapMode.PICK_ROOM: "Smart Select mode",
        }
        self._show_status(labels.get(mode, f"Mode: {mode.upper()}"))

    def _on_selection_changed(self, selected_set):
        n = len(selected_set)
        if n == 0:
            self._show_status("Selection cleared")
        else:
            self._show_status(f"{n} line{'s' if n != 1 else ''} selected  (Esc to clear)")

    # ──────────────────────────────────────────────────────────────────────────
    # Status bar
    # ──────────────────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        sb = self.statusBar()
        self._lbl_status = QLabel("Ready")
        self._lbl_coords = QLabel("x: —   y: —")
        self._lbl_coords.setMinimumWidth(160)
        self._lbl_image  = QLabel("No image loaded")

        sb.addWidget(self._lbl_status, 1)
        sb.addPermanentWidget(self._lbl_coords)
        sb.addPermanentWidget(QLabel(" | "))
        sb.addPermanentWidget(self._lbl_image)

    def _show_status(self, msg: str):
        if hasattr(self, "_lbl_status"):
            self._lbl_status.setText(msg)

    def set_current_workspace(self, key: str):
        if hasattr(self, "_workspace_switcher"):
            self._workspace_switcher.set_current_workspace(key)

    def close_workspace_switcher(self):
        if hasattr(self, "_workspace_switcher"):
            self._workspace_switcher.close_panel()

    def _show_notice(self, msg: str, timeout_ms: int = 3200):
        if not hasattr(self, "_notice_banner"):
            return
        self._notice_banner.setText(msg)
        self._notice_banner.show()
        self._notice_timer.start(timeout_ms)

    def _clear_rooms(self):
        self._rooms = []
        self._room_list.clear()
        self._stop_global_rtls()
        self._clear_rtls_history()
        self._canvas.highlighted_room = None
        self._canvas.update()

    def _reset_project_extract_dir(self):
        if self._project_tempdir is not None:
            self._project_tempdir.cleanup()
            self._project_tempdir = None

    # ──────────────────────────────────────────────────────────────────────────
    # Event filter – mouse coordinate readout
    # ──────────────────────────────────────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is self._canvas and event.type() == QEvent.Type.MouseMove:
            pos = event.position()
            wx, wy = self._canvas.vp.screen_to_world(pos.x(), pos.y())
            self._lbl_coords.setText(f"x: {wx:.2f}  y: {wy:.2f} ft")
        return super().eventFilter(obj, event)

    # ──────────────────────────────────────────────────────────────────────────
    # File loading
    # ──────────────────────────────────────────────────────────────────────────
    def _load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Floor Plan Image", "",
            "Raster Images (*.png *.jpg *.jpeg *.bmp *.tiff *.tif);;All Files (*)"
        )
        if not path:
            return
        ok = self._canvas.load_image(path)
        if ok:
            self._stop_global_rtls()
            filename = os.path.basename(path)
            self._lbl_image.setText(f"📷 {filename}")
            self._show_status(f"Loaded: {filename}")
            self._loaded_vector_path = None
            self._loaded_project_path = None
            self._reset_project_extract_dir()
            self._clear_rooms()
        else:
            QMessageBox.warning(self, "Load Error",
                                f"Could not load image:\n{path}")

    def _load_vector(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load SVG Floor Plan", "",
            "SVG Files (*.svg);;All Files (*)"
        )
        if not path:
            return
        ok = self._canvas.load_svg(path)
        if ok:
            self._stop_global_rtls()
            self._clear_rooms()
            filename = os.path.basename(path)
            self._lbl_image.setText(f"📐 {filename}")
            self._show_status(f"Loaded SVG: {filename}")
            self._loaded_vector_path = path
            self._loaded_project_path = None
            self._reset_project_extract_dir()
            if self.app_mode == self.MODE_RTLS:
                self._auto_load_room_data_for_svg(path)
        else:
            QMessageBox.warning(self, "Load Error",
                                f"Could not load SVG floor plan:\n{path}")

    def _load_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load RTLS Project",
            "",
            f"RTLS Project (*{PROJECT_EXTENSION});;All Files (*)"
        )
        if not path:
            return
        self._reset_project_extract_dir()
        self._project_tempdir = tempfile.TemporaryDirectory(prefix="rtls_project_")
        try:
            svg_path, _, rooms = load_project_package(path, self._project_tempdir.name)
            ok = self._canvas.load_svg(svg_path)
            if not ok:
                raise ValueError("Could not load floorplan.svg from project")
        except Exception as exc:
            self._reset_project_extract_dir()
            QMessageBox.warning(self, "Load Error", f"Could not load project:\n{exc}")
            return

        self._rooms = rooms
        self._clear_rtls_history()
        self._refresh_room_list()
        self._canvas.highlighted_room = None
        self._canvas.clear_active_tags()
        self._canvas.update()
        self._loaded_vector_path = svg_path
        self._loaded_project_path = path
        self._lbl_image.setText(f"📦 {os.path.basename(path)}")
        self._show_status(f"Loaded project with {len(rooms)} room(s)")

    def _auto_load_room_data_for_svg(self, svg_path: str):
        manifest_path = manifest_path_for_svg(svg_path)
        if not os.path.exists(manifest_path):
            return
        try:
            _, rooms = load_floorplan_manifest(manifest_path)
            self._stop_global_rtls()
            self._rooms = rooms
            self._clear_rtls_history()
            self._refresh_room_list()
            self._canvas.highlighted_room = None
            self._canvas.clear_active_tags()
            self._canvas.update()
            self._show_status(f"Loaded vector and restored {len(rooms)} room profile(s)")
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Room Data Load Error",
                f"Loaded SVG, but failed to restore room data:\n{exc}"
            )

    def _load_room_data(self):
        default_path = ""
        if self._loaded_vector_path:
            default_path = manifest_path_for_svg(self._loaded_vector_path)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Room Data",
            default_path,
            "Room Data (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            _, rooms = load_floorplan_manifest(path)
        except Exception as exc:
            QMessageBox.warning(self, "Load Error", f"Could not load room data:\n{exc}")
            return
        self._stop_global_rtls()
        self._rooms = rooms
        self._clear_rtls_history()
        self._refresh_room_list()
        self._canvas.highlighted_room = None
        self._canvas.clear_active_tags()
        self._canvas.update()
        self._show_status(f"Loaded room data for {len(rooms)} room(s)")

    def _save_room_data(self):
        if not self._rooms:
            QMessageBox.information(self, "No Rooms", "There are no rooms to save yet.")
            return
        if not self._loaded_vector_path:
            QMessageBox.information(
                self,
                "No SVG Loaded",
                "Load an SVG first so room data can be saved next to it."
            )
            return
        path = manifest_path_for_svg(self._loaded_vector_path)
        if os.path.exists(path):
            reply = QMessageBox.question(
                self,
                "Overwrite Room Data",
                f"Room data already exists for this SVG:\n{path}\n\nOverwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            path = save_floorplan_manifest(self._loaded_vector_path, self._rooms)
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Could not save room data:\n{exc}")
            return
        QMessageBox.information(self, "Room Data Saved", f"Saved room data to:\n{path}")
        self._show_status(f"Saved room data for {len(self._rooms)} room(s)")

    def _save_project(self):
        if not self._rooms:
            QMessageBox.information(self, "No Rooms", "There are no rooms to save yet.")
            return
        if not self._loaded_vector_path or not os.path.exists(self._loaded_vector_path):
            QMessageBox.information(
                self,
                "No SVG Loaded",
                "Load an SVG first so it can be bundled into the project file."
            )
            return

        default_base = os.path.splitext(os.path.basename(self._loaded_vector_path))[0] + PROJECT_EXTENSION
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save RTLS Project",
            default_base,
            f"RTLS Project (*{PROJECT_EXTENSION});;All Files (*)"
        )
        if not path:
            return
        if not path.endswith(PROJECT_EXTENSION):
            path = f"{path}{PROJECT_EXTENSION}"
        if os.path.exists(path):
            reply = QMessageBox.question(
                self,
                "Overwrite Project",
                f"Project file already exists:\n{path}\n\nOverwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            save_project_package(path, self._loaded_vector_path, self._rooms)
        except Exception as exc:
            QMessageBox.warning(self, "Save Error", f"Could not save project:\n{exc}")
            return
        self._loaded_project_path = path
        QMessageBox.information(self, "Project Saved", f"Saved project to:\n{path}")
        self._show_status(f"Saved project with {len(self._rooms)} room(s)")

    # ──────────────────────────────────────────────────────────────────────────
    # Room Manager Panel
    # ──────────────────────────────────────────────────────────────────────────
    def _build_feature_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("feature_panel")
        panel.setStyleSheet(FEATURE_PANEL_STYLE)
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header
        header = QLabel("Room Manager")
        header.setObjectName("feature_header")
        layout.addWidget(header)

        # Rooms section
        rooms_label = QLabel("Rooms")
        layout.addWidget(rooms_label)

        self._room_list = QListWidget()
        self._room_list.itemDoubleClicked.connect(self._on_room_double_click)
        self._room_list.itemSelectionChanged.connect(self._on_list_selection)
        self._room_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._room_list.customContextMenuRequested.connect(self._show_room_context_menu)
        
        # Connect map canvas double-click
        self._canvas.map_double_clicked.connect(self._on_map_double_click)
        layout.addWidget(self._room_list)

        if self.app_mode == self.MODE_RTLS:
            rtls_label = QLabel("Live RTLS")
            layout.addWidget(rtls_label)

            port_row = QHBoxLayout()
            port_row.setSpacing(6)
            self._rtls_port_combo = QComboBox()
            self._rtls_connect_btn = QPushButton("Connect")
            self._rtls_connect_btn.setCheckable(True)
            self._rtls_connect_btn.toggled.connect(self._toggle_global_rtls)
            port_row.addWidget(self._rtls_port_combo, 1)
            port_row.addWidget(self._rtls_connect_btn)
            layout.addLayout(port_row)

            action_row = QHBoxLayout()
            action_row.setSpacing(6)
            refresh_btn = QPushButton("Refresh Ports")
            refresh_btn.clicked.connect(self._refresh_global_rtls_ports)
            self._heatmap_toggle_btn = QPushButton("Heat Map")
            self._heatmap_toggle_btn.setCheckable(True)
            self._heatmap_toggle_btn.toggled.connect(self._toggle_heatmap)
            action_row.addWidget(refresh_btn)
            action_row.addWidget(self._heatmap_toggle_btn)
            layout.addLayout(action_row)

            heat_label = QLabel("Heat Sensitivity")
            heat_label.setStyleSheet("font-size: 11px; color: #9aa4d6;")
            layout.addWidget(heat_label)
            self._heatmap_slider = QSlider(Qt.Orientation.Horizontal)
            self._heatmap_slider.setRange(1, 100)
            self._heatmap_slider.setValue(20)
            self._heatmap_slider.valueChanged.connect(self._set_heatmap_sensitivity)
            layout.addWidget(self._heatmap_slider)

            self._rtls_status_label = QLabel("Disconnected")
            self._rtls_status_label.setWordWrap(True)
            self._rtls_status_label.setStyleSheet("font-size: 11px; color: #9aa4d6;")
            layout.addWidget(self._rtls_status_label)

            history_label = QLabel("Playback")
            layout.addWidget(history_label)

            self._history_slider = QSlider(Qt.Orientation.Horizontal)
            self._history_slider.setRange(0, 0)
            self._history_slider.setEnabled(False)
            self._history_slider.sliderPressed.connect(self._on_history_slider_pressed)
            self._history_slider.sliderReleased.connect(self._on_history_slider_released)
            self._history_slider.valueChanged.connect(self._on_history_slider_changed)
            layout.addWidget(self._history_slider)

            self._history_meta_label = QLabel("No history yet")
            self._history_meta_label.setWordWrap(True)
            self._history_meta_label.setStyleSheet("font-size: 11px; color: #9aa4d6;")
            layout.addWidget(self._history_meta_label)

            playback_row = QHBoxLayout()
            playback_row.setSpacing(6)
            self._history_rewind_btn = QPushButton("⏪")
            self._history_rewind_btn.clicked.connect(lambda: self._step_history_frame(-6))
            self._history_play_btn = QPushButton("▶")
            self._history_play_btn.setCheckable(True)
            self._history_play_btn.toggled.connect(self._toggle_history_playback)
            self._history_ff_btn = QPushButton("⏩")
            self._history_ff_btn.clicked.connect(lambda: self._step_history_frame(6))
            self._history_live_btn = QPushButton("Live")
            self._history_live_btn.clicked.connect(self._jump_to_live_history)
            playback_row.addWidget(self._history_rewind_btn)
            playback_row.addWidget(self._history_play_btn)
            playback_row.addWidget(self._history_ff_btn)
            playback_row.addWidget(self._history_live_btn)
            layout.addLayout(playback_row)
            self._refresh_global_rtls_ports()
            self._refresh_history_controls()

        layout.addStretch()
        return panel

    def _refresh_room_list(self):
        self._room_list.clear()
        for r in self._rooms:
            item = QListWidgetItem(f"🏠 {r.name} ({len(r.anchors)} anchors)")
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._room_list.addItem(item)
        if self.app_mode == self.MODE_RTLS and hasattr(self, "_rtls_status_label") and self._global_serial_thread is None:
            self._rtls_status_label.setText(f"Ready with {len(self._rooms)} room(s)")

    def _find_duplicate_room(self, room_name: str, segments: list):
        stripped_name = room_name.strip().lower()

        for room in self._rooms:
            if segments_match(room.segments, segments):
                return room, "geometry"
            if room.name.strip().lower() == stripped_name:
                return room, "name"
        return None, None

    def _on_room_designated(self, name: str, segments: list, interior_segments: list):
        dup_room, dup_reason = self._find_duplicate_room(name, segments)
        if dup_room is not None:
            if dup_reason == "geometry":
                QMessageBox.information(
                    self,
                    "Duplicate Room",
                    f"That room has already been defined as '{dup_room.name}'."
                )
            else:
                QMessageBox.information(
                    self,
                    "Duplicate Room Name",
                    f"A room named '{dup_room.name}' already exists. Please use a different name."
                )
            return
        r = Room(name=name, segments=segments, interior_segments=interior_segments)
        self._rooms.append(r)
        self._stop_global_rtls()
        self._clear_rtls_history()
        self._refresh_room_list()
        self._show_status(f"Room created: {name}")

    def _rename_room(self):
        item = self._room_list.currentItem()
        if not item:
            return
        room = item.data(Qt.ItemDataRole.UserRole)
        new_name, ok = QInputDialog.getText(
            self, "Rename Room", "Enter new name:", text=room.name
        )
        if ok and new_name.strip():
            room.name = new_name.strip()
            self._refresh_room_list()
            
    def _delete_room(self):
        item = self._room_list.currentItem()
        if not item:
            return
        room = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Delete Room", f"Are you sure you want to delete '{room.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._rooms.remove(room)
            self._stop_global_rtls()
            self._clear_rtls_history()
            self._refresh_room_list()

    def _show_room_context_menu(self, pos):
        item = self._room_list.itemAt(pos)
        if not item:
            return
        self._room_list.setCurrentItem(item)
        menu = QMenu(self)
        act_rename = menu.addAction("Rename Room")
        act_delete = menu.addAction("Delete Room")
        chosen = menu.exec(self._room_list.mapToGlobal(pos))
        if chosen == act_rename:
            self._rename_room()
        elif chosen == act_delete:
            self._delete_room()

    def _on_room_double_click(self, item):
        room = item.data(Qt.ItemDataRole.UserRole)
        self._open_room_view(room)
        
    def _open_room_view(self, room):
        self._show_status(f"Opening Room view for: {room.name}")
        
        from room_detail_view import RoomDetailDialog
        dlg = RoomDetailDialog(
            room,
            self._rooms,
            self,
            editable=(self.app_mode == self.MODE_ANCHOR_MAPPER),
            world_tag_provider=(
                (lambda: dict(self._active_tags_world))
                if self.app_mode == self.MODE_RTLS
                else None
            ),
        )
        dlg.exec()
        
        # Refresh list to update anchor count label (e.g. "Room 1 (4 anchors)")
        self._refresh_room_list()
        
    def _on_list_selection(self):
        items = self._room_list.selectedItems()
        if not items:
            self._canvas.highlighted_room = None
        else:
            self._canvas.highlighted_room = items[0].data(Qt.ItemDataRole.UserRole)
        self._canvas.update()
        
    def _on_map_double_click(self, wx: float, wy: float):
        for room in self._rooms:
            lx, ly = room.world_to_local(wx, wy)
            if room.contains_local_point(lx, ly):
                # We found the room they clicked inside
                self._open_room_view(room)
                break

    # ──────────────────────────────────────────────────────────────────────────
    # Placeholder handlers (future phases)
    # ──────────────────────────────────────────────────────────────────────────
    def _on_no_image(self):
        QMessageBox.information(self, "No Image",
                                "Please load a floor plan image first.")

    def _refresh_global_rtls_ports(self):
        if not hasattr(self, "_rtls_port_combo"):
            return
        ports = ["Virtual MOCK_RTLS"]
        try:
            import serial.tools.list_ports
            ports.extend(p.device for p in serial.tools.list_ports.comports())
        except ImportError:
            pass

        current = self._rtls_port_combo.currentText()
        self._rtls_port_combo.blockSignals(True)
        self._rtls_port_combo.clear()
        self._rtls_port_combo.addItems(ports)
        if current and current in ports:
            self._rtls_port_combo.setCurrentText(current)
        self._rtls_port_combo.blockSignals(False)

    def _build_global_anchor_positions(self):
        anchor_positions = {}
        missing_hw = []
        duplicate_hw = []
        for room in self._rooms:
            for anchor in room.anchors:
                hw_id = (anchor.hw_id or "").strip()
                if not hw_id:
                    missing_hw.append(f"{room.name}:{anchor.id}")
                    continue
                if hw_id in anchor_positions:
                    duplicate_hw.append(hw_id)
                    continue
                wx, wy = room.local_to_world(anchor.x, anchor.y)
                anchor_positions[hw_id] = (wx, wy)
        return anchor_positions, missing_hw, duplicate_hw

    def _default_global_tag_height(self) -> float:
        for room in self._rooms:
            try:
                value = float(room.rtls_settings.get("tag_height_ft", 0.0))
            except Exception:
                value = 0.0
            if value > 0.0:
                return value
        return 0.0

    def _toggle_heatmap(self, checked: bool):
        self._canvas.set_heatmap_enabled(checked)
        if hasattr(self, "_rtls_status_label") and self._global_serial_thread is None:
            self._rtls_status_label.setText("Heat map enabled" if checked else "Heat map disabled")

    def _set_heatmap_sensitivity(self, value: int):
        self._canvas.set_heatmap_sensitivity(value)
        if hasattr(self, "_rtls_status_label") and self._global_serial_thread is None:
            self._rtls_status_label.setText(f"Heat sensitivity: {value}")

    def _toggle_global_rtls(self, checked: bool):
        if checked:
            if len(self._rooms) == 0:
                QMessageBox.information(self, "No Rooms", "Load room data before connecting RTLS.")
                self._rtls_connect_btn.blockSignals(True)
                self._rtls_connect_btn.setChecked(False)
                self._rtls_connect_btn.blockSignals(False)
                return

            port = self._rtls_port_combo.currentText().strip() if hasattr(self, "_rtls_port_combo") else ""
            if not port:
                self._rtls_connect_btn.blockSignals(True)
                self._rtls_connect_btn.setChecked(False)
                self._rtls_connect_btn.blockSignals(False)
                return

            anchor_positions = {}
            missing_hw = []
            duplicate_hw = []
            if port != "Virtual MOCK_RTLS":
                anchor_positions, missing_hw, duplicate_hw = self._build_global_anchor_positions()
                if len(anchor_positions) < 2:
                    QMessageBox.information(
                        self,
                        "Insufficient Anchors",
                        "At least two anchors with unique hardware IDs are required across loaded rooms."
                    )
                    self._rtls_connect_btn.blockSignals(True)
                    self._rtls_connect_btn.setChecked(False)
                    self._rtls_connect_btn.blockSignals(False)
                    return

            try:
                if port == "Virtual MOCK_RTLS":
                    from serial_reader import MockSerialReaderThread
                    self._global_serial_thread = MockSerialReaderThread(
                        rooms=self._rooms,
                        coordinate_mode="world",
                    )
                    self._using_mock_rtls = True
                    self._mock_room = None
                    if hasattr(self, "_heatmap_toggle_btn") and not self._heatmap_toggle_btn.isChecked():
                        self._heatmap_toggle_btn.setChecked(True)
                else:
                    from serial_reader import SerialReaderThread
                    self._global_serial_thread = SerialReaderThread(
                        port,
                        115200,
                        anchor_positions,
                        tag_height=self._default_global_tag_height(),
                    )
                    self._using_mock_rtls = False
                    self._mock_room = None
                self._global_serial_thread.tag_update.connect(self._on_global_tag_update)
                self._global_serial_thread.connection_error.connect(self._on_global_rtls_error)
                self._global_serial_thread.start()
            except Exception as exc:
                QMessageBox.warning(self, "RTLS Error", str(exc))
                self._rtls_connect_btn.blockSignals(True)
                self._rtls_connect_btn.setChecked(False)
                self._rtls_connect_btn.blockSignals(False)
                return

            if missing_hw:
                self._show_notice(f"Skipped anchors without hardware IDs: {len(missing_hw)}")
            if duplicate_hw:
                self._show_notice(f"Skipped duplicate hardware IDs: {len(duplicate_hw)}")

            self._rtls_port_combo.setEnabled(False)
            self._rtls_connect_btn.setText("Disconnect")
            self._show_status("RTLS stream connected")
            if hasattr(self, "_rtls_status_label"):
                self._rtls_status_label.setText(f"Connected on {port}")
            self._set_history_live_mode(True)
        else:
            self._stop_global_rtls()

    def _stop_global_rtls(self):
        if self._global_serial_thread is not None:
            self._global_serial_thread.stop()
            self._global_serial_thread = None
        self._using_mock_rtls = False
        self._mock_room = None
        self._live_tags_world.clear()
        if hasattr(self, "_rtls_connect_btn"):
            self._rtls_connect_btn.blockSignals(True)
            self._rtls_connect_btn.setChecked(False)
            self._rtls_connect_btn.blockSignals(False)
            self._rtls_connect_btn.setText("Connect")
        if hasattr(self, "_rtls_port_combo"):
            self._rtls_port_combo.setEnabled(True)
        if hasattr(self, "_rtls_status_label"):
            self._rtls_status_label.setText("Disconnected")
        if self._rtls_history:
            self._set_history_live_mode(False)
            self._apply_history_snapshot(len(self._rtls_history) - 1)
        else:
            self._active_tags_world.clear()
            self._canvas.set_heatmap_snapshot_mode(False)
            self._canvas.clear_active_tags()
        self._refresh_history_controls()

    def _on_global_tag_update(self, tag_id: str, x: float, y: float):
        if self._using_mock_rtls and self._mock_room is not None:
            wx, wy = self._mock_room.local_to_world(x, y)
        else:
            wx, wy = x, y
        self._live_tags_world[tag_id] = (wx, wy)
        if self._history_follow_live:
            self._active_tags_world = dict(self._live_tags_world)
            self._canvas.set_active_tags_world(self._active_tags_world)

    def _on_global_rtls_error(self, err: str):
        QMessageBox.warning(self, "RTLS Error", err)
        self._stop_global_rtls()

    def _capture_rtls_history_frame(self):
        if self._global_serial_thread is None or not self._live_tags_world:
            return

        self._rtls_history.append((time.monotonic(), dict(self._live_tags_world)))
        if len(self._rtls_history) > self._history_max_frames:
            overflow = len(self._rtls_history) - self._history_max_frames
            self._rtls_history = self._rtls_history[overflow:]
            if not self._history_follow_live:
                self._history_index = max(0, self._history_index - overflow)

        if self._history_follow_live:
            self._history_index = len(self._rtls_history) - 1

        self._refresh_history_controls()

    def _format_history_label(self) -> str:
        if not self._rtls_history:
            return "No history yet"
        total = len(self._rtls_history)
        if self._history_follow_live:
            return f"Live · {total} frames buffered"
        idx = max(0, min(self._history_index, total - 1))
        latest_ts = self._rtls_history[-1][0]
        frame_ts = self._rtls_history[idx][0]
        seconds_behind = max(0.0, latest_ts - frame_ts)
        return f"{seconds_behind:.1f}s behind live · frame {idx + 1}/{total}"

    def _current_heatmap_frames(self):
        if not self._rtls_history:
            return []
        if self._history_follow_live:
            start = max(0, len(self._rtls_history) - 180)
            return [snapshot for _, snapshot in self._rtls_history[start:]]
        if self._history_index < 0:
            return []
        start = max(0, self._history_index - 90)
        end = min(len(self._rtls_history), self._history_index + 1)
        return [snapshot for _, snapshot in self._rtls_history[start:end]]

    def _refresh_history_controls(self):
        if not hasattr(self, "_history_slider"):
            return

        has_history = bool(self._rtls_history)
        max_index = max(0, len(self._rtls_history) - 1)

        self._history_slider.setEnabled(has_history)
        self._history_slider.blockSignals(True)
        self._history_slider.setRange(0, max_index)
        self._history_slider.setValue(
            max_index if self._history_follow_live and has_history else max(0, min(self._history_index, max_index))
        )
        self._history_slider.blockSignals(False)

        self._history_meta_label.setText(self._format_history_label())
        for btn in (
            self._history_rewind_btn,
            self._history_play_btn,
            self._history_ff_btn,
        ):
            btn.setEnabled(has_history)
        self._history_live_btn.setEnabled(has_history and self._global_serial_thread is not None)

        self._history_play_btn.blockSignals(True)
        self._history_play_btn.setChecked(self._history_playing)
        self._history_play_btn.setText("⏸" if self._history_playing else "▶")
        self._history_play_btn.blockSignals(False)

        self._history_live_btn.setStyleSheet(
            "font-weight: bold; color: #ffffff;" if self._history_follow_live else ""
        )

    def _set_history_live_mode(self, enabled: bool):
        self._history_follow_live = enabled
        self._history_playing = False
        self._history_play_timer.stop()
        if enabled:
            self._history_index = len(self._rtls_history) - 1
            self._active_tags_world = dict(self._live_tags_world)
            self._canvas.set_heatmap_snapshot_mode(False)
            self._canvas.set_active_tags_world(self._active_tags_world)
        else:
            self._canvas.set_heatmap_snapshot_mode(True)
        self._refresh_history_controls()

    def _apply_history_snapshot(self, index: int):
        if not self._rtls_history:
            return
        index = max(0, min(index, len(self._rtls_history) - 1))
        self._history_index = index
        self._active_tags_world = dict(self._rtls_history[index][1])
        self._canvas.set_active_tags_world(self._active_tags_world)
        self._refresh_history_controls()

    def _on_history_slider_pressed(self):
        self._history_slider_dragging = True
        if self._rtls_history:
            self._set_history_live_mode(False)

    def _on_history_slider_released(self):
        self._history_slider_dragging = False
        if self._rtls_history:
            self._set_history_live_mode(False)
            self._apply_history_snapshot(self._history_slider.value())

    def _on_history_slider_changed(self, value: int):
        if not self._rtls_history:
            return
        if self._history_slider_dragging or not self._history_follow_live:
            self._set_history_live_mode(False)
            self._apply_history_snapshot(value)

    def _toggle_history_playback(self, checked: bool):
        if not self._rtls_history:
            self._history_playing = False
            self._refresh_history_controls()
            return
        if checked:
            self._set_history_live_mode(False)
            if self._history_index >= len(self._rtls_history) - 1:
                self._history_index = 0
                self._apply_history_snapshot(self._history_index)
            self._history_playing = True
            self._history_play_timer.start()
        else:
            self._history_playing = False
            self._history_play_timer.stop()
        self._refresh_history_controls()

    def _advance_history_playback(self):
        if not self._history_playing or not self._rtls_history:
            return
        next_index = self._history_index + self._history_step
        if next_index >= len(self._rtls_history):
            self._history_playing = False
            self._history_play_timer.stop()
            self._apply_history_snapshot(len(self._rtls_history) - 1)
            return
        self._apply_history_snapshot(next_index)

    def _step_history_frame(self, delta: int):
        if not self._rtls_history:
            return
        self._set_history_live_mode(False)
        base_index = self._history_index if self._history_index >= 0 else len(self._rtls_history) - 1
        self._apply_history_snapshot(base_index + delta)

    def _jump_to_live_history(self):
        if self._global_serial_thread is None:
            if self._rtls_history:
                self._set_history_live_mode(False)
                self._apply_history_snapshot(len(self._rtls_history) - 1)
            return
        self._set_history_live_mode(True)

    def _clear_rtls_history(self):
        self._history_playing = False
        self._history_play_timer.stop()
        self._history_slider_dragging = False
        self._rtls_history.clear()
        self._history_index = -1
        self._history_follow_live = True
        self._live_tags_world.clear()
        self._active_tags_world.clear()
        self._canvas.set_heatmap_snapshot_mode(False)
        self._canvas.clear_active_tags()
        self._refresh_history_controls()

    def closeEvent(self, event):
        self._stop_global_rtls()
        super().closeEvent(event)




# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────
def main():
    # High-DPI policy must be set BEFORE creating QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("RTLS Dashboard")
    app.setOrganizationName("UWB Contact Tracing")

    win = RTLSDashboard()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
