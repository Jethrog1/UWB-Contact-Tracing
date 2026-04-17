# HowToVisuals — Complete Implementation Reference

Deep technical reference for the **Heat Map**, **Walking Bots**, and **Walking Animation** systems
in the BRIGID RTLS Dashboard.  Every parameter, constant, function, and data-flow path is documented here.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [File Map](#2-file-map)
3. [Shared Types and Settings](#3-shared-types-and-settings)
4. [Heat Map System](#4-heat-map-system)
   - 4.1 Grid Initialisation
   - 4.2 Per-Cell Polygon Mask
   - 4.3 Heat Deposit (`depositHeat`)
   - 4.4 Decay
   - 4.5 LUT and Rasterisation (`buildLUT`, `LUT32`, `renderHeatToOffscreen`)
   - 4.6 Screen Rendering with Clipping
   - 4.7 Settings Wiring
5. [Bot Simulation System](#5-bot-simulation-system)
   - 5.1 `BotState` Interface
   - 5.2 Bot Factory (`makeBot`, `seedBots`, `addBot`)
   - 5.3 Physics Step (`stepBot`)
   - 5.4 Polygon Confinement
   - 5.5 Angle Smoothing
6. [Walking Animation System](#6-walking-animation-system)
   - 6.1 Sprite Assets and Loading
   - 6.2 Backend Route
   - 6.3 Animation State Machine
   - 6.4 Rendering (Human / Dots / Invisible)
7. [rAF Game Loop](#7-raf-game-loop)
8. [Frontend Settings Panel](#8-frontend-settings-panel)
   - 8.1 `VisualSettings` Defaults
   - 8.2 `SliderInput` Component
   - 8.3 Visual Settings JSX
9. [CSS Classes](#9-css-classes)
10. [Backend Data Flow](#10-backend-data-flow)
11. [Performance Notes](#11-performance-notes)

---

## 1. System Overview

The RTLS Dashboard overlays three independent visual layers on top of a 2-D floor plan canvas:

| Layer | What it shows | Driven by |
|---|---|---|
| **Heat Map** | Colour raster showing cumulative proximity exposure between entities | Live tags + simulated bots |
| **Bots** | Autonomous agents walking around inside the room polygon | Pure client-side simulation |
| **Walking Animation** | Per-bot sprite or dot that animates in sync with movement speed | Bot physics + sprite images |

All three layers share the same `requestAnimationFrame` loop and read their configuration live from a
`propsRef` ref-wrapper so that React state changes propagate instantly without restarting the loop.

The canvas file is entirely self-contained.  The dashboard file owns all UI state and passes it down
via the `visualSettings` prop.

---

## 2. File Map

```
BRIGID/
├── assets/
│   └── Walking animation/
│       ├── Untitled Design (1).png   ← standing frame
│       ├── Untitled Design (2).png   ← left-foot frame
│       └── Untitled Design (3).png   ← right-foot frame
│
├── backend/
│   ├── cad_server.py                 ← FastAPI server; serves /assets/walk/{filename}
│   ├── RTLSDashboard/
│   │   └── rtls_runtime.py           ← snapshot() emits room_polygon_ft
│   └── utilities/rooms/
│       └── room_data.py              ← Room.to_dict() builds room_polygon_ft
│
└── frontend/src/components/modules/RTLSDashboardModule/
    ├── RTLSDashboardCanvas.tsx       ← ALL simulation + rendering
    ├── RTLSDashboard.tsx             ← Settings UI + polling
    └── RTLSDashboard.css             ← Styles including SliderInput
```

---

## 3. Shared Types and Settings

### `VisualSettings` (exported from `RTLSDashboardCanvas.tsx`)

```typescript
export type BotAppearance = 'invisible' | 'dots' | 'human'

export interface VisualSettings {
  heatMap: boolean            // master toggle — renders heat raster when true
  heatGradientRate: number    // seconds per gradient step  (range 0.05 – 5.0 s/step)
  heatRange: number           // proximity detection radius in ft  (range 0.5 – 30 ft)
  heatPeak: number            // caps max LUT colour index 1–100  (maps to 0–255)
  botAppearance: BotAppearance// 'invisible' | 'dots' | 'human'
  bots: boolean               // master toggle — runs physics + deposits heat when true
  botSpeed: number            // global top speed in ft/s  (range 0.5 – 8)
  botAccel: number            // global acceleration in ft/s²  (range 0.1 – 5)
  botPause: number            // pause duration in seconds  (range 0.2 – 3.0)
}
```

### Default values (`RTLSDashboard.tsx`)

```typescript
const DEFAULT_VISUAL: VisualSettings = {
  heatMap: false,
  heatGradientRate: 0.3,   // quick ramp by default
  heatRange: 5.0,          // 5 ft detection radius
  heatPeak: 70,            // caps at ~70 % of LUT range (yellow–orange region)
  botAppearance: 'dots',
  bots: false,
  botSpeed: 2.0,           // 2 ft/s ≈ casual walk
  botAccel: 1.5,           // 1.5 ft/s²
  botPause: 1.0,           // 1-second pauses ±40 %
}
```

### Simulation constants (`RTLSDashboardCanvas.tsx` module scope)

```typescript
const API_BASE     = 'http://localhost:8765'
const CELL_FT      = 0.02         // heat grid resolution: 0.02 ft per cell (~6 mm)
const BASE_HEAT    = 0.08         // floor value every unvisited cell decays toward
const SPRITE_PX    = 52           // fixed sprite diameter on screen in px (does not scale with zoom)
const BOT_DOT_R    = 7            // dot radius on screen in px
const MAX_BOTS     = 24           // hard cap on simultaneous bots
const MIN_MOVE_DIST = 4.0         // ft — shortest leg before a bot may pause
const MAX_MOVE_DIST = 16.0        // ft — longest leg before a bot may pause
const FRAME_BASE_TIME = 0.35      // seconds per walking animation frame at slow speed
const STOP_ANIM_SPEED = 0.004     // ft/frame — below this speed, stop animation plays
const MIN_SPEED_FACING = 0.003    // ft/frame — below this, do not update facing angle
const DIR_HISTORY  = 8            // how many velocity samples to average for facing angle
const DIR_SMOOTH   = 0.18         // lerp factor per frame for angle smoothing
const ANIM_REF_SPEED = 0.10       // ft/frame reference = ~6 ft/s at 60 fps
```

---

## 4. Heat Map System

### 4.1 Grid Initialisation

Called from `resetView()` and whenever the room bounds change.

```typescript
function initHeatGrid(b: { minX; minY; maxX; maxY }): void
```

**Steps:**
1. Adds a `margin = 1.0 ft` padding around the room bounding box.
2. Computes `gridW = ceil((roomWidth + 2) / CELL_FT)` and `gridH` the same way.
   At `CELL_FT = 0.02` a 20 × 10 ft room produces a 1 100 × 600 cell grid.
3. Stores the world-space origin of cell (0,0) in `gridOXRef` / `gridOYRef`.
4. Allocates a `Float32Array` of size `gridW * gridH` filled with `BASE_HEAT = 0.08`.
5. Creates an offscreen `HTMLCanvasElement` of the same pixel dimensions (`gridW × gridH`)
   for the rasterised output.
6. Calls the polygon-mask builder (see §4.2).

All grid state lives in React refs (never triggers re-render):

| Ref | Type | Contents |
|---|---|---|
| `heatRef` | `Float32Array` | raw heat values 0.0 – 1.0 per cell |
| `gridWRef` / `gridHRef` | `number` | grid dimensions in cells |
| `gridOXRef` / `gridOYRef` | `number` | world-ft origin of col 0 / row 0 |
| `heatCanvasRef` | `HTMLCanvasElement` | offscreen 1-px-per-cell raster |
| `heatMaskRef` | `Uint8Array` | 1 = inside polygon, 0 = outside |

### 4.2 Per-Cell Polygon Mask

Built during `initHeatGrid` and rebuilt whenever `roomPolygon` changes length.

```typescript
// During init:
for (let gy = 0; gy < h; gy++) {
  for (let gx = 0; gx < w; gx++) {
    const worldX = ox + (gx + 0.5) * CELL_FT   // cell-centre world X
    const worldY = oy + (gy + 0.5) * CELL_FT   // cell-centre world Y
    mask[gy * w + gx] = pointInPolygon(worldX, worldY, poly) ? 1 : 0
  }
}
```

`pointInPolygon` is a standard ray-casting algorithm (no external libraries):

```typescript
function pointInPolygon(x, y, poly): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y
    const xj = poly[j].x, yj = poly[j].y
    if (((yi > y) !== (yj > y)) && x < (xj - xi) * (y - yi) / (yj - yi) + xi)
      inside = !inside
  }
  return inside
}
```

The mask serves two purposes:
- **Deposit fast-exit**: `if (!heatMask[idx]) continue` skips ~50 % of cells in a typical room.
- **Decay reset**: cells outside the polygon are forced back to `BASE_HEAT` every frame,
  preventing ghost heat accumulation in corners the clip path might miss.

### 4.3 Heat Deposit (`depositHeat`)

Called pairwise for every combination of (live tags, bots) each heat-tick frame.

```typescript
function depositHeat(
  p1x: number, p1y: number,       // entity 1 world-ft position
  p2x: number, p2y: number,       // entity 2 world-ft position
  heat: Float32Array,
  heatMask: Uint8Array,
  gridW: number, gridH: number,
  gridOX: number, gridOY: number,
  gradientRate: number,            // vs.heatGradientRate
  rangeFt: number,                 // vs.heatRange
): void
```

**Step-by-step logic:**

1. **Range gate** — compute squared distance between the two entities:
   ```typescript
   const pdx = p2x - p1x, pdy = p2y - p1y
   const dist2 = pdx * pdx + pdy * pdy
   if (dist2 >= maxDist * maxDist) return   // entities too far apart — skip entirely
   ```
   `maxDist = rangeFt`.  One `Math.sqrt` outside the inner loop:
   ```typescript
   const dist     = Math.sqrt(dist2)
   const closeness = 1 - dist / maxDist      // 1.0 when touching, 0 at the edge
   ```

2. **Deposit strength** — power-law falloff with `gradientRate` scaling:
   ```typescript
   const depositBase = 0.005 / gradientRate   // smaller rate → faster ramp
   const strength    = depositBase * Math.pow(closeness, 2.2)
   ```
   At `gradientRate = 0.3`, `depositBase ≈ 0.0167`.

3. **Field radius** — how far around the segment the heat spreads:
   ```typescript
   const fieldRad = rangeFt * 0.28          // "exposure field" radius in ft
   const iterR    = Math.min(60, Math.max(3, fieldRad / CELL_FT))   // cells
   ```
   Cap at 60 cells prevents performance issues when `rangeFt` is large.

4. **Bounding box scan** — only iterate cells that could be within `iterR` cells
   of either endpoint:
   ```typescript
   const pad  = Math.ceil(iterR) + 1
   const minX = max(0, floor(min(x1g, x2g) - pad))
   const maxX = min(gridW-1, ceil(max(x1g, x2g) + pad))
   // same for Y
   ```

5. **Inner loop** — for each candidate cell:
   - Skip if `!heatMask[idx]` (outside polygon).
   - Compute squared distance from cell centre to segment using parametric projection
     (no `Math.sqrt`, no `Math.exp`):
     ```typescript
     const t  = clamp01(dot(cellVec, segVec) / slen2)
     const ex = px - (x1g + t * sdx), ey = py - (y1g + t * sdy)
     dSeg2    = ex * ex + ey * ey
     if (dSeg2 >= iterR2) continue
     ```
   - **Quadratic falloff** (smooth, zero at boundary, no transcendentals):
     ```typescript
     const r = dSeg2 / iterR2
     const f = (1 - r) * (1 - r)
     ```
   - **Midpoint proximity weight** — cells near the midpoint of the segment get
     extra heat (models where two people "meet"):
     ```typescript
     const mw = md2 < mR2 ? (1 - md2 / mR2) ** 2 : 0
     const v  = heat[idx] + f * (0.65 + 0.35 * mw) * strength
     heat[idx] = v < 1 ? v : 1    // clamp to 1.0
     ```

### 4.4 Decay

Every heat-tick frame (every 2 rAF frames, ~30 Hz), all cells decay toward `BASE_HEAT`:

```typescript
const decayRate = Math.max(0.90, 1 - 0.002 / vs.heatGradientRate)
for (let i = 0; i < heat.length; i++) {
  if (!heatMask[i]) { heat[i] = BASE_HEAT; continue }  // outside polygon → snap
  heat[i] += (BASE_HEAT - heat[i]) * (1 - decayRate)   // inside → exponential decay
}
```

- At `heatGradientRate = 0.3`: `decayRate = 1 - 0.002/0.3 ≈ 0.9933` → slow decay, heat lingers.
- At `heatGradientRate = 5.0`: `decayRate = max(0.90, 1 - 0.0004) ≈ 0.9996` → very slow decay.
- The `max(0.90, …)` floor prevents the formula producing negative `decayRate` for very small
  `heatGradientRate` values.

**Meaning of `heatGradientRate`**: Think of it as *seconds per gradient step*.  A small value
(e.g. 0.05 s/step) means each deposit adds a lot more heat per frame AND the decay is faster,
so the map responds very dynamically.  A large value (5 s/step) means very slow build-up and
very slow fade.

### 4.5 LUT and Rasterisation

#### Colour LUT (`buildLUT`)

12 stop smooth-step gradient: **deep blue → blue → medium blue → light blue → cyan-green → yellow-green → yellow → yellow-orange → orange-red → red → dark red**.

```typescript
const stops: [value, R, G, B][] = [
  [0.00,   0,   0, 200],   // deep blue
  [0.10,   0,  60, 255],   // blue
  [0.20,   0, 130, 255],   // medium blue
  [0.30,   0, 180, 255],   // light blue
  [0.40,   0, 220, 210],   // lighter blue / cyan-blue
  [0.50,   0, 255, 120],   // cyan-green
  [0.60, 100, 255,   0],   // yellow-green
  [0.70, 210, 255,   0],   // yellow
  [0.78, 255, 200,   0],   // yellow-orange
  [0.86, 255,  80,   0],   // orange-red
  [0.93, 215,  10,   0],   // red
  [1.00, 120,   0,   0],   // dark red
]
```

Between stops: smoothstep interpolation `t² × (3 − 2t)` for a smooth, perceptually-even ramp.

Output: `Uint8Array` of 256×3 bytes (R, G, B per index).

#### `LUT32` — packed RGBA Uint32

To write 4 bytes in a single 32-bit integer operation (zero-copy `Uint32Array` render):

```typescript
const LUT32 = new Uint32Array(256)
for (let i = 0; i < 256; i++) {
  LUT32[i] = LUT[i*3]           // R
           | (LUT[i*3+1] << 8)  // G
           | (LUT[i*3+2] << 16) // B
           | (210 << 24)         // A = 210 (≈ 82 % opacity)
}
// Little-endian layout: bytes in memory are R, G, B, A
```

Alpha = 210 gives the heat raster a slight transparency so the floor plan lines show through.

#### `renderHeatToOffscreen(heatPeak)`

Converts `Float32Array` heat values → RGBA `ImageData` on the offscreen canvas in one tight loop:

```typescript
function renderHeatToOffscreen(heatPeak: number): void {
  const imageData = ctx.createImageData(gw, gh)
  const data32    = new Uint32Array(imageData.data.buffer)

  const maxLut   = Math.max(1, (heatPeak / 100 * 255) | 0)  // e.g. heatPeak=70 → 178
  const heatSpan = 1 - BASE_HEAT                              // 0.92
  const scale    = maxLut / heatSpan                          // LUT index per heat unit

  for (let gy = 0; gy < gh; gy++) {
    const heatRow = gh - 1 - gy   // flip Y: world Y increases up, canvas Y increases down
    const srcOff  = heatRow * gw
    const dstOff  = gy * gw
    for (let gx = 0; gx < gw; gx++) {
      const idx = clamp(0, maxLut, ((heat[srcOff + gx] - BASE_HEAT) * scale) | 0)
      data32[dstOff + gx] = LUT32[idx]
    }
  }
  ctx.putImageData(imageData, 0, 0)
}
```

- **Y-flip**: the heat grid is in world-ft coordinates (Y increases up), but canvas pixels have Y
  increasing down.  The flip is `heatRow = gh - 1 - gy`.
- **`heatPeak`**: clamps the LUT index to `maxLut`.  At `heatPeak = 70` the brightest cell uses
  LUT index 178, which maps to the orange-red zone — cells never reach dark red unless `heatPeak = 100`.
- **Single `Uint32Array` write**: one 32-bit write per pixel replaces four 8-bit writes.

### 4.6 Screen Rendering with Clipping

In `drawFrame`, the offscreen canvas is `drawImage`-d onto the main canvas:

```typescript
if (vs.heatMap && heatCanvasRef.current) {
  // Clip to room polygon (prevents heat appearing in wall thickness / outside)
  ctx.save()
  ctx.beginPath()
  ctx.moveTo(tXoff(poly[0].x), tYoff(poly[0].y))
  for (let i = 1; i < poly.length; i++)
    ctx.lineTo(tXoff(poly[i].x), tYoff(poly[i].y))
  ctx.closePath()
  ctx.clip()

  ctx.globalAlpha = 0.72                   // slight transparency
  ctx.imageSmoothingEnabled = false        // nearest-neighbor → crisp pixelated blocks
  ctx.drawImage(
    heatCanvasRef.current,
    tXoff(gridOX),                         // screen X of grid left edge
    tYoff(gridOY + gh * CELL_FT),          // screen Y of grid top edge (Y flipped)
    gw * CELL_FT * scale,                  // screen width = world width × zoom
    gh * CELL_FT * scale,                  // screen height
  )
  ctx.imageSmoothingEnabled = true
  ctx.globalAlpha = 1.0
  ctx.restore()
}
```

`imageSmoothingEnabled = false` is the key to the "pixelated" look.  Each heat cell is upscaled to
`CELL_FT × scale` screen pixels without blurring — at `scale = 20 px/ft` each 0.02-ft cell renders
as a 0.4 × 0.4 px block; at `scale = 60` each cell is 1.2 × 1.2 px; zoomed in they become large,
visible squares.

The polygon clip provides a render-level guarantee that no heat pixels bleed outside the room walls,
complementing the mask-based deposit guard.

### 4.7 Settings Wiring

| Setting | Range | Effect |
|---|---|---|
| `heatMap` | bool | master toggle; skips `depositHeat` and `drawImage` when false |
| `heatGradientRate` | 0.05 – 5.0 s/step | controls `depositBase` and `decayRate` |
| `heatRange` | 0.5 – 30 ft | controls `maxDist` (trigger range) and `fieldRad` (spread) |
| `heatPeak` | 1 – 100 | caps `maxLut` → limits which portion of the LUT is used |

---

## 5. Bot Simulation System

### 5.1 `BotState` Interface

```typescript
interface BotState {
  id: number              // monotonically incrementing from nextBotIdRef
  x: number               // current world-ft X
  y: number               // current world-ft Y
  speed: number           // current speed in ft/frame (at nominal 60 fps)
  targetAngle: number     // heading toward current waypoint (radians)
  targetDistance: number  // total leg length for current move (ft)
  distanceTraveled: number// ft traveled on current leg
  speedFactor: number     // per-bot speed multiplier 0.7 – 1.3 (set once at birth)
  accelFactor: number     // per-bot accel multiplier 0.7 – 1.3 (set once at birth)
  pauseTicks: number      // frames remaining in current pause (0 = walking)
  angle: number           // smoothed facing angle for sprite rotation (radians)
  isWalking: boolean      // true if animation is in walk cycle
  walkPhase: number       // 0 = left-foot frame, 1 = right-foot frame
  animElapsed: number     // seconds since last animation frame flip
  directionSamples: [number, number][]  // recent velocity vectors for angle smoothing
}
```

### 5.2 Bot Factory

#### `makeBot(poly, b)`

Creates one bot at a random position inside the room polygon:

```typescript
function makeBot(poly, b): BotState {
  const { x, y } = randomPointInPolygon(poly, b)  // rejection-sample with 0.5 ft margin
  const angle    = Math.random() * Math.PI * 2
  return {
    id: nextBotIdRef.current++,
    x, y, speed: 0,
    targetAngle: angle,
    targetDistance: MIN_MOVE_DIST + Math.random() * (MAX_MOVE_DIST - MIN_MOVE_DIST),
    distanceTraveled: 0,
    speedFactor: 0.7 + Math.random() * 0.6,   // uniform [0.7, 1.3]
    accelFactor: 0.7 + Math.random() * 0.6,   // uniform [0.7, 1.3]
    pauseTicks: Math.round(60 * (0.3 + Math.random() * 0.7)),  // initial 0.3 – 1 s pause
    angle, isWalking: false, walkPhase: 0, animElapsed: 0, directionSamples: [],
  }
}
```

`speedFactor` and `accelFactor` are fixed for a bot's lifetime — they make each bot feel
slightly different (some wander fast, some meander slowly) without any extra runtime cost.

#### `randomPointInPolygon`

Up to 300 rejection-sample attempts.  Picks a random point inside the bounding box shrunk by
`0.5 ft` on each side, accepts it if `pointInPolygon` returns true.  Falls back to the bounding-box
centre after 300 misses.

#### `seedBots(n)` / `addBot()`

`seedBots` is called with `n = 6` when the Bots toggle is first enabled and the bot list is empty.
`addBot` adds one bot and returns the new count (displayed in the button label).
Both respect the `MAX_BOTS = 24` hard cap.

### 5.3 Physics Step (`stepBot`)

Called once per rAF frame per bot (60 Hz):

```typescript
function stepBot(
  bot: BotState,
  poly: { x; y }[],
  dt: number,              // elapsed seconds since last frame (capped at 0.1 s)
  botSpeedFtS: number,     // vs.botSpeed — global ft/s setting
  botAccelFtS2: number,    // vs.botAccel — global ft/s² setting
  pauseDuration: number,   // vs.botPause — seconds
): void
```

**Unit conversion at call time** (not stored, recomputed each step):

```typescript
const dtF      = dt * 60                                // normalise to 60-fps frames
const effTop   = botSpeedFtS   * bot.speedFactor / 60   // ft/frame top speed
const effAccel = botAccelFtS2  * bot.accelFactor / 60   // ft/frame acceleration
```

**Speed control (trapezoidal motion profile)**:

```typescript
if (bot.pauseTicks > 0) {
  // Paused: decelerate faster than normal (1.4× accel)
  bot.pauseTicks--
  bot.speed = Math.max(0, bot.speed - effAccel * 1.4 * dtF)
} else {
  const remaining = bot.targetDistance - bot.distanceTraveled
  const brakeDistance = bot.speed² / (2 × effAccel)
  if (remaining <= brakeDistance) {
    // Braking phase: decelerate toward 0
    bot.speed = Math.max(0, bot.speed - effAccel * dtF)
  } else {
    // Accelerating / cruising phase
    bot.speed = Math.min(effTop, bot.speed + effAccel * dtF)
  }
}
```

**Position update**:

```typescript
const vx = cos(bot.targetAngle) * bot.speed * dtF
const vy = sin(bot.targetAngle) * bot.speed * dtF
let nx = bot.x + vx, ny = bot.y + vy
```

**Waypoint completion → new leg**:

```typescript
if (bot.pauseTicks === 0 && bot.speed <= 0.001 && bot.distanceTraveled >= bot.targetDistance) {
  bot.targetAngle    = Math.random() * Math.PI * 2
  bot.targetDistance = MIN_MOVE_DIST + Math.random() * (MAX_MOVE_DIST - MIN_MOVE_DIST)
  bot.distanceTraveled = 0
  // Pause length varies ±40 % around the global setting
  bot.pauseTicks = Math.round(pauseDuration * 60 * (0.6 + Math.random() * 0.8))
}
```

The `0.6 + Math.random() * 0.8` factor means actual pauses are `pauseDuration × (0.6 – 1.4)`.

### 5.4 Polygon Confinement

After computing `nx, ny`, the bot checks if it is still inside the room:

```typescript
if (poly.length >= 3 && !pointInPolygon(nx, ny, poly)) {
  // Reflect heading off nearest wall
  bot.targetAngle = reflectAngleAgainstPolygon(bot.x, bot.y, bot.targetAngle, poly)
  // Try the reflected move
  const rvx = cos(bot.targetAngle) * bot.speed * dtF
  const rvy = sin(bot.targetAngle) * bot.speed * dtF
  nx = bot.x + rvx; ny = bot.y + rvy
  // If still outside, freeze in place (very rare corner case)
  if (!pointInPolygon(nx, ny, poly)) { nx = bot.x; ny = bot.y; bot.speed = 0 }
}
```

`reflectAngleAgainstPolygon` finds the nearest wall edge, computes its outward normal (right-hand
rule on the wound polygon), and reflects the velocity vector:

```typescript
// reflect v around normal n:  v' = v - 2(v·n)n
const dot = vx * nx + vy * ny
reflected  = atan2(vy - 2 * dot * ny, vx - 2 * dot * nx)
```

### 5.5 Angle Smoothing

Bots maintain a `directionSamples` ring buffer of the last `DIR_HISTORY = 8` velocity vectors.
The mean angle (circular mean via `atan2(Σdy, Σdx)`) is lerp-ed toward the bot's current `angle`
at `DIR_SMOOTH = 0.18` per frame:

```typescript
const m = meanAngle(bot.directionSamples)
if (m !== null) bot.angle = smoothAngle(bot.angle, m, DIR_SMOOTH)
```

`smoothAngle` correctly handles the ±π wrap:

```typescript
function smoothAngle(cur, target, t): number {
  return cur + wrapAngle(target - cur) * t
}
```

This prevents the sprite from snapping when the bot reverses direction.

---

## 6. Walking Animation System

### 6.1 Sprite Assets and Loading

Three PNG files in `BRIGID/assets/Walking animation/`:

| File | Key | Used when |
|---|---|---|
| `Untitled Design (1).png` | `stand` | bot is stationary |
| `Untitled Design (2).png` | `left` | `walkPhase === 0` (left foot forward) |
| `Untitled Design (3).png` | `right` | `walkPhase === 1` (right foot forward) |

Sprites face **right** in their natural orientation.  The canvas applies `ctx.rotate(-bot.angle)`
to align the sprite with the bot's world heading.  The negation accounts for the canvas Y-axis
being inverted relative to world Y.

**Loading** — Electron's Content Security Policy blocks `img.src = 'http://…'`.  The sprites are
fetched as binary blobs and converted to `blob://` URLs:

```typescript
useEffect(() => {
  const entries: [name, url][] = [
    ['stand', `${API_BASE}/assets/walk/Untitled%20Design%20(1).png`],
    ['left',  `${API_BASE}/assets/walk/Untitled%20Design%20(2).png`],
    ['right', `${API_BASE}/assets/walk/Untitled%20Design%20(3).png`],
  ]
  entries.forEach(([name, url]) => {
    fetch(url)
      .then(r => r.blob())
      .then(blob => {
        const blobUrl = URL.createObjectURL(blob)
        const img = new Image()
        img.onload = () => { spritesRef.current[name] = img }
        img.src = blobUrl
      })
  })
  return () => { blobUrls.forEach(u => URL.revokeObjectURL(u)) }  // cleanup on unmount
}, [])
```

Until the sprites are loaded, `spritesRef.current[name]` is `null`.  The renderer falls back to
a dot in that case.

### 6.2 Backend Route

`cad_server.py` registers the sprite endpoint:

```python
_WALK_ANIM_DIR = pathlib.Path(__file__).parent.parent / "assets" / "Walking animation"

@app.get("/assets/walk/{filename}")
async def get_walk_asset(filename: str):
    safe = pathlib.Path(filename).name   # strip any path traversal attempts
    fp   = _WALK_ANIM_DIR / safe
    if not fp.exists():
        raise HTTPException(404, detail=f"Asset not found: {safe}")
    return FileResponse(str(fp))
```

The `pathlib.Path(filename).name` call strips any `../` components so only files directly inside
`Walking animation/` can be served.

### 6.3 Animation State Machine

`animFrameTime(speed)` maps the bot's current `speed` (ft/frame) to a frame duration (seconds).
Returns `null` when speed is too low to animate:

```typescript
function animFrameTime(speed: number): number | null {
  if (speed <= STOP_ANIM_SPEED) return null           // below 0.004 ft/frame → stop anim
  const ratio = speed / ANIM_REF_SPEED                // normalise against 6 ft/s ref
  // Stepped lookup: faster speed → shorter frame time → faster stride
  if (ratio < 0.15) return FRAME_BASE_TIME            // 0.35 s
  if (ratio < 0.30) return FRAME_BASE_TIME * 0.85     // 0.298 s
  if (ratio < 0.50) return FRAME_BASE_TIME * 0.70     // 0.245 s
  if (ratio < 0.70) return FRAME_BASE_TIME * 0.55     // 0.193 s
  if (ratio < 0.85) return FRAME_BASE_TIME * 0.45     // 0.158 s
  return FRAME_BASE_TIME * 0.35                        // 0.123 s — full sprint
}
```

Inside `stepBot`, after position is updated:

```typescript
const ft = animFrameTime(bot.speed)
if (ft === null) {
  // Bot has stopped: play one final animation frame then freeze
  if (bot.animElapsed > 0) {
    bot.animElapsed += dt
    if (bot.animElapsed >= slowestFrameTime) {
      bot.isWalking = false; bot.walkPhase = 0; bot.animElapsed = 0
    }
  } else {
    bot.isWalking = false; bot.walkPhase = 0
  }
} else {
  bot.isWalking = true
  bot.animElapsed += dt
  while (bot.animElapsed >= ft) {
    bot.animElapsed -= ft
    bot.walkPhase = 1 - bot.walkPhase   // toggle 0 ↔ 1
  }
}
```

The `while` loop (rather than `if`) ensures the animation stays in sync even if `dt` is large
(e.g. first frame after tab focus is restored).

### 6.4 Rendering (Human / Dots / Invisible)

In `drawFrame`, bots are rendered inside a polygon clip (same technique as heat map):

```typescript
// Clip bots to room polygon
if (poly) { ctx.save(); /* build clip path */; ctx.clip() }

for (const bot of botsRef.current) {
  const bx = tXoff(bot.x), by = tYoff(bot.y)

  if (vs.botAppearance === 'human') {
    const frameName = bot.isWalking
      ? (bot.walkPhase === 0 ? 'left' : 'right')
      : 'stand'
    const sprite = spritesRef.current[frameName]
    if (sprite) {
      const half = SPRITE_PX / 2    // 26 px
      ctx.save()
      ctx.translate(bx, by)
      ctx.rotate(-bot.angle)        // sprite faces right; negate for canvas coords
      ctx.drawImage(sprite, -half, -half, SPRITE_PX, SPRITE_PX)
      ctx.restore()
    } else {
      // Fallback dot while sprite is still loading
      ctx.beginPath(); ctx.arc(bx, by, BOT_DOT_R, 0, Math.PI * 2)
      ctx.fillStyle = '#a0c4ff'; ctx.fill()
    }
  } else if (vs.botAppearance === 'dots') {
    ctx.beginPath(); ctx.arc(bx, by, BOT_DOT_R, 0, Math.PI * 2)
    ctx.fillStyle = '#a0c4ff'; ctx.fill()
    ctx.strokeStyle = 'rgba(255,255,255,0.3)'; ctx.lineWidth = 1; ctx.stroke()
  }
  // 'invisible' → nothing drawn, but bot still simulates and deposits heat

  // Bot label (always drawn regardless of appearance)
  ctx.fillStyle = 'rgba(160,196,255,0.7)'
  ctx.font = 'bold 9px sans-serif'
  ctx.fillText(`B${bot.id}`, bx + BOT_DOT_R + 3, by)
}

if (poly) ctx.restore()
```

`SPRITE_PX = 52` is fixed on screen in pixels — it does **not** scale with zoom level.  This means
bots look the same size regardless of zoom, like UI overlay elements.

---

## 7. rAF Game Loop

The single `useEffect(() => { … }, [])` rAF loop is the heart of the system.  It runs once on mount
and never restarts.  All live prop/state data is read through `propsRef.current` to avoid stale
closures.

```typescript
useEffect(() => {
  let lastTime = 0
  let heatTick = 0        // throttle heat to every other frame

  const loop = (time: number) => {
    const dt = lastTime === 0 ? 0 : Math.min(0.1, (time - lastTime) / 1000)
    lastTime = time

    const { visualSettings: vs, roomPolygon } = propsRef.current
    const b    = getRoomBounds()
    const poly = roomPolygon?.length >= 3 ? roomPolygon : [/* bounding box fallback */]

    // ① Simulate bots — every frame (60 Hz)
    if (vs.bots && dt > 0) {
      for (const bot of botsRef.current)
        stepBot(bot, poly, dt, vs.botSpeed, vs.botAccel, vs.botPause)
    }

    // ② Heat update — every 2nd frame (~30 Hz)
    heatTick++
    if (gw > 0 && gh > 0 && heatTick % 2 === 0) {
      // 2a. Decay all cells
      const decayRate = Math.max(0.90, 1 - 0.002 / vs.heatGradientRate)
      for each cell: heat[i] += (BASE_HEAT - heat[i]) * (1 - decayRate)

      // 2b. Collect entities (live tags + bots)
      const entities = [...tagPositions, ...botPositions]

      // 2c. Pairwise deposit
      for i in entities:
        for j > i in entities:
          depositHeat(entities[i], entities[j], …, vs.heatGradientRate, vs.heatRange)

      // 2d. Rasterise to offscreen canvas
      renderHeatToOffscreen(vs.heatPeak)
    }

    // ③ Draw frame to main canvas
    drawFrame()

    rafRef.current = requestAnimationFrame(loop)
  }

  rafRef.current = requestAnimationFrame(loop)
  return () => cancelAnimationFrame(rafRef.current)
}, [])
```

**Key design decisions:**
- Bot physics runs every frame so motion stays perfectly smooth at 60 fps.
- Heat updates are halved to 30 Hz — heat changes are too gradual to notice at 30 Hz, and this
  cuts heat cost by 50 %.
- `dt` is capped at 0.1 s so a long stall (tab hidden, GC pause) doesn't teleport bots.

---

## 8. Frontend Settings Panel

### 8.1 `VisualSettings` Defaults

Defined in `RTLSDashboard.tsx` and used to initialise the `visualSettings` state:

```typescript
const DEFAULT_VISUAL: VisualSettings = {
  heatMap: false,
  heatGradientRate: 0.3,   // moderate responsiveness
  heatRange: 5.0,          // 5-ft detection radius
  heatPeak: 70,            // stops at orange zone
  botAppearance: 'dots',
  bots: false,
  botSpeed: 2.0,
  botAccel: 1.5,
  botPause: 1.0,
}
```

### 8.2 `SliderInput` Component

A compound control: monospaced text input + range slider that stay in sync.

```typescript
const SliderInput: React.FC<{
  label: string
  value: number           // controlled value from parent
  min: number
  max: number
  step: number
  unit: string            // displayed after text input (e.g. "ft/s", "s/step")
  decimals?: number       // decimal places for formatting (default 1)
  onChange: (v: number) => void
}>
```

**Sync behaviour:**

| User action | Effect |
|---|---|
| Type a digit in text box | Slider moves immediately (clamped) |
| Type an invalid character | Slider stays at last valid value |
| Press Enter | Text is clamped/formatted, `onChange` fires, input blurs |
| Blur text input | Same as Enter |
| Drag slider | Text updates immediately, `onChange` fires |

```typescript
const [text, setText] = useState(() => fmt(value))
const focused = useRef(false)

// External value changes update text only when not focused
useEffect(() => { if (!focused.current) setText(fmt(value)) }, [value])

// Text onChange → immediate slider update
onChange={e => {
  setText(e.target.value)
  const v = parseFloat(e.target.value)
  if (isFinite(v)) onChange(clamp(v))
}}

// Enter/blur → clamp and confirm
onBlur={() => {
  focused.current = false
  const c = isFinite(parseFloat(text)) ? clamp(parseFloat(text)) : value
  setText(fmt(c)); onChange(c)
}}
```

### 8.3 Visual Settings JSX (in order of appearance)

```
Visual Settings section
├── Heat Map toggle (rtls-toggle)
├── SliderInput: "Exposure Rate"  0.05–5.0  step=0.05  unit="s/step"  decimals=2
├── SliderInput: "Range"          0.5–30    step=0.5   unit="ft"       decimals=1
├── Plain range: "Peak Color"     1–100     step=1     (no text input)
│
├── "Bot Appearance" sub-header
├── rtls-transport-tabs (3 buttons):
│   ├── "Invisible"  → botAppearance = 'invisible'
│   ├── "Normal"     → botAppearance = 'dots'
│   └── "Human"      → botAppearance = 'human'
│
├── Bots toggle (rtls-toggle)
│   └── On enable: if getBotCount() === 0, seedBots(6)
├── "Add Random (N/24)" button — disabled if !bots or botCount >= 24
│
├── SliderInput: "Speed"          0.5–8     step=0.1   unit="ft/s"
├── SliderInput: "Acceleration"   0.1–5     step=0.1   unit="ft/s²"
└── SliderInput: "Pause"          0.2–3.0   step=0.1   unit="s"
```

---

## 9. CSS Classes

All in `RTLSDashboard.css`.

### SliderInput-specific classes

```css
/* Monospaced typeable field to the right of the slider label */
.rtls-slider-text-input {
  width: 46px;
  padding: 1px 4px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-accent);            /* accent colour so it stands out */
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  text-align: right;
  outline: none;
  flex-shrink: 0;
}
.rtls-slider-text-input:focus { border-color: var(--border-active); }

/* Unit label ("ft/s", "s/step", etc.) after the text input */
.rtls-slider-unit {
  font-size: var(--text-xs);
  color: var(--text-muted);
  flex-shrink: 0;
}
```

### Toggle switch

```css
.rtls-toggle { position: relative; display: inline-block; width: 34px; height: 18px; }
.rtls-toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
.rtls-toggle-slider { position: absolute; inset: 0; background: var(--border-default); border-radius: 9px; }
.rtls-toggle-slider::after { content:''; position:absolute; width:12px; height:12px;
  left:3px; top:3px; background:#fff; border-radius:50%; transition: transform … }
.rtls-toggle input:checked + .rtls-toggle-slider { background: var(--accent-primary); }
.rtls-toggle input:checked + .rtls-toggle-slider::after { transform: translateX(16px); }
```

### Segmented control (Bot Appearance)

Re-uses `rtls-transport-tab` classes — no new CSS needed:

```css
.rtls-transport-tab--active, .rtls-transport-tab.active {
  background: rgba(75, 114, 159, 0.15);
  border-color: rgba(75, 114, 159, 0.4);
  color: var(--text-primary);
}
```

---

## 10. Backend Data Flow

### How `room_polygon_ft` reaches the canvas

1. **`room_data.py` → `Room.to_dict()`**
   Chains the boundary segments into an ordered polygon using `chain_segments_to_polygon`
   (pure Python, no PyQt6), then serialises every vertex in **world coordinates**:
   ```python
   "room_polygon_ft": [
       {"x": round(lx + self.min_x, 3), "y": round(ly + self.min_y, 3)}
       for lx, ly in self._local_polygon
   ]
   ```

2. **`rtls_runtime.py` → `snapshot()`**
   Stores the polygon list received from `update_from_workspace()` and re-emits it verbatim:
   ```python
   self._room_polygon_ft = room_data.get("room_polygon_ft", [])
   # …
   "room_polygon_ft": list(self._room_polygon_ft),
   ```

3. **`cad_server.py` → `GET /api/rtls/snapshot`**
   Returns the full snapshot dict; the frontend receives `room_polygon_ft` on every 80 ms poll.

4. **`RTLSDashboard.tsx`**
   Maps `data.room_polygon_ft` into the `RTLSSnapshot` type and passes it as:
   ```tsx
   <RTLSDashboardCanvas roomPolygon={snap.room_polygon_ft} … />
   ```

5. **`RTLSDashboardCanvas.tsx`**
   - `initHeatGrid` uses the polygon to build `heatMaskRef`.
   - The rAF loop uses the polygon for bot confinement (`pointInPolygon` / `reflectAngleAgainstPolygon`).
   - `drawFrame` uses the polygon for both the heat-map clip path and the bot clip path.
   - A dedicated `useEffect` on `roomPolygon?.length` rebuilds the mask whenever the polygon changes.

### Sprite asset endpoint

```
BRIGID/assets/Walking animation/Untitled Design (1).png
                               └──────────────────────────────────────┐
                                                                       ↓
FastAPI: GET /assets/walk/Untitled%20Design%20(1).png
         → FileResponse(BRIGID/assets/Walking animation/…)
                                                                       ↓
Frontend fetch() → Blob → blob:// URL → HTMLImageElement
                                                                       ↓
spritesRef.current.stand / .left / .right
```

---

## 11. Performance Notes

### Heat grid cost breakdown

At a typical 20 × 15 ft room with `CELL_FT = 0.02`:
- Grid size: 1 100 × 800 = 880 000 cells
- `Float32Array` footprint: ~3.5 MB
- `Uint8Array` mask: ~880 KB
- Offscreen canvas: 1 100 × 800 × 4 bytes RGBA = ~3.5 MB
- Decay loop (every 2nd frame): iterates 880 000 cells — pure float arithmetic ~0.5 ms
- `depositHeat` (2 entities, range 5 ft): scans ~50 000 cells, ~0.3 ms per pair
- `renderHeatToOffscreen`: 880 000 Uint32 writes ~1 ms

### Optimisations applied

| Technique | Where | Benefit |
|---|---|---|
| `CELL_FT = 0.02` | Grid | ~4× fewer cells than 0.01, still visually fine |
| Quadratic falloff `(1−r)²` | `depositHeat` | Replaces `Math.exp` — ~3× faster |
| Squared distances | `depositHeat` inner loop | Eliminates `Math.sqrt` per cell |
| `iterR` cap at 60 cells | `depositHeat` | Bounds scan area regardless of `rangeFt` |
| `heatMask` early-exit | `depositHeat` inner loop | Skips ~50 % of cells in typical room |
| `LUT32` Uint32Array write | `renderHeatToOffscreen` | 4× fewer array writes vs per-channel |
| Heat throttle ÷2 | rAF loop | Halves heat cost; 30 Hz imperceptible |
| `imageSmoothingEnabled = false` | `drawFrame` | Nearest-neighbor upscale is faster than bilinear |
| `propsRef.current` | rAF loop | Avoids stale closure, no re-mount needed |
| No re-renders in loop | Architecture | All simulation state in refs — zero React overhead |
