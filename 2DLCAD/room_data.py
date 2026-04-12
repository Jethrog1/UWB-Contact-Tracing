from dataclasses import dataclass, field
from typing import List, Tuple
import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPolygonF


def _normalize_segment(seg):
    x1, y1, x2, y2 = seg
    a = (round(float(x1), 4), round(float(y1), 4))
    b = (round(float(x2), 4), round(float(y2), 4))
    return (a, b) if a <= b else (b, a)


def segments_match(segments_a, segments_b, eps=1e-3):
    if len(segments_a) != len(segments_b):
        return False

    unmatched = list(segments_b)
    for seg_a in segments_a:
        match_index = None
        for idx, seg_b in enumerate(unmatched):
            if _segments_equal(seg_a, seg_b, eps):
                match_index = idx
                break
        if match_index is None:
            return False
        unmatched.pop(match_index)
    return not unmatched


def _segments_equal(seg_a, seg_b, eps=1e-3):
    ax1, ay1, ax2, ay2 = seg_a
    bx1, by1, bx2, by2 = seg_b
    return (
        _points_close((ax1, ay1), (bx1, by1), eps) and
        _points_close((ax2, ay2), (bx2, by2), eps)
    ) or (
        _points_close((ax1, ay1), (bx2, by2), eps) and
        _points_close((ax2, ay2), (bx1, by1), eps)
    )


def _points_close(a, b, eps=1e-3):
    return abs(float(a[0]) - float(b[0])) <= eps and abs(float(a[1]) - float(b[1])) <= eps


def _dist_point_to_segment(px, py, x1, y1, x2, y2) -> float:
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)

@dataclass
class Anchor:
    id: str          # Dashboard ID e.g. "R1A0", "R1A1"
    x: float         # local x-coord in room (feet)
    y: float         # local y-coord in room (feet)
    hw_id: str = "" # Physical hardware anchor ID e.g. "A0", "A3" (set by user)
    z: float = 0.0  # height from floor in feet

@dataclass
class Room:
    name: str
    segments: List[Tuple[float, float, float, float]]  # boundary sub-segments in world coords
    interior_segments: List[Tuple[float, float, float, float]] = field(default_factory=list)
    anchors: List[Anchor] = field(default_factory=list)
    rtls_settings: dict = field(default_factory=dict)
    
    # Bounding box in world coordinates
    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0
    
    # Ordered polygon in local coords
    _local_polygon: QPolygonF = field(init=False, default=None)
    
    def __post_init__(self):
        self._compute_bounds()
        self._build_polygon()

    def _compute_bounds(self):
        if not self.segments:
            return
            
        xs = []
        ys = []
        for x1, y1, x2, y2 in self.segments:
            xs.extend([x1, x2])
            ys.extend([y1, y2])
            
        self.min_x = min(xs)
        self.max_x = max(xs)
        self.min_y = min(ys)
        self.max_y = max(ys)
        
    @property
    def width(self) -> float:
        return max(self.max_x - self.min_x, 0.0)
        
    @property
    def height(self) -> float:
        return max(self.max_y - self.min_y, 0.0)

    def world_to_local(self, wx: float, wy: float) -> Tuple[float, float]:
        """Convert a world-space coordinate to the room's local coordinate system (origin at min_x, min_y)."""
        return (wx - self.min_x, wy - self.min_y)
        
    def local_to_world(self, lx: float, ly: float) -> Tuple[float, float]:
        """Convert a room-local coordinate back to world-space."""
        return (lx + self.min_x, ly + self.min_y)

    def _build_polygon(self):
        """Chain unordered segments into a continuous QPolygonF in local coords."""
        if not self.segments:
            self._local_polygon = QPolygonF()
            return
            
        # Convert all to local coords first
        local_segs = []
        for wx1, wy1, wx2, wy2 in self.segments:
            lx1, ly1 = self.world_to_local(wx1, wy1)
            lx2, ly2 = self.world_to_local(wx2, wy2)
            local_segs.append([(lx1, ly1), (lx2, ly2)])
            
        # Greedy chaining
        unvisited = local_segs[1:]
        chain = list(local_segs[0])
        
        def pts_close(p1, p2, eps=1e-4):
            return abs(p1[0]-p2[0]) < eps and abs(p1[1]-p2[1]) < eps
            
        while unvisited:
            progress = False
            last_pt = chain[-1]
            first_pt = chain[0]
            
            for i, seg in enumerate(unvisited):
                # Check if seg attaches to end of chain
                if pts_close(seg[0], last_pt):
                    chain.append(seg[1])
                    unvisited.pop(i)
                    progress = True
                    break
                elif pts_close(seg[1], last_pt):
                    chain.append(seg[0])
                    unvisited.pop(i)
                    progress = True
                    break
                # Check if seg attaches to start of chain
                elif pts_close(seg[0], first_pt):
                    chain.insert(0, seg[1])
                    unvisited.pop(i)
                    progress = True
                    break
                elif pts_close(seg[1], first_pt):
                    chain.insert(0, seg[0])
                    unvisited.pop(i)
                    progress = True
                    break
            
            # If no progress, just append the next segment (disconnected or multi-poly)
            # This handles disjoint selections gracefully.
            if not progress and unvisited:
                seg = unvisited.pop(0)
                chain.extend(seg)
                
        poly = QPolygonF()
        for x, y in chain:
            poly.append(QPointF(x, y))
        self._local_polygon = poly

    def contains_local_point(self, lx: float, ly: float) -> bool:
        """True if the local point is strictly inside the room boundary polygon."""
        if not self._local_polygon:
            return False
        return self._local_polygon.containsPoint(QPointF(lx, ly), Qt.FillRule.OddEvenFill)

    def contains_local_point_with_tolerance(self, lx: float, ly: float, tolerance_ft: float = 1.0) -> bool:
        """
        Accept points that are inside the room or slightly outside due to real RTLS noise.
        This keeps live tags visible and attributable when they land just beyond a wall edge.
        """
        if self.contains_local_point(lx, ly):
            return True
        if tolerance_ft <= 0.0:
            return False
        for wx1, wy1, wx2, wy2 in self.segments:
            sx1, sy1 = self.world_to_local(wx1, wy1)
            sx2, sy2 = self.world_to_local(wx2, wy2)
            if _dist_point_to_segment(lx, ly, sx1, sy1, sx2, sy2) <= tolerance_ft:
                return True
        return False
        
    def get_local_polygon(self) -> QPolygonF:
        return QPolygonF(self._local_polygon)

    def normalized_segment_signature(self):
        return tuple(sorted(_normalize_segment(seg) for seg in self.segments))
