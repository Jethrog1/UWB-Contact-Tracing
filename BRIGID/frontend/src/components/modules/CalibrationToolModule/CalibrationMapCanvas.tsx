import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react'
import { ANCHOR_IDS, CalibrationMapRuntime, CalibrationTagRuntime } from './types'

export interface CalibrationMapCanvasHandle {
  resetView: () => void
}

interface Props {
  map: CalibrationMapRuntime
  tags: CalibrationTagRuntime[]
  selectedTagId: string | null
  referenceDot: { x: number; y: number } | null
  placingReference: boolean
  onReferencePlaced: (x: number, y: number) => void
  onCancelReferencePlacement: () => void
  onMapChange: (map: CalibrationMapRuntime) => void
  onMapCommit: (map: CalibrationMapRuntime) => void
}

interface Viewport {
  offsetX: number
  offsetY: number
  scale: number
}

const ANCHOR_COLORS: Record<string, string> = {
  A0: '#ff5b4d',
  A1: '#42d17e',
  A2: '#ae62ff',
  A3: '#ffb11f',
}

const TAG_COLORS = ['#00f0d0', '#ffc44d', '#d16cff', '#78d0ff', '#8ee36b']

const BACKGROUND = '#151515'
const GRID = 'rgba(255,255,255,0.085)'
const AXIS = 'rgba(255,255,255,0.16)'
const LINE = '#f3f3f3'

const worldToScreen = (viewport: Viewport, x: number, y: number): [number, number] => (
  [viewport.offsetX + x * viewport.scale, viewport.offsetY - y * viewport.scale]
)

const screenToWorld = (viewport: Viewport, x: number, y: number): [number, number] => (
  [(x - viewport.offsetX) / viewport.scale, (viewport.offsetY - y) / viewport.scale]
)

const CalibrationMapCanvas = forwardRef<CalibrationMapCanvasHandle, Props>(({
  map,
  tags,
  selectedTagId,
  referenceDot,
  placingReference,
  onReferencePlaced,
  onCancelReferencePlacement,
  onMapChange,
  onMapCommit,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [viewport, setViewport] = useState<Viewport>({ offsetX: 0, offsetY: 0, scale: 30 })
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 })
  const didInitViewRef = useRef(false)
  const dragRef = useRef<{ anchorId: string } | null>(null)
  const panRef = useRef<{ active: boolean; x: number; y: number } | null>(null)
  const latestMapRef = useRef(map)

  latestMapRef.current = map

  const anchorList = useMemo(
    () => ANCHOR_IDS.map(anchorId => ({
      anchorId,
      coords: map.anchors[anchorId] ?? [0, 0],
    })),
    [map.anchors],
  )

  const resetView = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const xs = anchorList.map(anchor => anchor.coords[0])
    const ys = anchorList.map(anchor => anchor.coords[1])
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const span = Math.max(maxX - minX, maxY - minY, 1)
    const scale = Math.min(canvas.width, canvas.height) * 0.45 / span
    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2
    setViewport({
      scale,
      offsetX: canvas.width / 2 - centerX * scale,
      offsetY: canvas.height / 2 + centerY * scale,
    })
  }, [anchorList])

  useImperativeHandle(ref, () => ({ resetView }), [resetView])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const resize = () => {
      const nextWidth = canvas.offsetWidth
      const nextHeight = canvas.offsetHeight
      if (nextWidth > 0 && nextHeight > 0) {
        if (canvas.width !== nextWidth) canvas.width = nextWidth
        if (canvas.height !== nextHeight) canvas.height = nextHeight
        setCanvasSize(current => (
          current.width === nextWidth && current.height === nextHeight
            ? current
            : { width: nextWidth, height: nextHeight }
        ))
        if (!didInitViewRef.current) {
          didInitViewRef.current = true
          requestAnimationFrame(resetView)
        }
      }
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    requestAnimationFrame(resize)
    return () => observer.disconnect()
  }, [resetView])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    if (canvasSize.width <= 0 || canvasSize.height <= 0) return

    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = BACKGROUND
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    const worldLeft = screenToWorld(viewport, 0, canvas.height)[0]
    const worldRight = screenToWorld(viewport, canvas.width, 0)[0]
    const worldBottom = screenToWorld(viewport, 0, canvas.height)[1]
    const worldTop = screenToWorld(viewport, 0, 0)[1]
    const baseGrid = viewport.scale > 50 ? 2.5 : viewport.scale > 22 ? 5 : 10

    ctx.strokeStyle = GRID
    ctx.lineWidth = 1
    for (let x = Math.floor(worldLeft / baseGrid) * baseGrid; x <= worldRight + baseGrid; x += baseGrid) {
      const [screenX] = worldToScreen(viewport, x, 0)
      ctx.beginPath()
      ctx.moveTo(screenX, 0)
      ctx.lineTo(screenX, canvas.height)
      ctx.stroke()
    }
    for (let y = Math.floor(worldBottom / baseGrid) * baseGrid; y <= worldTop + baseGrid; y += baseGrid) {
      const [, screenY] = worldToScreen(viewport, 0, y)
      ctx.beginPath()
      ctx.moveTo(0, screenY)
      ctx.lineTo(canvas.width, screenY)
      ctx.stroke()
    }

    ctx.strokeStyle = AXIS
    const [axisX] = worldToScreen(viewport, 0, 0)
    const [, axisY] = worldToScreen(viewport, 0, 0)
    ctx.beginPath()
    ctx.moveTo(axisX, 0)
    ctx.lineTo(axisX, canvas.height)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(0, axisY)
    ctx.lineTo(canvas.width, axisY)
    ctx.stroke()

    ctx.strokeStyle = LINE
    ctx.lineWidth = 2
    ctx.fillStyle = '#8ea4c8'
    ctx.font = '12px var(--font-primary)'
    for (const [anchorA, anchorB] of map.lines) {
      const pointA = map.anchors[anchorA]
      const pointB = map.anchors[anchorB]
      if (!pointA || !pointB) continue
      const [x1, y1] = worldToScreen(viewport, pointA[0], pointA[1])
      const [x2, y2] = worldToScreen(viewport, pointB[0], pointB[1])
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()

      const distance = Math.hypot(pointB[0] - pointA[0], pointB[1] - pointA[1])
      ctx.fillText(`${distance.toFixed(1)} ft`, (x1 + x2) / 2 + 8, (y1 + y2) / 2 - 8)
    }

    for (const { anchorId, coords } of anchorList) {
      const [screenX, screenY] = worldToScreen(viewport, coords[0], coords[1])
      ctx.fillStyle = ANCHOR_COLORS[anchorId]
      ctx.strokeStyle = '#f0f4ff'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(screenX, screenY, 8, 0, Math.PI * 2)
      ctx.fill()
      ctx.stroke()

      ctx.fillStyle = ANCHOR_COLORS[anchorId]
      ctx.font = 'bold 12px var(--font-primary)'
      ctx.fillText(anchorId, screenX + 10, screenY - 4)
      ctx.fillStyle = '#9ab2d8'
      ctx.font = '11px var(--font-mono)'
      ctx.fillText(`(${coords[0].toFixed(1)}, ${coords[1].toFixed(1)})`, screenX + 10, screenY + 12)
    }

    if (referenceDot) {
      const [screenX, screenY] = worldToScreen(viewport, referenceDot.x, referenceDot.y)
      ctx.strokeStyle = '#7de9ff'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(screenX, screenY, 10, 0, Math.PI * 2)
      ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(screenX - 14, screenY)
      ctx.lineTo(screenX + 14, screenY)
      ctx.moveTo(screenX, screenY - 14)
      ctx.lineTo(screenX, screenY + 14)
      ctx.stroke()
    }

    tags.forEach((tag, index) => {
      const tagColor = TAG_COLORS[index % TAG_COLORS.length]
      if (tag.raw_xy) {
        const [screenX, screenY] = worldToScreen(viewport, tag.raw_xy[0], tag.raw_xy[1])
        ctx.save()
        ctx.translate(screenX, screenY)
        ctx.rotate(Math.PI / 4)
        ctx.fillStyle = 'rgba(255,255,255,0.15)'
        ctx.strokeStyle = tagColor
        ctx.lineWidth = 1.5
        ctx.fillRect(-6, -6, 12, 12)
        ctx.strokeRect(-6, -6, 12, 12)
        ctx.restore()
      }
      if (tag.calibrated_xy) {
        const [screenX, screenY] = worldToScreen(viewport, tag.calibrated_xy[0], tag.calibrated_xy[1])
        ctx.fillStyle = tagColor
        ctx.strokeStyle = selectedTagId === tag.tag_id ? '#ffffff' : tagColor
        ctx.lineWidth = selectedTagId === tag.tag_id ? 2 : 1.4
        ctx.beginPath()
        ctx.arc(screenX, screenY, selectedTagId === tag.tag_id ? 8 : 6, 0, Math.PI * 2)
        ctx.fill()
        ctx.stroke()
        ctx.fillStyle = tagColor
        ctx.font = 'bold 12px var(--font-primary)'
        ctx.fillText(tag.tag_id, screenX + 10, screenY - 4)
      }
    })
  }, [anchorList, canvasSize, map.anchors, map.lines, referenceDot, selectedTagId, tags, viewport])

  const hitAnchor = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    for (const { anchorId, coords } of anchorList) {
      const [screenX, screenY] = worldToScreen(viewport, coords[0], coords[1])
      if (Math.hypot(x - screenX, y - screenY) <= 12) return anchorId
    }
    return null
  }, [anchorList, viewport])

  const handleMouseDown = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas || event.button !== 0) return
    canvas.focus()
    const rect = canvas.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    const [worldX, worldY] = screenToWorld(viewport, x, y)

    if (placingReference) {
      onReferencePlaced(Number(worldX.toFixed(3)), Number(worldY.toFixed(3)))
      return
    }

    const anchorId = hitAnchor(event.clientX, event.clientY)
    if (anchorId) {
      dragRef.current = { anchorId }
      return
    }

    panRef.current = { active: true, x: event.clientX, y: event.clientY }
  }, [hitAnchor, onReferencePlaced, placingReference, viewport])

  const handleMouseMove = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    if (dragRef.current) {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const [worldX, worldY] = screenToWorld(viewport, event.clientX - rect.left, event.clientY - rect.top)
      const nextMap: CalibrationMapRuntime = {
        ...latestMapRef.current,
        anchors: {
          ...latestMapRef.current.anchors,
          [dragRef.current.anchorId]: [Number(worldX.toFixed(3)), Number(worldY.toFixed(3))],
        },
      }
      latestMapRef.current = nextMap
      onMapChange(nextMap)
      return
    }

    if (panRef.current?.active) {
      const dx = event.clientX - panRef.current.x
      const dy = event.clientY - panRef.current.y
      panRef.current = { ...panRef.current, x: event.clientX, y: event.clientY }
      setViewport(current => ({
        ...current,
        offsetX: current.offsetX + dx,
        offsetY: current.offsetY + dy,
      }))
    }
  }, [onMapChange, viewport])

  const handleMouseUp = useCallback(() => {
    if (dragRef.current) {
      dragRef.current = null
      onMapCommit(latestMapRef.current)
    }
    panRef.current = null
  }, [onMapCommit])

  const handleWheel = useCallback((event: React.WheelEvent<HTMLCanvasElement>) => {
    event.preventDefault()
    const rect = event.currentTarget.getBoundingClientRect()
    const pointerX = event.clientX - rect.left
    const pointerY = event.clientY - rect.top
    setViewport(current => {
      const nextScale = Math.max(6, Math.min(120, current.scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12)))
      return {
        scale: nextScale,
        offsetX: pointerX - (pointerX - current.offsetX) * (nextScale / current.scale),
        offsetY: pointerY - (pointerY - current.offsetY) * (nextScale / current.scale),
      }
    })
  }, [])

  const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLCanvasElement>) => {
    if (event.key === 'Escape') {
      dragRef.current = null
      panRef.current = null
      if (placingReference) onCancelReferencePlacement()
      event.preventDefault()
    }
    if (event.key === 'f' || event.key === 'F') {
      resetView()
      event.preventDefault()
    }
  }, [onCancelReferencePlacement, placingReference, resetView])

  return (
    <canvas
      ref={canvasRef}
      className="ct-map-canvas"
      tabIndex={0}
      onContextMenu={event => event.preventDefault()}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      onKeyDown={handleKeyDown}
      style={{ cursor: placingReference ? 'crosshair' : dragRef.current || panRef.current ? 'grabbing' : 'grab' }}
    />
  )
})

CalibrationMapCanvas.displayName = 'CalibrationMapCanvas'

export default CalibrationMapCanvas
