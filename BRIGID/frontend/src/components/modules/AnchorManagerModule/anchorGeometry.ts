import { AnchorData, RoomData, SegmentData } from '../../../types'

export interface SnapTarget {
  x: number
  y: number
  distance: number
  kind: 'endpoint' | 'segment'
}

type Point = [number, number]

const pointsClose = (a: Point, b: Point, eps = 1e-4): boolean => (
  Math.abs(a[0] - b[0]) <= eps && Math.abs(a[1] - b[1]) <= eps
)

export const segmentsEqual = (a: SegmentData, b: SegmentData, eps = 1e-3): boolean => (
  (pointsClose([a.x1, a.y1], [b.x1, b.y1], eps) && pointsClose([a.x2, a.y2], [b.x2, b.y2], eps))
  || (pointsClose([a.x1, a.y1], [b.x2, b.y2], eps) && pointsClose([a.x2, a.y2], [b.x1, b.y1], eps))
)

export const segmentsMatch = (segmentsA: SegmentData[], segmentsB: SegmentData[], eps = 1e-3): boolean => {
  if (segmentsA.length !== segmentsB.length) return false

  const unmatched = [...segmentsB]
  for (const segmentA of segmentsA) {
    const matchIndex = unmatched.findIndex(segmentB => segmentsEqual(segmentA, segmentB, eps))
    if (matchIndex === -1) return false
    unmatched.splice(matchIndex, 1)
  }

  return unmatched.length === 0
}

export const getAnchorWorldPosition = (room: RoomData, anchor: AnchorData): Point => (
  [room.room_bounds_ft.min_x + anchor.x_ft, room.room_bounds_ft.min_y + anchor.y_ft]
)

export const pointToSegmentDistance = (
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number => {
  const dx = x2 - x1
  const dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-12) return Math.hypot(px - x1, py - y1)
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}

export const projectPointOnSegment = (
  px: number,
  py: number,
  segment: SegmentData,
): Point => {
  const dx = segment.x2 - segment.x1
  const dy = segment.y2 - segment.y1
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-12) return [segment.x1, segment.y1]
  const t = Math.max(0, Math.min(1, ((px - segment.x1) * dx + (py - segment.y1) * dy) / lenSq))
  return [segment.x1 + t * dx, segment.y1 + t * dy]
}

export const chainSegmentsToPolygon = (segments: SegmentData[]): Point[] => {
  if (segments.length === 0) return []

  const localSegments = segments.map(seg => [[seg.x1, seg.y1], [seg.x2, seg.y2]] as [Point, Point])
  const unvisited = localSegments.slice(1)
  const chain: Point[] = [...localSegments[0]]

  while (unvisited.length > 0) {
    const lastPoint = chain[chain.length - 1]
    const firstPoint = chain[0]
    const matchIndex = unvisited.findIndex(([a, b]) => (
      pointsClose(a, lastPoint) ||
      pointsClose(b, lastPoint) ||
      pointsClose(a, firstPoint) ||
      pointsClose(b, firstPoint)
    ))

    if (matchIndex === -1) {
      const [a, b] = unvisited.shift()!
      chain.push(a, b)
      continue
    }

    const [a, b] = unvisited.splice(matchIndex, 1)[0]
    if (pointsClose(a, lastPoint)) chain.push(b)
    else if (pointsClose(b, lastPoint)) chain.push(a)
    else if (pointsClose(a, firstPoint)) chain.unshift(b)
    else chain.unshift(a)
  }

  return chain
}

export const pointInPolygon = (px: number, py: number, polygon: Point[]): boolean => {
  if (polygon.length < 3) return false
  let inside = false
  let j = polygon.length - 1
  for (let i = 0; i < polygon.length; i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    const crosses = ((yi > py) !== (yj > py))
      && (px < ((xj - xi) * (py - yi)) / ((yj - yi) || 1e-12) + xi)
    if (crosses) inside = !inside
    j = i
  }
  return inside
}

export const roomContainsWorldPoint = (room: RoomData, wx: number, wy: number, tolerance = 0): boolean => {
  const polygon = chainSegmentsToPolygon(room.segments_ft)
  if (pointInPolygon(wx, wy, polygon)) return true
  if (tolerance <= 0) return false
  return room.segments_ft.some(seg => pointToSegmentDistance(wx, wy, seg.x1, seg.y1, seg.x2, seg.y2) <= tolerance)
}

export const findConnectedSegments = (
  start: SegmentData,
  allSegments: SegmentData[],
  eps = 1e-4,
): SegmentData[] => {
  const sharesEndpoint = (a: SegmentData, b: SegmentData): boolean => {
    const ap: Point[] = [[a.x1, a.y1], [a.x2, a.y2]]
    const bp: Point[] = [[b.x1, b.y1], [b.x2, b.y2]]
    return ap.some(pa => bp.some(pb => pointsClose(pa, pb, eps)))
  }

  const connected = new Set<SegmentData>([start])
  const queue: SegmentData[] = [start]

  while (queue.length > 0) {
    const current = queue.shift()!
    for (const seg of allSegments) {
      if (connected.has(seg)) continue
      if (sharesEndpoint(current, seg)) {
        connected.add(seg)
        queue.push(seg)
      }
    }
  }

  return [...connected]
}

export const findSnapTarget = (
  x: number,
  y: number,
  segments: SegmentData[],
  tolerance = 0.3,
): SnapTarget | null => {
  let best: SnapTarget | null = null

  const maybeSetBest = (candidate: SnapTarget) => {
    if (candidate.distance > tolerance) return
    if (!best || candidate.distance < best.distance) best = candidate
  }

  for (const seg of segments) {
    maybeSetBest({
      x: seg.x1,
      y: seg.y1,
      distance: Math.hypot(x - seg.x1, y - seg.y1),
      kind: 'endpoint',
    })
    maybeSetBest({
      x: seg.x2,
      y: seg.y2,
      distance: Math.hypot(x - seg.x2, y - seg.y2),
      kind: 'endpoint',
    })

    const [projX, projY] = projectPointOnSegment(x, y, seg)
    maybeSetBest({
      x: projX,
      y: projY,
      distance: Math.hypot(x - projX, y - projY),
      kind: 'segment',
    })
  }

  return best
}

const segmentIntersectionT = (
  x1: number, y1: number, x2: number, y2: number,
  x3: number, y3: number, x4: number, y4: number,
  eps = 1e-12,
): number | null => {
  const d1x = x2 - x1
  const d1y = y2 - y1
  const d2x = x4 - x3
  const d2y = y4 - y3
  const denom = d1x * d2y - d1y * d2x
  if (Math.abs(denom) < eps) return null

  const dx = x3 - x1
  const dy = y3 - y1
  const t = (dx * d2y - dy * d2x) / denom
  const u = (dx * d1y - dy * d1x) / denom
  const rangeEps = 1e-4
  if (t < -rangeEps || t > 1 + rangeEps || u < -rangeEps || u > 1 + rangeEps) return null
  return Math.max(0, Math.min(1, t))
}

const projectTOnSegment = (segment: SegmentData, px: number, py: number): number => {
  const dx = segment.x2 - segment.x1
  const dy = segment.y2 - segment.y1
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-12) return 0
  return Math.max(0, Math.min(1, ((px - segment.x1) * dx + (py - segment.y1) * dy) / lenSq))
}

const getSegmentBreaks = (target: SegmentData, allSegments: SegmentData[]): number[] => {
  const dx = target.x2 - target.x1
  const dy = target.y2 - target.y1
  const segLenSq = dx * dx + dy * dy
  if (segLenSq < 1e-12) return [0, 1]

  const segLen = Math.sqrt(segLenSq)
  const snapWorld = Math.max(segLen * 2e-3, 0.01)
  const breaks = [0, 1]

  for (const seg of allSegments) {
    if (seg === target) continue
    const t = segmentIntersectionT(target.x1, target.y1, target.x2, target.y2, seg.x1, seg.y1, seg.x2, seg.y2)
    if (t !== null) {
      breaks.push(t)
      continue
    }

    for (const [px, py] of [[seg.x1, seg.y1], [seg.x2, seg.y2]] as Point[]) {
      const distance = pointToSegmentDistance(px, py, target.x1, target.y1, target.x2, target.y2)
      if (distance < snapWorld) {
        const tSnap = projectTOnSegment(target, px, py)
        if (snapWorld / segLen < tSnap && tSnap < 1 - snapWorld / segLen) breaks.push(tSnap)
      }
    }
  }

  breaks.sort((a, b) => a - b)
  const deduped = [breaks[0]]
  for (const value of breaks.slice(1)) {
    if (Math.abs(value - deduped[deduped.length - 1]) > 1e-9) deduped.push(value)
  }
  return deduped
}

export const getClickedSubsegment = (
  target: SegmentData,
  allSegments: SegmentData[],
  clickX: number,
  clickY: number,
): SegmentData => {
  const dx = target.x2 - target.x1
  const dy = target.y2 - target.y1
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-12) return target

  const tClick = Math.max(0, Math.min(1, ((clickX - target.x1) * dx + (clickY - target.y1) * dy) / lenSq))
  const breaks = getSegmentBreaks(target, allSegments)
  let tLeft = 0
  let tRight = 1
  for (let i = 0; i < breaks.length - 1; i++) {
    if (breaks[i] <= tClick && tClick <= breaks[i + 1]) {
      tLeft = breaks[i]
      tRight = breaks[i + 1]
      break
    }
  }

  return {
    x1: target.x1 + tLeft * dx,
    y1: target.y1 + tLeft * dy,
    x2: target.x1 + tRight * dx,
    y2: target.y1 + tRight * dy,
  }
}

export const getRoomReferenceAnchor = (room: RoomData): AnchorData | null => (
  room.anchors.find(anchor => anchor.id === room.reference_anchor_id)
  ?? room.anchors[0]
  ?? null
)

export const getAnchorRelativeBounds = (room: RoomData) => {
  const reference = getRoomReferenceAnchor(room)
  if (!reference) {
    return {
      width: 0,
      height: 0,
      anchors: [] as Array<AnchorData & { relX: number; relY: number }>,
    }
  }

  const anchors = room.anchors.map(anchor => ({
    ...anchor,
    relX: anchor.x_ft - reference.x_ft,
    relY: anchor.y_ft - reference.y_ft,
  }))

  const xs = anchors.map(anchor => anchor.relX)
  const ys = anchors.map(anchor => anchor.relY)
  const minX = Math.min(...xs, 0)
  const maxX = Math.max(...xs, 0)
  const minY = Math.min(...ys, 0)
  const maxY = Math.max(...ys, 0)

  return {
    width: maxX - minX,
    height: maxY - minY,
    minX,
    maxX,
    minY,
    maxY,
    anchors,
  }
}
