import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { RoomData, SegmentData } from '../../../types'
import {
  findSnapTarget,
  getAnchorWorldPosition,
  roomContainsWorldPoint,
} from './anchorGeometry'

export interface AnchorManagerViewport {
  offsetX: number
  offsetY: number
  scale: number
}

export interface AnchorManagerCanvasHandle {
  fitView: () => void
  zoomIn: () => void
  zoomOut: () => void
  focusCanvas: () => void
  cancelInteraction: () => void
}

interface AnchorHit {
  anchorId: string
  roomName: string
}

interface AnchorManagerCanvasProps {
  allSegments: SegmentData[]
  rooms: RoomData[]
  selectedRoomName: string | null
  selectedAnchorId: string | null
  selectedSegments: SegmentData[]
  viewport: AnchorManagerViewport
  onViewportChange: (viewport: AnchorManagerViewport) => void
  onSegmentClick: (seg: SegmentData, shiftHeld: boolean) => void
  onCanvasCtrlClick: (worldX: number, worldY: number) => void
  onAnchorClick: (anchorId: string, roomName: string) => void
  onAnchorMoveStart: (roomName: string, anchorId: string) => void
  onAnchorMove: (roomName: string, anchorId: string, worldX: number, worldY: number) => void
  onAnchorMoveEnd: () => void
  onNudgeAnchor: (dx: number, dy: number) => void
}

const COLORS = {
  bg: '#0a0b0d',
  segment: '#314052',
  segmentHover: '#5a90c8',
  segmentSelected: '#4a9eff',
  roomBoundary: '#2060b0',
  roomBoundaryActive: '#4a9eff',
  roomFill: 'rgba(74, 158, 255, 0.035)',
  roomFillActive: 'rgba(74, 158, 255, 0.08)',
  anchorPin: '#ff8c00',
  anchorPinActive: '#ffd700',
  anchorLabel: '#ffffff',
  previewFill: 'rgba(110, 195, 255, 0.22)',
  previewStroke: 'rgba(110, 195, 255, 0.55)',
  snap: '#7dd3fc',
}

const worldToScreen = (viewport: AnchorManagerViewport, wx: number, wy: number): [number, number] => (
  [wx * viewport.scale + viewport.offsetX, wy * viewport.scale + viewport.offsetY]
)

const screenToWorld = (viewport: AnchorManagerViewport, sx: number, sy: number): [number, number] => (
  [(sx - viewport.offsetX) / viewport.scale, (sy - viewport.offsetY) / viewport.scale]
)

const distPointToSegScreen = (
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number => {
  const dx = x2 - x1
  const dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  if (lenSq < 1e-8) return Math.hypot(px - x1, py - y1)
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lenSq))
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
}

const AnchorManagerCanvas = forwardRef<AnchorManagerCanvasHandle, AnchorManagerCanvasProps>(({
  allSegments,
  rooms,
  selectedRoomName,
  selectedAnchorId,
  selectedSegments,
  viewport,
  onViewportChange,
  onSegmentClick,
  onCanvasCtrlClick,
  onAnchorClick,
  onAnchorMoveStart,
  onAnchorMove,
  onAnchorMoveEnd,
  onNudgeAnchor,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hoverSeg, setHoverSeg] = useState<SegmentData | null>(null)
  const [hoverWorld, setHoverWorld] = useState<[number, number] | null>(null)
  const [hoverSnap, setHoverSnap] = useState<{ x: number; y: number } | null>(null)
  const panRef = useRef<{ active: boolean; lastX: number; lastY: number }>({
    active: false,
    lastX: 0,
    lastY: 0,
  })
  const dragRef = useRef<{
    active: boolean
    roomName: string
    anchorId: string
    originalX: number
    originalY: number
  } | null>(null)
  const spacePressedRef = useRef(false)

  const cancelInteraction = useCallback(() => {
    panRef.current.active = false
    if (dragRef.current?.active) {
      dragRef.current = null
      onAnchorMoveEnd()
    }
    spacePressedRef.current = false
    setHoverSnap(null)
  }, [onAnchorMoveEnd])

  const fitView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas || allSegments.length === 0) return
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const seg of allSegments) {
      minX = Math.min(minX, seg.x1, seg.x2)
      minY = Math.min(minY, seg.y1, seg.y2)
      maxX = Math.max(maxX, seg.x1, seg.x2)
      maxY = Math.max(maxY, seg.y1, seg.y2)
    }
    const gw = Math.max(maxX - minX, 1)
    const gh = Math.max(maxY - minY, 1)
    const scale = Math.min(canvas.width / gw, canvas.height / gh) * 0.95
    onViewportChange({
      scale,
      offsetX: (canvas.width - gw * scale) / 2 - minX * scale,
      offsetY: (canvas.height - gh * scale) / 2 - minY * scale,
    })
  }, [allSegments, onViewportChange])

  const zoomAroundPoint = useCallback((factor: number, sx?: number, sy?: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pivotX = sx ?? canvas.width / 2
    const pivotY = sy ?? canvas.height / 2
    const nextScale = Math.max(2, Math.min(240, viewport.scale * factor))
    onViewportChange({
      scale: nextScale,
      offsetX: pivotX - (pivotX - viewport.offsetX) * (nextScale / viewport.scale),
      offsetY: pivotY - (pivotY - viewport.offsetY) * (nextScale / viewport.scale),
    })
  }, [viewport, onViewportChange])

  useImperativeHandle(ref, () => ({
    fitView,
    zoomIn: () => zoomAroundPoint(1.15),
    zoomOut: () => zoomAroundPoint(1 / 1.15),
    focusCanvas: () => canvasRef.current?.focus(),
    cancelInteraction,
  }), [cancelInteraction, fitView, zoomAroundPoint])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const resize = () => {
      const width = canvas.offsetWidth
      const height = canvas.offsetHeight
      if (width > 0 && height > 0) {
        canvas.width = width
        canvas.height = height
      }
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    requestAnimationFrame(resize)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = COLORS.bg
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    const selectedSet = new Set(selectedSegments.map(seg => `${seg.x1},${seg.y1},${seg.x2},${seg.y2}`))

    for (const room of rooms) {
      if (room.segments_ft.length === 0) continue
      const isActive = room.room_name === selectedRoomName
      const points = room.segments_ft.map(seg => worldToScreen(viewport, seg.x1, seg.y1))
      if (points.length > 2) {
        ctx.fillStyle = isActive ? COLORS.roomFillActive : COLORS.roomFill
        ctx.beginPath()
        ctx.moveTo(points[0][0], points[0][1])
        for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1])
        ctx.closePath()
        ctx.fill()
      }
    }

    for (const seg of allSegments) {
      const key = `${seg.x1},${seg.y1},${seg.x2},${seg.y2}`
      const isSelected = selectedSet.has(key)
      const isHover = hoverSeg === seg
      const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
      const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
      ctx.strokeStyle = isSelected ? COLORS.segmentSelected : isHover ? COLORS.segmentHover : COLORS.segment
      ctx.lineWidth = isSelected ? 2.2 : isHover ? 1.6 : 1
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    for (const room of rooms) {
      const isActive = room.room_name === selectedRoomName
      ctx.strokeStyle = isActive ? COLORS.roomBoundaryActive : COLORS.roomBoundary
      ctx.lineWidth = isActive ? 2.4 : 1.4
      for (const seg of room.segments_ft) {
        const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
        const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }

      for (const anchor of room.anchors) {
        const [wx, wy] = getAnchorWorldPosition(room, anchor)
        const [sx, sy] = worldToScreen(viewport, wx, wy)
        const isSelected = anchor.id === selectedAnchorId
        const radius = isSelected ? 8 : 6
        ctx.fillStyle = isSelected ? COLORS.anchorPinActive : COLORS.anchorPin
        ctx.beginPath()
        ctx.arc(sx, sy, radius, 0, Math.PI * 2)
        ctx.fill()
        ctx.strokeStyle = '#ffffff'
        ctx.lineWidth = 1.4
        ctx.stroke()
        ctx.fillStyle = COLORS.anchorLabel
        ctx.font = `bold ${Math.max(9, Math.min(11, viewport.scale * 0.45))}px var(--font-mono, monospace)`
        ctx.textAlign = 'left'
        ctx.textBaseline = 'bottom'
        ctx.fillText(anchor.hw_id || anchor.id, sx + 12, sy - 12)
      }
    }

    if (selectedRoomName && hoverWorld) {
      const previewPoint = hoverSnap ?? { x: hoverWorld[0], y: hoverWorld[1] }
      const [sx, sy] = worldToScreen(viewport, previewPoint.x, previewPoint.y)
      const previewRadius = Math.max(5, Math.min(14, viewport.scale * 0.5))
      ctx.fillStyle = COLORS.previewFill
      ctx.strokeStyle = COLORS.previewStroke
      ctx.lineWidth = 1.4
      ctx.beginPath()
      ctx.arc(sx, sy, previewRadius, 0, Math.PI * 2)
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
  }, [
    allSegments,
    hoverSeg,
    hoverSnap,
    hoverWorld,
    rooms,
    selectedAnchorId,
    selectedRoomName,
    selectedSegments,
    viewport,
  ])

  const getSegmentAt = useCallback((mx: number, my: number): SegmentData | null => {
    let best: SegmentData | null = null
    let bestDistance = 6
    for (const seg of allSegments) {
      const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
      const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
      const distance = distPointToSegScreen(mx, my, x1, y1, x2, y2)
      if (distance < bestDistance) {
        best = seg
        bestDistance = distance
      }
    }
    return best
  }, [allSegments, viewport])

  const getAnchorAt = useCallback((mx: number, my: number): AnchorHit | null => {
    for (const room of rooms) {
      for (const anchor of room.anchors) {
        const [wx, wy] = getAnchorWorldPosition(room, anchor)
        const [sx, sy] = worldToScreen(viewport, wx, wy)
        if (Math.hypot(mx - sx, my - sy) <= 10) {
          return { anchorId: anchor.id, roomName: room.room_name }
        }
      }
    }
    return null
  }, [rooms, viewport])

  const updateHoverState = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = clientX - rect.left
    const my = clientY - rect.top
    const [worldX, worldY] = screenToWorld(viewport, mx, my)
    setHoverSeg(getSegmentAt(mx, my))
    setHoverWorld([worldX, worldY])
    setHoverSnap(selectedRoomName ? findSnapTarget(worldX, worldY, allSegments) : null)
  }, [allSegments, getSegmentAt, selectedRoomName, viewport])

  const handleMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    e.currentTarget.focus()
    if (e.button === 1 || (e.button === 0 && spacePressedRef.current)) {
      panRef.current = { active: true, lastX: e.clientX, lastY: e.clientY }
      e.preventDefault()
      return
    }

    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    if (e.button !== 0) return

    const anchorHit = getAnchorAt(mx, my)
    if (anchorHit) {
      const room = rooms.find(item => item.room_name === anchorHit.roomName)
      const anchor = room?.anchors.find(item => item.id === anchorHit.anchorId)
      if (!room || !anchor) return
      const [wx, wy] = getAnchorWorldPosition(room, anchor)
      dragRef.current = {
        active: true,
        roomName: anchorHit.roomName,
        anchorId: anchorHit.anchorId,
        originalX: wx,
        originalY: wy,
      }
      onAnchorClick(anchorHit.anchorId, anchorHit.roomName)
      onAnchorMoveStart(anchorHit.roomName, anchorHit.anchorId)
      return
    }

    if (e.ctrlKey && selectedRoomName) {
      const [worldX, worldY] = screenToWorld(viewport, mx, my)
      const snap = findSnapTarget(worldX, worldY, allSegments)
      const nextPoint = snap ? [snap.x, snap.y] : [worldX, worldY]
      onCanvasCtrlClick(nextPoint[0], nextPoint[1])
      return
    }

    const segment = getSegmentAt(mx, my)
    if (segment) {
      onSegmentClick(segment, e.shiftKey)
      return
    }

    panRef.current = { active: true, lastX: e.clientX, lastY: e.clientY }
  }, [
    allSegments,
    getAnchorAt,
    getSegmentAt,
    onAnchorClick,
    onAnchorMoveStart,
    onCanvasCtrlClick,
    onSegmentClick,
    rooms,
    selectedRoomName,
    viewport,
  ])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (panRef.current.active) {
      const dx = e.clientX - panRef.current.lastX
      const dy = e.clientY - panRef.current.lastY
      panRef.current.lastX = e.clientX
      panRef.current.lastY = e.clientY
      onViewportChange({
        ...viewport,
        offsetX: viewport.offsetX + dx,
        offsetY: viewport.offsetY + dy,
      })
      return
    }

    if (dragRef.current?.active) {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const [pointerWorldX, pointerWorldY] = screenToWorld(viewport, e.clientX - rect.left, e.clientY - rect.top)
      let nextX = pointerWorldX
      let nextY = pointerWorldY

      if (e.ctrlKey) {
        const dx = pointerWorldX - dragRef.current.originalX
        const dy = pointerWorldY - dragRef.current.originalY
        nextX = dragRef.current.originalX + dx * 0.2
        nextY = dragRef.current.originalY + dy * 0.2
      }

      if (!e.shiftKey) {
        const snap = findSnapTarget(nextX, nextY, allSegments)
        if (snap) {
          nextX = snap.x
          nextY = snap.y
        }
      }

      const room = rooms.find(item => item.room_name === dragRef.current?.roomName)
      if (room && roomContainsWorldPoint(room, nextX, nextY, 0.05)) {
        onAnchorMove(room.room_name, dragRef.current.anchorId, nextX, nextY)
        setHoverSnap(findSnapTarget(nextX, nextY, allSegments))
      }
      return
    }

    updateHoverState(e.clientX, e.clientY)
  }, [allSegments, onAnchorMove, onViewportChange, rooms, updateHoverState, viewport])

  const handleMouseUp = useCallback(() => {
    panRef.current.active = false
    if (dragRef.current?.active) {
      dragRef.current = null
      onAnchorMoveEnd()
    }
  }, [onAnchorMoveEnd])

  const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const rect = e.currentTarget.getBoundingClientRect()
    zoomAroundPoint(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - rect.left, e.clientY - rect.top)
  }, [zoomAroundPoint])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    if (e.key === ' ') {
      spacePressedRef.current = true
      e.preventDefault()
      return
    }
    if (e.key === 'Escape') {
      cancelInteraction()
      e.preventDefault()
      return
    }
    if (e.key === 'f' || e.key === 'F') {
      fitView()
      e.preventDefault()
      return
    }
    if (selectedAnchorId) {
      const step = 0.1
      if (e.key === 'ArrowLeft') { onNudgeAnchor(-step, 0); e.preventDefault() }
      if (e.key === 'ArrowRight') { onNudgeAnchor(step, 0); e.preventDefault() }
      if (e.key === 'ArrowUp') { onNudgeAnchor(0, -step); e.preventDefault() }
      if (e.key === 'ArrowDown') { onNudgeAnchor(0, step); e.preventDefault() }
    }
  }, [cancelInteraction, fitView, onNudgeAnchor, selectedAnchorId])

  const handleKeyUp = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    if (e.key === ' ') spacePressedRef.current = false
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="am-canvas"
      tabIndex={0}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      style={{
        cursor: dragRef.current?.active ? 'grabbing' : panRef.current.active ? 'grabbing' : hoverSeg ? 'pointer' : 'grab',
      }}
    />
  )
})

AnchorManagerCanvas.displayName = 'AnchorManagerCanvas'

export default AnchorManagerCanvas
