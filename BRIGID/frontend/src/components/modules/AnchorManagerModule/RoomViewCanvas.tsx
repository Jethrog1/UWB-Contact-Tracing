import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { AnchorData, RoomData, SegmentData } from '../../../types'
import { findSnapTarget, getAnchorWorldPosition, roomContainsWorldPoint } from './anchorGeometry'

interface Viewport {
  offsetX: number
  offsetY: number
  scale: number
}

export interface RoomViewCanvasHandle {
  fitView: () => void
}

interface Props {
  room: RoomData
  selectedAnchorId: string | null
  externalPreview?: { localX: number; localY: number } | null
  onAnchorSelect: (anchorId: string | null) => void
  onAnchorPlace: (localX: number, localY: number) => void
  onAnchorMoveStart: (anchorId: string) => void
  onAnchorMove: (anchorId: string, localX: number, localY: number) => void
  onAnchorMoveEnd: () => void
}

const COLORS = {
  bg: '#0a0b0d',
  segment: '#314052',
  roomBoundary: '#2060b0',
  roomFill: 'rgba(74, 158, 255, 0.06)',
  anchorPin: '#ff8c00',
  anchorPinActive: '#ffd700',
  anchorLabel: '#ffffff',
  previewFill: 'rgba(110, 195, 255, 0.22)',
  previewStroke: 'rgba(110, 195, 255, 0.55)',
  snap: '#7dd3fc',
}

const worldToScreen = (vp: Viewport, wx: number, wy: number): [number, number] => (
  [wx * vp.scale + vp.offsetX, wy * vp.scale + vp.offsetY]
)
const screenToWorld = (vp: Viewport, sx: number, sy: number): [number, number] => (
  [(sx - vp.offsetX) / vp.scale, (sy - vp.offsetY) / vp.scale]
)

const RoomViewCanvas = forwardRef<RoomViewCanvasHandle, Props>(({
  room,
  selectedAnchorId,
  externalPreview = null,
  onAnchorSelect,
  onAnchorPlace,
  onAnchorMoveStart,
  onAnchorMove,
  onAnchorMoveEnd,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [viewport, setViewport] = useState<Viewport>({ offsetX: 0, offsetY: 0, scale: 20 })
  const [hoverWorld, setHoverWorld] = useState<[number, number] | null>(null)
  const [hoverSnap, setHoverSnap] = useState<{ x: number; y: number } | null>(null)
  const [ctrlDown, setCtrlDown] = useState(false)
  const fitDoneRef = useRef(false)
  const panRef = useRef<{ active: boolean; lastX: number; lastY: number }>({ active: false, lastX: 0, lastY: 0 })
  const dragRef = useRef<{ active: boolean; anchorId: string; origX: number; origY: number } | null>(null)
  const spacePressedRef = useRef(false)
  const viewportRef = useRef(viewport)
  viewportRef.current = viewport

  const allSegments: SegmentData[] = [...room.segments_ft, ...room.interior_segments_ft]

  const fitView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const { min_x, min_y, width, height } = room.room_bounds_ft
    if (width <= 0 || height <= 0) return
    const scale = Math.min(canvas.width / width, canvas.height / height) * 0.85
    setViewport({
      scale,
      offsetX: (canvas.width - width * scale) / 2 - min_x * scale,
      offsetY: (canvas.height - height * scale) / 2 - min_y * scale,
    })
  }, [room.room_bounds_ft])

  useImperativeHandle(ref, () => ({ fitView }), [fitView])

  // Auto-fit on first mount and on room change
  useEffect(() => {
    fitDoneRef.current = false
  }, [room.room_name])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const observer = new ResizeObserver(() => {
      canvas.width = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
      if (!fitDoneRef.current && canvas.width > 0 && canvas.height > 0) {
        fitDoneRef.current = true
        fitView()
      }
    })
    observer.observe(canvas)
    return () => observer.disconnect()
  }, [fitView])

  const zoomAround = useCallback((factor: number, sx?: number, sy?: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pivotX = sx ?? canvas.width / 2
    const pivotY = sy ?? canvas.height / 2
    setViewport(vp => {
      const nextScale = Math.max(2, Math.min(400, vp.scale * factor))
      return {
        scale: nextScale,
        offsetX: pivotX - (pivotX - vp.offsetX) * (nextScale / vp.scale),
        offsetY: pivotY - (pivotY - vp.offsetY) * (nextScale / vp.scale),
      }
    })
  }, [])

  // Render
  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = COLORS.bg
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Room fill
    if (room.segments_ft.length > 2) {
      ctx.fillStyle = COLORS.roomFill
      ctx.beginPath()
      const pts = room.segments_ft.map(s => worldToScreen(viewport, s.x1, s.y1))
      ctx.moveTo(pts[0][0], pts[0][1])
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1])
      ctx.closePath()
      ctx.fill()
    }

    // All segments (interior + boundary)
    for (const seg of allSegments) {
      const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
      const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
      const isBoundary = room.segments_ft.includes(seg)
      ctx.strokeStyle = isBoundary ? COLORS.roomBoundary : COLORS.segment
      ctx.lineWidth = isBoundary ? 1.8 : 1
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    // Anchors
    for (const anchor of room.anchors) {
      const [wx, wy] = getAnchorWorldPosition(room, anchor)
      const [sx, sy] = worldToScreen(viewport, wx, wy)
      const isSelected = anchor.id === selectedAnchorId
      const radius = isSelected ? 9 : 6
      ctx.fillStyle = isSelected ? COLORS.anchorPinActive : COLORS.anchorPin
      ctx.beginPath()
      ctx.arc(sx, sy, radius, 0, Math.PI * 2)
      ctx.fill()
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.4
      ctx.stroke()
      ctx.fillStyle = COLORS.anchorLabel
      ctx.font = `bold ${Math.max(9, Math.min(12, viewport.scale * 0.45))}px var(--font-mono, monospace)`
      ctx.textAlign = 'left'
      ctx.textBaseline = 'bottom'
      ctx.fillText(anchor.id, sx + 12, sy - 4)
    }

    // Placement preview
    if (hoverWorld) {
      const previewPoint = hoverSnap ?? { x: hoverWorld[0], y: hoverWorld[1] }
      const [sx, sy] = worldToScreen(viewport, previewPoint.x, previewPoint.y)
      const r = Math.max(5, Math.min(14, viewport.scale * 0.5))
      ctx.fillStyle = COLORS.previewFill
      ctx.strokeStyle = COLORS.previewStroke
      ctx.lineWidth = 1.4
      ctx.beginPath()
      ctx.arc(sx, sy, r, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()
    }

    if (hoverSnap) {
      const [sx, sy] = worldToScreen(viewport, hoverSnap.x, hoverSnap.y)
      ctx.strokeStyle = COLORS.snap
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.arc(sx, sy, 8, 0, Math.PI * 2)
      ctx.stroke()
    }

    if (externalPreview) {
      const wx = room.room_bounds_ft.min_x + externalPreview.localX
      const wy = room.room_bounds_ft.min_y + externalPreview.localY
      const [sx, sy] = worldToScreen(viewport, wx, wy)
      const r = Math.max(5, Math.min(14, viewport.scale * 0.5))
      ctx.fillStyle = COLORS.previewFill
      ctx.strokeStyle = COLORS.previewStroke
      ctx.lineWidth = 1.4
      ctx.beginPath()
      ctx.arc(sx, sy, r, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()
    }
  }, [room, allSegments, viewport, selectedAnchorId, hoverWorld, hoverSnap, externalPreview])

  const getAnchorAt = useCallback((mx: number, my: number): AnchorData | null => {
    for (const anchor of room.anchors) {
      const [wx, wy] = getAnchorWorldPosition(room, anchor)
      const [sx, sy] = worldToScreen(viewportRef.current, wx, wy)
      if (Math.hypot(mx - sx, my - sy) <= 10) return anchor
    }
    return null
  }, [room])

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    e.currentTarget.focus()
    if (e.button === 1 || (e.button === 0 && spacePressedRef.current)) {
      panRef.current = { active: true, lastX: e.clientX, lastY: e.clientY }
      e.preventDefault()
      return
    }
    if (e.button !== 0) return

    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const vp = viewportRef.current

    const anchorHit = getAnchorAt(mx, my)
    if (anchorHit) {
      const [wx, wy] = getAnchorWorldPosition(room, anchorHit)
      dragRef.current = { active: true, anchorId: anchorHit.id, origX: wx, origY: wy }
      onAnchorSelect(anchorHit.id === selectedAnchorId ? null : anchorHit.id)
      onAnchorMoveStart(anchorHit.id)
      return
    }

    // Ctrl/Cmd + click in empty space places an anchor; plain click starts panning
    if (e.ctrlKey || e.metaKey) {
      const [worldX, worldY] = screenToWorld(vp, mx, my)
      const snap = findSnapTarget(worldX, worldY, allSegments)
      const placeX = snap?.x ?? worldX
      const placeY = snap?.y ?? worldY
      if (roomContainsWorldPoint(room, placeX, placeY, 0.1)) {
        const localX = placeX - room.room_bounds_ft.min_x
        const localY = placeY - room.room_bounds_ft.min_y
        onAnchorPlace(localX, localY)
        return
      }
    }

    panRef.current = { active: true, lastX: e.clientX, lastY: e.clientY }
  }, [allSegments, getAnchorAt, onAnchorMoveStart, onAnchorPlace, onAnchorSelect, room, selectedAnchorId])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const vp = viewportRef.current
    if (panRef.current.active) {
      const dx = e.clientX - panRef.current.lastX
      const dy = e.clientY - panRef.current.lastY
      panRef.current.lastX = e.clientX
      panRef.current.lastY = e.clientY
      setViewport(v => ({ ...v, offsetX: v.offsetX + dx, offsetY: v.offsetY + dy }))
      return
    }

    if (dragRef.current?.active) {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const [wx, wy] = screenToWorld(vp, e.clientX - rect.left, e.clientY - rect.top)
      const snap = !e.shiftKey ? findSnapTarget(wx, wy, allSegments) : null
      const nextX = snap?.x ?? wx
      const nextY = snap?.y ?? wy
      if (roomContainsWorldPoint(room, nextX, nextY, 0.05)) {
        const localX = nextX - room.room_bounds_ft.min_x
        const localY = nextY - room.room_bounds_ft.min_y
        onAnchorMove(dragRef.current.anchorId, localX, localY)
        setHoverSnap(snap ? { x: snap.x, y: snap.y } : null)
      }
      return
    }

    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const [worldX, worldY] = screenToWorld(vp, e.clientX - rect.left, e.clientY - rect.top)
    const isCtrlHeld = e.ctrlKey || e.metaKey
    setCtrlDown(isCtrlHeld)
    const isInRoom = roomContainsWorldPoint(room, worldX, worldY, 0.1)
    const snap = (isInRoom && isCtrlHeld) ? findSnapTarget(worldX, worldY, allSegments) : null
    setHoverWorld(isInRoom && isCtrlHeld && !getAnchorAt(e.clientX - rect.left, e.clientY - rect.top) ? [worldX, worldY] : null)
    setHoverSnap(snap ? { x: snap.x, y: snap.y } : null)
  }, [allSegments, getAnchorAt, onAnchorMove, room])

  const handleMouseUp = useCallback(() => {
    panRef.current.active = false
    if (dragRef.current?.active) {
      dragRef.current = null
      onAnchorMoveEnd()
    }
  }, [onAnchorMoveEnd])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const handler = (e: WheelEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const rect = canvas.getBoundingClientRect()
      zoomAround(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - rect.left, e.clientY - rect.top)
    }
    canvas.addEventListener('wheel', handler, { passive: false })
    return () => canvas.removeEventListener('wheel', handler)
  }, [zoomAround])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    if (e.key === ' ') { spacePressedRef.current = true; e.preventDefault() }
    if (e.key === 'f' || e.key === 'F') { fitView(); e.preventDefault() }
    if (e.key === 'Escape') { onAnchorSelect(null); e.preventDefault() }
    if (e.key === 'Control' || e.key === 'Meta') setCtrlDown(true)
  }, [fitView, onAnchorSelect])

  const handleKeyUp = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    if (e.key === ' ') spacePressedRef.current = false
    if (e.key === 'Control' || e.key === 'Meta') { setCtrlDown(false); setHoverWorld(null); setHoverSnap(null) }
  }, [])

  const isHoveringAnchor = hoverWorld === null && (hoverSnap !== null || false)

  return (
    <canvas
      ref={canvasRef}
      className="am-canvas am-room-view-canvas"
      tabIndex={0}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => { handleMouseUp(); setHoverWorld(null); setHoverSnap(null); setCtrlDown(false) }}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      style={{ cursor: panRef.current.active ? 'grabbing' : isHoveringAnchor ? 'grab' : ctrlDown ? 'crosshair' : 'default' }}
    />
  )
})

RoomViewCanvas.displayName = 'RoomViewCanvas'
export default RoomViewCanvas
