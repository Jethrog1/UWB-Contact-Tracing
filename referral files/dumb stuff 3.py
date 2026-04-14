import sys
import math
import random
import os
import numpy as np

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QSlider
)
from PyQt6.QtCore import Qt, QTimer, QPointF, QRect, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QFont, QImage
)

# ============================================================
# Paths
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def first_existing_path(*paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return ""


IMG_RIGHT = first_existing_path(
    os.path.join(SCRIPT_DIR, "Untitled design (3).png"),
    r"C:\RTLS\Pictures\Untitled design (3).png",
)

IMG_LEFT = first_existing_path(
    os.path.join(SCRIPT_DIR, "Untitled design (2).png"),
    r"C:\RTLS\Pictures\Untitled design (2).png"
)

IMG_STAND = first_existing_path(
    os.path.join(SCRIPT_DIR, "Untitled design (1).png"),
    r"C:\RTLS\Pictures\Untitled design (1).png"
)

# ============================================================
# Config
# ============================================================

TICK_MS = 30
PERSON_SIZE = 70

BG_COLOR = QColor(0, 0, 0)
GRID_MAJOR = QColor(70, 70, 70)
GRID_MINOR = QColor(40, 40, 40)
AXIS_COLOR = QColor(120, 120, 120)
ANCHOR_COLOR = QColor(220, 220, 220)

WORLD_STEP = 60

MIN_MOVE_DIST = 80
MAX_MOVE_DIST = 320

MIN_TOP_SPEED = 1.2
MAX_TOP_SPEED = 4.8

MIN_ACCEL = 0.035
MAX_ACCEL = 0.12

STOP_PAUSE_MIN = 12
STOP_PAUSE_MAX = 45

FRAME_BASE_TIME = 0.35
STOP_ANIMATION_SPEED = 0.1
MIN_SPEED_FOR_FACING_UPDATE = 0.15

DIRECTION_SMOOTHING = 0.18
TAG_DIRECTION_HISTORY = 8

# ============================================================
# Helpers
# ============================================================

def wrap_angle(angle):
    while angle <= -math.pi:
        angle += 2 * math.pi
    while angle > math.pi:
        angle -= 2 * math.pi
    return angle


def smooth_angle(current, target, amount):
    diff = wrap_angle(target - current)
    return current + diff * amount


def mean_angle_from_vectors(vectors):
    if not vectors:
        return None
    sx = 0.0
    sy = 0.0
    for dx, dy in vectors:
        sx += dx
        sy += dy
    if abs(sx) < 1e-9 and abs(sy) < 1e-9:
        return None
    return math.atan2(sy, sx)


def speed_to_frame_time(speed):
    if speed <= STOP_ANIMATION_SPEED:
        return None
    if speed < 1.0:
        return FRAME_BASE_TIME
    if speed < 2.0:
        return FRAME_BASE_TIME * 0.85
    if speed < 3.0:
        return FRAME_BASE_TIME * 0.7
    if speed < 4.0:
        return FRAME_BASE_TIME * 0.55
    if speed < 5.0:
        return FRAME_BASE_TIME * 0.45
    return FRAME_BASE_TIME * 0.35


# ============================================================
# Simulated person
# ============================================================

class Tag:
    def __init__(self, x: float, y: float, tag_id: int):
        self.id = tag_id
        self.x = x
        self.y = y
        self.prev_x = x
        self.prev_y = y

        self.vx = 0.0
        self.vy = 0.0
        self.speed = 0.0
        self.angle = 0.0

        self.target_angle = 0.0
        self.target_distance = 0.0
        self.distance_traveled = 0.0
        self.top_speed = 0.0
        self.accel = 0.0
        self.pause_ticks = 0

        self.is_walking = False
        self.walk_phase = 0
        self.anim_elapsed = 0.0

        self.direction_samples = []
        self._pick_new_motion()

    def _pick_new_motion(self):
        self.target_angle = random.uniform(0, math.tau)
        self.target_distance = random.uniform(MIN_MOVE_DIST, MAX_MOVE_DIST)
        self.distance_traveled = 0.0
        self.top_speed = random.uniform(MIN_TOP_SPEED, MAX_TOP_SPEED)
        self.accel = random.uniform(MIN_ACCEL, MAX_ACCEL)
        self.pause_ticks = random.randint(STOP_PAUSE_MIN, STOP_PAUSE_MAX)

    def _update_animation(self):
        frame_time = speed_to_frame_time(max(self.speed, STOP_ANIMATION_SPEED + 1e-6))

        if self.speed <= STOP_ANIMATION_SPEED:
            if self.anim_elapsed > 0:
                self.anim_elapsed += TICK_MS / 1000.0
                if self.anim_elapsed >= frame_time:
                    self.is_walking = False
                    self.walk_phase = 0
                    self.anim_elapsed = 0.0
            else:
                self.is_walking = False
                self.walk_phase = 0
            return

        self.is_walking = True
        self.anim_elapsed += TICK_MS / 1000.0

        while self.anim_elapsed >= frame_time:
            self.anim_elapsed -= frame_time
            self.walk_phase = 1 - self.walk_phase

    def current_frame_name(self):
        if not self.is_walking:
            return "stand"
        return "left" if self.walk_phase == 0 else "right"

    def update(self, xmin: float, ymin: float, xmax: float, ymax: float):
        self.prev_x = self.x
        self.prev_y = self.y

        if self.pause_ticks > 0:
            self.pause_ticks -= 1
            self.speed = max(0.0, self.speed - self.accel * 1.4)
        else:
            remaining = self.target_distance - self.distance_traveled
            brake_distance = (self.speed * self.speed) / (2.0 * max(self.accel, 1e-6))

            if remaining <= brake_distance:
                self.speed = max(0.0, self.speed - self.accel)
            else:
                self.speed = min(self.top_speed, self.speed + self.accel)

        self.vx = math.cos(self.target_angle) * self.speed
        self.vy = math.sin(self.target_angle) * self.speed

        self.x += self.vx
        self.y += self.vy
        self.distance_traveled += math.hypot(self.vx, self.vy)

        margin = PERSON_SIZE * 0.42
        bounced = False

        if self.x < xmin + margin:
            self.x = xmin + margin
            self.target_angle = math.pi - self.target_angle
            bounced = True
        if self.x > xmax - margin:
            self.x = xmax - margin
            self.target_angle = math.pi - self.target_angle
            bounced = True
        if self.y < ymin + margin:
            self.y = ymin + margin
            self.target_angle = -self.target_angle
            bounced = True
        if self.y > ymax - margin:
            self.y = ymax - margin
            self.target_angle = -self.target_angle
            bounced = True

        if bounced:
            self.target_angle %= math.tau

        dx = self.x - self.prev_x
        dy = self.y - self.prev_y
        inst_speed = math.hypot(dx, dy)

        if inst_speed > MIN_SPEED_FOR_FACING_UPDATE:
            self.direction_samples.append((dx, dy))
            if len(self.direction_samples) > TAG_DIRECTION_HISTORY:
                self.direction_samples.pop(0)

            mean_dir = mean_angle_from_vectors(self.direction_samples)
            if mean_dir is not None:
                self.angle = smooth_angle(self.angle, mean_dir, DIRECTION_SMOOTHING)

        if self.pause_ticks == 0 and self.speed <= 0.01 and self.distance_traveled >= self.target_distance:
            self._pick_new_motion()

        self._update_animation()

    def set_position(self, x, y):
        self.x = x
        self.y = y
        self.prev_x = x
        self.prev_y = y
        self.vx = 0.0
        self.vy = 0.0
        self.speed = 0.0
        self.is_walking = False
        self.walk_phase = 0
        self.anim_elapsed = 0.0
        self.direction_samples.clear()
        self._pick_new_motion()


# ============================================================
# Canvas
# ============================================================

class CrowdHeatMapCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.frames = self._load_frames()

        self.tags = []
        self.next_id = 1

        self.selected_index = None
        self.dragging = False
        self.place_person_mode = False

        self.base_heat = 0.08
        self.cell_size = 4
        self.grid_w = 1
        self.grid_h = 1
        self.heat = np.full((1, 1), self.base_heat, dtype=np.float32)

        self.sensitivity = 20
        self.decay_rate = 0.992

        self._rgb_buffer = np.zeros((1, 1, 3), dtype=np.uint8)
        self._qimage = QImage()
        self.lut = self.build_lut()

        self.resize_heat_array()
        self.rebuild_image()

        for _ in range(6):
            self.add_dot()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(TICK_MS)

    # --------------------------------------------------------
    # Sprites
    # --------------------------------------------------------

    def _load_frames(self):
        frames = {}

        stand = QPixmap(IMG_STAND)
        if stand.isNull():
            stand = self._make_fallback_pixmap("stand")

        left = QPixmap(IMG_LEFT)
        if left.isNull():
            left = self._make_fallback_pixmap("left")

        right = QPixmap(IMG_RIGHT)
        if right.isNull():
            right = self._make_fallback_pixmap("right")

        frames["stand"] = stand
        frames["left"] = left
        frames["right"] = right
        return frames

    @staticmethod
    def _make_fallback_pixmap(frame_name: str):
        px = QPixmap(72, 72)
        px.fill(Qt.GlobalColor.transparent)

        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(Qt.GlobalColor.white, 3))
        p.setBrush(Qt.BrushStyle.NoBrush)

        p.drawEllipse(24, 4, 18, 18)
        p.drawLine(33, 22, 33, 48)
        p.drawLine(20, 31, 46, 31)

        if frame_name == "left":
            p.drawLine(33, 48, 22, 64)
            p.drawLine(33, 48, 45, 57)
        elif frame_name == "right":
            p.drawLine(33, 48, 26, 57)
            p.drawLine(33, 48, 48, 64)
        else:
            p.drawLine(33, 48, 25, 62)
            p.drawLine(33, 48, 41, 62)

        p.end()
        return px

    # --------------------------------------------------------
    # Heat map
    # --------------------------------------------------------

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

    def screen_to_grid_float(self, x, y):
        return x / self.cell_size, y / self.cell_size

    def get_max_exposure_distance_px(self):
        return 80 + self.sensitivity * 7

    def get_deposit_strength(self):
        return 0.0015 + (self.sensitivity / 100.0) * 0.006

    def get_field_radius_px(self):
        return 35 + self.sensitivity * 1.2

    def deposit_proximity_field(self, p1, p2):
        dx_px = p2[0] - p1[0]
        dy_px = p2[1] - p1[1]
        dist_px = math.hypot(dx_px, dy_px)

        max_dist_px = self.get_max_exposure_distance_px()
        if dist_px >= max_dist_px:
            return

        closeness = 1.0 - (dist_px / max_dist_px)
        closeness = max(0.0, min(1.0, closeness))

        deposit_strength = self.get_deposit_strength() * (closeness ** 2.2)
        if deposit_strength <= 0:
            return

        x1, y1 = self.screen_to_grid_float(p1[0], p1[1])
        x2, y2 = self.screen_to_grid_float(p2[0], p2[1])

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

    def deposit_all_pair_heat(self):
        n = len(self.tags)
        for i in range(n):
            p1 = (self.tags[i].x, self.tags[i].y)
            for j in range(i + 1, n):
                p2 = (self.tags[j].x, self.tags[j].y)
                self.deposit_proximity_field(p1, p2)
        np.clip(self.heat, self.base_heat, 1.0, out=self.heat)

    # --------------------------------------------------------
    # General canvas logic
    # --------------------------------------------------------

    def _play_rect(self):
        margin = 50
        top_offset = 10
        return margin, margin + top_offset, self.width() - margin, self.height() - margin

    def resizeEvent(self, event):
        self.resize_heat_array()
        self.rebuild_image()
        super().resizeEvent(event)

    def add_dot(self):
        xmin, ymin, xmax, ymax = self._play_rect()
        x = random.uniform(xmin + 100, max(xmin + 101, xmax - 100))
        y = random.uniform(ymin + 100, max(ymin + 101, ymax - 100))
        self.tags.append(Tag(x, y, self.next_id))
        self.next_id += 1
        self.update()

    def add_dot_at(self, x, y):
        self.tags.append(Tag(x, y, self.next_id))
        self.next_id += 1
        self.update()

    def clear_people(self):
        self.tags.clear()
        self.selected_index = None
        self.dragging = False
        self.update()

    def reset_heat(self):
        self.heat.fill(self.base_heat)
        self.rebuild_image()
        self.update()

    def set_sensitivity(self, value):
        self.sensitivity = value

    def find_person_at_pos(self, pos):
        for i in range(len(self.tags) - 1, -1, -1):
            dx = self.tags[i].x - pos.x()
            dy = self.tags[i].y - pos.y()
            if dx * dx + dy * dy <= (PERSON_SIZE * 0.38) ** 2:
                return i
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.place_person_mode:
                xmin, ymin, xmax, ymax = self._play_rect()
                x = max(xmin + PERSON_SIZE * 0.42, min(xmax - PERSON_SIZE * 0.42, event.position().x()))
                y = max(ymin + PERSON_SIZE * 0.42, min(ymax - PERSON_SIZE * 0.42, event.position().y()))
                self.add_dot_at(x, y)
                self.place_person_mode = False
                return

            hit = self.find_person_at_pos(event.position())
            if hit is not None:
                self.selected_index = hit
                self.dragging = True
                self.update()

        elif event.button() == Qt.MouseButton.RightButton:
            hit = self.find_person_at_pos(event.position())
            if hit is not None:
                del self.tags[hit]
                self.selected_index = None
                self.dragging = False
                self.update()

    def mouseMoveEvent(self, event):
        if self.dragging and self.selected_index is not None and 0 <= self.selected_index < len(self.tags):
            xmin, ymin, xmax, ymax = self._play_rect()
            x = max(xmin + PERSON_SIZE * 0.42, min(xmax - PERSON_SIZE * 0.42, event.position().x()))
            y = max(ymin + PERSON_SIZE * 0.42, min(ymax - PERSON_SIZE * 0.42, event.position().y()))
            self.tags[self.selected_index].set_position(x, y)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.selected_index is not None:
            if 0 <= self.selected_index < len(self.tags):
                del self.tags[self.selected_index]
            self.selected_index = None
            self.dragging = False
            self.update()
            return

        if event.key() == Qt.Key.Key_Escape:
            self.place_person_mode = False
            self.dragging = False
            self.selected_index = None
            self.update()
            return

        super().keyPressEvent(event)

    def _tick(self):
        xmin, ymin, xmax, ymax = self._play_rect()

        for i, tag in enumerate(self.tags):
            if not (self.dragging and i == self.selected_index):
                tag.update(xmin, ymin, xmax, ymax)

        self.decay_heat()
        self.deposit_all_pair_heat()
        self.rebuild_image()
        self.update()

    # --------------------------------------------------------
    # Drawing
    # --------------------------------------------------------

    def _draw_grid(self, p: QPainter, xmin: int, ymin: int, xmax: int, ymax: int):
        minor = WORLD_STEP // 3

        p.setPen(QPen(GRID_MINOR, 1))
        x = xmin
        while x <= xmax:
            p.drawLine(x, ymin, x, ymax)
            x += minor

        y = ymin
        while y <= ymax:
            p.drawLine(xmin, y, xmax, y)
            y += minor

        p.setPen(QPen(GRID_MAJOR, 1))
        x = xmin
        while x <= xmax:
            p.drawLine(x, ymin, x, ymax)
            x += WORLD_STEP

        y = ymin
        while y <= ymax:
            p.drawLine(xmin, y, xmax, y)
            y += WORLD_STEP

        cx = (xmin + xmax) // 2
        cy = (ymin + ymax) // 2

        p.setPen(QPen(AXIS_COLOR, 2))
        p.drawLine(xmin, cy, xmax, cy)
        p.drawLine(cx, ymin, cx, ymax)

    def _draw_box(self, p: QPainter, xmin: int, ymin: int, xmax: int, ymax: int):
        p.setPen(QPen(QColor(150, 150, 150), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(xmin, ymin, xmax - xmin, ymax - ymin)

    def _draw_anchors(self, p: QPainter, xmin: int, ymin: int, xmax: int, ymax: int):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(ANCHOR_COLOR))
        for x, y in [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]:
            p.drawEllipse(QPointF(x, y), 5, 5)

    def _draw_person(self, p: QPainter, x: float, y: float, angle: float, frame_name: str):
        sprite = self.frames[frame_name]
        scaled = sprite.scaled(
            PERSON_SIZE, PERSON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        p.save()
        p.translate(x, y)
        p.rotate(math.degrees(angle))
        sw = scaled.width()
        sh = scaled.height()
        p.drawPixmap(-sw // 2, -sh // 2, scaled)
        p.restore()

    def _draw_label(self, p: QPainter, x: float, y: float, text: str):
        tx = int(x) + PERSON_SIZE // 2 + 6
        ty = int(y) - 5
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.drawText(tx, ty, text)

    def nearest_pair_distance(self):
        if len(self.tags) < 2:
            return None
        best = None
        for i in range(len(self.tags)):
            for j in range(i + 1, len(self.tags)):
                d = math.hypot(self.tags[i].x - self.tags[j].x, self.tags[i].y - self.tags[j].y)
                if best is None or d < best:
                    best = d
        return best

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.fillRect(self.rect(), BG_COLOR)

        if not self._qimage.isNull():
            p.drawImage(
                QRect(0, 0, self.width(), self.height()),
                self._qimage,
                QRect(0, 0, self._qimage.width(), self._qimage.height())
            )

        xmin, ymin, xmax, ymax = self._play_rect()
        self._draw_box(p, xmin, ymin, xmax, ymax)
        self._draw_anchors(p, xmin, ymin, xmax, ymax)

        for i, tag in enumerate(self.tags):
            self._draw_person(p, tag.x, tag.y, tag.angle, tag.current_frame_name())
            self._draw_label(p, tag.x, tag.y, f"T{tag.id}")

            if i == self.selected_index:
                p.setPen(QPen(QColor(255, 255, 255), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(tag.x, tag.y), PERSON_SIZE * 0.32, PERSON_SIZE * 0.32)

        p.setPen(QPen(QColor(255, 255, 255), 1))
        p.setFont(QFont("Courier New", 9))

        nearest = self.nearest_pair_distance()
        lines = [
            f"Sensitivity: {self.sensitivity}",
            f"Exposure range: {int(self.get_max_exposure_distance_px())} px",
            f"People: {len(self.tags)}",
            "Heat increases when any two people get too close",
            "Drag person to move, right click or Delete to remove"
        ]

        if nearest is not None:
            lines.append(f"Nearest pair: {int(nearest)} px")

        if self.place_person_mode:
            lines.append("PLACE DOT MODE: click inside the box")

        y = 22
        for line in lines:
            p.drawText(12, y, line)
            y += 18

        p.end()


# ============================================================
# Main Window
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTLS Simulator - Walking People + Heat Map")
        self._build_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        root.setStyleSheet("""
            QWidget {
                background: #000000;
                color: #ffffff;
                font-family: "Courier New";
            }
            QPushButton {
                background: #111111;
                border: 1px solid #666666;
                color: #ffffff;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background: #1a1a1a;
            }
            QLabel {
                color: #ffffff;
            }
            QSlider::groove:horizontal {
                background: #333333;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
        """)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)

        self.place_btn = QPushButton("Place Dot")
        self.add_random_btn = QPushButton("Add Random")
        self.clear_btn = QPushButton("Clear")
        self.reset_heat_btn = QPushButton("Reset Heat")

        top.addWidget(self.place_btn)
        top.addWidget(self.add_random_btn)
        top.addWidget(self.clear_btn)
        top.addWidget(self.reset_heat_btn)

        top.addSpacing(14)
        top.addWidget(QLabel("Sensitivity"))

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.setValue(20)

        self.slider_value = QLabel("20")
        self.slider_value.setFixedWidth(35)

        top.addWidget(self.slider, 1)
        top.addWidget(self.slider_value)

        layout.addLayout(top)

        self.canvas = CrowdHeatMapCanvas()
        layout.addWidget(self.canvas, 1)

        self.place_btn.clicked.connect(self.activate_place_mode)
        self.add_random_btn.clicked.connect(self.canvas.add_dot)
        self.clear_btn.clicked.connect(self.canvas.clear_people)
        self.reset_heat_btn.clicked.connect(self.canvas.reset_heat)
        self.slider.valueChanged.connect(self.canvas.set_sensitivity)
        self.slider.valueChanged.connect(lambda v: self.slider_value.setText(str(v)))

    def activate_place_mode(self):
        self.canvas.place_person_mode = True
        self.canvas.selected_index = None
        self.canvas.dragging = False
        self.canvas.update()


# ============================================================
# Main
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RTLS Simulator")

    screen = app.primaryScreen().availableGeometry()
    margin = 20

    win = MainWindow()
    win.setGeometry(
        screen.x() + margin,
        screen.y() + margin,
        max(800, screen.width() - margin * 2),
        max(600, screen.height() - margin * 2),
    )
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()