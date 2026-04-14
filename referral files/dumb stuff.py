import sys
import math
import numpy as np

from PyQt6.QtCore import Qt, QTimer, QPointF, QRect
from PyQt6.QtGui import QPainter, QColor, QImage, QPen, QFont, QBrush
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout,
    QHBoxLayout, QLabel, QSlider, QPushButton
)


class HeatMapWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(900, 600)

        self.base_heat = 0.08
        self.cell_size = 4
        self.dot_radius_px = 7

        self.grid_w = 1
        self.grid_h = 1
        self.heat = np.full((1, 1), self.base_heat, dtype=np.float32)

        self.mouse_pos = QPointF(100, 100)
        self.virtual_dots = []
        self.place_dot_mode = False
        self.selected_dot_index = None
        self.dragging_dot = False

        self.sensitivity = 20
        self.decay_rate = 0.992

        self._rgb_buffer = np.zeros((1, 1, 3), dtype=np.uint8)
        self._qimage = QImage()

        self.lut = self.build_lut()

        self.resize_heat_array()
        self.rebuild_image()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def build_lut(self):
        lut = np.zeros((256, 3), dtype=np.uint8)
        for i in range(256):
            v = i / 255.0

            if v < 0.14:
                t = v / 0.14
                r = 0
                g = int(120 * t)
                b = 255

            elif v < 0.28:
                t = (v - 0.14) / 0.14
                r = 0
                g = int(120 + (135 * t))
                b = 255

            elif v < 0.42:
                t = (v - 0.28) / 0.14
                r = 0
                g = 255
                b = int(255 * (1 - t))

            elif v < 0.58:
                t = (v - 0.42) / 0.16
                r = int(255 * t)
                g = 255
                b = 0

            elif v < 0.74:
                t = (v - 0.58) / 0.16
                r = 255
                g = int(255 - (90 * t))
                b = 0

            elif v < 0.88:
                t = (v - 0.74) / 0.14
                r = 255
                g = int(165 * (1 - t))
                b = 0

            else:
                t = (v - 0.88) / 0.12
                r = int(255 - (75 * t))
                g = 0
                b = 0

            lut[i] = [r, g, b]
        return lut

    def resize_heat_array(self):
        new_grid_w = max(1, self.width() // self.cell_size)
        new_grid_h = max(1, self.height() // self.cell_size)

        if new_grid_w == self.grid_w and new_grid_h == self.grid_h:
            return

        new_heat = np.full((new_grid_h, new_grid_w), self.base_heat, dtype=np.float32)

        copy_h = min(self.grid_h, new_grid_h)
        copy_w = min(self.grid_w, new_grid_w)
        new_heat[:copy_h, :copy_w] = self.heat[:copy_h, :copy_w]

        self.grid_w = new_grid_w
        self.grid_h = new_grid_h
        self.heat = new_heat
        self._rgb_buffer = np.zeros((self.grid_h, self.grid_w, 3), dtype=np.uint8)

    def resizeEvent(self, event):
        self.resize_heat_array()
        self.rebuild_image()
        super().resizeEvent(event)

    def set_sensitivity(self, value):
        self.sensitivity = value

    def set_place_dot_mode(self, enabled):
        self.place_dot_mode = enabled
        self.selected_dot_index = None
        self.dragging_dot = False
        self.update()

    def clear_dots(self):
        self.virtual_dots.clear()
        self.selected_dot_index = None
        self.dragging_dot = False
        self.update()

    def reset_heat(self):
        self.heat.fill(self.base_heat)
        self.rebuild_image()
        self.update()

    def screen_to_grid_float(self, pos):
        x = pos.x() / self.cell_size
        y = pos.y() / self.cell_size
        return x, y

    def get_max_exposure_distance_px(self):
        return 80 + self.sensitivity * 7

    def get_deposit_strength(self):
        return 0.0015 + (self.sensitivity / 100.0) * 0.006

    def get_field_radius_px(self):
        return 35 + self.sensitivity * 1.2

    def deposit_proximity_field(self, p1, p2):
        dx_px = p2.x() - p1.x()
        dy_px = p2.y() - p1.y()
        dist_px = math.hypot(dx_px, dy_px)

        max_dist_px = self.get_max_exposure_distance_px()
        if dist_px >= max_dist_px:
            return

        closeness = 1.0 - (dist_px / max_dist_px)
        closeness = max(0.0, min(1.0, closeness))

        deposit_strength = self.get_deposit_strength() * (closeness ** 2.2)

        if deposit_strength <= 0:
            return

        x1, y1 = self.screen_to_grid_float(p1)
        x2, y2 = self.screen_to_grid_float(p2)

        seg_dx = x2 - x1
        seg_dy = y2 - y1
        seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy

        influence_radius_cells = max(3.0, self.get_field_radius_px() / self.cell_size)
        pad = int(math.ceil(influence_radius_cells))

        min_x = int(max(0, math.floor(min(x1, x2) - pad)))
        max_x = int(min(self.grid_w - 1, math.ceil(max(x1, x2) + pad)))
        min_y = int(max(0, math.floor(min(y1, y2) - pad)))
        max_y = int(min(self.grid_h - 1, math.ceil(max(y1, y2) + pad)))

        if min_x > max_x or min_y > max_y:
            return

        xs = np.arange(min_x, max_x + 1, dtype=np.float32)
        ys = np.arange(min_y, max_y + 1, dtype=np.float32)
        xx, yy = np.meshgrid(xs, ys)

        px = xx + 0.5
        py = yy + 0.5

        if seg_len_sq < 1e-6:
            dist_to_pair = np.sqrt((px - x1) ** 2 + (py - y1) ** 2)
        else:
            t = ((px - x1) * seg_dx + (py - y1) * seg_dy) / seg_len_sq
            t = np.clip(t, 0.0, 1.0)

            proj_x = x1 + t * seg_dx
            proj_y = y1 + t * seg_dy

            dist_to_pair = np.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

        sigma = max(1.5, influence_radius_cells * (0.55 - 0.20 * closeness))
        field = np.exp(-(dist_to_pair ** 2) / (2.0 * sigma * sigma)).astype(np.float32)

        mid_x = (x1 + x2) * 0.5
        mid_y = (y1 + y2) * 0.5
        mid_dist = np.sqrt((px - mid_x) ** 2 + (py - mid_y) ** 2)
        mid_sigma = max(2.0, influence_radius_cells * 0.95)
        mid_weight = np.exp(-(mid_dist ** 2) / (2.0 * mid_sigma * mid_sigma)).astype(np.float32)

        combined = field * (0.65 + 0.35 * mid_weight)
        self.heat[min_y:max_y + 1, min_x:max_x + 1] += combined * deposit_strength

    def decay_heat(self):
        self.heat += (self.base_heat - self.heat) * (1.0 - self.decay_rate)
        np.clip(self.heat, self.base_heat, 1.0, out=self.heat)

    def deposit_exposure_heat(self):
        for dot in self.virtual_dots:
            self.deposit_proximity_field(self.mouse_pos, dot)
        np.clip(self.heat, self.base_heat, 1.0, out=self.heat)

    def rebuild_image(self):
        scaled = np.clip(self.heat * 255.0, 0, 255).astype(np.uint8)
        self._rgb_buffer[:, :, :] = self.lut[scaled]

        h, w, _ = self._rgb_buffer.shape
        bytes_per_line = 3 * w

        self._qimage = QImage(
            self._rgb_buffer.data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_RGB888
        )

    def find_dot_at_pos(self, pos):
        for i in range(len(self.virtual_dots) - 1, -1, -1):
            dot = self.virtual_dots[i]
            dx = dot.x() - pos.x()
            dy = dot.y() - pos.y()
            if dx * dx + dy * dy <= (self.dot_radius_px + 4) ** 2:
                return i
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mouse_pos = event.position()

            if self.place_dot_mode:
                self.virtual_dots.append(QPointF(event.position()))
                self.place_dot_mode = False
                self.update()
                return

            hit = self.find_dot_at_pos(event.position())
            if hit is not None:
                self.selected_dot_index = hit
                self.dragging_dot = True
                self.update()
                return

            self.update()

        elif event.button() == Qt.MouseButton.RightButton:
            hit = self.find_dot_at_pos(event.position())
            if hit is not None:
                del self.virtual_dots[hit]
                self.selected_dot_index = None
                self.dragging_dot = False
                self.update()

    def mouseMoveEvent(self, event):
        self.mouse_pos = event.position()

        if self.dragging_dot and self.selected_dot_index is not None:
            x = max(0.0, min(event.position().x(), self.width() - 1.0))
            y = max(0.0, min(event.position().y(), self.height() - 1.0))
            self.virtual_dots[self.selected_dot_index] = QPointF(x, y)

        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging_dot = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.selected_dot_index is not None:
            if 0 <= self.selected_dot_index < len(self.virtual_dots):
                del self.virtual_dots[self.selected_dot_index]
            self.selected_dot_index = None
            self.dragging_dot = False
            self.update()
            return

        if event.key() == Qt.Key.Key_Escape:
            self.place_dot_mode = False
            self.dragging_dot = False
            self.selected_dot_index = None
            self.update()
            return

        super().keyPressEvent(event)

    def tick(self):
        self.decay_heat()
        self.deposit_exposure_heat()
        self.rebuild_image()
        self.update()

    def draw_crosshair(self, painter, pos):
        x = int(pos.x())
        y = int(pos.y())

        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawLine(x - 20, y, x + 20, y)
        painter.drawLine(x, y - 20, x, y + 20)

        painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
        painter.drawEllipse(x - 8, y - 8, 16, 16)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))

        if not self._qimage.isNull():
            painter.drawImage(
                QRect(0, 0, self.width(), self.height()),
                self._qimage,
                QRect(0, 0, self._qimage.width(), self._qimage.height())
            )

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for i, dot in enumerate(self.virtual_dots):
            selected = i == self.selected_dot_index

            painter.setPen(QPen(QColor(255, 255, 255), 1))
            painter.setBrush(QBrush(QColor(255, 255, 255, 230) if selected else QColor(255, 255, 255, 180)))

            dx = int(dot.x())
            dy = int(dot.y())
            painter.drawEllipse(dx - self.dot_radius_px, dy - self.dot_radius_px, self.dot_radius_px * 2, self.dot_radius_px * 2)

            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawLine(dx - 10, dy, dx + 10, dy)
            painter.drawLine(dx, dy - 10, dx, dy + 10)

            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI", 9))
            painter.drawText(dx + 10, dy - 10, f"D{i + 1}")

        self.draw_crosshair(painter, self.mouse_pos)

        nearest = None
        if self.virtual_dots:
            nearest = min(
                math.hypot(dot.x() - self.mouse_pos.x(), dot.y() - self.mouse_pos.y())
                for dot in self.virtual_dots
            )

        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(12, 24, f"Cursor X: {int(self.mouse_pos.x())}   Y: {int(self.mouse_pos.y())}")
        painter.drawText(12, 44, f"Sensitivity: {self.sensitivity}")
        painter.drawText(12, 64, f"Exposure range: {int(self.get_max_exposure_distance_px())} px")
        painter.drawText(12, 84, f"Virtual dots: {len(self.virtual_dots)}")
        painter.drawText(12, 104, "Closer cursor-to-dot distance adds more heat over time")
        painter.drawText(12, 124, "Heat lingers and slowly cools back to blue")

        if nearest is not None:
            painter.drawText(12, 144, f"Nearest dot distance: {int(nearest)} px")

        painter.drawText(12, 164, "Drag dot to move it, right click or Delete to remove")

        if self.place_dot_mode:
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawText(12, 188, "PLACE DOT MODE: click anywhere on map")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Proximity Heat Map")
        self.resize(1100, 760)

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        self.heat_widget = HeatMapWidget()

        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(12)

        label_title = QLabel("Sensitivity")
        label_title.setStyleSheet("color: white; font-size: 14px;")

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.setValue(20)
        self.slider.valueChanged.connect(self.heat_widget.set_sensitivity)

        self.value_label = QLabel("20")
        self.value_label.setFixedWidth(40)
        self.value_label.setStyleSheet("color: white; font-size: 14px;")
        self.slider.valueChanged.connect(lambda v: self.value_label.setText(str(v)))

        self.place_dot_btn = QPushButton("Place Dot Cursor")
        self.place_dot_btn.clicked.connect(self.activate_place_dot_mode)

        self.clear_dots_btn = QPushButton("Clear Dots")
        self.clear_dots_btn.clicked.connect(self.heat_widget.clear_dots)

        self.reset_heat_btn = QPushButton("Reset Heat")
        self.reset_heat_btn.clicked.connect(self.heat_widget.reset_heat)

        controls_layout.addWidget(label_title)
        controls_layout.addWidget(self.slider, 1)
        controls_layout.addWidget(self.value_label)
        controls_layout.addWidget(self.place_dot_btn)
        controls_layout.addWidget(self.clear_dots_btn)
        controls_layout.addWidget(self.reset_heat_btn)

        main_layout.addLayout(controls_layout)
        main_layout.addWidget(self.heat_widget, 1)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1a1a;
            }
            QWidget {
                background-color: #1a1a1a;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #2c2c2c;
                color: white;
                border: 1px solid #555;
                padding: 6px 12px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
            QSlider::groove:horizontal {
                height: 8px;
                background: #444;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #dddddd;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
        """)

    def activate_place_dot_mode(self):
        self.heat_widget.set_place_dot_mode(True)
        self.heat_widget.setFocus()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())