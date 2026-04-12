import math
import os
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel, 
    QPushButton, QListWidget, QListWidgetItem, QSplitter,
    QMessageBox, QButtonGroup, QTextEdit, QStackedWidget,
    QSlider, QDoubleSpinBox, QScrollArea, QFileDialog
)
from PyQt6.QtGui import QPainter, QPainterPath, QPen, QColor, QMouseEvent, QWheelEvent, QBrush, QFont
from PyQt6.QtCore import Qt, QPointF, QRectF, QPoint, QRect, QTimer

from cad_core import Viewport
from room_data import Room, Anchor
from room_profiles import default_room_profile_path, save_room_profile

ROOM_ZOOM_MIN = 0.05
ROOM_ZOOM_MAX = 6000.0

class RoomCanvas(QWidget):
    """
    Local coordinate canvas for a specific Room.
    Origin (0,0) is at the bottom-left of the room's bounding box.
    """
    def __init__(self, room: Room, all_rooms: List[Room], parent=None, editable: bool = True):
        super().__init__(parent)
        self.room = room
        self.all_rooms = all_rooms
        self.editable = editable
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.vp = Viewport()
        self._pan_active = False
        self._pan_last = QPointF()
        
        self.dist_anchor_1: Optional[Anchor] = None
        self.dist_anchor_2: Optional[Anchor] = None
        self.mode = "PAN"
        
        self.active_tags = {}
        self.selected_anchor = None

        # ── RTLS Filter State ──────────────────────────────────
        self.filter_mode = "None"   # None | EMA | Rolling | Kalman
        self.tag_height = 0.0       # feet, for 3D range projection
        self.ema_alpha = 0.3
        self.roll_n = 8
        self.kalman_q = 0.1
        self.kalman_r = 2.0

        self._ema_pos = {}          # {tag_id: (x, y) or None}
        self._roll_buf = {}         # {tag_id: deque}
        self._kalman_state = {}     # {tag_id: [[rx],[ry],[vx],[vy]]}
        self._kalman_P = {}         # {tag_id: 4x4 matrix}
        
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
        
        # Instruction Overlay
        from PyQt6.QtWidgets import QHBoxLayout
        self.instruction_overlay = QWidget(self)
        self.instruction_overlay.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 20, 20, 220);
                border: 1px solid #444;
                border-radius: 8px;
            }
            QLabel {
                color: white;
                font-weight: bold;
                font-size: 14px;
                border: none;
                background: transparent;
            }
            QPushButton {
                background-color: #ef4444;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover { background-color: #dc2626; }
        """)
        overlay_layout = QHBoxLayout(self.instruction_overlay)
        overlay_layout.setContentsMargins(15, 8, 15, 8)
        self.lbl_instruction = QLabel("Instruction")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancel_action)
        overlay_layout.addWidget(self.lbl_instruction)
        overlay_layout.addWidget(self.btn_cancel)
        self.instruction_overlay.hide()

    def set_interaction_mode(self, mode: str):
        self.mode = mode
        if mode == "DIST_SELECT_1":
            self.lbl_instruction.setText("Select stationary anchor")
            self.instruction_overlay.adjustSize()
            self._center_overlay()
            self.instruction_overlay.show()
        elif mode == "DIST_SELECT_2":
            self.lbl_instruction.setText("Select an anchor to move")
            self.instruction_overlay.adjustSize()
            self._center_overlay()
            self.instruction_overlay.show()
        else:
            self.instruction_overlay.hide()
        self.update()

    def _center_overlay(self):
        w = self.instruction_overlay.width()
        self.instruction_overlay.move(int(self.width() / 2 - w / 2), 20)
        
    def cancel_action(self):
        self.dist_anchor_1 = None
        self.dist_anchor_2 = None
        parent = self.parentWidget()
        while parent and not hasattr(parent, 'set_mode'):
            parent = parent.parentWidget()
        if parent:
            parent.set_mode("PAN")
            if hasattr(parent, "btn_pan"):
                parent.btn_pan.setChecked(True)
        else:
            self.set_interaction_mode("PAN")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_action()
        super().keyPressEvent(event)

    @staticmethod
    def _dist_point_to_segment(px, py, x1, y1, x2, y2) -> float:
        dx, dy = x2 - x1, y2 - y1
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-12:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    def _update_tag(self, tag_id: str, local_x: float, local_y: float):
        sx, sy = self.smooth(tag_id, local_x, local_y)
        self.active_tags[tag_id] = (sx, sy)
        self.update()

    def _remove_tag(self, tag_id: str):
        self.active_tags.pop(tag_id, None)
        self._ema_pos.pop(tag_id, None)
        self._roll_buf.pop(tag_id, None)
        self._kalman_state.pop(tag_id, None)
        self._kalman_P.pop(tag_id, None)

    def sync_world_tags_for_room(self, world_tags: Dict[str, Tuple[float, float]]):
        visible_tags: Dict[str, Tuple[float, float]] = {}
        for tag_id, (world_x, world_y) in world_tags.items():
            local_x, local_y = self.room.world_to_local(world_x, world_y)
            if self.room.contains_local_point(local_x, local_y):
                visible_tags[tag_id] = (local_x, local_y)

        current_ids = set(self.active_tags.keys())
        next_ids = set(visible_tags.keys())
        for stale_tag_id in current_ids - next_ids:
            self._remove_tag(stale_tag_id)

        for tag_id, (local_x, local_y) in visible_tags.items():
            self._update_tag(tag_id, local_x, local_y)

        if not visible_tags:
            self.update()

    def smooth(self, tag_id: str, x: float, y: float):
        """Apply the selected smoothing filter to (x, y) and return filtered coords."""
        if self.filter_mode == "EMA":
            return self._apply_ema(tag_id, x, y)
        elif self.filter_mode == "Rolling":
            return self._apply_rolling(tag_id, x, y)
        elif self.filter_mode == "Kalman":
            return self._apply_kalman(tag_id, x, y)
        return (x, y)

    def _apply_ema(self, t_id, rx, ry):
        a = self.ema_alpha
        prev = self._ema_pos.get(t_id)
        if prev is None:
            result = (rx, ry)
        else:
            result = (a * rx + (1 - a) * prev[0], a * ry + (1 - a) * prev[1])
        self._ema_pos[t_id] = result
        return result

    def _apply_rolling(self, t_id, rx, ry):
        from collections import deque
        buf = self._roll_buf.get(t_id)
        if buf is None or buf.maxlen != self.roll_n:
            old = list(buf or [])
            buf = deque(old[-self.roll_n:], maxlen=self.roll_n)
            self._roll_buf[t_id] = buf
        buf.append((rx, ry))
        return (sum(p[0] for p in buf) / len(buf), sum(p[1] for p in buf) / len(buf))

    def _apply_kalman(self, t_id, rx, ry):
        q, r, dt = self.kalman_q, self.kalman_r, 0.05
        F = [[1,0,dt,0],[0,1,0,dt],[0,0,1,0],[0,0,0,1]]
        H = [[1,0,0,0],[0,1,0,0]]
        Q = [[q*dt**3/3,0,q*dt**2/2,0],[0,q*dt**3/3,0,q*dt**2/2],
             [q*dt**2/2,0,q*dt,0],[0,q*dt**2/2,0,q*dt]]
        R = [[r,0],[0,r]]

        def mm(A,B): return [[sum(A[i][k]*B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]
        def ma(A,B): return [[A[i][j]+B[i][j] for j in range(len(A[0]))] for i in range(len(A))]
        def ms(A,B): return [[A[i][j]-B[i][j] for j in range(len(A[0]))] for i in range(len(A))]
        def mT(A): return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]
        def eye(n): return [[1 if i==j else 0 for j in range(n)] for i in range(n)]
        def inv2(A):
            d = A[0][0]*A[1][1]-A[0][1]*A[1][0] or 1e-9
            return [[A[1][1]/d,-A[0][1]/d],[-A[1][0]/d,A[0][0]/d]]

        if self._kalman_state.get(t_id) is None:
            self._kalman_state[t_id] = [[rx],[ry],[0.0],[0.0]]
            self._kalman_P[t_id] = eye(4)

        x_s = self._kalman_state[t_id]
        P = self._kalman_P[t_id]
        xp = mm(F, x_s)
        Pp = ma(mm(mm(F,P),mT(F)), Q)
        z = [[rx],[ry]]
        yk = ms(z, mm(H,xp))
        S = ma(mm(mm(H,Pp),mT(H)), R)
        K = mm(mm(Pp,mT(H)), inv2(S))
        xn = ma(xp, mm(K,yk))
        Pn = mm(ms(eye(4),mm(K,H)), Pp)
        self._kalman_state[t_id] = xn
        self._kalman_P[t_id] = Pn
        return (xn[0][0], xn[1][0])

    def reset_filter_state(self, tag_id=None):
        if tag_id:
            self._ema_pos.pop(tag_id, None)
            self._roll_buf.pop(tag_id, None)
            self._kalman_state.pop(tag_id, None)
            self._kalman_P.pop(tag_id, None)
        else:
            self._ema_pos.clear()
            self._roll_buf.clear()
            self._kalman_state.clear()
            self._kalman_P.clear()

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
        self._center_overlay()
        if self._first_show:
            self.fit_in_view()
            self._first_show = False
            
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode in ("PAN", "CURSOR"):
                lx, ly = self.vp.screen_to_world(event.position().x(), event.position().y())
                hit = self._hit_test_anchor(lx, ly)
                if hit:
                    # Select the anchor and highlight it in the sidebar
                    self.selected_anchor = hit
                    parent = self.parentWidget()
                    while parent and not hasattr(parent, 'list_anchors'):
                        parent = parent.parentWidget()
                    if parent:
                        for i in range(parent.list_anchors.count()):
                            item = parent.list_anchors.item(i)
                            if item.text().startswith(hit.id):
                                parent.list_anchors.setCurrentItem(item)
                                break
                    self.update()
                    event.accept()
                    return
                else:
                    # Start pan drag
                    self.selected_anchor = None
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
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.editable:
                event.accept()
                return
            # In CURSOR/PAN mode, double-clicking an anchor triggers the edit dialog
            if self.mode in ("PAN", "CURSOR"):
                lx, ly = self.vp.screen_to_world(event.position().x(), event.position().y())
                hit = self._hit_test_anchor(lx, ly)
                if hit:
                    parent = self.parentWidget()
                    while parent and not hasattr(parent, '_edit_anchor_for'):
                        parent = parent.parentWidget()
                    if parent:
                        parent._edit_anchor_for(hit)
                    event.accept()
                    return

            # In DIST_EDIT mode, double-click on the distance label edits it
            if hasattr(self, "_last_dist_rect") and self._last_dist_rect.contains(event.position().toPoint()):
                a1 = self.dist_anchor_1
                a2 = self.dist_anchor_2
                if not (a1 and a2): return
                
                curr_dist = math.hypot(a2.x - a1.x, a2.y - a1.y)
                if curr_dist < 0.0001: return
                
                from PyQt6.QtWidgets import QInputDialog
                val, ok = QInputDialog.getDouble(
                    self, "Edit Distance", 
                    f"Enter new distance from {a1.id} to {a2.id} (ft):",
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
        
        # ── Interior Non-Wall Geometry ────────────────────────────────────
        if getattr(self.room, "interior_segments", None):
            interior_pen = QPen(QColor("#8E949C"))
            interior_pen.setWidthF(1.6)
            interior_pen.setCosmetic(True)
            p.setPen(interior_pen)

            for wx1, wy1, wx2, wy2 in self.room.interior_segments:
                lx1, ly1 = self.room.world_to_local(wx1, wy1)
                lx2, ly2 = self.room.world_to_local(wx2, wy2)

                sx1, sy1 = self.vp.world_to_screen(lx1, ly1)
                sx2, sy2 = self.vp.world_to_screen(lx2, ly2)
                p.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))

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
            
            # Measure & Annotate Physical Walls
            wall_len = math.hypot(lx2 - lx1, ly2 - ly1)
            if wall_len > 0.05:
                mx = (sx1 + sx2) / 2.0
                my = (sy1 + sy2) / 2.0
                label = f"{wall_len:.2f}ft"
                
                prev_pen = p.pen()
                p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                fm = p.fontMetrics()
                tw = fm.horizontalAdvance(label)
                th = fm.height()
                
                bg_rect = QRectF(mx - tw/2 - 4, my - th/2 - 2, tw + 8, th + 4)
                
                p.setBrush(QBrush(QColor(25, 25, 30, 220)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(bg_rect, 4, 4)
                
                p.setPen(QPen(QColor("#a8a8b3")))
                p.drawText(int(mx - tw/2), int(my + th/2 - 2), label)
                
                p.setPen(prev_pen)

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
            p.drawEllipse(QPointF(sx, sy), 5, 5)
            
            # Selection ring
            if a is self.selected_anchor:
                p.setPen(QPen(Qt.GlobalColor.white, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(sx, sy), 9, 9)
            
            p.setPen(QPen(Qt.GlobalColor.white))
            p.drawText(int(sx) + 8, int(sy) + 4, a.id)

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
            text = f"{dist:.2f}ft"
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
                    label = f"{dist:.2f}ft"
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

class AnchorEditDialog(QDialog):
    """Single popup to edit an anchor's Hardware ID and local coordinates."""
    def __init__(self, anchor, ref_anchor, parent=None):
        super().__init__(parent)
        self.anchor = anchor
        self.ref_anchor = ref_anchor
        self.setWindowTitle(f"Edit Anchor – {anchor.id}")
        self.setMinimumWidth(320)
        self.setModal(True)
        
        self.setStyleSheet("""
            QDialog { background-color: #1a1a2e; color: #e0e0f0; }
            QLabel { font-size: 13px; }
            QLineEdit {
                background-color: #12121f;
                color: #e0e0f0;
                border: 1px solid #3182CE;
                border-radius: 4px;
                padding: 6px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #2d2d5e;
                color: #e0e0f0;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a3a7a; }
            QPushButton#ok_btn { background-color: #3182CE; color: white; }
            QPushButton#ok_btn:hover { background-color: #2c71b8; }
        """)
        
        from PyQt6.QtWidgets import QFormLayout, QLineEdit, QDialogButtonBox
        outer = QVBoxLayout(self)
        outer.setSpacing(12)
        outer.setContentsMargins(20, 20, 20, 20)
        
        form = QFormLayout()
        form.setSpacing(10)
        
        self.field_hw = QLineEdit(anchor.hw_id or "")
        self.field_hw.setPlaceholderText("e.g. A0, A1, A2, A3")
        form.addRow("Hardware ID:", self.field_hw)
        
        # Show ABSOLUTE coords from room origin (0,0) = bottom-left corner
        self.field_x = QLineEdit(f"{anchor.x:.3f}")
        self.field_y = QLineEdit(f"{anchor.y:.3f}")
        form.addRow("X from room origin (ft):", self.field_x)
        form.addRow("Y from room origin (ft):", self.field_y)
        
        note = QLabel("↳ (0, 0) = room bottom-left corner")
        note.setStyleSheet("font-size: 10px; color: #888; font-weight: normal;")
        form.addRow("", note)
        
        outer.addLayout(form)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("ok_btn")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

class RoomDetailDialog(QDialog):
    """
    Dialog popup that hosts the RoomCanvas and an Anchor coordinate list.
    """
    def __init__(
        self,
        room: Room,
        all_rooms: List[Room],
        parent=None,
        editable: bool = True,
        world_tag_provider: Optional[Callable[[], Dict[str, Tuple[float, float]]]] = None,
    ):
        super().__init__(parent)
        self.room = room
        self.editable = editable
        self._world_tag_provider = world_tag_provider
        self._shared_tag_timer: Optional[QTimer] = None
        self.serial_thread = None
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
            QListWidget::item:selected {
                background-color: #3182CE;
                color: white;
                border-radius: 3px;
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

        # ── Top-level layout: banner + content ──────────────────────────────
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Banner ─────────────────────────────────────────────────────────
        banner = QWidget()
        banner.setFixedHeight(44)
        banner.setStyleSheet("background-color: #12121f; border-bottom: 1px solid #2d2d5e;")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(12, 0, 12, 0)
        banner_layout.setSpacing(8)

        lbl_banner = QLabel(f"🏛 Room: {room.name}")
        lbl_banner.setStyleSheet("font-size: 13px; font-weight: bold; color: #e0e0f0;")
        banner_layout.addWidget(lbl_banner)
        banner_layout.addStretch()

        if self.editable:
            self.btn_tab_tools = QPushButton("🗺️ Anchor Tools")
            self.btn_tab_tools.setCheckable(True)
            self.btn_tab_tools.setChecked(True)
            self.btn_tab_tools.setFixedHeight(30)
            self.btn_tab_calib = QPushButton("⚙️ Calibration")
            self.btn_tab_calib.setCheckable(True)
            self.btn_tab_calib.setFixedHeight(30)
            tab_group = QButtonGroup(self)
            tab_group.setExclusive(True)
            tab_group.addButton(self.btn_tab_tools)
            tab_group.addButton(self.btn_tab_calib)

            banner_layout.addWidget(self.btn_tab_tools)
            banner_layout.addWidget(self.btn_tab_calib)
        outer.addWidget(banner)

        # ── Content area ───────────────────────────────────────────────────
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        outer.addWidget(content, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        content_layout.addWidget(splitter)

        self.canvas = RoomCanvas(room, all_rooms, splitter, editable=self.editable)
        splitter.addWidget(self.canvas)
        self.canvas.tag_height = float(self.room.rtls_settings.get("tag_height_ft", 0.0))
        self.canvas.filter_mode = self.room.rtls_settings.get("filter_mode", "None")

        if not self.editable:
            if self._world_tag_provider is not None:
                lbl_shared = QLabel("Live RTLS")
                lbl_shared.setFixedHeight(30)
                lbl_shared.setStyleSheet(
                    "padding: 5px 10px; border-radius: 15px; "
                    "background-color: rgba(49, 130, 206, 0.18); color: #9bd1ff; "
                    "font-size: 11px; font-weight: bold;"
                )
                banner_layout.addWidget(lbl_shared)

            btn_fit = QPushButton("⊡ Fit View")
            btn_fit.setFixedHeight(30)
            btn_fit.setStyleSheet("color: #ffffff; font-weight: bold;")
            btn_fit.clicked.connect(self.canvas.fit_in_view)
            banner_layout.addWidget(btn_fit)

            zoom_wrap = QWidget()
            zoom_lay = QHBoxLayout(zoom_wrap)
            zoom_lay.setContentsMargins(0, 0, 0, 0)
            zoom_lay.setSpacing(6)
            zoom_label = QPushButton("Zoom")
            zoom_label.setEnabled(False)
            zoom_label.setFixedHeight(30)
            zoom_label.setStyleSheet("color: #aeb6ff; font-weight: bold; padding: 6px 10px;")
            zoom_lay.addWidget(zoom_label)
            zoom_col = QVBoxLayout()
            zoom_col.setContentsMargins(0, 0, 0, 0)
            zoom_col.setSpacing(3)

            btn_zoom_in = QPushButton("+")
            btn_zoom_in.setFixedSize(30, 18)
            btn_zoom_in.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold; padding: 0px;")
            btn_zoom_in.clicked.connect(
                lambda: self.canvas.vp.zoom_at(1.25, self.canvas.width() / 2, self.canvas.height() / 2) or self.canvas.update()
            )
            zoom_col.addWidget(btn_zoom_in)

            btn_zoom_out = QPushButton("-")
            btn_zoom_out.setFixedSize(30, 18)
            btn_zoom_out.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold; padding: 0px;")
            btn_zoom_out.clicked.connect(
                lambda: self.canvas.vp.zoom_at(0.8, self.canvas.width() / 2, self.canvas.height() / 2) or self.canvas.update()
            )
            zoom_col.addWidget(btn_zoom_out)
            zoom_lay.addLayout(zoom_col)
            banner_layout.addWidget(zoom_wrap)

            if self._world_tag_provider is not None:
                self._shared_tag_timer = QTimer(self)
                self._shared_tag_timer.timeout.connect(self._sync_shared_world_tags)
                self._shared_tag_timer.start(110)
                self._sync_shared_world_tags()

        if self.editable:
            # ── Stacked sidebar ────────────────────────────────────────────────
            self.sidebar_stack = QStackedWidget()
            self.sidebar_stack.setMinimumWidth(220)
            splitter.addWidget(self.sidebar_stack)

        # ===== Page 0: Anchor Tools =====
        if self.editable:
            tools_page = QWidget()
            tools_layout = QVBoxLayout(tools_page)
            tools_layout.setContentsMargins(12, 12, 12, 12)
            tools_layout.setSpacing(8)

            tools_layout.addWidget(QLabel(f"Room: {room.name}"))

            mode_layout = QVBoxLayout()
            mode_layout.setSpacing(5)
            self.btn_group = QButtonGroup(self)
            self.btn_group.setExclusive(True)

            self.btn_pan = QPushButton("🖱 Cursor")
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

            self.btn_pan.clicked.connect(lambda: self.set_mode("CURSOR"))
            self.btn_add.clicked.connect(lambda: self.set_mode("ADD"))
            self.btn_del.clicked.connect(lambda: self.set_mode("DELETE"))
            self.btn_dist.clicked.connect(lambda: self.set_mode("DIST_SELECT_1"))

            tools_layout.addLayout(mode_layout)

            self.list_anchors = QListWidget()
            self.list_anchors.itemDoubleClicked.connect(self._edit_anchor_coords)
            tools_layout.addWidget(self.list_anchors)

            from PyQt6.QtWidgets import QComboBox
            try:
                import serial.tools.list_ports
                ports = [p.device for p in serial.tools.list_ports.comports()]
            except ImportError:
                ports = []
            ports.insert(0, "Virtual MOCK_RTLS")

            lbl_rtls = QLabel("RTLS Connect")
            lbl_rtls.setStyleSheet("font-size: 11px; font-weight: bold; margin-top: 6px;")
            tools_layout.addWidget(lbl_rtls)
            rtls_row = QHBoxLayout()
            self.cb_ports = QComboBox()
            self.cb_ports.addItems(ports)
            self.btn_connect = QPushButton("Connect")
            self.btn_connect.setCheckable(True)
            self.btn_connect.clicked.connect(self._toggle_rtls)
            rtls_row.addWidget(self.cb_ports)
            rtls_row.addWidget(self.btn_connect)
            tools_layout.addLayout(rtls_row)

            lbl_dbg = QLabel("Serial Debug")
            lbl_dbg.setStyleSheet("font-size: 9px; color: #888;")
            tools_layout.addWidget(lbl_dbg)
            self.debug_log = QTextEdit()
            self.debug_log.setReadOnly(True)
            self.debug_log.setMaximumHeight(85)
            self.debug_log.setStyleSheet("background: #0a0a0a; color: #7ec8e3; font-size: 9px; border: 1px solid #333;")
            tools_layout.addWidget(self.debug_log)

            btn_save_profile = QPushButton("💾 Save Profile")
            btn_save_profile.clicked.connect(self._save_room_profile)
            tools_layout.addWidget(btn_save_profile)

            btn_done = QPushButton("Done")
            btn_done.clicked.connect(self.accept)
            tools_layout.addWidget(btn_done)

            self.sidebar_stack.addWidget(tools_page)   # index 0

        # ===== Page 1: RTLS Calibration =====
            calib_scroll = QScrollArea()
            calib_scroll.setWidgetResizable(True)
            calib_scroll.setStyleSheet("QScrollArea { border: none; }")
            calib_inner = QWidget()
            calib_layout = QVBoxLayout(calib_inner)
            calib_layout.setContentsMargins(12, 12, 12, 12)
            calib_layout.setSpacing(10)
            calib_scroll.setWidget(calib_inner)

        # Tag height
            lbl_h = QLabel("📐 Tag Height (ft)")
            lbl_h.setStyleSheet("font-size: 11px; font-weight: bold;")
            calib_layout.addWidget(lbl_h)
            self.spin_height = QDoubleSpinBox()
            self.spin_height.setRange(0.0, 10.0)
            self.spin_height.setSingleStep(0.05)
            self.spin_height.setDecimals(2)
            self.spin_height.setValue(self.canvas.tag_height)
            self.spin_height.setStyleSheet("background: #12121f; color: #e0e0f0; border: 1px solid #3182CE; border-radius: 4px; padding: 4px;")
            self.spin_height.valueChanged.connect(self._on_tag_height_changed)
            calib_layout.addWidget(self.spin_height)

        # Filter selection
            lbl_filt = QLabel("🌀 Smoothing Filter")
            lbl_filt.setStyleSheet("font-size: 11px; font-weight: bold; margin-top: 6px;")
            calib_layout.addWidget(lbl_filt)
            filt_grp = QButtonGroup(self)
            filt_grp.setExclusive(True)
            filt_row = QHBoxLayout()
            for mode in ("None", "EMA", "Rolling", "Kalman"):
                btn = QPushButton(mode)
                btn.setCheckable(True)
                if mode == self.canvas.filter_mode:
                    btn.setChecked(True)
                btn.setFixedHeight(28)
                btn.clicked.connect(lambda checked, m=mode: self._set_filter(m))
                filt_grp.addButton(btn)
                filt_row.addWidget(btn)
            calib_layout.addLayout(filt_row)

        # Slider helper
            def _slider_row(label, lo, hi, default, step, decimals, on_change):
                row_w = QWidget()
                row_l = QVBoxLayout(row_w)
                row_l.setContentsMargins(0, 0, 0, 0)
                row_l.setSpacing(2)
                hdr = QHBoxLayout()
                lbl_s = QLabel(label)
                lbl_s.setStyleSheet("font-size: 10px;")
                val_lbl = QLabel(f"{default:.{decimals}f}")
                val_lbl.setStyleSheet("font-size: 10px; color: #3182CE; font-weight: bold;")
                hdr.addWidget(lbl_s)
                hdr.addStretch()
                hdr.addWidget(val_lbl)
                sld = QSlider(Qt.Orientation.Horizontal)
                sld.setRange(int(lo / step), int(hi / step))
                sld.setValue(int(default / step))
                sld.valueChanged.connect(lambda v, vl=val_lbl, d=decimals, s=step, f=on_change: (
                    vl.setText(f"{v * s:.{d}f}"),
                    f(v * s)
                ))
                row_l.addLayout(hdr)
                row_l.addWidget(sld)
                return row_w

            calib_layout.addWidget(_slider_row(
                "EMA α  (0=smooth, 1=raw)", 0.01, 1.0, 0.3, 0.01, 2,
                lambda v: setattr(self.canvas, 'ema_alpha', v)))
            calib_layout.addWidget(_slider_row(
                "Rolling window (frames)", 2, 30, 8, 1, 0,
                lambda v: setattr(self.canvas, 'roll_n', int(v))))
            calib_layout.addWidget(_slider_row(
                "Kalman Q (process noise)", 0.01, 2.0, 0.1, 0.01, 2,
                lambda v: setattr(self.canvas, 'kalman_q', v)))
            calib_layout.addWidget(_slider_row(
                "Kalman R (meas. noise)", 0.1, 10.0, 2.0, 0.1, 1,
                lambda v: setattr(self.canvas, 'kalman_r', v)))

            btn_reset = QPushButton("🔄 Reset Filter State")
            btn_reset.clicked.connect(lambda: self.canvas.reset_filter_state())
            calib_layout.addWidget(btn_reset)
            calib_layout.addStretch()

            self.sidebar_stack.addWidget(calib_scroll)  # index 1

            # Banner tab connections
            self.btn_tab_tools.clicked.connect(lambda: self.sidebar_stack.setCurrentIndex(0))
            self.btn_tab_calib.clicked.connect(lambda: self.sidebar_stack.setCurrentIndex(1))

            splitter.setSizes([700, 280])
            self.refresh_anchor_list()
        else:
            splitter.setSizes([980, 20])
            self.canvas.fit_in_view()

    def set_mode(self, mode: str):
        self.canvas.set_interaction_mode(mode)
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
            hw_label = f" [hw:{a.hw_id}]" if a.hw_id else " [hw:?]"
            item = QListWidgetItem(f"{a.id}{hw_label}: ({rel_x:.2f}ft, {rel_y:.2f}ft)")
            self.list_anchors.addItem(item)

    def _edit_anchor_for(self, anchor):
        """Open the combined Anchor edit dialog for the given anchor."""
        dlg = AnchorEditDialog(anchor, None, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                hw = dlg.field_hw.text().strip()
                nx = float(dlg.field_x.text().strip())
                ny = float(dlg.field_y.text().strip())
                anchor.hw_id = hw
                # Store absolute local coords (origin = room bottom-left)
                anchor.x = nx
                anchor.y = ny
                self.refresh_anchor_list()
                self.canvas.update()
            except ValueError:
                QMessageBox.warning(self, "Error", "X and Y must be numeric.")

    def _edit_anchor_coords(self, item):
        aid = item.text().split(":")[0].strip()
        anchor = next((a for a in self.room.anchors if a.id == aid), None)
        if anchor:
            self._edit_anchor_for(anchor)

    def _set_filter(self, mode: str):
        self.canvas.filter_mode = mode
        self.canvas.reset_filter_state()
        self.room.rtls_settings["filter_mode"] = mode

    def _on_tag_height_changed(self, value: float):
        self.canvas.tag_height = value
        self.room.rtls_settings["tag_height_ft"] = value

    def _save_room_profile(self):
        default_path = default_room_profile_path(self.room.name)
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Room Profile",
            default_path,
            "JSON Files (*.json);;All Files (*)",
        )
        if not filepath:
            return
        if not filepath.lower().endswith(".json"):
            filepath += ".json"
        try:
            filepath = save_room_profile(
                self.room,
                tag_height_ft=self.canvas.tag_height,
                filter_mode=self.canvas.filter_mode,
                filepath=filepath,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Save Profile Failed", str(exc))
            return

        QMessageBox.information(
            self,
            "Profile Saved",
            f"Room profile saved to:\n{filepath}"
        )

    def _toggle_rtls(self, checked):
        if checked:
            port = self.cb_ports.currentText()
            if not port:
                self.btn_connect.setChecked(False)
                return
            
            try:
                if port == "Virtual MOCK_RTLS":
                    from serial_reader import MockSerialReaderThread
                    self.serial_thread = MockSerialReaderThread(
                        room=self.room,
                        coordinate_mode="local",
                    )
                else:
                    from serial_reader import SerialReaderThread
                    # Build anchor_positions dict for bilateration.
                    # Use short "A0", "A1"... suffix so it cross-matches hardware packets
                    # (e.g. "A0:11.37") regardless of room prefix.
                    anchor_positions = {}
                    for a in self.room.anchors:
                        # Prefer the user-set hardware ID; fall back to suffix extraction.
                        hw_key = a.hw_id.strip() if a.hw_id.strip() else None
                        if not hw_key:
                            suffix = a.id.split("A", 1)[-1] if "A" in a.id else a.id
                            hw_key = f"A{suffix}"
                        anchor_positions[hw_key] = (a.x, a.y)
                    
                    self.serial_thread = SerialReaderThread(
                        port, 115200, anchor_positions,
                        tag_height=self.canvas.tag_height
                    )
                
                self.serial_thread.tag_update.connect(self.canvas._update_tag)
                self.serial_thread.connection_error.connect(self._on_rtls_error)
                if hasattr(self.serial_thread, 'raw_line'):
                    self.serial_thread.raw_line.connect(self._on_raw_line)
                if hasattr(self.serial_thread, 'debug_msg'):
                    self.serial_thread.debug_msg.connect(self._on_debug_msg)
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

    def _sync_shared_world_tags(self):
        if self._world_tag_provider is None:
            return
        try:
            world_tags = dict(self._world_tag_provider() or {})
        except Exception:
            return
        self.canvas.sync_world_tags_for_room(world_tags)

    def _stop_live_updates(self):
        if self._shared_tag_timer is not None:
            self._shared_tag_timer.stop()
            self._shared_tag_timer = None
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread = None

    def _on_rtls_error(self, err):
        QMessageBox.warning(self, "RTLS Error", err)
        if hasattr(self, 'btn_connect'):
            self.btn_connect.setChecked(False)
            self.btn_connect.setText("Connect")
            self.cb_ports.setEnabled(True)
        if self.serial_thread:
            self.serial_thread.stop()
            self.serial_thread = None

    def _on_raw_line(self, line: str):
        if hasattr(self, 'debug_log'):
            self.debug_log.append(f"<span style='color:#666'>RAW: {line[:70]}</span>")
            self.debug_log.verticalScrollBar().setValue(self.debug_log.verticalScrollBar().maximum())

    def _on_debug_msg(self, msg: str):
        if hasattr(self, 'debug_log'):
            color = "#e74c3c" if "WARN" in msg or "SKIP" in msg else "#2ecc71"
            self.debug_log.append(f"<span style='color:{color}'>{msg}</span>")
            self.debug_log.verticalScrollBar().setValue(self.debug_log.verticalScrollBar().maximum())

    def done(self, result: int):
        self._stop_live_updates()
        super().done(result)
