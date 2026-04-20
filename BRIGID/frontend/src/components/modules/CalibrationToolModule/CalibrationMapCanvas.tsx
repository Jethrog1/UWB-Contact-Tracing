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
  onAnchorDragStart?: () => void
  onReferenceDotSelect: (selected: boolean) => void
  onReferenceDotDelete: () => void
  onAnchorDoubleClick: (anchorId: AnchorId, screenX: number, screenY: number) => void
  onReferenceDotDoubleClick: (screenX: number, screenY: number) => void
  selectedLineKey: string | null
  onLineSelect: (key: string | null) => void
  onLineDelete: (key: string) => void
  onLineCreate: (a: AnchorId, b: AnchorId) => void
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
const LINE = 'rgba(255,255,255,0.25)'
const LINE_SELECTED = '#ff3b3b'
const CROSSHAIR_COLOR = '#8c96a5'
const CROSSHAIR_SELECTED = '#c1c9d4'

const worldToScreen = (viewport: Viewport, x: number, y: number): [number, number] => (
  [viewport.offsetX + x * viewport.scale, viewport.offsetY - y * viewport.scale]
)

const screenToWorld = (viewport: Viewport, x: number, y: number): [number, number] => (
  [(x - viewport.offsetX) / viewport.scale, (viewport.offsetY - y) / viewport.scale]
)

const lineKey = (a: string, b: string) => `${a}-${b}`

// Point-to-segment distance in screen coordinates.
const distToSegment = (px: number, py: number, x1: number, y1: number, x2: number, y2: number) => {
  const dx = x2 - x1
  const dy = y2 - y1
  const lenSq = dx * dx + dy * dy
  if (lenSq === 0) return Math.hypot(px - x1, py - y1)
  let t = ((px - x1) * dx + (py - y1) * dy) / lenSq
  t = Math.max(0, Math.min(1, t))
  const cx = x1 + t * dx
  const cy = y1 + t * dy
  return Math.hypot(px - cx, py - cy)
}

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
  onAnchorDragStart,
  onReferenceDotSelect,
  onReferenceDotDelete,
  onAnchorDoubleClick,
  onReferenceDotDoubleClick,
  selectedLineKey,
  onLineSelect,
  onLineDelete,
  onLineCreate,
}, ref) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [viewport, setViewport] = useState<Viewport>({ offsetX: 0, offsetY: 0, scale: 30 })
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 })
  const didInitViewRef = useRef(false)
  const dragRef = useRef<{ anchorId?: string; refDot?: boolean; localRef?: { x: number; y: number } } | null>(null)
  const panRef = useRef<{ active: boolean; x: number; y: number } | null>(null)
  const latestMapRef = useRef(map)
  // Local-only reference-dot position used during drag so we don't wait on the
  // backend round-trip between mousemove events.
  const [dragRefPos, setDragRefPos] = useState<{ x: number; y: number } | null>(null)

  // Line-creation state: user holds ctrl and clicks an anchor to start, then
  // clicks a second anchor to commit. Ctrl is not required after the first click.
  const [creatingFrom, setCreatingFrom] = useState<AnchorId | null>(null)
  const [hoverAnchor, setHoverAnchor] = useState<AnchorId | null>(null)
  const [cursorWorld, setCursorWorld] = useState<{ x: number; y: number } | null>(null)
  const [ctrlDown, setCtrlDown] = useState(false)

  latestMapRef.current = map

  // Effective reference dot: prefer in-progress drag pos so motion is instant.
  const effectiveRef = dragRefPos ?? referenceDot

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

  // Track Ctrl key globally so the canvas knows whether we're in line-start mode.
  useEffect(() => {
    const down = (e: KeyboardEvent) => { if (e.key === 'Control' || e.ctrlKey) setCtrlDown(true) }
    const up = (e: KeyboardEvent) => { if (e.key === 'Control' || !e.ctrlKey) setCtrlDown(false) }
    const blur = () => setCtrlDown(false)
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('blur', blur)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', blur)
    }
  }, [])

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

    // ── Crosshair dotted lines to anchors ─────────────────────────
    if (effectiveRef) {
      const [rx, ry] = worldToScreen(viewport, effectiveRef.x, effectiveRef.y)
      ctx.save()
      ctx.setLineDash([5, 6])
      ctx.lineWidth = 1
      for (const { anchorId, coords } of anchorList) {
        const [ax, ay] = worldToScreen(viewport, coords[0], coords[1])
        const dist = Math.hypot(effectiveRef.x - coords[0], effectiveRef.y - coords[1])
        ctx.strokeStyle = ANCHOR_COLORS[anchorId] + '66'
        ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(ax, ay); ctx.stroke()

        const mx = (rx + ax) / 2
        const my = (ry + ay) / 2
        const angle = Math.atan2(ay - ry, ax - rx)
        const label = `${dist.toFixed(2)} ft`
        ctx.save()
        ctx.setLineDash([])
        ctx.translate(mx, my)
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
    ctx.fillStyle = '#8ea4c8'
    ctx.font = '12px var(--font-primary, sans-serif)'
    ctx.setLineDash([])
    for (const [anchorA, anchorB] of map.lines) {
      const pointA = map.anchors[anchorA]
      const pointB = map.anchors[anchorB]
      if (!pointA || !pointB) continue
      const [x1, y1] = worldToScreen(viewport, pointA[0], pointA[1])
      const [x2, y2] = worldToScreen(viewport, pointB[0], pointB[1])
      const isSelected = selectedLineKey === lineKey(anchorA, anchorB)
      ctx.strokeStyle = isSelected ? LINE_SELECTED : LINE
      ctx.lineWidth = isSelected ? 3 : 2
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
      const distance = Math.hypot(pointB[0] - pointA[0], pointB[1] - pointA[1])
      ctx.fillStyle = isSelected ? LINE_SELECTED : '#8ea4c8'
      ctx.fillText(`${distance.toFixed(1)} ft`, (x1 + x2) / 2 + 8, (y1 + y2) / 2 - 8)
    }

    // ── Line-in-progress preview ───────────────────────────────────
    if (creatingFrom && cursorWorld) {
      const fromPt = map.anchors[creatingFrom]
      if (fromPt) {
        const [fx, fy] = worldToScreen(viewport, fromPt[0], fromPt[1])
        const endPt = hoverAnchor && hoverAnchor !== creatingFrom
          ? map.anchors[hoverAnchor]
          : null
        const [tx, ty] = endPt
          ? worldToScreen(viewport, endPt[0], endPt[1])
          : worldToScreen(viewport, cursorWorld.x, cursorWorld.y)
        ctx.save()
        ctx.setLineDash([6, 6])
        ctx.strokeStyle = '#4fc3ff'
        ctx.lineWidth = 2
        ctx.beginPath(); ctx.moveTo(fx, fy); ctx.lineTo(tx, ty); ctx.stroke()
        ctx.restore()
      }
    }

    // ── Anchor dots ────────────────────────────────────────────────
    for (const { anchorId, coords } of anchorList) {
      const [screenX, screenY] = worldToScreen(viewport, coords[0], coords[1])
      const isHighlighted =
        (creatingFrom && hoverAnchor === anchorId && anchorId !== creatingFrom) ||
        (!creatingFrom && ctrlDown && hoverAnchor === anchorId) ||
        creatingFrom === anchorId
      const radius = isHighlighted ? 10 : 8
      ctx.fillStyle = ANCHOR_COLORS[anchorId]
      ctx.strokeStyle = isHighlighted ? '#4fc3ff' : '#f0f4ff'
      ctx.lineWidth = isHighlighted ? 3 : 2
      ctx.setLineDash([])
      ctx.beginPath(); ctx.arc(screenX, screenY, radius, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
      ctx.fillStyle = ANCHOR_COLORS[anchorId]
      ctx.font = 'bold 12px var(--font-primary, sans-serif)'
      ctx.fillText(anchorId, screenX + 10, screenY - 4)
      ctx.fillStyle = '#9ab2d8'
      ctx.font = '11px var(--font-mono, monospace)'
      ctx.fillText(`(${coords[0].toFixed(1)}, ${coords[1].toFixed(1)})`, screenX + 10, screenY + 12)
    }

    // ── Reference crosshair ────────────────────────────────────────
    if (effectiveRef) {
      const [screenX, screenY] = worldToScreen(viewport, effectiveRef.x, effectiveRef.y)
      const color = referenceDotSelected ? CROSSHAIR_SELECTED : CROSSHAIR_COLOR
      ctx.strokeStyle = color
      ctx.lineWidth = referenceDotSelected ? 1.8 : 1.2
      ctx.setLineDash([])
      const arm = 8
      ctx.beginPath()
      ctx.moveTo(screenX - arm, screenY); ctx.lineTo(screenX + arm, screenY)
      ctx.moveTo(screenX, screenY - arm); ctx.lineTo(screenX, screenY + arm)
      ctx.stroke()
      ctx.font = '9px var(--font-primary, sans-serif)'
      ctx.fillStyle = color
      ctx.fillText(`(${effectiveRef.x.toFixed(1)}, ${effectiveRef.y.toFixed(1)})`, screenX + arm + 4, screenY - arm)
    }

    // ── Inter-tag dotted distance lines (live)
    const positionedTags = tags
      .map((tag, index) => ({ tag, color: TAG_COLORS[index % TAG_COLORS.length], xy: tag.calibrated_xy }))
      .filter((entry): entry is { tag: CalibrationTagRuntime; color: string; xy: [number, number] } => entry.xy != null)

    if (positionedTags.length >= 2) {
      ctx.save()
      ctx.setLineDash([3, 4])
      ctx.lineWidth = 1
      ctx.strokeStyle = 'rgba(255, 160, 60, 0.7)'
      for (let i = 0; i < positionedTags.length; i++) {
        for (let j = i + 1; j < positionedTags.length; j++) {
          const a = positionedTags[i].xy
          const b = positionedTags[j].xy
          const [ax, ay] = worldToScreen(viewport, a[0], a[1])
          const [bx, by] = worldToScreen(viewport, b[0], b[1])
          ctx.beginPath(); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); ctx.stroke()

          const distance = Math.hypot(a[0] - b[0], a[1] - b[1])
          const label = `${distance.toFixed(2)} ft`
          const mx = (ax + bx) / 2
          const my = (ay + by) / 2
          const angle = Math.atan2(by - ay, bx - ax)
          const normAngle = ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)
          const flipped = normAngle > Math.PI / 2 && normAngle < Math.PI * 1.5

          ctx.save()
          ctx.setLineDash([])
          ctx.translate(mx, my)
          ctx.rotate(flipped ? angle + Math.PI : angle)
          ctx.font = '10px var(--font-primary, sans-serif)'
          ctx.textAlign = 'center'
          ctx.fillStyle = '#ffa03c'
          ctx.fillText(label, 0, -3)
          ctx.restore()
        }
      }
      ctx.restore()
    }

    positionedTags.forEach(({ tag, color, xy }) => {
      const [screenX, screenY] = worldToScreen(viewport, xy[0], xy[1])
      const radius = Math.max(7, Math.min(Math.round(viewport.scale * 0.22), 14))
      ctx.fillStyle = color
      ctx.strokeStyle = '#ffffff'
      ctx.lineWidth = 1.5
      ctx.setLineDash([])
      ctx.beginPath()
      ctx.arc(screenX, screenY, radius, 0, Math.PI * 2)
      ctx.fill(); ctx.stroke()
      ctx.fillStyle = color
      ctx.font = 'bold 12px var(--font-primary, sans-serif)'
      ctx.fillText(tag.tag_id, screenX + radius + 3, screenY - 2)
    })
  }, [anchorList, canvasSize, map.anchors, map.lines, effectiveRef, referenceDotSelected, selectedTagId, tags, viewport, selectedLineKey, creatingFrom, hoverAnchor, cursorWorld, ctrlDown])

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
    if (!effectiveRef) return false
    const canvas = canvasRef.current
    if (!canvas) return false
    const rect = canvas.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    const [screenX, screenY] = worldToScreen(viewport, effectiveRef.x, effectiveRef.y)
    return Math.hypot(x - screenX, y - screenY) <= 18
  }, [effectiveRef, viewport])

  const hitLine = useCallback((clientX: number, clientY: number): string | null => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    const threshold = 6
    for (const [a, b] of map.lines) {
      const pa = map.anchors[a]
      const pb = map.anchors[b]
      if (!pa || !pb) continue
      const [x1, y1] = worldToScreen(viewport, pa[0], pa[1])
      const [x2, y2] = worldToScreen(viewport, pb[0], pb[1])
      if (distToSegment(x, y, x1, y1, x2, y2) <= threshold) return lineKey(a, b)
    }
    return null
  }, [map.lines, map.anchors, viewport])

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

    const anchorId = hitAnchor(event.clientX, event.clientY) as AnchorId | null

    // Line creation handling — takes precedence over anchor drag when appropriate.
    if (creatingFrom) {
      if (anchorId && anchorId !== creatingFrom) {
        onLineCreate(creatingFrom, anchorId)
        setCreatingFrom(null)
        return
      }
      if (anchorId === creatingFrom) {
        setCreatingFrom(null)
        return
      }
      setCreatingFrom(null)
      return
    }
    if (event.ctrlKey && anchorId) {
      setCreatingFrom(anchorId)
      onLineSelect(null)
      return
    }

    if (anchorId) {
      onReferenceDotSelect(false)
      onLineSelect(null)
      dragRef.current = { anchorId }
      onAnchorDragStart?.()
      return
    }

    if (hitRefDot(event.clientX, event.clientY)) {
      onReferenceDotSelect(true)
      onLineSelect(null)
      dragRef.current = { refDot: true, localRef: effectiveRef ? { ...effectiveRef } : undefined }
      return
    }

    const lineHit = hitLine(event.clientX, event.clientY)
    if (lineHit) {
      onLineSelect(lineHit)
      onReferenceDotSelect(false)
      return
    }

    onReferenceDotSelect(false)
    onLineSelect(null)
    panRef.current = { active: true, x: event.clientX, y: event.clientY }
  }, [hitAnchor, hitRefDot, hitLine, onReferencePlaced, onReferenceDotSelect, placingReference, viewport, creatingFrom, effectiveRef, onLineCreate, onLineSelect])

  const handleDoubleClick = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    if (placingReference) return
    const anchorId = hitAnchor(event.clientX, event.clientY) as AnchorId | null
    if (anchorId) {
      const [sx, sy] = getScreenPos(event.clientX, event.clientY)
      onAnchorDoubleClick(anchorId, sx, sy)
      return
    }
    if (hitRefDot(event.clientX, event.clientY)) {
      const [sx, sy] = getScreenPos(event.clientX, event.clientY)
      onReferenceDotDoubleClick(sx, sy)
    }
  }, [getScreenPos, hitAnchor, hitRefDot, onAnchorDoubleClick, onReferenceDotDoubleClick, placingReference])

  const handleMouseMove = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = event.clientX - rect.left
    const my = event.clientY - rect.top
    const [worldX, worldY] = screenToWorld(viewport, mx, my)

    // Track hover (for ctrl+line-creation UX). Cheap hit test.
    const hovered = hitAnchor(event.clientX, event.clientY) as AnchorId | null
    setHoverAnchor(prev => (prev === hovered ? prev : hovered))
    if (creatingFrom) {
      setCursorWorld({ x: worldX, y: worldY })
    }

    if (dragRef.current) {
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
        const next = { x: Number(worldX.toFixed(3)), y: Number(worldY.toFixed(3)) }
        dragRef.current.localRef = next
        setDragRefPos(next)
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
  }, [onMapChange, viewport, hitAnchor, creatingFrom])

  const handleMouseUp = useCallback(() => {
    if (dragRef.current) {
      const wasRefDrag = dragRef.current.refDot === true
      const finalRef = dragRef.current.localRef
      const wasAnchorDrag = !!dragRef.current.anchorId
      dragRef.current = null
      if (wasAnchorDrag) onMapCommit(latestMapRef.current)
      if (wasRefDrag && finalRef) {
        onReferencePlaced(finalRef.x, finalRef.y)
        setDragRefPos(null)
      }
    }
    panRef.current = null
  }, [onMapCommit, onReferencePlaced])

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
      if (dragRef.current?.anchorId) onMapCommit(latestMapRef.current)
      dragRef.current = null
      panRef.current = null
      if (placingReference) onCancelReferencePlacement()
      if (creatingFrom) setCreatingFrom(null)
      if (selectedLineKey) onLineSelect(null)
      event.preventDefault()
    }
    if (event.key === 'f' || event.key === 'F') {
      resetView()
      event.preventDefault()
    }
    if (event.key === 'Delete' || event.key === 'Backspace') {
      if (referenceDotSelected) {
        onReferenceDotDelete()
        event.preventDefault()
        return
      }
      if (selectedLineKey) {
        onLineDelete(selectedLineKey)
        event.preventDefault()
        return
      }
    }
  }, [onCancelReferencePlacement, onMapCommit, onReferenceDotDelete, placingReference, referenceDotSelected, resetView, creatingFrom, selectedLineKey, onLineSelect, onLineDelete])

  const getCursor = () => {
    if (placingReference) return 'crosshair'
    if (creatingFrom) return 'crosshair'
    if (dragRef.current || panRef.current?.active) return 'grabbing'
    if (ctrlDown && hoverAnchor) return 'crosshair'
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
