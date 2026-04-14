import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useRef } from 'react'

// ── Types ──────────────────────────────────────────────────────────────────────

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
  segments: { x1: number; y1: number; x2: number; y2: number }[]
  anchors: Record<string, [number, number]>
  tags: RTLSTagState[]
  roomBounds: { min_x?: number; min_y?: number; max_x?: number; max_y?: number }
  svgContent?: string | null
  referenceAnchorId?: string
  onViewportChange?: (vp: RTLSViewport) => void
}

export interface RTLSDashboardCanvasHandle {
  resetView: () => void
  zoomIn: () => void
  zoomOut: () => void
}

// ── Colour helpers ──────────────────────────────────────────────────────────────

const TAG_PALETTE = [
  '#3a9fe8', '#e67e22', '#9b59b6', '#27ae60',
  '#e74c3c', '#f1c40f', '#1abc9c', '#d16cff',
]

export function tagColor(index: number): string {
  return TAG_PALETTE[index % TAG_PALETTE.length]
}

const ANCHOR_COLORS = ['#e05c5c', '#4ec97e', '#a070e8', '#e8a030', '#40c4e0']

function anchorColor(index: number): string {
  return ANCHOR_COLORS[index % ANCHOR_COLORS.length]
}

// ── Canvas ─────────────────────────────────────────────────────────────────────

const RTLSDashboardCanvas = forwardRef<RTLSDashboardCanvasHandle, RTLSDashboardCanvasProps>(
  ({ segments, anchors, tags, roomBounds, svgContent, referenceAnchorId, onViewportChange }, ref) => {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const vpRef = useRef<RTLSViewport>({ offsetX: 0, offsetY: 0, scale: 20 })
    const dragRef = useRef<{ x: number; y: number } | null>(null)
    const svgImgRef = useRef<HTMLImageElement | null>(null)
    const svgBlobUrlRef = useRef<string | null>(null)

    // ── Load SVG content into an Image for canvas rendering ───────────────
    useEffect(() => {
      if (svgBlobUrlRef.current) {
        URL.revokeObjectURL(svgBlobUrlRef.current)
        svgBlobUrlRef.current = null
      }
      svgImgRef.current = null

      if (!svgContent) return

      const blob = new Blob([svgContent], { type: 'image/svg+xml' })
      const url = URL.createObjectURL(blob)
      svgBlobUrlRef.current = url

      const img = new Image()
      img.onload = () => {
        svgImgRef.current = img
        draw()
      }
      img.src = url

      return () => {
        if (svgBlobUrlRef.current) {
          URL.revokeObjectURL(svgBlobUrlRef.current)
          svgBlobUrlRef.current = null
        }
      }
    }, [svgContent]) // eslint-disable-line react-hooks/exhaustive-deps

    // ── Auto-fit to room bounds ────────────────────────────────────────────
    const resetView = useCallback(() => {
      const canvas = canvasRef.current
      if (!canvas) return
      const cw = canvas.width
      const ch = canvas.height
      const padding = 80

      let minX = -1, minY = -1, maxX = 10, maxY = 10

      if (segments.length > 0) {
        const xs = segments.flatMap(s => [s.x1, s.x2])
        const ys = segments.flatMap(s => [s.y1, s.y2])
        minX = Math.min(...xs); maxX = Math.max(...xs)
        minY = Math.min(...ys); maxY = Math.max(...ys)
      }

      if (roomBounds.min_x !== undefined) {
        minX = roomBounds.min_x
        minY = roomBounds.min_y!
        maxX = roomBounds.max_x!
        maxY = roomBounds.max_y!
      }

      const roomW = maxX - minX
      const roomH = maxY - minY
      if (roomW <= 0 || roomH <= 0) return

      const scaleX = (cw - padding * 2) / roomW
      const scaleY = (ch - padding * 2) / roomH
      const scale = Math.min(scaleX, scaleY)

      const centerX = (minX + maxX) / 2
      const centerY = (minY + maxY) / 2

      vpRef.current = {
        scale,
        offsetX: cw / 2 - centerX * scale,
        offsetY: ch / 2 + centerY * scale,
      }
      draw()
      onViewportChange?.(vpRef.current)
    }, [segments, roomBounds, onViewportChange])

    const zoomIn = useCallback(() => {
      vpRef.current.scale = Math.min(300, vpRef.current.scale * 1.15)
      draw()
    }, [])

    const zoomOut = useCallback(() => {
      vpRef.current.scale = Math.max(1, vpRef.current.scale / 1.15)
      draw()
    }, [])

    useImperativeHandle(ref, () => ({ resetView, zoomIn, zoomOut }))

    // ── Draw ───────────────────────────────────────────────────────────────────
    const draw = useCallback(() => {
      const canvas = canvasRef.current
      if (!canvas) return
      const ctx = canvas.getContext('2d')
      if (!ctx) return

      const vp = vpRef.current
      const { offsetX: ox, offsetY: oy, scale } = vp

      const tx = (x: number) => ox + x * scale
      const ty = (y: number) => oy - y * scale

      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // ── Determine Reference Offset ──
      let refX = 0
      let refY = 0
      if (referenceAnchorId && anchors[referenceAnchorId]) {
        [refX, refY] = anchors[referenceAnchorId]
      }

      // Helper with offset
      const tXoff = (x: number) => tx(x - refX)
      const tYoff = (y: number) => ty(y - refY)

      // ── Floor plan segments ──
      ctx.strokeStyle = 'rgba(140, 180, 230, 0.6)'
      ctx.lineWidth = 1.5
      for (const seg of segments) {
        ctx.beginPath()
        ctx.moveTo(tXoff(seg.x1), tYoff(seg.y1))
        ctx.lineTo(tXoff(seg.x2), tYoff(seg.y2))
        ctx.stroke()
      }

      // ── Anchor-to-anchor connection lines ──
      const anchorIds = Object.keys(anchors)
      if (anchorIds.length >= 2) {
        ctx.strokeStyle = 'rgba(0, 180, 255, 0.2)'
        ctx.lineWidth = 1
        ctx.setLineDash([6, 4])
        for (let i = 0; i < anchorIds.length; i++) {
          const next = (i + 1) % anchorIds.length
          const [x1, y1] = anchors[anchorIds[i]]
          const [x2, y2] = anchors[anchorIds[next]]
          ctx.beginPath()
          ctx.moveTo(tXoff(x1), tYoff(y1))
          ctx.lineTo(tXoff(x2), tYoff(y2))
          ctx.stroke()
        }
        ctx.setLineDash([])
      }

      // ── Anchors ──
      for (let i = 0; i < anchorIds.length; i++) {
        const aid = anchorIds[i]
        const [ax, ay] = anchors[aid]
        const cx = tXoff(ax)
        const cy = tYoff(ay)
        const isRef = aid === referenceAnchorId
        const r = isRef ? 9 : 7
        const color = anchorColor(i)

        // Reference anchor gets a ring
        if (isRef) {
          ctx.beginPath()
          ctx.arc(cx, cy, r + 4, 0, Math.PI * 2)
          ctx.strokeStyle = color
          ctx.lineWidth = 1.5
          ctx.setLineDash([3, 2])
          ctx.stroke()
          ctx.setLineDash([])
        }

        ctx.beginPath()
        ctx.arc(cx, cy, r, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.25)'
        ctx.lineWidth = 1
        ctx.stroke()

        ctx.fillStyle = '#fff'
        ctx.font = `bold ${Math.max(9, Math.min(12, scale * 0.6))}px "SF Mono", monospace`
        ctx.textAlign = 'left'
        ctx.textBaseline = 'bottom'
        const displayAx = ax - refX
        const displayAy = ay - refY
        const label = isRef
          ? `${aid} ★ (0.0, 0.0)`
          : `${aid} (${displayAx.toFixed(1)}, ${displayAy.toFixed(1)})`
        ctx.fillText(label, cx + 10, cy - 4)
      }

      // ── Tag distance label lines (for connected tags) ──
      const connected = tags.filter(t => t.position !== null)
      for (let i = 0; i < connected.length; i++) {
        for (let j = i + 1; j < connected.length; j++) {
          const a = connected[i].position!
          const b = connected[j].position!
          const dist = Math.hypot(b.x - a.x, b.y - a.y)
          const cx1 = tXoff(a.x); const cy1 = tYoff(a.y)
          const cx2 = tXoff(b.x); const cy2 = tYoff(b.y)
          ctx.setLineDash([4, 4])
          ctx.strokeStyle = 'rgba(200, 140, 60, 0.35)'
          ctx.lineWidth = 1
          ctx.beginPath(); ctx.moveTo(cx1, cy1); ctx.lineTo(cx2, cy2); ctx.stroke()
          ctx.setLineDash([])
          ctx.fillStyle = 'rgba(200, 140, 60, 0.7)'
          ctx.font = '9px sans-serif'
          ctx.textAlign = 'center'
          ctx.fillText(`${dist.toFixed(2)} ft`, (cx1 + cx2) / 2, (cy1 + cy2) / 2 - 6)
        }
      }

      // ── Tags ──
      for (const tag of tags) {
        if (!tag.position) continue
        const cx = tXoff(tag.position.x)
        const cy = tYoff(tag.position.y)
        const r = 9

        // Glow
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 2.5)
        grad.addColorStop(0, tag.color + '66')
        grad.addColorStop(1, 'transparent')
        ctx.beginPath()
        ctx.arc(cx, cy, r * 2.5, 0, Math.PI * 2)
        ctx.fillStyle = grad
        ctx.fill()

        // Dot
        ctx.beginPath()
        ctx.arc(cx, cy, r, 0, Math.PI * 2)
        ctx.fillStyle = tag.color
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.4)'
        ctx.lineWidth = 1.5
        ctx.stroke()

        // Label
        ctx.fillStyle = tag.color
        ctx.font = 'bold 11px sans-serif'
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        ctx.fillText(tag.tag_id, cx + 14, cy)

        // Coords
        const displayX = tag.position.x - refX
        const displayY = tag.position.y - refY
        const coordLabel = `(${displayX.toFixed(2)}, ${displayY.toFixed(2)}) ft`
        ctx.fillStyle = 'rgba(200, 220, 255, 0.6)'
        ctx.font = '9px sans-serif'
        ctx.fillText(coordLabel, cx + 14, cy + 12)
      }
    }, [segments, anchors, tags, roomBounds, referenceAnchorId])

    // ── Resize observer ────────────────────────────────────────────────────────
    useEffect(() => {
      const canvas = canvasRef.current
      if (!canvas) return
      const parent = canvas.parentElement
      if (!parent) return

      const observer = new ResizeObserver(() => {
        canvas.width = parent.clientWidth
        canvas.height = parent.clientHeight
        draw()
      })
      observer.observe(parent)
      canvas.width = parent.clientWidth
      canvas.height = parent.clientHeight
      return () => observer.disconnect()
    }, [draw])

    // ── Auto-reset view when segments change ───────────────────────────────────
    useEffect(() => {
      if (segments.length > 0 || Object.keys(anchors).length > 0) {
        resetView()
      }
    }, [segments.length, Object.keys(anchors).length]) // eslint-disable-line react-hooks/exhaustive-deps

    // ── Redraw when tags move ──────────────────────────────────────────────────
    useEffect(() => { draw() }, [draw])

    // ── Mouse handlers ─────────────────────────────────────────────────────────
    const onMouseDown = (e: React.MouseEvent) => {
      dragRef.current = { x: e.clientX, y: e.clientY }
    }

    const onMouseMove = (e: React.MouseEvent) => {
      if (!dragRef.current) return
      const dx = e.clientX - dragRef.current.x
      const dy = e.clientY - dragRef.current.y
      dragRef.current = { x: e.clientX, y: e.clientY }
      vpRef.current.offsetX += dx
      vpRef.current.offsetY += dy
      draw()
    }

    const onMouseUp = () => { dragRef.current = null }

    const onWheel = useCallback((e: WheelEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const mouseY = e.clientY - rect.top
      const { scale, offsetX, offsetY } = vpRef.current
      const worldX = (mouseX - offsetX) / scale
      const worldY = (offsetY - mouseY) / scale
      const factor = e.deltaY < 0 ? 1.1 : 0.9
      const newScale = Math.max(1, Math.min(300, scale * factor))
      vpRef.current = {
        scale: newScale,
        offsetX: mouseX - worldX * newScale,
        offsetY: mouseY + worldY * newScale,
      }
      draw()
    }, [draw])

    // Native wheel listener with { passive: false } to guarantee preventDefault
    useEffect(() => {
      const el = canvasRef.current
      if (!el) return
      el.addEventListener('wheel', onWheel, { passive: false })
      return () => el.removeEventListener('wheel', onWheel)
    }, [onWheel])

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
