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
