import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from 'react'
import { RoomData, SegmentData } from '../../../types'
import { chainSegmentsToPolygon, pointInPolygon } from '../AnchorManagerModule/anchorGeometry'
import { FloorplanSettings } from './RTLSDashboard'

export interface RTLSViewport {
  offsetX: number
  offsetY: number
  scale: number
}

export interface RTLSTagState {
  tag_id: string
  status: string
  position: { x: number; y: number } | null
  color: string
}

interface RTLSDashboardCanvasProps {
  mode: 'floor-plan' | 'room'
  floorplanSegments: SegmentData[]
  rooms: RoomData[]
  activeRoomName: string | null
  currentRoom: RoomData | null
  hoverRoomName?: string | null
  anchors: Record<string, [number, number]>
  tags: RTLSTagState[]
  referenceAnchorId?: string
  floorplanSettings?: FloorplanSettings
  onRoomClick?: (roomName: string) => void
  onRoomDoubleClick?: (roomName: string) => void
  onRoomHover?: (roomName: string | null) => void
}

export interface RTLSDashboardCanvasHandle {
  resetView: () => void
  zoomIn: () => void
  zoomOut: () => void
}

const BG = '#0a0b0d'
const FLOORPLAN_SEGMENT = '#314052'
const FLOORPLAN_NON_WALL = '#556172'
const ROOM_OUTLINE = '#2060b0'
const ROOM_OUTLINE_ACTIVE = '#4a9eff'
const ROOM_OUTLINE_HOVER = '#3a78c0'
const ROOM_FILL = 'rgba(74, 158, 255, 0.035)'
const ROOM_FILL_ACTIVE = 'rgba(74, 158, 255, 0.08)'
const ROOM_FILL_HOVER = 'rgba(74, 158, 255, 0.055)'
const ANCHOR_COLOR_FP = '#ff9b38'
const ANCHOR_LABEL_COLOR = '#ffffff'

const FP_CELL_FT = 0.02
const FP_BASE_HEAT = 0.08
const FP_MARGIN_FT = 1.0

const TAG_PALETTE = [
  '#3a9fe8', '#e67e22', '#9b59b6', '#27ae60',
  '#e74c3c', '#f1c40f', '#1abc9c', '#d16cff',
]

const ANCHOR_COLORS = ['#e05c5c', '#4ec97e', '#a070e8', '#e8a030', '#40c4e0']

export function tagColor(index: number): string {
  return TAG_PALETTE[index % TAG_PALETTE.length]
}

function anchorColor(index: number): string {
  return ANCHOR_COLORS[index % ANCHOR_COLORS.length]
}

const worldToScreen = (vp: RTLSViewport, wx: number, wy: number): [number, number] => (
  [wx * vp.scale + vp.offsetX, wy * vp.scale + vp.offsetY]
)

const screenToWorld = (vp: RTLSViewport, sx: number, sy: number): [number, number] => (
  [(sx - vp.offsetX) / vp.scale, (sy - vp.offsetY) / vp.scale]
)

const segmentBounds = (segments: SegmentData[]): { minX: number; minY: number; maxX: number; maxY: number } | null => {
  if (segments.length === 0) return null
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const seg of segments) {
    minX = Math.min(minX, seg.x1, seg.x2)
    minY = Math.min(minY, seg.y1, seg.y2)
    maxX = Math.max(maxX, seg.x1, seg.x2)
    maxY = Math.max(maxY, seg.y1, seg.y2)
  }
  return { minX, minY, maxX, maxY }
}

const roomBounds = (rooms: RoomData[]): { minX: number; minY: number; maxX: number; maxY: number } | null => {
  if (rooms.length === 0) return null
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const room of rooms) {
    const bounds = room.room_bounds_ft
    minX = Math.min(minX, bounds.min_x)
    minY = Math.min(minY, bounds.min_y)
    maxX = Math.max(maxX, bounds.max_x)
    maxY = Math.max(maxY, bounds.max_y)
  }
  return { minX, minY, maxX, maxY }
}

const toRoomLocal = (room: RoomData, x: number, y: number): [number, number] => ([
  x - room.room_bounds_ft.min_x,
  y - room.room_bounds_ft.min_y,
])

const localizeSegment = (room: RoomData, segment: SegmentData): SegmentData => {
  const [x1, y1] = toRoomLocal(room, segment.x1, segment.y1)
  const [x2, y2] = toRoomLocal(room, segment.x2, segment.y2)
  return { x1, y1, x2, y2 }
}

const roomPolygon = (room: RoomData): [number, number][] => chainSegmentsToPolygon(room.segments_ft)
const roomLocalPolygon = (room: RoomData): [number, number][] => (
  chainSegmentsToPolygon(room.segments_ft.map(segment => localizeSegment(room, segment)))
)

const roomAtPoint = (rooms: RoomData[], worldX: number, worldY: number): string | null => {
  for (const room of rooms) {
    if (room.segments_ft.length < 3) continue
    const polygon = roomPolygon(room)
    if (polygon.length >= 3 && pointInPolygon(worldX, worldY, polygon)) {
      return room.room_name
    }
  }
  return null
}

function buildLUT(): Uint8Array {
  const lut = new Uint8Array(256 * 3)
  const stops: [number, number, number, number][] = [
    [0.00, 0, 0, 120],
    [0.05, 0, 30, 180],
    [0.10, 0, 70, 230],
    [0.16, 0, 120, 255],
    [0.22, 0, 170, 255],
    [0.28, 0, 210, 245],
    [0.34, 0, 230, 200],
    [0.40, 0, 245, 160],
    [0.46, 0, 255, 110],
    [0.52, 80, 255, 60],
    [0.58, 160, 255, 20],
    [0.64, 220, 255, 0],
    [0.70, 255, 230, 0],
    [0.76, 255, 195, 0],
    [0.82, 255, 150, 0],
    [0.88, 255, 95, 0],
    [0.93, 235, 45, 5],
    [0.97, 190, 15, 0],
    [1.00, 120, 0, 0],
  ]
  for (let i = 0; i < 256; i++) {
    const value = i / 255
    let start = stops[0]
    let end = stops[1]
    for (let j = 0; j < stops.length - 1; j++) {
      if (value >= stops[j][0] && value <= stops[j + 1][0]) {
        start = stops[j]
        end = stops[j + 1]
        break
      }
    }
    const span = end[0] - start[0]
    const t = span > 0 ? (value - start[0]) / span : 0
    const eased = t * t * (3 - 2 * t)
    lut[i * 3] = Math.round(start[1] + (end[1] - start[1]) * eased)
    lut[i * 3 + 1] = Math.round(start[2] + (end[2] - start[2]) * eased)
    lut[i * 3 + 2] = Math.round(start[3] + (end[3] - start[3]) * eased)
  }
  return lut
}

const LUT = buildLUT()
const LUT32 = new Uint32Array(256)
for (let i = 0; i < 256; i++) {
  LUT32[i] = LUT[i * 3]
    | (LUT[i * 3 + 1] << 8)
    | (LUT[i * 3 + 2] << 16)
    | (210 << 24)
}

function depositHeat(
  p1x: number,
  p1y: number,
  p2x: number,
  p2y: number,
  heat: Float32Array,
  heatMask: Uint8Array,
  gridW: number,
  gridH: number,
  gridOX: number,
  gridOY: number,
  gradientRate: number,
  rangeFt: number,
  cellFt: number,
): void {
  const maxDist = rangeFt
  const fieldRad = rangeFt * 0.28
  const depositBase = 0.005 / gradientRate

  const pdx = p2x - p1x
  const pdy = p2y - p1y
  const dist2 = pdx * pdx + pdy * pdy
  if (dist2 >= maxDist * maxDist) return

  const dist = Math.sqrt(dist2)
  const closeness = 1 - dist / maxDist
  const strength = depositBase * Math.pow(closeness, 2.2)
  if (strength <= 0) return

  const x1g = (p1x - gridOX) / cellFt
  const y1g = (p1y - gridOY) / cellFt
  const x2g = (p2x - gridOX) / cellFt
  const y2g = (p2y - gridOY) / cellFt

  const iterR = Math.min(60, Math.max(3, fieldRad / cellFt))
  const iterR2 = iterR * iterR
  const pad = Math.ceil(iterR) + 1
  const minX = Math.max(0, Math.floor(Math.min(x1g, x2g) - pad))
  const maxX = Math.min(gridW - 1, Math.ceil(Math.max(x1g, x2g) + pad))
  const minY = Math.max(0, Math.floor(Math.min(y1g, y2g) - pad))
  const maxY = Math.min(gridH - 1, Math.ceil(Math.max(y1g, y2g) + pad))
  if (minX > maxX || minY > maxY) return

  const sdx = x2g - x1g
  const sdy = y2g - y1g
  const slen2 = sdx * sdx + sdy * sdy
  const midX = (x1g + x2g) * 0.5
  const midY = (y1g + y2g) * 0.5
  const mR2 = Math.pow(Math.max(2.0, iterR * 0.95), 2) * 2

  for (let gy = minY; gy <= maxY; gy++) {
    const rowBase = gy * gridW
    for (let gx = minX; gx <= maxX; gx++) {
      const idx = rowBase + gx
      if (!heatMask[idx]) continue

      const px = gx + 0.5
      const py = gy + 0.5

      let dSeg2: number
      if (slen2 < 1e-6) {
        const ex = px - x1g
        const ey = py - y1g
        dSeg2 = ex * ex + ey * ey
      } else {
        const t = Math.max(0, Math.min(1, ((px - x1g) * sdx + (py - y1g) * sdy) / slen2))
        const ex = px - (x1g + t * sdx)
        const ey = py - (y1g + t * sdy)
        dSeg2 = ex * ex + ey * ey
      }
      if (dSeg2 >= iterR2) continue

      const r = dSeg2 / iterR2
      const falloff = (1 - r) * (1 - r)

      const mdx = px - midX
      const mdy = py - midY
      const md2 = mdx * mdx + mdy * mdy
      const midpointWeight = md2 < mR2 ? Math.pow(1 - md2 / mR2, 2) : 0

      const next = heat[idx] + falloff * (0.65 + 0.35 * midpointWeight) * strength
      heat[idx] = next < 1 ? next : 1
    }
  }
}

interface RuntimeProps {
  mode: 'floor-plan' | 'room'
  floorplanSegments: SegmentData[]
  rooms: RoomData[]
  activeRoomName: string | null
  activeRoom: RoomData | null
  hoverRoomName?: string | null
  anchors: Record<string, [number, number]>
  tags: RTLSTagState[]
  referenceAnchorId?: string
  floorplanSettings?: FloorplanSettings
}

const RTLSDashboardCanvas = forwardRef<RTLSDashboardCanvasHandle, RTLSDashboardCanvasProps>((
  props,
  ref,
) => {
  const {
    mode,
    floorplanSegments,
    rooms,
    activeRoomName,
    currentRoom,
    hoverRoomName,
    anchors,
    tags,
    referenceAnchorId,
    floorplanSettings,
    onRoomClick,
    onRoomDoubleClick,
    onRoomHover,
  } = props

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const vpRef = useRef<RTLSViewport>({ offsetX: 0, offsetY: 0, scale: 20 })
  const dragRef = useRef<{ x: number; y: number } | null>(null)
  const hoverRoomRef = useRef<string | null>(null)
  const rafRef = useRef(0)

  const activeRoom = currentRoom ?? rooms.find(room => room.room_name === activeRoomName) ?? null

  const propsRef = useRef<RuntimeProps>({
    mode,
    floorplanSegments,
    rooms,
    activeRoomName,
    activeRoom,
    hoverRoomName,
    anchors,
    tags,
    referenceAnchorId,
    floorplanSettings,
  })
  propsRef.current = {
    mode,
    floorplanSegments,
    rooms,
    activeRoomName,
    activeRoom,
    hoverRoomName,
    anchors,
    tags,
    referenceAnchorId,
    floorplanSettings,
  }

  // Floor-plan heat grid
  const heatRef = useRef<Float32Array>(new Float32Array(0))
  const heatMaskRef = useRef<Uint8Array>(new Uint8Array(0))
  const heatCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const gridWRef = useRef(0)
  const gridHRef = useRef(0)
  const gridOXRef = useRef(0)
  const gridOYRef = useRef(0)
  const heatKeyRef = useRef('')

  const displaySegments = mode === 'room'
    ? (activeRoom
        ? [...activeRoom.segments_ft, ...activeRoom.interior_segments_ft].map(segment => localizeSegment(activeRoom, segment))
        : [])
    : floorplanSegments

  const resetView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const padding = 70

    let bounds = segmentBounds(displaySegments)
    if (!bounds && mode === 'floor-plan') bounds = roomBounds(rooms)
    if (mode === 'room' && activeRoom) {
      bounds = {
        minX: 0,
        minY: 0,
        maxX: activeRoom.room_bounds_ft.width,
        maxY: activeRoom.room_bounds_ft.height,
      }
    }
    if (!bounds) return

    const width = Math.max(bounds.maxX - bounds.minX, 1)
    const height = Math.max(bounds.maxY - bounds.minY, 1)
    const scale = Math.min(
      (canvas.width - padding * 2) / width,
      (canvas.height - padding * 2) / height,
    )

    vpRef.current = {
      scale: Math.max(2, scale),
      offsetX: (canvas.width - width * Math.max(2, scale)) / 2 - bounds.minX * Math.max(2, scale),
      offsetY: (canvas.height - height * Math.max(2, scale)) / 2 - bounds.minY * Math.max(2, scale),
    }
  }, [activeRoom, displaySegments, mode, rooms])

  const zoomBy = useCallback((factor: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pivotX = canvas.width / 2
    const pivotY = canvas.height / 2
    const prev = vpRef.current
    const nextScale = Math.max(2, Math.min(300, prev.scale * factor))
    vpRef.current = {
      scale: nextScale,
      offsetX: pivotX - (pivotX - prev.offsetX) * (nextScale / prev.scale),
      offsetY: pivotY - (pivotY - prev.offsetY) * (nextScale / prev.scale),
    }
  }, [])

  useImperativeHandle(ref, () => ({
    resetView,
    zoomIn: () => zoomBy(1.15),
    zoomOut: () => zoomBy(1 / 1.15),
  }), [resetView, zoomBy])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const parent = canvas.parentElement
    if (!parent) return

    const observer = new ResizeObserver(() => {
      canvas.width = parent.clientWidth
      canvas.height = parent.clientHeight
      resetView()
    })
    observer.observe(parent)
    canvas.width = parent.clientWidth
    canvas.height = parent.clientHeight
    resetView()
    return () => observer.disconnect()
  }, [resetView])

  useEffect(() => {
    hoverRoomRef.current = null
    resetView()
  }, [mode, activeRoomName, activeRoom?.room_name, floorplanSegments.length, rooms.length, resetView])

  const ensureFloorplanHeatGrid = useCallback(() => {
    const runtime = propsRef.current
    const bounds = roomBounds(runtime.rooms) ?? segmentBounds(runtime.floorplanSegments)
    if (!bounds) return false
    const key = `${bounds.minX.toFixed(2)}|${bounds.minY.toFixed(2)}|${bounds.maxX.toFixed(2)}|${bounds.maxY.toFixed(2)}|${runtime.rooms.length}`
    if (key === heatKeyRef.current && heatRef.current.length > 0) return true

    const ox = bounds.minX - FP_MARGIN_FT
    const oy = bounds.minY - FP_MARGIN_FT
    const widthFt = (bounds.maxX - bounds.minX) + FP_MARGIN_FT * 2
    const heightFt = (bounds.maxY - bounds.minY) + FP_MARGIN_FT * 2
    const gridW = Math.max(4, Math.ceil(widthFt / FP_CELL_FT))
    const gridH = Math.max(4, Math.ceil(heightFt / FP_CELL_FT))

    gridOXRef.current = ox
    gridOYRef.current = oy
    gridWRef.current = gridW
    gridHRef.current = gridH

    const totalCells = gridW * gridH
    heatRef.current = new Float32Array(totalCells).fill(FP_BASE_HEAT)

    const heatCanvas = document.createElement('canvas')
    heatCanvas.width = gridW
    heatCanvas.height = gridH
    heatCanvasRef.current = heatCanvas

    const mask = new Uint8Array(totalCells)
    const polygons: [number, number][][] = []
    for (const room of runtime.rooms) {
      if (room.segments_ft.length < 3) continue
      const polygon = roomPolygon(room)
      if (polygon.length >= 3) polygons.push(polygon)
    }
    if (polygons.length === 0) {
      mask.fill(1)
    } else {
      for (let gy = 0; gy < gridH; gy++) {
        for (let gx = 0; gx < gridW; gx++) {
          const wx = ox + (gx + 0.5) * FP_CELL_FT
          const wy = oy + (gy + 0.5) * FP_CELL_FT
          let inside = 0
          for (const polygon of polygons) {
            if (pointInPolygon(wx, wy, polygon)) { inside = 1; break }
          }
          mask[gy * gridW + gx] = inside
        }
      }
    }
    heatMaskRef.current = mask
    heatKeyRef.current = key
    return true
  }, [])

  const updateFloorplanHeat = useCallback((settings: FloorplanSettings) => {
    if (!ensureFloorplanHeatGrid()) return
    const gridW = gridWRef.current
    const gridH = gridHRef.current
    const heat = heatRef.current
    const mask = heatMaskRef.current
    if (heat.length === 0) return

    const decayRate = Math.max(0.90, 1 - 0.002 / settings.heatGradientRate)
    const decayBlend = 1 - decayRate
    for (let i = 0; i < heat.length; i++) {
      if (!mask[i]) { heat[i] = FP_BASE_HEAT; continue }
      heat[i] += (FP_BASE_HEAT - heat[i]) * decayBlend
    }

    const positioned = propsRef.current.tags.filter(t => t.position)
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        depositHeat(
          positioned[i].position!.x,
          positioned[i].position!.y,
          positioned[j].position!.x,
          positioned[j].position!.y,
          heat,
          mask,
          gridW,
          gridH,
          gridOXRef.current,
          gridOYRef.current,
          settings.heatGradientRate,
          settings.heatRange,
          FP_CELL_FT,
        )
      }
    }

    const heatCanvas = heatCanvasRef.current
    if (!heatCanvas) return
    const ctx = heatCanvas.getContext('2d')
    if (!ctx) return
    const imageData = ctx.createImageData(gridW, gridH)
    const data32 = new Uint32Array(imageData.data.buffer)
    const maxLut = Math.max(1, (settings.heatPeak / 100 * 255) | 0)
    const heatSpan = 1 - FP_BASE_HEAT
    const scale = maxLut / heatSpan
    for (let i = 0; i < heat.length; i++) {
      const idx = Math.min(maxLut, Math.max(0, ((heat[i] - FP_BASE_HEAT) * scale) | 0))
      data32[i] = LUT32[idx]
    }
    ctx.putImageData(imageData, 0, 0)
  }, [ensureFloorplanHeatGrid])

  const drawFrame = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    const viewport = vpRef.current
    const runtime = propsRef.current

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = BG
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    if (runtime.mode === 'floor-plan') {
      for (const room of runtime.rooms) {
        const isActive = room.room_name === runtime.activeRoomName
        const isHovered = room.room_name === runtime.hoverRoomName && !isActive
        const polygon = roomPolygon(room)
        const points = polygon.map(([x, y]) => worldToScreen(viewport, x, y))
        if (points.length >= 3) {
          ctx.fillStyle = isActive ? ROOM_FILL_ACTIVE : isHovered ? ROOM_FILL_HOVER : ROOM_FILL
          ctx.beginPath()
          ctx.moveTo(points[0][0], points[0][1])
          for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1])
          ctx.closePath()
          ctx.fill()
        }
      }

      if (runtime.floorplanSettings?.heatMap && heatCanvasRef.current) {
        const gridW = gridWRef.current
        const gridH = gridHRef.current
        if (gridW > 0 && gridH > 0) {
          ctx.save()
          ctx.beginPath()
          let clipped = false
          for (const room of runtime.rooms) {
            if (room.segments_ft.length < 3) continue
            const polygon = roomPolygon(room)
            if (polygon.length < 3) continue
            const pts = polygon.map(([x, y]) => worldToScreen(viewport, x, y))
            ctx.moveTo(pts[0][0], pts[0][1])
            for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1])
            ctx.closePath()
            clipped = true
          }
          if (clipped) ctx.clip()

          const [screenX, screenY] = worldToScreen(viewport, gridOXRef.current, gridOYRef.current)
          ctx.globalAlpha = 0.78
          ctx.imageSmoothingEnabled = true
          ctx.imageSmoothingQuality = 'high'
          ctx.drawImage(
            heatCanvasRef.current,
            screenX,
            screenY,
            gridW * FP_CELL_FT * viewport.scale,
            gridH * FP_CELL_FT * viewport.scale,
          )
          ctx.globalAlpha = 1
          ctx.restore()
        }
      }

      for (const seg of runtime.floorplanSegments) {
        const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
        const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
        ctx.strokeStyle = (seg as SegmentData & { role?: string }).role === 'non_wall'
          ? FLOORPLAN_NON_WALL
          : FLOORPLAN_SEGMENT
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }

      for (const room of runtime.rooms) {
        const isActive = room.room_name === runtime.activeRoomName
        const isHovered = room.room_name === runtime.hoverRoomName && !isActive
        ctx.strokeStyle = isActive ? ROOM_OUTLINE_ACTIVE : isHovered ? ROOM_OUTLINE_HOVER : ROOM_OUTLINE
        ctx.lineWidth = isActive ? 2.4 : isHovered ? 1.8 : 1.4
        for (const seg of room.segments_ft) {
          const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
          const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
          ctx.beginPath()
          ctx.moveTo(x1, y1)
          ctx.lineTo(x2, y2)
          ctx.stroke()
        }
      }

      if (runtime.floorplanSettings?.showAnchors) {
        for (const room of runtime.rooms) {
          for (const anchor of room.anchors) {
            const wx = room.room_bounds_ft.min_x + anchor.x_ft
            const wy = room.room_bounds_ft.min_y + anchor.y_ft
            const [sx, sy] = worldToScreen(viewport, wx, wy)
            ctx.beginPath()
            ctx.arc(sx, sy, 5, 0, Math.PI * 2)
            ctx.fillStyle = ANCHOR_COLOR_FP
            ctx.fill()
            ctx.strokeStyle = 'rgba(255,255,255,0.3)'
            ctx.lineWidth = 1
            ctx.stroke()

            if (runtime.floorplanSettings.showAnchorLabels) {
              ctx.fillStyle = ANCHOR_LABEL_COLOR
              ctx.font = 'bold 10px "SF Mono", monospace'
              ctx.textAlign = 'left'
              ctx.textBaseline = 'bottom'
              ctx.fillText(
                `${anchor.hw_id || anchor.id} (${anchor.x_ft.toFixed(1)}, ${anchor.y_ft.toFixed(1)})`,
                sx + 8,
                sy - 4,
              )
            }
          }
        }
      }
    } else if (runtime.activeRoom) {
      const room: RoomData = runtime.activeRoom
      const polygon = roomLocalPolygon(room)
      const points = polygon.map(([x, y]) => worldToScreen(viewport, x, y))
      if (points.length >= 3) {
        ctx.fillStyle = ROOM_FILL_ACTIVE
        ctx.beginPath()
        ctx.moveTo(points[0][0], points[0][1])
        for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1])
        ctx.closePath()
        ctx.fill()
      }

      for (const seg of [...room.segments_ft, ...room.interior_segments_ft]) {
        const localSeg = localizeSegment(room, seg)
        const [x1, y1] = worldToScreen(viewport, localSeg.x1, localSeg.y1)
        const [x2, y2] = worldToScreen(viewport, localSeg.x2, localSeg.y2)
        const isBoundary = room.segments_ft.includes(seg)
        ctx.strokeStyle = isBoundary ? ROOM_OUTLINE_ACTIVE : FLOORPLAN_SEGMENT
        ctx.lineWidth = isBoundary ? 1.9 : 1.1
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }

      const anchorIds = Object.keys(runtime.anchors)
      let refX = 0
      let refY = 0
      if (runtime.referenceAnchorId && runtime.anchors[runtime.referenceAnchorId]) {
        [refX, refY] = toRoomLocal(room, runtime.anchors[runtime.referenceAnchorId][0], runtime.anchors[runtime.referenceAnchorId][1])
      }
      for (let i = 0; i < anchorIds.length; i++) {
        const anchorId = anchorIds[i]
        const [ax, ay] = runtime.anchors[anchorId]
        const [localAx, localAy] = toRoomLocal(room, ax, ay)
        const [sx, sy] = worldToScreen(viewport, localAx, localAy)
        const color = anchorColor(i)

        ctx.beginPath()
        ctx.arc(sx, sy, 6, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.25)'
        ctx.lineWidth = 1
        ctx.stroke()

        const labelX = localAx - refX
        const labelY = localAy - refY
        ctx.fillStyle = '#ffffff'
        ctx.font = 'bold 11px "SF Mono", monospace'
        ctx.textAlign = 'left'
        ctx.textBaseline = 'bottom'
        ctx.fillText(
          `${anchorId} (${labelX.toFixed(1)}, ${labelY.toFixed(1)})`,
          sx + 10,
          sy - 4,
        )
      }

      for (const tag of runtime.tags) {
        if (!tag.position) continue
        const [localX, localY] = toRoomLocal(room, tag.position.x, tag.position.y)
        const [sx, sy] = worldToScreen(viewport, localX, localY)
        const radius = 8
        const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, radius * 2.5)
        grad.addColorStop(0, `${tag.color}66`)
        grad.addColorStop(1, 'transparent')
        ctx.beginPath()
        ctx.arc(sx, sy, radius * 2.5, 0, Math.PI * 2)
        ctx.fillStyle = grad
        ctx.fill()

        ctx.beginPath()
        ctx.arc(sx, sy, radius, 0, Math.PI * 2)
        ctx.fillStyle = tag.color
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.4)'
        ctx.lineWidth = 1.5
        ctx.stroke()

        ctx.fillStyle = tag.color
        ctx.font = 'bold 11px sans-serif'
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        ctx.fillText(tag.tag_id, sx + 14, sy)
      }
    }
  }, [])

  useEffect(() => {
    let heatTick = 0
    const loop = () => {
      const runtime = propsRef.current
      if (runtime.mode === 'floor-plan' && runtime.floorplanSettings?.heatMap) {
        heatTick += 1
        if (heatTick % 2 === 0) updateFloorplanHeat(runtime.floorplanSettings)
      }
      drawFrame()
      rafRef.current = window.requestAnimationFrame(loop)
    }
    rafRef.current = window.requestAnimationFrame(loop)
    return () => window.cancelAnimationFrame(rafRef.current)
  }, [drawFrame, updateFloorplanHeat])

  useEffect(() => {
    if (mode === 'floor-plan') {
      heatKeyRef.current = ''
    }
  }, [mode, rooms])

  const updateHover = useCallback((clientX: number, clientY: number) => {
    if (mode !== 'floor-plan' || !onRoomHover) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const [worldX, worldY] = screenToWorld(vpRef.current, clientX - rect.left, clientY - rect.top)
    const hovered = roomAtPoint(rooms, worldX, worldY)
    if (hovered !== hoverRoomRef.current) {
      hoverRoomRef.current = hovered
      onRoomHover(hovered)
    }
  }, [mode, onRoomHover, rooms])

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    dragRef.current = { x: e.clientX, y: e.clientY }
  }

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    updateHover(e.clientX, e.clientY)
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.x
    const dy = e.clientY - dragRef.current.y
    dragRef.current = { x: e.clientX, y: e.clientY }
    vpRef.current.offsetX += dx
    vpRef.current.offsetY += dy
  }

  const onMouseUp = () => { dragRef.current = null }

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (mode !== 'floor-plan' || !onRoomClick) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const [worldX, worldY] = screenToWorld(vpRef.current, e.clientX - rect.left, e.clientY - rect.top)
    const roomName = roomAtPoint(rooms, worldX, worldY)
    if (roomName) onRoomClick(roomName)
  }

  const onDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (mode !== 'floor-plan' || !onRoomDoubleClick) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const [worldX, worldY] = screenToWorld(vpRef.current, e.clientX - rect.left, e.clientY - rect.top)
    const roomName = roomAtPoint(rooms, worldX, worldY)
    if (roomName) onRoomDoubleClick(roomName)
  }

  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault()
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top
    const prev = vpRef.current
    const [worldX, worldY] = screenToWorld(prev, mouseX, mouseY)
    const nextScale = Math.max(2, Math.min(300, prev.scale * (e.deltaY < 0 ? 1.1 : 0.9)))
    vpRef.current = {
      scale: nextScale,
      offsetX: mouseX - worldX * nextScale,
      offsetY: mouseY - worldY * nextScale,
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [onWheel])

  return (
    <canvas
      ref={canvasRef}
      className="rtls-map-canvas"
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={() => {
        dragRef.current = null
        hoverRoomRef.current = null
        onRoomHover?.(null)
      }}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
    />
  )
})

RTLSDashboardCanvas.displayName = 'RTLSDashboardCanvas'

export default RTLSDashboardCanvas
