
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .geometry_utils import (
    build_room_bounds,
    chain_segments_to_polygon,
    point_in_polygon,
    point_to_segment_distance,
)

Segment = Tuple[float, float, float, float]
Point = Tuple[float, float]

def _points_close(a: Point, b: Point, eps: float = 1e-3) -> bool:
    return abs(float(a[0]) - float(b[0])) <= eps and abs(float(a[1]) - float(b[1])) <= eps

def segments_equal(seg_a: Segment, seg_b: Segment, eps: float = 1e-3) -> bool:
    ax1, ay1, ax2, ay2 = seg_a
    bx1, by1, bx2, by2 = seg_b
    return (
        _points_close((ax1, ay1), (bx1, by1), eps)
        and _points_close((ax2, ay2), (bx2, by2), eps)
    ) or (
        _points_close((ax1, ay1), (bx2, by2), eps)
        and _points_close((ax2, ay2), (bx1, by1), eps)
    )

def segments_match(segments_a: List[Segment], segments_b: List[Segment], eps: float = 1e-3) -> bool:
    if len(segments_a) != len(segments_b):
        return False

    unmatched = list(segments_b)
    for seg_a in segments_a:
        match_index = next((idx for idx, seg_b in enumerate(unmatched) if segments_equal(seg_a, seg_b, eps)), None)
        if match_index is None:
            return False
        unmatched.pop(match_index)
    return not unmatched

@dataclass
class Anchor:
    id: str                                             
    x: float                                        
    y: float                                        
    hw_id: str = ""                                                              
    z: float = 0.0                               

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "hw_id": self.hw_id,
            "hardware_id": self.hw_id,
            "x_ft": round(float(self.x), 3),
            "y_ft": round(float(self.y), 3),
            "z_ft": round(float(self.z), 3),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Anchor":
        return cls(
            id=str(d.get("id", "")),
            hw_id=str(d.get("hardware_id", d.get("hw_id", ""))),
            x=float(d.get("x_ft", d.get("x", 0.0))),
            y=float(d.get("y_ft", d.get("y", 0.0))),
            z=float(d.get("z_ft", d.get("z", 0.0))),
        )

@dataclass
class Room:
    name: str
    segments: List[Segment]                                                    
    interior_segments: List[Segment] = field(default_factory=list)
    anchors: List[Anchor] = field(default_factory=list)
    edges: List[Tuple[str, str]] = field(default_factory=list)
    rtls_settings: dict = field(default_factory=dict)
    reference_anchor_id: Optional[str] = None

    min_x: float = 0.0
    min_y: float = 0.0
    max_x: float = 0.0
    max_y: float = 0.0

    _local_polygon: List[Point] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self._compute_bounds()
        self._build_polygon()

    def _compute_bounds(self) -> None:
        if not self.segments:
            return
        self.min_x, self.min_y, self.max_x, self.max_y = build_room_bounds(self.segments)

    @property
    def width(self) -> float:
        return max(self.max_x - self.min_x, 0.0)

    @property
    def height(self) -> float:
        return max(self.max_y - self.min_y, 0.0)

    def world_to_local(self, wx: float, wy: float) -> Tuple[float, float]:
        return (wx - self.min_x, wy - self.min_y)

    def local_to_world(self, lx: float, ly: float) -> Tuple[float, float]:
        return (lx + self.min_x, ly + self.min_y)

    def _build_polygon(self) -> None:
        if not self.segments:
            self._local_polygon = []
            return
        local_segs: List[Segment] = []
        for wx1, wy1, wx2, wy2 in self.segments:
            lx1, ly1 = self.world_to_local(wx1, wy1)
            lx2, ly2 = self.world_to_local(wx2, wy2)
            local_segs.append((lx1, ly1, lx2, ly2))
        self._local_polygon = chain_segments_to_polygon(local_segs)

    def rebuild_polygon(self) -> None:
        self._compute_bounds()
        self._build_polygon()

    def contains_local_point(self, lx: float, ly: float) -> bool:
        if len(self._local_polygon) < 3:
            return False
        return point_in_polygon(lx, ly, self._local_polygon)

    def contains_world_point(self, wx: float, wy: float) -> bool:
        lx, ly = self.world_to_local(wx, wy)
        return self.contains_local_point(lx, ly)

    def contains_world_point_with_tolerance(
        self, wx: float, wy: float, tolerance_ft: float = 1.0
    ) -> bool:
        lx, ly = self.world_to_local(wx, wy)
        if self.contains_local_point(lx, ly):
            return True
        if tolerance_ft <= 0.0:
            return False
        for wx1, wy1, wx2, wy2 in self.segments:
            sx1, sy1 = self.world_to_local(wx1, wy1)
            sx2, sy2 = self.world_to_local(wx2, wy2)
            if point_to_segment_distance(lx, ly, sx1, sy1, sx2, sy2) <= tolerance_ft:
                return True
        return False

    def next_anchor_id(self, room_index: int = 1) -> str:
        prefix = f"R{room_index}A"
        existing = {a.id for a in self.anchors}
        for i in range(26):
            candidate = f"{prefix}{i}"
            if candidate not in existing:
                return candidate
        return f"{prefix}{len(self.anchors)}"

    def to_dict(self) -> dict:
        reference_anchor_id = self.reference_anchor_id
        if reference_anchor_id is None and self.anchors:
            reference_anchor_id = self.anchors[0].id
        rtls_settings = {
            "tag_height_ft": 0.0,
            "filter_mode": "None",
            "ble_module_port": "",
            **dict(self.rtls_settings),
        }
        return {
            "room_name": self.name,
            "units": "ft",
            "rtls_settings": rtls_settings,
            "reference_anchor_id": reference_anchor_id,
            "room_bounds_ft": {
                "min_x": round(self.min_x, 3),
                "min_y": round(self.min_y, 3),
                "max_x": round(self.max_x, 3),
                "max_y": round(self.max_y, 3),
                "width": round(self.width, 3),
                "height": round(self.height, 3),
            },
            "anchors": [a.to_dict() for a in self.anchors],
            "edges": [[str(u), str(v)] for u, v in self.edges],
            "segments_ft": [
                {"x1": round(x1, 3), "y1": round(y1, 3),
                 "x2": round(x2, 3), "y2": round(y2, 3)}
                for x1, y1, x2, y2 in self.segments
            ],
            "interior_segments_ft": [
                {"x1": round(x1, 3), "y1": round(y1, 3),
                 "x2": round(x2, 3), "y2": round(y2, 3)}
                for x1, y1, x2, y2 in self.interior_segments
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Room":
        segments: List[Segment] = [
            (float(s["x1"]), float(s["y1"]), float(s["x2"]), float(s["y2"]))
            for s in d.get("segments_ft", [])
        ]
        interior: List[Segment] = [
            (float(s["x1"]), float(s["y1"]), float(s["x2"]), float(s["y2"]))
            for s in d.get("interior_segments_ft", [])
        ]
        room = cls(
            name=str(d.get("room_name", "Room")),
            segments=segments,
            interior_segments=interior,
            rtls_settings={
                "tag_height_ft": 0.0,
                "filter_mode": "None",
                "ble_module_port": "",
                **dict(d.get("rtls_settings", {})),
            },
            reference_anchor_id=d.get("reference_anchor_id"),
        )
        room.anchors = [Anchor.from_dict(a) for a in d.get("anchors", [])]
        room.edges = [(str(edge[0]), str(edge[1])) for edge in d.get("edges", []) if len(edge) == 2]
        if room.reference_anchor_id is None and room.anchors:
            room.reference_anchor_id = room.anchors[0].id
        return room
