import React, {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

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

export type BotAppearance = 'invisible' | 'dots' | 'human'

export interface VisualSettings {
  heatMap: boolean
  heatGradientRate: number   // seconds per gradient step (0.05–5.0)
  heatRange: number          // proximity detection distance in ft (0.5–16)
  heatPeak: number           // max LUT colour 1–100
  botAppearance: BotAppearance
  bots: boolean
  botSpeed: number           // ft/s (0.5–8)
  botAccel: number           // ft/s² (0.1–5)
  botPause: number           // pause duration in seconds (0.2–3.0)
}

/** Opaque handle — minimal public type; full physics lives inside the canvas. */
export interface SimBot { id: number }

export interface VisualEntity { id: string; x: number; y: number }

interface RTLSDashboardCanvasProps {
  segments: { x1: number; y1: number; x2: number; y2: number }[]
  anchors: Record<string, [number, number]>
  tags: RTLSTagState[]
  roomBounds: { min_x?: number; min_y?: number; max_x?: number; max_y?: number }
  roomPolygon?: { x: number; y: number }[]
  svgContent?: string | null
  referenceAnchorId?: string
  visualSettings: VisualSettings
  onViewportChange?: (vp: RTLSViewport) => void
}

export interface RTLSDashboardCanvasHandle {
  resetView: () => void
  zoomIn: () => void
  zoomOut: () => void
  seedBots: (n: number) => void
  addBot: () => number
  getBotCount: () => number
}

// ─────────────────────────────────────────────────────────────────────────────
// Colour helpers
// ─────────────────────────────────────────────────────────────────────────────

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

// ─────────────────────────────────────────────────────────────────────────────
// Simulation constants (world-space ft / 60 fps frame)
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = 'http://localhost:8765'

// Heat grid
const CELL_FT = 0.02          // world-space grid cell size in feet (finer = higher res)
const BASE_HEAT = 0.08
// DECAY_RATE is now dynamic — computed per-frame from vs.heatIntensity

// Bot rendering
const SPRITE_PX = 52          // fixed on-screen sprite diameter (px)
const BOT_DOT_R = 7           // fixed on-screen dot radius
const MAX_BOTS = 24

// Bot motion
const MIN_MOVE_DIST = 4.0     // ft — min leg distance before pausing
const MAX_MOVE_DIST = 16.0    // ft
const FRAME_BASE_TIME = 0.35  // seconds per walking animation frame (at slow speed)
const STOP_ANIM_SPEED = 0.004 // ft/frame — below this, play stop animation
const MIN_SPEED_FACING = 0.003
const DIR_HISTORY = 8
const DIR_SMOOTH = 0.18
const ANIM_REF_SPEED = 0.10   // ft/frame reference for animation rate (≈ 6 ft/s)

// ─────────────────────────────────────────────────────────────────────────────
// Internal bot state (full physics, never exposed outside canvas)
// ─────────────────────────────────────────────────────────────────────────────

interface BotState {
  id: number
  x: number; y: number          // world ft
  speed: number                 // current speed, ft/frame (nominal 60 fps)
  targetAngle: number
  targetDistance: number
  distanceTraveled: number
  speedFactor: number           // per-bot variation 0.7–1.3 applied to vs.botSpeed
  accelFactor: number           // per-bot variation 0.7–1.3 applied to vs.botAccel
  pauseTicks: number            // frames remaining in current pause
  angle: number                 // facing angle (radians)
  isWalking: boolean
  walkPhase: number             // 0 or 1
  animElapsed: number
  directionSamples: [number, number][]
}

// ─────────────────────────────────────────────────────────────────────────────
// Pure simulation helpers (defined outside component — stable references)
// ─────────────────────────────────────────────────────────────────────────────

function wrapAngle(a: number): number {
  while (a <= -Math.PI) a += 2 * Math.PI
  while (a > Math.PI) a -= 2 * Math.PI
  return a
}

function smoothAngle(cur: number, target: number, t: number): number {
  return cur + wrapAngle(target - cur) * t
}

function meanAngle(vecs: [number, number][]): number | null {
  if (!vecs.length) return null
  let sx = 0, sy = 0
  for (const [dx, dy] of vecs) { sx += dx; sy += dy }
  if (Math.abs(sx) < 1e-9 && Math.abs(sy) < 1e-9) return null
  return Math.atan2(sy, sx)
}

function animFrameTime(speed: number): number | null {
  if (speed <= STOP_ANIM_SPEED) return null
  const ratio = speed / ANIM_REF_SPEED   // normalise against 6 ft/s reference
  if (ratio < 0.15) return FRAME_BASE_TIME
  if (ratio < 0.30) return FRAME_BASE_TIME * 0.85
  if (ratio < 0.50) return FRAME_BASE_TIME * 0.70
  if (ratio < 0.70) return FRAME_BASE_TIME * 0.55
  if (ratio < 0.85) return FRAME_BASE_TIME * 0.45
  return FRAME_BASE_TIME * 0.35
}

function pointInPolygon(x: number, y: number, poly: { x: number; y: number }[]): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y
    const xj = poly[j].x, yj = poly[j].y
    if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) {
      inside = !inside
    }
  }
  return inside
}

function reflectAngleAgainstPolygon(
  x: number, y: number,
  angle: number,
  poly: { x: number; y: number }[],
): number {
  let bestDist = Infinity
  let bestNx = 0, bestNy = 1
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length]
    const edx = b.x - a.x, edy = b.y - a.y
    const len = Math.hypot(edx, edy)
    if (len < 1e-9) continue
    const t = Math.max(0, Math.min(1, ((x - a.x) * edx + (y - a.y) * edy) / (len * len)))
    const cx = a.x + t * edx, cy = a.y + t * edy
    const dist = Math.hypot(cx - x, cy - y)
    if (dist < bestDist) {
      bestDist = dist
      // Outward normal (right-hand rule for CCW polygon)
      bestNx = -edy / len; bestNy = edx / len
    }
  }
  const vx = Math.cos(angle), vy = Math.sin(angle)
  const dot = vx * bestNx + vy * bestNy
  return Math.atan2(vy - 2 * dot * bestNy, vx - 2 * dot * bestNx)
}

function randomPointInPolygon(
  poly: { x: number; y: number }[],
  b: { minX: number; minY: number; maxX: number; maxY: number },
): { x: number; y: number } {
  const margin = 0.5
  for (let attempt = 0; attempt < 300; attempt++) {
    const x = b.minX + margin + Math.random() * (b.maxX - b.minX - 2 * margin)
    const y = b.minY + margin + Math.random() * (b.maxY - b.minY - 2 * margin)
    if (pointInPolygon(x, y, poly)) return { x, y }
  }
  return { x: (b.minX + b.maxX) / 2, y: (b.minY + b.maxY) / 2 }
}

function stepBot(
  bot: BotState,
  poly: { x: number; y: number }[],
  dt: number,             // seconds
  botSpeedFtS: number,    // vs.botSpeed  ft/s
  botAccelFtS2: number,   // vs.botAccel  ft/s²
  pauseDuration: number,  // vs.botPause  seconds
): void {
  const dtF = dt * 60   // normalise to 60-fps frames
  // Convert ft/s → ft/frame (nominal 60 fps) with per-bot variation
  const effTop   = botSpeedFtS   * bot.speedFactor / 60
  const effAccel = botAccelFtS2  * bot.accelFactor / 60

  if (bot.pauseTicks > 0) {
    bot.pauseTicks--
    bot.speed = Math.max(0, bot.speed - effAccel * 1.4 * dtF)
  } else {
    const remaining = bot.targetDistance - bot.distanceTraveled
    const brake = (bot.speed * bot.speed) / (2 * Math.max(effAccel, 1e-6))
    if (remaining <= brake) {
      bot.speed = Math.max(0, bot.speed - effAccel * dtF)
    } else {
      bot.speed = Math.min(effTop, bot.speed + effAccel * dtF)
    }
  }

  const vx = Math.cos(bot.targetAngle) * bot.speed * dtF
  const vy = Math.sin(bot.targetAngle) * bot.speed * dtF
  let nx = bot.x + vx, ny = bot.y + vy

  if (poly.length >= 3 && !pointInPolygon(nx, ny, poly)) {
    bot.targetAngle = reflectAngleAgainstPolygon(bot.x, bot.y, bot.targetAngle, poly)
    const rvx = Math.cos(bot.targetAngle) * bot.speed * dtF
    const rvy = Math.sin(bot.targetAngle) * bot.speed * dtF
    nx = bot.x + rvx; ny = bot.y + rvy
    if (!pointInPolygon(nx, ny, poly)) { nx = bot.x; ny = bot.y; bot.speed = 0 }
  }

  bot.distanceTraveled += Math.hypot(nx - bot.x, ny - bot.y)
  bot.x = nx; bot.y = ny

  const instSpeed = Math.hypot(vx, vy)
  if (instSpeed > MIN_SPEED_FACING) {
    bot.directionSamples.push([vx, vy])
    if (bot.directionSamples.length > DIR_HISTORY) bot.directionSamples.shift()
    const m = meanAngle(bot.directionSamples)
    if (m !== null) bot.angle = smoothAngle(bot.angle, m, DIR_SMOOTH)
  }

  if (bot.pauseTicks === 0 && bot.speed <= 0.001 && bot.distanceTraveled >= bot.targetDistance) {
    bot.targetAngle = Math.random() * Math.PI * 2
    bot.targetDistance = MIN_MOVE_DIST + Math.random() * (MAX_MOVE_DIST - MIN_MOVE_DIST)
    bot.distanceTraveled = 0
    // Pause length: pauseDuration ±40 % natural variation
    bot.pauseTicks = Math.round(pauseDuration * 60 * (0.6 + Math.random() * 0.8))
  }

  // Walking animation frames
  const ft = animFrameTime(bot.speed)
  if (ft === null) {
    if (bot.animElapsed > 0) {
      bot.animElapsed += dt
      if (bot.animElapsed >= (animFrameTime(STOP_ANIM_SPEED + 0.001) ?? FRAME_BASE_TIME)) {
        bot.isWalking = false; bot.walkPhase = 0; bot.animElapsed = 0
      }
    } else { bot.isWalking = false; bot.walkPhase = 0 }
  } else {
    bot.isWalking = true
    bot.animElapsed += dt
    while (bot.animElapsed >= ft) { bot.animElapsed -= ft; bot.walkPhase = 1 - bot.walkPhase }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Heat deposit — optimised: quadratic falloff (no exp/sqrt in inner loop),
// squared distances throughout, capped iteration radius, mask early-exit
// ─────────────────────────────────────────────────────────────────────────────

function depositHeat(
  p1x: number, p1y: number,
  p2x: number, p2y: number,
  heat: Float32Array,
  heatMask: Uint8Array,
  gridW: number, gridH: number,
  gridOX: number, gridOY: number,
  gradientRate: number,    // seconds per gradient step (vs.heatGradientRate)
  rangeFt: number,         // proximity distance in ft (vs.heatRange)
): void {
  const maxDist     = rangeFt
  const fieldRad    = rangeFt * 0.28
  const depositBase = 0.005 / gradientRate

  const pdx = p2x - p1x, pdy = p2y - p1y
  const dist2 = pdx * pdx + pdy * pdy
  if (dist2 >= maxDist * maxDist) return

  const dist      = Math.sqrt(dist2)          // one sqrt, outside inner loop
  const closeness = 1 - dist / maxDist        // > 0 guaranteed
  const strength  = depositBase * Math.pow(closeness, 2.2)
  if (strength <= 0) return

  const x1g = (p1x - gridOX) / CELL_FT, y1g = (p1y - gridOY) / CELL_FT
  const x2g = (p2x - gridOX) / CELL_FT, y2g = (p2y - gridOY) / CELL_FT

  // Cap iteration radius in cells regardless of CELL_FT / sensitivity
  const iterR  = Math.min(60, Math.max(3, fieldRad / CELL_FT))
  const iterR2 = iterR * iterR

  const pad  = Math.ceil(iterR) + 1
  const minX = Math.max(0,       Math.floor(Math.min(x1g, x2g) - pad))
  const maxX = Math.min(gridW-1, Math.ceil (Math.max(x1g, x2g) + pad))
  const minY = Math.max(0,       Math.floor(Math.min(y1g, y2g) - pad))
  const maxY = Math.min(gridH-1, Math.ceil (Math.max(y1g, y2g) + pad))
  if (minX > maxX || minY > maxY) return

  const sdx   = x2g - x1g, sdy = y2g - y1g
  const slen2 = sdx * sdx + sdy * sdy
  const midX  = (x1g + x2g) * 0.5, midY = (y1g + y2g) * 0.5
  const mR2   = (Math.max(2.0, iterR * 0.95) ** 2) * 2  // midpoint falloff scale

  for (let gy = minY; gy <= maxY; gy++) {
    const rowBase = gy * gridW
    for (let gx = minX; gx <= maxX; gx++) {
      const idx = rowBase + gx
      if (!heatMask[idx]) continue           // outside polygon — skip

      const px = gx + 0.5, py = gy + 0.5

      // Squared distance to segment — no sqrt, no exp
      let dSeg2: number
      if (slen2 < 1e-6) {
        const ex = px - x1g, ey = py - y1g
        dSeg2 = ex * ex + ey * ey
      } else {
        const t  = Math.max(0, Math.min(1, ((px - x1g) * sdx + (py - y1g) * sdy) / slen2))
        const ex = px - (x1g + t * sdx), ey = py - (y1g + t * sdy)
        dSeg2 = ex * ex + ey * ey
      }
      if (dSeg2 >= iterR2) continue          // outside radius

      // Quadratic falloff: (1 - d²/R²)² — smooth, zero at boundary, no transcendentals
      const r = dSeg2 / iterR2
      const f = (1 - r) * (1 - r)

      // Midpoint proximity weight (also quadratic)
      const mdx = px - midX, mdy = py - midY
      const md2 = mdx * mdx + mdy * mdy
      const mw  = md2 < mR2 ? (1 - md2 / mR2) * (1 - md2 / mR2) : 0

      const v = heat[idx] + f * (0.65 + 0.35 * mw) * strength
      heat[idx] = v < 1 ? v : 1
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Look-up table: cyan → green → yellow → orange → deep-red (smoother ramp)
// ─────────────────────────────────────────────────────────────────────────────

function buildLUT(): Uint8Array {
  const lut = new Uint8Array(256 * 3)
  // [value 0–1, R, G, B]  — blue → light blue → cyan → green → yellow → red → dark red
  const stops: [number, number, number, number][] = [
    [0.00,   0,   0, 200],  // deep blue
    [0.10,   0,  60, 255],  // blue
    [0.20,   0, 130, 255],  // medium blue
    [0.30,   0, 180, 255],  // light blue
    [0.40,   0, 220, 210],  // lighter blue / cyan-blue
    [0.50,   0, 255, 120],  // cyan-green
    [0.60, 100, 255,   0],  // yellow-green
    [0.70, 210, 255,   0],  // yellow
    [0.78, 255, 200,   0],  // yellow-orange
    [0.86, 255,  80,   0],  // orange-red
    [0.93, 215,  10,   0],  // red
    [1.00, 120,   0,   0],  // dark red
  ]
  for (let i = 0; i < 256; i++) {
    const v = i / 255
    let s0 = stops[0], s1 = stops[1]
    for (let j = 0; j < stops.length - 1; j++) {
      if (v >= stops[j][0] && v <= stops[j + 1][0]) { s0 = stops[j]; s1 = stops[j + 1]; break }
    }
    const span = s1[0] - s0[0]
    const t = span > 0 ? (v - s0[0]) / span : 0
    const u = t * t * (3 - 2 * t) // smooth-step
    lut[i * 3 + 0] = Math.round(s0[1] + (s1[1] - s0[1]) * u)
    lut[i * 3 + 1] = Math.round(s0[2] + (s1[2] - s0[2]) * u)
    lut[i * 3 + 2] = Math.round(s0[3] + (s1[3] - s0[3]) * u)
  }
  return lut
}
const LUT = buildLUT()
// RGBA packed as little-endian uint32: bytes R,G,B,A → R|(G<<8)|(B<<16)|(A<<24)
const LUT32 = new Uint32Array(256)
for (let i = 0; i < 256; i++) {
  LUT32[i] = LUT[i*3] | (LUT[i*3+1] << 8) | (LUT[i*3+2] << 16) | (210 << 24)
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

const RTLSDashboardCanvas = forwardRef<RTLSDashboardCanvasHandle, RTLSDashboardCanvasProps>(
  (
    {
      segments, anchors, tags, roomBounds, roomPolygon,
      svgContent, referenceAnchorId, visualSettings, onViewportChange,
    },
    ref,
  ) => {
    const canvasRef = useRef<HTMLCanvasElement>(null)

    // Viewport (pan + zoom)
    const vpRef = useRef<RTLSViewport>({ offsetX: 0, offsetY: 0, scale: 20 })
    const dragRef = useRef<{ x: number; y: number } | null>(null)

    // SVG floor-plan image
    const svgImgRef = useRef<HTMLImageElement | null>(null)
    const svgBlobUrlRef = useRef<string | null>(null)

    // Walking-animation sprites
    const spritesRef = useRef<{
      stand: HTMLImageElement | null
      left: HTMLImageElement | null
      right: HTMLImageElement | null
    }>({ stand: null, left: null, right: null })

    // Bots (full internal state)
    const botsRef = useRef<BotState[]>([])
    const nextBotIdRef = useRef(1)

    // Heat grid (world-space)
    const heatRef = useRef<Float32Array>(new Float32Array(0))
    const gridWRef = useRef(0)
    const gridHRef = useRef(0)
    const gridOXRef = useRef(0)   // world x of grid col 0
    const gridOYRef = useRef(0)   // world y of grid row 0

    // Offscreen canvas for heat raster
    const heatCanvasRef = useRef<HTMLCanvasElement | null>(null)

    // Per-cell polygon mask: 1 = inside room, 0 = outside
    const heatMaskRef = useRef<Uint8Array>(new Uint8Array(0))

    // rAF handle
    const rafRef = useRef(0)

    // Live copy of props accessible from the rAF closure without stale captures
    const propsRef = useRef({ segments, anchors, tags, roomBounds, roomPolygon, referenceAnchorId, visualSettings, onViewportChange })
    propsRef.current = { segments, anchors, tags, roomBounds, roomPolygon, referenceAnchorId, visualSettings, onViewportChange }

    // ── Load sprites ─────────────────────────────────────────────────────────

    useEffect(() => {
      const entries: [keyof typeof spritesRef.current, string][] = [
        ['stand', `${API_BASE}/assets/walk/Untitled%20Design%20(1).png`],
        ['left',  `${API_BASE}/assets/walk/Untitled%20Design%20(2).png`],
        ['right', `${API_BASE}/assets/walk/Untitled%20Design%20(3).png`],
      ]
      const blobUrls: string[] = []
      entries.forEach(([name, url]) => {
        fetch(url)
          .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.blob() })
          .then(blob => {
            const blobUrl = URL.createObjectURL(blob)
            blobUrls.push(blobUrl)
            const img = new Image()
            img.onload = () => { spritesRef.current[name] = img }
            img.src = blobUrl
          })
          .catch(err => console.warn(`[RTLS] sprite ${name} failed:`, err))
      })
      return () => { blobUrls.forEach(u => URL.revokeObjectURL(u)) }
    }, [])

    // ── Load SVG ─────────────────────────────────────────────────────────────

    useEffect(() => {
      if (svgBlobUrlRef.current) { URL.revokeObjectURL(svgBlobUrlRef.current); svgBlobUrlRef.current = null }
      svgImgRef.current = null
      if (!svgContent) return
      const blob = new Blob([svgContent], { type: 'image/svg+xml' })
      const url = URL.createObjectURL(blob)
      svgBlobUrlRef.current = url
      const img = new Image()
      img.onload = () => { svgImgRef.current = img }
      img.src = url
      return () => { if (svgBlobUrlRef.current) { URL.revokeObjectURL(svgBlobUrlRef.current); svgBlobUrlRef.current = null } }
    }, [svgContent])

    // ── Room bounds helper ────────────────────────────────────────────────────

    function getRoomBounds() {
      const { segments: segs, roomBounds: rb } = propsRef.current
      let minX = -1, minY = -1, maxX = 10, maxY = 10
      if (segs.length > 0) {
        const xs = segs.flatMap(s => [s.x1, s.x2])
        const ys = segs.flatMap(s => [s.y1, s.y2])
        minX = Math.min(...xs); maxX = Math.max(...xs)
        minY = Math.min(...ys); maxY = Math.max(...ys)
      }
      if (rb.min_x !== undefined) { minX = rb.min_x!; minY = rb.min_y!; maxX = rb.max_x!; maxY = rb.max_y! }
      return { minX, minY, maxX, maxY }
    }

    // ── Init heat grid ────────────────────────────────────────────────────────

    function initHeatGrid(b: { minX: number; minY: number; maxX: number; maxY: number }) {
      const margin = 1.0
      const ox = b.minX - margin, oy = b.minY - margin
      const w = Math.max(4, Math.ceil((b.maxX - b.minX + 2 * margin) / CELL_FT))
      const h = Math.max(4, Math.ceil((b.maxY - b.minY + 2 * margin) / CELL_FT))
      gridOXRef.current = ox
      gridOYRef.current = oy
      gridWRef.current = w
      gridHRef.current = h
      heatRef.current = new Float32Array(w * h).fill(BASE_HEAT)
      const hc = document.createElement('canvas')
      hc.width = w; hc.height = h
      heatCanvasRef.current = hc
      // Build per-cell polygon mask
      const poly = propsRef.current.roomPolygon
      const mask = new Uint8Array(w * h)
      if (poly && poly.length >= 3) {
        for (let gy = 0; gy < h; gy++) {
          for (let gx = 0; gx < w; gx++) {
            mask[gy * w + gx] = pointInPolygon(ox + (gx + 0.5) * CELL_FT, oy + (gy + 0.5) * CELL_FT, poly) ? 1 : 0
          }
        }
      } else {
        mask.fill(1)
      }
      heatMaskRef.current = mask
    }

    // ── Reset view ────────────────────────────────────────────────────────────

    function resetView() {
      const canvas = canvasRef.current; if (!canvas) return
      const cw = canvas.clientWidth, ch = canvas.clientHeight
      const padding = 80
      const b = getRoomBounds()
      const rw = b.maxX - b.minX, rh = b.maxY - b.minY
      if (rw <= 0 || rh <= 0) return
      const scale = Math.min((cw - padding * 2) / rw, (ch - padding * 2) / rh)
      vpRef.current = {
        scale,
        offsetX: cw / 2 - ((b.minX + b.maxX) / 2) * scale,
        offsetY: ch / 2 + ((b.minY + b.maxY) / 2) * scale,
      }
      propsRef.current.onViewportChange?.(vpRef.current)
      initHeatGrid(b)
    }

    function zoomIn() { vpRef.current.scale = Math.min(300, vpRef.current.scale * 1.15) }
    function zoomOut() { vpRef.current.scale = Math.max(1, vpRef.current.scale / 1.15) }

    // ── Bot factory ───────────────────────────────────────────────────────────

    function makeBot(poly: { x: number; y: number }[], b: { minX: number; minY: number; maxX: number; maxY: number }): BotState {
      const { x, y } = randomPointInPolygon(poly, b)
      const angle = Math.random() * Math.PI * 2
      return {
        id: nextBotIdRef.current++,
        x, y, speed: 0,
        targetAngle: angle,
        targetDistance: MIN_MOVE_DIST + Math.random() * (MAX_MOVE_DIST - MIN_MOVE_DIST),
        distanceTraveled: 0,
        speedFactor: 0.7 + Math.random() * 0.6,   // per-bot speed variation 0.7–1.3
        accelFactor: 0.7 + Math.random() * 0.6,   // per-bot accel variation 0.7–1.3
        pauseTicks: Math.round(60 * (0.3 + Math.random() * 0.7)),  // initial 0.3–1 s
        angle, isWalking: false, walkPhase: 0, animElapsed: 0, directionSamples: [],
      }
    }

    function activePoly(b: { minX: number; minY: number; maxX: number; maxY: number }) {
      const poly = propsRef.current.roomPolygon
      if (poly && poly.length >= 3) return poly
      return [
        { x: b.minX, y: b.minY }, { x: b.maxX, y: b.minY },
        { x: b.maxX, y: b.maxY }, { x: b.minX, y: b.maxY },
      ]
    }

    function seedBots(n: number) {
      const b = getRoomBounds()
      const poly = activePoly(b)
      for (let i = 0; i < n && botsRef.current.length < MAX_BOTS; i++) {
        botsRef.current.push(makeBot(poly, b))
      }
    }

    function addBot(): number {
      const b = getRoomBounds()
      const poly = activePoly(b)
      if (botsRef.current.length < MAX_BOTS) botsRef.current.push(makeBot(poly, b))
      return botsRef.current.length
    }

    function getBotCount(): number { return botsRef.current.length }

    useImperativeHandle(ref, () => ({ resetView, zoomIn, zoomOut, seedBots, addBot, getBotCount }))

    // ── Render heat to offscreen canvas ───────────────────────────────────────

    function renderHeatToOffscreen(heatPeak: number) {
      const hc = heatCanvasRef.current; if (!hc) return
      const gw = gridWRef.current, gh = gridHRef.current
      if (gw === 0 || gh === 0) return
      const ctx = hc.getContext('2d'); if (!ctx) return
      const imageData = ctx.createImageData(gw, gh)
      const data32 = new Uint32Array(imageData.data.buffer)
      const heat = heatRef.current
      // heatPeak (1–100) caps the max LUT index so peak colour is controllable
      const maxLut   = Math.max(1, (heatPeak / 100 * 255) | 0)
      const heatSpan = 1 - BASE_HEAT
      const scale    = maxLut / heatSpan
      for (let gy = 0; gy < gh; gy++) {
        const heatRow = gh - 1 - gy
        const srcOff  = heatRow * gw
        const dstOff  = gy * gw
        for (let gx = 0; gx < gw; gx++) {
          const idx = Math.min(maxLut, Math.max(0, ((heat[srcOff + gx] - BASE_HEAT) * scale) | 0))
          data32[dstOff + gx] = LUT32[idx]
        }
      }
      ctx.putImageData(imageData, 0, 0)
    }

    // ── Draw one frame ────────────────────────────────────────────────────────

    function drawFrame() {
      const canvas = canvasRef.current; if (!canvas) return
      const ctx = canvas.getContext('2d'); if (!ctx) return

      const { segments: segs, anchors: anch, tags: liveTags, roomPolygon: poly,
              referenceAnchorId: refId, visualSettings: vs } = propsRef.current
      const { offsetX: ox, offsetY: oy, scale } = vpRef.current

      let refX = 0, refY = 0
      if (refId && anch[refId]) { [refX, refY] = anch[refId] }

      const tx = (x: number) => ox + x * scale
      const ty = (y: number) => oy - y * scale
      const tXoff = (x: number) => tx(x - refX)
      const tYoff = (y: number) => ty(y - refY)

      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // ── Heat raster ──────────────────────────────────────────────────────
      if (vs.heatMap && heatCanvasRef.current) {
        const gw = gridWRef.current, gh = gridHRef.current
        if (gw > 0 && gh > 0) {
          const gox = gridOXRef.current, goy = gridOYRef.current
          // Screen rect: top-left = tXoff(gox), tYoff(goy + gh*CELL_FT); bottom-right = tXoff(gox + gw*CELL_FT), tYoff(goy)
          const screenX = tXoff(gox)
          const screenY = tYoff(goy + gh * CELL_FT)   // top of rendered area (highest world Y → smallest screen Y)
          const screenW = gw * CELL_FT * scale
          const screenH = gh * CELL_FT * scale

          if (poly && poly.length >= 3) {
            ctx.save()
            ctx.beginPath()
            ctx.moveTo(tXoff(poly[0].x), tYoff(poly[0].y))
            for (let i = 1; i < poly.length; i++) ctx.lineTo(tXoff(poly[i].x), tYoff(poly[i].y))
            ctx.closePath()
            ctx.clip()
          }
          ctx.globalAlpha = 0.72
          ctx.imageSmoothingEnabled = false   // nearest-neighbor → crisp pixelated blocks
          ctx.drawImage(heatCanvasRef.current, screenX, screenY, screenW, screenH)
          ctx.imageSmoothingEnabled = true
          ctx.globalAlpha = 1.0
          if (poly && poly.length >= 3) ctx.restore()
        }
      }

      // ── Floor plan segments ──────────────────────────────────────────────
      ctx.strokeStyle = 'rgba(140, 180, 230, 0.6)'
      ctx.lineWidth = 1.5
      for (const seg of segs) {
        ctx.beginPath()
        ctx.moveTo(tXoff(seg.x1), tYoff(seg.y1))
        ctx.lineTo(tXoff(seg.x2), tYoff(seg.y2))
        ctx.stroke()
      }

      // ── Anchor connection lines ──────────────────────────────────────────
      const anchorIds = Object.keys(anch)
      if (anchorIds.length >= 2) {
        ctx.strokeStyle = 'rgba(0, 180, 255, 0.2)'; ctx.lineWidth = 1; ctx.setLineDash([6, 4])
        for (let i = 0; i < anchorIds.length; i++) {
          const next = (i + 1) % anchorIds.length
          const [x1, y1] = anch[anchorIds[i]], [x2, y2] = anch[anchorIds[next]]
          ctx.beginPath(); ctx.moveTo(tXoff(x1), tYoff(y1)); ctx.lineTo(tXoff(x2), tYoff(y2)); ctx.stroke()
        }
        ctx.setLineDash([])
      }

      // ── Anchors ──────────────────────────────────────────────────────────
      for (let i = 0; i < anchorIds.length; i++) {
        const aid = anchorIds[i], [ax, ay] = anch[aid]
        const cx = tXoff(ax), cy = tYoff(ay)
        const isRef = aid === refId
        const r = isRef ? 9 : 7, color = anchorColor(i)
        if (isRef) {
          ctx.beginPath(); ctx.arc(cx, cy, r + 4, 0, Math.PI * 2)
          ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash([3, 2]); ctx.stroke(); ctx.setLineDash([])
        }
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2)
        ctx.fillStyle = color; ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.25)'; ctx.lineWidth = 1; ctx.stroke()
        ctx.fillStyle = '#fff'
        ctx.font = `bold ${Math.max(9, Math.min(12, scale * 0.6))}px "SF Mono", monospace`
        ctx.textAlign = 'left'; ctx.textBaseline = 'bottom'
        const lbl = isRef ? `${aid} ★ (0.0, 0.0)` : `${aid} (${(ax - refX).toFixed(1)}, ${(ay - refY).toFixed(1)})`
        ctx.fillText(lbl, cx + 10, cy - 4)
      }

      // ── Tag distance lines ────────────────────────────────────────────────
      const connected = liveTags.filter(t => t.position !== null)
      ctx.setLineDash([4, 4]); ctx.strokeStyle = 'rgba(200, 140, 60, 0.35)'; ctx.lineWidth = 1
      for (let i = 0; i < connected.length; i++) {
        for (let j = i + 1; j < connected.length; j++) {
          const a = connected[i].position!, b2 = connected[j].position!
          const dist = Math.hypot(b2.x - a.x, b2.y - a.y)
          const cx1 = tXoff(a.x), cy1 = tYoff(a.y), cx2 = tXoff(b2.x), cy2 = tYoff(b2.y)
          ctx.beginPath(); ctx.moveTo(cx1, cy1); ctx.lineTo(cx2, cy2); ctx.stroke()
          ctx.setLineDash([])
          ctx.fillStyle = 'rgba(200, 140, 60, 0.7)'; ctx.font = '9px sans-serif'; ctx.textAlign = 'center'
          ctx.fillText(`${dist.toFixed(2)} ft`, (cx1 + cx2) / 2, (cy1 + cy2) / 2 - 6)
          ctx.setLineDash([4, 4])
        }
      }
      ctx.setLineDash([])

      // ── Live tags ─────────────────────────────────────────────────────────
      for (const tag of liveTags) {
        if (!tag.position) continue
        const cx = tXoff(tag.position.x), cy = tYoff(tag.position.y), r = 9
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 2.5)
        grad.addColorStop(0, tag.color + '66'); grad.addColorStop(1, 'transparent')
        ctx.beginPath(); ctx.arc(cx, cy, r * 2.5, 0, Math.PI * 2); ctx.fillStyle = grad; ctx.fill()
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2)
        ctx.fillStyle = tag.color; ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.4)'; ctx.lineWidth = 1.5; ctx.stroke()
        ctx.fillStyle = tag.color; ctx.font = 'bold 11px sans-serif'
        ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
        ctx.fillText(tag.tag_id, cx + 14, cy)
        ctx.fillStyle = 'rgba(200, 220, 255, 0.6)'; ctx.font = '9px sans-serif'
        ctx.fillText(`(${(tag.position.x - refX).toFixed(2)}, ${(tag.position.y - refY).toFixed(2)}) ft`, cx + 14, cy + 12)
      }

      // ── Bots ──────────────────────────────────────────────────────────────
      if (vs.bots && botsRef.current.length > 0) {
        if (poly && poly.length >= 3) {
          ctx.save()
          ctx.beginPath()
          ctx.moveTo(tXoff(poly[0].x), tYoff(poly[0].y))
          for (let i = 1; i < poly.length; i++) ctx.lineTo(tXoff(poly[i].x), tYoff(poly[i].y))
          ctx.closePath(); ctx.clip()
        }

        for (const bot of botsRef.current) {
          const bx = tXoff(bot.x), by = tYoff(bot.y)

          if (vs.botAppearance === 'human') {
            const frameName = bot.isWalking ? (bot.walkPhase === 0 ? 'left' : 'right') : 'stand'
            const sprite = spritesRef.current[frameName]
            if (sprite) {
              const half = SPRITE_PX / 2
              ctx.save()
              ctx.translate(bx, by)
              ctx.rotate(-bot.angle)   // sprite faces right; negate world angle → canvas angle
              ctx.drawImage(sprite, -half, -half, SPRITE_PX, SPRITE_PX)
              ctx.restore()
            } else {
              // Sprite not loaded yet — fall back to dot
              ctx.beginPath(); ctx.arc(bx, by, BOT_DOT_R, 0, Math.PI * 2)
              ctx.fillStyle = '#a0c4ff'; ctx.fill()
            }
          } else if (vs.botAppearance === 'dots') {
            ctx.beginPath(); ctx.arc(bx, by, BOT_DOT_R, 0, Math.PI * 2)
            ctx.fillStyle = '#a0c4ff'; ctx.fill()
            ctx.strokeStyle = 'rgba(255,255,255,0.3)'; ctx.lineWidth = 1; ctx.stroke()
          }
          // 'invisible' → render nothing

          ctx.fillStyle = 'rgba(160,196,255,0.7)'; ctx.font = 'bold 9px sans-serif'
          ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
          ctx.fillText(`B${bot.id}`, bx + BOT_DOT_R + 3, by)
        }

        if (poly && poly.length >= 3) ctx.restore()
      }
    }

    // ── rAF loop ─────────────────────────────────────────────────────────────

    useEffect(() => {
      let lastTime = 0
      let heatTick = 0   // throttle heat update to every other rAF frame

      const loop = (time: number) => {
        const dt = lastTime === 0 ? 0 : Math.min(0.1, (time - lastTime) / 1000)
        lastTime = time

        const { visualSettings: vs, roomPolygon } = propsRef.current
        const b = getRoomBounds()
        const poly = (roomPolygon && roomPolygon.length >= 3)
          ? roomPolygon
          : [{ x: b.minX, y: b.minY }, { x: b.maxX, y: b.minY }, { x: b.maxX, y: b.maxY }, { x: b.minX, y: b.maxY }]

        // Simulate bots every frame (stays smooth)
        if (vs.bots && dt > 0) {
          for (const bot of botsRef.current)
            stepBot(bot, poly, dt, vs.botSpeed, vs.botAccel, vs.botPause)
        }

        // Heat update every 2 frames (~30 hz) — cuts heat cost in half
        heatTick++
        const gw = gridWRef.current, gh = gridHRef.current
        if (gw > 0 && gh > 0 && heatTick % 2 === 0) {
          const heat = heatRef.current
          const heatMask = heatMaskRef.current
          // Decay rate from heatGradientRate: slower rate = slower decay = lingers longer
          const decayRate = Math.max(0.90, 1 - 0.002 / vs.heatGradientRate)
          for (let i = 0; i < heat.length; i++) {
            if (!heatMask[i]) { heat[i] = BASE_HEAT; continue }
            heat[i] += (BASE_HEAT - heat[i]) * (1 - decayRate)
          }

          // Collect entities: live tags + bots
          const entities: [number, number][] = []
          for (const tag of propsRef.current.tags) {
            if (tag.position) entities.push([tag.position.x, tag.position.y])
          }
          if (vs.bots) {
            for (const bot of botsRef.current) entities.push([bot.x, bot.y])
          }

          // Pairwise heat deposit
          const n = entities.length
          for (let i = 0; i < n; i++) {
            for (let j = i + 1; j < n; j++) {
              depositHeat(
                entities[i][0], entities[i][1],
                entities[j][0], entities[j][1],
                heat, heatMask, gw, gh,
                gridOXRef.current, gridOYRef.current,
                vs.heatGradientRate, vs.heatRange,
              )
            }
          }

          renderHeatToOffscreen(vs.heatPeak)
        }

        drawFrame()
        rafRef.current = requestAnimationFrame(loop)
      }

      rafRef.current = requestAnimationFrame(loop)
      return () => cancelAnimationFrame(rafRef.current)
    }, []) // eslint-disable-line react-hooks/exhaustive-deps

    // ── Resize observer ───────────────────────────────────────────────────────

    useEffect(() => {
      const canvas = canvasRef.current; if (!canvas) return
      const parent = canvas.parentElement; if (!parent) return
      const obs = new ResizeObserver(() => {
        canvas.width = parent.clientWidth
        canvas.height = parent.clientHeight
      })
      obs.observe(parent)
      canvas.width = parent.clientWidth
      canvas.height = parent.clientHeight
      return () => obs.disconnect()
    }, [])

    // ── Auto-reset view when room loads ───────────────────────────────────────

    useEffect(() => {
      if (segments.length > 0 || Object.keys(anchors).length > 0) resetView()
    }, [segments.length, Object.keys(anchors).length]) // eslint-disable-line react-hooks/exhaustive-deps

    // ── Rebuild polygon mask when room polygon arrives / changes ──────────────

    useEffect(() => {
      if (!roomPolygon || roomPolygon.length < 3) return
      const gw = gridWRef.current, gh = gridHRef.current
      if (gw === 0 || gh === 0) return
      const ox = gridOXRef.current, oy = gridOYRef.current
      const mask = new Uint8Array(gw * gh)
      for (let gy = 0; gy < gh; gy++) {
        for (let gx = 0; gx < gw; gx++) {
          mask[gy * gw + gx] = pointInPolygon(
            ox + (gx + 0.5) * CELL_FT,
            oy + (gy + 0.5) * CELL_FT,
            roomPolygon,
          ) ? 1 : 0
        }
      }
      heatMaskRef.current = mask
    }, [roomPolygon?.length]) // eslint-disable-line react-hooks/exhaustive-deps

    // ── Mouse: pan ────────────────────────────────────────────────────────────

    const onMouseDown = (e: React.MouseEvent) => { dragRef.current = { x: e.clientX, y: e.clientY } }
    const onMouseMove = (e: React.MouseEvent) => {
      if (!dragRef.current) return
      vpRef.current.offsetX += e.clientX - dragRef.current.x
      vpRef.current.offsetY += e.clientY - dragRef.current.y
      dragRef.current = { x: e.clientX, y: e.clientY }
    }
    const onMouseUp = () => { dragRef.current = null }

    // ── Mouse: zoom ───────────────────────────────────────────────────────────

    useEffect(() => {
      const el = canvasRef.current; if (!el) return
      const handler = (e: WheelEvent) => {
        e.preventDefault(); e.stopPropagation()
        const rect = el.getBoundingClientRect()
        const mx = e.clientX - rect.left, my = e.clientY - rect.top
        const { scale, offsetX, offsetY } = vpRef.current
        const wx = (mx - offsetX) / scale, wy = (offsetY - my) / scale
        const factor = e.deltaY < 0 ? 1.1 : 0.9
        const ns = Math.max(1, Math.min(300, scale * factor))
        vpRef.current = { scale: ns, offsetX: mx - wx * ns, offsetY: my + wy * ns }
      }
      el.addEventListener('wheel', handler, { passive: false })
      return () => el.removeEventListener('wheel', handler)
    }, [])

    return (
      <canvas
        ref={canvasRef}
        className="rtls-map-canvas"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      />
    )
  },
)

RTLSDashboardCanvas.displayName = 'RTLSDashboardCanvas'
export default RTLSDashboardCanvas
