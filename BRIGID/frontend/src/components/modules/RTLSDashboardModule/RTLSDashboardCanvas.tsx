import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { RoomData, SegmentData } from '../../../types'
import { chainSegmentsToPolygon, pointInPolygon } from '../AnchorManagerModule/anchorGeometry'

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
  mode: 'floor-plan' | 'room'
  floorplanSegments: SegmentData[]
  rooms: RoomData[]
  activeRoomName: string | null
  currentRoom: RoomData | null
  hoverRoomName?: string | null
  anchors: Record<string, [number, number]>
  tags: RTLSTagState[]
  referenceAnchorId?: string
  onRoomClick?: (roomName: string) => void
  onRoomDoubleClick?: (roomName: string) => void
  onRoomHover?: (roomName: string | null) => void
}

export interface RTLSDashboardCanvasHandle {
  resetView: () => void
  zoomIn: () => void
  zoomOut: () => void
}

const BG = '#0a0b0d'
const FLOORPLAN_SEGMENT = '#314052'
const FLOORPLAN_NON_WALL = '#556172'
const ROOM_OUTLINE = '#2060b0'
const ROOM_OUTLINE_ACTIVE = '#4a9eff'
const ROOM_OUTLINE_HOVER = '#3a78c0'
const ROOM_FILL = 'rgba(74, 158, 255, 0.035)'
const ROOM_FILL_ACTIVE = 'rgba(74, 158, 255, 0.08)'
const ROOM_FILL_HOVER = 'rgba(74, 158, 255, 0.055)'

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

const worldToScreen = (vp: RTLSViewport, wx: number, wy: number): [number, number] => (
  [wx * vp.scale + vp.offsetX, wy * vp.scale + vp.offsetY]
)

const screenToWorld = (vp: RTLSViewport, sx: number, sy: number): [number, number] => (
  [(sx - vp.offsetX) / vp.scale, (sy - vp.offsetY) / vp.scale]
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

const segmentBounds = (segments: SegmentData[]): { minX: number; minY: number; maxX: number; maxY: number } | null => {
  if (segments.length === 0) return null
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const seg of segments) {
    minX = Math.min(minX, seg.x1, seg.x2)
    minY = Math.min(minY, seg.y1, seg.y2)
    maxX = Math.max(maxX, seg.x1, seg.x2)
    maxY = Math.max(maxY, seg.y1, seg.y2)
  }
  return { minX, minY, maxX, maxY }
}

const roomBounds = (rooms: RoomData[]): { minX: number; minY: number; maxX: number; maxY: number } | null => {
  if (rooms.length === 0) return null
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const room of rooms) {
    const bounds = room.room_bounds_ft
    minX = Math.min(minX, bounds.min_x)
    minY = Math.min(minY, bounds.min_y)
    maxX = Math.max(maxX, bounds.max_x)
    maxY = Math.max(maxY, bounds.max_y)
  }
  return { minX, minY, maxX, maxY }
}

const toRoomLocal = (room: RoomData, x: number, y: number): [number, number] => ([
  x - room.room_bounds_ft.min_x,
  y - room.room_bounds_ft.min_y,
])

const localizeSegment = (room: RoomData, segment: SegmentData): SegmentData => {
  const [x1, y1] = toRoomLocal(room, segment.x1, segment.y1)
  const [x2, y2] = toRoomLocal(room, segment.x2, segment.y2)
  return { x1, y1, x2, y2 }
}

const roomPolygon = (room: RoomData): [number, number][] => chainSegmentsToPolygon(room.segments_ft)
const roomLocalPolygon = (room: RoomData): [number, number][] => (
  chainSegmentsToPolygon(room.segments_ft.map(segment => localizeSegment(room, segment)))
)

const roomAtPoint = (rooms: RoomData[], worldX: number, worldY: number): string | null => {
  for (const room of rooms) {
    if (room.segments_ft.length < 3) continue
    const polygon = roomPolygon(room)
    if (polygon.length >= 3 && pointInPolygon(worldX, worldY, polygon)) {
      return room.room_name
    }
  }
  return null
}

const RTLSDashboardCanvas = forwardRef<RTLSDashboardCanvasHandle, RTLSDashboardCanvasProps>(({
  mode,
  floorplanSegments,
  rooms,
  activeRoomName,
  currentRoom,
  hoverRoomName,
  anchors,
  tags,
  referenceAnchorId,
  onRoomClick,
  onRoomDoubleClick,
  onRoomHover,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const vpRef = useRef<RTLSViewport>({ offsetX: 0, offsetY: 0, scale: 20 })
  const dragRef = useRef<{ x: number; y: number } | null>(null)
  const [canvasVersion, setCanvasVersion] = useState(0)
  const hoverRoomRef = useRef<string | null>(null)

  const activeRoom = currentRoom ?? rooms.find(room => room.room_name === activeRoomName) ?? null
  const displaySegments = mode === 'room'
    ? (activeRoom
        ? [...activeRoom.segments_ft, ...activeRoom.interior_segments_ft].map(segment => localizeSegment(activeRoom, segment))
        : [])
    : floorplanSegments

  const resetView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const padding = 70

    let bounds = segmentBounds(displaySegments)
    if (!bounds && mode === 'floor-plan') bounds = roomBounds(rooms)
    if (mode === 'room' && activeRoom) {
      bounds = {
        minX: 0,
        minY: 0,
        maxX: activeRoom.room_bounds_ft.width,
        maxY: activeRoom.room_bounds_ft.height,
      }
    }
    if (!bounds) return

    const width = Math.max(bounds.maxX - bounds.minX, 1)
    const height = Math.max(bounds.maxY - bounds.minY, 1)
    const scale = Math.min(
      (canvas.width - padding * 2) / width,
      (canvas.height - padding * 2) / height,
    )

    vpRef.current = {
      scale: Math.max(2, scale),
      offsetX: (canvas.width - width * Math.max(2, scale)) / 2 - bounds.minX * Math.max(2, scale),
      offsetY: (canvas.height - height * Math.max(2, scale)) / 2 - bounds.minY * Math.max(2, scale),
    }
    setCanvasVersion(version => version + 1)
  }, [activeRoom, displaySegments, mode])

  const zoomBy = useCallback((factor: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pivotX = canvas.width / 2
    const pivotY = canvas.height / 2
    const prev = vpRef.current
    const nextScale = Math.max(2, Math.min(300, prev.scale * factor))
    vpRef.current = {
      scale: nextScale,
      offsetX: pivotX - (pivotX - prev.offsetX) * (nextScale / prev.scale),
      offsetY: pivotY - (pivotY - prev.offsetY) * (nextScale / prev.scale),
    }
    setCanvasVersion(version => version + 1)
  }, [])

  useImperativeHandle(ref, () => ({
    resetView,
    zoomIn: () => zoomBy(1.15),
    zoomOut: () => zoomBy(1 / 1.15),
  }), [resetView, zoomBy])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const parent = canvas.parentElement
    if (!parent) return

    const observer = new ResizeObserver(() => {
      canvas.width = parent.clientWidth
      canvas.height = parent.clientHeight
      resetView()
    })
    observer.observe(parent)
    canvas.width = parent.clientWidth
    canvas.height = parent.clientHeight
    resetView()
    return () => observer.disconnect()
  }, [resetView])

  useEffect(() => {
    hoverRoomRef.current = null
    resetView()
  }, [mode, activeRoomName, activeRoom?.room_name, floorplanSegments.length, rooms.length, resetView])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return

    const viewport = vpRef.current
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = BG
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    if (mode === 'floor-plan') {
      for (const room of rooms) {
        const isActive = room.room_name === activeRoomName
        const isHovered = room.room_name === hoverRoomName && !isActive
        const polygon = roomPolygon(room)
        const points = polygon.map(([x, y]) => worldToScreen(viewport, x, y))
        if (points.length >= 3) {
          ctx.fillStyle = isActive ? ROOM_FILL_ACTIVE : isHovered ? ROOM_FILL_HOVER : ROOM_FILL
          ctx.beginPath()
          ctx.moveTo(points[0][0], points[0][1])
          for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1])
          ctx.closePath()
          ctx.fill()
        }
      }

      for (const seg of floorplanSegments) {
        const [x1, y1] = worldToScreen(viewport, seg.x1, seg.y1)
        const [x2, y2] = worldToScreen(viewport, seg.x2, seg.y2)
        ctx.strokeStyle = (seg as SegmentData & { role?: string }).role === 'non_wall'
          ? FLOORPLAN_NON_WALL
          : FLOORPLAN_SEGMENT
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }

      for (const room of rooms) {
        const isActive = room.room_name === activeRoomName
        const isHovered = room.room_name === hoverRoomName && !isActive
        ctx.strokeStyle = isActive ? ROOM_OUTLINE_ACTIVE : isHovered ? ROOM_OUTLINE_HOVER : ROOM_OUTLINE
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
    } else if (activeRoom) {
      const polygon = roomLocalPolygon(activeRoom)
      const points = polygon.map(([x, y]) => worldToScreen(viewport, x, y))
      if (points.length >= 3) {
        ctx.fillStyle = ROOM_FILL_ACTIVE
        ctx.beginPath()
        ctx.moveTo(points[0][0], points[0][1])
        for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1])
        ctx.closePath()
        ctx.fill()
      }

      for (const seg of [...activeRoom.segments_ft, ...activeRoom.interior_segments_ft]) {
        const localSeg = localizeSegment(activeRoom, seg)
        const [x1, y1] = worldToScreen(viewport, localSeg.x1, localSeg.y1)
        const [x2, y2] = worldToScreen(viewport, localSeg.x2, localSeg.y2)
        const isBoundary = activeRoom.segments_ft.includes(seg)
        ctx.strokeStyle = isBoundary ? ROOM_OUTLINE_ACTIVE : FLOORPLAN_SEGMENT
        ctx.lineWidth = isBoundary ? 1.9 : 1.1
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }
    }

    if (mode === 'room') {
      const anchorIds = Object.keys(anchors)
      let refX = 0
      let refY = 0
      if (referenceAnchorId && anchors[referenceAnchorId]) {
        [refX, refY] = toRoomLocal(activeRoom, anchors[referenceAnchorId][0], anchors[referenceAnchorId][1])
      }

      for (let i = 0; i < anchorIds.length; i++) {
        const anchorId = anchorIds[i]
        const [ax, ay] = anchors[anchorId]
        const [localAx, localAy] = toRoomLocal(activeRoom, ax, ay)
        const [sx, sy] = worldToScreen(viewport, localAx, localAy)
        const isRef = anchorId === referenceAnchorId
        const r = isRef ? 8 : 6
        const color = anchorColor(i)

        if (isRef) {
          ctx.beginPath()
          ctx.arc(sx, sy, r + 4, 0, Math.PI * 2)
          ctx.strokeStyle = color
          ctx.lineWidth = 1.5
          ctx.setLineDash([3, 2])
          ctx.stroke()
          ctx.setLineDash([])
        }

        ctx.beginPath()
        ctx.arc(sx, sy, r, 0, Math.PI * 2)
        ctx.fillStyle = color
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.25)'
        ctx.lineWidth = 1
        ctx.stroke()

        const labelX = localAx - refX
        const labelY = localAy - refY
        ctx.fillStyle = '#ffffff'
        ctx.font = 'bold 11px "SF Mono", monospace'
        ctx.textAlign = 'left'
        ctx.textBaseline = 'bottom'
        ctx.fillText(
          isRef ? `${anchorId} ★ (0.0, 0.0)` : `${anchorId} (${labelX.toFixed(1)}, ${labelY.toFixed(1)})`,
          sx + 10,
          sy - 4,
        )
      }

      for (const tag of tags) {
        if (!tag.position) continue
        const [localX, localY] = toRoomLocal(activeRoom, tag.position.x, tag.position.y)
        const [sx, sy] = worldToScreen(viewport, localX, localY)
        const radius = 8
        const grad = ctx.createRadialGradient(sx, sy, 0, sx, sy, radius * 2.5)
        grad.addColorStop(0, `${tag.color}66`)
        grad.addColorStop(1, 'transparent')
        ctx.beginPath()
        ctx.arc(sx, sy, radius * 2.5, 0, Math.PI * 2)
        ctx.fillStyle = grad
        ctx.fill()

        ctx.beginPath()
        ctx.arc(sx, sy, radius, 0, Math.PI * 2)
        ctx.fillStyle = tag.color
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.4)'
        ctx.lineWidth = 1.5
        ctx.stroke()

        ctx.fillStyle = tag.color
        ctx.font = 'bold 11px sans-serif'
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        ctx.fillText(tag.tag_id, sx + 14, sy)

        const labelX = localX - refX
        const labelY = localY - refY
        ctx.fillStyle = 'rgba(200, 220, 255, 0.7)'
        ctx.font = '9px sans-serif'
        ctx.fillText(`(${labelX.toFixed(2)}, ${labelY.toFixed(2)}) ft`, sx + 14, sy + 12)
      }
    }
  }, [
    activeRoom,
    activeRoomName,
    anchors,
    canvasVersion,
    floorplanSegments,
    hoverRoomName,
    mode,
    referenceAnchorId,
    rooms,
    tags,
  ])

  const updateHover = useCallback((clientX: number, clientY: number) => {
    if (mode !== 'floor-plan' || !onRoomHover) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const [worldX, worldY] = screenToWorld(vpRef.current, clientX - rect.left, clientY - rect.top)
    const hovered = roomAtPoint(rooms, worldX, worldY)
    if (hovered !== hoverRoomRef.current) {
      hoverRoomRef.current = hovered
      onRoomHover(hovered)
    }
  }, [mode, onRoomHover, rooms])

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    dragRef.current = { x: e.clientX, y: e.clientY }
  }

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    updateHover(e.clientX, e.clientY)
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.x
    const dy = e.clientY - dragRef.current.y
    dragRef.current = { x: e.clientX, y: e.clientY }
    vpRef.current.offsetX += dx
    vpRef.current.offsetY += dy
    setCanvasVersion(version => version + 1)
  }

  const onMouseUp = () => { dragRef.current = null }

  const onClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (mode !== 'floor-plan' || !onRoomClick) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const [worldX, worldY] = screenToWorld(vpRef.current, e.clientX - rect.left, e.clientY - rect.top)
    const roomName = roomAtPoint(rooms, worldX, worldY)
    if (roomName) onRoomClick(roomName)
  }

  const onDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (mode !== 'floor-plan' || !onRoomDoubleClick) return
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const [worldX, worldY] = screenToWorld(vpRef.current, e.clientX - rect.left, e.clientY - rect.top)
    const roomName = roomAtPoint(rooms, worldX, worldY)
    if (roomName) onRoomDoubleClick(roomName)
  }

  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault()
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top
    const prev = vpRef.current
    const [worldX, worldY] = screenToWorld(prev, mouseX, mouseY)
    const nextScale = Math.max(2, Math.min(300, prev.scale * (e.deltaY < 0 ? 1.1 : 0.9)))
    vpRef.current = {
      scale: nextScale,
      offsetX: mouseX - worldX * nextScale,
      offsetY: mouseY - worldY * nextScale,
    }
    setCanvasVersion(version => version + 1)
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [onWheel])

  return (
    <canvas
      ref={canvasRef}
      className="rtls-map-canvas"
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={() => {
        dragRef.current = null
        hoverRoomRef.current = null
        onRoomHover?.(null)
      }}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
    />
  )
})

RTLSDashboardCanvas.displayName = 'RTLSDashboardCanvas'

export default RTLSDashboardCanvas
