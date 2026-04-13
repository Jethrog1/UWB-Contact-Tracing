import sys
import math
import random
import os

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPixmap, QFont
)

# based on your current code here: :contentReference[oaicite:0]{index=0}

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
    r"C:\Users\ibesh\Downloads\Untitled design (3).png",
    "/mnt/data/Untitled design (3).png",
)

IMG_LEFT = first_existing_path(
    os.path.join(SCRIPT_DIR, "Untitled design (2).png"),
    r"C:\Users\ibesh\Downloads\Untitled design (2).png",
    "/mnt/data/Untitled design (2).png",
)

IMG_STAND = first_existing_path(
    os.path.join(SCRIPT_DIR, "Untitled design (1).png"),
    r"C:\Users\ibesh\Downloads\Untitled design (1).png",
    "/mnt/data/Untitled design (1).png",
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
CURSOR_COLOR = QColor(255, 255, 255)

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
CURSOR_DIRECTION_HISTORY = 8
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
# Simulated RTLS Tag
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


# ============================================================
# Canvas
# ============================================================

class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)

        self.frames = self._load_frames()

        self.tags = []
        self.next_id = 1

        self.cursor_x = 260.0
        self.cursor_y = 220.0
        self.cursor_prev_x = self.cursor_x
        self.cursor_prev_y = self.cursor_y
        self.cursor_speed = 0.0
        self.cursor_angle = 0.0
        self.cursor_is_walking = False
        self.cursor_walk_phase = 0
        self.cursor_anim_elapsed = 0.0
        self.cursor_direction_samples = []

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(TICK_MS)

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

    def add_dot(self):
        xmin, ymin, xmax, ymax = self._play_rect()
        x = random.uniform(xmin + 100, max(xmin + 101, xmax - 100))
        y = random.uniform(ymin + 100, max(ymin + 101, ymax - 100))
        self.tags.append(Tag(x, y, self.next_id))
        self.next_id += 1

    def mouseMoveEvent(self, event):
        self.cursor_x = event.position().x()
        self.cursor_y = event.position().y()

    def _play_rect(self):
        margin = 50
        top_offset = 10
        return margin, margin + top_offset, self.width() - margin, self.height() - margin

    def _tick(self):
        xmin, ymin, xmax, ymax = self._play_rect()

        for tag in self.tags:
            tag.update(xmin, ymin, xmax, ymax)

        self._update_cursor_animation()
        self.update()

    def _update_cursor_animation(self):
        xmin, ymin, xmax, ymax = self._play_rect()

        self.cursor_x = max(xmin + PERSON_SIZE * 0.42, min(xmax - PERSON_SIZE * 0.42, self.cursor_x))
        self.cursor_y = max(ymin + PERSON_SIZE * 0.42, min(ymax - PERSON_SIZE * 0.42, self.cursor_y))

        dx = self.cursor_x - self.cursor_prev_x
        dy = self.cursor_y - self.cursor_prev_y
        self.cursor_speed = math.hypot(dx, dy)

        if self.cursor_speed > MIN_SPEED_FOR_FACING_UPDATE:
            self.cursor_direction_samples.append((dx, dy))
            if len(self.cursor_direction_samples) > CURSOR_DIRECTION_HISTORY:
                self.cursor_direction_samples.pop(0)

            mean_dir = mean_angle_from_vectors(self.cursor_direction_samples)
            if mean_dir is not None:
                self.cursor_angle = smooth_angle(self.cursor_angle, mean_dir, DIRECTION_SMOOTHING)

        frame_time = speed_to_frame_time(max(self.cursor_speed, STOP_ANIMATION_SPEED + 1e-6))

        if self.cursor_speed <= STOP_ANIMATION_SPEED:
            if self.cursor_anim_elapsed > 0:
                self.cursor_anim_elapsed += TICK_MS / 1000.0
                if self.cursor_anim_elapsed >= frame_time:
                    self.cursor_is_walking = False
                    self.cursor_walk_phase = 0
                    self.cursor_anim_elapsed = 0.0
            else:
                self.cursor_is_walking = False
                self.cursor_walk_phase = 0
        else:
            frame_time = speed_to_frame_time(self.cursor_speed)

            if frame_time is None:
                self.cursor_is_walking = False
                self.cursor_walk_phase = 0
                self.cursor_anim_elapsed = 0.0
            else:
                self.cursor_is_walking = True
                self.cursor_anim_elapsed += TICK_MS / 1000.0

                while self.cursor_anim_elapsed >= frame_time:
                    self.cursor_anim_elapsed -= frame_time
                    self.cursor_walk_phase = 1 - self.cursor_walk_phase

        self.cursor_prev_x = self.cursor_x
        self.cursor_prev_y = self.cursor_y

    def _cursor_frame_name(self):
        if not self.cursor_is_walking:
            return "stand"
        return "left" if self.cursor_walk_phase == 0 else "right"

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = self.width()
        h = self.height()

        p.fillRect(self.rect(), BG_COLOR)

        xmin, ymin, xmax, ymax = self._play_rect()
        self._draw_grid(p, xmin, ymin, xmax, ymax)
        self._draw_box(p, xmin, ymin, xmax, ymax)
        self._draw_anchors(p, xmin, ymin, xmax, ymax)

        for tag in self.tags:
            self._draw_person(p, tag.x, tag.y, tag.angle, tag.current_frame_name())
            self._draw_label(p, tag.x, tag.y, f"T{tag.id}")

        self._draw_person(p, self.cursor_x, self.cursor_y, self.cursor_angle, self._cursor_frame_name())
        self._draw_label(p, self.cursor_x, self.cursor_y, "YOU")

        p.end()

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


# ============================================================
# Main Window
# ============================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RTLS Simulator - Walking Person Animation")
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
        """)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.place_btn = QPushButton("Place Dot")
        layout.addWidget(self.place_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self.canvas = Canvas()
        layout.addWidget(self.canvas, 1)

        self.place_btn.clicked.connect(self.canvas.add_dot)


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