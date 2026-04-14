import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from 'react'
import { ANCHOR_IDS, AnchorId, CalibrationMapRuntime, CalibrationTagRuntime } from './types'

export interface CalibrationMapCanvasHandle {
  resetView: (insets?: { rightInset?: number; bottomInset?: number }) => void
  zoomIn: () => void
  zoomOut: () => void
}

interface Props {
  map: CalibrationMapRuntime
  tags: CalibrationTagRuntime[]
  selectedTagId: string | null
  referenceDot: { x: number; y: number } | null
  referenceDotSelected: boolean
  placingReference: boolean
  onReferencePlaced: (x: number, y: number) => void
  onCancelReferencePlacement: () => void
  onMapChange: (map: CalibrationMapRuntime) => void
  onMapCommit: (map: CalibrationMapRuntime) => void
  onReferenceDotSelect: (selected: boolean) => void
  onReferenceDotDelete: () => void
  onAnchorDoubleClick: (anchorId: AnchorId, screenX: number, screenY: number) => void
  onReferenceDotDoubleClick: (screenX: number, screenY: number) => void
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

const BACKGROUND = '#0a0b0d'
const GRID = 'rgba(0,0,0,0)'
const AXIS = 'rgba(255,255,255,0.06)'
const LINE = 'rgba(255,255,255,0.25)'
const CROSSHAIR_COLOR = '#8c96a5'
const CROSSHAIR_SELECTED = '#c1c9d4'

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
  referenceDotSelected,
  placingReference,
  onReferencePlaced,
  onCancelReferencePlacement,
  onMapChange,
  onMapCommit,
  onReferenceDotSelect,
  onReferenceDotDelete,
  onAnchorDoubleClick,
  onReferenceDotDoubleClick,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [viewport, setViewport] = useState<Viewport>({ offsetX: 0, offsetY: 0, scale: 30 })
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 })
  const didInitViewRef = useRef(false)
  const dragRef = useRef<{ anchorId?: string; refDot?: boolean } | null>(null)
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

    const resetView = useCallback((insets?: { rightInset?: number; bottomInset?: number }) => {
      const canvas = canvasRef.current
      if (!canvas) return
      
      // If we somehow get a number (like from requestAnimationFrame directly), fallback to defaults
      const isEvent = typeof insets !== 'object' || insets === null
      const ri = (!isEvent && insets?.rightInset) != null ? insets!.rightInset! : 352
      const bi = (!isEvent && insets?.bottomInset) != null ? insets!.bottomInset! : 290
  
      const xs = anchorList.map(anchor => anchor.coords[0])
      const ys = anchorList.map(anchor => anchor.coords[1])
      const minX = Math.min(...xs)
      const maxX = Math.max(...xs)
      const minY = Math.min(...ys)
      const maxY = Math.max(...ys)
      const span = Math.max(maxX - minX, maxY - minY, 1)
      const availW = canvas.width - ri
      const availH = canvas.height - bi
      const scale = Math.min(availW, availH) * 0.45 / span
      const centerX = (minX + maxX) / 2
      const centerY = (minY + maxY) / 2
      setViewport({
        scale,
        offsetX: availW / 2 - centerX * scale,
        offsetY: availH / 2 + centerY * scale,
      })
    }, [anchorList])

  const zoomIn = useCallback(() => {
    setViewport(v => ({ ...v, scale: Math.min(v.scale * 1.25, 120) }))
  }, [])

  const zoomOut = useCallback(() => {
    setViewport(v => ({ ...v, scale: Math.max(v.scale / 1.25, 6) }))
  }, [])

  useImperativeHandle(ref, () => ({ resetView, zoomIn, zoomOut }), [resetView, zoomIn, zoomOut])

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
          requestAnimationFrame(() => resetView({ rightInset: 352, bottomInset: 290 }))
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
      ctx.beginPath(); ctx.moveTo(screenX, 0); ctx.lineTo(screenX, canvas.height); ctx.stroke()
    }
    for (let y = Math.floor(worldBottom / baseGrid) * baseGrid; y <= worldTop + baseGrid; y += baseGrid) {
      const [, screenY] = worldToScreen(viewport, 0, y)
      ctx.beginPath(); ctx.moveTo(0, screenY); ctx.lineTo(canvas.width, screenY); ctx.stroke()
    }


    // Axis lines removed per user request

    // ── Crosshair dotted lines to anchors ─────────────────────────
    if (referenceDot) {
      const [rx, ry] = worldToScreen(viewport, referenceDot.x, referenceDot.y)
      ctx.save()
      ctx.setLineDash([5, 6])
      ctx.lineWidth = 1
      for (const { anchorId, coords } of anchorList) {
        const [ax, ay] = worldToScreen(viewport, coords[0], coords[1])
        const dist = Math.hypot(referenceDot.x - coords[0], referenceDot.y - coords[1])
        ctx.strokeStyle = ANCHOR_COLORS[anchorId] + '66'
        ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(ax, ay); ctx.stroke()

        // Distance label aligned along line
        const mx = (rx + ax) / 2
        const my = (ry + ay) / 2
        const angle = Math.atan2(ay - ry, ax - rx)
        const label = `${dist.toFixed(2)} ft`
        ctx.save()
        ctx.setLineDash([])
        ctx.translate(mx, my)
        // Flip label so it's always readable (not upside down)
        const normAngle = ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)
        const flipped = normAngle > Math.PI / 2 && normAngle < Math.PI * 1.5
        ctx.rotate(flipped ? angle + Math.PI : angle)
        ctx.font = '10px var(--font-primary, sans-serif)'
        ctx.textAlign = 'center'
        const metrics = ctx.measureText(label)
        ctx.fillStyle = 'rgba(21, 21, 21, 0.75)'
        ctx.fillRect(-metrics.width / 2 - 3, -15, metrics.width + 6, 13)
        ctx.fillStyle = '#ffffff'
        ctx.fillText(label, 0, -4)
        ctx.restore()
      }
      ctx.restore()
    }

    // ── Map lines ──────────────────────────────────────────────────
    ctx.strokeStyle = LINE
    ctx.lineWidth = 2
    ctx.fillStyle = '#8ea4c8'
    ctx.font = '12px var(--font-primary, sans-serif)'
    ctx.setLineDash([])
    for (const [anchorA, anchorB] of map.lines) {
      const pointA = map.anchors[anchorA]
      const pointB = map.anchors[anchorB]
      if (!pointA || !pointB) continue
      const [x1, y1] = worldToScreen(viewport, pointA[0], pointA[1])
      const [x2, y2] = worldToScreen(viewport, pointB[0], pointB[1])
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
      const distance = Math.hypot(pointB[0] - pointA[0], pointB[1] - pointA[1])
      ctx.fillText(`${distance.toFixed(1)} ft`, (x1 + x2) / 2 + 8, (y1 + y2) / 2 - 8)
    }

    // ── Anchor dots ────────────────────────────────────────────────
    for (const { anchorId, coords } of anchorList) {
      const [screenX, screenY] = worldToScreen(viewport, coords[0], coords[1])
      ctx.fillStyle = ANCHOR_COLORS[anchorId]
      ctx.strokeStyle = '#f0f4ff'
      ctx.lineWidth = 2
      ctx.setLineDash([])
      ctx.beginPath(); ctx.arc(screenX, screenY, 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
      ctx.fillStyle = ANCHOR_COLORS[anchorId]
      ctx.font = 'bold 12px var(--font-primary, sans-serif)'
      ctx.fillText(anchorId, screenX + 10, screenY - 4)
      ctx.fillStyle = '#9ab2d8'
      ctx.font = '11px var(--font-mono, monospace)'
      ctx.fillText(`(${coords[0].toFixed(1)}, ${coords[1].toFixed(1)})`, screenX + 10, screenY + 12)
    }

    // ── Reference crosshair — small + with coordinates ─────────────
    if (referenceDot) {
      const [screenX, screenY] = worldToScreen(viewport, referenceDot.x, referenceDot.y)
      const color = referenceDotSelected ? CROSSHAIR_SELECTED : CROSSHAIR_COLOR
      ctx.strokeStyle = color
      ctx.lineWidth = referenceDotSelected ? 1.8 : 1.2
      ctx.setLineDash([])

      // Draw small + crosshair arms (8px)
      const arm = 8
      ctx.beginPath()
      ctx.moveTo(screenX - arm, screenY); ctx.lineTo(screenX + arm, screenY)
      ctx.moveTo(screenX, screenY - arm); ctx.lineTo(screenX, screenY + arm)
      ctx.stroke()

      // Coordinate label beside crosshair
      ctx.font = '9px var(--font-primary, sans-serif)'
      ctx.fillStyle = color
      ctx.fillText(`(${referenceDot.x.toFixed(1)}, ${referenceDot.y.toFixed(1)})`, screenX + arm + 4, screenY - arm)

      // Dashed lines to anchors with distance labels
      ctx.save()
      ctx.setLineDash([4, 4])
      ctx.lineWidth = 1
      for (const { anchorId, coords } of anchorList) {
        const [ax, ay] = worldToScreen(viewport, coords[0], coords[1])
        const floorDist = Math.hypot(referenceDot.x - coords[0], referenceDot.y - coords[1])
        ctx.strokeStyle = '#8c96a566' // Gray lines
        ctx.beginPath(); ctx.moveTo(screenX, screenY); ctx.lineTo(ax, ay); ctx.stroke()
        const mx = (screenX + ax) / 2
        const my = (screenY + ay) / 2
        ctx.setLineDash([])
        ctx.font = '8px var(--font-primary, sans-serif)'
        ctx.fillStyle = '#8c96a5' // Gray text
        ctx.fillText(`${floorDist.toFixed(2)} ft`, mx + 4, my - 4)
        ctx.setLineDash([4, 4])
      }
      ctx.restore()
    }

    // ── Tags ───────────────────────────────────────────────────────
    tags.forEach((tag, index) => {
      const tagColor = TAG_COLORS[index % TAG_COLORS.length]
      if (tag.raw_xy) {
        const [screenX, screenY] = worldToScreen(viewport, tag.raw_xy[0], tag.raw_xy[1])
        ctx.save()
        ctx.translate(screenX, screenY); ctx.rotate(Math.PI / 4)
        ctx.fillStyle = 'rgba(255,255,255,0.15)'
        ctx.strokeStyle = tagColor; ctx.lineWidth = 1.5
        ctx.setLineDash([])
        ctx.fillRect(-6, -6, 12, 12); ctx.strokeRect(-6, -6, 12, 12)
        ctx.restore()
      }
      if (tag.calibrated_xy) {
        const [screenX, screenY] = worldToScreen(viewport, tag.calibrated_xy[0], tag.calibrated_xy[1])
        ctx.fillStyle = tagColor
        ctx.strokeStyle = selectedTagId === tag.tag_id ? '#ffffff' : tagColor
        ctx.lineWidth = selectedTagId === tag.tag_id ? 2 : 1.4
        ctx.setLineDash([])
        ctx.beginPath()
        ctx.arc(screenX, screenY, selectedTagId === tag.tag_id ? 8 : 6, 0, Math.PI * 2)
        ctx.fill(); ctx.stroke()
        ctx.fillStyle = tagColor
        ctx.font = 'bold 12px var(--font-primary, sans-serif)'
        ctx.fillText(tag.tag_id, screenX + 10, screenY - 4)
      }
    })
  }, [anchorList, canvasSize, map.anchors, map.lines, referenceDot, referenceDotSelected, selectedTagId, tags, viewport])

  // ── Hit testing ─────────────────────────────────────────────────

  const hitAnchor = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    for (const { anchorId, coords } of anchorList) {
      const [screenX, screenY] = worldToScreen(viewport, coords[0], coords[1])
      if (Math.hypot(x - screenX, y - screenY) <= 14) return anchorId
    }
    return null
  }, [anchorList, viewport])

  const hitRefDot = useCallback((clientX: number, clientY: number): boolean => {
    if (!referenceDot) return false
    const canvas = canvasRef.current
    if (!canvas) return false
    const rect = canvas.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    const [screenX, screenY] = worldToScreen(viewport, referenceDot.x, referenceDot.y)
    return Math.hypot(x - screenX, y - screenY) <= 18
  }, [referenceDot, viewport])

  const getScreenPos = useCallback((clientX: number, clientY: number): [number, number] => {
    const canvas = canvasRef.current
    if (!canvas) return [clientX, clientY]
    const rect = canvas.getBoundingClientRect()
    return [clientX - rect.left, clientY - rect.top]
  }, [])

  // ── Mouse handlers ───────────────────────────────────────────────

  const handleMouseDown = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas || event.button !== 0) return
    // Let doubleClick handle double-clicks
    if (event.detail >= 2) return
    canvas.focus()

    const rect = canvas.getBoundingClientRect()
    const x = event.clientX - rect.left
    const y = event.clientY - rect.top
    const [worldX, worldY] = screenToWorld(viewport, x, y)

    if (placingReference) {
      onReferencePlaced(Number(worldX.toFixed(3)), Number(worldY.toFixed(3)))
      return
    }

    // Hit: anchor drag
    const anchorId = hitAnchor(event.clientX, event.clientY)
    if (anchorId) {
      onReferenceDotSelect(false)
      dragRef.current = { anchorId }
      return
    }

    // Hit: ref dot select
    if (hitRefDot(event.clientX, event.clientY)) {
      onReferenceDotSelect(true)
      dragRef.current = { refDot: true }
      return
    }

    // Miss: deselect ref dot and start pan
    onReferenceDotSelect(false)
    panRef.current = { active: true, x: event.clientX, y: event.clientY }
  }, [hitAnchor, hitRefDot, onReferencePlaced, onReferenceDotSelect, placingReference, viewport])

  const handleDoubleClick = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    if (placingReference) return

    // Hit: anchor double-click → edit
    const anchorId = hitAnchor(event.clientX, event.clientY) as AnchorId | null
    if (anchorId) {
      const [sx, sy] = getScreenPos(event.clientX, event.clientY)
      onAnchorDoubleClick(anchorId, sx, sy)
      return
    }

    // Hit: ref dot double-click → edit
    if (hitRefDot(event.clientX, event.clientY)) {
      const [sx, sy] = getScreenPos(event.clientX, event.clientY)
      onReferenceDotDoubleClick(sx, sy)
    }
  }, [getScreenPos, hitAnchor, hitRefDot, onAnchorDoubleClick, onReferenceDotDoubleClick, placingReference])

  const handleMouseMove = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    if (dragRef.current) {
      const canvas = canvasRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      const [worldX, worldY] = screenToWorld(viewport, event.clientX - rect.left, event.clientY - rect.top)
      
      if (dragRef.current.anchorId) {
        const nextMap: CalibrationMapRuntime = {
          ...latestMapRef.current,
          anchors: {
            ...latestMapRef.current.anchors,
            [dragRef.current.anchorId]: [Number(worldX.toFixed(3)), Number(worldY.toFixed(3))],
          },
        }
        latestMapRef.current = nextMap
        onMapChange(nextMap)
      } else if (dragRef.current.refDot) {
        onReferencePlaced(Number(worldX.toFixed(3)), Number(worldY.toFixed(3)))
      }
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
    if ((event.key === 'Delete' || event.key === 'Backspace') && referenceDotSelected) {
      onReferenceDotDelete()
      event.preventDefault()
    }
  }, [onCancelReferencePlacement, onReferenceDotDelete, placingReference, referenceDotSelected, resetView])

  const getCursor = () => {
    if (placingReference) return 'crosshair'
    if (dragRef.current || panRef.current?.active) return 'grabbing'
    return 'grab'
  }

  return (
    <canvas
      ref={canvasRef}
      className="ct-map-canvas"
      tabIndex={0}
      onContextMenu={event => event.preventDefault()}
      onMouseDown={handleMouseDown}
      onDoubleClick={handleDoubleClick}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
      onKeyDown={handleKeyDown}
      style={{ cursor: getCursor() }}
    />
  )
})

CalibrationMapCanvas.displayName = 'CalibrationMapCanvas'

export default CalibrationMapCanvas
