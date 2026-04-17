import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import { AnchorData, RoomData, SegmentData } from '../../../types'
import { chainSegmentsToPolygon } from '../AnchorManagerModule/anchorGeometry'
import { RTLSTagState } from './RTLSDashboardCanvas'

export interface RTLSRoomViewHandle {
  resetView: () => void
  zoomIn: () => void
  zoomOut: () => void
}

interface Props {
  room: RoomData
  tags: RTLSTagState[]
  activeSolveRoomName: string | null
  referenceAnchorId?: string
}

interface Viewport {
  offsetX: number
  offsetY: number
  scale: number
}

const COLORS = {
  bg: '#0a0b0d',
  segment: '#314052',
  roomBoundary: '#4a9eff',
  roomFill: 'rgba(74, 158, 255, 0.08)',
  anchor: '#ff9b38',
  anchorRef: '#ffd166',
  anchorLabel: '#ffffff',
}

const worldToScreen = (vp: Viewport, wx: number, wy: number): [number, number] => (
  [wx * vp.scale + vp.offsetX, wy * vp.scale + vp.offsetY]
)

const screenToWorld = (vp: Viewport, sx: number, sy: number): [number, number] => (
  [(sx - vp.offsetX) / vp.scale, (sy - vp.offsetY) / vp.scale]
)

const toLocalPoint = (room: RoomData, x: number, y: number): [number, number] => ([
  x - room.room_bounds_ft.min_x,
  y - room.room_bounds_ft.min_y,
])

const toLocalSegment = (room: RoomData, segment: SegmentData): SegmentData => {
  const [x1, y1] = toLocalPoint(room, segment.x1, segment.y1)
  const [x2, y2] = toLocalPoint(room, segment.x2, segment.y2)
  return { x1, y1, x2, y2 }
}

const polygonPoints = (segments: SegmentData[]): [number, number][] => chainSegmentsToPolygon(segments)

const RTLSRoomView = forwardRef<RTLSRoomViewHandle, Props>(({
  room,
  tags,
  activeSolveRoomName,
  referenceAnchorId,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const viewportRef = useRef<Viewport>({ offsetX: 0, offsetY: 0, scale: 20 })
  const dragRef = useRef<{ x: number; y: number } | null>(null)
  const [version, setVersion] = useState(0)

  const localBoundary = room.segments_ft.map(segment => toLocalSegment(room, segment))
  const localInterior = room.interior_segments_ft.map(segment => toLocalSegment(room, segment))
  const localPolygon = polygonPoints(localBoundary)
  const activeReferenceAnchor = room.anchors.find(anchor => (
    anchor.id === (room.reference_anchor_id ?? null)
    || (!!referenceAnchorId && (anchor.hw_id === referenceAnchorId || anchor.id === referenceAnchorId))
  )) ?? null
  const localTags = tags
    .filter(tag => tag.position)
    .map(tag => {
      const [x, y] = toLocalPoint(room, tag.position!.x, tag.position!.y)
      return { ...tag, localX: x, localY: y }
    })
    .filter(tag => (
      tag.localX >= -0.25
      && tag.localX <= room.room_bounds_ft.width + 0.25
      && tag.localY >= -0.25
      && tag.localY <= room.room_bounds_ft.height + 0.25
    ))

  const resetView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const width = Math.max(room.room_bounds_ft.width, 1)
    const height = Math.max(room.room_bounds_ft.height, 1)
    const padding = 70
    const scale = Math.min(
      (canvas.width - padding * 2) / width,
      (canvas.height - padding * 2) / height,
    )
    viewportRef.current = {
      scale: Math.max(2, scale),
      offsetX: (canvas.width - width * Math.max(2, scale)) / 2,
      offsetY: (canvas.height - height * Math.max(2, scale)) / 2,
    }
    setVersion(current => current + 1)
  }, [room.room_bounds_ft.height, room.room_bounds_ft.width])

  const zoomBy = useCallback((factor: number) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const pivotX = canvas.width / 2
    const pivotY = canvas.height / 2
    const current = viewportRef.current
    const nextScale = Math.max(2, Math.min(320, current.scale * factor))
    viewportRef.current = {
      scale: nextScale,
      offsetX: pivotX - (pivotX - current.offsetX) * (nextScale / current.scale),
      offsetY: pivotY - (pivotY - current.offsetY) * (nextScale / current.scale),
    }
    setVersion(value => value + 1)
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
    resetView()
  }, [resetView, room.room_name])

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return

    const viewport = viewportRef.current
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = COLORS.bg
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    if (localPolygon.length >= 3) {
      ctx.fillStyle = COLORS.roomFill
      ctx.beginPath()
      const [x0, y0] = worldToScreen(viewport, localPolygon[0][0], localPolygon[0][1])
      ctx.moveTo(x0, y0)
      for (let i = 1; i < localPolygon.length; i++) {
        const [x, y] = worldToScreen(viewport, localPolygon[i][0], localPolygon[i][1])
        ctx.lineTo(x, y)
      }
      ctx.closePath()
      ctx.fill()
    }

    for (const segment of localInterior) {
      const [x1, y1] = worldToScreen(viewport, segment.x1, segment.y1)
      const [x2, y2] = worldToScreen(viewport, segment.x2, segment.y2)
      ctx.strokeStyle = COLORS.segment
      ctx.lineWidth = 1.1
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    for (const segment of localBoundary) {
      const [x1, y1] = worldToScreen(viewport, segment.x1, segment.y1)
      const [x2, y2] = worldToScreen(viewport, segment.x2, segment.y2)
      ctx.strokeStyle = COLORS.roomBoundary
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    const refLocalX = activeReferenceAnchor?.x_ft ?? 0
    const refLocalY = activeReferenceAnchor?.y_ft ?? 0

    for (const anchor of room.anchors) {
      const [sx, sy] = worldToScreen(viewport, anchor.x_ft, anchor.y_ft)
      const isReference = anchor === activeReferenceAnchor
      const radius = isReference ? 8 : 6

      if (isReference) {
        ctx.beginPath()
        ctx.arc(sx, sy, radius + 4, 0, Math.PI * 2)
        ctx.strokeStyle = COLORS.anchorRef
        ctx.lineWidth = 1.5
        ctx.setLineDash([3, 2])
        ctx.stroke()
        ctx.setLineDash([])
      }

      ctx.beginPath()
      ctx.arc(sx, sy, radius, 0, Math.PI * 2)
      ctx.fillStyle = isReference ? COLORS.anchorRef : COLORS.anchor
      ctx.fill()
      ctx.strokeStyle = 'rgba(255,255,255,0.3)'
      ctx.lineWidth = 1
      ctx.stroke()

      ctx.fillStyle = COLORS.anchorLabel
      ctx.font = 'bold 11px "SF Mono", monospace'
      ctx.textAlign = 'left'
      ctx.textBaseline = 'bottom'
      const label = isReference
        ? `${anchor.hw_id || anchor.id} ★ (0.0, 0.0)`
        : `${anchor.hw_id || anchor.id} (${(anchor.x_ft - refLocalX).toFixed(1)}, ${(anchor.y_ft - refLocalY).toFixed(1)})`
      ctx.fillText(label, sx + 10, sy - 4)
    }

    for (const tag of localTags) {
      const [sx, sy] = worldToScreen(viewport, tag.localX, tag.localY)
      const radius = 8
      const glow = ctx.createRadialGradient(sx, sy, 0, sx, sy, radius * 2.5)
      glow.addColorStop(0, `${tag.color}66`)
      glow.addColorStop(1, 'transparent')
      ctx.beginPath()
      ctx.arc(sx, sy, radius * 2.5, 0, Math.PI * 2)
      ctx.fillStyle = glow
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

      ctx.fillStyle = 'rgba(200, 220, 255, 0.7)'
      ctx.font = '9px sans-serif'
      ctx.fillText(
        `(${(tag.localX - refLocalX).toFixed(2)}, ${(tag.localY - refLocalY).toFixed(2)}) ft`,
        sx + 14,
        sy + 12,
      )
    }

    if (localTags.length === 0) {
      ctx.fillStyle = 'rgba(180, 194, 214, 0.7)'
      ctx.font = '12px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(
        activeSolveRoomName === room.room_name
          ? 'Waiting for live RTLS positions...'
          : `Room tab open. Active solve room is ${activeSolveRoomName || 'not selected'}.`,
        canvas.width / 2,
        24,
      )
    }
  }, [activeReferenceAnchor, activeSolveRoomName, localBoundary, localInterior, localPolygon, localTags, room, version])

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    dragRef.current = { x: e.clientX, y: e.clientY }
  }

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!dragRef.current) return
    const dx = e.clientX - dragRef.current.x
    const dy = e.clientY - dragRef.current.y
    dragRef.current = { x: e.clientX, y: e.clientY }
    viewportRef.current.offsetX += dx
    viewportRef.current.offsetY += dy
    setVersion(current => current + 1)
  }

  const onMouseUp = () => {
    dragRef.current = null
  }

  const onWheel = useCallback((e: WheelEvent) => {
    e.preventDefault()
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top
    const current = viewportRef.current
    const [worldX, worldY] = screenToWorld(current, mouseX, mouseY)
    const nextScale = Math.max(2, Math.min(320, current.scale * (e.deltaY < 0 ? 1.1 : 0.9)))
    viewportRef.current = {
      scale: nextScale,
      offsetX: mouseX - worldX * nextScale,
      offsetY: mouseY - worldY * nextScale,
    }
    setVersion(value => value + 1)
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    canvas.addEventListener('wheel', onWheel, { passive: false })
    return () => canvas.removeEventListener('wheel', onWheel)
  }, [onWheel])

  return (
    <div className="rtls-room-view">
      <div className="rtls-room-view__header">
        <div className="rtls-room-view__title">{room.room_name}</div>
        <div className="rtls-room-view__meta">
          {room.room_bounds_ft.width.toFixed(1)} × {room.room_bounds_ft.height.toFixed(1)} ft
          {' · '}
          {room.anchors.length} anchor{room.anchors.length !== 1 ? 's' : ''}
          {' · '}
          Ref: {activeReferenceAnchor?.hw_id || activeReferenceAnchor?.id || '—'}
        </div>
      </div>
      <canvas
        ref={canvasRef}
        className="rtls-room-view__canvas"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
      />
    </div>
  )
})

RTLSRoomView.displayName = 'RTLSRoomView'

export default RTLSRoomView
