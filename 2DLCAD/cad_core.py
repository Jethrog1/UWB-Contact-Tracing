import math

EPS = 1e-9

class Viewport:
    def __init__(self):
        self.scale = 60.0
        self.offx = 0.0
        self.offy = 0.0

    def world_to_screen(self, x, y):
        # Invert Y so positive Y is up
        return x * self.scale + self.offx, -y * self.scale + self.offy

    def screen_to_world(self, sx, sy):
        # Invert Y so positive Y is up
        return (sx - self.offx) / self.scale, -(sy - self.offy) / self.scale

    def zoom_at(self, factor, anchor_sx, anchor_sy):
        # Determine world coordinates of the anchor before zooming
        wx, wy = self.screen_to_world(anchor_sx, anchor_sy)
        
        # Apply zoom
        self.scale *= factor
        
        # Adjust offset so that the world point remains at the screen anchor
        self.offx = anchor_sx - wx * self.scale
        # Since world_to_screen does: sy = -wy * scale + offy -> offy = sy + wy * scale
        self.offy = anchor_sy + wy * self.scale


class Line:
    __slots__ = ("x1", "y1", "x2", "y2", "color", "selected", "group_id")

    def __init__(self, x1, y1, x2, y2, color="#4A9EFF"):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.color = color
        self.selected = False
        self.group_id = None  # None = ungrouped, int = group ID

    def clone(self):
        new_line = Line(self.x1, self.y1, self.x2, self.y2, self.color)
        new_line.selected = self.selected
        new_line.group_id = self.group_id
        return new_line

    def length(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def distance_to_point(self, px, py):
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        if abs(dx) < EPS and abs(dy) < EPS:
            return math.hypot(px - self.x1, py - self.y1)
        t = ((px - self.x1) * dx + (py - self.y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proj_x = self.x1 + t * dx
        proj_y = self.y1 + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def closest_point(self, px, py):
        dx = self.x2 - self.x1
        dy = self.y2 - self.y1
        if abs(dx) < EPS and abs(dy) < EPS:
            return self.x1, self.y1, 0.0
        t = ((px - self.x1) * dx + (py - self.y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proj_x = self.x1 + t * dx
        proj_y = self.y1 + t * dy
        return proj_x, proj_y, t


class Spline:
    __slots__ = ("x1", "y1", "cx1", "cy1", "cx2", "cy2", "x2", "y2", "color", "selected", "group_id")

    def __init__(self, x1, y1, cx1, cy1, cx2, cy2, x2, y2, color="#4A9EFF"):
        self.x1, self.y1 = x1, y1
        self.cx1, self.cy1 = cx1, cy1
        self.cx2, self.cy2 = cx2, cy2
        self.x2, self.y2 = x2, y2
        self.color = color
        self.selected = False
        self.group_id = None

    def clone(self):
        new_spline = Spline(self.x1, self.y1, self.cx1, self.cy1, self.cx2, self.cy2, self.x2, self.y2, self.color)
        new_spline.selected = self.selected
        new_spline.group_id = self.group_id
        return new_spline

    def get_point(self, t):
        # Cubic Bezier: (1-t)^3*P0 + 3(1-t)^2*t*P1 + 3(1-t)t^2*P2 + t^3*P3
        mt = 1 - t
        c0 = mt * mt * mt
        c1 = 3 * mt * mt * t
        c2 = 3 * mt * t * t
        c3 = t * t * t
        rx = c0 * self.x1 + c1 * self.cx1 + c2 * self.cx2 + c3 * self.x2
        ry = c0 * self.y1 + c1 * self.cy1 + c2 * self.cy2 + c3 * self.y2
        return rx, ry

    def closest_point(self, px, py, samples=40):
        # Sampling approximation for closest point
        best_p = (self.x1, self.y1)
        best_d = math.hypot(px - self.x1, py - self.y1)
        best_t = 0.0
        
        for i in range(1, samples + 1):
            t = i / samples
            sx, sy = self.get_point(t)
            d = math.hypot(px - sx, py - sy)
            if d < best_d:
                best_d = d
                best_p = (sx, sy)
                best_t = t
        return best_p[0], best_p[1], best_t

    def distance_to_point(self, px, py, samples=40):
        # Use closest_point sampling approximation
        cx, cy, _ = self.closest_point(px, py, samples)
        return math.hypot(px - cx, py - cy)
