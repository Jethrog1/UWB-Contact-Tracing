import time
import re
import math
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import serial
except ImportError:
    serial = None


def _pick_bilateration_candidate(candidates, anchor_points, preferred_position=None):
    """
    Choose the most plausible 2-anchor intersection.

    If we have a prior solved tag position, prefer continuity and choose the
    candidate closest to it. Otherwise, fall back to the centroid of all known
    anchor positions so the choice is still based on room geometry.
    """
    if preferred_position is not None:
        target_x, target_y = preferred_position
    else:
        target_x = sum(x for x, _ in anchor_points) / len(anchor_points)
        target_y = sum(y for _, y in anchor_points) / len(anchor_points)

    return min(
        candidates,
        key=lambda pt: (pt[0] - target_x) ** 2 + (pt[1] - target_y) ** 2
    )


def _solve_position(anchor_positions: dict, distances: dict, tag_height: float = 0.0,
                    preferred_position=None):
    """
    Compute 2D tag position from anchor ranges using:
    - bilateration when 2 anchors are available
    - trilateration when 3 anchors are available
    - multilateration when 4+ anchors are available

    tag_height: vertical offset in feet for 3D->2D range projection.
    """
    valid = []
    for a_id, r in distances.items():
        if r > 0.0 and a_id in anchor_positions:
            if tag_height > 0 and r > tag_height:
                r = math.sqrt(r ** 2 - tag_height ** 2)
            elif tag_height > 0:
                r = 0.01
            valid.append((anchor_positions[a_id][0], anchor_positions[a_id][1], r))

    if len(valid) < 2:
        return None, None

    if len(valid) == 2:
        # Bilateration: two intersecting circles, then disambiguate the two
        # mirrored candidates using the prior tag position when available.
        x1, y1, r1 = valid[0]
        x2, y2, r2 = valid[1]
        d = math.hypot(x2 - x1, y2 - y1)
        if d < 1e-6:
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

        pick_x, pick_y = _pick_bilateration_candidate(
            [(ix1, iy1), (ix2, iy2)],
            [(pos[0], pos[1]) for pos in anchor_positions.values()],
            preferred_position=preferred_position,
        )
        return round(pick_x, 3), round(pick_y, 3)

    else:
        # Trilateration / multilateration: solve with linear least squares.
        x0, y0, r0 = valid[0]
        A_mat, B_vec = [], []
        for i in range(1, len(valid)):
            xi, yi, ri = valid[i]
            A_mat.append([2 * (xi - x0), 2 * (yi - y0)])
            B_vec.append(r0 ** 2 - ri ** 2 - x0 ** 2 - y0 ** 2 + xi ** 2 + yi ** 2)

        a11 = sum(row[0] ** 2 for row in A_mat)
        a12 = sum(row[0] * row[1] for row in A_mat)
        a22 = sum(row[1] ** 2 for row in A_mat)
        b1 = sum(A_mat[i][0] * B_vec[i] for i in range(len(B_vec)))
        b2 = sum(A_mat[i][1] * B_vec[i] for i in range(len(B_vec)))

        det = a11 * a22 - a12 ** 2
        if abs(det) < 1e-5:
            return None, None
        px = (a22 * b1 - a12 * b2) / det
        py = (-a12 * b1 + a11 * b2) / det
        return round(px, 3), round(py, 3)


def _lateration_mode(anchor_count: int) -> str:
    if anchor_count == 2:
        return "bilateration"
    if anchor_count == 3:
        return "trilateration"
    if anchor_count >= 4:
        return "multilateration"
    return "insufficient anchors"


class SerialReaderThread(QThread):
    """
    Background QThread that reads raw anchor-distance packets from the hardware:
      Format:  "T2 | A0:11.37 | A3:16.55"
    Performs bi/tri-lateration using the anchor positions provided by the room
    and emits (tag_id, x, y) once a position is resolved.
    """
    tag_update = pyqtSignal(str, float, float)
    connection_error = pyqtSignal(str)
    raw_line = pyqtSignal(str)          # every serial line received
    debug_msg = pyqtSignal(str)         # diagnostic messages

    def __init__(self, port: str, baudrate: int = 115200, anchor_positions: dict = None, tag_height: float = 0.0):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self._running = True
        self.anchor_positions = anchor_positions or {}
        self.tag_height = tag_height
        self._last_positions = {}

    def _parse_line(self, line: str):
        """
        Parse a hardware distance packet of the form:
            T2 | A0:11.37 | A1:10.90 | A2:--- | A3:16.55
        Returns (tag_id, distances_dict) or (None, None).
        """
        # Strip optional Arduino IDE timestamp prefix "HH:MM:SS.mmm -> ..."
        if " -> " in line:
            line = line.split(" -> ", 1)[1].strip()

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            return None, None

        tag_id = parts[0].strip()
        if not tag_id.startswith("T"):
            return None, None

        distances = {}
        for seg in parts[1:]:
            seg = seg.replace(":", " ").strip()
            tokens = seg.split()
            if len(tokens) >= 2:
                a_id = tokens[0]
                val = tokens[1]
                if val not in ("---", "--", "nan", ""):
                    try:
                        distances[a_id] = float(val)
                    except ValueError:
                        pass

        return tag_id, distances

    def run(self):
        if serial is None:
            self.connection_error.emit("pyserial is not installed. Run: pip install pyserial")
            return

        try:
            with serial.Serial(self.port, self.baudrate, timeout=1.0) as ser:
                while self._running:
                    try:
                        line = ser.readline().decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue

                        self.raw_line.emit(line)

                        tag_id, distances = self._parse_line(line)
                        if tag_id is None or not distances:
                            self.debug_msg.emit(f"[SKIP] Could not parse: {line[:60]}")
                            continue

                        if not self.anchor_positions:
                            self.debug_msg.emit("[WARN] No anchor positions set — cannot solve tag position. Place anchors in the room first.")
                            continue

                        # Resolve anchor positions
                        resolved = {}
                        for dist_anchor_id, dist_val in distances.items():
                            if dist_anchor_id in self.anchor_positions:
                                resolved[dist_anchor_id] = dist_val
                            else:
                                for ap_key in self.anchor_positions:
                                    if ap_key.endswith(dist_anchor_id) or dist_anchor_id.endswith(ap_key):
                                        resolved[ap_key] = dist_val
                                        break

                        if len(resolved) < 2:
                            self.debug_msg.emit(f"[WARN] Only {len(resolved)} anchor(s) matched for {tag_id}. Distances: {distances}. Anchors: {list(self.anchor_positions.keys())}")
                            continue

                        solve_mode = _lateration_mode(len(resolved))
                        x, y = _solve_position(
                            self.anchor_positions,
                            resolved,
                            self.tag_height,
                            preferred_position=self._last_positions.get(tag_id),
                        )
                        if x is not None:
                            self._last_positions[tag_id] = (x, y)
                            self.debug_msg.emit(
                                f"[OK] {tag_id} {solve_mode} -> ({x:.3f}, {y:.3f}) "
                                f"using {len(resolved)} anchor(s)"
                            )
                            self.tag_update.emit(tag_id, x, y)
                        else:
                            self.debug_msg.emit(
                                f"[WARN] {solve_mode} returned None for {tag_id} "
                                f"with {len(resolved)} anchor(s)"
                            )

                    except serial.SerialException as e:
                        self.connection_error.emit(f"Serial read error: {e}")
                        break
        except Exception as e:
            self.connection_error.emit(f"Failed to open port {self.port}: {e}")

    def stop(self):
        self._running = False
        self.wait()


class MockSerialReaderThread(QThread):
    """
    Virtual Hardware Simulator — oscillates fake T0, T1, T2 tags.
    """
    tag_update = pyqtSignal(str, float, float)
    connection_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        t = 0.0
        while self._running:
            try:
                x0 = 5.0 + 3.0 * math.cos(t)
                y0 = 4.0 + 3.0 * math.sin(t)
                x1 = 5.0 + 2.0 * math.sin(t)
                y1 = 4.0 + 2.0 * math.sin(t) * math.cos(t)
                x2 = 2.0 + 1.5 * math.cos(t * 0.5)
                y2 = 6.0 + 1.5 * math.sin(t * 0.3)

                self.tag_update.emit("T0", x0, y0)
                self.tag_update.emit("T1", x1, y1)
                self.tag_update.emit("T2", x2, y2)

                t += 0.1
                time.sleep(0.1)
            except Exception as e:
                self.connection_error.emit(str(e))
                break

    def stop(self):
        self._running = False
        self.wait()
