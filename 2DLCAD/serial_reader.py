import time
import re
import math
import random
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
    Virtual RTLS simulator that keeps mock tags inside actual room bounds.

    It supports:
    - a single room in local coordinates for the room-detail viewer
    - multiple rooms in world coordinates for the ship-level RTLS dashboard
    """
    tag_update = pyqtSignal(str, float, float)
    connection_error = pyqtSignal(str)

    class _MockPerson:
        def __init__(self, tag_id, zone, choose_zone=None):
            self.tag_id = tag_id
            self.zone = zone
            self._choose_zone = choose_zone
            self.x, self.y = zone["spawn"]()
            self.target_x, self.target_y = self.x, self.y
            self.speed = 0.0
            self.top_speed = random.uniform(0.18, 0.72)
            self.accel = random.uniform(0.010, 0.045)
            self.pause_ticks = random.randint(10, 30)
            self._choose_new_target()

        def _choose_new_target(self):
            if self._choose_zone is not None and random.random() < 0.18:
                next_zone = self._choose_zone(self.zone)
                if next_zone is not None and next_zone is not self.zone:
                    self.zone = next_zone
                    self.x, self.y = self.zone["spawn"]()
                    self.pause_ticks = random.randint(10, 24)
            self.target_x, self.target_y = self.zone["spawn"]()
            self.top_speed = random.uniform(0.18, 0.72)
            self.accel = random.uniform(0.010, 0.045)
            self.pause_ticks = random.randint(12, 40)

        def update(self):
            if self.pause_ticks > 0:
                self.pause_ticks -= 1
                self.speed = max(0.0, self.speed - self.accel * 1.8)
                return self.x, self.y

            dx = self.target_x - self.x
            dy = self.target_y - self.y
            dist = math.hypot(dx, dy)
            if dist < 0.08:
                self.speed = 0.0
                self._choose_new_target()
                return self.x, self.y

            brake_distance = (self.speed * self.speed) / (2.0 * max(self.accel, 1e-6))
            if dist <= brake_distance + 0.04:
                self.speed = max(0.0, self.speed - self.accel)
            else:
                self.speed = min(self.top_speed, self.speed + self.accel)

            step = min(dist, self.speed)
            nx = self.x + (dx / dist) * step
            ny = self.y + (dy / dist) * step

            if self.zone["contains"](nx, ny):
                self.x = nx
                self.y = ny
            else:
                self.speed = 0.0
                self.pause_ticks = random.randint(6, 18)
                self._choose_new_target()

            return self.x, self.y

    def __init__(self, room=None, rooms=None, coordinate_mode="local", tags_per_room=None):
        super().__init__()
        self._running = True
        self.coordinate_mode = coordinate_mode
        self._people = []
        self._zones = self._build_zones(room=room, rooms=rooms, tags_per_room=tags_per_room)
        self._seed_people()

    def _build_zones(self, room=None, rooms=None, tags_per_room=None):
        source_rooms = []
        if room is not None:
            source_rooms = [room]
        elif rooms:
            source_rooms = list(rooms)

        zones = []
        for idx, rm in enumerate(source_rooms):
            count = tags_per_room if tags_per_room is not None else self._default_people_count(rm)
            zone = {
                "room": rm,
                "index": idx,
                "count": max(1, int(count)),
                "center_world": rm.local_to_world(rm.width * 0.5, rm.height * 0.5),
            }

            def contains_local_factory(target_room):
                return lambda lx, ly: target_room.contains_local_point(lx, ly)

            def spawn_local_factory(target_room):
                def _spawn():
                    margin = 0.18
                    min_x = margin
                    min_y = margin
                    max_x = max(target_room.width - margin, min_x + 0.01)
                    max_y = max(target_room.height - margin, min_y + 0.01)
                    for _ in range(80):
                        lx = random.uniform(min_x, max_x)
                        ly = random.uniform(min_y, max_y)
                        if target_room.contains_local_point(lx, ly):
                            return lx, ly
                    return target_room.width / 2.0, target_room.height / 2.0
                return _spawn

            if self.coordinate_mode == "world":
                def contains_world_factory(target_room):
                    return lambda wx, wy: target_room.contains_local_point(*target_room.world_to_local(wx, wy))

                def spawn_world_factory(target_room):
                    local_spawn = spawn_local_factory(target_room)
                    return lambda: target_room.local_to_world(*local_spawn())

                zone["contains"] = contains_world_factory(rm)
                zone["spawn"] = spawn_world_factory(rm)
            else:
                zone["contains"] = contains_local_factory(rm)
                zone["spawn"] = spawn_local_factory(rm)

            zones.append(zone)

        return zones

    @staticmethod
    def _default_people_count(room):
        area = max(float(room.width) * float(room.height), 1.0)
        if area < 35:
            return 1
        if area < 120:
            return 2
        if area < 220:
            return 3
        if area < 360:
            return 4
        return 4 + random.randint(0, 1)

    def _seed_people(self):
        if not self._zones:
            return
        sailor_index = 1
        for zone in self._zones:
            for i in range(zone["count"]):
                tag_id = f"S{sailor_index:02d}"
                sailor_index += 1
                choose_zone = self._pick_next_zone if self.coordinate_mode == "world" and len(self._zones) > 1 else None
                self._people.append(self._MockPerson(tag_id, zone, choose_zone=choose_zone))

    def _pick_next_zone(self, current_zone):
        if len(self._zones) < 2:
            return current_zone

        current_cx, current_cy = current_zone["center_world"]
        weighted_choices = []
        for zone in self._zones:
            if zone is current_zone:
                continue
            zx, zy = zone["center_world"]
            distance = math.hypot(zx - current_cx, zy - current_cy)
            # Prefer nearby rooms, but still allow occasional longer moves.
            weight = 1.0 / max(distance, 6.0)
            weighted_choices.append((zone, weight))

        total_weight = sum(weight for _, weight in weighted_choices)
        if total_weight <= 0.0:
            return random.choice([zone for zone, _ in weighted_choices]) if weighted_choices else current_zone

        pick = random.uniform(0.0, total_weight)
        running = 0.0
        for zone, weight in weighted_choices:
            running += weight
            if pick <= running:
                return zone
        return weighted_choices[-1][0]

    def run(self):
        if not self._people:
            self.connection_error.emit("Virtual MOCK_RTLS requires at least one room.")
            return

        while self._running:
            try:
                for person in self._people:
                    x, y = person.update()
                    self.tag_update.emit(person.tag_id, x, y)
                time.sleep(0.10)
            except Exception as e:
                self.connection_error.emit(str(e))
                break

    def stop(self):
        self._running = False
        self.wait()
