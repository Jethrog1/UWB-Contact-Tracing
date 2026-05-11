import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { AnchorData, RoomData } from '../../../types'

export interface AnchorPreviewCanvasHandle {
  resetView: () => void
  zoomIn: () => void
  zoomOut: () => void
}

interface Props {
  room: RoomData
  selectedAnchorId: string | null
  onAnchorSelect: (anchorId: string | null) => void
  onEdgeDraw: (a1: string, a2: string) => void
  onEdgeDelete: (a1: string, a2: string) => void
}

interface Viewport {
  offsetX: number
  offsetY: number
  scale: number
}

const COLORS = {
  bg: 'transparent',
  grid: 'rgba(255, 255, 255, 0.04)',
  anchor: '#4a9eff',
  anchorActive: '#ffd700',
  anchorSelectStroke: 'rgba(255, 215, 0, 0.14)',
  textLabel: '#ffffff',
  line: 'rgba(255, 255, 255, 0.35)',
  lineActive: '#ef4444',
  previewLine: 'rgba(74, 158, 255, 0.65)',
}

const worldToScreen = (viewport: Viewport, x: number, y: number): [number, number] => (
  [viewport.offsetX + x * viewport.scale, viewport.offsetY - y * viewport.scale]
)

const screenToWorld = (viewport: Viewport, sx: number, sy: number): [number, number] => (
  [(sx - viewport.offsetX) / viewport.scale, (viewport.offsetY - sy) / viewport.scale]
)

const distPointToSegScreen = (
  px: number, py: number,
  x1: number, y1: number,
  x2: number, y2: number
): number => {
  const dx = x2 - x1
  const dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-8) return Math.hypot(px - x1, py - y1)
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}

const AnchorPreviewCanvas = forwardRef<AnchorPreviewCanvasHandle, Props>(({
  room,
  selectedAnchorId,
  onAnchorSelect,
  onEdgeDraw,
  onEdgeDelete,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [viewport, setViewport] = useState<Viewport>({ offsetX: 0, offsetY: 0, scale: 20 })
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 })

  const [hoverAnchor, setHoverAnchor] = useState<string | null>(null)
  const [hoverEdge, setHoverEdge] = useState<[string, string] | null>(null)
  const [selectedEdge, setSelectedEdge] = useState<[string, string] | null>(null)
  const panRef = useRef<{ active: boolean; x: number; y: number } | null>(null)
  const drawEdgeRef = useRef<{ startId: string; px: number; py: number } | null>(null)

  const anchors = room.anchors
  const edges = room.edges ?? []

  const resetView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || anchors.length === 0) return
    const xs = anchors.map(a => a.x_ft)
    const ys = anchors.map(a => a.y_ft)

    const minX = Math.min(...xs, 0)
    const maxX = Math.max(...xs, 1)
    const minY = Math.min(...ys, 0)
    const maxY = Math.max(...ys, 1)

    const span = Math.max(maxX - minX, maxY - minY, 1)
    const paddingX = 40
    const paddingY = 40
    const availW = canvas.width - paddingX * 2
    const availH = canvas.height - paddingY * 2

    const scale = Math.min(availW, availH) / span
    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2

    setViewport({
      scale,
      offsetX: canvas.width / 2 - centerX * scale,
      offsetY: canvas.height / 2 + centerY * scale,
    })
  }, [anchors])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const resize = () => {
      const nextWidth = canvas.offsetWidth
      const nextHeight = canvas.offsetHeight
      if (nextWidth > 0 && nextHeight > 0) {
        if (canvas.width !== nextWidth) {
          canvas.width = nextWidth
          canvas.height = nextHeight
          setCanvasSize({ width: nextWidth, height: nextHeight })
          resetView()
        }
      }
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    requestAnimationFrame(resize)
    return () => observer.disconnect()
  }, [resetView])

  useImperativeHandle(ref, () => ({
    resetView,
    zoomIn: () => setViewport(v => ({ ...v, scale: Math.min(v.scale * 1.25, 200) })),
    zoomOut: () => setViewport(v => ({ ...v, scale: Math.max(v.scale / 1.25, 2) })),
  }), [resetView])

  const hitTestAnchor = useCallback((mx: number, my: number) => {
    for (const anchor of anchors) {
      const [sx, sy] = worldToScreen(viewport, anchor.x_ft, anchor.y_ft)
      if (Math.hypot(mx - sx, my - sy) <= 12) return anchor.id
    }
    return null
  }, [anchors, viewport])

  const hitTestEdge = useCallback((mx: number, my: number) => {
    let bestDist = 6
    let bestHit: [string, string] | null = null

    for (const edge of edges) {
      const a1 = anchors.find(a => a.id === edge[0])
      const a2 = anchors.find(a => a.id === edge[1])
      if (!a1 || !a2) continue
      const [x1, y1] = worldToScreen(viewport, a1.x_ft, a1.y_ft)
      const [x2, y2] = worldToScreen(viewport, a2.x_ft, a2.y_ft)
      const dist = distPointToSegScreen(mx, my, x1, y1, x2, y2)
      if (dist < bestDist) {
        bestDist = dist
        bestHit = edge
      }
    }
    return bestHit
  }, [anchors, edges, viewport])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    if (canvasSize.width <= 0 || canvasSize.height <= 0) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)

    const worldLeft = screenToWorld(viewport, 0, canvas.height)[0]
    const worldRight = screenToWorld(viewport, canvas.width, 0)[0]
    const worldBottom = screenToWorld(viewport, 0, canvas.height)[1]
    const worldTop = screenToWorld(viewport, 0, 0)[1]
    const baseGrid = viewport.scale > 50 ? 1 : viewport.scale > 15 ? 2.5 : 10

    ctx.strokeStyle = COLORS.grid
    ctx.lineWidth = 1
    for (let x = Math.floor(worldLeft / baseGrid) * baseGrid; x <= worldRight + baseGrid; x += baseGrid) {
      const [screenX] = worldToScreen(viewport, x, 0)
      ctx.beginPath(); ctx.moveTo(screenX, 0); ctx.lineTo(screenX, canvas.height); ctx.stroke()
    }
    for (let y = Math.floor(worldBottom / baseGrid) * baseGrid; y <= worldTop + baseGrid; y += baseGrid) {
      const [, screenY] = worldToScreen(viewport, 0, y)
      ctx.beginPath(); ctx.moveTo(0, screenY); ctx.lineTo(canvas.width, screenY); ctx.stroke()
    }

    for (const [a1Id, a2Id] of edges) {
      const a1 = anchors.find(a => a.id === a1Id)
      const a2 = anchors.find(a => a.id === a2Id)
      if (!a1 || !a2) continue

      const isSelected = selectedEdge?.[0] === a1Id && selectedEdge?.[1] === a2Id
      const isHover = hoverEdge?.[0] === a1Id && hoverEdge?.[1] === a2Id

      const [sx1, sy1] = worldToScreen(viewport, a1.x_ft, a1.y_ft)
      const [sx2, sy2] = worldToScreen(viewport, a2.x_ft, a2.y_ft)

      ctx.strokeStyle = isSelected ? COLORS.lineActive : isHover ? '#ffffff' : COLORS.line
      ctx.lineWidth = isSelected ? 3 : isHover ? 2.5 : 1.5
      ctx.setLineDash(isSelected ? [] : [4, 4])
      ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(sx2, sy2); ctx.stroke()

      const dist = Math.hypot(a2.x_ft - a1.x_ft, a2.y_ft - a1.y_ft)
      const mx = (sx1 + sx2) / 2
      const my = (sy1 + sy2) / 2
      const angle = Math.atan2(sy2 - sy1, sx2 - sx1)

      ctx.save()
      ctx.setLineDash([])
      ctx.translate(mx, my)
      const normAngle = ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)
      const flipped = normAngle > Math.PI / 2 && normAngle < Math.PI * 1.5
      ctx.rotate(flipped ? angle + Math.PI : angle)
      ctx.font = '10px var(--font-primary, sans-serif)'
      ctx.textAlign = 'center'

      const label = `${dist.toFixed(1)} ft`
      const metrics = ctx.measureText(label)
      ctx.fillStyle = 'rgba(18, 20, 24, 0.95)'
      ctx.fillRect(-metrics.width / 2 - 4, -8, metrics.width + 8, 16)
      ctx.fillStyle = isSelected ? COLORS.lineActive : COLORS.textLabel
      ctx.fillText(label, 0, 4)
      ctx.restore()
    }

    const drawState = drawEdgeRef.current
    if (drawState) {
      const aStart = anchors.find(a => a.id === drawState.startId)
      if (aStart) {
        const [sx1, sy1] = worldToScreen(viewport, aStart.x_ft, aStart.y_ft)
        ctx.strokeStyle = COLORS.previewLine
        ctx.lineWidth = 1.5
        ctx.setLineDash([4, 4])
        ctx.beginPath(); ctx.moveTo(sx1, sy1); ctx.lineTo(drawState.px, drawState.py); ctx.stroke()
      }
    }
    ctx.setLineDash([])

    for (const anchor of anchors) {
      const [sx, sy] = worldToScreen(viewport, anchor.x_ft, anchor.y_ft)
      const isActive = anchor.id === selectedAnchorId || hoverAnchor === anchor.id
      ctx.fillStyle = isActive ? COLORS.anchorActive : COLORS.anchor
      ctx.beginPath(); ctx.arc(sx, sy, 6, 0, Math.PI * 2); ctx.fill()

      if (isActive) {
        ctx.strokeStyle = COLORS.anchorSelectStroke
        ctx.lineWidth = 4
        ctx.stroke()
      }

      ctx.fillStyle = COLORS.textLabel
      ctx.font = '10px var(--font-primary, sans-serif)'
      ctx.textAlign = 'center'
      ctx.fillText(anchor.id, sx, sy - 12)
    }

  }, [
    anchors, edges, canvasSize, viewport, selectedAnchorId,
    hoverAnchor, hoverEdge, selectedEdge, drawEdgeRef.current?.px, drawEdgeRef.current?.py
  ])

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    e.currentTarget.focus()
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    if (e.button === 1 || e.shiftKey) {
      panRef.current = { active: true, x: e.clientX, y: e.clientY }
      return
    }

    const anchorId = hitTestAnchor(mx, my)
    if (anchorId) {
      setSelectedEdge(null)
      onAnchorSelect(anchorId)
      drawEdgeRef.current = { startId: anchorId, px: mx, py: my }
      return
    }

    const edgeHit = hitTestEdge(mx, my)
    if (edgeHit) {
      setSelectedEdge(edgeHit)
      onAnchorSelect(null)
      return
    }

    setSelectedEdge(null)
    onAnchorSelect(null)
    panRef.current = { active: true, x: e.clientX, y: e.clientY }
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    if (panRef.current?.active) {
      const dx = e.clientX - panRef.current.x
      const dy = e.clientY - panRef.current.y
      panRef.current = { ...panRef.current, x: e.clientX, y: e.clientY }
      setViewport(v => ({ ...v, offsetX: v.offsetX + dx, offsetY: v.offsetY + dy }))
      return
    }

    if (drawEdgeRef.current) {
      drawEdgeRef.current.px = mx
      drawEdgeRef.current.py = my
      setHoverAnchor(hitTestAnchor(mx, my))
      return
    }

    setHoverAnchor(hitTestAnchor(mx, my))
    setHoverEdge(hitTestEdge(mx, my))
  }

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    panRef.current = null
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    if (drawEdgeRef.current) {
      const targetAnchor = hitTestAnchor(mx, my)
      if (targetAnchor && targetAnchor !== drawEdgeRef.current.startId) {
        onEdgeDraw(drawEdgeRef.current.startId, targetAnchor)
      }
      drawEdgeRef.current = null
    }
  }

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    e.stopPropagation()
    const rect = e.currentTarget.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15

    setViewport(v => {
      const nextScale = Math.max(2, Math.min(240, v.scale * factor))
      return {
        scale: nextScale,
        offsetX: mx - (mx - v.offsetX) * (nextScale / v.scale),
        offsetY: my - (my - v.offsetY) * (nextScale / v.scale),
      }
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLCanvasElement>) => {
    if ((e.key === 'Delete' || e.key === 'Backspace') && selectedEdge) {
      onEdgeDelete(selectedEdge[0], selectedEdge[1])
      setSelectedEdge(null)
      e.preventDefault()
    }
    if (e.key === 'f' || e.key === 'F') {
      resetView()
      e.preventDefault()
    }
    if (e.key === 'Escape') {
      drawEdgeRef.current = null
      panRef.current = null
      setSelectedEdge(null)
      e.preventDefault()
    }
  }

  useEffect(() => {
    const el = canvasRef.current
    if (!el) return
    const nativeWheel = (e: WheelEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const rect = el.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
      setViewport(v => {
        const nextScale = Math.max(2, Math.min(240, v.scale * factor))
        return {
          scale: nextScale,
          offsetX: mx - (mx - v.offsetX) * (nextScale / v.scale),
          offsetY: my - (my - v.offsetY) * (nextScale / v.scale),
        }
      })
    }
    el.addEventListener('wheel', nativeWheel, { passive: false })
    return () => el.removeEventListener('wheel', nativeWheel)
  }, [])

  return (
    <canvas
      ref={canvasRef}
      tabIndex={0}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onKeyDown={handleKeyDown}
      style={{
        width: '100%',
        height: '240px',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-sm)',
        background: 'transparent',
        cursor: drawEdgeRef.current ? 'crosshair' : panRef.current?.active ? 'grabbing' : hoverAnchor || hoverEdge ? 'pointer' : 'grab',
        outline: 'none',
      }}
    />
  )
})

AnchorPreviewCanvas.displayName = 'AnchorPreviewCanvas'
export default AnchorPreviewCanvas
