import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
} from 'react'
import { AnchorData, RoomData, SegmentData } from '../../../types'
import { chainSegmentsToPolygon, pointInPolygon } from '../AnchorManagerModule/anchorGeometry'
import { RTLSTagState } from './RTLSDashboardCanvas'

const API_BASE = 'http://localhost:8765'
const CELL_FT = 0.02
const BASE_HEAT = 0.08
const SPRITE_PX = 52
const TAG_DOT_R = 7
const FRAME_BASE_TIME = 0.35
const STOP_ANIM_SPEED = 0.004
const MIN_SPEED_FACING = 0.003
const DIR_HISTORY = 8
const DIR_SMOOTH = 0.18
const ANIM_REF_SPEED = 0.1

const COLORS = {
  bg: '#0a0b0d',
  segment: '#314052',
  roomBoundary: '#4a9eff',
  roomFill: 'rgba(74, 158, 255, 0.08)',
  anchor: '#ff9b38',
  anchorRef: '#ffd166',
  anchorLabel: '#ffffff',
}

export type TagAppearance = 'invisible' | 'dots' | 'human'

export interface RTLSVisualSettings {
  heatMap: boolean
  heatGradientRate: number
  heatRange: number
  heatPeak: number
  tagAppearance: TagAppearance
  showInterTagLines: boolean
  showAnchors: boolean
  showAnchorLabels: boolean
}

export interface RTLSRoomViewHandle {
  resetView: () => void
  zoomIn: () => void
  zoomOut: () => void
}

interface Props {
  room: RoomData
  tags: RTLSTagState[]
  activeSolveRoomName: string | null
  referenceAnchorId?: string
  visualSettings: RTLSVisualSettings
}

interface Viewport {
  offsetX: number
  offsetY: number
  scale: number
}

interface LocalTag extends RTLSTagState {
  localX: number
  localY: number
}

interface RuntimeProps {
  room: RoomData
  localBoundary: SegmentData[]
  localInterior: SegmentData[]
  localPolygon: [number, number][]
  localTags: LocalTag[]
  activeReferenceAnchor: AnchorData | null
  activeSolveRoomName: string | null
  visualSettings: RTLSVisualSettings
}

interface TagRenderState {
  tagId: string
  color: string
  x: number
  y: number
  sampleX: number
  sampleY: number
  speed: number
  angle: number
  targetAngle: number
  isWalking: boolean
  walkPhase: 0 | 1
  animElapsed: number
  lastSampleTs: number
  lastMoveTs: number
  directionSamples: [number, number][]
}

const worldToScreen = (vp: Viewport, wx: number, wy: number): [number, number] => (
  [wx * vp.scale + vp.offsetX, wy * vp.scale + vp.offsetY]
)

const screenToWorld = (vp: Viewport, sx: number, sy: number): [number, number] => (
  [(sx - vp.offsetX) / vp.scale, (sy - vp.offsetY) / vp.scale]
)

const toLocalPoint = (room: RoomData, x: number, y: number): [number, number] => ([
  x - room.room_bounds_ft.min_x,
  y - room.room_bounds_ft.min_y,
])

const toLocalSegment = (room: RoomData, segment: SegmentData): SegmentData => {
  const [x1, y1] = toLocalPoint(room, segment.x1, segment.y1)
  const [x2, y2] = toLocalPoint(room, segment.x2, segment.y2)
  return { x1, y1, x2, y2 }
}

const polygonPoints = (segments: SegmentData[]): [number, number][] => chainSegmentsToPolygon(segments)

function wrapAngle(angle: number): number {
  let next = angle
  while (next <= -Math.PI) next += Math.PI * 2
  while (next > Math.PI) next -= Math.PI * 2
  return next
}

function smoothAngle(current: number, target: number, factor: number): number {
  return current + wrapAngle(target - current) * factor
}

function meanAngle(vectors: [number, number][]): number | null {
  if (vectors.length === 0) return null
  let sumX = 0
  let sumY = 0
  for (const [dx, dy] of vectors) {
    sumX += dx
    sumY += dy
  }
  if (Math.abs(sumX) < 1e-9 && Math.abs(sumY) < 1e-9) return null
  return Math.atan2(sumY, sumX)
}

function animFrameTime(speed: number): number | null {
  if (speed <= STOP_ANIM_SPEED) return null
  const ratio = speed / ANIM_REF_SPEED
  if (ratio < 0.15) return FRAME_BASE_TIME
  if (ratio < 0.30) return FRAME_BASE_TIME * 0.85
  if (ratio < 0.50) return FRAME_BASE_TIME * 0.70
  if (ratio < 0.70) return FRAME_BASE_TIME * 0.55
  if (ratio < 0.85) return FRAME_BASE_TIME * 0.45
  return FRAME_BASE_TIME * 0.35
}

function buildLUT(): Uint8Array {
  const lut = new Uint8Array(256 * 3)
  // Smooth gradient from deep blue → light blue → cyan → green → yellow → orange → red → dark red.
  // More stops = smoother transitions between regions.
  const stops: [number, number, number, number][] = [
    [0.00,   0,   0, 120],  // deep blue (low)
    [0.05,   0,  30, 180],
    [0.10,   0,  70, 230],
    [0.16,   0, 120, 255],  // blue
    [0.22,   0, 170, 255],  // light blue
    [0.28,   0, 210, 245],
    [0.34,   0, 230, 200],  // cyan-teal
    [0.40,   0, 245, 160],
    [0.46,   0, 255, 110],  // green
    [0.52,  80, 255,  60],
    [0.58, 160, 255,  20],  // yellow-green
    [0.64, 220, 255,   0],
    [0.70, 255, 230,   0],  // yellow
    [0.76, 255, 195,   0],
    [0.82, 255, 150,   0],  // orange
    [0.88, 255,  95,   0],
    [0.93, 235,  45,   5],  // red
    [0.97, 190,  15,   0],
    [1.00, 120,   0,   0],  // dark red (high)
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

  const x1g = (p1x - gridOX) / CELL_FT
  const y1g = (p1y - gridOY) / CELL_FT
  const x2g = (p2x - gridOX) / CELL_FT
  const y2g = (p2y - gridOY) / CELL_FT

  const iterR = Math.min(60, Math.max(3, fieldRad / CELL_FT))
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

const RTLSRoomView = forwardRef<RTLSRoomViewHandle, Props>(({
  room,
  tags,
  activeSolveRoomName,
  referenceAnchorId,
  visualSettings,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const viewportRef = useRef<Viewport>({ offsetX: 0, offsetY: 0, scale: 20 })
  const dragRef = useRef<{ x: number; y: number } | null>(null)
  const tagStatesRef = useRef<Map<string, TagRenderState>>(new Map())
  const heatRef = useRef<Float32Array>(new Float32Array(0))
  const gridWRef = useRef(0)
  const gridHRef = useRef(0)
  const gridOXRef = useRef(0)
  const gridOYRef = useRef(0)
  const heatCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const heatMaskRef = useRef<Uint8Array>(new Uint8Array(0))
  const rafRef = useRef(0)
  const propsRef = useRef<RuntimeProps>({
    room,
    localBoundary: [],
    localInterior: [],
    localPolygon: [],
    localTags: [],
    activeReferenceAnchor: null,
    activeSolveRoomName,
    visualSettings,
  })
  const spritesRef = useRef<{
    stand: HTMLImageElement | null
    left: HTMLImageElement | null
    right: HTMLImageElement | null
  }>({ stand: null, left: null, right: null })

  const localBoundary = room.segments_ft.map(segment => toLocalSegment(room, segment))
  const localInterior = room.interior_segments_ft.map(segment => toLocalSegment(room, segment))
  const localPolygon = polygonPoints(localBoundary)
  const activeReferenceAnchor = room.anchors.find(anchor => (
    anchor.id === (room.reference_anchor_id ?? null)
    || (!!referenceAnchorId && (anchor.hw_id === referenceAnchorId || anchor.id === referenceAnchorId))
  )) ?? null
  const localTags = tags
    .filter(tag => tag.position)
    .map(tag => {
      const [x, y] = toLocalPoint(room, tag.position!.x, tag.position!.y)
      return { ...tag, localX: x, localY: y }
    })
    .filter(tag => (
      tag.localX >= -0.25
      && tag.localX <= room.room_bounds_ft.width + 0.25
      && tag.localY >= -0.25
      && tag.localY <= room.room_bounds_ft.height + 0.25
    ))

  propsRef.current = {
    room,
    localBoundary,
    localInterior,
    localPolygon,
    localTags,
    activeReferenceAnchor,
    activeSolveRoomName,
    visualSettings,
  }

  const resetView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const width = Math.max(room.room_bounds_ft.width, 1)
    const height = Math.max(room.room_bounds_ft.height, 1)
    const padding = 70
    const scale = Math.min(
      (canvas.width - padding * 2) / width,
      (canvas.height - padding * 2) / height,
    )
    viewportRef.current = {
      scale: Math.max(2, scale),
      offsetX: (canvas.width - width * Math.max(2, scale)) / 2,
      offsetY: (canvas.height - height * Math.max(2, scale)) / 2,
    }
  }, [room.room_bounds_ft.height, room.room_bounds_ft.width])

  const initHeatGrid = useCallback(() => {
    const { room: currentRoom, localPolygon: polygon } = propsRef.current
    const margin = 1.0
    const ox = -margin
    const oy = -margin
    const widthFt = currentRoom.room_bounds_ft.width
    const heightFt = currentRoom.room_bounds_ft.height
    const gridW = Math.max(4, Math.ceil((widthFt + margin * 2) / CELL_FT))
    const gridH = Math.max(4, Math.ceil((heightFt + margin * 2) / CELL_FT))

    gridOXRef.current = ox
    gridOYRef.current = oy
    gridWRef.current = gridW
    gridHRef.current = gridH
    heatRef.current = new Float32Array(gridW * gridH).fill(BASE_HEAT)

    const heatCanvas = document.createElement('canvas')
    heatCanvas.width = gridW
    heatCanvas.height = gridH
    heatCanvasRef.current = heatCanvas

    const mask = new Uint8Array(gridW * gridH)
    if (polygon.length >= 3) {
      for (let gy = 0; gy < gridH; gy++) {
        for (let gx = 0; gx < gridW; gx++) {
          const wx = ox + (gx + 0.5) * CELL_FT
          const wy = oy + (gy + 0.5) * CELL_FT
          mask[gy * gridW + gx] = pointInPolygon(wx, wy, polygon) ? 1 : 0
        }
      }
    } else {
      mask.fill(1)
    }
    heatMaskRef.current = mask
  }, [])

  const renderHeatToOffscreen = useCallback((heatPeak: number) => {
    const heatCanvas = heatCanvasRef.current
    const gridW = gridWRef.current
    const gridH = gridHRef.current
    if (!heatCanvas || gridW === 0 || gridH === 0) return
    const ctx = heatCanvas.getContext('2d')
    if (!ctx) return

    const imageData = ctx.createImageData(gridW, gridH)
    const data32 = new Uint32Array(imageData.data.buffer)
    const heat = heatRef.current
    const maxLut = Math.max(1, (heatPeak / 100 * 255) | 0)
    const heatSpan = 1 - BASE_HEAT
    const scale = maxLut / heatSpan

    for (let gy = 0; gy < gridH; gy++) {
      const srcOffset = gy * gridW
      const dstOffset = gy * gridW
      for (let gx = 0; gx < gridW; gx++) {
        const idx = Math.min(maxLut, Math.max(0, ((heat[srcOffset + gx] - BASE_HEAT) * scale) | 0))
        data32[dstOffset + gx] = LUT32[idx]
      }
    }

    ctx.putImageData(imageData, 0, 0)
  }, [])

  const syncTagStates = useCallback((timeMs: number, dt: number) => {
    const map = tagStatesRef.current
    const present = new Set<string>()

    for (const tag of propsRef.current.localTags) {
      present.add(tag.tag_id)
      let state = map.get(tag.tag_id)
      if (!state) {
        state = {
          tagId: tag.tag_id,
          color: tag.color,
          x: tag.localX,
          y: tag.localY,
          sampleX: tag.localX,
          sampleY: tag.localY,
          speed: 0,
          angle: 0,
          targetAngle: 0,
          isWalking: false,
          walkPhase: 0,
          animElapsed: 0,
          lastSampleTs: timeMs,
          lastMoveTs: timeMs,
          directionSamples: [],
        }
        map.set(tag.tag_id, state)
      }

      state.color = tag.color
      state.x = tag.localX
      state.y = tag.localY

      const dx = tag.localX - state.sampleX
      const dy = tag.localY - state.sampleY
      const dist = Math.hypot(dx, dy)

      if (dist > 1e-3) {
        const sampleDt = Math.max(1 / 60, (timeMs - state.lastSampleTs) / 1000)
        state.speed = dist / (sampleDt * 60)
        state.sampleX = tag.localX
        state.sampleY = tag.localY
        state.lastSampleTs = timeMs
        state.lastMoveTs = timeMs

        if (state.speed > MIN_SPEED_FACING) {
          state.directionSamples.push([dx, dy])
          if (state.directionSamples.length > DIR_HISTORY) state.directionSamples.shift()
          const avgAngle = meanAngle(state.directionSamples)
          if (avgAngle !== null) state.targetAngle = avgAngle
        }
      } else if ((timeMs - state.lastMoveTs) > 140) {
        state.speed = 0
      }

      if (state.speed > MIN_SPEED_FACING) {
        state.angle = smoothAngle(state.angle, state.targetAngle, DIR_SMOOTH)
      }

      const frameTime = animFrameTime(state.speed)
      if (frameTime === null) {
        if (state.animElapsed > 0) {
          state.animElapsed += dt
          const stopFrame = animFrameTime(STOP_ANIM_SPEED + 0.001) ?? FRAME_BASE_TIME
          if (state.animElapsed >= stopFrame) {
            state.isWalking = false
            state.walkPhase = 0
            state.animElapsed = 0
          }
        } else {
          state.isWalking = false
          state.walkPhase = 0
        }
      } else {
        state.isWalking = true
        state.animElapsed += dt
        while (state.animElapsed >= frameTime) {
          state.animElapsed -= frameTime
          state.walkPhase = state.walkPhase === 0 ? 1 : 0
        }
      }
    }

    for (const tagId of map.keys()) {
      if (!present.has(tagId)) map.delete(tagId)
    }
  }, [])

  const updateHeatLayer = useCallback((vs: RTLSVisualSettings) => {
    const gridW = gridWRef.current
    const gridH = gridHRef.current
    if (gridW === 0 || gridH === 0) return

    const heat = heatRef.current
    const mask = heatMaskRef.current
    const decayRate = Math.max(0.90, 1 - 0.002 / vs.heatGradientRate)
    const decayBlend = 1 - decayRate

    for (let i = 0; i < heat.length; i++) {
      if (!mask[i]) {
        heat[i] = BASE_HEAT
        continue
      }
      heat[i] += (BASE_HEAT - heat[i]) * decayBlend
    }

    const entities = propsRef.current.localTags
    for (let i = 0; i < entities.length; i++) {
      for (let j = i + 1; j < entities.length; j++) {
        depositHeat(
          entities[i].localX,
          entities[i].localY,
          entities[j].localX,
          entities[j].localY,
          heat,
          mask,
          gridW,
          gridH,
          gridOXRef.current,
          gridOYRef.current,
          vs.heatGradientRate,
          vs.heatRange,
        )
      }
    }

    renderHeatToOffscreen(vs.heatPeak)
  }, [renderHeatToOffscreen])

  const drawFrame = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return

    const viewport = viewportRef.current
    const runtime = propsRef.current
    const { localBoundary: boundary, localInterior: interior, localPolygon: polygon, activeReferenceAnchor: referenceAnchor, activeSolveRoomName: solveRoomName, visualSettings: vs } = runtime

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = COLORS.bg
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    if (polygon.length >= 3) {
      ctx.fillStyle = COLORS.roomFill
      ctx.beginPath()
      const [x0, y0] = worldToScreen(viewport, polygon[0][0], polygon[0][1])
      ctx.moveTo(x0, y0)
      for (let i = 1; i < polygon.length; i++) {
        const [x, y] = worldToScreen(viewport, polygon[i][0], polygon[i][1])
        ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.fill()
    }

    if (vs.heatMap && heatCanvasRef.current) {
      const gridW = gridWRef.current
      const gridH = gridHRef.current
      if (gridW > 0 && gridH > 0) {
        if (polygon.length >= 3) {
          ctx.save()
          ctx.beginPath()
          const [x0, y0] = worldToScreen(viewport, polygon[0][0], polygon[0][1])
          ctx.moveTo(x0, y0)
          for (let i = 1; i < polygon.length; i++) {
            const [x, y] = worldToScreen(viewport, polygon[i][0], polygon[i][1])
            ctx.lineTo(x, y)
          }
          ctx.closePath()
          ctx.clip()
        }

        const [screenX, screenY] = worldToScreen(viewport, gridOXRef.current, gridOYRef.current)
        ctx.globalAlpha = 0.78
        ctx.imageSmoothingEnabled = true
        ctx.imageSmoothingQuality = 'high'
        ctx.drawImage(
          heatCanvasRef.current,
          screenX,
          screenY,
          gridW * CELL_FT * viewport.scale,
          gridH * CELL_FT * viewport.scale,
        )
        ctx.globalAlpha = 1
        if (polygon.length >= 3) ctx.restore()
      }
    }

    for (const segment of interior) {
      const [x1, y1] = worldToScreen(viewport, segment.x1, segment.y1)
      const [x2, y2] = worldToScreen(viewport, segment.x2, segment.y2)
      ctx.strokeStyle = COLORS.segment
      ctx.lineWidth = 1.1
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    for (const segment of boundary) {
      const [x1, y1] = worldToScreen(viewport, segment.x1, segment.y1)
      const [x2, y2] = worldToScreen(viewport, segment.x2, segment.y2)
      ctx.strokeStyle = COLORS.roomBoundary
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    const refLocalX = referenceAnchor?.x_ft ?? 0
    const refLocalY = referenceAnchor?.y_ft ?? 0

    if (vs.showAnchors) {
      for (const anchor of room.anchors) {
        const [sx, sy] = worldToScreen(viewport, anchor.x_ft, anchor.y_ft)
        const radius = 6

        ctx.beginPath()
        ctx.arc(sx, sy, radius, 0, Math.PI * 2)
        ctx.fillStyle = COLORS.anchor
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.3)'
        ctx.lineWidth = 1
        ctx.stroke()

        if (vs.showAnchorLabels) {
          ctx.fillStyle = COLORS.anchorLabel
          ctx.font = 'bold 11px "SF Mono", monospace'
          ctx.textAlign = 'left'
          ctx.textBaseline = 'bottom'
          const label = `${anchor.hw_id || anchor.id} (${(anchor.x_ft - refLocalX).toFixed(1)}, ${(anchor.y_ft - refLocalY).toFixed(1)})`
          ctx.fillText(label, sx + 10, sy - 4)
        }
      }
    }

    if (polygon.length >= 3) {
      ctx.save()
      ctx.beginPath()
      const [x0, y0] = worldToScreen(viewport, polygon[0][0], polygon[0][1])
      ctx.moveTo(x0, y0)
      for (let i = 1; i < polygon.length; i++) {
        const [x, y] = worldToScreen(viewport, polygon[i][0], polygon[i][1])
        ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.clip()
    }

    if (vs.showInterTagLines) {
      const states = Array.from(tagStatesRef.current.values())
      if (states.length >= 2) {
        const LINE_COLOR = 'rgba(255, 185, 0, 0.9)'
        ctx.strokeStyle = LINE_COLOR
        ctx.lineWidth = 1.5
        ctx.setLineDash([5, 4])
        for (let i = 0; i < states.length; i++) {
          for (let j = i + 1; j < states.length; j++) {
            const s1 = states[i]
            const s2 = states[j]
            const [sx1, sy1] = worldToScreen(viewport, s1.x, s1.y)
            const [sx2, sy2] = worldToScreen(viewport, s2.x, s2.y)

            ctx.beginPath()
            ctx.moveTo(sx1, sy1)
            ctx.lineTo(sx2, sy2)
            ctx.stroke()

            const dist = Math.hypot(s2.x - s1.x, s2.y - s1.y)
            const midSx = (sx1 + sx2) / 2
            const midSy = (sy1 + sy2) / 2

            ctx.setLineDash([])
            ctx.fillStyle = LINE_COLOR
            ctx.font = 'bold 10px "SF Mono", monospace'
            ctx.textAlign = 'center'
            ctx.textBaseline = 'bottom'
            ctx.fillText(`${dist.toFixed(2)} ft`, midSx, midSy - 5)
            ctx.setLineDash([5, 4])
          }
        }
        ctx.setLineDash([])
      }
    }

    for (const state of tagStatesRef.current.values()) {
      const [sx, sy] = worldToScreen(viewport, state.x, state.y)
      const isHuman = vs.tagAppearance === 'human'

      if (isHuman) {
        const frameName = state.isWalking ? (state.walkPhase === 0 ? 'left' : 'right') : 'stand'
        const sprite = spritesRef.current[frameName]
        if (sprite) {
          const half = SPRITE_PX / 2
          ctx.save()
          ctx.translate(sx, sy)
          ctx.rotate(-state.angle)
          ctx.drawImage(sprite, -half, -half, SPRITE_PX, SPRITE_PX)
          ctx.restore()
        } else {
          ctx.beginPath()
          ctx.arc(sx, sy, TAG_DOT_R, 0, Math.PI * 2)
          ctx.fillStyle = state.color
          ctx.fill()
          ctx.strokeStyle = 'rgba(255,255,255,0.35)'
          ctx.lineWidth = 1
          ctx.stroke()
        }
      } else if (vs.tagAppearance === 'dots') {
        const glow = ctx.createRadialGradient(sx, sy, 0, sx, sy, TAG_DOT_R * 2.5)
        glow.addColorStop(0, `${state.color}66`)
        glow.addColorStop(1, 'transparent')
        ctx.beginPath()
        ctx.arc(sx, sy, TAG_DOT_R * 2.5, 0, Math.PI * 2)
        ctx.fillStyle = glow
        ctx.fill()

        ctx.beginPath()
        ctx.arc(sx, sy, TAG_DOT_R, 0, Math.PI * 2)
        ctx.fillStyle = state.color
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.4)'
        ctx.lineWidth = 1.5
        ctx.stroke()
      }

      if (vs.tagAppearance !== 'invisible') {
        ctx.fillStyle = isHuman ? '#ffffff' : state.color
        ctx.font = 'bold 11px sans-serif'
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        const labelOffset = isHuman ? SPRITE_PX / 2 + 4 : TAG_DOT_R + 7
        ctx.fillText(state.tagId, sx + labelOffset, sy)
      }
    }

    if (polygon.length >= 3) ctx.restore()

    if (tagStatesRef.current.size === 0) {
      ctx.fillStyle = 'rgba(180, 194, 214, 0.7)'
      ctx.font = '12px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(
        solveRoomName === room.room_name
          ? 'Waiting for live RTLS positions...'
          : `Room tab open. Active solve room is ${solveRoomName || 'not selected'}.`,
        canvas.width / 2,
        24,
      )
    }
  }, [room.anchors, room.room_name])

  const zoomBy = useCallback((factor: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pivotX = canvas.width / 2
    const pivotY = canvas.height / 2
    const current = viewportRef.current
    const nextScale = Math.max(2, Math.min(320, current.scale * factor))
    viewportRef.current = {
      scale: nextScale,
      offsetX: pivotX - (pivotX - current.offsetX) * (nextScale / current.scale),
      offsetY: pivotY - (pivotY - current.offsetY) * (nextScale / current.scale),
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
    tagStatesRef.current.clear()
    initHeatGrid()
    resetView()
  }, [initHeatGrid, resetView, room.room_bounds_ft.height, room.room_bounds_ft.width, room.room_name, room.segments_ft.length])

  useEffect(() => {
    const entries: [keyof typeof spritesRef.current, string][] = [
      ['stand', `${API_BASE}/assets/walk/Untitled%20Design%20(1).png`],
      ['left', `${API_BASE}/assets/walk/Untitled%20Design%20(2).png`],
      ['right', `${API_BASE}/assets/walk/Untitled%20Design%20(3).png`],
    ]
    const blobUrls: string[] = []
    entries.forEach(([name, url]) => {
      fetch(url)
        .then(response => {
          if (!response.ok) throw new Error(String(response.status))
          return response.blob()
        })
        .then(blob => {
          const blobUrl = URL.createObjectURL(blob)
          blobUrls.push(blobUrl)
          const image = new Image()
          image.onload = () => { spritesRef.current[name] = image }
          image.src = blobUrl
        })
        .catch(() => {
          spritesRef.current[name] = null
        })
    })
    return () => {
      blobUrls.forEach(url => URL.revokeObjectURL(url))
    }
  }, [])

  useEffect(() => {
    let lastTime = 0
    let heatTick = 0

    const loop = (time: number) => {
      const dt = lastTime === 0 ? 0 : Math.min(0.1, (time - lastTime) / 1000)
      lastTime = time

      syncTagStates(time, dt)

      if (propsRef.current.visualSettings.heatMap) {
        heatTick += 1
        if (heatTick % 2 === 0) updateHeatLayer(propsRef.current.visualSettings)
      }

      drawFrame()
      rafRef.current = window.requestAnimationFrame(loop)
    }

    rafRef.current = window.requestAnimationFrame(loop)
    return () => window.cancelAnimationFrame(rafRef.current)
  }, [drawFrame, syncTagStates, updateHeatLayer])

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    dragRef.current = { x: e.clientX, y: e.clientY }
  }

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.x
    const dy = e.clientY - dragRef.current.y
    dragRef.current = { x: e.clientX, y: e.clientY }
    viewportRef.current.offsetX += dx
    viewportRef.current.offsetY += dy
  }

  const onMouseUp = () => {
    dragRef.current = null
  }

  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault()
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top
    const current = viewportRef.current
    const [worldX, worldY] = screenToWorld(current, mouseX, mouseY)
    const nextScale = Math.max(2, Math.min(320, current.scale * (e.deltaY < 0 ? 1.1 : 0.9)))
    viewportRef.current = {
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
    <div className="rtls-room-view">
      <canvas
        ref={canvasRef}
        className="rtls-room-view__canvas"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      />
    </div>
  )
})

RTLSRoomView.displayName = 'RTLSRoomView'

export default RTLSRoomView
