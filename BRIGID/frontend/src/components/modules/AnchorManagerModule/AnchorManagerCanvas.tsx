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
  chainSegmentsToPolygon,
  getClickedSubsegment,
  pointInPolygon,
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

type ActiveTool = 'cursor' | 'select' | 'smartSelect'

const resolveTool = (
  baseTool: ActiveTool,
  shiftHeld: boolean,
  ctrlOrMetaHeld: boolean,
): ActiveTool => {
  if (shiftHeld && ctrlOrMetaHeld) return 'smartSelect'
  if (shiftHeld) return 'select'
  return baseTool
}

interface AnchorManagerCanvasProps {
  allSegments: SegmentData[]
  rooms: RoomData[]
  selectedRoomName: string | null
  selectedAnchorId: string | null
  selectedSegments: SegmentData[]
  viewport: AnchorManagerViewport
  activeTool: ActiveTool
  hoverRoomName: string | null
  onViewportChange: (viewport: AnchorManagerViewport) => void
  onToolChange?: (tool: ActiveTool) => void
  onSegmentClick: (seg: SegmentData, shiftHeld: boolean, worldX: number, worldY: number) => void
  onRoomClick: (roomName: string) => void
  onRoomHover: (roomName: string | null) => void
  onNudgeAnchor: (dx: number, dy: number) => void
  onSmartSelectClick?: (worldX: number, worldY: number, shiftHeld: boolean) => void
  onCanvasContextMenu?: () => void
  onRoomDoubleClick?: (roomName: string) => void
}

const COLORS = {
  bg: '#0a0b0d',
  segment: '#314052',
  segmentHover: '#5a90c8',
  segmentSelected: '#4a9eff',
  roomBoundary: '#2060b0',
  roomBoundaryActive: '#4a9eff',
  roomBoundaryHover: '#3a78c0',
  roomFill: 'rgba(74, 158, 255, 0.035)',
  roomFillActive: 'rgba(74, 158, 255, 0.08)',
  roomFillHover: 'rgba(74, 158, 255, 0.055)',
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
  activeTool,
  hoverRoomName,
  onViewportChange,
  onToolChange,
  onSegmentClick,
  onRoomClick,
  onRoomHover,
  onNudgeAnchor,
  onSmartSelectClick,
  onCanvasContextMenu,
  onRoomDoubleClick,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [hoverSeg, setHoverSeg] = useState<SegmentData | null>(null)
  const [transientTool, setTransientTool] = useState<ActiveTool | null>(null)
  const panRef = useRef<{ active: boolean; lastX: number; lastY: number }>({
    active: false,
    lastX: 0,
    lastY: 0,
  })
  const spacePressedRef = useRef(false)
  const hoverRoomNameRef = useRef<string | null>(null)

  const cancelInteraction = useCallback(() => {
    panRef.current.active = false
    spacePressedRef.current = false
  }, [])

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
    if (activeTool !== 'select') setHoverSeg(null)
    if (activeTool === 'cursor') setTransientTool(null)
  }, [activeTool])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = COLORS.bg
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    for (const room of rooms) {
      if (room.segments_ft.length === 0) continue
      const isActive = room.room_name === selectedRoomName
      const isHovered = room.room_name === hoverRoomName && !isActive
      const points = room.segments_ft.map(seg => worldToScreen(viewport, seg.x1, seg.y1))
      if (points.length > 2) {
        ctx.fillStyle = isActive ? COLORS.roomFillActive : isHovered ? COLORS.roomFillHover : COLORS.roomFill
        ctx.beginPath()
        ctx.moveTo(points[0][0], points[0][1])
        for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1])
        ctx.closePath()
        ctx.fill()
      }
    }

    for (const seg of allSegments) {
      const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
      const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
      ctx.strokeStyle = COLORS.segment
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    for (const room of rooms) {
      const isActive = room.room_name === selectedRoomName
      const isHovered = room.room_name === hoverRoomName && !isActive
      ctx.strokeStyle = isActive ? COLORS.roomBoundaryActive : isHovered ? COLORS.roomBoundaryHover : COLORS.roomBoundary
      ctx.lineWidth = isActive ? 2.4 : isHovered ? 1.8 : 1.4
      for (const seg of room.segments_ft) {
        const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
        const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }
    }

    if (hoverSeg) {
      const [x1, y1] = worldToScreen(viewport, hoverSeg.x1, hoverSeg.y1)
      const [x2, y2] = worldToScreen(viewport, hoverSeg.x2, hoverSeg.y2)
      ctx.strokeStyle = COLORS.segmentHover
      ctx.lineWidth = 2.2
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    if (selectedSegments.length > 0) {
      ctx.strokeStyle = COLORS.segmentSelected
      ctx.lineWidth = 3.2
      for (const seg of selectedSegments) {
        const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
        const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }
    }
  }, [
    allSegments,
    hoverRoomName,
    hoverSeg,
    rooms,
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

  const updateHoverState = useCallback((clientX: number, clientY: number, currentRooms: RoomData[], currentTool: ActiveTool) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = clientX - rect.left
    const my = clientY - rect.top
    const [worldX, worldY] = screenToWorld(viewport, mx, my)
    if (currentTool === 'select') {
      const segment = getSegmentAt(mx, my)
      setHoverSeg(segment ? getClickedSubsegment(segment, allSegments, worldX, worldY) : null)
    } else {
      setHoverSeg(null)
    }

    let nextHoverRoom: string | null = null
    for (const room of currentRooms) {
      if (room.segments_ft.length < 3) continue
      const polygon = chainSegmentsToPolygon(room.segments_ft)
      if (pointInPolygon(worldX, worldY, polygon)) {
        nextHoverRoom = room.room_name
        break
      }
    }
    if (nextHoverRoom !== hoverRoomNameRef.current) {
      hoverRoomNameRef.current = nextHoverRoom
      onRoomHover(nextHoverRoom)
    }
  }, [allSegments, getSegmentAt, onRoomHover, viewport])

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

    const [worldX, worldY] = screenToWorld(viewport, mx, my)
    const currentTool = resolveTool(activeTool, e.shiftKey, e.ctrlKey || e.metaKey)

    // Smart Select fires on any click — no segment hit-test required
    if (currentTool === 'smartSelect') {
      onSmartSelectClick?.(worldX, worldY, e.shiftKey)
      return
    }

    const segment = currentTool === 'select' ? getSegmentAt(mx, my) : null
    if (segment) {
      setHoverSeg(null)
      onSegmentClick(segment, e.shiftKey, worldX, worldY)
      return
    }

    if (currentTool === 'cursor') {
      for (const room of rooms) {
        if (roomContainsWorldPoint(room, worldX, worldY, 0)) {
          onRoomClick(room.room_name)
          return
        }
      }
    }

    panRef.current = { active: true, lastX: e.clientX, lastY: e.clientY }
  }, [
    activeTool,
    allSegments,
    getSegmentAt,
    onRoomClick,
    onSegmentClick,
    onSmartSelectClick,
    rooms,
    viewport,
  ])

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const currentTool = resolveTool(activeTool, e.shiftKey, e.ctrlKey || e.metaKey)
    setTransientTool(currentTool === activeTool ? null : currentTool)
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

    updateHoverState(e.clientX, e.clientY, rooms, currentTool)
  }, [activeTool, onViewportChange, rooms, updateHoverState, viewport])

  const handleMouseUp = useCallback(() => {
    panRef.current.active = false
  }, [])

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
    if ((e.key === 'c' || e.key === 'C') && !e.ctrlKey && !e.metaKey && !e.altKey) {
      setTransientTool(null)
      setHoverSeg(null)
      onToolChange?.('cursor')
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
  }, [cancelInteraction, fitView, onNudgeAnchor, onToolChange, selectedAnchorId])

  const handleKeyUp = useCallback((e: React.KeyboardEvent<HTMLCanvasElement>) => {
    if (e.key === ' ') spacePressedRef.current = false
  }, [])

  const handleContextMenu = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const currentTool = resolveTool(activeTool, e.shiftKey, e.ctrlKey || e.metaKey)
    if (currentTool !== 'cursor') onCanvasContextMenu?.()
  }, [activeTool, onCanvasContextMenu])

  const handleDoubleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const [worldX, worldY] = screenToWorld(viewport, e.clientX - rect.left, e.clientY - rect.top)
    for (const room of rooms) {
      if (roomContainsWorldPoint(room, worldX, worldY, 0)) {
        onRoomDoubleClick?.(room.room_name)
        return
      }
    }
  }, [onRoomDoubleClick, rooms, viewport])

  return (
    <canvas
      ref={canvasRef}
      className="am-canvas"
      tabIndex={0}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={() => { handleMouseUp(); hoverRoomNameRef.current = null; onRoomHover(null); setHoverSeg(null); setTransientTool(null) }}
      onWheel={handleWheel}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      onContextMenu={handleContextMenu}
      onDoubleClick={handleDoubleClick}
      style={{
        cursor: panRef.current.active
          ? 'grabbing'
          : hoverSeg
            ? 'pointer'
            : (transientTool ?? activeTool) !== 'cursor'
              ? 'crosshair'
              : 'grab',
      }}
    />
  )
})

AnchorManagerCanvas.displayName = 'AnchorManagerCanvas'

export default AnchorManagerCanvas
