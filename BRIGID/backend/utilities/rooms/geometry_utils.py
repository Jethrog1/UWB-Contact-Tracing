
from __future__ import annotations

import math
from typing import List, Optional, Tuple

Segment = Tuple[float, float, float, float]                    
Point = Tuple[float, float]

def _points_close(a: Point, b: Point, eps: float = 1e-4) -> bool:
    return abs(float(a[0]) - float(b[0])) <= eps and abs(float(a[1]) - float(b[1])) <= eps

def point_to_segment_distance(px: float, py: float,
                               x1: float, y1: float,
                               x2: float, y2: float) -> float:
    dx = x2 - x1
    dy = y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
    proj_x = x1 + t * dx
    proj_y = y1 + t * dy
    return math.hypot(px - proj_x, py - proj_y)

def point_in_polygon(px: float, py: float, polygon: List[Point]) -> bool:
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

def chain_segments_to_polygon(segments: List[Segment], eps: float = 1e-4) -> List[Point]:
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

def build_room_bounds(segments: List[Segment]) -> Tuple[float, float, float, float]:
    if not segments:
        return 0.0, 0.0, 0.0, 0.0
    xs: List[float] = []
    ys: List[float] = []
    for x1, y1, x2, y2 in segments:
        xs.extend([float(x1), float(x2)])
        ys.extend([float(y1), float(y2)])
    return min(xs), min(ys), max(xs), max(ys)

def find_connected_segments(
    all_segments: List[Segment],
    start_idx: int,
    eps: float = 1e-3,
) -> List[int]:
    if not all_segments or start_idx < 0 or start_idx >= len(all_segments):
        return []

    visited = {start_idx}
    queue = [start_idx]

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

def normalize_segment(seg: Segment) -> tuple:
    x1, y1, x2, y2 = seg
    a = (round(float(x1), 4), round(float(y1), 4))
    b = (round(float(x2), 4), round(float(y2), 4))
    return (a, b) if a <= b else (b, a)

def _intersect_t_on_a(
    ax1: float, ay1: float, ax2: float, ay2: float,
    bx1: float, by1: float, bx2: float, by2: float,
) -> Optional[float]:
    dax = ax2 - ax1;  day = ay2 - ay1
    dbx = bx2 - bx1;  dby = by2 - by1
    denom = dax * dby - day * dbx
    if abs(denom) < 1e-12:
        return None
    dx = bx1 - ax1;  dy = by1 - ay1
    t = (dx * dby - dy * dbx) / denom
    s = (dx * day - dy * dax) / denom
    EPS = 1e-4
    if -EPS <= t <= 1 + EPS and -EPS <= s <= 1 + EPS:
        return max(0.0, min(1.0, t))
    return None

def _project_t_on_a(
    ax1: float, ay1: float, ax2: float, ay2: float,
    px: float, py: float,
) -> float:
    dx, dy = ax2 - ax1, ay2 - ay1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return 0.0
    return max(0.0, min(1.0, ((px - ax1) * dx + (py - ay1) * dy) / seg_len_sq))

def _segment_breaks(segments: List[Segment], seg_idx: int) -> List[float]:
    x1, y1, x2, y2 = segments[seg_idx]
    dx, dy = x2 - x1, y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return [0.0, 1.0]
    seg_len = math.sqrt(seg_len_sq)
    snap_world = max(seg_len * 2e-3, 0.01)
    breaks = [0.0, 1.0]
    for j, (bx1, by1, bx2, by2) in enumerate(segments):
        if j == seg_idx:
            continue
        t = _intersect_t_on_a(x1, y1, x2, y2, bx1, by1, bx2, by2)
        if t is not None:
            breaks.append(t)
            continue
        for px, py in ((bx1, by1), (bx2, by2)):
            d = point_to_segment_distance(px, py, x1, y1, x2, y2)
            if d < snap_world:
                t_snap = _project_t_on_a(x1, y1, x2, y2, px, py)
                if snap_world / seg_len < t_snap < 1 - snap_world / seg_len:
                    breaks.append(t_snap)
    breaks.sort()
    deduped = [breaks[0]]
    for t in breaks[1:]:
        if abs(t - deduped[-1]) > 1e-9:
            deduped.append(t)
    return deduped

def _all_atomic_subsegments(segments: List[Segment]) -> List[Segment]:
    unique: List[Segment] = []
    seen: set = set()

    def norm(seg: Segment) -> tuple:
        ax, ay, bx, by = seg
        p1 = (round(ax, 4), round(ay, 4))
        p2 = (round(bx, 4), round(by, 4))
        return (p1, p2) if p1 <= p2 else (p2, p1)

    for seg_idx, (x1, y1, x2, y2) in enumerate(segments):
        dx, dy = x2 - x1, y2 - y1
        breaks = _segment_breaks(segments, seg_idx)
        for i in range(len(breaks) - 1):
            t0, t1 = breaks[i], breaks[i + 1]
            if t1 - t0 <= 1e-9:
                continue
            seg: Segment = (
                x1 + t0 * dx, y1 + t0 * dy,
                x1 + t1 * dx, y1 + t1 * dy,
            )
            if math.hypot(seg[2] - seg[0], seg[3] - seg[1]) < 1e-6:
                continue
            key = norm(seg)
            if key in seen:
                continue
            seen.add(key)
            unique.append(seg)
    return unique

def detect_room_boundary(
    segments: List[Segment],
    wx: float,
    wy: float,
) -> Optional[List[Segment]]:
    atomic = _all_atomic_subsegments(segments)
    if len(atomic) < 3:
        return None

    vertex_ids: dict = {}
    vertex_points: List[Tuple[float, float]] = []
    edges = []

    def get_vid(x: float, y: float) -> int:
        key = (round(x, 4), round(y, 4))
        vid = vertex_ids.get(key)
        if vid is None:
            vid = len(vertex_points)
            vertex_ids[key] = vid
            vertex_points.append((x, y))
        return vid

    for seg in atomic:
        v1 = get_vid(seg[0], seg[1])
        v2 = get_vid(seg[2], seg[3])
        if v1 != v2:
            edges.append((v1, v2, seg))

    if len(edges) < 3:
        return None

    halfedges: List[dict] = []
    outgoing: dict = {i: [] for i in range(len(vertex_points))}

    for edge_idx, (u, v, seg) in enumerate(edges):
        ux, uy = vertex_points[u]
        vx, vy = vertex_points[v]
        a_uv = math.atan2(vy - uy, vx - ux)
        a_vu = math.atan2(uy - vy, ux - vx)
        i1 = len(halfedges)
        halfedges.append({"origin": u, "dest": v, "rev": i1 + 1, "next": None, "seg": seg})
        i2 = len(halfedges)
        halfedges.append({"origin": v, "dest": u, "rev": i1, "next": None, "seg": seg})
        outgoing[u].append((a_uv, i1))
        outgoing[v].append((a_vu, i2))

    for vid in outgoing:
        outgoing[vid].sort(key=lambda item: item[0])

    pos_in_outgoing: dict = {}
    for vid, items in outgoing.items():
        for idx, (_, hedge_idx) in enumerate(items):
            pos_in_outgoing[hedge_idx] = idx

    for hedge_idx, hedge in enumerate(halfedges):
        dest = hedge["dest"]
        rev_idx = hedge["rev"]
        out = outgoing[dest]
        if not out:
            continue
        rev_pos = pos_in_outgoing[rev_idx]
        next_idx = out[(rev_pos - 1) % len(out)][1]
        hedge["next"] = next_idx

    best_cycle = None
    best_area: Optional[float] = None
    visited: set = set()

    for start_idx in range(len(halfedges)):
        if start_idx in visited:
            continue
        cycle: List[int] = []
        seen_local: dict = {}
        cur: Optional[int] = start_idx
        while cur is not None and cur not in seen_local:
            seen_local[cur] = len(cycle)
            cycle.append(cur)
            cur = halfedges[cur]["next"]
        if cur is None or cur not in seen_local:
            continue
        loop = cycle[seen_local[cur]:]
        for idx in loop:
            visited.add(idx)
        points = [vertex_points[halfedges[idx]["origin"]] for idx in loop]
        if len(points) < 3:
            continue
        area = 0.0
        for i in range(len(points)):
            x1, y1 = points[i]
            x2, y2 = points[(i + 1) % len(points)]
            area += x1 * y2 - x2 * y1
        area /= 2.0
        if abs(area) < 1e-4:
            continue
        if not point_in_polygon(wx, wy, points):
            continue
        if best_area is None or abs(area) < best_area:
            best_area = abs(area)
            best_cycle = loop

    if not best_cycle:
        return None

    boundary: List[Segment] = []
    seen_seg: set = set()
    for idx in best_cycle:
        seg = halfedges[idx]["seg"]
        key = (
            round(min(seg[0], seg[2]), 4),
            round(min(seg[1], seg[3]), 4),
            round(max(seg[0], seg[2]), 4),
            round(max(seg[1], seg[3]), 4),
        )
        if key not in seen_seg:
            seen_seg.add(key)
            boundary.append(seg)
    return boundary

def compute_subsegment(
    segments: List[Segment],
    seg_idx: int,
    wx: float,
    wy: float,
) -> Segment:
    x1, y1, x2, y2 = segments[seg_idx]
    dx, dy = x2 - x1, y2 - y1
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-12:
        return (x1, y1, x2, y2)
    t_click = max(0.0, min(1.0, ((wx - x1) * dx + (wy - y1) * dy) / seg_len_sq))
    deduped = _segment_breaks(segments, seg_idx)
    t_left, t_right = 0.0, 1.0
    for i in range(len(deduped) - 1):
        if deduped[i] <= t_click <= deduped[i + 1]:
            t_left = deduped[i]
            t_right = deduped[i + 1]
            break
    return (
        x1 + t_left * dx,  y1 + t_left * dy,
        x1 + t_right * dx, y1 + t_right * dy,
    )
