from dataclasses import dataclass, field
from typing import List, Tuple
import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPolygonF

@dataclass
class Anchor:
    id: str          # "A0", "A1", "A2", "A3"
    x: float         # local x-coord in room (metres)
    y: float         # local y-coord in room (metres)

@dataclass
class Room:
    name: str
    segments: List[Tuple[float, float, float, float]]  # boundary sub-segments in world coords
    anchors: List[Anchor] = field(default_factory=list)
    
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
        
    def get_local_polygon(self) -> QPolygonF:
        return QPolygonF(self._local_polygon)
