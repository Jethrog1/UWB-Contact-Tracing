import math
from typing import List, Tuple, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, 
    QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QMessageBox, QButtonGroup
)
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QColor, QMouseEvent, QWheelEvent, QBrush, QFont
from PyQt6.QtCore import Qt, QPointF, QRectF, QPoint, QRect

from cad_core import Viewport
from room_data import Room, Anchor

ROOM_ZOOM_MIN = 0.05
ROOM_ZOOM_MAX = 6000.0

class RoomCanvas(QWidget):
    """
    Local coordinate canvas for a specific Room.
    Origin (0,0) is at the bottom-left of the room's bounding box.
    """
    def __init__(self, room: Room, all_rooms: List[Room], parent=None):
        super().__init__(parent)
        self.room = room
        self.all_rooms = all_rooms
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.vp = Viewport()
        self._pan_active = False
        self._pan_last = QPointF()
        
        self.dist_anchor_1: Optional[Anchor] = None
        self.dist_anchor_2: Optional[Anchor] = None
        self.mode = "PAN"
        
        self.active_tags = {}
        
        # Colors
        self.bg_color = QColor("#141414")
        self.room_bg_color = QColor("#1c1c28")
        self.grid_color = QColor("#303040")
        self.axis_color = QColor("#444466")
        self.wall_color = QColor("#ffffff")
        self.anchor_colors = [
            QColor("#ef4444"), # A0 Red
            QColor("#3b82f6"), # A1 Blue
            QColor("#10b981"), # A2 Green
            QColor("#f59e0b")  # A3 Yellow
        ]
        
        # Auto-fit on show
        self._first_show = True

    @staticmethod
    def _dist_point_to_segment(px, py, x1, y1, x2, y2) -> float:
        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-12:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    def _update_tag(self, tag_id: str, local_x: float, local_y: float):
        self.active_tags[tag_id] = (local_x, local_y)
        self.update()

    def fit_in_view(self):
        W, H = self.width(), self.height()
        if W < 10 or H < 10:
            return
            
        span_x = max(self.room.width, 1e-3)
        span_y = max(self.room.height, 1e-3)
        
        MARGIN = 0.15 # 15% padding
        scale = min((W * (1 - MARGIN * 2)) / span_x,
                    (H * (1 - MARGIN * 2)) / span_y)
        scale = max(ROOM_ZOOM_MIN, min(ROOM_ZOOM_MAX, scale))
        
        # Center of room in local coords is (width/2, height/2)
        cx_w = self.room.width / 2.0
        cy_w = self.room.height / 2.0
        
        self.vp.scale = scale
        self.vp.offx = W / 2 - cx_w * scale
        self.vp.offy = H / 2 + cy_w * scale
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._first_show:
            self.fit_in_view()
            self._first_show = False
            
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "PAN":
                self._pan_active = True
                self._pan_last = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
            elif self.mode == "ADD":
                lx, ly = self.vp.screen_to_world(event.position().x(), event.position().y())
                self._add_anchor(lx, ly)
                event.accept()
                return
            elif self.mode == "DELETE":
                lx, ly = self.vp.screen_to_world(event.position().x(), event.position().y())
                self._remove_anchor_near(lx, ly)
                event.accept()
                return
            elif self.mode in ("DIST_SELECT_1", "DIST_SELECT_2"):
                lx, ly = self.vp.screen_to_world(event.position().x(), event.position().y())
                a = self._hit_test_anchor(lx, ly)
                if a:
                    if self.mode == "DIST_SELECT_1":
                        self.dist_anchor_1 = a
                        parent = self.parentWidget()
                        while parent and not hasattr(parent, 'set_mode'):
                            parent = parent.parentWidget()
                        if parent: parent.set_mode("DIST_SELECT_2")
                    else:
                        if a != self.dist_anchor_1:
                            self.dist_anchor_2 = a
                            parent = self.parentWidget()
                            while parent and not hasattr(parent, 'set_mode'):
                                parent = parent.parentWidget()
                            if parent: parent.set_mode("DIST_EDIT")
                self.update()
                event.accept()
                return

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._pan_active:
            delta = event.position() - self._pan_last
            self._pan_last = event.position()
            self.vp.offx += delta.x()
            self.vp.offy += delta.y()
            self.update()
            event.accept()
            return
        
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._pan_active and event.button() == Qt.MouseButton.LeftButton:
            self._pan_active = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self.mode == "DIST_EDIT" and event.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, "_last_dist_rect") and self._last_dist_rect.contains(event.position().toPoint()):
                a1 = self.dist_anchor_1
                a2 = self.dist_anchor_2
                if not (a1 and a2): return
                
                curr_dist = math.hypot(a2.x - a1.x, a2.y - a1.y)
                if curr_dist < 0.0001: return
                
                from PyQt6.QtWidgets import QInputDialog
                val, ok = QInputDialog.getDouble(
                    self, "Edit Distance", 
                    f"Enter new distance from {a1.id} to {a2.id} (m):",
                    value=curr_dist, min=0.01, max=1000.0, decimals=3
                )
                if ok and val != curr_dist:
                    ratio = val / curr_dist
                    dx = a2.x - a1.x
                    dy = a2.y - a1.y
                    a2.x = a1.x + dx * ratio
                    a2.y = a1.y + dy * ratio
                    
                    self.update()
                    parent = self.parentWidget()
                    while parent and not hasattr(parent, 'refresh_anchor_list'):
                        parent = parent.parentWidget()
                    if parent: parent.refresh_anchor_list()
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        angle = event.angleDelta().y()
        factor = 1.15 if angle > 0 else (1 / 1.15)
        pos = event.position()
        new_scale = self.vp.scale * factor
        new_scale = max(ROOM_ZOOM_MIN, min(ROOM_ZOOM_MAX, new_scale))
        if new_scale != self.vp.scale:
            self.vp.zoom_at(new_scale / self.vp.scale, pos.x(), pos.y())
        self.update()
        event.accept()
        
    def _add_anchor(self, lx: float, ly: float):
        if len(self.room.anchors) >= 4:
            return
            
        # Placement validation: must be inside or very close to polygon
        valid = self.room.contains_local_point(lx, ly)
        if not valid:
            # Fallback: allow points right on the corner edges (0.05m tolerance)
            for wx1, wy1, wx2, wy2 in self.room.segments:
                lx1, ly1 = self.room.world_to_local(wx1, wy1)
                lx2, ly2 = self.room.world_to_local(wx2, wy2)
                if self._dist_point_to_segment(lx, ly, lx1, ly1, lx2, ly2) <= 0.05:
                    valid = True
                    break
        
        if not valid:
            QMessageBox.warning(self, "Invalid Placement", "Anchors must be placed inside or on the boundary of the room.")
            return

        room_idx = self.all_rooms.index(self.room) + 1
        used_ids = {a.id for a in self.room.anchors}

        i = 0
        while f"R{room_idx}A{i}" in used_ids:
            i += 1
        next_id = f"R{room_idx}A{i}"
                
        self.room.anchors.append(Anchor(id=next_id, x=lx, y=ly))
        self.room.anchors.sort(key=lambda a: int(a.id.split('A')[-1]) if 'A' in a.id else 0)
        
        parent = self.parentWidget()
        while parent and not isinstance(parent, RoomDetailDialog):
            parent = parent.parentWidget()
        if parent:
            parent.refresh_anchor_list()
            
        self.update()

    def _hit_test_anchor(self, lx: float, ly: float):
        hit_dist = max(0.5, 15.0 / self.vp.scale)
        best_a = None
        best_d = hit_dist + 1
        
        for a in self.room.anchors:
            d = math.hypot(lx - a.x, ly - a.y)
            if d < hit_dist and d < best_d:
                best_d = d
                best_a = a
        return best_a

    def _remove_anchor_near(self, lx: float, ly: float):
        a = self._hit_test_anchor(lx, ly)
        if a:
            self.room.anchors.remove(a)
            parent = self.parentWidget()
            while parent and not hasattr(parent, 'refresh_anchor_list'):
                parent = parent.parentWidget()
            if parent:
                parent.refresh_anchor_list()
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), self.bg_color)
        
        W, H = self.width(), self.height()
        wx0, wy0 = self.vp.screen_to_world(0, H)
        wx1, wy1 = self.vp.screen_to_world(W, 0)
        
        # Build screen-space painter path for clipping
        room_poly_local = self.room.get_local_polygon()
        room_path_screen = QPainterPath()
        if not room_poly_local.isEmpty():
            first_pt = True
            for i in range(room_poly_local.count()):
                pt = room_poly_local.at(i)
                sx, sy = self.vp.world_to_screen(pt.x(), pt.y())
                if first_pt:
                    room_path_screen.moveTo(sx, sy)
                    first_pt = False
                else:
                    room_path_screen.lineTo(sx, sy)
            room_path_screen.closeSubpath()

            # Fill the room's inner boundary
            p.fillPath(room_path_screen, QBrush(self.room_bg_color))

        # Check for reference anchor (first placed)
        ref_a = self.room.anchors[0] if self.room.anchors else None
        
        # ── Grid (Only if ref_a is placed, clipped to room) ───────────────────
        if ref_a and not room_path_screen.isEmpty():
            p.save()
            p.setClipPath(room_path_screen)
            
            # Grid offset from ref_a
            min_gx = math.floor(wx0 - ref_a.x)
            max_gx = math.ceil(wx1 - ref_a.x)
            min_gy = math.floor(wy0 - ref_a.y)
            max_gy = math.ceil(wy1 - ref_a.y)
            
            grid_pen = QPen(self.grid_color)
            grid_pen.setCosmetic(True)
            p.setPen(grid_pen)
            
            # Draw vertical lines relative to ref_a.x
            for gx in range(min_gx, max_gx + 1):
                world_x = ref_a.x + gx
                sx, sy0 = self.vp.world_to_screen(world_x, wy0)
                _, sy1 = self.vp.world_to_screen(world_x, wy1)
                p.drawLine(int(sx), int(sy0), int(sx), int(sy1))
                
            # Draw horizontal lines relative to ref_a.y
            for gy in range(min_gy, max_gy + 1):
                world_y = ref_a.y + gy
                sx0, sy = self.vp.world_to_screen(wx0, world_y)
                sx1, _ = self.vp.world_to_screen(wx1, world_y)
                p.drawLine(int(sx0), int(sy), int(sx1), int(sy))
                
            # Draw primary ref_a Axes
            axis_pen = QPen(self.axis_color)
            axis_pen.setWidth(2)
            axis_pen.setCosmetic(True)
            p.setPen(axis_pen)
            
            sx0, sy = self.vp.world_to_screen(wx0, ref_a.y)
            sx1, _ = self.vp.world_to_screen(wx1, ref_a.y)
            p.drawLine(int(sx0), int(sy), int(sx1), int(sy))
            
            sx, sy0 = self.vp.world_to_screen(ref_a.x, wy0)
            _, sy1 = self.vp.world_to_screen(ref_a.x, wy1)
            p.drawLine(int(sx), int(sy0), int(sx), int(sy1))
            
            p.restore()
        
        # ── Room Boundary Line ─────────────────────────────────────────────
        wall_pen = QPen(self.wall_color)
        wall_pen.setWidthF(2.0)
        wall_pen.setCosmetic(True)
        p.setPen(wall_pen)
        
        for wx1, wy1, wx2, wy2 in self.room.segments:
            # Convert world segments to local room coords
            lx1, ly1 = self.room.world_to_local(wx1, wy1)
            lx2, ly2 = self.room.world_to_local(wx2, wy2)
            
            sx1, sy1 = self.vp.world_to_screen(lx1, ly1)
            sx2, sy2 = self.vp.world_to_screen(lx2, ly2)
            p.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))

        # ── Anchors ────────────────────────────────────────────────────────
        font = p.font()
        font.setBold(True)
        font.setPointSize(10)
        p.setFont(font)
        
        for a in self.room.anchors:
            sx, sy = self.vp.world_to_screen(a.x, a.y)
            
            idx = int(a.id[1]) if len(a.id) > 1 and a.id[1].isdigit() else 0
            color = self.anchor_colors[idx % len(self.anchor_colors)]
            
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            # Decreased size
            p.drawEllipse(QPointF(sx, sy), 5, 5)
            
            p.setPen(QPen(Qt.GlobalColor.white))
            p.drawText(int(sx) + 8, int(sy) + 4, a.id)

        # ── Room Dimensions Overlay ───────────────────────────────────────────
        p.setPen(QPen(Qt.GlobalColor.white))
        p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        p.drawText(15, 25, f"Room Dimensions: {self.room.width:.2f}m x {self.room.height:.2f}m")
        
        # ── Distance Editing Overlay ──────────────────────────────────────────
        if self.mode == "DIST_EDIT" and self.dist_anchor_1 and self.dist_anchor_2:
            a1, a2 = self.dist_anchor_1, self.dist_anchor_2
            s1x, s1y = self.vp.world_to_screen(a1.x, a1.y)
            s2x, s2y = self.vp.world_to_screen(a2.x, a2.y)
            
            d_pen = QPen(Qt.GlobalColor.yellow, 2, Qt.PenStyle.DashLine)
            p.setPen(d_pen)
            p.drawLine(int(s1x), int(s1y), int(s2x), int(s2y))
            
            dist = math.hypot(a2.x - a1.x, a2.y - a1.y)
            mx, my = (s1x + s2x) / 2, (s1y + s2y) / 2
            
            p.setPen(QPen(Qt.GlobalColor.white))
            p.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            text = f"{dist:.2f}m"
            fm = p.fontMetrics()
            rect = fm.boundingRect(text)
            rect.moveCenter(QPoint(int(mx), int(my)))
            
            p.fillRect(rect.adjusted(-4, -2, 4, 2), QColor(0, 0, 0, 150))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            self._last_dist_rect = rect.adjusted(-4, -2, 4, 2)

        # ── RTLS Tags Overlay ─────────────────────────────────────────────────
        if hasattr(self, 'active_tags') and self.active_tags:
            TAG_COLORS = {"T0":"#3498db","T1":"#e67e22","T2":"#9b59b6","T3":"#e74c3c"}
            tr = max(7, min(int(self.vp.scale * 0.22), 14))
            tag_ids = list(self.active_tags.keys())
            
            # Connect tags with physical inter-distance dashed lines
            for i in range(len(tag_ids)):
                for j in range(i + 1, len(tag_ids)):
                    tid_a = tag_ids[i]; tid_b = tag_ids[j]
                    pos_a = self.active_tags[tid_a]; pos_b = self.active_tags[tid_b]
                    s1x, s1y = self.vp.world_to_screen(pos_a[0], pos_a[1])
                    s2x, s2y = self.vp.world_to_screen(pos_b[0], pos_b[1])
                    
                    pen = QPen(QColor("#e67e22"), 2, Qt.PenStyle.DashLine)
                    pen.setDashPattern([6, 4])
                    p.setPen(pen)
                    p.drawLine(int(s1x), int(s1y), int(s2x), int(s2y))
                    
                    dist = math.hypot(pos_b[0] - pos_a[0], pos_b[1] - pos_a[1])
                    mx = (s1x + s2x) / 2; my = (s1y + s2y) / 2
                    label = f"{dist:.2f}m"
                    p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                    fm = p.fontMetrics()
                    tw = fm.horizontalAdvance(label); th = fm.height()
                    
                    bg_rect = QRectF(mx - tw/2 - 3, my - th/2 - 2, tw + 6, th + 4)
                    p.setBrush(QBrush(QColor(20, 20, 20, 210)))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(bg_rect, 3, 3)
                    p.setPen(QPen(QColor("#e67e22")))
                    p.drawText(int(mx - tw/2), int(my + th/2 - 2), label)
            
            # Layer interactive tracking dots and IDs on top
            for tid, pos in self.active_tags.items():
                spx, spy = self.vp.world_to_screen(pos[0], pos[1])
                col = QColor(TAG_COLORS.get(tid, "#3498db"))
                
                p.setPen(QPen(Qt.GlobalColor.white, 2))
                p.setBrush(QBrush(col))
                p.drawEllipse(QPointF(spx, spy), tr, tr)
                
                p.setFont(QFont("Segoe UI", max(8, tr - 2), QFont.Weight.Bold))
                p.setPen(col)
                p.drawText(int(spx) + tr + 4, int(spy) - 2, tid)
                p.setFont(QFont("Segoe UI", max(7, tr - 4)))
                p.setPen(QColor("#888888"))
                p.drawText(int(spx) + tr + 4, int(spy) + 12, f"({pos[0]:.2f}, {pos[1]:.2f})")

        p.end()

class RoomDetailDialog(QDialog):
    """
    Dialog popup that hosts the RoomCanvas and an Anchor coordinate list.
    """
    def __init__(self, room: Room, all_rooms: List[Room], parent=None):
        super().__init__(parent)
        self.room = room
        self.setWindowTitle(f"Room Detail – {room.name}")
        self.resize(1000, 700)
        
        # Overall dark style
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #1a1a2e;
                color: #e0e0f0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                font-size: 14px;
                font-weight: bold;
            }
            QListWidget {
                background-color: #12121f;
                border: 1px solid #2d2d5e;
                border-radius: 4px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #1a1a2e;
            }
            QPushButton {
                background-color: #2d2d5e;
                color: #e0e0f0;
                border: 2px solid transparent;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a7a;
            }
            QPushButton:checked {
                background-color: #3182CE;
                border: 2px solid #63B3ED;
                color: white;
            }
            QSplitter::handle {
                background-color: #3a3a7a;
                width: 4px;
                border-left: 1px solid #1a1a2e;
                border-right: 1px solid #1a1a2e;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # Canvas left
        self.canvas = RoomCanvas(room, all_rooms, splitter)
        splitter.addWidget(self.canvas)
        
        # Side panel right
        side_panel = QWidget(splitter)
        side_panel.setMinimumWidth(200)
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(16, 16, 16, 16)
        side_layout.setSpacing(10)
        
        lbl_title = QLabel(f"Room: {room.name}")
        
        mode_layout = QVBoxLayout()
        mode_layout.setSpacing(5)
        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)
        
        self.btn_pan = QPushButton("✋ Pan")
        self.btn_pan.setCheckable(True)
        self.btn_pan.setChecked(True)
        
        self.btn_add = QPushButton("📌 Add Anchor")
        self.btn_add.setCheckable(True)
        
        self.btn_del = QPushButton("🗑 Delete Anchor")
        self.btn_del.setCheckable(True)
        
        self.btn_dist = QPushButton("📏 Edit Distance")
        self.btn_dist.setCheckable(True)
        
        self.btn_group.addButton(self.btn_pan)
        self.btn_group.addButton(self.btn_add)
        self.btn_group.addButton(self.btn_del)
        self.btn_group.addButton(self.btn_dist)
        
        mode_layout.addWidget(self.btn_pan)
        mode_layout.addWidget(self.btn_add)
        mode_layout.addWidget(self.btn_del)
        mode_layout.addWidget(self.btn_dist)
        
        self.btn_fit = QPushButton("🔍 Fit View")
        self.btn_fit.clicked.connect(self.canvas.fit_in_view)
        mode_layout.addWidget(self.btn_fit)
        
        self.btn_reindex = QPushButton("🔄 Reindex")
        self.btn_reindex.clicked.connect(self.reindex_anchors)
        mode_layout.addWidget(self.btn_reindex)
        
        self.btn_pan.clicked.connect(lambda: self.set_mode("PAN"))
        self.btn_add.clicked.connect(lambda: self.set_mode("ADD"))
        self.btn_del.clicked.connect(lambda: self.set_mode("DELETE"))
        self.btn_dist.clicked.connect(lambda: self.set_mode("DIST_SELECT_1"))
        
        # Remove old instruction label
        side_layout.addWidget(lbl_title)
        side_layout.addLayout(mode_layout)
        
        self.list_anchors = QListWidget()
        self.list_anchors.itemDoubleClicked.connect(self._edit_anchor_coords)
        side_layout.addWidget(self.list_anchors)
        
        # ── RTLS Serial ──────────────────────────────────────────────────────────
        from PyQt6.QtWidgets import QComboBox
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except ImportError:
            ports = []
        ports.insert(0, "Virtual MOCK_RTLS")
            
        lbl_rtls = QLabel("RTLS Serial Connect")
        lbl_rtls.setStyleSheet("font-weight: bold; margin-top: 10px;")
        side_layout.addWidget(lbl_rtls)

        rtls_layout = QHBoxLayout()
        self.cb_ports = QComboBox()
        self.cb_ports.addItems(ports)
        
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setCheckable(True)
        self.btn_connect.clicked.connect(self._toggle_rtls)

        rtls_layout.addWidget(self.cb_ports)
        rtls_layout.addWidget(self.btn_connect)
        side_layout.addLayout(rtls_layout)

        btn_close = QPushButton("Done")
        btn_close.clicked.connect(self.accept)
        side_layout.addWidget(btn_close)
        
        splitter.setSizes([700, 300])
        
        self.refresh_anchor_list()

    def set_mode(self, mode: str):
        self.canvas.mode = mode
        if mode == "DIST_SELECT_1":
            self.canvas.dist_anchor_1 = None
            self.canvas.dist_anchor_2 = None
            self.setWindowTitle("Room Viewer - Select Stationary Anchor")
        elif mode == "DIST_SELECT_2":
            self.setWindowTitle("Room Viewer - Select Moving Anchor")
        elif mode == "DIST_EDIT":
            self.setWindowTitle("Room Viewer - Double-click distance text to edit")
        else:
            self.setWindowTitle(f"Room Viewer - {self.room.name}")
            self.canvas.dist_anchor_1 = None
            self.canvas.dist_anchor_2 = None
        self.canvas.update()

    def reindex_anchors(self):
        reply = QMessageBox.question(
            self, "Reindex Anchors", 
            "Are you sure you want to reindex all anchors?\n"
            "This will sequentially rename all anchors matching their room index (e.g. R1A0, R1A1...), closing any numbering gaps.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            for r_idx, r in enumerate(self.canvas.all_rooms, start=1):
                r.anchors.sort(key=lambda a: int(a.id.split('A')[-1]) if 'A' in a.id else 0)
                for a_idx, a in enumerate(r.anchors):
                    a.id = f"R{r_idx}A{a_idx}"
            self.refresh_anchor_list()
            self.canvas.update()

    def refresh_anchor_list(self):
        self.list_anchors.clear()
        ref_a = self.room.anchors[0] if self.room.anchors else None
        
        for a in self.room.anchors:
            if ref_a:
                rel_x = a.x - ref_a.x
                rel_y = a.y - ref_a.y
            else:
                rel_x, rel_y = a.x, a.y
            item = QListWidgetItem(f"{a.id}: ({rel_x:.2f}m, {rel_y:.2f}m)")
            self.list_anchors.addItem(item)

    def _edit_anchor_coords(self, item):
        aid = item.text().split(":")[0]
        anchor = next((a for a in self.room.anchors if a.id == aid), None)
        if not anchor: return

        ref_a = self.room.anchors[0] if self.room.anchors else None
        rel_x = anchor.x - ref_a.x if ref_a else anchor.x
        rel_y = anchor.y - ref_a.y if ref_a else anchor.y
        
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self, "Edit Coordinates", 
            f"Enter new relative coordinates for {aid} (X, Y):",
            text=f"{rel_x:.2f}, {rel_y:.2f}"
        )
        if ok and text.strip():
            try:
                parts = text.split(',')
                if len(parts) == 2:
                    nx, ny = float(parts[0].strip()), float(parts[1].strip())
                    anchor.x = nx + ref_a.x if ref_a else nx
                    anchor.y = ny + ref_a.y if ref_a else ny
                    self.refresh_anchor_list()
                    self.canvas.update()
                else:
                    QMessageBox.warning(self, "Error", "Invalid format. Target X, Y.")
            except ValueError:
                QMessageBox.warning(self, "Error", "Coordinates must be numeric.")

    def _toggle_rtls(self, checked):
        if checked:
            port = self.cb_ports.currentText()
            if not port:
                self.btn_connect.setChecked(False)
                return
            
            try:
                if port == "Virtual MOCK_RTLS":
                    from serial_reader import MockSerialReaderThread
                    self.serial_thread = MockSerialReaderThread()
                else:
                    from serial_reader import SerialReaderThread
                    self.serial_thread = SerialReaderThread(port, 115200)
                
                self.serial_thread.tag_update.connect(self.canvas._update_tag)
                self.serial_thread.connection_error.connect(self._on_rtls_error)
                self.serial_thread.start()
                self.btn_connect.setText("Disconnect")
                self.cb_ports.setEnabled(False)
            except Exception as e:
                self._on_rtls_error(str(e))
        else:
            if hasattr(self, 'serial_thread') and self.serial_thread:
                self.serial_thread.stop()
                self.serial_thread = None
            self.btn_connect.setText("Connect")
            self.cb_ports.setEnabled(True)
            self.canvas.active_tags.clear()
            self.canvas.update()

    def _on_rtls_error(self, err):
        QMessageBox.warning(self, "RTLS Error", err)
        if hasattr(self, 'btn_connect'):
            self.btn_connect.setChecked(False)
            self.btn_connect.setText("Connect")
            self.cb_ports.setEnabled(True)
        if hasattr(self, 'serial_thread') and self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread = None
