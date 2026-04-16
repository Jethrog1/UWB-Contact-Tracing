"""
runtime.py - BRIGID calibration workspace runtime.

This ports the non-UI behavior from the legacy `home.py` calibration tool
into a backend session that the TypeScript frontend can drive.
"""

from __future__ import annotations

import asyncio
import math
import sys
import threading
import time
from collections import deque
from datetime import date
from typing import Any, Callable

import numpy as np

from utilities.profilers.calibration_math import build_eval_func, compile_manual_equation
from utilities.profilers.constants import ANCHOR_IDS, FIT_MODES

try:
    import serial
    import serial.tools.list_ports

    HAS_SERIAL = True
except ImportError:  # pragma: no cover - optional dependency
    serial = None
    HAS_SERIAL = False

try:
    from bleak import BleakClient

    HAS_BLEAK = True
except ImportError:  # pragma: no cover - optional dependency
    BleakClient = None
    HAS_BLEAK = False


CHAR_UUID = "deadbeef-0000-0000-0000-000000000001"
ESP32_C6_IDENTIFIERS = [
    ("303a", "1001"),
    ("303a", "4001"),
    ("1a86", "55d4"),
    ("10c4", "ea60"),
    ("0403", "6001"),
]

DEFAULT_ANCHORS: dict[str, list[float]] = {
    "A0": [0.0, 0.0],
    "A1": [0.0, 10.0],
    "A2": [10.0, 10.0],
    "A3": [10.0, 0.0],
}
DEFAULT_LINES: list[tuple[str, str]] = [
    ("A0", "A1"),
    ("A1", "A2"),
    ("A2", "A3"),
    ("A3", "A0"),
]


def _identity(x: float) -> float:
    return float(x)


def _anchor_measurements(default: float = -1.0) -> dict[str, float]:
    return {anchor_id: float(default) for anchor_id in ANCHOR_IDS}


def _anchor_optional_map() -> dict[str, Optional[float]]:
    return {anchor_id: None for anchor_id in ANCHOR_IDS}


def _fit_config() -> dict[str, Any]:
    return {
        "auto": False,
        "fit_mode": "Polynomial",
        "poly_deg": 4,
        "ma_period": 4,
        "ma_type": "Trailing",
    }


def calc_pos(anchor_positions: dict[str, list[float]], distances_dict: dict[str, float]) -> Optional[tuple[float], Optional[float]]:
    valid = [
        (anchor_positions[a][0], anchor_positions[a][1], r)
        for a, r in distances_dict.items()
        if r > 0 and a in anchor_positions
    ]
    if len(valid) < 2:
        return None, None

    if len(valid) == 2:
        x1, y1, r1 = valid[0]
        x2, y2, r2 = valid[1]
        d = math.hypot(x2 - x1, y2 - y1)
        if d == 0 or d > r1 + r2 or d < abs(r1 - r2):
            return None, None
        a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
        h = math.sqrt(max(0.0, r1 * r1 - a * a))
        x3 = x1 + a * (x2 - x1) / d
        y3 = y1 + a * (y2 - y1) / d
        ix1 = x3 + h * (y2 - y1) / d
        iy1 = y3 - h * (x2 - x1) / d
        ix2 = x3 - h * (y2 - y1) / d
        iy2 = y3 + h * (x2 - x1) / d
        cx = sum(point[0] for point in valid) / len(valid)
        cy = sum(point[1] for point in valid) / len(valid)
        if (ix1 - cx) ** 2 + (iy1 - cy) ** 2 < (ix2 - cx) ** 2 + (iy2 - cy) ** 2:
            return round(ix1, 3), round(iy1, 3)
        return round(ix2, 3), round(iy2, 3)

    x0, y0, r0 = valid[0]
    matrix_a: list[list[float]] = []
    matrix_b: list[float] = []
    for xi, yi, ri in valid[1:]:
        matrix_a.append([2 * (xi - x0), 2 * (yi - y0)])
        matrix_b.append(r0 * r0 - ri * ri - x0 * x0 - y0 * y0 + xi * xi + yi * yi)

    a11 = sum(row[0] ** 2 for row in matrix_a)
    a12 = sum(row[0] * row[1] for row in matrix_a)
    a22 = sum(row[1] ** 2 for row in matrix_a)
    b1 = sum(matrix_a[index][0] * matrix_b[index] for index in range(len(matrix_b)))
    b2 = sum(matrix_a[index][1] * matrix_b[index] for index in range(len(matrix_b)))
    det = a11 * a22 - a12 * a12
    if abs(det) < 1e-6:
        return None, None

    return (
        round((a22 * b1 - a12 * b2) / det, 3),
        round((-a12 * b1 + a11 * b2) / det, 3),
    )


def correct_slant_distance(slant_distance: float, height_offset: float) -> float:
    if height_offset <= 0 or slant_distance <= 0:
        return float(slant_distance)
    squared = slant_distance * slant_distance - height_offset * height_offset
    return math.sqrt(max(squared, 0.0001))


class CalibrationRuntime:
    def __init__(self) -> None:
        self._lock = threading.Lock()

        self._mode: Optional[str] = None
        self._transport_status = "idle"
        self._transport_detail = "Disconnected."
        self._selected_port = ""
        self._last_attempting_tag: Optional[str] = None
        self._profile_macs: dict[str, str] = {}
        self._mac_to_tag: dict[str, str] = {}
        self._tag_values: dict[str, dict[str, float]] = {}
        self._tag_status: dict[str, str] = {}
        self._tag_seen_at: dict[str, float] = {}

        self._serial_thread: threading.Optional[Thread] = None
        self._serial_stop = threading.Event()
        self._serial_port_handle: Any = None

        self._ble_thread: threading.Optional[Thread] = None
        self._ble_stop = threading.Event()

        self._reset_session_locked()

    def _reset_session_locked(self) -> None:
        self._anchors = {anchor_id: list(coords) for anchor_id, coords in DEFAULT_ANCHORS.items()}
        self._lines = list(DEFAULT_LINES)
        self._height_offset = 0.0

        self._profile_cache: dict[str, dict[str, Any]] = {}
        self._tag_order: list[str] = []
        self._reference_floor: dict[str, dict[str, Optional[float]]] = {}
        self._reference_height: dict[str, float] = {}
        self._locked_reference: dict[str, dict[str, Optional[float]]] = {}
        self._cal_points: dict[str, dict[str, list[tuple[float, float]]]] = {}
        self._cal_funcs: dict[str, dict[str, Callable[[float], float]]] = {}
        self._equations: dict[str, dict[str, str]] = {}
        self._fit_options: dict[str, dict[str, dict[str, Any]]] = {}
        self._raw_floor: dict[str, dict[str, float]] = {}
        self._calibrated: dict[str, dict[str, float]] = {}
        self._raw_xy: dict[str, tuple[float, Optional[float]]] = {}
        self._cal_xy: dict[str, tuple[float, Optional[float]]] = {}

        self._filter_mode = "EMA"
        self._filt_ema_alpha = 0.2
        self._filt_roll_n = 8
        self._filt_kal_q = 0.1
        self._filt_kal_r = 2.0
        self._ema_pos: dict[str, tuple[float, Optional[float]]] = {}
        self._roll_buf: dict[str, deque[tuple[float, float]]] = {}
        self._kal_state: dict[str, Optional[list[list[float]]]] = {}
        self._kal_p: dict[str, Optional[list[list[float]]]] = {}

        self._capture_active = False
        self._capture_phase = "idle"
        self._capture_tid: Optional[str] = None
        self._capture_target = 0
        self._capture_true: dict[str, float] = {}
        self._capture_buf: dict[str, list[float]] = {}
        self._capture_last_sample_at: dict[str, float] = {}
        self._capture_phase_started_at = 0.0
        self._capture_fuse_frames = 15

    def reset_session(self) -> None:
        with self._lock:
            self._reset_session_locked()

    def shutdown(self) -> None:
        self.disconnect()
        with self._lock:
            self._reset_session_locked()

    def sync_profiles(self, profiles: list[dict]) -> None:
        with self._lock:
            next_order: list[str] = []
            next_cache: dict[str, dict[str, Any]] = {}
            next_macs: dict[str, str] = {}
            next_mac_to_tag: dict[str, str] = {}

            for profile in profiles:
                tag_id = str(profile.get("tag_id", "")).strip()
                if not tag_id:
                    continue

                next_order.append(tag_id)
                next_cache[tag_id] = profile
                self._ensure_tag_locked(tag_id)

                self._tag_values.setdefault(tag_id, _anchor_measurements())
                self._tag_status.setdefault(tag_id, "Disconnected")

                mac_address = str(profile.get("device", {}).get("mac_address", "")).strip()
                next_macs[tag_id] = mac_address
                if mac_address:
                    next_mac_to_tag[mac_address.lower()] = tag_id

            stale_tags = set(self._tag_values) - set(next_order)
            for tag_id in stale_tags:
                self._tag_values.pop(tag_id, None)
                self._tag_status.pop(tag_id, None)
                self._tag_seen_at.pop(tag_id, None)
                self._profile_cache.pop(tag_id, None)
                self._reference_floor.pop(tag_id, None)
                self._reference_height.pop(tag_id, None)
                self._locked_reference.pop(tag_id, None)
                self._cal_points.pop(tag_id, None)
                self._cal_funcs.pop(tag_id, None)
                self._equations.pop(tag_id, None)
                self._fit_options.pop(tag_id, None)
                self._raw_floor.pop(tag_id, None)
                self._calibrated.pop(tag_id, None)
                self._raw_xy.pop(tag_id, None)
                self._cal_xy.pop(tag_id, None)
                self._ema_pos.pop(tag_id, None)
                self._roll_buf.pop(tag_id, None)
                self._kal_state.pop(tag_id, None)
                self._kal_p.pop(tag_id, None)

            if self._capture_tid and self._capture_tid not in next_cache:
                self._cancel_capture_locked()

            self._tag_order = next_order
            self._profile_cache = next_cache
            self._profile_macs = next_macs
            self._mac_to_tag = next_mac_to_tag

    def _ensure_tag_locked(self, tag_id: str) -> None:
        self._reference_floor.setdefault(tag_id, _anchor_optional_map())
        self._reference_height.setdefault(tag_id, 0.0)
        self._locked_reference.setdefault(tag_id, _anchor_optional_map())
        self._cal_points.setdefault(tag_id, {anchor_id: [] for anchor_id in ANCHOR_IDS})
        self._cal_funcs.setdefault(tag_id, {anchor_id: _identity for anchor_id in ANCHOR_IDS})
        self._equations.setdefault(tag_id, {anchor_id: "Raw (no data)" for anchor_id in ANCHOR_IDS})
        self._fit_options.setdefault(tag_id, {anchor_id: _fit_config() for anchor_id in ANCHOR_IDS})
        self._raw_floor.setdefault(tag_id, _anchor_measurements())
        self._calibrated.setdefault(tag_id, _anchor_measurements())
        self._raw_xy.setdefault(tag_id, None)
        self._cal_xy.setdefault(tag_id, None)
        self._ema_pos.setdefault(tag_id, None)
        self._roll_buf.setdefault(tag_id, deque(maxlen=int(self._filt_roll_n)))
        self._kal_state.setdefault(tag_id, None)
        self._kal_p.setdefault(tag_id, None)

    def get_serial_ports(self) -> list[str]:
        if not HAS_SERIAL:
            return []
        try:
            return [port.device for port in serial.tools.list_ports.comports()]
        except Exception:
            return []

    def auto_detect_serial_port(self) -> str:
        if not HAS_SERIAL:
            return ""
        try:
            for port in serial.tools.list_ports.comports():
                vid = f"{port.vid:04x}" if port.vid else ""
                pid = f"{port.pid:04x}" if port.pid else ""
                if any((vid, pid) == pair for pair in ESP32_C6_IDENTIFIERS):
                    return port.device
                desc = (port.description or "").lower()
                if any(token in desc for token in ("esp32", "xiao", "ch343", "cp210", "ft232")):
                    return port.device
        except Exception:
            return ""
        return ""

    def disconnect(self) -> None:
        with self._lock:
            mode = self._mode
            self._mode = None
            self._transport_status = "idle"
            self._transport_detail = "Disconnected."
            self._selected_port = ""
            self._last_attempting_tag = None
            self._cancel_capture_locked()
            for tag_id in self._tag_status:
                self._tag_status[tag_id] = "Disconnected"

        if mode == "serial":
            self._serial_stop.set()
            if self._serial_port_handle and getattr(self._serial_port_handle, "is_open", False):
                try:
                    self._serial_port_handle.close()
                except Exception:
                    pass
            self._serial_port_handle = None
            if self._serial_thread and self._serial_thread.is_alive():
                self._serial_thread.join(timeout=1.0)
            self._serial_thread = None
            self._serial_stop.clear()

        if mode == "ble":
            self._ble_stop.set()
            if self._ble_thread and self._ble_thread.is_alive():
                self._ble_thread.join(timeout=1.5)
            self._ble_thread = None
            self._ble_stop.clear()

    def connect(self, mode: str, profiles: list[dict], port: str = "") -> tuple[bool, str]:
        self.sync_profiles(profiles)
        self.disconnect()

        if mode == "serial":
            if not HAS_SERIAL:
                return False, "pyserial is not installed on the backend."
            resolved_port = port or self.auto_detect_serial_port()
            if not resolved_port:
                return False, "No serial port selected."
            with self._lock:
                self._mode = "serial"
                self._transport_status = "connecting"
                self._transport_detail = f"Connecting to {resolved_port}..."
                self._selected_port = resolved_port
            self._serial_thread = threading.Thread(
                target=self._serial_reader_loop,
                args=(resolved_port, 115200),
                daemon=True,
            )
            self._serial_thread.start()
            return True, f"Connecting to {resolved_port}."

        if mode == "ble":
            if not HAS_BLEAK:
                return False, "bleak is not installed on the backend."
            ble_profiles = {
                str(profile.get("tag_id", "")).strip(): str(profile.get("device", {}).get("mac_address", "")).strip()
                for profile in profiles
            }
            ble_profiles = {tag_id: mac for tag_id, mac in ble_profiles.items() if tag_id and mac}
            if not ble_profiles:
                return False, "No profiled tags have BLE MAC addresses yet."
            with self._lock:
                self._mode = "ble"
                self._transport_status = "connecting"
                self._transport_detail = f"Starting BLE listeners for {len(ble_profiles)} tag(s)..."
            self._ble_thread = threading.Thread(
                target=self._ble_thread_main,
                args=(ble_profiles,),
                daemon=True,
            )
            self._ble_thread.start()
            return True, f"Starting BLE listeners for {len(ble_profiles)} tag(s)."

        return False, f"Unsupported calibration mode: {mode}"

    def update_map(self, anchors: dict[str, list[float]], lines: list[list[str]], height_offset: float) -> tuple[bool, str]:
        normalized_anchors: dict[str, list[float]] = {}
        for anchor_id in ANCHOR_IDS:
            coords = anchors.get(anchor_id)
            if not coords or len(coords) != 2:
                return False, f"Missing coordinates for {anchor_id}."
            try:
                normalized_anchors[anchor_id] = [round(float(coords[0]), 3), round(float(coords[1]), 3)]
            except (TypeError, ValueError):
                return False, f"Invalid coordinates for {anchor_id}."

        normalized_lines: list[tuple[str, str]] = []
        for pair in lines:
            if len(pair) != 2:
                return False, "Lines must contain exactly two anchor ids."
            anchor_a = str(pair[0]).strip()
            anchor_b = str(pair[1]).strip()
            if anchor_a not in ANCHOR_IDS or anchor_b not in ANCHOR_IDS or anchor_a == anchor_b:
                return False, f"Invalid line: {pair}"
            if (anchor_a, anchor_b) in normalized_lines or (anchor_b, anchor_a) in normalized_lines:
                continue
            normalized_lines.append((anchor_a, anchor_b))

        try:
            next_height = max(0.0, float(height_offset))
        except (TypeError, ValueError):
            return False, "Invalid anchor-to-tag height."

        with self._lock:
            self._anchors = normalized_anchors
            self._lines = normalized_lines
            self._height_offset = next_height
            self._reset_all_filters_locked()
        return True, "Map updated."

    def set_reference_distances(
        self,
        tag_id: str,
        distances: dict[str, Optional[float]],
        height: float,
    ) -> tuple[bool, str]:
        with self._lock:
            self._ensure_tag_locked(tag_id)
            for anchor_id in ANCHOR_IDS:
                value = distances.get(anchor_id)
                if value is None:
                    self._reference_floor[tag_id][anchor_id] = None
                else:
                    self._reference_floor[tag_id][anchor_id] = round(float(value), 3)
            self._reference_height[tag_id] = round(float(height), 3)
        return True, "Reference distances updated."

    def place_reference_dot(self, tag_id: str, world_x: float, world_y: float) -> dict[str, float]:
        with self._lock:
            self._ensure_tag_locked(tag_id)
            placed: dict[str, float] = {}
            for anchor_id, coords in self._anchors.items():
                floor_distance = math.hypot(world_x - coords[0], world_y - coords[1])
                self._reference_floor[tag_id][anchor_id] = round(floor_distance, 3)
                placed[anchor_id] = round(floor_distance, 3)
            return placed

    def calculate_reference(self, tag_id: str) -> tuple[bool, str, dict[str, float]]:
        with self._lock:
            self._ensure_tag_locked(tag_id)
            height = self._reference_height[tag_id]
            locked: dict[str, float] = {}
            for anchor_id in ANCHOR_IDS:
                floor_distance = self._reference_floor[tag_id].get(anchor_id)
                if floor_distance is None:
                    return False, f"Fill floor distance for {anchor_id}.", {}
                locked_distance = math.sqrt(floor_distance * floor_distance + height * height)
                self._locked_reference[tag_id][anchor_id] = round(locked_distance, 3)
                locked[anchor_id] = round(locked_distance, 3)
            return True, "Reference locked.", locked

    def update_fit_settings(
        self,
        tag_id: str,
        anchor_id: str,
        *,
        auto: Optional[bool] = None,
        fit_mode: Optional[str] = None,
        poly_deg: Optional[int] = None,
        ma_period: Optional[int] = None,
        ma_type: Optional[str] = None,
    ) -> tuple[bool, str]:
        if anchor_id not in ANCHOR_IDS:
            return False, f"Unknown anchor: {anchor_id}"
        if fit_mode is not None and fit_mode not in FIT_MODES:
            return False, f"Unsupported fit mode: {fit_mode}"

        with self._lock:
            self._ensure_tag_locked(tag_id)
            options = dict(self._fit_options[tag_id][anchor_id])
            if auto is not None:
                options["auto"] = bool(auto)
            if fit_mode is not None:
                options["fit_mode"] = fit_mode
            if poly_deg is not None:
                options["poly_deg"] = max(1, min(10, int(poly_deg)))
            if ma_period is not None:
                options["ma_period"] = max(2, min(10, int(ma_period)))
            if ma_type is not None:
                options["ma_type"] = "Centered" if ma_type == "Centered" else "Trailing"
            self._fit_options[tag_id][anchor_id] = options
            self._recalculate_tag_locked(tag_id)
        return True, "Fit settings updated."

    def set_manual_equation(self, tag_id: str, anchor_id: str, equation: str) -> tuple[bool, str]:
        if anchor_id not in ANCHOR_IDS:
            return False, f"Unknown anchor: {anchor_id}"
        try:
            func = compile_manual_equation(equation)
        except Exception as exc:
            return False, str(exc)

        with self._lock:
            self._ensure_tag_locked(tag_id)
            self._equations[tag_id][anchor_id] = equation.strip() or "Raw (no data)"
            self._cal_funcs[tag_id][anchor_id] = func
        return True, "Equation updated."

    def start_capture(self, tag_id: str, sample_count: int) -> tuple[bool, str]:
        with self._lock:
            self._ensure_tag_locked(tag_id)
            locked_reference = {
                anchor_id: value
                for anchor_id, value in self._locked_reference[tag_id].items()
                if value is not None and value > 0
            }
            if not locked_reference:
                return False, "Calculate Reference distances first before capturing."

            self._capture_active = True
            self._capture_phase = "collect"
            self._capture_tid = tag_id
            self._capture_target = max(1, min(100, int(sample_count)))
            self._capture_true = {anchor_id: float(value) for anchor_id, value in locked_reference.items()}
            self._capture_buf = {anchor_id: [] for anchor_id in locked_reference}
            self._capture_last_sample_at = {anchor_id: 0.0 for anchor_id in locked_reference}
            self._capture_phase_started_at = time.time()
        return True, "Capture started."

    def cancel_capture(self) -> None:
        with self._lock:
            self._cancel_capture_locked()

    def _cancel_capture_locked(self) -> None:
        self._capture_active = False
        self._capture_phase = "idle"
        self._capture_tid = None
        self._capture_target = 0
        self._capture_true = {}
        self._capture_buf = {}
        self._capture_last_sample_at = {}
        self._capture_phase_started_at = 0.0

    def clear_points(self, tag_id: str) -> None:
        with self._lock:
            self._ensure_tag_locked(tag_id)
            for anchor_id in ANCHOR_IDS:
                self._cal_points[tag_id][anchor_id].clear()
                self._equations[tag_id][anchor_id] = "Raw (no data)"
                self._cal_funcs[tag_id][anchor_id] = _identity
            self._recalculate_tag_locked(tag_id)

    def update_filter(
        self,
        mode: str,
        *,
        ema_alpha: Optional[float] = None,
        roll_n: Optional[int] = None,
        kal_q: Optional[float] = None,
        kal_r: Optional[float] = None,
    ) -> tuple[bool, str]:
        if mode not in {"EMA", "Rolling", "Kalman"}:
            return False, f"Unsupported filter mode: {mode}"
        with self._lock:
            self._filter_mode = mode
            if ema_alpha is not None:
                self._filt_ema_alpha = min(1.0, max(0.01, float(ema_alpha)))
            if roll_n is not None:
                self._filt_roll_n = min(30, max(2, int(roll_n)))
            if kal_q is not None:
                self._filt_kal_q = min(2.0, max(0.01, float(kal_q)))
            if kal_r is not None:
                self._filt_kal_r = min(10.0, max(0.1, float(kal_r)))
            self._reset_all_filters_locked()
        return True, "Filter updated."

    def export_profile_equations(self, tag_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_tag_locked(tag_id)
            return {
                "equations": dict(self._equations[tag_id]),
                "last_calibration_date": date.today().isoformat(),
                "equations_enabled": True,
            }

    def snapshot(self, profiles: list[dict]) -> dict[str, Any]:
        self.sync_profiles(profiles)
        now = time.time()
        with self._lock:
            self._tick_capture_locked(now)
            self._update_live_positions_locked(now)
            tags: list[dict[str, Any]] = []
            for tag_id in self._tag_order:
                effective_status = self._effective_tag_status_locked(tag_id, now)
                profile = self._profile_cache.get(tag_id, {})
                saved_equations = profile.get("calibration", {}).get("equations", {}) or {}
                tags.append({
                    "tag_id": tag_id,
                    "name": str(profile.get("identity", {}).get("name", "")).strip(),
                    "device_type": str(profile.get("device", {}).get("device_type", "")).strip(),
                    "mac_address": self._profile_macs.get(tag_id, ""),
                    "status": effective_status,
                    "last_seen_seconds": (
                        round(now - self._tag_seen_at[tag_id], 2)
                        if tag_id in self._tag_seen_at
                        else None
                    ),
                    "raw_distances": dict(self._raw_floor.get(tag_id, _anchor_measurements())),
                    "calibrated_distances": dict(self._calibrated.get(tag_id, _anchor_measurements())),
                    "raw_xy": self._raw_xy.get(tag_id),
                    "calibrated_xy": self._cal_xy.get(tag_id),
                    "reference_floor": dict(self._reference_floor[tag_id]),
                    "reference_height": self._reference_height[tag_id],
                    "locked_reference": dict(self._locked_reference[tag_id]),
                    "equations": dict(self._equations[tag_id]),
                    "saved_profile_equations": {
                        anchor_id: str(saved_equations.get(anchor_id, "") or "")
                        for anchor_id in ANCHOR_IDS
                    },
                    "fit_options": {
                        anchor_id: dict(self._fit_options[tag_id][anchor_id])
                        for anchor_id in ANCHOR_IDS
                    },
                    "points": {
                        anchor_id: [
                            {"measured": round(point[0], 4), "true_dist": round(point[1], 4)}
                            for point in self._cal_points[tag_id][anchor_id]
                        ]
                        for anchor_id in ANCHOR_IDS
                    },
                    "captured_points_log": self._captured_points_log_locked(tag_id),
                    "graph": self._graph_snapshot_locked(tag_id),
                })

            return {
                "mode": self._mode,
                "transport_status": self._transport_status,
                "transport_detail": self._transport_detail,
                "selected_port": self._selected_port,
                "ble_available": HAS_BLEAK,
                "serial_available": HAS_SERIAL,
                "ports": self.get_serial_ports(),
                "auto_detect_port": self.auto_detect_serial_port(),
                "capture": {
                    "active": self._capture_active,
                    "phase": self._capture_phase,
                    "tag_id": self._capture_tid,
                    "target": self._capture_target,
                    "counts": {anchor_id: len(values) for anchor_id, values in self._capture_buf.items()},
                },
                "map": {
                    "anchors": {anchor_id: list(coords) for anchor_id, coords in self._anchors.items()},
                    "lines": [list(line) for line in self._lines],
                    "height_offset": self._height_offset,
                },
                "filter": {
                    "mode": self._filter_mode,
                    "ema_alpha": self._filt_ema_alpha,
                    "roll_n": self._filt_roll_n,
                    "kal_q": self._filt_kal_q,
                    "kal_r": self._filt_kal_r,
                },
                "tags": tags,
            }

    def _captured_points_log_locked(self, tag_id: str) -> list[str]:
        lines: list[str] = []
        for anchor_id in ANCHOR_IDS:
            for index, point in enumerate(self._cal_points[tag_id][anchor_id], start=1):
                lines.append(f"{anchor_id} [{index}]  Raw:{point[0]:.3f} -> True:{point[1]:.3f} ft")
        return lines

    def _graph_snapshot_locked(self, tag_id: str) -> dict[str, Any]:
        graph: dict[str, Any] = {}
        live_burst = self._capture_preview_locked(tag_id)
        for anchor_id in ANCHOR_IDS:
            points = self._cal_points[tag_id][anchor_id]
            fit_line: list[dict[str, float]] = []
            if len(points) >= 2:
                func = self._cal_funcs[tag_id][anchor_id]
                for x in np.linspace(0.01, 30.0, 120):
                    try:
                        fit_line.append({"x": round(float(x), 4), "y": round(float(func(float(x))), 4)})
                    except Exception:
                        fit_line = []
                        break

            live_raw = None
            live_cal = None
            locked_reference = self._locked_reference[tag_id].get(anchor_id)
            raw_distance = self._raw_floor[tag_id].get(anchor_id, -1.0)
            cal_distance = self._calibrated[tag_id].get(anchor_id, -1.0)
            if locked_reference is not None and raw_distance > 0:
                live_raw = {"x": round(raw_distance, 4), "y": round(locked_reference, 4)}
            if locked_reference is not None and cal_distance > 0:
                live_cal = {"x": round(cal_distance, 4), "y": round(locked_reference, 4)}

            graph[anchor_id] = {
                "points": [
                    {"x": round(point[0], 4), "y": round(point[1], 4)}
                    for point in points
                ],
                "fit_line": fit_line,
                "capture": live_burst.get(anchor_id, []),
                "live_raw": live_raw,
                "live_cal": live_cal,
            }
        return graph

    def _capture_preview_locked(self, tag_id: str) -> dict[str, list[dict[str, float]]]:
        if not self._capture_active or self._capture_tid != tag_id:
            return {}

        preview: dict[str, list[dict[str, float]]] = {}
        blend = 0.0
        if self._capture_phase == "fusing":
            elapsed = max(0.0, time.time() - self._capture_phase_started_at)
            blend = min(1.0, elapsed / max(self._capture_fuse_frames * 0.03, 0.01))

        for anchor_id, values in self._capture_buf.items():
            if not values:
                preview[anchor_id] = []
                continue
            target_y = self._capture_true.get(anchor_id, 0.0)
            if self._capture_phase == "fusing":
                mean_value = sum(values) / len(values)
                xs = [value + (mean_value - value) * blend for value in values]
            else:
                xs = list(values)
            preview[anchor_id] = [{"x": round(value, 4), "y": round(target_y, 4)} for value in xs]
        return preview

    def _tick_capture_locked(self, now: float) -> None:
        if not self._capture_active or not self._capture_tid:
            return

        if self._capture_phase == "collect":
            all_done = True
            for anchor_id in self._capture_true:
                values = self._capture_buf.setdefault(anchor_id, [])
                if len(values) < self._capture_target:
                    all_done = False
                    raw_value = self._tag_values.get(self._capture_tid, {}).get(anchor_id, -1.0)
                    last_at = self._capture_last_sample_at.get(anchor_id, 0.0)
                    if raw_value > 0 and (now - last_at) >= 0.08:
                        values.append(raw_value)
                        self._capture_last_sample_at[anchor_id] = now

            if all_done:
                self._capture_phase = "fusing"
                self._capture_phase_started_at = now
            return

        if self._capture_phase == "fusing":
            if (now - self._capture_phase_started_at) < (self._capture_fuse_frames * 0.03):
                return
            for anchor_id, values in self._capture_buf.items():
                if not values:
                    continue
                mean_raw = sum(values) / len(values)
                self._cal_points[self._capture_tid][anchor_id].append((mean_raw, self._capture_true[anchor_id]))
            capture_tag = self._capture_tid
            self._cancel_capture_locked()
            self._recalculate_tag_locked(capture_tag)

    def _recalculate_tag_locked(self, tag_id: str) -> None:
        for anchor_id in ANCHOR_IDS:
            points = self._cal_points[tag_id][anchor_id]
            options = self._fit_options[tag_id][anchor_id]

            if len(points) < 2:
                if not points:
                    self._equations[tag_id][anchor_id] = "Raw (no data)"
                    self._cal_funcs[tag_id][anchor_id] = _identity
                else:
                    offset = points[0][1] - points[0][0]
                    self._equations[tag_id][anchor_id] = f"Raw + {offset:.4f}"
                    self._cal_funcs[tag_id][anchor_id] = lambda x, off=offset: float(x) + off
                continue

            x_values = [point[0] for point in points]
            y_values = [point[1] for point in points]

            if options["auto"]:
                best_error = float("inf")
                best_func: Callable[[float], float] = _identity
                best_equation = "Raw (no data)"
                best_mode = "Linear"
                for mode_name in ["Linear", "Polynomial", "Logarithmic", "Power Series", "Exponential"]:
                    try:
                        func, equation = build_eval_func(
                            mode_name,
                            x_values,
                            y_values,
                            poly_deg=int(options["poly_deg"]),
                        )
                        avg_error = sum(abs(func(x) - y) for x, y in points) / len(points)
                        if avg_error < best_error:
                            best_error = avg_error
                            best_func = func
                            best_equation = f"[Auto:{mode_name}] {equation}"
                            best_mode = mode_name
                    except Exception:
                        continue
                self._cal_funcs[tag_id][anchor_id] = best_func
                self._equations[tag_id][anchor_id] = best_equation
                options["fit_mode"] = best_mode
                continue

            try:
                func, equation = build_eval_func(
                    options["fit_mode"],
                    x_values,
                    y_values,
                    poly_deg=int(options["poly_deg"]),
                    ma_period=int(options["ma_period"]),
                    ma_type=str(options["ma_type"]),
                )
                self._cal_funcs[tag_id][anchor_id] = func
                self._equations[tag_id][anchor_id] = equation
            except Exception:
                self._cal_funcs[tag_id][anchor_id] = _identity
                self._equations[tag_id][anchor_id] = "Error fitting"

    def _effective_tag_status_locked(self, tag_id: str, now: float) -> str:
        status = self._tag_status.get(tag_id, "Disconnected")
        if self._mode == "serial" and self._transport_status == "connected" and status == "Connected":
            seen_at = self._tag_seen_at.get(tag_id)
            if seen_at is None or (now - seen_at) > 4:
                return "Waiting"
        return status

    def _update_live_positions_locked(self, now: float) -> None:
        anchor_positions = {anchor_id: coords for anchor_id, coords in self._anchors.items()}

        for tag_id in self._tag_order:
            effective_status = self._effective_tag_status_locked(tag_id, now)
            if effective_status != "Connected":
                self._raw_floor[tag_id] = _anchor_measurements()
                self._calibrated[tag_id] = _anchor_measurements()
                self._raw_xy[tag_id] = None
                self._cal_xy[tag_id] = None
                self._reset_filter_locked(tag_id)
                continue

            raw_distances = _anchor_measurements()
            for anchor_id in ANCHOR_IDS:
                slant = self._tag_values.get(tag_id, {}).get(anchor_id, -1.0)
                if slant > 0:
                    raw_distances[anchor_id] = round(correct_slant_distance(slant, self._height_offset), 4)

            raw_xy = calc_pos(anchor_positions, raw_distances)
            self._raw_floor[tag_id] = raw_distances
            self._raw_xy[tag_id] = raw_xy if raw_xy[0] is not None else None

            calibrated = _anchor_measurements()
            for anchor_id, floor_distance in raw_distances.items():
                if floor_distance <= 0:
                    continue
                func = self._cal_funcs[tag_id].get(anchor_id, _identity)
                try:
                    calibrated[anchor_id] = round(float(func(floor_distance)), 4)
                except Exception:
                    calibrated[anchor_id] = floor_distance

            self._calibrated[tag_id] = calibrated
            cal_xy = calc_pos(anchor_positions, calibrated)
            if cal_xy[0] is not None and cal_xy[1] is not None:
                smoothed = self._smooth_locked(tag_id, cal_xy[0], cal_xy[1])
                self._cal_xy[tag_id] = (round(smoothed[0], 3), round(smoothed[1], 3))
            else:
                self._cal_xy[tag_id] = None

    def _smooth_locked(self, tag_id: str, raw_x: float, raw_y: float) -> tuple[float, float]:
        if self._filter_mode == "EMA":
            return self._ema_locked(tag_id, raw_x, raw_y)
        if self._filter_mode == "Rolling":
            return self._rolling_locked(tag_id, raw_x, raw_y)
        if self._filter_mode == "Kalman":
            return self._kalman_locked(tag_id, raw_x, raw_y)
        return raw_x, raw_y

    def _ema_locked(self, tag_id: str, raw_x: float, raw_y: float) -> tuple[float, float]:
        previous = self._ema_pos.get(tag_id)
        if previous is None:
            self._ema_pos[tag_id] = (raw_x, raw_y)
        else:
            alpha = self._filt_ema_alpha
            self._ema_pos[tag_id] = (
                alpha * raw_x + (1 - alpha) * previous[0],
                alpha * raw_y + (1 - alpha) * previous[1],
            )
        return self._ema_pos[tag_id] or (raw_x, raw_y)

    def _rolling_locked(self, tag_id: str, raw_x: float, raw_y: float) -> tuple[float, float]:
        buffer = self._roll_buf.setdefault(tag_id, deque(maxlen=int(self._filt_roll_n)))
        if buffer.maxlen != int(self._filt_roll_n):
            self._roll_buf[tag_id] = deque(list(buffer)[-int(self._filt_roll_n):], maxlen=int(self._filt_roll_n))
            buffer = self._roll_buf[tag_id]
        buffer.append((raw_x, raw_y))
        return (
            sum(point[0] for point in buffer) / len(buffer),
            sum(point[1] for point in buffer) / len(buffer),
        )

    def _kalman_locked(self, tag_id: str, raw_x: float, raw_y: float) -> tuple[float, float]:
        q_val = self._filt_kal_q
        r_val = self._filt_kal_r
        delta_t = 0.05

        def matrix_multiply(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
            return [
                [sum(left[row][index] * right[index][col] for index in range(len(right))) for col in range(len(right[0]))]
                for row in range(len(left))
            ]

        def matrix_add(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
            return [
                [left[row][col] + right[row][col] for col in range(len(left[0]))]
                for row in range(len(left))
            ]

        def matrix_subtract(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
            return [
                [left[row][col] - right[row][col] for col in range(len(left[0]))]
                for row in range(len(left))
            ]

        def transpose(matrix: list[list[float]]) -> list[list[float]]:
            return [[matrix[col][row] for col in range(len(matrix))] for row in range(len(matrix[0]))]

        def eye(size: int) -> list[list[float]]:
            return [[1.0 if row == col else 0.0 for col in range(size)] for row in range(size)]

        def inverse_2x2(matrix: list[list[float]]) -> list[list[float]]:
            det = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
            if abs(det) < 1e-9:
                det = 1e-9
            return [
                [matrix[1][1] / det, -matrix[0][1] / det],
                [-matrix[1][0] / det, matrix[0][0] / det],
            ]

        matrix_f = [[1, 0, delta_t, 0], [0, 1, 0, delta_t], [0, 0, 1, 0], [0, 0, 0, 1]]
        matrix_h = [[1, 0, 0, 0], [0, 1, 0, 0]]
        matrix_q = [
            [q_val * delta_t**3 / 3, 0, q_val * delta_t**2 / 2, 0],
            [0, q_val * delta_t**3 / 3, 0, q_val * delta_t**2 / 2],
            [q_val * delta_t**2 / 2, 0, q_val * delta_t, 0],
            [0, q_val * delta_t**2 / 2, 0, q_val * delta_t],
        ]
        matrix_r = [[r_val, 0], [0, r_val]]

        if self._kal_state.get(tag_id) is None:
            self._kal_state[tag_id] = [[raw_x], [raw_y], [0.0], [0.0]]
            self._kal_p[tag_id] = eye(4)

        state = self._kal_state[tag_id]
        covariance = self._kal_p[tag_id]
        if state is None or covariance is None:
            self._kal_state[tag_id] = [[raw_x], [raw_y], [0.0], [0.0]]
            self._kal_p[tag_id] = eye(4)
            return raw_x, raw_y

        predicted_state = matrix_multiply(matrix_f, state)
        predicted_covariance = matrix_add(matrix_multiply(matrix_multiply(matrix_f, covariance), transpose(matrix_f)), matrix_q)
        measurement = [[raw_x], [raw_y]]
        innovation = matrix_subtract(measurement, matrix_multiply(matrix_h, predicted_state))
        innovation_covariance = matrix_add(matrix_multiply(matrix_multiply(matrix_h, predicted_covariance), transpose(matrix_h)), matrix_r)
        kalman_gain = matrix_multiply(matrix_multiply(predicted_covariance, transpose(matrix_h)), inverse_2x2(innovation_covariance))
        next_state = matrix_add(predicted_state, matrix_multiply(kalman_gain, innovation))
        next_covariance = matrix_multiply(matrix_subtract(eye(4), matrix_multiply(kalman_gain, matrix_h)), predicted_covariance)

        self._kal_state[tag_id] = next_state
        self._kal_p[tag_id] = next_covariance
        return next_state[0][0], next_state[1][0]

    def _reset_filter_locked(self, tag_id: str) -> None:
        self._ema_pos[tag_id] = None
        self._roll_buf[tag_id] = deque(maxlen=int(self._filt_roll_n))
        self._kal_state[tag_id] = None
        self._kal_p[tag_id] = None

    def _reset_all_filters_locked(self) -> None:
        for tag_id in self._tag_order:
            self._reset_filter_locked(tag_id)

    def _serial_reader_loop(self, port: str, baud: int) -> None:
        if not HAS_SERIAL:
            return
        try:
            connection = serial.Serial(port, baud, timeout=1)
        except Exception as exc:
            with self._lock:
                if self._mode == "serial":
                    self._transport_status = "error"
                    self._transport_detail = f"Could not open {port}: {exc}"
            return

        with self._lock:
            self._serial_port_handle = connection
            if self._mode == "serial":
                self._transport_status = "connected"
                self._transport_detail = f"Connected: {port}"

        try:
            while not self._serial_stop.is_set():
                try:
                    raw = connection.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    stripped = line.split(" -> ", 1)[1].strip() if " -> " in line else line
                    if stripped.startswith("T") and "|" in stripped:
                        self._parse_measurement_payload(stripped)
                    else:
                        self._parse_status_line(line)
                except Exception as exc:
                    with self._lock:
                        if self._mode == "serial":
                            self._transport_status = "error"
                            self._transport_detail = f"Serial read failed: {exc}"
                    time.sleep(0.5)
        finally:
            try:
                connection.close()
            except Exception:
                pass
            with self._lock:
                self._serial_port_handle = None
                if self._mode == "serial":
                    self._transport_status = "idle"
                    self._transport_detail = "Disconnected."

    def _parse_measurement_payload(self, payload: str, fallback_tag_id: Optional[str] = None) -> None:
        parts = [part.strip() for part in payload.split("|") if part.strip()]
        if not parts:
            return
        tag_id = parts[0] or fallback_tag_id or ""
        if fallback_tag_id and tag_id not in self._tag_values and "|" not in payload:
            tag_id = fallback_tag_id
        if not tag_id:
            return

        with self._lock:
            self._tag_values.setdefault(tag_id, _anchor_measurements())
            self._tag_status[tag_id] = "Connected"
            self._tag_seen_at[tag_id] = time.time()
            for fragment in parts[1:]:
                tokens = fragment.replace(":", " ").split()
                if len(tokens) < 2:
                    continue
                anchor_id, value = tokens[0], tokens[1]
                if anchor_id not in ANCHOR_IDS:
                    continue
                if value.lower() in {"---", "--", "nan"}:
                    self._tag_values[tag_id][anchor_id] = -1.0
                    continue
                try:
                    self._tag_values[tag_id][anchor_id] = float(value)
                except ValueError:
                    self._tag_values[tag_id][anchor_id] = -1.0

    def _parse_status_line(self, line: str) -> None:
        if " -> " in line:
            line = line.split(" -> ", 1)[1].strip()
        stripped = line.strip()

        with self._lock:
            if "[*] Attempting to connect to" in stripped:
                mac = stripped.split("to", 1)[-1].strip().rstrip(".").lower()
                tag_id = self._mac_to_tag.get(mac)
                if tag_id:
                    self._tag_status[tag_id] = "Connecting..."
                    self._last_attempting_tag = tag_id
                return

            if "[+] Connected to" in stripped:
                mac = stripped.split("to", 1)[-1].strip().rstrip("!.").lower()
                tag_id = self._mac_to_tag.get(mac)
                if tag_id:
                    self._tag_status[tag_id] = "Connected"
                    self._last_attempting_tag = None
                return

            if "[-]" in stripped and self._last_attempting_tag:
                self._tag_status[self._last_attempting_tag] = "Disconnected"
                self._tag_values[self._last_attempting_tag] = _anchor_measurements()
                self._last_attempting_tag = None

    def _ble_thread_main(self, profiles: dict[str, str]) -> None:
        if not HAS_BLEAK:
            return
        if sys.platform.startswith("win"):
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass
        asyncio.run(self._ble_main(profiles))

    async def _ble_main(self, profiles: dict[str, str]) -> None:
        tasks = [asyncio.create_task(self._ble_connect_and_listen(tag_id, mac)) for tag_id, mac in profiles.items()]
        with self._lock:
            if self._mode == "ble":
                self._transport_status = "connected"
                self._transport_detail = f"BLE listeners running for {len(tasks)} tag(s)."
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()

    async def _ble_connect_and_listen(self, tag_id: str, mac_address: str) -> None:
        if not HAS_BLEAK:
            return
        while not self._ble_stop.is_set():
            try:
                with self._lock:
                    if self._mode == "ble":
                        self._tag_status[tag_id] = "Connecting..."
                async with BleakClient(mac_address) as client:
                    with self._lock:
                        if self._mode == "ble":
                            self._tag_status[tag_id] = "Connected"
                    await client.start_notify(
                        CHAR_UUID,
                        lambda _sender, data, tid=tag_id: self._parse_measurement_payload(
                            data.decode("utf-8", errors="replace").strip(),
                            fallback_tag_id=tid,
                        ),
                    )
                    while client.is_connected and not self._ble_stop.is_set():
                        await asyncio.sleep(1.0)
            except Exception:
                with self._lock:
                    self._tag_status[tag_id] = "Disconnected"
                    self._tag_values[tag_id] = _anchor_measurements()
                await self._sleep_with_stop(3.0)

    async def _sleep_with_stop(self, seconds: float) -> None:
        deadline = time.time() + seconds
        while not self._ble_stop.is_set() and time.time() < deadline:
            await asyncio.sleep(0.25)
