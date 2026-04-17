# CodeForHowToVisuals — Full Annotated Source

Every line of code that drives the **Heat Map**, **Walking Bots**, and **Walking Animation**
in the BRIGID RTLS Dashboard.  Each block is followed by a plain-English explanation of exactly
what it does and why it was written that way.

Files touched:
- `BRIGID/frontend/src/components/modules/RTLSDashboardModule/RTLSDashboardCanvas.tsx` — all simulation + rendering
- `BRIGID/frontend/src/components/modules/RTLSDashboardModule/RTLSDashboard.tsx` — settings UI
- `BRIGID/frontend/src/components/modules/RTLSDashboardModule/RTLSDashboard.css` — styles
- `BRIGID/backend/cad_server.py` — sprite asset HTTP endpoint
- `BRIGID/backend/RTLSDashboard/rtls_runtime.py` — room polygon serialisation

---

## PART 1 — CANVAS FILE (`RTLSDashboardCanvas.tsx`)

---

### 1.1 Public Types (top of file, exported)

```typescript
export type BotAppearance = 'invisible' | 'dots' | 'human'

export interface VisualSettings {
  heatMap: boolean
  heatGradientRate: number   // seconds per gradient step  (0.05 – 5.0)
  heatRange: number          // proximity detection radius in ft  (0.5 – 30)
  heatPeak: number           // caps max LUT colour index  (1 – 100)
  botAppearance: BotAppearance
  bots: boolean
  botSpeed: number           // ft/s  (0.5 – 8)
  botAccel: number           // ft/s²  (0.1 – 5)
  botPause: number           // pause duration in seconds  (0.2 – 3.0)
}

export interface SimBot { id: number }

export interface RTLSDashboardCanvasHandle {
  resetView: () => void
  zoomIn: () => void
  zoomOut: () => void
  seedBots: (n: number) => void
  addBot: () => number
  getBotCount: () => number
}
```

**Why:** `VisualSettings` is the single object passed from the settings panel down to the canvas.
Every simulation parameter lives here.  Exporting `BotAppearance` lets the dashboard file use
the type when rendering the segmented control buttons.  `RTLSDashboardCanvasHandle` is the ref
interface — it exposes only the imperative actions the parent needs (reset view, zoom, add bots).
Everything else (physics, heat, animation) is internal and invisible to the outside.

---

### 1.2 Simulation Constants (module scope, never change at runtime)

```typescript
const API_BASE = 'http://localhost:8765'

// ── Heat grid ──────────────────────────────────────────────────────
const CELL_FT  = 0.02   // world-space size of one heat cell in feet (~6 mm)
const BASE_HEAT = 0.08  // floor value: every cell decays toward this

// ── Bot rendering ─────────────────────────────────────────────────
const SPRITE_PX  = 52   // fixed on-screen sprite diameter in pixels (does not zoom)
const BOT_DOT_R  = 7    // fixed on-screen dot radius in pixels
const MAX_BOTS   = 24   // hard upper limit on simultaneous bots

// ── Bot motion ────────────────────────────────────────────────────
const MIN_MOVE_DIST   = 4.0    // ft — shortest leg before bot may pause
const MAX_MOVE_DIST   = 16.0   // ft — longest leg before bot may pause
const FRAME_BASE_TIME = 0.35   // seconds per sprite frame at slowest walking speed
const STOP_ANIM_SPEED = 0.004  // ft/frame — below this speed the walk animation stops
const MIN_SPEED_FACING = 0.003 // ft/frame — below this speed don't update facing angle
const DIR_HISTORY     = 8      // how many recent velocity vectors to average for facing
const DIR_SMOOTH      = 0.18   // lerp factor per frame for angle smoothing (0 = no smooth)
const ANIM_REF_SPEED  = 0.10   // ft/frame reference = roughly 6 ft/s at 60 fps
```

**Why:** These are tuning knobs that were found through experimentation.  `CELL_FT = 0.02` gives
a grid fine enough to look good but coarse enough to stay fast — halving it to 0.01 quadruples
the cell count and makes the heat system ~4× slower.  `BASE_HEAT = 0.08` means "unvisited" cells
map to LUT index ~20, which lands in the deep-blue range of the colour ramp — giving the floor a
cool baseline tint.  `SPRITE_PX = 52` is fixed in screen pixels so bots always look the same size
regardless of zoom, which feels more natural (like placing icons on a map).

---

### 1.3 Internal Bot State Interface

```typescript
interface BotState {
  id: number                          // unique ID, shown as "B1", "B2", etc.
  x: number                           // current position, world feet X
  y: number                           // current position, world feet Y
  speed: number                       // current speed in ft/frame (at 60 fps nominal)
  targetAngle: number                 // heading toward current waypoint, radians
  targetDistance: number              // total distance for this leg in ft
  distanceTraveled: number            // distance covered on current leg in ft
  speedFactor: number                 // per-bot speed multiplier 0.7 – 1.3 (fixed at birth)
  accelFactor: number                 // per-bot accel multiplier 0.7 – 1.3 (fixed at birth)
  pauseTicks: number                  // frames remaining in current stop (0 = walking)
  angle: number                       // smoothed facing angle for sprite rotation
  isWalking: boolean                  // true if walk animation is running
  walkPhase: number                   // 0 = left-foot frame, 1 = right-foot frame
  animElapsed: number                 // seconds since last sprite frame flip
  directionSamples: [number, number][]// recent (dx, dy) velocity vectors, max DIR_HISTORY
}
```

**Why:** This entire struct lives in a `useRef` array — it never touches React state so it never
triggers a re-render.  The distinction between `speed` (ft/frame) and `botSpeed` (ft/s from
settings) is intentional: all physics runs in frame-units internally so you never divide by 60
in the inner loop, only once on the way in.  `speedFactor` and `accelFactor` are assigned once
at birth and never change — they make each bot feel unique (some are slow dawdlers, some are fast
walkers) without any runtime cost.

---

### 1.4 Pure Math Helpers (defined outside component — stable references)

```typescript
// Wrap an angle to the range (-π, π]
function wrapAngle(a: number): number {
  while (a <= -Math.PI) a += 2 * Math.PI
  while (a >   Math.PI) a -= 2 * Math.PI
  return a
}
```

**Why:** Angles wrap when you cross the ±180° boundary.  Without this, lerping from 170° toward
-170° would rotate the sprite all the way around the long way.

```typescript
// Lerp from cur to target, handling the wrap correctly
function smoothAngle(cur: number, target: number, t: number): number {
  return cur + wrapAngle(target - cur) * t
}
```

**Why:** Standard lerp `cur + (target - cur) * t` breaks at the ±π boundary.  `wrapAngle` on the
delta fixes it — always takes the shortest arc.

```typescript
// Circular mean of a list of (dx, dy) velocity vectors
function meanAngle(vecs: [number, number][]): number | null {
  if (!vecs.length) return null
  let sx = 0, sy = 0
  for (const [dx, dy] of vecs) { sx += dx; sy += dy }
  if (Math.abs(sx) < 1e-9 && Math.abs(sy) < 1e-9) return null
  return Math.atan2(sy, sx)
}
```

**Why:** A bot that's been walking north but just turned south has conflicting recent samples.
Summing the unit vectors and taking `atan2` gives the "average direction" correctly — it handles
the circular wrap, and the near-zero guard returns `null` when samples cancel out (bot is
oscillating in place).

```typescript
// Ray-casting point-in-polygon test (no external library needed)
function pointInPolygon(x: number, y: number, poly: { x: number; y: number }[]): boolean {
  let inside = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i].x, yi = poly[i].y
    const xj = poly[j].x, yj = poly[j].y
    if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi))
      inside = !inside
  }
  return inside
}
```

**Why:** Used in three places: building the heat mask, testing bot positions, and spawning bots.
The ray-casting algorithm fires an imaginary ray leftward from the test point and counts how many
polygon edges it crosses — odd count = inside.  No dependencies, works for any convex or concave
polygon.

```typescript
// Reflect a travel angle off the nearest wall of a polygon
function reflectAngleAgainstPolygon(
  x: number, y: number,
  angle: number,
  poly: { x: number; y: number }[],
): number {
  let bestDist = Infinity
  let bestNx = 0, bestNy = 1

  // Find the nearest polygon edge
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length]
    const edx = b.x - a.x, edy = b.y - a.y
    const len = Math.hypot(edx, edy)
    if (len < 1e-9) continue

    // Project bot position onto the edge
    const t  = Math.max(0, Math.min(1, ((x - a.x) * edx + (y - a.y) * edy) / (len * len)))
    const cx = a.x + t * edx, cy = a.y + t * edy
    const dist = Math.hypot(cx - x, cy - y)

    if (dist < bestDist) {
      bestDist = dist
      // Outward normal via right-hand rule on a CCW polygon: rotate edge 90° left
      bestNx = -edy / len
      bestNy =  edx / len
    }
  }

  // Reflect the velocity vector: v' = v - 2(v·n)n
  const vx  = Math.cos(angle), vy = Math.sin(angle)
  const dot = vx * bestNx + vy * bestNy
  return Math.atan2(vy - 2 * dot * bestNy, vx - 2 * dot * bestNx)
}
```

**Why:** When a bot walks outside the polygon, rather than teleporting it back to a random position,
we reflect its heading off the nearest wall — like a billiard ball.  This looks natural and keeps
bots moving continuously.  The outward normal is derived from the edge direction using the right-hand
rule (valid for counter-clockwise wound polygons, which is the standard CAD output).

```typescript
// Pick a random point inside the room polygon (rejection sampling)
function randomPointInPolygon(
  poly: { x: number; y: number }[],
  b: { minX: number; minY: number; maxX: number; maxY: number },
): { x: number; y: number } {
  const margin = 0.5   // ft — keeps bots away from walls at spawn
  for (let attempt = 0; attempt < 300; attempt++) {
    const x = b.minX + margin + Math.random() * (b.maxX - b.minX - 2 * margin)
    const y = b.minY + margin + Math.random() * (b.maxY - b.minY - 2 * margin)
    if (pointInPolygon(x, y, poly)) return { x, y }
  }
  // Fallback: bounding box centre (handles degenerate rooms)
  return { x: (b.minX + b.maxX) / 2, y: (b.minY + b.maxY) / 2 }
}
```

**Why:** Rejection sampling is simple and correct for arbitrary polygons.  300 attempts is
overkill for most rooms but handles very narrow L-shaped or T-shaped spaces.  The 0.5 ft margin
prevents bots spawning on or inside a wall.

---

### 1.5 Bot Physics Step (`stepBot`)

This is called once per bot per rAF frame (60 Hz).

```typescript
function stepBot(
  bot: BotState,
  poly: { x: number; y: number }[],
  dt: number,              // elapsed time this frame in seconds (capped at 0.1)
  botSpeedFtS: number,     // vs.botSpeed — user setting, ft/s
  botAccelFtS2: number,    // vs.botAccel — user setting, ft/s²
  pauseDuration: number,   // vs.botPause — user setting, seconds
): void {
  const dtF = dt * 60   // normalise dt to "how many 60-fps frames elapsed"

  // Convert global ft/s settings → ft/frame, then apply per-bot variation
  const effTop   = botSpeedFtS  * bot.speedFactor / 60
  const effAccel = botAccelFtS2 * bot.accelFactor / 60
```

**Why:** All physics is done in ft/frame (not ft/s) so the inner loop is just multiply-adds
with no division.  The `dtF` factor scales acceleration for frames that took longer than 1/60 s
(e.g. the browser was throttled).  `speedFactor` and `accelFactor` give each bot a unique gait.

```typescript
  // ── Speed control: trapezoidal motion profile ──────────────────────
  if (bot.pauseTicks > 0) {
    // Bot is stopped — count down the pause and decelerate
    bot.pauseTicks--
    bot.speed = Math.max(0, bot.speed - effAccel * 1.4 * dtF)
  } else {
    const remaining     = bot.targetDistance - bot.distanceTraveled
    const brakeDistance = (bot.speed * bot.speed) / (2 * Math.max(effAccel, 1e-6))

    if (remaining <= brakeDistance) {
      // Braking phase: close to waypoint, start decelerating
      bot.speed = Math.max(0, bot.speed - effAccel * dtF)
    } else {
      // Accelerate toward top speed
      bot.speed = Math.min(effTop, bot.speed + effAccel * dtF)
    }
  }
```

**Why:** A constant-speed bot would feel robotic.  A trapezoidal profile (accelerate → cruise →
brake) looks like a real person.  The braking distance formula is kinematics: `v² = 2as` →
`s = v²/2a`.  The 1.4× deceleration during pauses makes bots come to a firm stop quickly
rather than slowly crawling to zero.

```typescript
  // ── Position update ────────────────────────────────────────────────
  const vx = Math.cos(bot.targetAngle) * bot.speed * dtF
  const vy = Math.sin(bot.targetAngle) * bot.speed * dtF
  let nx = bot.x + vx, ny = bot.y + vy

  // ── Polygon confinement ────────────────────────────────────────────
  if (poly.length >= 3 && !pointInPolygon(nx, ny, poly)) {
    // New position is outside the room — reflect heading off nearest wall
    bot.targetAngle = reflectAngleAgainstPolygon(bot.x, bot.y, bot.targetAngle, poly)
    const rvx = Math.cos(bot.targetAngle) * bot.speed * dtF
    const rvy = Math.sin(bot.targetAngle) * bot.speed * dtF
    nx = bot.x + rvx
    ny = bot.y + rvy
    // If still outside after reflection (very rare corner), freeze in place
    if (!pointInPolygon(nx, ny, poly)) { nx = bot.x; ny = bot.y; bot.speed = 0 }
  }

  bot.distanceTraveled += Math.hypot(nx - bot.x, ny - bot.y)
  bot.x = nx
  bot.y = ny
```

**Why:** Two checks catch the outside case.  The first reflection handles the common case (bot
walks into a wall at a mild angle).  The second freeze handles the degenerate case (concave corner
where both the original and reflected moves land outside) — it's better to freeze for one frame
than to teleport.

```typescript
  // ── Facing angle update ────────────────────────────────────────────
  const instSpeed = Math.hypot(vx, vy)
  if (instSpeed > MIN_SPEED_FACING) {
    bot.directionSamples.push([vx, vy])
    if (bot.directionSamples.length > DIR_HISTORY) bot.directionSamples.shift()
    const m = meanAngle(bot.directionSamples)
    if (m !== null) bot.angle = smoothAngle(bot.angle, m, DIR_SMOOTH)
  }
```

**Why:** Using the instantaneous velocity direction would make the sprite jitter when bots slow
down or turn.  Instead, we keep a rolling buffer of the last 8 velocity vectors, take their
circular mean, then lerp the facing angle 18% toward that mean each frame.  The result is a
sprite that turns smoothly, like a person changing direction.

```typescript
  // ── Waypoint completion → pick new leg ────────────────────────────
  if (bot.pauseTicks === 0 && bot.speed <= 0.001 && bot.distanceTraveled >= bot.targetDistance) {
    bot.targetAngle    = Math.random() * Math.PI * 2
    bot.targetDistance = MIN_MOVE_DIST + Math.random() * (MAX_MOVE_DIST - MIN_MOVE_DIST)
    bot.distanceTraveled = 0
    // Pause length: user setting ± 40% natural variation
    bot.pauseTicks = Math.round(pauseDuration * 60 * (0.6 + Math.random() * 0.8))
  }
```

**Why:** A bot is "done" with its leg when it has both traveled far enough AND slowed to a stop.
Checking both prevents premature waypoint completion during braking.  Random angle and random
distance produce varied, believable movement.  The `0.6 + random * 0.8` factor gives a ±40%
variation around the user's pause duration setting so all bots don't stop and start together.

```typescript
  // ── Walking animation state machine ───────────────────────────────
  const ft = animFrameTime(bot.speed)   // returns null if too slow to animate

  if (ft === null) {
    // Below threshold speed: play one last frame then freeze
    if (bot.animElapsed > 0) {
      bot.animElapsed += dt
      if (bot.animElapsed >= (animFrameTime(STOP_ANIM_SPEED + 0.001) ?? FRAME_BASE_TIME)) {
        bot.isWalking  = false
        bot.walkPhase  = 0
        bot.animElapsed = 0
      }
    } else {
      bot.isWalking  = false
      bot.walkPhase  = 0
    }
  } else {
    bot.isWalking    = true
    bot.animElapsed += dt
    // while loop (not if) ensures sync is maintained if dt is large
    while (bot.animElapsed >= ft) {
      bot.animElapsed -= ft
      bot.walkPhase = 1 - bot.walkPhase   // toggle between 0 and 1
    }
  }
}
```

**Why:** The animation timer is decoupled from the physics timer.  `animFrameTime` returns how
many seconds each sprite frame should be displayed — slower speed = longer frame time = slower
stride.  The `while` loop (not `if`) is important: if `dt` is 0.1 s and `ft` is 0.04 s, the
animation needs to advance 2–3 frames in a single update to stay in sync.

---

### 1.6 `animFrameTime` — Speed-to-Stride Mapping

```typescript
function animFrameTime(speed: number): number | null {
  // Returns null when bot is too slow to animate (plays stop frame)
  if (speed <= STOP_ANIM_SPEED) return null   // threshold: 0.004 ft/frame

  const ratio = speed / ANIM_REF_SPEED   // normalise: ANIM_REF_SPEED = 0.10 ft/frame (~6 ft/s)

  // Stepped lookup: higher speed = shorter frame time = faster stride
  if (ratio < 0.15) return FRAME_BASE_TIME             // 0.350 s — creeping
  if (ratio < 0.30) return FRAME_BASE_TIME * 0.85      // 0.298 s — slow walk
  if (ratio < 0.50) return FRAME_BASE_TIME * 0.70      // 0.245 s — normal walk
  if (ratio < 0.70) return FRAME_BASE_TIME * 0.55      // 0.193 s — brisk walk
  if (ratio < 0.85) return FRAME_BASE_TIME * 0.45      // 0.158 s — fast walk
  return FRAME_BASE_TIME * 0.35                         // 0.123 s — running
}
```

**Why:** A continuous function would also work, but a stepped lookup is simpler to tune and debug.
The ratio is normalised against `ANIM_REF_SPEED` so the same stride table works regardless of
what the user sets for `botSpeed` — the animation rate scales proportionally to actual movement.

---

### 1.7 Heat Deposit Function (`depositHeat`)

This is the most performance-critical function in the system.  It adds heat to all grid cells
near the midpoint between two entities.

```typescript
function depositHeat(
  p1x: number, p1y: number,   // entity 1 world-ft position
  p2x: number, p2y: number,   // entity 2 world-ft position
  heat: Float32Array,
  heatMask: Uint8Array,
  gridW: number, gridH: number,
  gridOX: number, gridOY: number,    // world-ft origin of grid cell (0, 0)
  gradientRate: number,               // vs.heatGradientRate
  rangeFt: number,                    // vs.heatRange
): void {
  const maxDist  = rangeFt
  const fieldRad = rangeFt * 0.28     // how far heat spreads from the two entities
  const depositBase = 0.005 / gradientRate
```

**Why:** `fieldRad = rangeFt * 0.28` was tuned so that at range = 5 ft the heat blob is about
1.4 ft wide — enough to be visible but not so large it fills the room.  `depositBase = 0.005 / gradientRate`
means at `gradientRate = 0.3` (fast ramp) each deposit adds ~0.0167 per call.  Higher
`gradientRate` = smaller deposit per frame = slower build-up.

```typescript
  // ── Range gate: skip entirely if entities are too far apart ──────
  const pdx = p2x - p1x, pdy = p2y - p1y
  const dist2 = pdx * pdx + pdy * pdy
  if (dist2 >= maxDist * maxDist) return   // squared comparison: no Math.sqrt yet
```

**Why:** The most common case is entities are far apart — this early return costs one multiply
and one compare, and skips all the work that follows.  Using squared distance avoids a `Math.sqrt`
for this check.

```typescript
  const dist      = Math.sqrt(dist2)          // only one sqrt, paid once outside the inner loop
  const closeness = 1 - dist / maxDist        // 1.0 = touching, 0.0 = at range boundary
  const strength  = depositBase * Math.pow(closeness, 2.2)
  if (strength <= 0) return
```

**Why:** `closeness^2.2` is a slightly super-quadratic falloff — entities that are very close
deposit significantly more heat than entities near the edge of range.  The single `Math.sqrt`
here is the *only* one in this entire function.  Everything in the inner loop uses squared
distances.

```typescript
  // Convert world positions to grid-cell coordinates
  const x1g = (p1x - gridOX) / CELL_FT
  const y1g = (p1y - gridOY) / CELL_FT
  const x2g = (p2x - gridOX) / CELL_FT
  const y2g = (p2y - gridOY) / CELL_FT

  // Iteration radius in cells — capped at 60 to bound cost regardless of rangeFt
  const iterR  = Math.min(60, Math.max(3, fieldRad / CELL_FT))
  const iterR2 = iterR * iterR
```

**Why:** Capping at 60 cells means even at `rangeFt = 30` the inner loop never scans more than
a 121 × 121 cell region.  Without the cap, a large range setting would scan millions of cells
and stall the browser.

```typescript
  // Tight bounding box: only iterate cells that could possibly be within iterR
  const pad  = Math.ceil(iterR) + 1
  const minX = Math.max(0,       Math.floor(Math.min(x1g, x2g) - pad))
  const maxX = Math.min(gridW-1, Math.ceil (Math.max(x1g, x2g) + pad))
  const minY = Math.max(0,       Math.floor(Math.min(y1g, y2g) - pad))
  const maxY = Math.min(gridH-1, Math.ceil (Math.max(y1g, y2g) + pad))
  if (minX > maxX || minY > maxY) return
```

**Why:** Iterating the entire grid every frame would be catastrophically slow.  This tight
bounding box restricts the scan to only the cells that are plausibly within range.

```typescript
  // Precompute segment vector for point-to-segment distance calculation
  const sdx   = x2g - x1g, sdy = y2g - y1g
  const slen2 = sdx * sdx + sdy * sdy
  const midX  = (x1g + x2g) * 0.5, midY = (y1g + y2g) * 0.5
  const mR2   = (Math.max(2.0, iterR * 0.95) ** 2) * 2  // midpoint weight radius squared

  for (let gy = minY; gy <= maxY; gy++) {
    const rowBase = gy * gridW
    for (let gx = minX; gx <= maxX; gx++) {
      const idx = rowBase + gx

      // Fast early-exit: skip cells outside the room polygon
      if (!heatMask[idx]) continue

      const px = gx + 0.5, py = gy + 0.5   // cell centre in grid coordinates
```

**Why:** `heatMask[idx]` is a `Uint8Array` read — extremely fast.  It immediately discards all
cells outside the room polygon without any math.  Using cell-centre coordinates (`gx + 0.5`) gives
more accurate distance calculations than using the corner.

```typescript
      // Squared distance from cell centre to the segment (no Math.sqrt, no Math.exp)
      let dSeg2: number
      if (slen2 < 1e-6) {
        // Segment is a point (both entities at same location)
        const ex = px - x1g, ey = py - y1g
        dSeg2 = ex * ex + ey * ey
      } else {
        // Parametric projection: clamp t to [0,1] to get closest point on segment
        const t  = Math.max(0, Math.min(1, ((px - x1g) * sdx + (py - y1g) * sdy) / slen2))
        const ex = px - (x1g + t * sdx)
        const ey = py - (y1g + t * sdy)
        dSeg2 = ex * ex + ey * ey
      }
      if (dSeg2 >= iterR2) continue   // outside radius — skip
```

**Why:** This is the critical path — executed for every cell in the scan region.  No `Math.sqrt`
here.  The parametric projection finds the closest point on the line segment between the two
entities, then computes squared distance to the cell centre.  The `slen2 < 1e-6` guard handles
the degenerate case where both entities are at the exact same position.

```typescript
      // Quadratic falloff: (1 - d²/R²)² — 1 at centre, 0 at boundary, no transcendentals
      const r = dSeg2 / iterR2
      const f = (1 - r) * (1 - r)

      // Midpoint proximity weight: cells near the segment's midpoint get a bonus
      const mdx = px - midX, mdy = py - midY
      const md2 = mdx * mdx + mdy * mdy
      const mw  = md2 < mR2 ? (1 - md2 / mR2) * (1 - md2 / mR2) : 0

      // Final heat deposit: clamp to 1.0
      const v = heat[idx] + f * (0.65 + 0.35 * mw) * strength
      heat[idx] = v < 1 ? v : 1
    }
  }
}
```

**Why:** `(1-r)²` is a quadratic falloff.  It replaced `Math.exp(-k * d²)` because it is
equally smooth but involves only a subtraction and a multiply — roughly 3× faster in the inner
loop.  The midpoint weight (`mw`) adds extra heat at the centre of the segment (where the two
entities are closest to each other) which creates a natural "hot spot" exactly where contact
occurred.

---

### 1.8 Colour Look-Up Table (`buildLUT` + `LUT32`)

```typescript
function buildLUT(): Uint8Array {
  const lut = new Uint8Array(256 * 3)   // 256 entries × 3 channels (R, G, B)

  // Gradient stops: [normalised value 0–1,  R,  G,  B]
  const stops: [number, number, number, number][] = [
    [0.00,   0,   0, 200],   // deep blue      ← BASE_HEAT maps here (unvisited floor)
    [0.10,   0,  60, 255],   // blue
    [0.20,   0, 130, 255],   // medium blue
    [0.30,   0, 180, 255],   // light blue
    [0.40,   0, 220, 210],   // cyan-blue
    [0.50,   0, 255, 120],   // cyan-green
    [0.60, 100, 255,   0],   // yellow-green
    [0.70, 210, 255,   0],   // yellow
    [0.78, 255, 200,   0],   // yellow-orange
    [0.86, 255,  80,   0],   // orange-red
    [0.93, 215,  10,   0],   // red
    [1.00, 120,   0,   0],   // dark red       ← only reached at heatPeak = 100
  ]

  for (let i = 0; i < 256; i++) {
    const v = i / 255
    // Find the two stops that bracket this value
    let s0 = stops[0], s1 = stops[1]
    for (let j = 0; j < stops.length - 1; j++) {
      if (v >= stops[j][0] && v <= stops[j + 1][0]) { s0 = stops[j]; s1 = stops[j + 1]; break }
    }
    const span = s1[0] - s0[0]
    const t    = span > 0 ? (v - s0[0]) / span : 0
    // Smoothstep: t² × (3 - 2t)  →  eases in and out between stops
    const u = t * t * (3 - 2 * t)
    lut[i * 3 + 0] = Math.round(s0[1] + (s1[1] - s0[1]) * u)   // R
    lut[i * 3 + 1] = Math.round(s0[2] + (s1[2] - s0[2]) * u)   // G
    lut[i * 3 + 2] = Math.round(s0[3] + (s1[3] - s0[3]) * u)   // B
  }
  return lut
}

const LUT = buildLUT()

// Pack RGB + alpha into a single Uint32 for single-write rendering
// Little-endian layout: bytes in memory = R, G, B, A  →  integer = R | G<<8 | B<<16 | A<<24
const LUT32 = new Uint32Array(256)
for (let i = 0; i < 256; i++) {
  LUT32[i] = LUT[i*3]              // R in bits 0–7
           | (LUT[i*3+1] << 8)     // G in bits 8–15
           | (LUT[i*3+2] << 16)    // B in bits 16–23
           | (210 << 24)            // A = 210 (~82% opacity) in bits 24–31
}
```

**Why:** The LUT is computed once at module load time and never changes.  At render time we just
index into `LUT32` — a single array lookup replaces an RGB interpolation calculation per pixel.
`LUT32` packs all four channels into one 32-bit integer so writing to `Uint32Array(imageData.data.buffer)`
is a single memory write per cell instead of four.  Alpha = 210 lets the floor plan lines show
faintly through the heat map.  Smoothstep between colour stops avoids the harsh banding you'd
get from linear interpolation.

---

### 1.9 Refs Declared Inside the Component

```typescript
const canvasRef = useRef<HTMLCanvasElement>(null)
const vpRef     = useRef<RTLSViewport>({ offsetX: 0, offsetY: 0, scale: 20 })
const dragRef   = useRef<{ x: number; y: number } | null>(null)

const svgImgRef     = useRef<HTMLImageElement | null>(null)
const svgBlobUrlRef = useRef<string | null>(null)

// Walking sprite images, loaded once via fetch → blob URL
const spritesRef = useRef<{
  stand: HTMLImageElement | null
  left:  HTMLImageElement | null
  right: HTMLImageElement | null
}>({ stand: null, left: null, right: null })

// Bot physics state — lives entirely in a ref (never triggers re-render)
const botsRef       = useRef<BotState[]>([])
const nextBotIdRef  = useRef(1)

// Heat grid
const heatRef   = useRef<Float32Array>(new Float32Array(0))
const gridWRef  = useRef(0)
const gridHRef  = useRef(0)
const gridOXRef = useRef(0)   // world-ft X of grid column 0
const gridOYRef = useRef(0)   // world-ft Y of grid row 0

const heatCanvasRef = useRef<HTMLCanvasElement | null>(null)  // offscreen raster
const heatMaskRef   = useRef<Uint8Array>(new Uint8Array(0))  // 1 = inside polygon

const rafRef = useRef(0)   // requestAnimationFrame handle for cleanup

// Live mirror of props — lets the rAF closure read current values without stale captures
const propsRef = useRef({ segments, anchors, tags, roomBounds, roomPolygon,
                           referenceAnchorId, visualSettings, onViewportChange })
propsRef.current = { … }   // reassigned every render
```

**Why:** The `propsRef` pattern is the most important architectural decision here.  The rAF loop
is started once (empty dependency array `[]`) and runs forever.  If it captured `visualSettings`
directly, it would always see the value from the first render — a stale closure.  Instead, it
reads `propsRef.current.visualSettings` which is updated on every render.  All simulation state
(bots, heat, viewport) lives in refs so that updating them doesn't cause React to re-render the
component on every frame.

---

### 1.10 Sprite Loading Effect

```typescript
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
        img.src = blobUrl   // setting src on blob:// URL is allowed by Electron CSP
      })
      .catch(err => console.warn(`[RTLS] sprite ${name} failed:`, err))
  })

  // Cleanup: revoke blob URLs when the component unmounts
  return () => { blobUrls.forEach(u => URL.revokeObjectURL(u)) }
}, [])   // empty deps: run once on mount
```

**Why:** Electron's Content Security Policy (CSP) blocks `img.src = 'http://localhost:8765/…'`
directly — it treats any `http://` image source as potentially unsafe.  The fix is to `fetch()`
the binary data, convert it to a `Blob`, then create a `blob://` URL from it.  `blob://` URLs
are local and trusted by Electron's CSP.  Until `img.onload` fires, `spritesRef.current[name]`
stays `null` and the renderer falls back to drawing a dot — so there is no blank frame.

---

### 1.11 Heat Grid Initialisation

```typescript
function initHeatGrid(b: { minX: number; minY: number; maxX: number; maxY: number }) {
  const margin = 1.0   // 1-ft padding around the room bounding box
  const ox = b.minX - margin
  const oy = b.minY - margin
  const w  = Math.max(4, Math.ceil((b.maxX - b.minX + 2 * margin) / CELL_FT))
  const h  = Math.max(4, Math.ceil((b.maxY - b.minY + 2 * margin) / CELL_FT))

  // Store grid origin and dimensions
  gridOXRef.current = ox
  gridOYRef.current = oy
  gridWRef.current  = w
  gridHRef.current  = h

  // Initialise all cells to BASE_HEAT (deep blue = "unvisited")
  heatRef.current = new Float32Array(w * h).fill(BASE_HEAT)

  // Create the offscreen canvas exactly the same size as the grid (1px per cell)
  const hc = document.createElement('canvas')
  hc.width  = w
  hc.height = h
  heatCanvasRef.current = hc

  // Build per-cell polygon mask
  const poly = propsRef.current.roomPolygon
  const mask = new Uint8Array(w * h)
  if (poly && poly.length >= 3) {
    for (let gy = 0; gy < h; gy++) {
      for (let gx = 0; gx < w; gx++) {
        // Test the world-ft centre of each cell
        const wx = ox + (gx + 0.5) * CELL_FT
        const wy = oy + (gy + 0.5) * CELL_FT
        mask[gy * w + gx] = pointInPolygon(wx, wy, poly) ? 1 : 0
      }
    }
  } else {
    mask.fill(1)   // no polygon available: treat entire grid as inside
  }
  heatMaskRef.current = mask
}
```

**Why:** The offscreen canvas is 1 pixel per cell.  This is intentional: it means the canvas
is tiny (e.g. 1 100 × 800 px for a 20 × 15 ft room) and `putImageData` on it is fast.  When it
is drawn to the main canvas with `drawImage`, it is scaled up by the current zoom level — and
because `imageSmoothingEnabled = false`, it upscales with nearest-neighbor giving the crisp
pixelated block look.  The mask build is an O(w×h) loop that runs only on room load, not every
frame.

---

### 1.12 Render Heat to Offscreen Canvas

```typescript
function renderHeatToOffscreen(heatPeak: number) {
  const hc = heatCanvasRef.current; if (!hc) return
  const gw = gridWRef.current, gh = gridHRef.current
  if (gw === 0 || gh === 0) return
  const ctx = hc.getContext('2d'); if (!ctx) return

  const imageData = ctx.createImageData(gw, gh)
  // View the RGBA byte array as 32-bit integers for single-write per pixel
  const data32 = new Uint32Array(imageData.data.buffer)

  const heat = heatRef.current
  // heatPeak (1–100) caps the LUT index — at 70 the peak cell maps to LUT[178] (orange)
  const maxLut   = Math.max(1, (heatPeak / 100 * 255) | 0)
  const heatSpan = 1 - BASE_HEAT   // range of heat values above the baseline
  const scale    = maxLut / heatSpan

  for (let gy = 0; gy < gh; gy++) {
    // Y-flip: world Y increases upward, canvas Y increases downward
    const heatRow = gh - 1 - gy
    const srcOff  = heatRow * gw
    const dstOff  = gy * gw

    for (let gx = 0; gx < gw; gx++) {
      // Map heat value → LUT index, clamped to [0, maxLut]
      const idx = Math.min(maxLut, Math.max(0, ((heat[srcOff + gx] - BASE_HEAT) * scale) | 0))
      data32[dstOff + gx] = LUT32[idx]   // single 32-bit write: R, G, B, A at once
    }
  }
  ctx.putImageData(imageData, 0, 0)
}
```

**Why:** The Y-flip (`heatRow = gh - 1 - gy`) is necessary because world coordinates have Y
increasing upward (standard math / engineering convention) but the canvas has Y increasing
downward.  Without the flip, the heat map appears mirrored vertically.  The `| 0` is a fast
floor (bitwise OR with 0 truncates to integer).  Writing to a `Uint32Array` view of the
`ImageData` buffer writes all 4 bytes (R, G, B, A) at once — four times fewer array operations
than writing each channel separately.

---

### 1.13 Draw Frame — Heat Raster Section

```typescript
// In drawFrame():

if (vs.heatMap && heatCanvasRef.current) {
  const gw = gridWRef.current, gh = gridHRef.current
  if (gw > 0 && gh > 0) {
    const gox = gridOXRef.current, goy = gridOYRef.current

    // Clip rendering to the room polygon — heat cannot bleed outside walls
    if (poly && poly.length >= 3) {
      ctx.save()
      ctx.beginPath()
      ctx.moveTo(tXoff(poly[0].x), tYoff(poly[0].y))
      for (let i = 1; i < poly.length; i++) ctx.lineTo(tXoff(poly[i].x), tYoff(poly[i].y))
      ctx.closePath()
      ctx.clip()
    }

    ctx.globalAlpha = 0.72               // slight transparency so floor plan shows through
    ctx.imageSmoothingEnabled = false    // nearest-neighbor upscale → crisp pixelated blocks

    ctx.drawImage(
      heatCanvasRef.current,
      tXoff(gox),                        // screen X of grid left edge
      tYoff(goy + gh * CELL_FT),         // screen Y of grid top (world Y increases up → subtract)
      gw * CELL_FT * scale,              // screen width = world width × zoom scale
      gh * CELL_FT * scale,              // screen height
    )

    ctx.imageSmoothingEnabled = true
    ctx.globalAlpha = 1.0
    if (poly && poly.length >= 3) ctx.restore()
  }
}
```

**Why:** Two layers of confinement: the `heatMask` prevents deposit outside the polygon, and
`ctx.clip()` prevents the drawn pixels from appearing outside it.  The clip is the safety net
for interpolation artifacts at grid edges.  `tYoff(goy + gh * CELL_FT)` is the screen Y of the
*top* of the grid because higher world Y maps to lower screen Y — the canvas coordinate system
is flipped.

---

### 1.14 Draw Frame — Bot Rendering Section

```typescript
if (vs.bots && botsRef.current.length > 0) {
  // Clip bots to room polygon (same technique as heat map)
  if (poly && poly.length >= 3) {
    ctx.save()
    ctx.beginPath()
    ctx.moveTo(tXoff(poly[0].x), tYoff(poly[0].y))
    for (let i = 1; i < poly.length; i++) ctx.lineTo(tXoff(poly[i].x), tYoff(poly[i].y))
    ctx.closePath()
    ctx.clip()
  }

  for (const bot of botsRef.current) {
    const bx = tXoff(bot.x), by = tYoff(bot.y)

    if (vs.botAppearance === 'human') {
      // Pick sprite frame based on walk state
      const frameName = bot.isWalking
        ? (bot.walkPhase === 0 ? 'left' : 'right')
        : 'stand'
      const sprite = spritesRef.current[frameName]

      if (sprite) {
        const half = SPRITE_PX / 2   // 26px — draw centred on bot position
        ctx.save()
        ctx.translate(bx, by)
        ctx.rotate(-bot.angle)   // sprites face RIGHT by default; negate world angle for canvas
        ctx.drawImage(sprite, -half, -half, SPRITE_PX, SPRITE_PX)
        ctx.restore()
      } else {
        // Sprite not yet loaded — draw dot as placeholder
        ctx.beginPath(); ctx.arc(bx, by, BOT_DOT_R, 0, Math.PI * 2)
        ctx.fillStyle = '#a0c4ff'; ctx.fill()
      }

    } else if (vs.botAppearance === 'dots') {
      ctx.beginPath(); ctx.arc(bx, by, BOT_DOT_R, 0, Math.PI * 2)
      ctx.fillStyle = '#a0c4ff'; ctx.fill()
      ctx.strokeStyle = 'rgba(255,255,255,0.3)'; ctx.lineWidth = 1; ctx.stroke()
    }
    // 'invisible': nothing drawn but bot still moves and deposits heat

    // Bot ID label (always shown regardless of botAppearance)
    ctx.fillStyle = 'rgba(160,196,255,0.7)'
    ctx.font = 'bold 9px sans-serif'
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
    ctx.fillText(`B${bot.id}`, bx + BOT_DOT_R + 3, by)
  }

  if (poly && poly.length >= 3) ctx.restore()
}
```

**Why:** `ctx.rotate(-bot.angle)` — the sprites were drawn facing right (angle = 0 in the
sprite).  In world space, angle = 0 also means "facing right" (positive X).  The canvas Y axis
is inverted, which flips angles: `ctx.rotate(+angle)` would mirror the rotation.  Negating
`bot.angle` corrects for the flip so the sprite faces the direction the bot is actually moving.
`SPRITE_PX = 52` is fixed on screen — bots don't scale with zoom.

---

### 1.15 The rAF Game Loop

```typescript
useEffect(() => {
  let lastTime = 0
  let heatTick = 0   // used to throttle heat updates to every 2nd frame

  const loop = (time: number) => {
    // dt = elapsed time in seconds; cap at 0.1 s to prevent physics explosion after stall
    const dt = lastTime === 0 ? 0 : Math.min(0.1, (time - lastTime) / 1000)
    lastTime = time

    const { visualSettings: vs, roomPolygon } = propsRef.current
    const b    = getRoomBounds()
    const poly = (roomPolygon && roomPolygon.length >= 3)
      ? roomPolygon
      : [{ x: b.minX, y: b.minY }, { x: b.maxX, y: b.minY },
         { x: b.maxX, y: b.maxY }, { x: b.minX, y: b.maxY }]

    // ── ① Bot physics — every frame (60 Hz) ──────────────────────────
    if (vs.bots && dt > 0) {
      for (const bot of botsRef.current)
        stepBot(bot, poly, dt, vs.botSpeed, vs.botAccel, vs.botPause)
    }

    // ── ② Heat update — every 2nd frame (~30 Hz) ──────────────────────
    heatTick++
    const gw = gridWRef.current, gh = gridHRef.current

    if (gw > 0 && gh > 0 && heatTick % 2 === 0) {
      const heat     = heatRef.current
      const heatMask = heatMaskRef.current

      // Exponential decay toward BASE_HEAT
      // decayRate close to 1 = very slow decay (heat lingers)
      const decayRate = Math.max(0.90, 1 - 0.002 / vs.heatGradientRate)
      for (let i = 0; i < heat.length; i++) {
        if (!heatMask[i]) {
          heat[i] = BASE_HEAT   // outside polygon: snap to baseline (no ghost heat)
          continue
        }
        heat[i] += (BASE_HEAT - heat[i]) * (1 - decayRate)
      }

      // Collect all entity positions: live UWB tags + simulated bots
      const entities: [number, number][] = []
      for (const tag of propsRef.current.tags) {
        if (tag.position) entities.push([tag.position.x, tag.position.y])
      }
      if (vs.bots) {
        for (const bot of botsRef.current) entities.push([bot.x, bot.y])
      }

      // Pairwise deposit: every unique pair of entities
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

      // Rasterise updated heat values to offscreen canvas
      renderHeatToOffscreen(vs.heatPeak)
    }

    // ── ③ Render everything to main canvas ────────────────────────────
    drawFrame()

    rafRef.current = requestAnimationFrame(loop)
  }

  rafRef.current = requestAnimationFrame(loop)
  return () => cancelAnimationFrame(rafRef.current)   // cleanup on unmount
}, [])   // empty deps: loop starts once and runs forever
```

**Why:** Bot physics runs at 60 Hz for smooth animation.  Heat runs at 30 Hz because heat
changes are gradual and imperceptible at 30 Hz — this halves the heat computation cost.
`heatTick % 2` is the throttle gate.  The decay formula `heat[i] += (BASE_HEAT - heat[i]) * (1 - decayRate)`
is exponential decay — it asymptotically approaches `BASE_HEAT` rather than going negative.
Pairwise deposit (`i < j` nested loop) ensures each pair is counted once — if you used all pairs
including `(i, j)` and `(j, i)` separately, every deposit would be counted twice.

---

## PART 2 — DASHBOARD FILE (`RTLSDashboard.tsx`)

---

### 2.1 `SliderInput` Component

```typescript
const SliderInput: React.FC<{
  label: string
  value: number          // controlled value owned by parent
  min: number
  max: number
  step: number
  unit: string           // unit label shown after the text input (e.g. "ft/s", "s/step")
  decimals?: number      // decimal places for display (default 1)
  onChange: (v: number) => void
}> = ({ label, value, min, max, step, unit, decimals = 1, onChange }) => {

  const fmt = (n: number) => n.toFixed(decimals)
  const [text, setText] = useState(() => fmt(value))
  const focused = useRef(false)

  // When value changes externally and input is not focused, sync display text
  useEffect(() => {
    if (!focused.current) setText(fmt(value))
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps

  const clamp    = (n: number) => Math.max(min, Math.min(max, n))
  const parsed   = parseFloat(text)
  const sliderVal = isFinite(parsed) ? clamp(parsed) : value

  return (
    <div className="rtls-slider-row">
      <div className="rtls-slider-header">
        <span className="rtls-slider-label">{label}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>

          {/* Typeable text input */}
          <input
            type="text"
            className="rtls-slider-text-input"
            value={text}
            onFocus={() => { focused.current = true }}
            onChange={e => {
              setText(e.target.value)
              const v = parseFloat(e.target.value)
              if (isFinite(v)) onChange(clamp(v))   // slider moves immediately as you type
            }}
            onBlur={() => {
              focused.current = false
              const v = parseFloat(text)
              const c = isFinite(v) ? clamp(v) : value
              setText(fmt(c)); onChange(c)           // clamp and format on blur
            }}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                const v = parseFloat(text)
                const c = isFinite(v) ? clamp(v) : value
                setText(fmt(c)); onChange(c)
                ;(e.target as HTMLInputElement).blur()
              }
            }}
          />

          <span className="rtls-slider-unit">{unit}</span>
        </div>
      </div>

      {/* Range slider — tracks text input value */}
      <input
        type="range" className="rtls-range"
        min={min} max={max} step={step}
        value={sliderVal}
        onChange={e => {
          const v = parseFloat(e.target.value)
          setText(fmt(v)); onChange(v)
        }}
      />
    </div>
  )
}
```

**Why:** The `focused` ref prevents an external value update from overwriting text the user is
actively typing.  The `onChange` on the text input fires on every keystroke — if the current
text is a valid number, it immediately updates the slider position (via `sliderVal`) so the user
gets visual feedback while typing.  Enter/blur triggers clamping and formatting so the text box
always shows a clean, valid number after confirmation.

---

### 2.2 Default Visual Settings

```typescript
const DEFAULT_VISUAL: VisualSettings = {
  heatMap: false,
  heatGradientRate: 0.3,   // fast ramp: heat builds up quickly at default
  heatRange: 5.0,          // 5-ft detection radius
  heatPeak: 70,            // peaks at orange zone (index 178/255)
  botAppearance: 'dots',   // dots until user switches to Human
  bots: false,
  botSpeed: 2.0,           // 2 ft/s ≈ relaxed walking pace
  botAccel: 1.5,           // moderate acceleration
  botPause: 1.0,           // 1-second pauses at waypoints
}
```

---

### 2.3 Visual Settings JSX — Complete Section

```tsx
{/* Visual Settings */}
<div className="rtls-section">
  <div className="rtls-section-title">Visual Settings</div>

  {/* ── Heat Map master toggle ── */}
  <div className="rtls-toggle-row">
    <span className="rtls-toggle-label">Heat Map</span>
    <label className="rtls-toggle">
      <input
        type="checkbox"
        checked={visualSettings.heatMap}
        onChange={e => setVisualSettings(p => ({ ...p, heatMap: e.target.checked }))}
      />
      <span className="rtls-toggle-slider" />
    </label>
  </div>

  {/* ── Exposure Rate: seconds per gradient step ── */}
  <SliderInput
    label="Exposure Rate"
    value={visualSettings.heatGradientRate}
    min={0.05} max={5.0} step={0.05} decimals={2} unit="s/step"
    onChange={v => setVisualSettings(p => ({ ...p, heatGradientRate: v }))}
  />

  {/* ── Range: proximity detection radius in ft ── */}
  <SliderInput
    label="Range"
    value={visualSettings.heatRange}
    min={0.5} max={30} step={0.5} decimals={1} unit="ft"
    onChange={v => setVisualSettings(p => ({ ...p, heatRange: v }))}
  />

  {/* ── Peak Color: plain slider, no text input ── */}
  <div className="rtls-slider-row">
    <div className="rtls-slider-header">
      <span className="rtls-slider-label">Peak Color</span>
      <span className="rtls-slider-value">{visualSettings.heatPeak}</span>
    </div>
    <input
      type="range" className="rtls-range"
      min={1} max={100} step={1}
      value={visualSettings.heatPeak}
      onChange={e => setVisualSettings(p => ({ ...p, heatPeak: parseInt(e.target.value) }))}
    />
  </div>

  {/* ── Bot Appearance: 3-option segmented control ── */}
  <div className="rtls-section-title" style={{ marginTop: 10 }}>Bot Appearance</div>
  <div className="rtls-transport-tabs">
    {(['invisible', 'dots', 'human'] as BotAppearance[]).map(opt => (
      <button
        key={opt}
        className={`rtls-transport-tab${visualSettings.botAppearance === opt ? ' active' : ''}`}
        onClick={() => setVisualSettings(p => ({ ...p, botAppearance: opt }))}
      >
        {opt === 'invisible' ? 'Invisible' : opt === 'dots' ? 'Normal' : 'Human'}
      </button>
    ))}
  </div>

  {/* ── Bots master toggle — seeds 6 bots on first enable ── */}
  <div className="rtls-toggle-row" style={{ marginTop: 6 }}>
    <span className="rtls-toggle-label">Bots</span>
    <label className="rtls-toggle">
      <input
        type="checkbox"
        checked={visualSettings.bots}
        onChange={e => {
          const enabled = e.target.checked
          setVisualSettings(p => ({ ...p, bots: enabled }))
          // Auto-seed 6 bots the first time the toggle is turned on
          if (enabled && canvasRef.current && canvasRef.current.getBotCount() === 0) {
            canvasRef.current.seedBots(6)
            setBotCount(6)
          }
        }}
      />
      <span className="rtls-toggle-slider" />
    </label>
  </div>

  {/* ── Add Random button — disabled when bots off or at cap ── */}
  <button
    className="rtls-btn rtls-btn--full"
    style={{ marginTop: 4 }}
    disabled={!visualSettings.bots || botCount >= MAX_BOTS}
    onClick={() => {
      if (!canvasRef.current) return
      setBotCount(canvasRef.current.addBot())
    }}
  >
    Add Random{botCount > 0 ? ` (${botCount}/${MAX_BOTS})` : ''}
  </button>

  {/* ── Speed, Acceleration, Pause ── */}
  <SliderInput
    label="Speed"
    value={visualSettings.botSpeed}
    min={0.5} max={8} step={0.1} decimals={1} unit="ft/s"
    onChange={v => setVisualSettings(p => ({ ...p, botSpeed: v }))}
  />
  <SliderInput
    label="Acceleration"
    value={visualSettings.botAccel}
    min={0.1} max={5} step={0.1} decimals={1} unit="ft/s²"
    onChange={v => setVisualSettings(p => ({ ...p, botAccel: v }))}
  />
  <SliderInput
    label="Pause"
    value={visualSettings.botPause}
    min={0.2} max={3.0} step={0.1} decimals={1} unit="s"
    onChange={v => setVisualSettings(p => ({ ...p, botPause: v }))}
  />

</div>
```

**Why the segmented control uses `rtls-transport-tab` styles:** The Bluetooth/Serial tabs in the
Connectivity section already have exactly the right visual treatment (inactive grey → active blue
highlight).  Re-using the same class for Bot Appearance keeps the design consistent without adding
new CSS.

---

## PART 3 — CSS (`RTLSDashboard.css`)

---

### 3.1 SliderInput Classes

```css
/* Monospaced number field on the right of the slider label row */
.rtls-slider-text-input {
  width: 46px;
  padding: 1px 4px;
  background: transparent;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  color: var(--text-accent);       /* accent colour distinguishes it from muted label text */
  font-family: var(--font-mono);   /* monospaced so digits don't jump width as you type */
  font-size: var(--text-xs);
  text-align: right;               /* numbers right-aligned look cleaner */
  outline: none;
  flex-shrink: 0;                  /* never shrink — always 46px wide */
}

.rtls-slider-text-input:focus {
  border-color: var(--border-active);   /* highlights which field is active */
}

/* Unit label shown after the text input ("ft/s", "s/step", etc.) */
.rtls-slider-unit {
  font-size: var(--text-xs);
  color: var(--text-muted);   /* muted so it's visible but doesn't compete with the value */
  flex-shrink: 0;
}
```

### 3.2 Toggle Switch Classes

```css
/* Container — fixed size, relative positioning for the absolute children */
.rtls-toggle {
  position: relative;
  display: inline-block;
  width: 34px;
  height: 18px;
  flex-shrink: 0;
  cursor: pointer;
}

/* Hide native checkbox — we draw our own */
.rtls-toggle input {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}

/* The pill background */
.rtls-toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--border-default);   /* grey when off */
  border-radius: 9px;
  transition: background var(--transition-fast);
}

/* The white circle knob */
.rtls-toggle-slider::after {
  content: '';
  position: absolute;
  width: 12px;
  height: 12px;
  left: 3px;
  top: 3px;
  background: #fff;
  border-radius: 50%;
  transition: transform var(--transition-fast);
}

/* Checked state: pill turns accent blue */
.rtls-toggle input:checked + .rtls-toggle-slider {
  background: var(--accent-primary);
}

/* Checked state: knob slides 16px to the right */
.rtls-toggle input:checked + .rtls-toggle-slider::after {
  transform: translateX(16px);
}
```

### 3.3 Range Slider

```css
/* Track */
.rtls-range {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 3px;
  border-radius: 0;
  background: var(--border-default);
  outline: none;
  cursor: pointer;
}

/* Thumb — WebKit */
.rtls-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 0;              /* square thumb for a technical/instrument look */
  background: var(--text-secondary);
  border: 1px solid var(--bg-primary);
  cursor: pointer;
  transition: background var(--transition-fast);
}
.rtls-range::-webkit-slider-thumb:hover { background: var(--text-primary); }

/* Thumb — Firefox */
.rtls-range::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border-radius: 0;
  background: var(--text-secondary);
  border: 1px solid var(--bg-primary);
  cursor: pointer;
}
```

---

## PART 4 — BACKEND

---

### 4.1 Sprite Asset Endpoint (`cad_server.py`)

```python
import pathlib as _pathlib

# Resolve path relative to this file: cad_server.py is in BRIGID/backend/
# so parent.parent = BRIGID/, then assets/Walking animation/
_WALK_ANIM_DIR = _pathlib.Path(__file__).parent.parent / "assets" / "Walking animation"


@app.get("/assets/walk/{filename}")
async def get_walk_asset(filename: str):
    from fastapi.responses import FileResponse
    from fastapi import HTTPException

    # Strip any path traversal attempts (e.g. "../../etc/passwd")
    # pathlib.Path(filename).name returns only the final filename component
    safe = _pathlib.Path(filename).name

    fp = _WALK_ANIM_DIR / safe
    if not fp.exists():
        raise HTTPException(status_code=404, detail=f"Asset not found: {safe}")

    return FileResponse(str(fp))
```

**Why:** The route is `GET /assets/walk/{filename}` rather than a generic static files mount so
it is explicit and limited in scope — only files directly in the `Walking animation/` folder are
accessible.  `pathlib.Path(filename).name` is the security guard: it discards everything before
the final `/`, so `../../secret.txt` becomes `secret.txt` which then fails the `.exists()` check
because that file is not in the walking animation folder.

---

### 4.2 Room Polygon in `room_data.py`

```python
# In Room.to_dict():
def to_dict(self) -> dict:
    return {
        # ... other fields ...
        "room_polygon_ft": [
            {"x": round(lx + self.min_x, 3), "y": round(ly + self.min_y, 3)}
            for lx, ly in self._local_polygon   # local coords → world coords
        ],
    }
```

**Why:** The `_local_polygon` is built from room boundary segments using `chain_segments_to_polygon`
(a pure Python chaining algorithm, no PyQt6 dependency).  It stores vertices in local (room-relative)
coordinates.  Adding `self.min_x` / `self.min_y` converts to world coordinates, which is what the
canvas expects — all entity positions (tags, bots) are in world feet.

---

### 4.3 Room Polygon in `rtls_runtime.py`

```python
# In RTLSRuntime.__init__:
self._room_polygon_ft: list[dict] = []   # list of {"x": float, "y": float}

# In RTLSRuntime.update_from_workspace():
if room_data:
    self._segments        = room_data.get("segments_ft", [])
    self._room_bounds     = room_data.get("room_bounds_ft", {})
    self._room_name       = room_data.get("room_name", "")
    self._room_polygon_ft = room_data.get("room_polygon_ft", [])   # stored verbatim

# In RTLSRuntime.snapshot():
def snapshot(self) -> dict:
    with self._lock:
        return {
            # ... other fields ...
            "room_polygon_ft": list(self._room_polygon_ft),   # copy to avoid mutation
        }
```

**Why:** The polygon is stored as a plain Python list of dicts — no custom objects, no
serialisation step required.  `list(self._room_polygon_ft)` creates a shallow copy so external
code can't accidentally mutate the runtime's polygon.  The frontend polls `GET /api/rtls/snapshot`
every 80 ms and receives this in the response, then passes it as `roomPolygon` to the canvas.

---

## PART 5 — DATA FLOW SUMMARY

```
room_data.py
  Room.to_dict()
    └─ "room_polygon_ft": [{x, y}, ...]   ← world-ft vertices, chained from wall segments

rtls_runtime.py
  update_from_workspace(room_data)
    └─ self._room_polygon_ft = room_data["room_polygon_ft"]

  snapshot()
    └─ returns {"room_polygon_ft": [...], ...}

cad_server.py
  GET /api/rtls/snapshot
    └─ returns snapshot() dict as JSON

RTLSDashboard.tsx
  poll() every 80ms
    └─ setSnap(data)                       ← snap.room_polygon_ft updated

  <RTLSDashboardCanvas roomPolygon={snap.room_polygon_ft} ... />

RTLSDashboardCanvas.tsx
  propsRef.current.roomPolygon           ← always current in rAF loop
  initHeatGrid()  → builds heatMaskRef   ← O(w×h) mask build, only on room load
  stepBot()       → pointInPolygon()     ← confinement check every frame per bot
  drawFrame()     → ctx.clip()           ← rendering confinement

Walking sprites:
  cad_server.py   GET /assets/walk/*.png
    └─ FileResponse from BRIGID/assets/Walking animation/

  RTLSDashboardCanvas.tsx
    fetch() → blob → URL.createObjectURL() → img.src = blobUrl
    spritesRef.current.stand / .left / .right
    drawFrame() → ctx.drawImage(sprite, ...) with ctx.rotate(-bot.angle)
```
