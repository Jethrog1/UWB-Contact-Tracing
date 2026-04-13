"""
geometry_utils.py — Geometric helpers for room/anchor management (no PyQt6).
"""

from __future__ import annotations

import math
from typing import List, Tuple


Segment = Tuple[float, float, float, float]  # (x1, y1, x2, y2)
Point = Tuple[float, float]


# ---------------------------------------------------------------------------
# Point / Segment helpers
# ---------------------------------------------------------------------------

def _points_close(a: Point, b: Point, eps: float = 1e-4) -> bool:
    return abs(float(a[0]) - float(b[0])) <= eps and abs(float(a[1]) - float(b[1])) <= eps


def point_to_segment_distance(px: float, py: float,
                               x1: float, y1: float,
                               x2: float, y2: float) -> float:
    """Perpendicular distance from point (px, py) to finite segment (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)


# ---------------------------------------------------------------------------
# Polygon containment — pure Python ray-casting (replaces QPolygonF)
# ---------------------------------------------------------------------------

def point_in_polygon(px: float, py: float, polygon: List[Point]) -> bool:
    """
    Ray-casting point-in-polygon test (OddEven fill rule).
    polygon: ordered list of (x, y) vertices.
    Returns True if (px, py) is strictly inside.
    """
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside


# ---------------------------------------------------------------------------
# Polygon building — chain segments into ordered vertex list
# ---------------------------------------------------------------------------

def chain_segments_to_polygon(segments: List[Segment], eps: float = 1e-4) -> List[Point]:
    """
    Greedily chain unordered line segments into a continuous polygon vertex list.
    Handles disconnected segments by simply appending them (graceful degradation).
    Returns a list of (x, y) points.
    """
    if not segments:
        return []

    local_segs = [[(x1, y1), (x2, y2)] for x1, y1, x2, y2 in segments]
    unvisited = local_segs[1:]
    chain: List[Point] = list(local_segs[0])

    while unvisited:
        progress = False
        last_pt = chain[-1]
        first_pt = chain[0]

        for i, seg in enumerate(unvisited):
            if _points_close(seg[0], last_pt, eps):
                chain.append(seg[1])
                unvisited.pop(i)
                progress = True
                break
            elif _points_close(seg[1], last_pt, eps):
                chain.append(seg[0])
                unvisited.pop(i)
                progress = True
                break
            elif _points_close(seg[0], first_pt, eps):
                chain.insert(0, seg[1])
                unvisited.pop(i)
                progress = True
                break
            elif _points_close(seg[1], first_pt, eps):
                chain.insert(0, seg[0])
                unvisited.pop(i)
                progress = True
                break

        if not progress and unvisited:
            seg = unvisited.pop(0)
            chain.extend(seg)

    return chain


# ---------------------------------------------------------------------------
# Bounding box
# ---------------------------------------------------------------------------

def build_room_bounds(segments: List[Segment]) -> Tuple[float, float, float, float]:
    """Return (min_x, min_y, max_x, max_y) from a list of segments."""
    if not segments:
        return 0.0, 0.0, 0.0, 0.0
    xs: List[float] = []
    ys: List[float] = []
    for x1, y1, x2, y2 in segments:
        xs.extend([float(x1), float(x2)])
        ys.extend([float(y1), float(y2)])
    return min(xs), min(ys), max(xs), max(ys)


# ---------------------------------------------------------------------------
# Segment connectivity
# ---------------------------------------------------------------------------

def find_connected_segments(
    all_segments: List[Segment],
    start_idx: int,
    eps: float = 1e-3,
) -> List[int]:
    """
    BFS/flood-fill: find all segment indices connected (sharing endpoints) to
    all_segments[start_idx].  Returns a list of indices (including start_idx).
    """
    if not all_segments or start_idx < 0 or start_idx >= len(all_segments):
        return []

    visited = {start_idx}
    queue = [start_idx]

    # Build adjacency: endpoint → segment indices
    from collections import defaultdict
    endpoint_map: dict[tuple, list[int]] = defaultdict(list)
    for idx, (x1, y1, x2, y2) in enumerate(all_segments):
        k1 = (round(float(x1), 3), round(float(y1), 3))
        k2 = (round(float(x2), 3), round(float(y2), 3))
        endpoint_map[k1].append(idx)
        endpoint_map[k2].append(idx)

    while queue:
        cur = queue.pop()
        x1, y1, x2, y2 = all_segments[cur]
        k1 = (round(float(x1), 3), round(float(y1), 3))
        k2 = (round(float(x2), 3), round(float(y2), 3))
        for k in (k1, k2):
            for neighbor in endpoint_map.get(k, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

    return sorted(visited)


# ---------------------------------------------------------------------------
# Segment normalization (for deduplication / comparison)
# ---------------------------------------------------------------------------

def normalize_segment(seg: Segment) -> tuple:
    x1, y1, x2, y2 = seg
    a = (round(float(x1), 4), round(float(y1), 4))
    b = (round(float(x2), 4), round(float(y2), 4))
    return (a, b) if a <= b else (b, a)
