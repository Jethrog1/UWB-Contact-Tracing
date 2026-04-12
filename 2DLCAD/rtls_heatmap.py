import math
from dataclasses import dataclass

try:
    import numpy as np
except ImportError:  # pragma: no cover - graceful fallback if numpy is absent
    np = None

from PyQt6.QtCore import QRect, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter


@dataclass(frozen=True)
class HeatmapTokens:
    cell_size_px: int = 10
    pair_threshold_ft: float = 6.0
    room_pair_threshold_ft: float = 8.0
    base_radius_px: float = 52.0
    radius_gain_px: float = 1.6
    base_strength: float = 0.006
    strength_gain: float = 0.014
    decay_rate: float = 0.92
    opacity: float = 0.36
    room_base_strength: float = 0.014
    room_strength_gain: float = 0.030
    occupant_strength: float = 0.010


class ProximityHeatmapLayer:
    """
    Cached RTLS heat layer.

    The expensive heat field is accumulated in a dedicated offscreen image tied
    to a reference viewport. Normal camera motion then reuses that cached image
    by applying the current viewport transform at paint time instead of
    regenerating the field on every pan/zoom.
    """

    def __init__(self, tokens: HeatmapTokens | None = None):
        self.tokens = tokens or HeatmapTokens()
        self.visible = False
        self.sensitivity = 20

        self._grid_w = 1
        self._grid_h = 1
        self._heat = None
        self._rgb_buffer = None
        self._image = QImage()
        self._lut = self._build_lut()
        self._reference_view = None
        self._buffer_width_px = 1
        self._buffer_height_px = 1
        self._ensure_buffers(1, 1)

    def set_enabled(self, enabled: bool):
        self.visible = enabled

    def is_visible(self) -> bool:
        return self.visible

    def set_sensitivity(self, sensitivity: int):
        self.sensitivity = max(1, min(int(sensitivity), 100))

    def clear(self):
        if self._heat is not None:
            self._heat.fill(0.0)
        self._rebuild_image()

    def rebase_view(self, viewport, width: int, height: int):
        self._reference_view = {
            "scale": float(viewport.scale),
            "offx": float(viewport.offx),
            "offy": float(viewport.offy),
        }
        self._buffer_width_px = int(width)
        self._buffer_height_px = int(height)
        self._ensure_buffers(width, height, force_reset=True)
        self.clear()

    def step(self, tag_positions: dict, viewport, width: int, height: int, rooms=None, accumulate: bool = True):
        """
        Advance the heatmap one frame.

        The heat field is accumulated in the reference-view image so normal
        camera motion can simply transform this cached layer.
        """
        if np is None or width <= 0 or height <= 0:
            return

        self._ensure_reference_view(viewport, width, height)

        if accumulate:
            self._decay()
        else:
            self.clear()
        self._deposit_room_activity(tag_positions, rooms or [])
        self._deposit_pairs(tag_positions)
        self._rebuild_image()

    def paint(self, painter: QPainter, width: int, height: int, viewport):
        if not self.visible or self._image.isNull() or self._reference_view is None:
            return

        ref_scale = self._reference_view["scale"]
        if abs(ref_scale) < 1e-9:
            return

        scale_ratio = float(viewport.scale) / ref_scale
        tx = float(viewport.offx) - scale_ratio * self._reference_view["offx"]
        ty = float(viewport.offy) - scale_ratio * self._reference_view["offy"]

        painter.save()
        painter.setOpacity(self.tokens.opacity)
        painter.translate(tx, ty)
        painter.scale(scale_ratio, scale_ratio)
        painter.drawImage(
            QRectF(
                0,
                0,
                self._image.width() * self.tokens.cell_size_px,
                self._image.height() * self.tokens.cell_size_px,
            ),
            self._image,
        )
        painter.restore()

    def _ensure_reference_view(self, viewport, width: int, height: int):
        if self._reference_view is None:
            self.rebase_view(viewport, width, height)
            return
        if width != self._buffer_width_px or height != self._buffer_height_px:
            self.rebase_view(viewport, width, height)

    def _ensure_buffers(self, width: int, height: int, force_reset: bool = False):
        grid_w = max(1, math.ceil(width / self.tokens.cell_size_px))
        grid_h = max(1, math.ceil(height / self.tokens.cell_size_px))

        if (
            not force_reset
            and self._heat is not None
            and grid_w == self._grid_w
            and grid_h == self._grid_h
        ):
            return

        self._grid_w = grid_w
        self._grid_h = grid_h

        if np is None:
            self._heat = None
            self._rgb_buffer = None
            self._image = QImage()
            return

        self._heat = np.zeros((self._grid_h, self._grid_w), dtype=np.float32)
        self._rgb_buffer = np.zeros((self._grid_h, self._grid_w, 4), dtype=np.uint8)
        self._image = QImage()

    def _build_lut(self):
        if np is None:
            return None

        lut = np.zeros((256, 4), dtype=np.uint8)
        for i in range(256):
            v = i / 255.0
            if v < 0.2:
                t = v / 0.2
                r = int(40 + 20 * t)
                g = int(94 + 80 * t)
                b = int(160 + 55 * t)
                a = int(40 * t)
            elif v < 0.52:
                t = (v - 0.2) / 0.32
                r = int(60 + 40 * t)
                g = int(174 + 36 * t)
                b = int(215 + 10 * t)
                a = int(40 + 85 * t)
            elif v < 0.8:
                t = (v - 0.52) / 0.28
                r = int(100 + 84 * t)
                g = int(210 - 32 * t)
                b = int(225 - 95 * t)
                a = int(125 + 65 * t)
            else:
                t = (v - 0.8) / 0.2
                r = int(184 + 45 * t)
                g = int(178 - 48 * t)
                b = int(130 - 70 * t)
                a = int(190 + 50 * t)
            lut[i] = [r, g, b, a]
        return lut

    def _decay(self):
        self._heat *= self.tokens.decay_rate
        np.clip(self._heat, 0.0, 1.0, out=self._heat)

    def _ref_world_to_screen(self, world_x: float, world_y: float):
        scale = self._reference_view["scale"]
        return (
            world_x * scale + self._reference_view["offx"],
            -world_y * scale + self._reference_view["offy"],
        )

    def _deposit_pairs(self, tag_positions: dict):
        items = list(tag_positions.items())
        threshold_ft = self.tokens.pair_threshold_ft
        radius_px = self.tokens.base_radius_px + self.sensitivity * self.tokens.radius_gain_px
        strength = self.tokens.base_strength + (self.sensitivity / 100.0) * self.tokens.strength_gain

        for i in range(len(items)):
            _, p1 = items[i]
            sx1, sy1 = self._ref_world_to_screen(p1[0], p1[1])
            for j in range(i + 1, len(items)):
                _, p2 = items[j]
                dist_ft = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if dist_ft >= threshold_ft:
                    continue

                sx2, sy2 = self._ref_world_to_screen(p2[0], p2[1])
                closeness = max(0.0, 1.0 - (dist_ft / threshold_ft))
                deposit_strength = strength * (closeness ** 2.0)
                self._deposit_segment_field((sx1, sy1), (sx2, sy2), radius_px, deposit_strength)

        np.clip(self._heat, 0.0, 1.0, out=self._heat)

    def _deposit_room_activity(self, tag_positions: dict, rooms):
        if not rooms:
            return

        room_strength = self.tokens.room_base_strength + (self.sensitivity / 100.0) * self.tokens.room_strength_gain
        occupant_strength = self.tokens.occupant_strength * (0.55 + self.sensitivity / 100.0)

        for room in rooms:
            occupant_points = []
            for _, (world_x, world_y) in tag_positions.items():
                local_x, local_y = room.world_to_local(world_x, world_y)
                if room.contains_local_point_with_tolerance(local_x, local_y, tolerance_ft=1.2):
                    occupant_points.append((world_x, world_y))

            if not occupant_points:
                continue

            area = max(float(room.width) * float(room.height), 1.0)
            occupancy_count = len(occupant_points)
            density_score = min(1.0, occupancy_count / max(area / 55.0, 1.2))
            occupancy_score = min(1.0, occupancy_count / 4.0)
            interaction_score = self._room_interaction_score(occupant_points)

            room_score = (
                0.38 * occupancy_score
                + 0.34 * density_score
                + 0.28 * interaction_score
            )
            if room_score <= 0.0:
                continue

            center_x = room.min_x + room.width * 0.5
            center_y = room.min_y + room.height * 0.5
            screen_x, screen_y = self._ref_world_to_screen(center_x, center_y)
            radius_x = max(32.0, room.width * self._reference_view["scale"] * 0.42)
            radius_y = max(32.0, room.height * self._reference_view["scale"] * 0.42)
            self._deposit_ellipse_field(
                screen_x,
                screen_y,
                radius_x,
                radius_y,
                room_strength * room_score,
            )

            local_density_boost = 0.75 + 0.35 * room_score
            occupant_radius = max(
                18.0,
                self.tokens.base_radius_px * 0.26 + self.sensitivity * self.tokens.radius_gain_px * 0.12,
            )
            for world_x, world_y in occupant_points:
                sx, sy = self._ref_world_to_screen(world_x, world_y)
                self._deposit_radial_field(
                    sx,
                    sy,
                    occupant_radius,
                    occupant_strength * local_density_boost,
                )

        np.clip(self._heat, 0.0, 1.0, out=self._heat)

    def _room_interaction_score(self, occupant_points):
        if len(occupant_points) < 2:
            return 0.0

        close_pairs = 0
        total_pairs = 0
        threshold = self.tokens.room_pair_threshold_ft
        for i in range(len(occupant_points)):
            x1, y1 = occupant_points[i]
            for j in range(i + 1, len(occupant_points)):
                x2, y2 = occupant_points[j]
                total_pairs += 1
                if math.hypot(x2 - x1, y2 - y1) <= threshold:
                    close_pairs += 1
        if total_pairs == 0:
            return 0.0
        return close_pairs / total_pairs

    def _deposit_segment_field(self, p1, p2, radius_px: float, deposit_strength: float):
        x1 = p1[0] / self.tokens.cell_size_px
        y1 = p1[1] / self.tokens.cell_size_px
        x2 = p2[0] / self.tokens.cell_size_px
        y2 = p2[1] / self.tokens.cell_size_px

        seg_dx = x2 - x1
        seg_dy = y2 - y1
        seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy

        influence_cells = max(2.0, radius_px / self.tokens.cell_size_px)
        pad = int(math.ceil(influence_cells))

        min_x = int(max(0, math.floor(min(x1, x2) - pad)))
        max_x = int(min(self._grid_w - 1, math.ceil(max(x1, x2) + pad)))
        min_y = int(max(0, math.floor(min(y1, y2) - pad)))
        max_y = int(min(self._grid_h - 1, math.ceil(max(y1, y2) + pad)))
        if min_x > max_x or min_y > max_y:
            return

        xs = np.arange(min_x, max_x + 1, dtype=np.float32)
        ys = np.arange(min_y, max_y + 1, dtype=np.float32)
        xx, yy = np.meshgrid(xs, ys)
        px = xx + 0.5
        py = yy + 0.5

        if seg_len_sq < 1e-6:
            dist = np.sqrt((px - x1) ** 2 + (py - y1) ** 2)
        else:
            t = ((px - x1) * seg_dx + (py - y1) * seg_dy) / seg_len_sq
            t = np.clip(t, 0.0, 1.0)
            proj_x = x1 + t * seg_dx
            proj_y = y1 + t * seg_dy
            dist = np.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)

        sigma = max(1.25, influence_cells * 0.48)
        field = np.exp(-(dist ** 2) / (2.0 * sigma * sigma)).astype(np.float32)

        mid_x = (x1 + x2) * 0.5
        mid_y = (y1 + y2) * 0.5
        mid_dist = np.sqrt((px - mid_x) ** 2 + (py - mid_y) ** 2)
        mid_sigma = max(1.8, influence_cells * 0.9)
        midpoint_weight = np.exp(-(mid_dist ** 2) / (2.0 * mid_sigma * mid_sigma)).astype(np.float32)

        combined = field * (0.64 + 0.36 * midpoint_weight)
        self._heat[min_y:max_y + 1, min_x:max_x + 1] += combined * deposit_strength

    def _deposit_radial_field(self, screen_x: float, screen_y: float, radius_px: float, deposit_strength: float):
        center_x = screen_x / self.tokens.cell_size_px
        center_y = screen_y / self.tokens.cell_size_px
        influence_cells = max(1.8, radius_px / self.tokens.cell_size_px)
        pad = int(math.ceil(influence_cells))

        min_x = int(max(0, math.floor(center_x - pad)))
        max_x = int(min(self._grid_w - 1, math.ceil(center_x + pad)))
        min_y = int(max(0, math.floor(center_y - pad)))
        max_y = int(min(self._grid_h - 1, math.ceil(center_y + pad)))
        if min_x > max_x or min_y > max_y:
            return

        xs = np.arange(min_x, max_x + 1, dtype=np.float32)
        ys = np.arange(min_y, max_y + 1, dtype=np.float32)
        xx, yy = np.meshgrid(xs, ys)
        px = xx + 0.5
        py = yy + 0.5

        dist = np.sqrt((px - center_x) ** 2 + (py - center_y) ** 2)
        sigma = max(1.1, influence_cells * 0.42)
        field = np.exp(-(dist ** 2) / (2.0 * sigma * sigma)).astype(np.float32)
        self._heat[min_y:max_y + 1, min_x:max_x + 1] += field * deposit_strength

    def _deposit_ellipse_field(
        self,
        screen_x: float,
        screen_y: float,
        radius_x_px: float,
        radius_y_px: float,
        deposit_strength: float,
    ):
        center_x = screen_x / self.tokens.cell_size_px
        center_y = screen_y / self.tokens.cell_size_px
        radius_x = max(2.0, radius_x_px / self.tokens.cell_size_px)
        radius_y = max(2.0, radius_y_px / self.tokens.cell_size_px)
        pad_x = int(math.ceil(radius_x))
        pad_y = int(math.ceil(radius_y))

        min_x = int(max(0, math.floor(center_x - pad_x)))
        max_x = int(min(self._grid_w - 1, math.ceil(center_x + pad_x)))
        min_y = int(max(0, math.floor(center_y - pad_y)))
        max_y = int(min(self._grid_h - 1, math.ceil(center_y + pad_y)))
        if min_x > max_x or min_y > max_y:
            return

        xs = np.arange(min_x, max_x + 1, dtype=np.float32)
        ys = np.arange(min_y, max_y + 1, dtype=np.float32)
        xx, yy = np.meshgrid(xs, ys)
        px = xx + 0.5
        py = yy + 0.5

        norm = ((px - center_x) / radius_x) ** 2 + ((py - center_y) / radius_y) ** 2
        field = np.exp(-norm * 1.75).astype(np.float32)
        self._heat[min_y:max_y + 1, min_x:max_x + 1] += field * deposit_strength

    def _rebuild_image(self):
        if np is None or self._heat is None or self._rgb_buffer is None:
            self._image = QImage()
            return

        scaled = np.clip(self._heat * 255.0, 0, 255).astype(np.uint8)
        self._rgb_buffer[:, :, :] = self._lut[scaled]

        h, w, _ = self._rgb_buffer.shape
        bytes_per_line = 4 * w
        self._image = QImage(
            self._rgb_buffer.data,
            w,
            h,
            bytes_per_line,
            QImage.Format.Format_RGBA8888,
        ).copy()
