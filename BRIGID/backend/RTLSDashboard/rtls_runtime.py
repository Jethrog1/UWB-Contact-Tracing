"""
rtls_runtime.py — Headless BRIGID RTLS Runtime
================================================
Preserves all real logic from rtls_main_official.py / home_rtls.py:
  - parse_and_store / parse_dongle_status
  - serial_reader_thread / start_serial / stop_serial
  - calc_pos_multi  (bi/tri/multi-lateration, height projection)
  - apply_ema / apply_rolling / apply_kalman / smooth / reset_filter_state
  - loop() logic (position solve → smooth → snapshot)
  - CSV distance logging (ported from home_rtls.py)

Changes from original:
  - Tkinter / terminal UI removed
  - Tags are profile-driven (no hardcoded T0/T1/T2)
  - Anchors come from workspace room data (not global ANCHORS constant)
  - Anchor IDs mapped: room IDs (R1A0) → serial IDs (A0) via hw_id
  - Anchor coords converted from local (room-relative) to world (CAD-absolute)
  - Tag height is per-tag (|anchor_z - tag_z|) or global override
  - CSV output directed to workspace RTLS/ folder
  - State exposed via snapshot() dict for frontend polling
"""

from __future__ import annotations

import asyncio
import csv
import math
import os
import re
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import serial
import serial.tools.list_ports

from utilities.profilers.calibration_math import compile_manual_equation

try:
    from bleak import BleakClient

    HAS_BLEAK = True
except ImportError:
    BleakClient = None
    HAS_BLEAK = False

# ── ESP32-C6 auto-detect identifiers (same as original) ───────────────────────
ESP32_C6_IDENTIFIERS = [
    ("303a", "1001"),
    ("303a", "4001"),
    ("1a86", "55d4"),
    ("10c4", "ea60"),
    ("0403", "6001"),
]
CHAR_UUID = "deadbeef-0000-0000-0000-000000000001"
HOME_PY_BLE_ORDER = ("T0", "T1", "T2")

DEVICE_HEIGHT_FIELD_MAP = {
    "Wrist Band": "wrist_to_floor_ft",
    "Arm Band": "arm_to_floor_ft",
    "Belt Clip-on": "hip_to_floor_ft",
    "Breast Pocket": "breast_to_floor_ft",
}


def _normalize_ble_mac(value: str) -> str:
    return str(value or "").strip().replace("-", ":").upper()


def _home_py_ble_sort_key(tag_id: str) -> tuple[int, str]:
    text = str(tag_id or "").strip().upper()
    if text in HOME_PY_BLE_ORDER:
        return (0, f"{HOME_PY_BLE_ORDER.index(text):02d}")
    return (1, text)


def _anchor_key_candidates(anchor_id: str) -> list[str]:
    raw = str(anchor_id or "").strip()
    if not raw:
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(candidate: str) -> None:
        text = str(candidate or "").strip()
        if text and text not in seen:
            seen.add(text)
            candidates.append(text)

    _add(raw)
    upper = raw.upper()
    _add(upper)
    if "A" in upper:
        _add(upper[upper.rfind("A"):])
    return candidates


def _resolve_anchor_equation(equations: dict[str, Any], anchor_id: str) -> tuple[str, str]:
    if not isinstance(equations, dict):
        return "", ""

    for candidate in _anchor_key_candidates(anchor_id):
        expr = str(equations.get(candidate, "")).strip()
        if expr:
            return candidate, expr

    normalized = {candidate.casefold() for candidate in _anchor_key_candidates(anchor_id)}
    for key, expr in equations.items():
        key_text = str(key or "").strip()
        if key_text and key_text.casefold() in normalized:
            expr_text = str(expr or "").strip()
            if expr_text:
                return key_text, expr_text
    return "", ""


def auto_detect_esp32_port() -> Optional[str]:
    """Scan COM ports for ESP32-C6. Returns device path or None."""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        vid = f"{p.vid:04x}" if p.vid else ""
        pid = f"{p.pid:04x}" if p.pid else ""
        for ev, ep in ESP32_C6_IDENTIFIERS:
            if vid == ev and pid == ep:
                return p.device
        desc = (p.description or "").lower()
        if any(k in desc for k in ("esp32", "xiao", "ch343", "cp210", "ft232")):
            return p.device
    return None


# ── Multi-lateration (preserved verbatim from rtls_main_official.py) ──────────
def calc_pos_multi(
    distances_dict: dict[str, float],
    anchors: dict[str, tuple[float, float]],
    anchor_z: dict[str, Optional[float]] = None,
    tag_z: float = 0.0,
) -> Optional[tuple[float], Optional[float]]:
    """
    Calculate 2-D position from anchor distances using bi/tri/multi-lateration.

    distances_dict : {anchor_id: measured_distance_ft}
    anchors        : {anchor_id: (x_ft, y_ft)}
    anchor_z       : {anchor_id: z_ft}  — per-anchor elevation (ceiling/wall mount height)
    tag_z          : tag height from floor (ft) from device profile

    For each anchor the 3-D slant distance is projected to the 2-D floor plane via:
        h = abs(anchor_z[a_id] - tag_z)          ← per-anchor, NOT a global mean
        r_2d = sqrt(r^2 - h^2)

    Returns (x, y) in feet, or (None, None) when insufficient data.
    """
    valid: list[tuple[float, float, float]] = []
    for a_id, r in distances_dict.items():
        if r > 0.0 and a_id in anchors:
            h = abs((anchor_z.get(a_id, 0.0) if anchor_z else 0.0) - tag_z)
            if r > h:
                r_2d = math.sqrt(r ** 2 - h ** 2)
            else:
                r_2d = 0.01
            valid.append((anchors[a_id][0], anchors[a_id][1], r_2d))

    if len(valid) < 2:
        return None, None

    if len(valid) == 2:
        # Bi-lateration — two circle intersections, pick closer to room centre
        x1, y1, r1 = valid[0]
        x2, y2, r2 = valid[1]
        d = math.hypot(x2 - x1, y2 - y1)
        if d == 0:
            return None, None

        a = (r1 ** 2 - r2 ** 2 + d ** 2) / (2 * d)
        a = max(-r1, min(r1, a))

        h2 = r1 ** 2 - a ** 2
        h = math.sqrt(h2) if h2 > 0.0 else 0.0
        x3 = x1 + a * (x2 - x1) / d
        y3 = y1 + a * (y2 - y1) / d
        ix1 = x3 + h * (y2 - y1) / d
        iy1 = y3 - h * (x2 - x1) / d
        ix2 = x3 - h * (y2 - y1) / d
        iy2 = y3 + h * (x2 - x1) / d

        # Pick the point closer to the centroid of known anchors
        all_x = [v[0] for v in valid]
        all_y = [v[1] for v in valid]
        cx = sum(all_x) / len(all_x)
        cy = sum(all_y) / len(all_y)

        def dist_to_centre(px: float, py: float) -> float:
            return (px - cx) ** 2 + (py - cy) ** 2

        if dist_to_centre(ix1, iy1) < dist_to_centre(ix2, iy2):
            return round(ix1, 3), round(iy1, 3)
        return round(ix2, 3), round(iy2, 3)

    # Tri/multi-lateration — linear least squares (preserved from original)
    x0, y0, r0 = valid[0]
    A: list[list[float]] = []
    B: list[float] = []
    for i in range(1, len(valid)):
        xi, yi, ri = valid[i]
        A.append([2 * (xi - x0), 2 * (yi - y0)])
        B.append(r0 ** 2 - ri ** 2 - x0 ** 2 - y0 ** 2 + xi ** 2 + yi ** 2)

    a11 = sum(row[0] * row[0] for row in A)
    a12 = sum(row[0] * row[1] for row in A)
    a21 = a12
    a22 = sum(row[1] * row[1] for row in A)
    b1 = sum(A[i][0] * B[i] for i in range(len(B)))
    b2 = sum(A[i][1] * B[i] for i in range(len(B)))

    det = a11 * a22 - a12 * a21
    if abs(det) < 1e-5:
        return None, None
    px = (a22 * b1 - a12 * b2) / det
    py = (-a21 * b1 + a11 * b2) / det
    return round(px, 3), round(py, 3)


# ── RTLSRuntime ────────────────────────────────────────────────────────────────
class RTLSRuntime:
    """
    Headless RTLS session manager.

    Call update_from_workspace() whenever workspace room/tag data changes.
    Call snapshot() to get current state for the frontend.
    """

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    def __init__(self) -> None:
        self._lock = threading.Lock()

        # ── Profile-driven tag registry ───────────────────────────────────────
        # tag_id → { mac_address, height_ft, color }
        self._tag_registry: dict[str, dict[str, Any]] = {}

        # Runtime distance & status stores (keyed by canonical tag_id e.g. "T0")
        self._tag_data: dict[str, dict[str, float]] = {}   # tag_id → anchor_id → dist
        self._tag_status: dict[str, str] = {}              # tag_id → Connected/Disconnected/…
        self._tag_positions: dict[str, tuple[float, Optional[float]]] = {}
        self._tag_seen_at: dict[str, float] = {}

        # MAC → canonical tag_id (for dongle status parsing)
        self._mac_to_tag: dict[str, str] = {}

        # ── Anchor geometry (from workspace room) ─────────────────────────────
        # Keyed by serial-data IDs (A0, A1, ...) not room IDs (R1A0)
        self._anchors: dict[str, tuple[float, float]] = {}  # serial_aid → (world_x, world_y)
        self._anchor_z: dict[str, float] = {}               # serial_aid → z_ft
        self._reference_anchor_id: str = ""                  # e.g. "A0"

        # Floor-plan rendering data (segments in world coords, bounds)
        self._segments: list[dict] = []
        self._room_bounds: dict[str, float] = {}
        self._room_name: str = ""
        self._room_rtls_settings: dict[str, Any] = {
            "tag_height_ft": 0.0,
            "filter_mode": "Raw",
            "ble_module_port": "",
        }

        # ── Smoothing filter state ─────────────────────────────────────────────
        self._filter_mode: str = "Raw"       # Raw | EMA | Rolling | Kalman
        self._ema_alpha: float = 0.20
        self._roll_n: int = 8
        self._kal_q: float = 0.10
        self._kal_r: float = 2.00

        self._ema_pos: dict[str, tuple[float, Optional[float]]] = {}
        self._roll_buf: dict[str, deque] = {}
        self._kal_state: dict[str, Optional[list]] = {}
        self._kal_P: dict[str, Optional[list]] = {}

        # ── Tag elevation ──────────────────────────────────────────────────────
        self._global_elevation_override: bool = False
        self._global_elevation_ft: float = 3.0   # used only when override=True

        # ── Serial / BLE transport ─────────────────────────────────────────────
        self._serial_port_obj: serial.Optional[Serial] = None
        self._serial_running: bool = False
        self._serial_thread: threading.Optional[Thread] = None
        self._ble_thread: threading.Optional[Thread] = None
        self._ble_stop = threading.Event()
        self._mode: Optional[str] = None
        self._selected_port: str = ""
        self._transport_status: str = "idle"   # idle | connecting | connected | error
        self._transport_detail: str = "Disconnected."
        self._serial_debug: deque[str] = deque(maxlen=80)

        # ── CSV distance logging (ported from home_rtls.py) ───────────────────
        self._csv_enabled: bool = False
        self._csv_path: Optional[str] = None
        self._csv_rtls_dir: str = ""           # workspace RTLS/ folder
        self._csv_last_ts: float = 0.0

        # ── Loop ──────────────────────────────────────────────────────────────
        self._loop_thread: threading.Optional[Thread] = None
        self._loop_running: bool = False
        self._start_loop()

    # ── Workspace integration ──────────────────────────────────────────────────

    @staticmethod
    def _serial_aid_from_room_id(room_aid: str, hw_id: str) -> str:
        """
        Map a room anchor ID (R1A0) to the serial-data anchor ID (A0).
        Priority: hw_id if set, otherwise extract A-number from room ID.
        """
        if hw_id:
            return hw_id
        m = re.match(r"R\d+A(\d+)", room_aid)
        if m:
            return f"A{m.group(1)}"
        return room_aid

    def update_from_workspace(
        self,
        room_data: Optional[dict],
        tag_profiles: Optional[list[dict]],
    ) -> None:
        """
        Called by the API whenever the RTLS session loads or refreshes workspace data.

        room_data    : the room dict from the floorplan manifest
        tag_profiles : list of profile dicts from Tags/ directory

        Anchor coords are converted from LOCAL (room-relative) to WORLD (CAD-absolute)
        using room_bounds min_x/min_y so they align with segment coordinates.
        Anchor IDs are mapped from room IDs (R1A0) to serial IDs (A0) via hw_id.
        """
        with self._lock:
            if room_data:
                self._anchors = {}
                self._anchor_z = {}
                self._reference_anchor_id = ""

                # Room bounds for local→world coordinate conversion
                bounds = room_data.get("room_bounds_ft", {})
                min_x = float(bounds.get("min_x", 0))
                min_y = float(bounds.get("min_y", 0))

                settings = {
                    "tag_height_ft": 0.0,
                    "filter_mode": "Raw",
                    "ble_module_port": "",
                    **dict(room_data.get("rtls_settings", {})),
                }

                # Reference anchor (default anchor = coordinate origin)
                ref_room_id = room_data.get("reference_anchor_id", "")

                for a in room_data.get("anchors", []):
                    room_aid = a.get("id", "")
                    hw_id = a.get("hw_id", "").strip()
                    serial_aid = self._serial_aid_from_room_id(room_aid, hw_id)

                    # Convert local coords to world coords (same system as segments)
                    local_x = float(a.get("x_ft", 0))
                    local_y = float(a.get("y_ft", 0))
                    world_x = local_x + min_x
                    world_y = local_y + min_y

                    self._anchors[serial_aid] = (round(world_x, 3), round(world_y, 3))
                    self._anchor_z[serial_aid] = float(a.get("z_ft", 0))

                    # Track reference anchor in serial-ID space
                    if room_aid == ref_room_id:
                        self._reference_anchor_id = serial_aid

                self._segments = room_data.get("segments_ft", [])
                self._room_bounds = room_data.get("room_bounds_ft", {})
                self._room_name = room_data.get("room_name", "")
                self._room_rtls_settings = settings

                filter_mode = str(settings.get("filter_mode", "Raw") or "Raw").strip() or "Raw"
                if filter_mode.lower() == "none":
                    filter_mode = "Raw"
                self._filter_mode = filter_mode

                if not self._global_elevation_override:
                    try:
                        self._global_elevation_ft = float(settings.get("tag_height_ft", 0.0))
                    except (TypeError, ValueError):
                        self._global_elevation_ft = 0.0

                if self._transport_status != "connected":
                    self._selected_port = str(settings.get("ble_module_port", "") or "").strip()

            if tag_profiles:
                new_registry: dict[str, dict[str, Any]] = {}
                new_mac_map: dict[str, str] = {}
                for p in tag_profiles:
                    tag_id = p.get("tag_id", "")
                    if not tag_id:
                        continue
                    mac = _normalize_ble_mac(p.get("device", {}).get("mac_address", ""))
                    # Derive height for this tag based on device type
                    device = p.get("device", {})
                    dev_type = device.get("device_type", "")
                    height_key = DEVICE_HEIGHT_FIELD_MAP.get(dev_type, "")
                    try:
                        tag_height_ft = float(device.get(height_key, 0.0)) if height_key else 0.0
                    except (TypeError, ValueError):
                        tag_height_ft = 0.0

                    calibration = dict(p.get("calibration", {}))
                    new_registry[tag_id] = {
                        "mac_address": mac,
                        "tag_height_ft": tag_height_ft,
                        "calibration_enabled": bool(calibration.get("equations_enabled")),
                        "calibration_equations": dict(calibration.get("equations", {})),
                        "compiled_calibration": {},
                    }
                    if mac:
                        new_mac_map[mac.lower()] = tag_id

                # Preserve any tags already in registry that aren't being replaced
                for tid in list(self._tag_data.keys()):
                    if tid not in new_registry:
                        del self._tag_data[tid]
                        self._tag_status.pop(tid, None)
                        self._tag_positions.pop(tid, None)
                        self._tag_seen_at.pop(tid, None)

                # Register new tags
                for tag_id in new_registry:
                    if tag_id not in self._tag_data:
                        self._tag_data[tag_id] = {aid: -1.0 for aid in self._anchors}
                        self._tag_status[tag_id] = "Disconnected"
                        self._tag_positions[tag_id] = None
                        self._ema_pos[tag_id] = None
                        self._roll_buf[tag_id] = deque(maxlen=20)
                        self._kal_state[tag_id] = None
                        self._kal_P[tag_id] = None
                    else:
                        # Update anchor keys if they changed
                        existing = self._tag_data[tag_id]
                        for aid in self._anchors:
                            if aid not in existing:
                                existing[aid] = -1.0

                self._tag_registry = new_registry
                self._mac_to_tag = new_mac_map

    # ── Data parsing (preserved from rtls_main_official.py) ───────────────────

    def _resolve_tag_id(self, raw_id: str) -> Optional[str]:
        """
        Map incoming data tag prefix (T0, t0, T1, t1…) to profile tag_id.
        Case-insensitive match: 't0' → 'T0', 'T1' → 'T1', etc.
        """
        upper = raw_id.strip().upper()
        # Direct match
        if upper in self._tag_registry:
            return upper
        # Try case-insensitive search
        for tid in self._tag_registry:
            if tid.upper() == upper:
                return tid
        return None

    def parse_and_store(self, data_str: str, fallback_tag_id: Optional[str] = None) -> None:
        """
        Parse distance line: T2 | A0:11.37 | A1:10.90 | A2:--- | A3:16.55
        Profile-driven: resolves incoming tag prefix against registry and mirrors
        the calibration runtime by treating live measurements as proof of connection.
        """
        try:
            parts = [p.strip() for p in data_str.split("|") if p.strip()]
            if len(parts) < 2:
                return
            raw_tid = parts[0]
            tag_id = self._resolve_tag_id(raw_tid)
            fragments = parts[1:]
            if tag_id is None and fallback_tag_id:
                tag_id = self._resolve_tag_id(fallback_tag_id)
                fragments = parts
            if tag_id is None:
                return
            with self._lock:
                if tag_id not in self._tag_data:
                    self._tag_data[tag_id] = {aid: -1.0 for aid in self._anchors}
                self._tag_status[tag_id] = "Connected"
                self._tag_seen_at[tag_id] = time.time()
                for fragment in fragments:
                    tokens = fragment.replace(":", " ").split()
                    if len(tokens) < 2:
                        continue
                    a_id, val_str = tokens[0], tokens[1]
                    if val_str.lower() in {"---", "--", "nan"}:
                        self._tag_data[tag_id][a_id] = -1.0
                        continue
                    try:
                        self._tag_data[tag_id][a_id] = float(val_str)
                    except ValueError:
                        self._tag_data[tag_id][a_id] = -1.0
        except Exception:
            pass

    _last_attempting: Optional[str] = None

    def parse_dongle_status(self, line: str) -> None:
        """
        Parse ESP32-C6 dongle status lines (preserved from original).
        Uses MAC→tag_id mapping built from profiles.
        """
        if " -> " in line:
            line = line.split(" -> ", 1)[1]
        line = line.strip()

        if "[*] Attempting to connect to" in line:
            mac = line.split("to")[-1].strip().rstrip(".")
            tag = self._mac_to_tag.get(mac.lower())
            if tag:
                with self._lock:
                    self._tag_status[tag] = "Connecting..."
                self._last_attempting = tag
            return

        if "[+] Connected to" in line:
            mac = line.split("to")[-1].strip().rstrip("!").rstrip(".")
            tag = self._mac_to_tag.get(mac.lower())
            if tag:
                with self._lock:
                    self._tag_status[tag] = "Connected"
                self._last_attempting = None
            return

        if "[-]" in line:
            tag = self._last_attempting
            if tag:
                with self._lock:
                    self._tag_status[tag] = "Disconnected"
                    self._tag_data[tag] = {aid: -1.0 for aid in self._tag_data.get(tag, {})}
                    self._tag_seen_at.pop(tag, None)
                self._last_attempting = None
            return

    def _effective_tag_status(self, tag_id: str, now: float) -> str:
        status = self._tag_status.get(tag_id, "Disconnected")
        if self._transport_status == "connected" and status == "Connected":
            seen_at = self._tag_seen_at.get(tag_id)
            if seen_at is None or (now - seen_at) > 4:
                return "Waiting"
        return status

    def _append_serial_debug(self, message: str) -> None:
        text = str(message or "").strip()
        if not text:
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self._serial_debug.append(f"[{stamp}] {text}")

    def _home_py_ble_profiles(self) -> dict[str, str]:
        items = []
        for tag_id, info in self._tag_registry.items():
            mac = _normalize_ble_mac(info.get("mac_address", ""))
            if mac:
                items.append((tag_id, mac))
        items.sort(key=lambda item: _home_py_ble_sort_key(item[0]))
        return dict(items)

    # ── Transport lifecycle ────────────────────────────────────────────────────

    def connect(self, mode: str, port: str = "") -> tuple[bool, str]:
        self.disconnect()

        if mode == "serial":
            resolved_port = port or auto_detect_esp32_port() or ""
            if not resolved_port:
                self._transport_status = "error"
                self._transport_detail = "No serial port selected."
                return False, self._transport_detail
            self._mode = "serial"
            self._selected_port = resolved_port
            self._transport_status = "connecting"
            self._transport_detail = f"Connecting: {resolved_port}..."
            self._append_serial_debug(f"Connecting to {resolved_port}...")
            thread = threading.Thread(target=self._serial_reader, args=(resolved_port,), daemon=True)
            self._serial_thread = thread
            thread.start()
            return True, self._transport_detail

        if mode == "ble":
            if not HAS_BLEAK:
                self._transport_status = "error"
                self._transport_detail = "bleak is not installed on the backend."
                return False, self._transport_detail
            ble_profiles = self._home_py_ble_profiles()
            if not ble_profiles:
                self._transport_status = "error"
                self._transport_detail = "No profiled tags have BLE MAC addresses yet."
                return False, self._transport_detail
            self._mode = "ble"
            self._selected_port = ""
            self._transport_status = "connecting"
            self._transport_detail = f"Starting BLE listeners for {len(ble_profiles)} tag(s)..."
            self._append_serial_debug(self._transport_detail)
            thread = threading.Thread(target=self._ble_thread_main, args=(ble_profiles,), daemon=True)
            self._ble_thread = thread
            thread.start()
            return True, self._transport_detail

        self._transport_status = "error"
        self._transport_detail = f"Unsupported transport mode: {mode}"
        return False, self._transport_detail

    def disconnect(self) -> None:
        mode = self._mode
        self._mode = None
        self._transport_status = "idle"
        self._transport_detail = "Disconnected."
        self._selected_port = ""
        self._last_attempting = None
        with self._lock:
            for tag_id in self._tag_status:
                self._tag_status[tag_id] = "Disconnected"
                self._tag_seen_at.pop(tag_id, None)
                self._tag_positions[tag_id] = None
                if tag_id in self._tag_data:
                    for aid in list(self._tag_data[tag_id].keys()):
                        self._tag_data[tag_id][aid] = -1.0

        if mode == "serial":
            self._serial_running = False
            if self._serial_port_obj and self._serial_port_obj.is_open:
                try:
                    self._serial_port_obj.close()
                except Exception:
                    pass
            if self._serial_thread and self._serial_thread.is_alive():
                self._serial_thread.join(timeout=1.0)
            self._serial_thread = None
            self._serial_port_obj = None

        if mode == "ble":
            self._ble_stop.set()
            if self._ble_thread and self._ble_thread.is_alive():
                self._ble_thread.join(timeout=1.5)
            self._ble_thread = None
            self._ble_stop.clear()

        self._append_serial_debug("Transport stopped.")

    # ── Serial transport (preserved from rtls_main_official.py) ───────────────

    def _serial_reader(self, port: str, baud: int = 115200) -> None:
        try:
            self._serial_port_obj = serial.Serial(port, baud, timeout=1)
            if self._mode == "serial":
                self._transport_status = "connected"
                self._transport_detail = f"Connected: {port}"
            self._append_serial_debug(f"Connected to {port}")
        except Exception as e:
            if self._mode == "serial":
                self._transport_status = "error"
                self._transport_detail = f"Could not open {port}: {e}"
            self._append_serial_debug(f"Open failed on {port}: {e}")
            self._serial_running = False
            return

        self._serial_running = True
        while self._serial_running:
            try:
                raw = self._serial_port_obj.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                self._append_serial_debug(line)

                stripped = line
                if " -> " in line:
                    stripped = line.split(" -> ", 1)[1].strip()

                if stripped and stripped[0].upper() == "T" and "|" in stripped:
                    self.parse_and_store(stripped)
                else:
                    self.parse_dongle_status(line)
            except Exception as exc:
                self._append_serial_debug(f"Read error: {exc}")
                time.sleep(0.2)

        if self._serial_port_obj and self._serial_port_obj.is_open:
            self._serial_port_obj.close()
        if self._mode == "serial":
            self._transport_status = "idle"
            self._transport_detail = "Disconnected."
        self._append_serial_debug("Disconnected.")

    def start_serial(self, port: str) -> None:
        self.connect("serial", port)

    def stop_serial(self) -> None:
        self.disconnect()

    def get_serial_ports(self) -> list[str]:
        return [p.device for p in serial.tools.list_ports.comports()]

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
        tasks = []
        for tag_id, mac in profiles.items():
            tasks.append(asyncio.create_task(self._ble_connect_and_listen(tag_id, mac)))
            await self._sleep_with_stop(3.0)
        if self._mode == "ble":
            self._transport_status = "connected"
            self._transport_detail = f"BLE listeners running for {len(tasks)} tag(s)."
            self._append_serial_debug(self._transport_detail)
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
                    self._tag_status[tag_id] = "Connecting..."
                async with BleakClient(mac_address) as client:
                    with self._lock:
                        self._tag_status[tag_id] = "Connected"
                    await client.start_notify(
                        CHAR_UUID,
                        lambda _sender, data, tid=tag_id: self.parse_and_store(
                            data.decode("utf-8", errors="replace").strip(),
                            fallback_tag_id=tid,
                        ),
                    )
                    while client.is_connected and not self._ble_stop.is_set():
                        await asyncio.sleep(1.0)
            except Exception as exc:
                with self._lock:
                    self._tag_status[tag_id] = "Disconnected"
                    if tag_id in self._tag_data:
                        for aid in list(self._tag_data[tag_id].keys()):
                            self._tag_data[tag_id][aid] = -1.0
                    self._tag_seen_at.pop(tag_id, None)
                self._append_serial_debug(f"{tag_id}: {exc}")
                await self._sleep_with_stop(3.0)

    async def _sleep_with_stop(self, seconds: float) -> None:
        deadline = time.time() + seconds
        while not self._ble_stop.is_set() and time.time() < deadline:
            await asyncio.sleep(0.25)

    # ── Smoothing filters (preserved verbatim from rtls_main_official.py) ─────

    def _apply_ema(self, t_id: str, rx: float, ry: float) -> tuple[float, float]:
        alpha = self._ema_alpha
        prev = self._ema_pos.get(t_id)
        if prev is None:
            self._ema_pos[t_id] = (rx, ry)
        else:
            self._ema_pos[t_id] = (
                alpha * rx + (1 - alpha) * prev[0],
                alpha * ry + (1 - alpha) * prev[1],
            )
        return self._ema_pos[t_id]  # type: ignore[return-value]

    def _apply_rolling(self, t_id: str, rx: float, ry: float) -> tuple[float, float]:
        n = self._roll_n
        buf = self._roll_buf.get(t_id)
        if buf is None or buf.maxlen != n:
            existing = list(buf)[-n:] if buf else []
            buf = deque(existing, maxlen=n)
            self._roll_buf[t_id] = buf
        buf.append((rx, ry))
        xs = [p[0] for p in buf]
        ys = [p[1] for p in buf]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    def _apply_kalman(self, t_id: str, rx: float, ry: float) -> tuple[float, float]:
        """4-state Kalman filter (x, y, vx, vy) — preserved from original."""
        q = self._kal_q
        r = self._kal_r
        dt = 0.05

        F = [[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]]
        H = [[1, 0, 0, 0], [0, 1, 0, 0]]
        Q = [
            [q * dt ** 3 / 3, 0, q * dt ** 2 / 2, 0],
            [0, q * dt ** 3 / 3, 0, q * dt ** 2 / 2],
            [q * dt ** 2 / 2, 0, q * dt, 0],
            [0, q * dt ** 2 / 2, 0, q * dt],
        ]
        R_mat = [[r, 0], [0, r]]

        def mm(A: list, B: list) -> list:
            rA, cA = len(A), len(A[0])
            cB = len(B[0])
            return [[sum(A[i][k] * B[k][j] for k in range(cA)) for j in range(cB)] for i in range(rA)]

        def ma(A: list, B: list) -> list:
            return [[A[i][j] + B[i][j] for j in range(len(A[0]))] for i in range(len(A))]

        def ms(A: list, B: list) -> list:
            return [[A[i][j] - B[i][j] for j in range(len(A[0]))] for i in range(len(A))]

        def mt(A: list) -> list:
            return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]

        def inv2(A: list) -> list:
            det = A[0][0] * A[1][1] - A[0][1] * A[1][0]
            if abs(det) < 1e-9:
                det = 1e-9
            return [[A[1][1] / det, -A[0][1] / det], [-A[1][0] / det, A[0][0] / det]]

        def eye(n: int) -> list:
            return [[1 if i == j else 0 for j in range(n)] for i in range(n)]

        if self._kal_state.get(t_id) is None:
            self._kal_state[t_id] = [[rx], [ry], [0.0], [0.0]]
            self._kal_P[t_id] = eye(4)

        x = self._kal_state[t_id]
        P = self._kal_P[t_id]

        x_pred = mm(F, x)
        P_pred = ma(mm(mm(F, P), mt(F)), Q)

        z = [[rx], [ry]]
        y_k = ms(z, mm(H, x_pred))
        S = ma(mm(mm(H, P_pred), mt(H)), R_mat)
        K = mm(mm(P_pred, mt(H)), inv2(S))
        x_new = ma(x_pred, mm(K, y_k))
        P_new = mm(ms(eye(4), mm(K, H)), P_pred)

        self._kal_state[t_id] = x_new
        self._kal_P[t_id] = P_new
        return (x_new[0][0], x_new[1][0])

    def smooth(self, t_id: str, rx: float, ry: float) -> tuple[float, float]:
        if self._filter_mode == "EMA":
            return self._apply_ema(t_id, rx, ry)
        if self._filter_mode == "Rolling":
            return self._apply_rolling(t_id, rx, ry)
        if self._filter_mode == "Kalman":
            return self._apply_kalman(t_id, rx, ry)
        return (rx, ry)

    def _apply_anchor_correction(self, tag_info: dict[str, Any], anchor_id: str, raw_distance: float) -> float:
        if raw_distance <= 0.0 or not tag_info.get("calibration_enabled"):
            return raw_distance

        equations = tag_info.get("calibration_equations", {})
        cache = tag_info.setdefault("compiled_calibration", {})
        resolved_anchor_id, expr = _resolve_anchor_equation(equations, anchor_id)
        if not expr:
            return raw_distance

        cache_key = resolved_anchor_id or str(anchor_id or "").strip()
        func = cache.get(cache_key)
        if func is None:
            try:
                func = compile_manual_equation(expr)
            except Exception:
                cache[cache_key] = False
                return raw_distance
            cache[cache_key] = func
        elif func is False:
            return raw_distance

        try:
            corrected = float(func(float(raw_distance)))
        except Exception:
            return raw_distance
        return corrected if corrected > 0.0 else raw_distance

    def reset_filter_state(self, t_id: str) -> None:
        self._ema_pos[t_id] = None
        self._roll_buf[t_id] = deque(maxlen=20)
        self._kal_state[t_id] = None
        self._kal_P[t_id] = None

    # ── Position loop (preserved logic from rtls_main_official.py) ────────────

    def _loop_body(self) -> None:
        """Core loop iteration — preserves rtls_main_official.py loop() logic."""
        now = time.time()
        with self._lock:
            tag_ids = list(self._tag_registry.keys())
            anchors = dict(self._anchors)
            anchor_z = dict(self._anchor_z)

        for t_id in tag_ids:
            with self._lock:
                status = self._effective_tag_status(t_id, now)

            if status != "Connected":
                if self._tag_positions.get(t_id) is not None:
                    self.reset_filter_state(t_id)
                self._tag_positions[t_id] = None
                continue

            # Per-anchor height correction: h = abs(anchor_z[a_id] - tag_z)
            # Global override collapses all anchors to the same fixed offset.
            if self._global_elevation_override:
                eff_anchor_z = {aid: self._global_elevation_ft for aid in anchor_z}
                tag_z = 0.0
            else:
                tag_info = self._tag_registry.get(t_id, {})
                tag_z = float(tag_info.get("tag_height_ft", 0.0))
                eff_anchor_z = anchor_z

            with self._lock:
                dists = dict(self._tag_data.get(t_id, {}))

            corrected_dists = {
                a_id: self._apply_anchor_correction(tag_info, a_id, raw_distance)
                for a_id, raw_distance in dists.items()
            }

            x, y = calc_pos_multi(corrected_dists, anchors, anchor_z=eff_anchor_z, tag_z=tag_z)
            if x is not None and y is not None:
                sx, sy = self.smooth(t_id, x, y)
                self._tag_positions[t_id] = (round(sx, 3), round(sy, 3))
            else:
                self._tag_positions[t_id] = None

        # CSV logging — write inter-tag distances each cycle
        self._write_csv_distances()

    def _start_loop(self) -> None:
        self._loop_running = True

        def _run():
            while self._loop_running:
                self._loop_body()
                time.sleep(0.05)   # 20 Hz — same cadence as original root.after(50)

        self._loop_thread = threading.Thread(target=_run, daemon=True)
        self._loop_thread.start()

    # ── CSV distance logging (ported from home_rtls.py) ───────────────────────

    def set_rtls_dir(self, rtls_dir: str) -> None:
        """Set the workspace RTLS/ folder for CSV output."""
        self._csv_rtls_dir = rtls_dir

    def start_csv_logging(self) -> tuple[bool, str]:
        """Initialize CSV log file in workspace RTLS/ folder."""
        if not self._csv_rtls_dir:
            return False, "No workspace RTLS folder set."
        os.makedirs(self._csv_rtls_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        room_slug = re.sub(r"[^A-Za-z0-9_-]", "_", self._room_name or "Room")
        base_name = f"RTLS_{room_slug}_{date_str}"
        suffix = ""
        counter = 1
        while True:
            path = os.path.join(self._csv_rtls_dir, f"{base_name}{suffix}.csv")
            if not os.path.exists(path):
                self._csv_path = path
                break
            suffix = f"({counter})"
            counter += 1
        try:
            with open(self._csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Tag1", "Tag2", "Distance_ft", "Delta_s"])
            self._csv_enabled = True
            self._csv_last_ts = time.time()
            return True, self._csv_path
        except OSError as e:
            return False, str(e)

    def stop_csv_logging(self) -> None:
        self._csv_enabled = False

    def _write_csv_distances(self) -> None:
        """Write inter-tag distances to CSV (preserved from home_rtls.py)."""
        if not self._csv_enabled or not self._csv_path:
            return
        now = time.time()
        dt = now - self._csv_last_ts
        self._csv_last_ts = now
        ts = datetime.now().strftime(f"{datetime.now().month}.{datetime.now().day}.{datetime.now().year} %H:%M:%S")

        positioned = [
            (tid, pos)
            for tid, pos in self._tag_positions.items()
            if pos is not None
        ]
        if len(positioned) < 2:
            return

        rows: list[list] = []
        for i in range(len(positioned)):
            for j in range(i + 1, len(positioned)):
                t1_id, p1 = positioned[i]
                t2_id, p2 = positioned[j]
                dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                rows.append([ts, t1_id, t2_id, f"{dist:.1f}ft", f"{dt:.2f}s"])
        try:
            with open(self._csv_path, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(rows)
        except OSError:
            pass

    def shutdown(self) -> None:
        self._loop_running = False
        self.stop_serial()
        self.stop_csv_logging()

    # ── Public control API ─────────────────────────────────────────────────────

    def set_filter(
        self,
        mode: Optional[str] = None,
        ema_alpha: Optional[float] = None,
        roll_n: Optional[int] = None,
        kal_q: Optional[float] = None,
        kal_r: Optional[float] = None,
    ) -> None:
        if mode is not None:
            self._filter_mode = mode
        if ema_alpha is not None:
            self._ema_alpha = ema_alpha
        if roll_n is not None:
            self._roll_n = roll_n
        if kal_q is not None:
            self._kal_q = kal_q
        if kal_r is not None:
            self._kal_r = kal_r

    def set_elevation(self, override: bool, value_ft: Optional[float] = None) -> None:
        self._global_elevation_override = override
        if value_ft is not None:
            self._global_elevation_ft = value_ft

    # ── State snapshot ─────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """
        Returns the current RTLS state for frontend polling.
        Called by GET /api/rtls/snapshot.
        """
        with self._lock:
            tags_out: list[dict] = []
            for t_id in self._tag_registry:
                pos = self._tag_positions.get(t_id)
                status = self._effective_tag_status(t_id, time.time())
                tags_out.append({
                    "tag_id": t_id,
                    "status": status,
                    "position": {"x": pos[0], "y": pos[1]} if pos else None,
                    "distances": dict(self._tag_data.get(t_id, {})),
                })

            return {
                "mode": self._mode,
                "transport_status": self._transport_status,
                "transport_detail": self._transport_detail,
                "selected_port": self._selected_port,
                "ports": self.get_serial_ports(),
                "auto_detect_port": auto_detect_esp32_port() or "",
                "ble_available": HAS_BLEAK,
                "tags": tags_out,
                "anchors": {aid: list(pos) for aid, pos in self._anchors.items()},
                "segments": self._segments,
                "room_bounds": self._room_bounds,
                "room_name": self._room_name,
                "reference_anchor_id": self._reference_anchor_id,
                "room_settings": dict(self._room_rtls_settings),
                "filter": {
                    "mode": self._filter_mode,
                    "ema_alpha": self._ema_alpha,
                    "roll_n": self._roll_n,
                    "kal_q": self._kal_q,
                    "kal_r": self._kal_r,
                },
                "elevation": {
                    "override": self._global_elevation_override,
                    "value_ft": self._global_elevation_ft,
                },
                "csv": {
                    "enabled": self._csv_enabled,
                    "path": self._csv_path or "",
                },
                "serial_debug": list(self._serial_debug),
            }
