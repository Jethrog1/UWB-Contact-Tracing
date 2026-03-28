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

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QLabel, QWidget,
    QHBoxLayout, QVBoxLayout, QPushButton, QSizePolicy,
    QSplitter, QListWidget, QListWidgetItem, QInputDialog
)
from PyQt6.QtGui import QAction, QIcon, QFont, QColor, QPalette, QPixmap
from PyQt6.QtCore import Qt, QPointF, QEvent, QTimer, pyqtSignal

from map_canvas import MapCanvas, MapMode
from room_data import Room, Anchor


# ──────────────────────────────────────────────────────────────────────────────
# Style
# ──────────────────────────────────────────────────────────────────────────────
DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #12121f;
    color: #e0e0f0;
    font-family: 'Segoe UI', 'SF Pro Text', sans-serif;
    font-size: 13px;
}
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


# ──────────────────────────────────────────────────────────────────────────────
# RTLSDashboard
# ──────────────────────────────────────────────────────────────────────────────
class RTLSDashboard(QMainWindow):
    # Emitted when the user clicks the Home button (used when embedded in main_qt)
    go_home = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTLS Dashboard – Ship Floor Plan Tracker")
        self.resize(1400, 900)
        self.setStyleSheet(DARK_STYLESHEET)

        # ── State ─────────────────────────────────────────────────────────
        self._rooms: list[Room] = []

        # ── Central Layout (Splitter) ─────────────────────────────────────
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        # ── Map canvas (left panel) ───────────────────────────────────────
        self._canvas = MapCanvas(self.splitter)
        self._canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._canvas.no_image_warning.connect(self._on_no_image)
        self._canvas.room_designated.connect(self._on_room_designated)
        self.splitter.addWidget(self._canvas)

        # ── Feature Manager (right panel) ─────────────────────────────────
        self._feature_panel = self._build_feature_panel()
        self.splitter.addWidget(self._feature_panel)

        # Give the feature panel a minimum size, but make default smaller
        self.splitter.setSizes([1100, 300])
        self._feature_panel.setMinimumWidth(200)

        # ── Toolbar ───────────────────────────────────────────────────────
        self._build_toolbar()

        # ── Status bar ────────────────────────────────────────────────────
        self._build_statusbar()

        # ── Track mouse position on canvas ────────────────────────────────
        self._canvas.setMouseTracking(True)
        self._canvas.installEventFilter(self)

        # ── Welcome hint ─────────────────────────────────────────────────
        self._show_status("Load a floor plan image to get started  (File → Load Image)")

    # ──────────────────────────────────────────────────────────────────────────
    # Toolbar
    # ──────────────────────────────────────────────────────────────────────────
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
        title = QLabel("⚓ RTLS Dashboard", self)
        title.setObjectName("title_label")
        tb.addWidget(title)
        tb.addSeparator()

        # Load Image
        act_img = QAction("🖼  Load Image", self)
        act_img.setToolTip("Load a PNG / JPG / BMP floor plan image")
        act_img.triggered.connect(self._load_image)
        tb.addAction(act_img)

        # Load Vector (PDF/SVG)
        act_vector = QAction("📄  Load Vector", self)
        act_vector.setToolTip("Load a mathematical vector floor plan (PDF or SVG)")
        act_vector.triggered.connect(self._load_vector)
        tb.addAction(act_vector)

        tb.addSeparator()

        # Fit view
        act_fit = QAction("⊡  Fit View", self)
        act_fit.setToolTip("Fit the entire floor plan in view  (F)")
        act_fit.setShortcut("F")
        act_fit.triggered.connect(self._canvas.fit_in_view)
        tb.addAction(act_fit)

        # Zoom in / out
        act_zin = QAction("＋  Zoom In", self)
        act_zin.setShortcut("Ctrl+=")
        act_zin.triggered.connect(lambda: self._canvas.zoom_by(1.25))
        tb.addAction(act_zin)

        act_zout = QAction("－  Zoom Out", self)
        act_zout.setShortcut("Ctrl+-")
        act_zout.triggered.connect(lambda: self._canvas.zoom_by(0.8))
        tb.addAction(act_zout)

        tb.addSeparator()

        # Mode: Pan
        self._act_pan = QAction("✋  Pan", self)
        self._act_pan.setCheckable(True)
        self._act_pan.setChecked(True)
        self._act_pan.triggered.connect(lambda: self._set_mode(MapMode.PAN))
        tb.addAction(self._act_pan)

        # Mode: Select
        self._act_select = QAction("🖍  Select", self)
        self._act_select.setCheckable(True)
        self._act_select.setChecked(False)
        self._act_select.setToolTip("Click lines to select / deselect them  (Esc = clear)")
        self._act_select.triggered.connect(lambda: self._set_mode(MapMode.SELECT))
        tb.addAction(self._act_select)

        self._mode_actions = [self._act_pan, self._act_select]
        self._canvas.set_mode(MapMode.PAN)
        self._canvas.selection_changed.connect(self._on_selection_changed)

    def _set_mode(self, mode: str):
        for act in self._mode_actions:
            act.setChecked(False)
        if mode == MapMode.PAN:
            self._act_pan.setChecked(True)
        elif mode == MapMode.SELECT:
            self._act_select.setChecked(True)
        self._canvas.set_mode(mode)
        self._show_status(f"Mode: {mode.upper()}")

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
        self._lbl_status.setText(msg)

    # ──────────────────────────────────────────────────────────────────────────
    # Event filter – mouse coordinate readout
    # ──────────────────────────────────────────────────────────────────────────
    def eventFilter(self, obj, event):
        if obj is self._canvas and event.type() == QEvent.Type.MouseMove:
            pos = event.position()
            wx, wy = self._canvas.vp.screen_to_world(pos.x(), pos.y())
            self._lbl_coords.setText(f"x: {wx:.2f}  y: {wy:.2f} m")
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
            filename = os.path.basename(path)
            self._lbl_image.setText(f"📷 {filename}")
            self._show_status(f"Loaded: {filename}")
        else:
            QMessageBox.warning(self, "Load Error",
                                f"Could not load image:\n{path}")

    def _load_vector(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Vector Floor Plan", "",
            "Vector Graphics (*.pdf *.svg);;All Files (*)"
        )
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".svg":
            ok = self._canvas.load_svg(path)
        elif ext == ".pdf":
            ok = self._canvas.load_pdf(path)
        else:
            ok = self._canvas.load_image(path)
        if ok:
            filename = os.path.basename(path)
            self._lbl_image.setText(f"📐 {filename}")
            self._show_status(f"Loaded Vector: {filename}")
        else:
            QMessageBox.warning(self, "Load Error",
                                f"Could not load vector graphic:\n{path}\n\nMake sure PyMuPDF (fitz) is installed for PDF support.")

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
        
        # Connect map canvas double-click
        self._canvas.map_double_clicked.connect(self._on_map_double_click)
        layout.addWidget(self._room_list)

        # Buttons
        btn_layout = QHBoxLayout()
        self._btn_rename = QPushButton("Rename")
        self._btn_rename.clicked.connect(self._rename_room)
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.clicked.connect(self._delete_room)

        btn_layout.addWidget(self._btn_rename)
        btn_layout.addWidget(self._btn_delete)
        layout.addLayout(btn_layout)

        layout.addStretch()
        return panel

    def _refresh_room_list(self):
        self._room_list.clear()
        for r in self._rooms:
            item = QListWidgetItem(f"🏠 {r.name} ({len(r.anchors)} anchors)")
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._room_list.addItem(item)

    def _on_room_designated(self, name: str, segments: list):
        r = Room(name=name, segments=segments)
        self._rooms.append(r)
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
            self._refresh_room_list()

    def _on_room_double_click(self, item):
        room = item.data(Qt.ItemDataRole.UserRole)
        self._open_room_view(room)
        
    def _open_room_view(self, room):
        self._show_status(f"Opening Room view for: {room.name}")
        
        from room_detail_view import RoomDetailDialog
        dlg = RoomDetailDialog(room, self._rooms, self)
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
