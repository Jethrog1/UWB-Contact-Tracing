import sys
import math
import random
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton,
                             QFrame, QSizePolicy, QSpacerItem, QStackedWidget, QCheckBox, QDoubleSpinBox,
                             QDockWidget, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
                             QToolButton, QMenu, QInputDialog, QMessageBox, QLayout)
from PyQt6.QtGui import QAction, QActionGroup, QFont, QFontDatabase, QIcon, QColor, QPalette, QPainter, QPen, QPainterPath
from PyQt6.QtCore import Qt, QSize, QRect, QPoint, QEasingCurve, QPropertyAnimation, QParallelAnimationGroup, QSequentialAnimationGroup, QTimer
from utils.font_utils import get_default_font_family
from workspace_switcher import WorkspaceSwitcher

# Local Imports
from cad_core import Line, Viewport
# from geometry import intersect_lines, get_intersection # Unused and not found
from qt_snap import QtSnapController

HOME_FONT_FAMILY = get_default_font_family()

HOME_SCREEN_STYLE = (
f"""
QWidget#home_screen {{
    background-color: #000000;
    font-family: "{HOME_FONT_FAMILY}";
}}
"""
"""
QFrame#hero_panel {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(18, 25, 41, 246),
        stop:1 rgba(24, 37, 60, 240)
    );
    border: 1px solid rgba(120, 146, 194, 0.20);
    border-radius: 28px;
}
QFrame#tool_panel {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(16, 23, 38, 242),
        stop:1 rgba(22, 34, 55, 236)
    );
    border: 1px solid rgba(111, 130, 172, 0.18);
    border-radius: 24px;
}
QFrame#intro_outline {
    background-color: transparent;
    border: 1px solid rgba(120, 146, 194, 0.55);
    border-radius: 28px;
}
QLabel#brand_badge {
    background-color: rgba(255, 255, 255, 0.05);
    color: #d9e4ff;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 14px;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#hero_title {
    color: #f5f7ff;
    font-size: 30px;
    font-weight: 700;
}
QLabel#hero_copy {
    color: #aab6d4;
    font-size: 14px;
    line-height: 1.45em;
}
QLabel#loading_copy {
    color: #8e9dbc;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
QPushButton#launch_card {
    background-color: rgba(27, 36, 58, 235);
    border: 1px solid rgba(123, 146, 196, 0.20);
    border-radius: 22px;
    text-align: left;
    padding: 0px;
}
QPushButton#launch_card:hover {
    background-color: rgba(34, 45, 71, 248);
    border: 1px solid rgba(122, 157, 255, 0.55);
}
QPushButton#launch_card:pressed {
    background-color: rgba(21, 29, 47, 248);
}
QLabel#launch_icon {
    color: #f5f7ff;
    background-color: transparent;
    font-size: 24px;
    font-weight: 700;
}
QLabel#launch_title {
    color: #f5f7ff;
    background-color: transparent;
    font-size: 18px;
    font-weight: 700;
}
QLabel#launch_subtitle {
    color: #9eacc8;
    background-color: transparent;
    font-size: 13px;
    line-height: 1.45em;
}
QLabel#launch_hint {
    color: #7d8fb4;
    background-color: transparent;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
QFrame#launch_badge {
    background-color: rgba(255, 255, 255, 0.06);
    border-radius: 14px;
}
"""
)


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=18):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        right_edge = rect.x() + rect.width()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if line_height > 0 and next_x - spacing > right_edge:
                x = rect.x()
                y += line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))

            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y()


class LaunchCard(QPushButton):
    def __init__(self, title, subtitle, icon_text, hint_text, parent=None):
        super().__init__(parent)
        self.setObjectName("launch_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._card_size = QSize(280, 196)
        self.setMinimumSize(self._card_size)
        self.setMaximumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)

        badge = QFrame()
        badge.setObjectName("launch_badge")
        badge.setFixedSize(46, 46)
        badge_layout = QVBoxLayout(badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel(icon_text)
        icon_lbl.setObjectName("launch_icon")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_layout.addWidget(icon_lbl)

        top_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        top_row.addStretch()
        layout.addLayout(top_row)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("launch_title")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("launch_subtitle")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)
        layout.addStretch()

        hint = QLabel(hint_text)
        hint.setObjectName("launch_hint")
        layout.addWidget(hint)

    def sizeHint(self):
        return QSize(self._card_size)

    def minimumSizeHint(self):
        return QSize(self._card_size)


class HomeScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("home_screen")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet(HOME_SCREEN_STYLE)
        self._intro_group = None
        self._intro_animations = []
        self._intro_played_once = False
        self._intro_reveal_targets = {}
        self._intro_width_targets = {}
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(260)
        self._loading_timer.timeout.connect(self._advance_loading_dots)
        self._intro_start_timer = QTimer(self)
        self._intro_start_timer.setSingleShot(True)
        self._intro_start_timer.timeout.connect(self._start_main_intro_sequence)
        self._loading_dot_count = 0
        self._intro_loading_active = False

        self.btn_new_plan = None
        self.btn_anchor_mapper = None
        self.btn_rtls_dashboard = None
        self.hero_badge = None
        self.hero_title = None
        self.hero_copy = None
        self.tool_badge = None
        self.tool_title = None
        self.tool_copy = None
        self.tool_card_host = None
        self.intro_welcome = None
        self.intro_loading = None
        self.intro_outline = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(34, 30, 34, 30)
        outer.setSpacing(24)

        self.hero_panel = self._build_hero_panel()
        outer.addWidget(self.hero_panel)

        self.tools_panel = self._build_tools_panel()
        outer.addWidget(self.tools_panel, 1)

        self.intro_welcome = QLabel("Welcome, User", self)
        self.intro_welcome.setObjectName("hero_title")
        self.intro_welcome.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.intro_welcome.hide()
        self.intro_welcome.raise_()

        self.intro_loading = QLabel("loading", self)
        self.intro_loading.setObjectName("loading_copy")
        self.intro_loading.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.intro_loading.hide()
        self.intro_loading.raise_()

        self.intro_outline = QFrame(self)
        self.intro_outline.setObjectName("intro_outline")
        self.intro_outline.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.intro_outline.hide()
        self.intro_outline.raise_()

        QTimer.singleShot(0, self.play_intro_animation)

    def _build_hero_panel(self):
        panel = QFrame()
        panel.setObjectName("hero_panel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(6)

        self.hero_badge = QLabel("UWB WORKSPACE")
        self.hero_badge.setObjectName("brand_badge")
        self.hero_badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.hero_badge, 0, Qt.AlignmentFlag.AlignLeft)

        self.hero_title = QLabel("Welcome, User")
        self.hero_title.setObjectName("hero_title")
        self.hero_title.setWordWrap(True)
        layout.addWidget(self.hero_title)

        self.hero_copy = QLabel(
            "Choose a workspace to start drawing floor plans, mapping anchors, or opening live RTLS views."
        )
        self.hero_copy.setObjectName("hero_copy")
        self.hero_copy.setWordWrap(True)
        self.hero_copy.setMaximumWidth(760)
        layout.addWidget(self.hero_copy)

        layout.addStretch(1)
        return panel

    def _build_tools_panel(self):
        panel = QFrame()
        panel.setObjectName("tool_panel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(6)

        self.tool_badge = QLabel("LAUNCHPAD")
        self.tool_badge.setObjectName("brand_badge")
        self.tool_badge.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.tool_badge)

        self.tool_title = QLabel("Choose a workspace")
        self.tool_title.setObjectName("hero_title")
        layout.addWidget(self.tool_title)

        self.tool_copy = QLabel(
            "Each tool opens into its own focused environment."
        )
        self.tool_copy.setObjectName("hero_copy")
        self.tool_copy.setWordWrap(True)
        self.tool_copy.setMaximumWidth(760)
        layout.addWidget(self.tool_copy)

        card_host = QWidget()
        self.tool_card_host = card_host
        card_host.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout.addSpacing(12)
        flow = FlowLayout(card_host, spacing=18)
        self.launch_cards = []

        tool_specs = [
            ("Launch 2DLCAD", "Start a fresh CAD workspace for drawing and editing 2D floor plans.", "✦", "CREATE"),
            ("Launch Anchor Mapper", "Load SVG floor plans, define rooms, place anchors, and save room data.", "⚓", "CONFIGURE"),
            ("Launch RTLS Dashboard", "Open prepared projects and monitor live RTLS behavior in a focused viewer.", "◉", "TRACK"),
        ]

        for title, subtitle, icon_text, hint_text in tool_specs:
            card = LaunchCard(title, subtitle, icon_text, hint_text)
            self.launch_cards.append(card)
            flow.addWidget(card)

        self.btn_new_plan = self.launch_cards[0]
        self.btn_anchor_mapper = self.launch_cards[1]
        self.btn_rtls_dashboard = self.launch_cards[2]

        layout.addWidget(card_host)
        layout.addStretch(1)
        return panel

    def _activate_home_layouts(self):
        if self.layout() is not None:
            self.layout().activate()
        if self.hero_panel.layout() is not None:
            self.hero_panel.layout().activate()
        if self.tools_panel.layout() is not None:
            self.tools_panel.layout().activate()
        if self.tool_card_host is not None and self.tool_card_host.layout() is not None:
            self.tool_card_host.layout().activate()

    def _set_collapsed(self, widget, collapsed: bool):
        if widget is None:
            return
        widget.setMinimumHeight(0)
        if collapsed:
            widget.setMaximumHeight(0)
        else:
            widget.setMaximumHeight(16777215)

    def _reset_intro_state(self):
        self._activate_home_layouts()
        self._loading_timer.stop()
        self._intro_start_timer.stop()
        self._intro_loading_active = False
        self._intro_reveal_targets = {}
        self._intro_width_targets = {}
        self.hero_panel.show()
        self.tools_panel.show()
        for widget in (
            self.hero_panel,
            self.tools_panel,
            self.hero_badge,
            self.hero_title,
            self.hero_copy,
            self.tool_badge,
            self.tool_title,
            self.tool_copy,
            *self.launch_cards,
        ):
            self._set_collapsed(widget, collapsed=False)
        self.hero_badge.setMaximumWidth(16777215)
        self.tool_badge.setMaximumWidth(16777215)
        if self.intro_welcome is not None:
            self.intro_welcome.hide()
        if self.intro_loading is not None:
            self.intro_loading.hide()
        if self.intro_outline is not None:
            self.intro_outline.hide()

    def _position_intro_overlay(self):
        if self.intro_welcome is None:
            return
        self.intro_welcome.adjustSize()
        bounds = self.rect()
        welcome_x = bounds.x() + (bounds.width() - self.intro_welcome.width()) // 2
        welcome_y = bounds.y() + (bounds.height() - self.intro_welcome.height()) // 2 - 12
        self.intro_welcome.move(welcome_x, welcome_y)
        if self.intro_loading is not None:
            self.intro_loading.adjustSize()
            loading_x = bounds.x() + (bounds.width() - self.intro_loading.width()) // 2
            loading_y = self.intro_welcome.y() + self.intro_welcome.height() + 12
            self.intro_loading.move(loading_x, loading_y)

    def _advance_loading_dots(self):
        self._loading_dot_count = (self._loading_dot_count + 1) % 4
        self.intro_loading.setText("loading" + ("." * self._loading_dot_count))
        self._position_intro_overlay()

    def _start_main_intro_sequence(self):
        if not self.isVisible():
            return

        self._loading_timer.stop()
        self._intro_loading_active = False
        self.intro_loading.hide()

        if self._intro_group is not None:
            self._intro_group.stop()

        self._activate_home_layouts()
        self._position_intro_overlay()

        container = QParallelAnimationGroup(self)
        animations = []
        reveal_targets = dict(self._intro_reveal_targets)
        width_targets = dict(self._intro_width_targets)

        target_pos = self.hero_title.mapTo(self, QPoint(0, 0))

        intro_move = QPropertyAnimation(self.intro_welcome, b"pos", self)
        intro_move.setDuration(1400)
        intro_move.setStartValue(self.intro_welcome.pos())
        intro_move.setEndValue(target_pos)
        intro_move.setEasingCurve(QEasingCurve.Type.OutCubic)
        container.addAnimation(intro_move)
        animations.append((self.intro_welcome, intro_move))

        overlay_hide_seq = QSequentialAnimationGroup(self)
        overlay_hide_seq.addPause(1500)
        overlay_hide_seq.finished.connect(self.intro_welcome.hide)
        container.addAnimation(overlay_hide_seq)

        for widget in (
            self.tools_panel,
            self.hero_badge,
            self.hero_title,
            self.hero_copy,
            self.tool_badge,
            self.tool_title,
            self.tool_copy,
            *self.launch_cards,
        ):
            self._set_collapsed(widget, collapsed=True)

        for widget, delay, duration in (
            (self.hero_title, 1400, 420),
            (self.hero_copy, 1580, 460),
            (self.tools_panel, 1800, 520),
            (self.tool_title, 2220, 420),
            (self.tool_copy, 2400, 420),
        ):
            seq, refs = self._build_reveal(widget, delay, duration, reveal_targets[widget])
            container.addAnimation(seq)
            animations.append(refs)

        for widget, delay, duration in (
            (self.hero_badge, 1320, 360),
            (self.tool_badge, 2140, 360),
        ):
            seq, refs = self._build_horizontal_reveal(widget, delay, duration, width_targets[widget])
            container.addAnimation(seq)
            animations.append(refs)

        card_delay_start = 2720
        for index, card in enumerate(self.launch_cards):
            seq, refs = self._build_reveal(card, card_delay_start + (index * 180), 320, reveal_targets[card])
            container.addAnimation(seq)
            animations.append(refs)

        self._intro_group = container
        self._intro_animations = animations
        self._intro_group.finished.connect(self._reset_intro_state)
        self._intro_group.start()
        self._intro_played_once = True

    def _build_reveal(self, widget, delay_ms, duration_ms=260, end_height=None):
        if end_height is None:
            end_height = max(widget.height(), widget.sizeHint().height(), 1)
        self._set_collapsed(widget, collapsed=True)
        reveal_anim = QPropertyAnimation(widget, b"maximumHeight", self)
        reveal_anim.setDuration(duration_ms)
        reveal_anim.setStartValue(0)
        reveal_anim.setEndValue(end_height)
        reveal_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        seq = QSequentialAnimationGroup(self)
        seq.addPause(delay_ms)
        seq.addAnimation(reveal_anim)
        return seq, (widget, reveal_anim)

    def _build_horizontal_reveal(self, widget, delay_ms, duration_ms=260, end_width=None):
        if end_width is None:
            end_width = max(widget.width(), widget.sizeHint().width(), 1)
        end_height = max(widget.height(), widget.sizeHint().height(), 1)
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(0)
        widget.setMaximumHeight(end_height)
        reveal_anim = QPropertyAnimation(widget, b"maximumWidth", self)
        reveal_anim.setDuration(duration_ms)
        reveal_anim.setStartValue(0)
        reveal_anim.setEndValue(end_width)
        reveal_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        seq = QSequentialAnimationGroup(self)
        seq.addPause(delay_ms)
        seq.addAnimation(reveal_anim)
        return seq, (widget, reveal_anim)

    def play_intro_animation(self):
        if not self.isVisible():
            return
        self._intro_played_once = True

        if self._intro_group is not None:
            self._intro_group.stop()

        self._reset_intro_state()
        self._activate_home_layouts()
        self._intro_reveal_targets = {
            widget: max(widget.height(), widget.sizeHint().height(), 1)
            for widget in (
                self.hero_badge,
                self.hero_title,
                self.hero_copy,
                self.tools_panel,
                self.tool_badge,
                self.tool_title,
                self.tool_copy,
                *self.launch_cards,
            )
        }
        self._intro_width_targets = {
            widget: max(widget.width(), widget.sizeHint().width(), 1)
            for widget in (
                self.hero_badge,
                self.tool_badge,
            )
        }

        self.hero_panel.show()
        self.tools_panel.show()
        self.intro_outline.hide()
        self.hero_badge.setMaximumWidth(16777215)
        self.tool_badge.setMaximumWidth(16777215)
        self._loading_dot_count = 0
        self.intro_loading.setText("loading")
        self._position_intro_overlay()
        self.intro_welcome.show()
        self.intro_welcome.raise_()
        self.intro_loading.show()
        self.intro_loading.raise_()
        self._intro_loading_active = True

        for widget in (
            self.tools_panel,
            self.hero_badge,
            self.hero_title,
            self.hero_copy,
            self.tool_badge,
            self.tool_title,
            self.tool_copy,
            *self.launch_cards,
        ):
            self._set_collapsed(widget, collapsed=True)

        self._loading_timer.start()
        self._intro_start_timer.start(random.randint(1000, 2000))

    def showEvent(self, event):
        super().showEvent(event)
        if not self._intro_played_once:
            QTimer.singleShot(0, self.play_intro_animation)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._intro_loading_active and self.intro_welcome.isVisible():
            self._position_intro_overlay()
            QTimer.singleShot(0, self._position_intro_overlay)

from cad_core import Viewport, Line, Spline
from qt_snap import QtSnapController
import geometry
from pdf_importer import extract_lines_from_pdf
from rtls_dashboard import RTLSDashboard

class CADWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # Enable keyboard events
        self.vp = Viewport()
        self.lines = []
        self.history = []
        self.history_index = -1
        self.show_vertices = True
        
        # Snapping components

        self.snap_enabled = True  # Default to on
        self.snap_controller = QtSnapController(self)
            
        self.angle_snaps = [0.0, 90.0, 180.0, 270.0]
        self.snap_dist_endpoint = 0.2
        self.snap_dist_line = 0.15
        self.snap_align_threshold = 0.12
        
        # Drag State
        self.drag_active = False
        self.drag_mode = None # "vertex", "body"
        self.drag_refs = []
        self.drag_line = None
        self.drag_start_world = (0, 0)
        self.drag_line_start_coords = None
        
        self.snap_hint = None         # ("endpoint", x, y)
        self.alignment_guides = []    # list of (x1, y1, x2, y2, type)
        self.parallel_guides = []
        self.equal_length_guides = []
        
        
        self.grid_enabled = True # Grid state
        self.grid_snap_enabled = False # Snap state
        self.current_grid_step = 1.0 # Updated by paintEvent
        
        self.selected_line = None 
        self._length_label_rects = []  # [(QRect, Line)] — populated each paintEvent
        
        self.on_lines_changed = None # Callback function

        # Tool state
        self.tool_mode = "cursor" # cursor, line
        self.selection_mode = "chain" # chain, element
        self.maintain_connectivity = True
        self.next_group_id = 1 # Counter for group IDs
        self.drawing_line = False
        self.temp_line_start = None
        self.current_mouse_pos = (0, 0)
        self.spline_points = [] # For construction: p1, cp1, cp2, p2
        
        # Pan state
        self.panning = False
        self.last_pan_pos = None

        # Trim State
        self.trim_step = 0 # 0=Select Line, 1=Click P1, 2=Click P2
        self.trim_target = None
        self.trim_points = []

        # Aesthetics
        self.grid_color = QColor(60, 60, 60)
        self.bg_color = QColor(20, 20, 20)
        self.line_color = QColor("#4A9EFF")
        self.selected_color = QColor("#FF4444")
        self.temp_line_color = QColor("#FFFFFF")
        self.snap_marker_color = QColor("#FFDD00")

        # Cancel Button (Overlay)
        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #D32F2F; 
                color: white; 
                border-radius: 4px;
                font-weight: bold;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #F44336;
            }
        """)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(self.cancel_operation)
        
        # Initialize history
        self.save_state()

    def fit_in_view(self):
        """Scale and pan to fit all geometry in the viewport."""
        if not self.lines:
            return
            
        min_x = min(min(L.x1, L.x2) for L in self.lines)
        max_x = max(max(L.x1, L.x2) for L in self.lines)
        min_y = min(min(L.y1, L.y2) for L in self.lines)
        max_y = max(max(L.y1, L.y2) for L in self.lines)
        
        from cad_core import Spline
        for obj in self.lines:
            if isinstance(obj, Spline):
                min_x = min(min_x, obj.cx1, obj.cx2)
                max_x = max(max_x, obj.cx1, obj.cx2)
                min_y = min(min_y, obj.cy1, obj.cy2)
                max_y = max(max_y, obj.cy1, obj.cy2)
                
        w = max(max_x - min_x, 1e-3)
        h = max(max_y - min_y, 1e-3)
        
        W, H = self.width(), self.height()
        if W < 10 or H < 10:
            return
            
        MARGIN = 0.15 # 15% margin
        scale = min((W * (1 - MARGIN*2)) / w, (H * (1 - MARGIN*2)) / h)
        scale = max(2.0, min(6000.0, scale))
        
        cx_w = min_x + w / 2.0
        cy_w = min_y + h / 2.0
        
        self.vp.scale = scale
        self.vp.offx = W / 2 - cx_w * scale
        self.vp.offy = H / 2 + cy_w * scale
        self.update()

    def save_state(self):
        # Truncate redo futures
        if self.history_index < len(self.history) - 1:
            self.history = self.history[:self.history_index + 1]
            
        # Clone current state
        state = {
            'lines': [obj.clone() for obj in self.lines],
            'selection_mode': getattr(self, "selection_mode", "chain"),
            'maintain_connectivity': getattr(self, "maintain_connectivity", True)
        }
        self.history.append(state)
        self.history_index += 1
        
        # Optional: limit history size
        if len(self.history) > 50:
            self.history.pop(0)
            self.history_index -= 1

    def undo(self):
        if self.history_index > 0:
            self.history_index -= 1
            state = self.history[self.history_index]
            self.lines = [obj.clone() for obj in state['lines']]
            self.selection_mode = state['selection_mode']
            self.maintain_connectivity = state['maintain_connectivity']
            self.selected_line = None
            self.drag_active = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Initialize viewport offset on first real resize so (0,0) is near bottom-left
        if self.vp.offy == 0.0 and self.height() > 100:
            self.vp.offx = 50.0
            self.vp.offy = self.height() - 50.0
            self.trim_step = 0
            self.trim_target = None
            self.trigger_lines_changed()
            self.update()

    def redo(self):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            state = self.history[self.history_index]
            self.lines = [obj.clone() for obj in state['lines']]
            self.selection_mode = state['selection_mode']
            self.maintain_connectivity = state['maintain_connectivity']
            self.selected_line = None
            self.drag_active = False
            self.trim_step = 0
            self.trim_target = None
            self.trigger_lines_changed()
            self.update()

    def resizeEvent(self, event):
        # Position Cancel button top-right
        self.btn_cancel.move(self.width() - self.btn_cancel.width() - 20, 20)
        super().resizeEvent(event)

    def cancel_operation(self):
        # Reset Line Tool
        self.drawing_line = False
        self.temp_line_start = None
        
        # Reset Trim Tool
        self.trim_step = 0
        self.trim_target = None
        self.trim_points = []
        
        # Hide self
        self.btn_cancel.hide()
        
        self.update()
        
    def check_cancel_visibility(self):
        # Show if in middle of operation
        show = False
        if self.tool_mode == "line" and self.drawing_line:
            show = True
        if self.tool_mode == "trim" and self.trim_step > 0:
            show = True
            
        self.btn_cancel.setVisible(show)

    def trigger_lines_changed(self):
        if self.on_lines_changed:
            self.on_lines_changed()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw Background
        painter.fillRect(self.rect(), self.bg_color)
        
        # Draw Grid & Axes
        if self.grid_enabled:
            # Grid color
            grid_pen = QPen(QColor(60, 60, 60))
            grid_pen.setWidth(1)
            painter.setPen(grid_pen)
            
            # Visible world bounds
            left, top = self.vp.screen_to_world(0, 0)
            right, bottom = self.vp.screen_to_world(self.width(), self.height())
            
            # Determine grid step based on scale (target ~50px spacing)
            target_pixel_spacing = 50.0
            min_step_world = target_pixel_spacing / self.vp.scale
            
            # Find closest power of 10 (or 2/5/10 splits)
            # Simple power of 10 floor: 10^floor(log10(min_step))
            exponent = math.floor(math.log10(min_step_world))
            step = 10**exponent
            
            # Adjust if too sparse (optional, e.g. if 1.1 -> 1.0 is fine, but if 8.0 -> 1.0 is too dense? 
            # actually min_step is the MINIMUM world units to get 50px. 
            # So if min_step is 40, we might get 10 (too dense) or 100 (good).
            # We want step >= min_step.
            if step < min_step_world:
                if step * 2 >= min_step_world:
                    step *= 2
                elif step * 5 >= min_step_world:
                    step *= 5
                else:
                    step *= 10
            
            self.current_grid_step = step
            
            # Draw Vertical Lines & Labels
            start_x = math.floor(left / step) * step
            x = start_x
            
            # Format string for labels
            # if step is integer, use no decimals. If float, use adequate decimals.
            decimals = 0
            if step < 1.0:
                decimals = abs(int(math.floor(math.log10(step))))
            fmt = f"{{:.{decimals}f}}ft"
            
            # Font for grid labels
            label_font = painter.font()
            label_font.setPointSize(8)
            painter.setFont(label_font)
            
            while x < right + step: 
                sx, _ = self.vp.world_to_screen(x, 0)
                painter.drawLine(int(sx), 0, int(sx), self.height())
                
                # Draw X Label
                # Position: near bottom, or near X axis if visible?
                # For basic clarity, let's put them at the bottom used-space
                # But X axis is at y=0.
                
                label_y = self.height() - 5
                # If X axis is visible, maybe put it there? 
                # _, sy0 = self.vp.world_to_screen(0, 0)
                # if 0 <= sy0 <= self.height(): label_y = int(sy0) + 15
                
                # Draw text
                # Avoid drawing 0 label twice if it overlaps Y axis label?
                if abs(x) > 1e-9:
                    painter.setPen(QColor(150, 150, 150))
                    painter.drawText(int(sx) + 2, label_y, fmt.format(x))
                    painter.setPen(grid_pen) # Reset pen
                
                x += step
                
            # Draw Horizontal Lines & Labels
            min_y = min(top, bottom)
            max_y = max(top, bottom)
            
            start_y = math.floor(min_y / step) * step
            y = start_y
            
            while y < max_y + step:
                _, sy = self.vp.world_to_screen(0, y)
                painter.drawLine(0, int(sy), self.width(), int(sy))
                
                # Draw Y Label
                label_x = 5
                # If Y axis is visible?
                # sx0, _ = self.vp.world_to_screen(0, 0)
                # if 0 <= sx0 <= self.width(): label_x = int(sx0) + 5
                
                if abs(y) > 1e-9:
                    painter.setPen(QColor(150, 150, 150))
                    painter.drawText(label_x, int(sy) - 2, fmt.format(y))
                    painter.setPen(grid_pen)

                y += step

            # Draw Axes (X=0, Y=0)
            axis_pen = QPen(QColor(100, 100, 100))
            axis_pen.setWidth(2)
            painter.setPen(axis_pen)
            
            # Y Axis (x=0)
            sx0, _ = self.vp.world_to_screen(0, 0)
            if -2e9 < sx0 < 2e9:
                painter.drawLine(int(sx0), 0, int(sx0), self.height())
            
            # X Axis (y=0)
            _, sy0 = self.vp.world_to_screen(0, 0)
            if -2e9 < sy0 < 2e9:
                painter.drawLine(0, int(sy0), self.width(), int(sy0))
        
        # Draw Lines
        pen = QPen(self.line_color)
        pen.setWidth(2)
        
        sel_pen = QPen(self.selected_color)
        sel_pen.setWidth(3)
        
        for line in self.lines:
            painter.setPen(sel_pen if line.selected else pen)
            if isinstance(line, Line):
                sx1, sy1 = self.vp.world_to_screen(line.x1, line.y1)
                sx2, sy2 = self.vp.world_to_screen(line.x2, line.y2)
                painter.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))
            elif isinstance(line, Spline):
                path = QPainterPath()
                sx1, sy1 = self.vp.world_to_screen(line.x1, line.y1)
                scx1, scy1 = self.vp.world_to_screen(line.cx1, line.cy1)
                scx2, scy2 = self.vp.world_to_screen(line.cx2, line.cy2)
                sx2, sy2 = self.vp.world_to_screen(line.x2, line.y2)
                path.moveTo(sx1, sy1)
                path.cubicTo(scx1, scy1, scx2, scy2, sx2, sy2)
                painter.drawPath(path)
                
        # Draw Temp Line or Spline
        if self.drawing_line:
            wx, wy = self.vp.screen_to_world(*self.current_mouse_pos)
            sx_snap, sy_snap = self.snap_controller.get_snap(wx, wy, drawing_line=True)
            tpen = QPen(self.temp_line_color)
            tpen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(tpen)
            
            if self.tool_mode == "line" and self.temp_line_start:
                wx1, wy1 = self.temp_line_start
                sx1, sy1 = self.vp.world_to_screen(wx1, wy1)
                dsx, dsy = self.vp.world_to_screen(sx_snap, sy_snap)
                painter.drawLine(int(sx1), int(sy1), int(dsx), int(dsy))
            elif self.tool_mode == "spline":
                pts = self.spline_points
                n = len(pts)
                if n > 0:
                    # Draw already set points
                    for i in range(n):
                        sx, sy = self.vp.world_to_screen(pts[i][0], pts[i][1])
                        painter.drawEllipse(int(sx-2), int(sy-2), 4, 4)
                    
                    # Preview the next segment
                    wx1, wy1 = pts[0]
                    sx1, sy1 = self.vp.world_to_screen(wx1, wy1)
                    dsx, dsy = self.vp.world_to_screen(sx_snap, sy_snap)
                    
                    if n == 1: # Preview CP1
                        painter.drawLine(int(sx1), int(sy1), int(dsx), int(dsy))
                    elif n == 2: # Preview CP2
                        scx1, scy1 = self.vp.world_to_screen(pts[1][0], pts[1][1])
                        path = QPainterPath()
                        path.moveTo(sx1, sy1)
                        # Quad for now? No, let's just draw lines to visualize
                        painter.drawLine(int(sx1), int(sy1), int(scx1), int(scy1))
                        painter.drawLine(int(scx1), int(scy1), int(dsx), int(dsy))
                    elif n == 3: # Preview End and Curve
                        scx1, scy1 = self.vp.world_to_screen(pts[1][0], pts[1][1])
                        scx2, scy2 = self.vp.world_to_screen(pts[2][0], pts[2][1])
                        path = QPainterPath()
                        path.moveTo(sx1, sy1)
                        path.cubicTo(scx1, scy1, scx2, scy2, dsx, dsy)
                        painter.drawPath(path)

        # Draw Vertices (if zoomed in AND enabled)
        # Threshold: scale > 5.0 (meaning 1 world unit is at least 5 pixels)
        if getattr(self, "show_vertices", True) and self.vp.scale > 5.0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 150))
            r = 3
            drawn_vertices = set()
            for obj in self.lines:
                p_list = []
                if isinstance(obj, Line):
                    p_list = [(obj.x1, obj.y1), (obj.x2, obj.y2)]
                elif isinstance(obj, Spline):
                    p_list = [(obj.x1, obj.y1), (obj.x2, obj.y2)]
                
                for px, py in p_list:
                    key = (round(px, 3), round(py, 3))
                    if key not in drawn_vertices:
                        sx, sy = self.vp.world_to_screen(px, py)
                        painter.drawEllipse(int(sx-r), int(sy-r), int(r*2), int(r*2))
                        drawn_vertices.add(key)

        # Draw Dimensions (for selected lines)
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        
        # Rebuild label rects each paint so hit-testing stays current
        self._length_label_rects = []
        
        for line in self.lines:
            if line.selected:
                # Calculate mid point
                mx = (line.x1 + line.x2) / 2
                my = (line.y1 + line.y2) / 2
                sx, sy = self.vp.world_to_screen(mx, my)
                
                # Calculate length
                length = math.hypot(line.x2 - line.x1, line.y2 - line.y1)
                text = f"{length:.2f}"
                
                # Draw background rect for text
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(text)
                th = fm.height()
                rx = int(sx - tw/2 - 2)
                ry = int(sy - th/2 - 1)
                rw = int(tw + 4)
                rh = int(th + 2)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 122, 204, 200))  # Blue tint = clickable hint
                painter.drawRect(rx, ry, rw, rh)
                
                # Draw text
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(int(sx - tw/2), int(sy + th/2 - 2), text)
                
                # Store rect for click detection
                self._length_label_rects.append((QRect(rx, ry, rw, rh), line))

        # Draw Snap Hints
        if self.snap_hint:
            kind, hx, hy = self.snap_hint
            sx, sy = self.vp.world_to_screen(hx, hy)
            
            painter.setPen(QPen(self.snap_marker_color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            
            if kind == "endpoint":
                s = 5
                painter.drawRect(int(sx-s), int(sy-s), int(s*2), int(s*2))
            elif kind == "line":
                s = 4
                painter.drawLine(int(sx-s), int(sy-s), int(sx+s), int(sy+s))
                painter.drawLine(int(sx-s), int(sy+s), int(sx+s), int(sy-s))
                
        # Draw Alignment Guides
        guide_pen = QPen(QColor(100, 255, 100))
        guide_pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(guide_pen)
        for gx1, gy1, gx2, gy2, gtype in self.alignment_guides:
             gsx1, gsy1 = self.vp.world_to_screen(gx1, gy1)
             gsx2, gsy2 = self.vp.world_to_screen(gx2, gy2)
             painter.drawLine(int(gsx1), int(gsy1), int(gsx2), int(gsy2))
             
        # Draw Trim Visuals
        if self.tool_mode == "trim":
            # Highlight target Line
            if self.trim_target and self.trim_step > 0:
                tpen = QPen(QColor("#FF00FF")) # Magenta for target
                tpen.setWidth(3)
                painter.setPen(tpen)
                ln = self.trim_target
                sx1, sy1 = self.vp.world_to_screen(ln.x1, ln.y1)
                sx2, sy2 = self.vp.world_to_screen(ln.x2, ln.y2)
                painter.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))
                
            # Draw Cut Markers (perpendicular dashed lines)
            marker_pen = QPen(QColor("#FF4444"))
            marker_pen.setWidth(2)
            marker_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(marker_pen)
            
            # Helper to draw marker at world pos
            def draw_marker(wx, wy, line_dir):
                # line_dir is (dx, dy) of the line
                # perpendicular: (-dy, dx)
                dx, dy = line_dir
                norm = math.hypot(dx, dy)
                if norm < 1e-9: return
                nx, ny = -dy/norm, dx/norm
                
                len_s = 10 # Screen pixels
                sx, sy = self.vp.world_to_screen(wx, wy)
                
                # We need screen-space normal... actually simpler to draw vertical/horizontal on screen?
                # or world space normal?
                # Let's do simple screen cross or X?
                # User asked for "dashed lines perpendicular".
                # Convert normal to screen vector (roughly, scaling ignores aspect)
                # Just use fixed screen length perpendicular to line screen vector
                
                # Screen vector of line
                slx1, sly1 = self.vp.world_to_screen(0,0)
                slx2, sly2 = self.vp.world_to_screen(dx, dy)
                sdx, sdy = slx2-slx1, sly2-sly1
                snorm = math.hypot(sdx, sdy)
                if snorm < 1e-9: return
                snx, sny = -sdy/snorm, sdx/snorm
                
                p1x = sx + snx * 15
                p1y = sy + sny * 15
                p2x = sx - snx * 15
                p2y = sy - sny * 15
                painter.drawLine(int(p1x), int(p1y), int(p2x), int(p2y))

            # 1. Existing points
            if self.trim_target:
                ldx = self.trim_target.x2 - self.trim_target.x1
                ldy = self.trim_target.y2 - self.trim_target.y1
                
                for px, py in self.trim_points:
                    draw_marker(px, py, (ldx, ldy))
                    
                # 2. Live cursor (if step > 0)
                if self.trim_step > 0:
                     wx, wy = self.vp.screen_to_world(*self.current_mouse_pos)
                     # Snap to line for visualization?
                     px, py, _ = self.trim_target.closest_point(wx, wy)
                     draw_marker(px, py, (ldx, ldy))
            
    def _pull_attached_vertices(self, ox, oy, new_pos, ignore_lines):
        # Find all objects not in ignore_list that share vertex (ox, oy)
        # and move that vertex to new_pos
        for obj in self.lines:
            if obj in ignore_lines:
                continue
            
            # Check P1
            if math.hypot(obj.x1 - ox, obj.y1 - oy) < 1e-9:
                obj.x1, obj.y1 = new_pos
            
            # Check P2
            if math.hypot(obj.x2 - ox, obj.y2 - oy) < 1e-9:
                obj.x2, obj.y2 = new_pos

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            # Delete selected lines
            old_count = len(self.lines)
            self.lines = [ln for ln in self.lines if not ln.selected]
            self.update()
            if len(self.lines) != old_count:
                self.trigger_lines_changed()

    def wheelEvent(self, event):
        # Zoom support
        factor = 1.1 if event.angleDelta().y() > 0 else 0.9
        # Zoom centered on mouse
        mouse_pos = event.position()
        self.vp.zoom_at(factor, mouse_pos.x(), mouse_pos.y())
        self.update()

    def select_line_by_index(self, index):
        # Deselect all
        for ln in self.lines:
            ln.selected = False
        
        # Select target
        if 0 <= index < len(self.lines):
            self.lines[index].selected = True
        
        self.update()

    def select_lines_by_indices(self, indices):
        # Deselect all
        for ln in self.lines:
            ln.selected = False
        
        # Select targets
        for idx in indices:
             if 0 <= idx < len(self.lines):
                 self.lines[idx].selected = True
        
        self.update()

    def _find_vertex_near(self, wx, wy):
        threshold = 0.15 # World units
        best = None
        best_d = 1e18
        for ln in self.lines:
            d1 = math.hypot(wx - ln.x1, wy - ln.y1)
            if d1 < best_d:
                best_d = d1
                best = (ln.x1, ln.y1)
            d2 = math.hypot(wx - ln.x2, wy - ln.y2)
            if d2 < best_d:
                best_d = d2
                best = (ln.x2, ln.y2)
        if best is not None and best_d < threshold:
            return best
        return None

    def _collect_vertex_refs(self, vx, vy):
        refs = []
        for obj in self.lines:
            if math.hypot(obj.x1 - vx, obj.y1 - vy) < 1e-6:
                refs.append((obj, "start"))
            if math.hypot(obj.x2 - vx, obj.y2 - vy) < 1e-6:
                refs.append((obj, "end"))
        return refs

    def find_connected_chain(self, start_line, visited=None):
        if visited is None:
            visited = set()
        
        visited.add(start_line)
        chain = [start_line]
        
        p1 = (start_line.x1, start_line.y1)
        p2 = (start_line.x2, start_line.y2)
        
        for neighbor in self.lines:
            if neighbor in visited:
                continue
            
            # Check connectivity (epsilon)
            np1 = (neighbor.x1, neighbor.y1)
            np2 = (neighbor.x2, neighbor.y2)
            
            connected = False
            tol = 1e-5
            if math.hypot(p1[0]-np1[0], p1[1]-np1[1]) < tol: connected = True
            elif math.hypot(p1[0]-np2[0], p1[1]-np2[1]) < tol: connected = True
            elif math.hypot(p2[0]-np1[0], p2[1]-np1[1]) < tol: connected = True
            elif math.hypot(p2[0]-np2[0], p2[1]-np2[1]) < tol: connected = True
            
            if connected:
                sub_chain = self.find_connected_chain(neighbor, visited)
                chain.extend(sub_chain)
                
        return chain

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.panning = True
            self.last_pan_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            
        elif event.button() == Qt.MouseButton.RightButton:
            # If in Line Mode, Right Click = Cancel / Finish Chain
            if self.tool_mode == "line":
                self.cancel_operation()
                return

            # Context Menu
            wx, wy = self.vp.screen_to_world(event.position().x(), event.position().y())
            
            # Check if we clicked a line
            hit_line = None
            best_d = 10.0 / self.vp.scale
            for ln in self.lines:
                d = ln.distance_to_point(wx, wy)
                if d < best_d:
                    best_d = d
                    hit_line = ln
            
            if hit_line:
                # If not selected, select it (and chain if default)
                if not hit_line.selected:
                    # Select logic same as left click
                    is_chain_mode = getattr(self, "selection_mode", "chain") == "chain"
                    if is_chain_mode:
                        chain = self.find_connected_chain(hit_line)
                        for l in chain: l.selected = True
                    else:
                        hit_line.selected = True
                    self.trigger_lines_changed()
                    self.update()
            
            # Show Menu if we have selection
            selected_count = sum(1 for l in self.lines if l.selected)
            if selected_count > 0:
                menu = QMenu(self)
                
                # Mode Toggle
                cur_mode = getattr(self, "selection_mode", "chain")
                
                # Edit Elements Action
                act_edit = QAction("Edit Elements (Sub-select)", self)
                act_edit.setCheckable(True)
                act_edit.setChecked(cur_mode == "element")
                act_edit.toggled.connect(lambda checked: self.set_selection_mode("element" if checked else "chain"))
                menu.addAction(act_edit)
                
                # Group / Ungroup
                act_group = QAction("Group Elements", self)
                act_group.triggered.connect(self.group_selection)
                menu.addAction(act_group)
                
                act_ungroup = QAction("Ungroup Elements", self)
                act_ungroup.triggered.connect(self.ungroup_selection)
                menu.addAction(act_ungroup)
                
                menu.addSeparator()
                
                act_del = QAction("Delete", self)
                act_del.triggered.connect(self.delete_selected)
                menu.addAction(act_del)
                
                menu.exec(event.globalPosition().toPoint())
            
        elif event.button() == Qt.MouseButton.LeftButton:
            wx, wy = self.vp.screen_to_world(event.position().x(), event.position().y())
            
            # --- Length label click detection (cursor mode only) ---
            if self.tool_mode == "cursor":
                sp = event.position().toPoint()
                for rect, ln in self._length_label_rects:
                    if rect.contains(sp):
                        self._edit_line_length(ln)
                        return
            
            if self.tool_mode == "trim":
                # Manual Trim Logic
                self.trim_line_manual(wx, wy)
                return
            elif self.tool_mode == "extend":
                self.extend_line_at(wx, wy)
                return
            
            if self.tool_mode == "spline":
                # Spline Tool: 4-click sequence
                sx_snap, sy_snap = self.snap_controller.get_snap(wx, wy, drawing_line=True)
                
                self.spline_points.append((sx_snap, sy_snap))
                self.drawing_line = True # Keep showing temp preview
                
                if len(self.spline_points) == 4:
                    # Final Point reached! Create the spline.
                    p1, cp1, cp2, p2 = self.spline_points
                    new_spline = Spline(p1[0], p1[1], cp1[0], cp1[1], cp2[0], cp2[1], p2[0], p2[1], self.line_color.name())
                    self.lines.append(new_spline)
                    self.save_state()
                    self.trigger_lines_changed()
                    
                    # Reset
                    self.spline_points = []
                    self.drawing_line = False
                self.update()
                return

            if self.tool_mode == "line":
                # Snap logic first
                sx_snap, sy_snap = self.snap_controller.get_snap(wx, wy, self.drawing_line)
                
                if self.drawing_line and self.temp_line_start:
                    # We are FINISHING a line
                    start_x, start_y = self.temp_line_start
                    
                    # Apply Constraints
                    mw = self.window()
                    
                    if mw: 
                        dx = sx_snap - start_x
                        dy = sy_snap - start_y
                        
                        # 1. Angle Constraint (Direction)
                        if getattr(mw, "chk_angle", None) and mw.chk_angle.isChecked():
                             target_rad = math.radians(mw.spin_angle.value())
                             ux = math.cos(target_rad)
                             uy = math.sin(target_rad)
                             proj = dx*ux + dy*uy
                             dx = proj * ux
                             dy = proj * uy
                             
                        # 2. Length Constraint (Magnitude)
                        if mw.chk_len.isChecked():
                            target_len = mw.spin_len.value()
                            current_len = math.hypot(dx, dy)
                            if current_len < 1e-9:
                                if mw.chk_angle.isChecked():
                                    target_rad = math.radians(mw.spin_angle.value())
                                    dx = target_len * math.cos(target_rad)
                                    dy = target_len * math.sin(target_rad)
                                else:
                                    pass
                            else:
                                scale = target_len / current_len
                                dx *= scale
                                dy *= scale
                                
                        sx_snap = start_x + dx
                        sy_snap = start_y + dy

                    # Create Line
                    new_line = Line(start_x, start_y, sx_snap, sy_snap)
                    self.lines.append(new_line)
                    
                    # Chain Drawing: Start next line at end of this one
                    self.drawing_line = True
                    self.temp_line_start = (sx_snap, sy_snap)
                    self.trigger_lines_changed()
                    
                else:
                    # We are STARTING a line
                    self.drawing_line = True
                    self.temp_line_start = (sx_snap, sy_snap)
                
                self.save_state()
                self.check_cancel_visibility()
                self.update()
            
            elif self.tool_mode == "cursor":
                is_chain_mode = getattr(self, "selection_mode", "chain") == "chain"
                
                # 1. Check for vertex click (Only in Sub-select / Element mode!)
                if not is_chain_mode:
                    hit_vertex = self._find_vertex_near(wx, wy)
                    if hit_vertex:
                        vx, vy = hit_vertex
                        refs = self._collect_vertex_refs(vx, vy)
                        if refs:
                            self.drag_active = True
                            self.drag_mode = "vertex"
                            self.drag_refs = refs
                            self.snap_hint = ("endpoint", vx, vy)
                            return
                        
                # 2. Check for line body click
                clicked_line = None
                best_d = 1e18
                threshold = 10.0 / self.vp.scale # Screen pixels converted to world
                
                for ln in self.lines:
                    d = ln.distance_to_point(wx, wy)
                    if d < best_d:
                        best_d = d
                        clicked_line = ln
                
                if clicked_line and best_d < threshold:
                    # Check for Shift modifier
                    modifiers = QApplication.keyboardModifiers()
                    is_multi = (modifiers & Qt.KeyboardModifier.ShiftModifier)
                    
                    if is_chain_mode:
                        # Chain Logic
                        chain = self.find_connected_chain(clicked_line)
                        if is_multi:
                            # Toggle Chain
                            any_selected = any(l.selected for l in chain)
                            new_state = not any_selected
                            for l in chain: l.selected = new_state
                        else:
                            # Exclusive Chain
                            for l in self.lines: l.selected = False
                            for l in chain: l.selected = True
                    else:
                        # Element Logic
                        if is_multi:
                            clicked_line.selected = not clicked_line.selected
                        else:
                            for l in self.lines: l.selected = False
                            clicked_line.selected = True
                    
                    self.selected_line = clicked_line 
                    
                    # Expand selection to include all group members
                    # (Only do this in chain mode; in element mode we specifically want sub-select)
                    if is_chain_mode:
                        self._expand_selection_to_groups()
                    
                    # Start dragging body if it is now selected
                    # Note: We need to handle dragging ALL selected lines
                    if clicked_line.selected: # or any selected
                        self.drag_active = True
                        self.drag_mode = "body"
                        self.drag_line = clicked_line
                        self.drag_start_world = (wx, wy)
                        
                        # Store initial coords for ALL selected lines/splines
                        self.drag_refs = []
                        for l in self.lines:
                            if l.selected:
                                if isinstance(l, Line):
                                    self.drag_refs.append((l, l.x1, l.y1, l.x2, l.y2))
                                elif isinstance(l, Spline):
                                    self.drag_refs.append((l, l.x1, l.y1, l.x2, l.y2, l.cx1, l.cy1, l.cx2, l.cy2))
                        
                        # Pre-compute attached neighbors for connected dragging
                        self.drag_neighbors = []
                        maintain = getattr(self, "maintain_connectivity", True)
                        if maintain:
                            selected_lines = {r[0] for r in self.drag_refs}
                            for r in self.drag_refs:
                                l, ox1, oy1, ox2, oy2 = r[0], r[1], r[2], r[3], r[4]
                                for nl in self.lines:
                                    if nl in selected_lines:
                                        continue
                                    if math.hypot(nl.x1 - ox1, nl.y1 - oy1) < 1e-4:
                                        self.drag_neighbors.append((nl, "start", ox1, oy1))
                                    elif math.hypot(nl.x2 - ox1, nl.y2 - oy1) < 1e-4:
                                        self.drag_neighbors.append((nl, "end", ox1, oy1))
                                    
                                    if math.hypot(nl.x1 - ox2, nl.y1 - oy2) < 1e-4:
                                        self.drag_neighbors.append((nl, "start", ox2, oy2))
                                    elif math.hypot(nl.x2 - ox2, nl.y2 - oy2) < 1e-4:
                                        self.drag_neighbors.append((nl, "end", ox2, oy2))

                    
                    self.trigger_lines_changed()
                    self.update()
                else:
                    # Clicked on empty space -> Pan & Deselect All
                    # Only deselect if not holding shift? 
                    if not (QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier):
                        for ln in self.lines:
                            ln.selected = False
                        self.trigger_lines_changed()
                        
                    self.panning = True
                    self.last_pan_pos = event.position()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.update()
                    
                    self.update()
        
    def mouseMoveEvent(self, event):
        self.current_mouse_pos = (event.position().x(), event.position().y())
        
        # Pan handling (Middle button OR Left button pan mode)
        if self.panning and self.last_pan_pos:
            delta = event.position() - self.last_pan_pos
            self.vp.offx += delta.x()
            self.vp.offy += delta.y()
            self.last_pan_pos = event.position()
            self.update()
            return

        wx, wy = self.vp.screen_to_world(event.position().x(), event.position().y())

        # Handle Dragging
        if self.drag_active:
            if self.drag_mode == "vertex":
                # Snap the vertex being dragged
                sx, sy = self.snap_controller.get_snap(wx, wy)
                
                # Update all connected lines
                for ln, end in self.drag_refs:
                    if end == "start":
                        ln.x1, ln.y1 = sx, sy
                    else:
                        ln.x2, ln.y2 = sx, sy
                self.update()
                return
            
            elif self.drag_mode == "body":
                # Move line body
                dx = wx - self.drag_start_world[0]
                dy = wy - self.drag_start_world[1]
                
                # We need to move selected lines.
                # BUT, if in "connected element" mode, we must also update neighbors that share vertices
                # but are NOT selected.
                
                # 1. Move selected lines/splines
                for r in self.drag_refs:
                    l = r[0]
                    l.x1 = r[1] + dx
                    l.y1 = r[2] + dy
                    l.x2 = r[3] + dx
                    l.y2 = r[4] + dy
                    if isinstance(l, Spline):
                        l.cx1 = r[5] + dx
                        l.cy1 = r[6] + dy
                        l.cx2 = r[7] + dx
                        l.cy2 = r[8] + dy
                
                # 2. Pull attached vertices on non-selected neighbours.
                for nl, end_type, nx, ny in self.drag_neighbors:
                    if end_type == "start":
                        nl.x1 = nx + dx
                        nl.y1 = ny + dy
                    else:
                        nl.x2 = nx + dx
                        nl.y2 = ny + dy

                self.update()
                return

        if self.drawing_line:
            # Update snap state logic handled inside paintEvent for temp line? 
            # No, update state here for feedback
            self.snap_controller.get_snap(wx, wy, drawing_line=True)
            self.update()
            return

        # Passive snap update
        if self.snap_enabled and self.tool_mode in ["line", "spline"]:
             self.snap_controller.get_snap(wx, wy, drawing_line=self.drawing_line)
        else:
             self.snap_hint = None
             self.alignment_guides = []
        
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            if self.panning:
                self.panning = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                
            if self.drag_active:
                self.drag_active = False
                self.drag_mode = None
                self.drag_refs = []
                self.drag_line = None
                self.save_state()
                self.update()

    def trim_line_manual(self, wx, wy):
        # Step 0: Select Line
        if self.trim_step == 0:
            # Find line similar to selection logic
            best_line = None
            best_d = 0.5
            for ln in self.lines:
                d = ln.distance_to_point(wx, wy)
                if d < best_d:
                    best_d = d
                    best_line = ln
            
            if best_line:
                self.trim_target = best_line
                self.trim_step = 1
                self.trim_points = []
                # Auto-highlight?
                # We can reuse selection or just visually feedback
                self.update()
                self.check_cancel_visibility()
            return

        # Step 1 & 2: Click Points on Line
        if self.trim_step in [1, 2]:
            if not self.trim_target or self.trim_target not in self.lines:
                # Target lost (deleted?), reset
                self.trim_step = 0
                self.trim_target = None
                self.check_cancel_visibility()
                return

            # Project click onto target line to ensure it is ON the line
            px, py, t = self.trim_target.closest_point(wx, wy)
            
            self.trim_points.append((px, py))
            
            if self.trim_step == 1:
                self.trim_step = 2
                self.update()
            elif self.trim_step == 2:
                # Perform Cut
                p1 = self.trim_points[0]
                p2 = self.trim_points[1]
                self.perform_trim_segment(self.trim_target, p1, p2)
                
                # Reset or continue? Usually one op at a time.
                # Reset to allow selecting another line? Or same line?
                # User might want to do multiple cuts on same line?
                # But line object changes Identity after split.
                self.trim_step = 0
                self.trim_target = None
                self.trim_points = []
                self.update()
            self.check_cancel_visibility()

    def perform_trim_segment(self, line, p1, p2):
        # Calculate t params
        _, _, t1 = line.closest_point(p1[0], p1[1])
        _, _, t2 = line.closest_point(p2[0], p2[1])
        
        if t1 > t2:
            t1, t2 = t2, t1
            
        # We need to Keep [0, t1] and [t2, 1]
        # Create new lines
        new_lines = []
        
        # Segment 1: Start to t1
        if t1 > 1e-6:
            lx = line.x1 + t1 * (line.x2 - line.x1)
            ly = line.y1 + t1 * (line.y2 - line.y1)
            new_lines.append(Line(line.x1, line.y1, lx, ly, line.color))
            
        # Segment 2: t2 to End
        if t2 < 1.0 - 1e-6:
            rx = line.x1 + t2 * (line.x2 - line.x1)
            ry = line.y1 + t2 * (line.y2 - line.y1)
            new_lines.append(Line(rx, ry, line.x2, line.y2, line.color))
            
        self.lines.remove(line)
        self.lines.extend(new_lines)
        self.save_state()
        self.trigger_lines_changed()

    def _edit_line_length(self, ln):
        """Open a dialog to edit the length of *ln*. Optionally scales entire drawing."""
        old_len = math.hypot(ln.x2 - ln.x1, ln.y2 - ln.y1)
        if old_len < 1e-9:
            return
        new_len, ok = QInputDialog.getDouble(
            self, "Edit Length", "Line length:",
            old_len, 0.001, 1e9, 4
        )
        if not ok or abs(new_len - old_len) < 1e-9:
            return
            
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Scale Entire Drawing?",
            "Would you like to scale the entire CAD drawing proportionally to match this new dimension?\n\n"
            "Yes: Scales all lines globally (calibrates drawing).\n"
            "No: Resizes only this specific line.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )

        ratio = new_len / old_len

        if reply == QMessageBox.StandardButton.Yes:
            cx = (ln.x1 + ln.x2) / 2.0
            cy = (ln.y1 + ln.y2) / 2.0
            from cad_core import Spline
            for obj in self.lines:
                if isinstance(obj, Spline):
                    obj.x1 = cx + (obj.x1 - cx) * ratio
                    obj.y1 = cy + (obj.y1 - cy) * ratio
                    obj.cx1 = cx + (obj.cx1 - cx) * ratio
                    obj.cy1 = cy + (obj.cy1 - cy) * ratio
                    obj.cx2 = cx + (obj.cx2 - cx) * ratio
                    obj.cy2 = cy + (obj.cy2 - cy) * ratio
                    obj.x2 = cx + (obj.x2 - cx) * ratio
                    obj.y2 = cy + (obj.y2 - cy) * ratio
                else:
                    obj.x1 = cx + (obj.x1 - cx) * ratio
                    obj.y1 = cy + (obj.y1 - cy) * ratio
                    obj.x2 = cx + (obj.x2 - cx) * ratio
                    obj.y2 = cy + (obj.y2 - cy) * ratio
        else:
            # Resize from midpoint (direction preserved)
            mx = (ln.x1 + ln.x2) / 2
            my = (ln.y1 + ln.y2) / 2
            ux = (ln.x2 - ln.x1) / old_len
            uy = (ln.y2 - ln.y1) / old_len
            half = new_len / 2.0
            ln.x1, ln.y1 = mx - ux * half, my - uy * half
            ln.x2, ln.y2 = mx + ux * half, my + uy * half

        self.save_state()
        self.trigger_lines_changed()
        self.update()

    def extend_line_at(self, wx, wy):
        # 1. Find clicked line (zoom-aware screen-pixel threshold)
        clicked_line = None
        best_d = 10.0 / self.vp.scale  # 10 screen pixels, independent of zoom
        for ln in self.lines:
            d = ln.distance_to_point(wx, wy)
            if d < best_d:
                best_d = d
                clicked_line = ln
        
        if not clicked_line:
            return
            
        # 2. Determine which end to extend
        d1 = math.hypot(wx - clicked_line.x1, wy - clicked_line.y1)
        d2 = math.hypot(wx - clicked_line.x2, wy - clicked_line.y2)
        
        extend_start = (d1 < d2) # True if extending from Start (x1, y1)
        
        # Ray definition
        if extend_start:
            # Ray origin: x1, y1. Dir: (x1-x2, y1-y2)
            rx, ry = clicked_line.x1, clicked_line.y1
            dx, dy = clicked_line.x1 - clicked_line.x2, clicked_line.y1 - clicked_line.y2
        else:
            # Ray origin: x2, y2. Dir: (x2-x1, y2-y1)
            rx, ry = clicked_line.x2, clicked_line.y2
            dx, dy = clicked_line.x2 - clicked_line.x1, clicked_line.y2 - clicked_line.y1
            
        norm = math.hypot(dx, dy)
        if norm < 1e-9: return
        dx /= norm
        dy /= norm
        
        # Cast ray against all other lines
        # We model the ray as a very long segment
        huge_dist = 10000.0
        ray_end_x = rx + dx * huge_dist
        ray_end_y = ry + dy * huge_dist
        
        best_dist = huge_dist
        best_int = None
        
        # Temporary line for intersection check
        ray_line = Line(rx, ry, ray_end_x, ray_end_y) # Dummy for helper, or just use tuple math
        
        p1 = (rx, ry)
        p2 = (ray_end_x, ray_end_y)
        
        for other in self.lines:
            if other is clicked_line: continue
            
            p3 = (other.x1, other.y1)
            p4 = (other.x2, other.y2)
            
            res = geometry.line_intersection(p1, p2, p3, p4)
            if res:
                ix, iy, t, u = res
                # Check if intersection is valid on 'other' segment (0 <= u <= 1)
                # And valid on ray (t > 0, we don't want to extend backwards or self-intersect at 0)
                if -1e-9 <= u <= 1.0 + 1e-9 and t > 1e-6:
                    dist = math.hypot(ix - rx, iy - ry)
                    if dist < best_dist:
                        best_dist = dist
                        best_int = (ix, iy)
        
        if best_int:
            # Update endpoint
            if extend_start:
                clicked_line.x1, clicked_line.y1 = best_int
            else:
                clicked_line.x2, clicked_line.y2 = best_int
            
            self.save_state()
            self.trigger_lines_changed()
            self.update()

    def set_selection_mode(self, mode):
        self.selection_mode = mode
        self.maintain_connectivity = True # Reset on mode switch logic? or keep? 
        # Usually checking "Edit Elements" implies we WANT connectivity logic by default.
        # "Separate" is the special case.
        
        # If switching to chain, maybe expand current selection to chains?
        if mode == "chain":
            new_selection = set()
            for l in self.lines:
                if l.selected:
                    chain = self.find_connected_chain(l)
                    new_selection.update(chain)
            for l in new_selection:
                l.selected = True
        self.trigger_lines_changed()
        self.update()

    def group_selection(self):
        """Assign a shared group_id to all currently selected lines."""
        selected = [l for l in self.lines if l.selected]
        if len(selected) < 2:
            return  # Need at least 2 lines to group
        
        gid = self.next_group_id
        self.next_group_id += 1
        
        for l in selected:
            l.group_id = gid
            
        # Optional: Heal vertices that are visually touching but microscopically apart
        # (For example, if they were previously ungrouped and 'drifted').
        # We snap any vertices within 0.1 world units of each other to identical coordinates
        # so that Sub-select connectivity logic (which uses a strict 1e-4 tolerance) will work.
        HEAL_TOL = 0.1
        for i in range(len(selected)):
            l1 = selected[i]
            for j in range(i + 1, len(selected)):
                l2 = selected[j]
                
                # Check all 4 point combinations
                if math.hypot(l1.x1 - l2.x1, l1.y1 - l2.y1) < HEAL_TOL:
                    l2.x1, l2.y1 = l1.x1, l1.y1
                if math.hypot(l1.x1 - l2.x2, l1.y1 - l2.y2) < HEAL_TOL:
                    l2.x2, l2.y2 = l1.x1, l1.y1
                    
                if math.hypot(l1.x2 - l2.x1, l1.y2 - l2.y1) < HEAL_TOL:
                    l2.x1, l2.y1 = l1.x2, l1.y2
                if math.hypot(l1.x2 - l2.x2, l1.y2 - l2.y2) < HEAL_TOL:
                    l2.x2, l2.y2 = l1.x2, l1.y2
        
        self.save_state()
        self.trigger_lines_changed()
        self.update()

    def ungroup_selection(self):
        """Remove group_id from all groups that have at least one line selected."""
        groups_to_remove = set()
        for l in self.lines:
            if l.selected and l.group_id is not None:
                groups_to_remove.add(l.group_id)
                
        for l in self.lines:
            if l.group_id in groups_to_remove:
                l.group_id = None
                
        # To break physical chains (where lines share exact vertices), we must
        # imperceptibly offset the selected lines' vertices so they fail the 1e-4 tolerance.
        TOL = 1e-4
        DRIFT = 2e-4  # Enough to break the 1e-4 tolerance without being visible
        
        selected_lines = [l for l in self.lines if l.selected]
        
        # We process by index so we can apply drift deterministically 
        # (e.g., only one line in a connected pair moves, or they move opposite ways)
        for i in range(len(selected_lines)):
            l = selected_lines[i]
            for j in range(len(self.lines)):
                neighbor = self.lines[j]
                if l is neighbor:
                    continue
                
                # To prevent both lines moving together if both are selected,
                # we only apply drift if our line's index in self.lines is < neighbor's index
                l_idx = self.lines.index(l)
                if l_idx >= j:
                    continue
                
                # Check start point
                if math.hypot(l.x1 - neighbor.x1, l.y1 - neighbor.y1) < TOL:
                    l.x1 += DRIFT; l.y1 += DRIFT
                elif math.hypot(l.x1 - neighbor.x2, l.y1 - neighbor.y2) < TOL:
                    l.x1 += DRIFT; l.y1 += DRIFT
                    
                # Check end point
                if math.hypot(l.x2 - neighbor.x1, l.y2 - neighbor.y1) < TOL:
                    l.x2 += DRIFT; l.y2 += DRIFT
                elif math.hypot(l.x2 - neighbor.x2, l.y2 - neighbor.y2) < TOL:
                    l.x2 += DRIFT; l.y2 += DRIFT
                
        self.save_state()
        self.trigger_lines_changed()
        self.update()

    def _expand_selection_to_groups(self):
        """Expand current selection to include all members of any group
        that has at least one selected member."""
        group_ids = set()
        for l in self.lines:
            if l.selected and l.group_id is not None:
                group_ids.add(l.group_id)
        
        if group_ids:
            for l in self.lines:
                if l.group_id in group_ids:
                    l.selected = True

    def keyPressEvent(self, event):
        modifiers = QApplication.keyboardModifiers()
        is_ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier) or \
                  bool(modifiers & Qt.KeyboardModifier.MetaModifier) # Mac Cmd support
        is_shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if is_ctrl:
            if event.key() == Qt.Key.Key_Z:
                if is_shift:
                    self.redo()
                else:
                    self.undo()
                return
            elif event.key() == Qt.Key.Key_Y:
                self.redo()
                return

        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self.delete_selected()
        elif event.key() == Qt.Key.Key_Escape:
            self.cancel_operation()
            # Also clear selection
            for l in self.lines: l.selected = False
            self.update()

    def delete_selected(self):
        # Remove lines
        self.lines = [l for l in self.lines if not l.selected]
        
        # Clear states
        self.selected_line = None
        self.drag_active = False
        self.save_state()
        self.trigger_lines_changed()
        self.update()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Solid-CAD Prototype (PyQt6)")
        self.resize(1200, 800)
        
        # Stacked Widget (Page Manager)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        # --- Page 1: Home Screen ---
        self.home_screen = HomeScreen()
        self.stack.addWidget(self.home_screen)
        
        # Connect Home Screen buttons
        self.home_screen.btn_new_plan.clicked.connect(self.go_to_cad)
        self.home_screen.btn_anchor_mapper.clicked.connect(self.open_anchor_mapper)
        self.home_screen.btn_rtls_dashboard.clicked.connect(self.open_rtls_dashboard)

        workspace_items = [
            ("cad", "Launch 2DLCAD"),
            ("anchor_mapper", "Anchor Mapper"),
            ("rtls_dashboard", "RTLS Dashboard"),
        ]
        
        # --- Page 2: CAD Interface ---
        self.cad_container = QWidget()
        cad_layout = QVBoxLayout(self.cad_container) # Vertical Layout for Ribbon + Canvas
        cad_layout.setContentsMargins(0, 0, 0, 0)
        cad_layout.setSpacing(0)
        
        # Initialize canvas early so toolbar can connect to it
        self.cad_canvas = CADWidget()
        self.cad_canvas.on_lines_changed = self.sync_feature_tree
        
        # Top Ribbon
        ribbon = QFrame()
        ribbon.setFixedHeight(60)
        ribbon.setStyleSheet("background-color: #2D2D30; border-bottom: 1px solid #3E3E42;")
        ribbon_layout = QHBoxLayout(ribbon)
        ribbon_layout.setContentsMargins(15, 5, 15, 5)
        ribbon_layout.setSpacing(15)
        
        # 1. Back Home Button
        btn_home = QPushButton("🏠") 
        btn_home.setFixedSize(40, 40)
        btn_home.setToolTip("Back to Home")
        btn_home.setStyleSheet("""
            QPushButton { background-color: #3C3C3C; border: none; border-radius: 4px; color: white; font-size: 18px; }
            QPushButton:hover { background-color: #505050; }
        """)
        btn_home.clicked.connect(self.go_to_home)
        ribbon_layout.addWidget(btn_home)
        
        # Vertical Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #555;")
        ribbon_layout.addWidget(sep1)
        
        # 2. Tools Label
        lbl = QLabel("TOOLS:")
        lbl.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        ribbon_layout.addWidget(lbl)
        
        # 3. Tool Buttons (Horizontal)
        self.btn_cursor = QPushButton("Cursor")
        self.btn_cursor.setFixedSize(80, 40)
        self.btn_cursor.clicked.connect(lambda: self.set_tool("cursor"))
        self.style_tool_btn_ribbon(self.btn_cursor, active=True)
        ribbon_layout.addWidget(self.btn_cursor)
        
        # Line Tools Group (Composite Widget)
        # Container to hold them together
        self.line_group_container = QWidget()
        self.line_group_container.setFixedSize(115, 40) # reduced from 130
        lg_layout = QHBoxLayout(self.line_group_container)
        lg_layout.setContentsMargins(0, 0, 0, 0)
        lg_layout.setSpacing(0)
        
        # 1. Main Action Button
        self.btn_line_tool = QPushButton("Line")
        self.btn_line_tool.setFixedSize(100, 40)
        self.btn_line_tool.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_line_tool.clicked.connect(lambda: self.trigger_current_line_tool())
        
        # 2. Arrow Button (Menu)
        self.btn_line_arrow = QToolButton()
        self.btn_line_arrow.setFixedSize(15, 40) # Half size (30 -> 15)
        self.btn_line_arrow.setArrowType(Qt.ArrowType.DownArrow)
        self.btn_line_arrow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_line_arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Menu
        line_menu = QMenu(self.btn_line_arrow)
        self.line_actions = QActionGroup(self)
        self.line_actions.setExclusive(True)
        
        # Action: Line
        self.act_line = QAction("Line", self)
        self.act_line.setCheckable(True)
        self.act_line.setChecked(True)
        self.act_line.triggered.connect(lambda: self.set_tool("line"))
        self.line_actions.addAction(self.act_line)
        line_menu.addAction(self.act_line)
        
        # Action: Trim
        self.act_trim = QAction("Trim", self)
        self.act_trim.setCheckable(True)
        self.act_trim.triggered.connect(lambda: self.set_tool("trim"))
        self.line_actions.addAction(self.act_trim)
        line_menu.addAction(self.act_trim)
        
        # Action: Extend
        self.act_extend = QAction("Extend", self)
        self.act_extend.setCheckable(True)
        self.act_extend.triggered.connect(lambda: self.set_tool("extend"))
        self.line_actions.addAction(self.act_extend)
        line_menu.addAction(self.act_extend)
        
        # Action: Spline
        self.act_spline = QAction("Spline", self)
        self.act_spline.setCheckable(True)
        self.act_spline.triggered.connect(lambda: self.set_tool("spline"))
        self.line_actions.addAction(self.act_spline)
        line_menu.addAction(self.act_spline)
        
        self.btn_line_arrow.setMenu(line_menu)
        
        # Add to layout
        lg_layout.addWidget(self.btn_line_tool)
        lg_layout.addWidget(self.btn_line_arrow)
        
        ribbon_layout.addWidget(self.line_group_container)
        
        # Initial styling call
        self.style_line_group_custom(active=False)
        
        # Vertical Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #555;")
        ribbon_layout.addWidget(sep2)
        
        # Snap Toggle
        self.chk_snap = QCheckBox("Snap")
        self.chk_snap.setChecked(True)
        self.chk_snap.setStyleSheet("color: white; margin-right: 10px;")
        self.chk_snap.toggled.connect(self.toggle_snap)
        ribbon_layout.addWidget(self.chk_snap)
        
        # Grid Snap Toggle
        self.chk_grid_snap = QCheckBox("Grid Snap")
        self.chk_grid_snap.setChecked(False)
        self.chk_grid_snap.setStyleSheet("color: white; margin-right: 10px;")
        self.chk_grid_snap.toggled.connect(self.toggle_grid_snap)
        ribbon_layout.addWidget(self.chk_grid_snap)

        # 3. Tool Buttons (Horizontal)e
        self.chk_grid = QCheckBox("Grid")
        self.chk_grid.setChecked(True)
        self.chk_grid.setStyleSheet("""
            QCheckBox { color: white; spacing: 5px; }
            QCheckBox::indicator { width: 18px; height: 18px; }
        """)
        self.chk_grid.toggled.connect(self.toggle_grid)
        ribbon_layout.addWidget(self.chk_grid)
        
        # Endpoints Toggle
        self.chk_vertices = QCheckBox("Endpoints")
        self.chk_vertices.setChecked(True)
        self.chk_vertices.setStyleSheet("color: white; margin-right: 10px;")
        self.chk_vertices.toggled.connect(self.toggle_vertices)
        ribbon_layout.addWidget(self.chk_vertices)
        
        
        # Vertical Separator
        sep_import = QFrame()
        sep_import.setFrameShape(QFrame.Shape.VLine)
        sep_import.setStyleSheet("color: #555;")
        ribbon_layout.addWidget(sep_import)

        # Import Button
        btn_import = QPushButton("📂 Import")
        btn_import.setFixedSize(90, 40)
        btn_import.setToolTip("Import PDF file")
        btn_import.setStyleSheet("""
            QPushButton {
                background-color: #3C3C3C;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #505050; }
        """)
        btn_import.clicked.connect(self.import_file)
        ribbon_layout.addWidget(btn_import)

        # Fit View Button
        self.btn_fit = QPushButton("🔍 Fit View")
        self.btn_fit.setFixedSize(90, 40)
        self.btn_fit.setToolTip("Fit all geometry into the view")
        self.btn_fit.setStyleSheet("""
            QPushButton { background-color: #3C3C3C; color: white; border: none; border-radius: 4px; font-size: 12px; }
            QPushButton:hover { background-color: #505050; }
        """)
        self.btn_fit.clicked.connect(self.cad_canvas.fit_in_view)
        ribbon_layout.addWidget(self.btn_fit)

        # Save SVG Button
        btn_save = QPushButton("💾 Save SVG")
        btn_save.setFixedSize(90, 40)
        btn_save.setToolTip("Save CAD model as SVG")
        btn_save.setStyleSheet("""
            QPushButton { background-color: #3C3C3C; color: white; border: none; border-radius: 4px; font-size: 12px; }
            QPushButton:hover { background-color: #505050; }
        """)
        btn_save.clicked.connect(self.save_as_svg)
        ribbon_layout.addWidget(btn_save)

        # Save PDF Button
        btn_save_pdf = QPushButton("📄 Save PDF")
        btn_save_pdf.setFixedSize(90, 40)
        btn_save_pdf.setToolTip("Save CAD model as a high-res vector PDF")
        btn_save_pdf.setStyleSheet("""
            QPushButton { background-color: #3C3C3C; color: white; border: none; border-radius: 4px; font-size: 12px; }
            QPushButton:hover { background-color: #505050; }
        """)
        btn_save_pdf.clicked.connect(self.save_as_pdf)
        ribbon_layout.addWidget(btn_save_pdf)

        ribbon_layout.addStretch()
        
        # Constraints Group (Right aligned)
        # Length
        self.chk_len = QCheckBox("L:")
        self.chk_len.setStyleSheet("color: #DDD;")
        ribbon_layout.addWidget(self.chk_len)
        
        self.spin_len = QDoubleSpinBox()
        self.spin_len.setRange(0, 10000)
        self.spin_len.setSuffix(" ft")
        self.spin_len.setFixedWidth(80)
        self.spin_len.setStyleSheet("background-color: #333; color: white; border: 1px solid #555;")
        self.spin_len.setEnabled(False)
        ribbon_layout.addWidget(self.spin_len)
        
        self.chk_len.toggled.connect(self.spin_len.setEnabled)
        
        # Angle
        self.chk_angle = QCheckBox("A:")
        self.chk_angle.setStyleSheet("color: #DDD; margin-left: 10px;")
        ribbon_layout.addWidget(self.chk_angle)
        
        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(-360, 360)
        self.spin_angle.setSuffix(" °")
        self.spin_angle.setFixedWidth(70)
        self.spin_angle.setStyleSheet("background-color: #333; color: white; border: 1px solid #555;")
        self.spin_angle.setEnabled(False)
        ribbon_layout.addWidget(self.spin_angle)
        
        self.chk_angle.toggled.connect(self.spin_angle.setEnabled)
        
        # Spacer before canvas
        cad_layout.addWidget(ribbon)
        
        # Center Canvas
        cad_layout.addWidget(self.cad_canvas)
        
        self.stack.addWidget(self.cad_container)
        self.cad_switcher = WorkspaceSwitcher(
            self.cad_container,
            workspace_items,
            current_key="cad",
            top_offset=60,
        )
        self.cad_switcher.workspace_requested.connect(self._open_workspace_from_key)
        
        # --- Page 3: Anchor Mapper ---
        self.anchor_mapper_container = RTLSDashboard(app_mode=RTLSDashboard.MODE_ANCHOR_MAPPER)
        self.anchor_mapper_container.go_home.connect(self.go_to_home)
        self.anchor_mapper_container.workspace_requested.connect(self._open_workspace_from_key)
        self.stack.addWidget(self.anchor_mapper_container)

        # --- Page 4: RTLS Dashboard ---
        self.rtls_dashboard_container = RTLSDashboard(app_mode=RTLSDashboard.MODE_RTLS)
        self.rtls_dashboard_container.go_home.connect(self.go_to_home)
        self.rtls_dashboard_container.workspace_requested.connect(self._open_workspace_from_key)
        self.stack.addWidget(self.rtls_dashboard_container)
        
        # --- Dockable Feature Tree ---
        self.dock_tree = QDockWidget("Feature Manager", self)
        self.dock_tree.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.dock_tree.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Features"])
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background-color: #252526;
                color: #D4D4D4;
                border: 1px solid #3E3E42;
            }
            QTreeWidget::item:hover {
                background-color: #3E3E42;
            }
            QTreeWidget::item:selected {
                background-color: #094771;
            }
        """)
        self.dock_tree.setWidget(self.tree_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock_tree)
        
        # Connect Tree Selection
        self.tree_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_widget.itemSelectionChanged.connect(self.on_tree_selection_changed)
        
        self.dock_tree.hide()
        self._sync_workspace_switchers("cad")

    def go_to_cad(self):
        self.stack.setCurrentWidget(self.cad_container)
        self.dock_tree.show()
        self._sync_workspace_switchers("cad")

    def open_anchor_mapper(self):
        self.stack.setCurrentWidget(self.anchor_mapper_container)
        self.dock_tree.hide()
        self._sync_workspace_switchers("anchor_mapper")

    def open_rtls_dashboard(self):
        self.stack.setCurrentWidget(self.rtls_dashboard_container)
        self.dock_tree.hide()
        self._sync_workspace_switchers("rtls_dashboard")

    def _open_workspace_from_key(self, key: str):
        if key == "cad":
            self.go_to_cad()
        elif key == "anchor_mapper":
            self.open_anchor_mapper()
        elif key == "rtls_dashboard":
            self.open_rtls_dashboard()

    def _sync_workspace_switchers(self, current_key: str):
        self.cad_switcher.set_current_workspace(current_key)
        self.anchor_mapper_container.set_current_workspace(current_key)
        self.rtls_dashboard_container.set_current_workspace(current_key)
        if current_key != "cad":
            self.cad_switcher.close_panel()
        if current_key != "anchor_mapper":
            self.anchor_mapper_container.close_workspace_switcher()
        if current_key != "rtls_dashboard":
            self.rtls_dashboard_container.close_workspace_switcher()

    def save_as_svg(self):
        """Export the current CAD model to an SVG file."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import math

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save CAD Model as SVG", "",
            "SVG Files (*.svg);;All Files (*)"
        )
        if not filepath:
            return
        if not filepath.lower().endswith(".svg"):
            filepath += ".svg"

        lines = self.cad_canvas.lines
        if not lines:
            QMessageBox.information(self, "Nothing to Save", "The canvas is empty.")
            return

        # Compute bounding box
        all_pts = []
        for obj in lines:
            all_pts += [(obj.x1, obj.y1), (obj.x2, obj.y2)]
        min_x = min(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        w = max(max_x - min_x, 1e-3)
        h = max(max_y - min_y, 1e-3)
        
        # We use a large virtual coordinate space (1000x1000) for the SVG viewBox.
        # This prevents "blockiness" by providing high precision for vector renderers.
        DOC_SIZE = 1000.0
        MARGIN = 50.0 # 5% margin
        AVAILABLE = DOC_SIZE - (MARGIN * 2)
        
        # Calculate scale to fit in AVAILABLE space
        scale = min(AVAILABLE / w, AVAILABLE / h)
        
        # Center the drawing on the 1000x1000 canvas
        offset_x = (DOC_SIZE - (w * scale)) / 2.0
        offset_y = (DOC_SIZE - (h * scale)) / 2.0

        def tx(x): return (x - min_x) * scale + offset_x
        def ty(y): return (DOC_SIZE - (y - min_y) * scale) - offset_y  # flip y and center

        svg_lines = []
        from cad_core import Spline
        for obj in lines:
            color = getattr(obj, 'color', '#FFFFFF')
            if isinstance(obj, Spline):
                svg_lines.append(
                    f'  <path d="M {tx(obj.x1):.3f},{ty(obj.y1):.3f} '
                    f'C {tx(obj.cx1):.3f},{ty(obj.cy1):.3f} '
                    f'{tx(obj.cx2):.3f},{ty(obj.cy2):.3f} '
                    f'{tx(obj.x2):.3f},{ty(obj.y2):.3f}" '
                    f'fill="none" stroke="{color}" stroke-width="{max(1.0, 1.0 * (scale/2.0))}"/>'
                )
            else:
                svg_lines.append(
                    f'  <line x1="{tx(obj.x1):.3f}" y1="{ty(obj.y1):.3f}" '
                    f'x2="{tx(obj.x2):.3f}" y2="{ty(obj.y2):.3f}" '
                    f'stroke="{color}" stroke-width="{max(1.0, 1.0 * (scale/2.0))}"/>'
                )

        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="100%" height="100%" '
            f'viewBox="0 0 {DOC_SIZE} {DOC_SIZE}" '
            f'data-cad-min-x="{min_x}" data-cad-min-y="{min_y}" '
            f'data-cad-scale="{scale}" '
            f'data-cad-offset-x="{offset_x}" data-cad-offset-y="{offset_y}">',
            f'  <rect width="100%" height="100%" fill="#1E1E1E"/>',
            *svg_lines,
            '</svg>'
        ]

        try:
            with open(filepath, 'w') as f:
                f.write('\n'.join(svg))
            QMessageBox.information(self, "Saved", f"Model saved to:\n{filepath}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    def save_as_pdf(self):
        """Export the current CAD model to a vector PDF file."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        from PyQt6.QtGui import QPdfWriter, QPainter, QPen, QColor
        from PyQt6.QtCore import QSizeF

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save CAD Model as PDF", "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if not filepath:
            return
        if not filepath.lower().endswith(".pdf"):
            filepath += ".pdf"

        lines = self.cad_canvas.lines
        if not lines:
            QMessageBox.information(self, "Nothing to Save", "The canvas is empty.")
            return

        # Compute bounding box
        all_pts = []
        for obj in lines:
            all_pts += [(obj.x1, obj.y1), (obj.x2, obj.y2)]
        min_x = min(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        w = max(max_x - min_x, 1e-3)
        h = max(max_y - min_y, 1e-3)

        # Standard A4 Landscape: 297mm x 210mm
        PAGE_W = 297.0
        PAGE_H = 210.0
        MARGIN = 20.0 # 20mm margin
        AVAIL_W = PAGE_W - (MARGIN * 2)
        AVAIL_H = PAGE_H - (MARGIN * 2)

        # Calculate best auto-scale to fill the page
        scale = min(AVAIL_W / w, AVAIL_H / h)
        
        # Center on the page
        offset_x = (PAGE_W - (w * scale)) / 2.0
        offset_y = (PAGE_H - (h * scale)) / 2.0

        def tx(x): return (x - min_x) * scale + offset_x
        def ty(y): return (PAGE_H - (y - min_y) * scale) - offset_y # flip & center

        pdf_w = PAGE_W
        pdf_h = PAGE_H

        try:
            from PyQt6.QtGui import QPageSize
            writer = QPdfWriter(filepath)
            writer.setPageSize(QPageSize(QSizeF(pdf_w, pdf_h), QPageSize.Unit.Millimeter))
            writer.setResolution(300)

            painter = QPainter(writer)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            from cad_core import Spline
            for obj in lines:
                color = getattr(obj, 'color', '#000000') # PDFs use white backgrounds, so default to black lines
                if color == '#FFFFFF': color = '#000000'

                pen = QPen(QColor(color))
                pen.setWidth(max(1, int(1 * scale)))
                painter.setPen(pen)

                if isinstance(obj, Spline):
                    from PyQt6.QtGui import QPainterPath
                    path = QPainterPath()
                    path.moveTo(tx(obj.x1), ty(obj.y1))
                    path.cubicTo(tx(obj.cx1), ty(obj.cy1), tx(obj.cx2), ty(obj.cy2), tx(obj.x2), ty(obj.y2))
                    painter.drawPath(path)
                else:
                    painter.drawLine(int(tx(obj.x1)), int(ty(obj.y1)), int(tx(obj.x2)), int(ty(obj.y2)))

            painter.end()
            QMessageBox.information(self, "Saved", f"Model saved to:\n{filepath}")
        except Exception as e:
            QMessageBox.warning(self, "Save Error", str(e))

    def import_file(self):
        """Open a file dialog and import PDF or SVG vector geometry into the canvas."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Vector File", "",
            "Vector Files (*.pdf *.svg);;"
            "All Files (*)"
        )

        if not filepath:
            return

        filepath_lower = filepath.lower()

        if filepath_lower.endswith(".pdf"):
            segments, error = extract_lines_from_pdf(filepath)
        elif filepath_lower.endswith(".svg"):
            try:
                from svg_importer import extract_lines_from_svg
                segments, error = extract_lines_from_svg(filepath)
            except ImportError:
                segments, error = [], "svg_importer module not found."
        else:
            QMessageBox.warning(self, "Unsupported Format", "Only PDF and SVG files are allowed.")
            return
        
        if error:
            QMessageBox.warning(self, "Import Error", error)
            return
        
        if not segments:
            QMessageBox.information(self, "No Geometry", "No line geometry was found in the file.")
            return
        
        # Switch to CAD view
        self.go_to_cad()
        
        canvas = self.cad_canvas
        
        # Center the imported geometry at the current viewport center
        vp = canvas.vp
        center_wx = (0 - vp.offx) / vp.scale
        center_wy = (0 - vp.offy) / vp.scale

        # Find bounding center of imported geometry (segments are (x1,y1,x2,y2) tuples)
        xs = [s[0] for s in segments] + [s[2] for s in segments]
        ys = [s[1] for s in segments] + [s[3] for s in segments]

        geom_cx = (min(xs) + max(xs)) / 2
        geom_cy = (min(ys) + max(ys)) / 2

        # Offset so geometry centers on viewport center
        off_x = center_wx - geom_cx
        off_y = center_wy - geom_cy

        # Create CAD line objects from flat (x1, y1, x2, y2) tuples
        new_elements = []
        for x1, y1, x2, y2 in segments:
            new_elements.append(Line(x1 + off_x, y1 + off_y, x2 + off_x, y2 + off_y))
        
        canvas.lines.extend(new_elements)
        canvas.trigger_lines_changed()
        canvas.update()
        
        # Notify user
        QMessageBox.information(
            self, "Import Successful",
            f"Imported {len(new_elements)} geometry element(s) from:\n{filepath}"
        )

    def go_to_home(self):
        self.stack.setCurrentWidget(self.home_screen)
        self.dock_tree.hide()
        self.cad_switcher.close_panel()
        self.anchor_mapper_container.close_workspace_switcher()
        self.rtls_dashboard_container.close_workspace_switcher()
        
    def sync_feature_tree(self):
        # Block signals to prevent feedback loop during sync
        self.tree_widget.blockSignals(True)
        self.tree_widget.clear()
        
        # Root node for Lines
        lines_root = QTreeWidgetItem(["Lines"])
        lines_root.setExpanded(True)
        self.tree_widget.addTopLevelItem(lines_root)
        
        for i, line in enumerate(self.cad_canvas.lines):
            length = math.hypot(line.x2 - line.x1, line.y2 - line.y1)
            item = QTreeWidgetItem([f"Line {i+1} [L={length:.2f}]"])
            item.setData(0, Qt.ItemDataRole.UserRole, i) # Store index
            lines_root.addChild(item)
            if line.selected:
                item.setSelected(True)
                
        self.tree_widget.blockSignals(False)
        
    def on_tree_selection_changed(self):
        items = self.tree_widget.selectedItems()
        indices = []
        for item in items:
            idx = item.data(0, Qt.ItemDataRole.UserRole)
            if idx is not None:
                indices.append(idx)
        
        self.cad_canvas.select_lines_by_indices(indices)
        
    def toggle_snap(self, checked):
        self.cad_canvas.snap_enabled = checked
        self.cad_canvas.update()
        
    def toggle_grid_snap(self, checked):
        self.cad_canvas.grid_snap_enabled = checked
        self.cad_canvas.update()

    def toggle_grid(self, checked):
        self.cad_canvas.grid_enabled = checked
        self.cad_canvas.update()

    def toggle_vertices(self, checked):
        self.cad_canvas.show_vertices = checked
        self.cad_canvas.update()
        
    def style_tool_btn_ribbon(self, btn, active=False):
        bg = "#007ACC" if active else "transparent"
        border = "none" if active else "1px solid #555"
        # Type name for QToolButton vs QPushButton
        type_name = btn.metaObject().className()
        
        btn.setStyleSheet(f"""
            {type_name} {{
                background-color: {bg};
                color: white;
                border: {border};
                border-radius: 4px;
                font-weight: bold;
                padding: 4px; 
                padding-right: 15px; /* Make room for arrow if we draw one, or just spacing */
            }}
            {type_name}:hover {{
                background-color: #505050;
                border: none;
            }}
            /* Re-enable indicator but style it smaller */
            {type_name}::menu-indicator {{ 
                image: none;
                width: 20px; /* Larger hit area */
                border-left: 1px solid #777;
                subcontrol-origin: padding;
                subcontrol-position: center right;
            }}
            /* Since we use text only, we might want a small unicode arrow in text or just the indicator.
               Let's try a standard cleaner arrow. */
            {type_name}::menu-indicator:pressed, {type_name}::menu-indicator:open {{
                background-color: #303030;
            }}
            /* Menu Styling */
            QMenu {{
                background-color: #2D2D30;
                border: 1px solid #3E3E42;
                color: #D4D4D4;
            }}
            QMenu::item {{
                padding: 5px 20px;
            }}
            QMenu::item:selected {{
                background-color: #094771;
            }}
            QMenu::item:checked {{
                background-color: #3C3C3C;
                font-weight: bold;
                color: #FFFFFF;
                border-left: 2px solid #007ACC;
            }}
        """)

    def style_line_group_custom(self, active=False):
        # Custom styling for the split button look
        bg = "#007ACC" if active else "transparent"
        border = "none" if active else "1px solid #555"
        text_col = "white"
        
        # Main Button: Rounded Left only
        self.btn_line_tool.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {text_col};
                border: {border};
                border-top-left-radius: 4px;
                border-bottom-left-radius: 4px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                font-weight: bold;
                border-right: 1px solid #444; /* Separator */
                text-align: center;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: #505050;
            }}
        """)
        
        # Arrow Button: Rounded Right only
        # IMPORTANT: Hide the ::menu-indicator because we rely on the QToolButton's own ArrowIcon
        self.btn_line_arrow.setStyleSheet(f"""
            QToolButton {{
                background-color: {bg};
                color: {text_col};
                border: {border};
                border-left: none;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                padding: 0px;
            }}
            QToolButton:hover {{
                background-color: #505050;
            }}
            QToolButton:pressed, QToolButton:checked {{
                background-color: #005A9E;
            }}
            QToolButton::menu-indicator {{
                image: none;
                width: 0px;
            }}
        """)

    def trigger_current_line_tool(self):
        # Trigger whichever is active in the menu
        if self.act_line.isChecked(): self.set_tool("line")
        elif self.act_trim.isChecked(): self.set_tool("trim")
        elif self.act_extend.isChecked(): self.set_tool("extend")
        elif self.act_spline.isChecked(): self.set_tool("spline")

    def set_tool(self, mode):
        # Force cancel any pending operation to avoid ghost lines/states
        self.cad_canvas.cancel_operation()
        
        self.cad_canvas.tool_mode = mode
        self.style_tool_btn_ribbon(self.btn_cursor, mode == "cursor")
        
        # Group logic: Active if mode is one of the drawing/editing tools
        is_line_group = mode in ["line", "trim", "extend", "spline"]
        self.style_line_group_custom(active=is_line_group)
        
        # Update text/icon and checked state of menu
        if mode == "line":
            self.btn_line_tool.setText("Line")
            self.act_line.setChecked(True)
        elif mode == "trim":
            self.btn_line_tool.setText("Trim")
            self.act_trim.setChecked(True)
        elif mode == "extend":
            self.btn_line_tool.setText("Extend")
            self.act_extend.setChecked(True)
        elif mode == "spline":
            self.btn_line_tool.setText("Spline")
            self.act_spline.setChecked(True)
        # If switching to cursor, clear snaps immediately
        if mode != "line":
            self.cad_canvas.snap_hint = None
            self.cad_canvas.alignment_guides = []
            
        # Reset Trim State
        self.cad_canvas.trim_step = 0
        self.cad_canvas.trim_target = None
        self.cad_canvas.trim_points = []
            
        self.cad_canvas.update()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Pick a font family that exists on the current platform to avoid
    # the "qt.qpa.fonts: Populating font family aliases" slow-path warning.
    # Use utility to select an appropriate default font family for the platform
    font_family = get_default_font_family()
    font = QFont(font_family, 10)
    app.setFont(font)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())
