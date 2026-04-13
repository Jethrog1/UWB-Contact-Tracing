// ── CAD Canvas — HTML5 renderer ───────────────────────────────────
import React, { useRef, useEffect, useCallback } from 'react'
import { CADState, CADCommand, CADViewport } from './types'
import './CADCanvas.css'

interface Props {
  state: CADState | null
  onCommand: (cmd: CADCommand) => void
}

// ── Coordinate helpers ────────────────────────────────────────────
function w2s(vp: CADViewport, wx: number, wy: number): [number, number] {
  return [wx * vp.scale + vp.offx, wy * vp.scale + vp.offy]
}

function s2w(vp: CADViewport, sx: number, sy: number): [number, number] {
  return [(sx - vp.offx) / vp.scale, (sy - vp.offy) / vp.scale]
}

// ── Drawing helpers ───────────────────────────────────────────────
const GRID_COLOR        = 'rgba(30,45,70,0.7)'
const GRID_MAJOR_COLOR  = 'rgba(40,60,90,0.9)'
const AXIS_COLOR        = 'rgba(56,68,94,0.8)'
const SNAP_COLOR        = '#38bdf8'
const GUIDE_COLOR       = 'rgba(56,189,248,0.35)'
const TEMP_LINE_COLOR   = 'rgba(56,189,248,0.6)'
const DIM_COLOR         = '#94a3b8'
const DIM_LABEL_COLOR   = '#cbd5e1'

function drawGrid(ctx: CanvasRenderingContext2D, vp: CADViewport, w: number, h: number) {
  const step = vp.scale >= 40 ? 1 : vp.scale >= 8 ? 5 : 25
  const [wxMin] = s2w(vp, 0, 0)
  const [wxMax] = s2w(vp, w, 0)
  const [, wyMin] = s2w(vp, 0, 0)
  const [, wyMax] = s2w(vp, 0, h)

  const startX = Math.floor(wxMin / step) * step
  const startY = Math.floor(wyMin / step) * step

  ctx.lineWidth = 0.5
  for (let wx = startX; wx <= wxMax; wx += step) {
    const isMajor = wx % (step * 5) === 0
    ctx.strokeStyle = isMajor ? GRID_MAJOR_COLOR : GRID_COLOR
    const [sx] = w2s(vp, wx, 0)
    ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, h); ctx.stroke()
  }
  for (let wy = startY; wy <= wyMax; wy += step) {
    const isMajor = wy % (step * 5) === 0
    ctx.strokeStyle = isMajor ? GRID_MAJOR_COLOR : GRID_COLOR
    const [, sy] = w2s(vp, 0, wy)
    ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(w, sy); ctx.stroke()
  }

  // Axes
  ctx.strokeStyle = AXIS_COLOR
  ctx.lineWidth = 1
  const [ox, oy] = w2s(vp, 0, 0)
  ctx.beginPath(); ctx.moveTo(ox, 0); ctx.lineTo(ox, h); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(0, oy); ctx.lineTo(w, oy); ctx.stroke()
}

function drawLines(ctx: CanvasRenderingContext2D, state: CADState) {
  const { vp, lines, selected_id, multi_selected_ids, hovered_id } = state

  for (const ln of lines) {
    const isSelected = ln.id === selected_id || multi_selected_ids.includes(ln.id)
    const isHovered  = ln.id === hovered_id

    const [x1, y1] = w2s(vp, ln.x1, ln.y1)
    const [x2, y2] = w2s(vp, ln.x2, ln.y2)

    ctx.beginPath()
    ctx.moveTo(x1, y1)
    ctx.lineTo(x2, y2)

    if (isSelected) {
      ctx.strokeStyle = '#38bdf8'
      ctx.lineWidth = 2.5
      ctx.shadowColor = 'rgba(56,189,248,0.4)'
      ctx.shadowBlur = 6
    } else if (isHovered) {
      ctx.strokeStyle = '#7dd3fc'
      ctx.lineWidth = 2
      ctx.shadowBlur = 0
    } else {
      ctx.strokeStyle = ln.color || '#8a9ab8'
      ctx.lineWidth = 1.5
      ctx.shadowBlur = 0
    }
    ctx.stroke()
    ctx.shadowBlur = 0

    // Endpoint dots for selected
    if (isSelected || isHovered) {
      const r = isSelected ? 4 : 3
      for (const [ex, ey] of [[x1, y1], [x2, y2]] as [number, number][]) {
        ctx.beginPath()
        ctx.arc(ex, ey, r, 0, Math.PI * 2)
        ctx.fillStyle = isSelected ? '#38bdf8' : '#7dd3fc'
        ctx.fill()
      }
    }
  }
}

function drawTempLine(ctx: CanvasRenderingContext2D, state: CADState) {
  if (!state.drawing_line || !state.temp_line_start) return
  const { vp, temp_line_start, cursor_world_snapped } = state
  const [x1, y1] = w2s(vp, temp_line_start[0], temp_line_start[1])
  const [x2, y2] = w2s(vp, cursor_world_snapped[0], cursor_world_snapped[1])

  ctx.beginPath()
  ctx.moveTo(x1, y1)
  ctx.lineTo(x2, y2)
  ctx.strokeStyle = TEMP_LINE_COLOR
  ctx.lineWidth = 1.5
  ctx.setLineDash([6, 4])
  ctx.stroke()
  ctx.setLineDash([])
}

function drawAlignmentGuides(ctx: CanvasRenderingContext2D, state: CADState) {
  const { vp, alignment_guides } = state
  ctx.strokeStyle = GUIDE_COLOR
  ctx.lineWidth = 1
  ctx.setLineDash([4, 6])
  for (const g of alignment_guides) {
    const [x1, y1] = w2s(vp, g.x1, g.y1)
    const [x2, y2] = w2s(vp, g.x2, g.y2)
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
  }
  ctx.setLineDash([])
}

function drawSnapHint(ctx: CanvasRenderingContext2D, state: CADState) {
  if (!state.snap_hint) return
  const { vp, snap_hint } = state
  const [sx, sy] = w2s(vp, snap_hint.x, snap_hint.y)

  if (snap_hint.kind === 'endpoint') {
    ctx.beginPath()
    ctx.arc(sx, sy, 7, 0, Math.PI * 2)
    ctx.strokeStyle = SNAP_COLOR
    ctx.lineWidth = 1.5
    ctx.stroke()
  } else {
    // Line snap — small X
    ctx.strokeStyle = SNAP_COLOR
    ctx.lineWidth = 1.5
    const d = 5
    ctx.beginPath(); ctx.moveTo(sx - d, sy - d); ctx.lineTo(sx + d, sy + d); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(sx + d, sy - d); ctx.lineTo(sx - d, sy + d); ctx.stroke()
  }
}

function drawFixedLengthLabels(ctx: CanvasRenderingContext2D, state: CADState) {
  const { vp, lines, fixed_lengths } = state
  ctx.font = '11px "JetBrains Mono", monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'

  for (const [id, meta] of Object.entries(fixed_lengths)) {
    const ln = lines.find(l => l.id === id)
    if (!ln || !meta.label) continue
    const [lx, ly] = w2s(vp, meta.label[0], meta.label[1])
    ctx.fillStyle = 'rgba(10,14,23,0.7)'
    const text = `${meta.len.toFixed(2)}`
    const tm = ctx.measureText(text)
    ctx.fillRect(lx - tm.width / 2 - 4, ly - 8, tm.width + 8, 16)
    ctx.fillStyle = DIM_LABEL_COLOR
    ctx.fillText(text, lx, ly)
  }
}

function drawDistanceConstraints(ctx: CanvasRenderingContext2D, state: CADState) {
  const { vp, distance_constraints } = state
  ctx.font = '11px "JetBrains Mono", monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.strokeStyle = DIM_COLOR
  ctx.lineWidth = 1

  for (const dc of distance_constraints) {
    if (!dc.Pa || !dc.Pb) continue
    const [ax, ay] = w2s(vp, dc.Pa[0], dc.Pa[1])
    const [bx, by] = w2s(vp, dc.Pb[0], dc.Pb[1])

    // Extension lines
    ctx.setLineDash([3, 4])
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()
    ctx.setLineDash([])

    if (dc.label) {
      const [lx, ly] = w2s(vp, dc.label[0], dc.label[1])
      const text = `${dc.dist.toFixed(2)}`
      const tm = ctx.measureText(text)
      ctx.fillStyle = 'rgba(10,14,23,0.7)'
      ctx.fillRect(lx - tm.width / 2 - 4, ly - 8, tm.width + 8, 16)
      ctx.fillStyle = DIM_LABEL_COLOR
      ctx.fillText(text, lx, ly)
    }
  }
}

function drawAngleConstraints(ctx: CanvasRenderingContext2D, state: CADState) {
  const { vp, angle_constraints } = state
  ctx.font = '11px "JetBrains Mono", monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'

  for (const ac of angle_constraints) {
    const [vx, vy] = w2s(vp, ac.vx, ac.vy)
    const r = 24
    const baseAngle = Math.atan2(-ac.vy, ac.vx) // rough — backend provides full arc data
    ctx.beginPath()
    ctx.arc(vx, vy, r, baseAngle, baseAngle + (ac.deg * Math.PI / 180) * ac.side)
    ctx.strokeStyle = DIM_COLOR
    ctx.lineWidth = 1
    ctx.stroke()

    // Label offset
    const midAngle = baseAngle + (ac.deg * Math.PI / 180) * ac.side / 2
    const lx = vx + (r + 14) * Math.cos(midAngle)
    const ly = vy + (r + 14) * Math.sin(midAngle)
    const text = `${ac.deg.toFixed(1)}°`
    const tm = ctx.measureText(text)
    ctx.fillStyle = 'rgba(10,14,23,0.7)'
    ctx.fillRect(lx - tm.width / 2 - 3, ly - 7, tm.width + 6, 14)
    ctx.fillStyle = DIM_LABEL_COLOR
    ctx.fillText(text, lx, ly)
  }
}

function drawVertexHover(ctx: CanvasRenderingContext2D, state: CADState) {
  if (!state.vertex_hover) return
  const [wx, wy] = state.vertex_hover
  const [sx, sy] = w2s(state.vp, wx, wy)
  ctx.beginPath()
  ctx.arc(sx, sy, 6, 0, Math.PI * 2)
  ctx.strokeStyle = '#f59e0b'
  ctx.lineWidth = 2
  ctx.stroke()
}

function drawCursor(ctx: CanvasRenderingContext2D, state: CADState, w: number, h: number) {
  if (state.tool_mode === 'cursor') return
  const [sx, sy] = w2s(state.vp, state.cursor_world_snapped[0], state.cursor_world_snapped[1])
  if (sx < 0 || sy < 0 || sx > w || sy > h) return

  ctx.strokeStyle = 'rgba(56,189,248,0.5)'
  ctx.lineWidth = 0.5
  ctx.setLineDash([4, 4])
  ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, h); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(w, sy); ctx.stroke()
  ctx.setLineDash([])

  ctx.beginPath()
  ctx.arc(sx, sy, 3, 0, Math.PI * 2)
  ctx.fillStyle = '#38bdf8'
  ctx.fill()
}

// ── Component ─────────────────────────────────────────────────────
const CADCanvas: React.FC<Props> = ({ state, onCommand }) => {
  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // ── Render ───────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const w = canvas.width
    const h = canvas.height

    ctx.clearRect(0, 0, w, h)
    ctx.fillStyle = '#080d18'
    ctx.fillRect(0, 0, w, h)

    if (!state) return

    drawGrid(ctx, state.vp, w, h)
    drawAlignmentGuides(ctx, state)
    drawLines(ctx, state)
    drawTempLine(ctx, state)
    drawFixedLengthLabels(ctx, state)
    drawDistanceConstraints(ctx, state)
    drawAngleConstraints(ctx, state)
    drawSnapHint(ctx, state)
    drawVertexHover(ctx, state)
    drawCursor(ctx, state, w, h)
  }, [state])

  // ── Resize observer ──────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current
    const canvas    = canvasRef.current
    if (!container || !canvas) return

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        const dpr = window.devicePixelRatio || 1
        canvas.width  = Math.round(width  * dpr)
        canvas.height = Math.round(height * dpr)
        canvas.style.width  = `${width}px`
        canvas.style.height = `${height}px`
        const ctx = canvas.getContext('2d')
        if (ctx) ctx.scale(dpr, dpr)
        onCommand({ type: 'viewport_resize', width: Math.round(width), height: Math.round(height) })
      }
    })

    ro.observe(container)
    return () => ro.disconnect()
  }, [onCommand])

  // ── Pointer events ───────────────────────────────────────────────
  const getXY = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = canvasRef.current!.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  const onMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    canvasRef.current?.focus()
    const { x, y } = getXY(e)
    if (e.button === 2) {
      onCommand({ type: 'right_click', x, y })
    } else {
      onCommand({ type: 'mouse_down', x, y, button: e.button, ctrl: e.ctrlKey, shift: e.shiftKey })
    }
  }, [onCommand])

  const onMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getXY(e)
    onCommand({ type: 'mouse_move', x, y })
  }, [onCommand])

  const onMouseUp = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getXY(e)
    onCommand({ type: 'mouse_up', x, y, button: e.button })
  }, [onCommand])

  const onDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getXY(e)
    onCommand({ type: 'double_click', x, y })
  }, [onCommand])

  const onWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const { x, y } = getXY(e)
    onCommand({ type: 'wheel', x, y, delta: e.deltaY })
  }, [onCommand])

  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const key = e.key

    // Global shortcuts
    if (e.ctrlKey) {
      if (key === 'z') { onCommand({ type: 'undo' }); return }
      if (key === 'y') { onCommand({ type: 'redo' }); return }
      if (key === 'c') { onCommand({ type: 'copy' }); return }
      if (key === 'v') { onCommand({ type: 'paste' }); return }
    }
    if (key === 'Delete' || key === 'Backspace') { onCommand({ type: 'delete' }); return }
    if (key === 'Escape') { onCommand({ type: 'escape' }); return }

    onCommand({ type: 'key_press', key, ctrl: e.ctrlKey, shift: e.shiftKey })
  }, [onCommand])

  const onContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
  }, [])

  return (
    <div ref={containerRef} className="cad-canvas-container">
      <canvas
        ref={canvasRef}
        className="cad-canvas"
        tabIndex={0}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onDoubleClick={onDoubleClick}
        onWheel={onWheel}
        onKeyDown={onKeyDown}
        onContextMenu={onContextMenu}
      />
    </div>
  )
}

export default CADCanvas
