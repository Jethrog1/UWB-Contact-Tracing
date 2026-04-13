import React, { useCallback, useEffect, useRef } from 'react'
import { CADCommand, CADRenderPrimitive, CADState } from './types'
import './CADCanvas.css'

interface Props {
  state: CADState | null
  onCommand: (cmd: CADCommand) => void
}

function fontToCss(font: unknown): string {
  if (Array.isArray(font)) {
    const [family = 'sans-serif', size = 12, weight = 'normal'] = font
    return `${weight} ${size}px "${family}", sans-serif`
  }
  if (typeof font === 'string') {
    return font
  }
  return '12px "JetBrains Mono", monospace'
}

function drawPrimitive(ctx: CanvasRenderingContext2D, primitive: CADRenderPrimitive) {
  const { kind, points, options } = primitive
  const fill = options.fill ?? null
  const stroke = options.outline ?? options.stroke ?? options.fill ?? null
  const lineWidth = Number(options.width ?? 1)
  const dash = Array.isArray(options.dash) ? options.dash.map(Number) : []

  ctx.setLineDash(dash)
  ctx.lineWidth = lineWidth

  if (kind === 'line') {
    if (points.length < 4) return
    ctx.beginPath()
    ctx.moveTo(points[0], points[1])
    for (let i = 2; i < points.length; i += 2) {
      ctx.lineTo(points[i], points[i + 1])
    }
    if (stroke) {
      ctx.strokeStyle = String(stroke)
      ctx.stroke()
    }
    return
  }

  if (kind === 'oval') {
    if (points.length !== 4) return
    const [x1, y1, x2, y2] = points
    const cx = (x1 + x2) / 2
    const cy = (y1 + y2) / 2
    const rx = Math.abs(x2 - x1) / 2
    const ry = Math.abs(y2 - y1) / 2
    ctx.beginPath()
    ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2)
    if (fill && fill !== '') {
      ctx.fillStyle = String(fill)
      ctx.fill()
    }
    if (stroke && stroke !== '') {
      ctx.strokeStyle = String(stroke)
      ctx.stroke()
    }
    return
  }

  if (kind === 'rect') {
    if (points.length !== 4) return
    const [x1, y1, x2, y2] = points
    const width = x2 - x1
    const height = y2 - y1
    if (fill && fill !== '') {
      ctx.fillStyle = String(fill)
      ctx.fillRect(x1, y1, width, height)
    }
    if (stroke && stroke !== '') {
      ctx.strokeStyle = String(stroke)
      ctx.strokeRect(x1, y1, width, height)
    }
    return
  }

  if (kind === 'polygon') {
    if (points.length < 4) return
    ctx.beginPath()
    ctx.moveTo(points[0], points[1])
    for (let i = 2; i < points.length; i += 2) {
      ctx.lineTo(points[i], points[i + 1])
    }
    ctx.closePath()
    if (fill && fill !== '') {
      ctx.fillStyle = String(fill)
      ctx.fill()
    }
    if (stroke && stroke !== '') {
      ctx.strokeStyle = String(stroke)
      ctx.stroke()
    }
    return
  }

  if (kind === 'text') {
    if (points.length < 2) return
    const [x, y] = points
    ctx.save()
    ctx.font = fontToCss(options.font)
    ctx.fillStyle = String(fill ?? '#cbd5e1')
    ctx.textAlign = options.anchor === 'w' ? 'left' : 'center'
    ctx.textBaseline = 'middle'
    const angle = Number(options.angle ?? 0)
    ctx.translate(x, y)
    if (angle) {
      ctx.rotate((angle * Math.PI) / 180)
    }
    ctx.fillText(String(options.text ?? ''), 0, 0)
    ctx.restore()
  }
}

const CADCanvas: React.FC<Props> = ({ state, onCommand }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const w = canvas.width / dpr
    const h = canvas.height / dpr

    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.scale(dpr, dpr)
    ctx.fillStyle = '#080d18'
    ctx.fillRect(0, 0, w, h)

    if (!state) return

    for (const primitive of state.render_primitives ?? []) {
      drawPrimitive(ctx, primitive)
      ctx.setLineDash([])
    }
  }, [state])

  useEffect(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return

    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        const dpr = window.devicePixelRatio || 1
        canvas.width = Math.round(width * dpr)
        canvas.height = Math.round(height * dpr)
        canvas.style.width = `${width}px`
        canvas.style.height = `${height}px`
        onCommand({ type: 'viewport_resize', width: Math.round(width), height: Math.round(height) })
      }
    })

    ro.observe(container)
    return () => ro.disconnect()
  }, [onCommand])

  const getXY = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect()
    return { x: e.clientX - rect.left, y: e.clientY - rect.top }
  }

  const onMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    canvasRef.current?.focus()
    const { x, y } = getXY(e)
    if (e.button === 2 && !e.shiftKey) {
      onCommand({ type: 'right_click', x, y })
      return
    }
    onCommand({
      type: 'mouse_down',
      x,
      y,
      button: e.button,
      ctrl: e.ctrlKey,
      shift: e.shiftKey,
      buttons: e.buttons,
    })
  }, [onCommand])

  const onMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getXY(e)
    onCommand({
      type: 'mouse_move',
      x,
      y,
      ctrl: e.ctrlKey,
      shift: e.shiftKey,
      buttons: e.buttons,
    })
  }, [onCommand])

  const onMouseUp = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getXY(e)
    onCommand({
      type: 'mouse_up',
      x,
      y,
      button: e.button,
      ctrl: e.ctrlKey,
      shift: e.shiftKey,
      buttons: e.buttons,
    })
  }, [onCommand])

  const onDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getXY(e)
    onCommand({ type: 'double_click', x, y })
  }, [onCommand])

  const onWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const rect = canvasRef.current!.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    onCommand({ type: 'wheel', x, y, delta: e.deltaY })
  }, [onCommand])

  const onKeyDown = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    const key = e.key
    const lower = key.toLowerCase()

    if (e.ctrlKey && e.shiftKey && lower === 'z') {
      e.preventDefault()
      onCommand({ type: 'redo' })
      return
    }
    if (e.ctrlKey && lower === 'z') {
      e.preventDefault()
      onCommand({ type: 'undo' })
      return
    }
    if (e.ctrlKey && lower === 'y') {
      e.preventDefault()
      onCommand({ type: 'redo' })
      return
    }
    if (e.ctrlKey && lower === 'c') {
      e.preventDefault()
      onCommand({ type: 'copy' })
      return
    }
    if (e.ctrlKey && lower === 'v') {
      e.preventDefault()
      onCommand({ type: 'paste' })
      return
    }
    if (key === 'Delete' || key === 'Backspace') {
      e.preventDefault()
      onCommand({ type: 'delete' })
      return
    }
    if (key === 'Escape') {
      e.preventDefault()
      onCommand({ type: 'escape' })
      return
    }

    onCommand({ type: 'key_press', key, ctrl: e.ctrlKey, shift: e.shiftKey })
  }, [onCommand])

  const onMouseLeave = useCallback(() => {
    onCommand({ type: 'mouse_leave' })
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
        onMouseLeave={onMouseLeave}
        onDoubleClick={onDoubleClick}
        onWheel={onWheel}
        onKeyDown={onKeyDown}
        onContextMenu={onContextMenu}
      />
    </div>
  )
}

export default CADCanvas
