import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AnchorData, FloorplanManifest, RoomData, SegmentData } from '../../../types'
import AnchorEditPanel, { AnchorPanelPage } from './AnchorEditPanel'
import AnchorManagerCanvas, { AnchorManagerCanvasHandle, AnchorManagerViewport } from './AnchorManagerCanvas'
import { roomContainsWorldPoint, segmentsMatch } from './anchorGeometry'
import { confirmAsync } from '../../common/ConfirmDialog'
import './AnchorManager.css'

const API = 'http://localhost:8765'

type ActiveTool = 'cursor' | 'select' | 'smartSelect'

type LoadedSegment = SegmentData & { color?: string }

interface CreateRoomDialog {
  open: boolean
  name: string
  segments: SegmentData[]
}

interface AnchorManagerProps {
  workspaceId: string
  workspaceName: string
}

interface AnchorWorkspaceState {
  allSegments: LoadedSegment[]
  geometrySegments: LoadedSegment[]
  rooms: RoomData[]
  selectedRoomName: string | null
  selectedAnchorId: string | null
  selectedSegments: SegmentData[]
  svgPath: string
  svgContent: string
  projectName: string
  viewport: AnchorManagerViewport
}

interface SerialPortState {
  ports: string[]
  autoDetectPort: string
  loading: boolean
}

const DEFAULT_VIEWPORT: AnchorManagerViewport = { offsetX: 0, offsetY: 0, scale: 20 }

const createDefaultState = (): AnchorWorkspaceState => ({
  allSegments: [],
  geometrySegments: [],
  rooms: [],
  selectedRoomName: null,
  selectedAnchorId: null,
  selectedSegments: [],
  svgPath: '',
  svgContent: '',
  projectName: 'Untitled',
  viewport: DEFAULT_VIEWPORT,
})

const cloneState = (state: AnchorWorkspaceState): AnchorWorkspaceState => JSON.parse(JSON.stringify(state))

const normalizeRoomSettings = (settings: RoomData['rtls_settings'] | undefined) => ({
  tag_height_ft: Number(settings?.tag_height_ft ?? 0),
  filter_mode: settings?.filter_mode ?? 'None',
  ble_module_port: settings?.ble_module_port ?? '',
})

const normalizeRoom = (room: RoomData): RoomData => {
  const anchors = Array.isArray(room.anchors) ? room.anchors : []
  return {
    ...room,
    anchors,
    rtls_settings: normalizeRoomSettings(room.rtls_settings),
    reference_anchor_id: room.reference_anchor_id ?? anchors[0]?.id ?? null,
    edges: room.edges ?? [],
  }
}

const normalizeState = (state: Partial<AnchorWorkspaceState> | null | undefined): AnchorWorkspaceState => {
  const fallback = createDefaultState()
  if (!state) return fallback
  return {
    ...fallback,
    ...state,
    rooms: Array.isArray(state.rooms) ? state.rooms.map(normalizeRoom) : fallback.rooms,
    allSegments: Array.isArray(state.allSegments) ? state.allSegments : fallback.allSegments,
    geometrySegments: Array.isArray(state.geometrySegments) ? state.geometrySegments : fallback.geometrySegments,
    selectedSegments: Array.isArray(state.selectedSegments) ? state.selectedSegments : fallback.selectedSegments,
    viewport: state.viewport ?? fallback.viewport,
  }
}

const roomStateSignature = (state: AnchorWorkspaceState) => JSON.stringify({
  rooms: state.rooms,
  selectedRoomName: state.selectedRoomName,
  selectedAnchorId: state.selectedAnchorId,
  selectedSegments: state.selectedSegments,
})

const buildAnchorCounters = (rooms: RoomData[]): Record<string, number> => {
  const counters: Record<string, number> = {}
  for (const room of rooms) {
    let nextIndex = room.anchors.length
    for (const anchor of room.anchors) {
      const match = anchor.id.match(/A(\d+)$/)
      if (match) nextIndex = Math.max(nextIndex, parseInt(match[1], 10) + 1)
    }
    counters[room.room_name] = nextIndex
  }
  return counters
}

const deriveSegmentsFromRooms = (rooms: RoomData[]): LoadedSegment[] => {
  const seen = new Set<string>()
  const segments: LoadedSegment[] = []
  for (const room of rooms) {
    for (const seg of [...room.segments_ft, ...room.interior_segments_ft]) {
      const key = `${Math.min(seg.x1, seg.x2)},${Math.min(seg.y1, seg.y2)},${Math.max(seg.x1, seg.x2)},${Math.max(seg.y1, seg.y2)}`
      if (seen.has(key)) continue
      seen.add(key)
      segments.push(seg)
    }
  }
  return segments
}

const roundCoord = (value: number): number => Math.round(value * 1e4) / 1e4

const segmentKey = (segment: SegmentData): string => {
  const start: [number, number] = [roundCoord(segment.x1), roundCoord(segment.y1)]
  const end: [number, number] = [roundCoord(segment.x2), roundCoord(segment.y2)]
  const [a, b] = start[0] < end[0] || (start[0] === end[0] && start[1] <= end[1])
    ? [start, end]
    : [end, start]
  return `${a[0]},${a[1]},${b[0]},${b[1]}`
}

const segmentFromList = (raw: number[]): SegmentData => ({
  x1: raw[0],
  y1: raw[1],
  x2: raw[2],
  y2: raw[3],
})

const serializeSegments = (segments: SegmentData[]): number[][] => (
  segments.map(segment => [segment.x1, segment.y1, segment.x2, segment.y2])
)

const findMatchingRoomName = (rooms: RoomData[], segments: SegmentData[]): string | null => {
  for (const room of rooms) {
    if (segmentsMatch(room.segments_ft, segments)) return room.room_name
  }
  return null
}

const AnchorManager: React.FC<AnchorManagerProps> = ({ workspaceId, workspaceName }) => {
  const rootRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<AnchorManagerCanvasHandle>(null)
  const roomCounter = useRef(1)
  const anchorCounter = useRef<Record<string, number>>({})
  const fitAfterLoadRef = useRef(false)
  const dragSnapshotRef = useRef<AnchorWorkspaceState | null>(null)
  const workspaceStateRef = useRef<AnchorWorkspaceState>(createDefaultState())

  const [workspaceState, setWorkspaceState] = useState<AnchorWorkspaceState>(createDefaultState)
  const [undoStack, setUndoStack] = useState<AnchorWorkspaceState[]>([])
  const [redoStack, setRedoStack] = useState<AnchorWorkspaceState[]>([])
  const [status, setStatus] = useState<string>('')
  const [statusKind, setStatusKind] = useState<'ok' | 'error' | ''>('')
  const [createDialog, setCreateDialog] = useState<CreateRoomDialog>({ open: false, name: '', segments: [] })
  const [activeTool, setActiveTool] = useState<ActiveTool>('cursor')
  const [hoverRoomName, setHoverRoomName] = useState<string | null>(null)
  const [panelPage, setPanelPage] = useState<AnchorPanelPage>('rooms')
  const [placementPreview, setPlacementPreview] = useState<{ roomName: string; localX: number; localY: number } | null>(null)
  const [serialPortState, setSerialPortState] = useState<SerialPortState>({
    ports: [],
    autoDetectPort: '',
    loading: false,
  })
  const [workspacePaths, setWorkspacePaths] = useState<{ svg?: string; rooms?: string }>({})

  useEffect(() => {
    let cancelled = false
    fetch(`${API}/api/workspace/paths/${encodeURIComponent(workspaceId)}?workspace_name=${encodeURIComponent(workspaceName)}`)
      .then(r => r.json())
      .then(data => {
        if (!cancelled && data.success) {
          setWorkspacePaths({ svg: data.svg, rooms: data.rooms })
        }
      })
      .catch(() => { /* workspace paths are optional */ })
    return () => { cancelled = true }
  }, [workspaceId, workspaceName])

  useEffect(() => {
    workspaceStateRef.current = workspaceState
    roomCounter.current = workspaceState.rooms.length + 1
    anchorCounter.current = buildAnchorCounters(workspaceState.rooms)
  }, [workspaceState])

  useEffect(() => {
    if (!fitAfterLoadRef.current || workspaceState.allSegments.length === 0) return
    fitAfterLoadRef.current = false
    requestAnimationFrame(() => canvasRef.current?.fitView())
  }, [workspaceState.allSegments.length])

  const loadSerialPorts = useCallback(async () => {
    setSerialPortState(current => ({ ...current, loading: true }))
    try {
      const res = await fetch(`${API}/api/rtls/serial/ports`)
      const data = await res.json()
      if (!data.success) throw new Error(data.error || 'Could not load serial ports.')
      setSerialPortState({
        ports: Array.isArray(data.ports) ? data.ports : [],
        autoDetectPort: typeof data.auto_detect_port === 'string' ? data.auto_detect_port : '',
        loading: false,
      })
    } catch {
      setSerialPortState(current => ({ ...current, loading: false }))
    }
  }, [])

  useEffect(() => {
    void loadSerialPorts()
  }, [loadSerialPorts])

  const showStatus = (message: string, kind: 'ok' | 'error') => {
    setStatus(message)
    setStatusKind(kind)
    window.setTimeout(() => {
      setStatus('')
      setStatusKind('')
    }, 4000)
  }

  const replaceWorkspaceState = useCallback((next: AnchorWorkspaceState) => {
    setWorkspaceState(normalizeState(next))
    setUndoStack([])
    setRedoStack([])
  }, [])

  const commitWorkspaceState = useCallback((updater: (current: AnchorWorkspaceState) => AnchorWorkspaceState) => {
    setWorkspaceState(current => {
      const next = normalizeState(updater(current))
      if (roomStateSignature(current) === roomStateSignature(next)) return current
      setUndoStack(stack => [...stack.slice(-49), cloneState(current)])
      setRedoStack([])
      return next
    })
  }, [])

  const updateWorkspaceState = useCallback((updater: (current: AnchorWorkspaceState) => AnchorWorkspaceState) => {
    setWorkspaceState(current => normalizeState(updater(current)))
  }, [])

  const handleUndo = useCallback(() => {
    setUndoStack(stack => {
      const snapshot = stack[stack.length - 1]
      if (!snapshot) return stack
      setWorkspaceState(current => {
        setRedoStack(redo => [...redo.slice(-49), cloneState(current)])
        return snapshot
      })
      return stack.slice(0, -1)
    })
  }, [])

  const handleRedo = useCallback(() => {
    setRedoStack(stack => {
      const snapshot = stack[stack.length - 1]
      if (!snapshot) return stack
      setWorkspaceState(current => {
        setUndoStack(undo => [...undo.slice(-49), cloneState(current)])
        return snapshot
      })
      return stack.slice(0, -1)
    })
  }, [])

  const ingestSvgContent = useCallback((text: string, sourceName: string) => {
    try {
      const parser = new DOMParser()
      const doc = parser.parseFromString(text, 'image/svg+xml')
      const root = doc.documentElement

      const cadMinX = parseFloat(root.getAttribute('data-cad-min-x') ?? 'NaN')
      const cadMinY = parseFloat(root.getAttribute('data-cad-min-y') ?? 'NaN')
      const cadScale = parseFloat(root.getAttribute('data-cad-scale') ?? 'NaN')
      const cadOffX = parseFloat(root.getAttribute('data-cad-offset-x') ?? 'NaN')
      const cadOffY = parseFloat(root.getAttribute('data-cad-offset-y') ?? 'NaN')
      const docSize = 1000
      const hasCadMetadata = !Number.isNaN(cadMinX) && !Number.isNaN(cadMinY) && !Number.isNaN(cadScale) && cadScale > 0

      const toWorldX = hasCadMetadata
        ? (screenX: number) => (screenX - cadOffX) / cadScale + cadMinX
        : (screenX: number) => screenX
      const toWorldY = hasCadMetadata
        ? (screenY: number) => (docSize - screenY - cadOffY) / cadScale + cadMinY
        : (screenY: number) => screenY

      const segments: LoadedSegment[] = Array.from(doc.querySelectorAll('line')).map(line => ({
        x1: toWorldX(parseFloat(line.getAttribute('x1') ?? '0')),
        y1: toWorldY(parseFloat(line.getAttribute('y1') ?? '0')),
        x2: toWorldX(parseFloat(line.getAttribute('x2') ?? '0')),
        y2: toWorldY(parseFloat(line.getAttribute('y2') ?? '0')),
        color: line.getAttribute('stroke') ?? undefined,
      }))

      if (segments.length === 0) {
        showStatus('No line segments found in SVG.', 'error')
        return
      }

      fitAfterLoadRef.current = true
      replaceWorkspaceState({
        ...workspaceStateRef.current,
        allSegments: segments,
        geometrySegments: segments,
        rooms: [],
        selectedRoomName: null,
        selectedAnchorId: null,
        selectedSegments: [],
        svgPath: sourceName,
        svgContent: text,
        projectName: sourceName.replace(/\.svg$/i, ''),
        viewport: DEFAULT_VIEWPORT,
      })
      showStatus(`Loaded ${segments.length} segment${segments.length === 1 ? '' : 's'} from ${sourceName}`, 'ok')
    } catch (error) {
      showStatus(`Failed to parse SVG: ${String(error)}`, 'error')
    }
  }, [replaceWorkspaceState])

  const handleLoadSVG = useCallback(async () => {
    const openFile = window.api?.openFile
    const readTextFile = window.api?.readTextFile
    if (!openFile || !readTextFile) {
      showStatus('File dialogs are unavailable in this environment.', 'error')
      return
    }
    const result = await openFile([{ name: 'SVG Files', extensions: ['svg'] }], workspacePaths.svg)
    if (result.canceled || !result.filePaths[0]) return
    showStatus('Loading SVG...', 'ok')
    const readResult = await readTextFile(result.filePaths[0])
    if (!readResult.success || typeof readResult.content !== 'string') {
      showStatus(readResult.error ?? 'Could not read file.', 'error')
      return
    }
    const baseName = result.filePaths[0].split(/[\\/]/).pop() ?? 'plan.svg'
    ingestSvgContent(readResult.content, baseName)
  }, [ingestSvgContent, workspacePaths.svg])

  const handleLoadManifest = useCallback(async () => {
    const openFile = window.api?.openFile
    const readTextFile = window.api?.readTextFile
    if (!openFile || !readTextFile) {
      showStatus('File dialogs are unavailable in this environment.', 'error')
      return
    }
    const result = await openFile(
      [{ name: 'Rooms Manifest', extensions: ['json'] }],
      workspacePaths.rooms,
    )
    if (result.canceled || !result.filePaths[0]) return
    const readResult = await readTextFile(result.filePaths[0])
    if (!readResult.success || typeof readResult.content !== 'string') {
      showStatus(readResult.error ?? 'Could not read file.', 'error')
      return
    }
    const baseName = result.filePaths[0].split(/[\\/]/).pop() ?? 'rooms.json'
    try {
      const manifest = JSON.parse(readResult.content) as FloorplanManifest
      const rooms = (manifest.rooms ?? []).map(normalizeRoom)
      fitAfterLoadRef.current = true
      replaceWorkspaceState({
        ...workspaceStateRef.current,
        rooms,
        allSegments: workspaceStateRef.current.allSegments.length > 0
          ? workspaceStateRef.current.allSegments
          : deriveSegmentsFromRooms(rooms),
        geometrySegments: workspaceStateRef.current.geometrySegments,
        svgPath: manifest.svg_file ?? workspaceStateRef.current.svgPath,
        projectName: manifest.project_name ?? 'Project',
        selectedRoomName: rooms[0]?.room_name ?? null,
        selectedAnchorId: null,
        selectedSegments: [],
        viewport: DEFAULT_VIEWPORT,
      })
      showStatus(`Loaded ${rooms.length} room${rooms.length === 1 ? '' : 's'} from ${baseName}`, 'ok')
    } catch {
      showStatus('Invalid manifest JSON.', 'error')
    }
  }, [replaceWorkspaceState, workspacePaths.rooms])

  const handleSaveManifest = useCallback(async () => {
    try {
      const res = await fetch(
        `${API}/api/rooms/manifest/save?workspace_id=${encodeURIComponent(workspaceId)}&workspace_name=${encodeURIComponent(workspaceName)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_name: workspaceState.projectName,
            svg_path: workspaceState.svgPath,
            rooms: workspaceState.rooms,
          }),
        },
      )
      const data = await res.json()
      if (data.success) showStatus(`Saved to ${data.path}`, 'ok')
      else showStatus(data.error, 'error')
    } catch {
      showStatus('Backend unreachable.', 'error')
    }
  }, [workspaceId, workspaceName, workspaceState.projectName, workspaceState.rooms, workspaceState.svgPath])

  const handleSaveProject = useCallback(async () => {
    if (!workspaceState.svgContent.trim()) {
      showStatus('Load an SVG before saving a project package.', 'error')
      return
    }
    try {
      const res = await fetch(`${API}/api/rooms/project/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceId,
          workspace_name: workspaceName,
          project_name: workspaceState.projectName,
          svg_path: workspaceState.svgPath,
          svg_filename: workspaceState.svgPath,
          svg_content: workspaceState.svgContent,
          rooms: workspaceState.rooms,
        }),
      })
      const data = await res.json()
      if (data.success) showStatus(`Saved project to ${data.path}`, 'ok')
      else showStatus(data.error, 'error')
    } catch {
      showStatus('Backend unreachable.', 'error')
    }
  }, [
    workspaceId,
    workspaceName,
    workspaceState.projectName,
    workspaceState.rooms,
    workspaceState.svgContent,
    workspaceState.svgPath,
  ])

  const handleSegmentClick = useCallback(async (segment: SegmentData, _shiftHeld: boolean, worldX: number, worldY: number) => {
    const current = workspaceStateRef.current
    if (current.geometrySegments.length === 0) {
      showStatus('Load the original SVG floor plan to use Select.', 'error')
      return
    }

    const segIdx = current.geometrySegments.findIndex(item => item === segment || segmentKey(item) === segmentKey(segment))
    let nextSegment = segment

    if (segIdx >= 0) {
      try {
        const res = await fetch(`${API}/api/rooms/geometry/compute-subsegment`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            all_segments: serializeSegments(current.geometrySegments),
            seg_idx: segIdx,
            click_x: worldX,
            click_y: worldY,
          }),
        })
        const data = await res.json()
        if (data.success && Array.isArray(data.subsegment) && data.subsegment.length === 4) {
          nextSegment = segmentFromList(data.subsegment)
        } else if (!data.success && data.error) {
          showStatus(data.error, 'error')
        }
      } catch {
        showStatus('Backend unreachable.', 'error')
      }
    }

    updateWorkspaceState(state => {
      const key = segmentKey(nextSegment)
      const exists = state.selectedSegments.some(item => segmentKey(item) === key)
      const nextSegments = exists
        ? state.selectedSegments.filter(item => segmentKey(item) !== key)
        : [...state.selectedSegments, nextSegment]
      return { ...state, selectedSegments: nextSegments }
    })
  }, [updateWorkspaceState])

  const handleSmartSelectClick = useCallback(async (worldX: number, worldY: number, _shiftHeld: boolean) => {
    const current = workspaceStateRef.current
    if (current.geometrySegments.length === 0) {
      showStatus('Load the original SVG floor plan to use Smart Select.', 'error')
      return
    }

    const roomAtPoint = current.rooms.find(room => roomContainsWorldPoint(room, worldX, worldY, 0))
    if (roomAtPoint) {
      showStatus(`Room already defined: ${roomAtPoint.room_name}`, 'error')
      return
    }

    try {
      const res = await fetch(`${API}/api/rooms/geometry/detect-boundary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          segments: serializeSegments(current.geometrySegments),
          click_x: worldX,
          click_y: worldY,
        }),
      })
      const data = await res.json()
      if (!data.success || !Array.isArray(data.boundary)) {
        showStatus('Could not find a closed room boundary at that point.', 'error')
        return
      }

      const boundary = data.boundary.map((segment: number[]) => segmentFromList(segment))
      const matchingRoomName = findMatchingRoomName(current.rooms, boundary)
      if (matchingRoomName) {
        showStatus(`Room already defined: ${matchingRoomName}`, 'error')
        return
      }

      updateWorkspaceState(state => ({ ...state, selectedSegments: boundary }))
      setActiveTool('cursor')
    } catch {
      showStatus('Backend unreachable.', 'error')
    }
  }, [updateWorkspaceState])

  const handleCreateRoom = useCallback(() => {
    if (workspaceState.selectedSegments.length === 0) {
      showStatus('Select segments on the canvas first.', 'error')
      return
    }
    const matchingRoomName = findMatchingRoomName(workspaceState.rooms, workspaceState.selectedSegments)
    if (matchingRoomName) {
      showStatus(`Room already defined: ${matchingRoomName}`, 'error')
      return
    }
    setCreateDialog({
      open: true,
      name: `Room_${roomCounter.current}`,
      segments: workspaceState.selectedSegments,
    })
  }, [workspaceState.rooms, workspaceState.selectedSegments])

  const handleConfirmCreateRoom = useCallback(async () => {
    if (!createDialog.name.trim()) return
    try {
      const res = await fetch(`${API}/api/rooms/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: createDialog.name.trim(),
          segments: createDialog.segments.map(seg => [seg.x1, seg.y1, seg.x2, seg.y2]),
          existing_rooms: workspaceStateRef.current.rooms,
        }),
      })
      const data = await res.json()
      if (!data.success) {
        showStatus(data.error, 'error')
        return
      }
      const nextRoom = normalizeRoom(data.room as RoomData)
      commitWorkspaceState(current => ({
        ...current,
        rooms: [...current.rooms, nextRoom],
        selectedRoomName: nextRoom.room_name,
        selectedAnchorId: null,
        selectedSegments: [],
      }))
      roomCounter.current += 1
      setCreateDialog({ open: false, name: '', segments: [] })
      setActiveTool('cursor')
      showStatus(`Room "${nextRoom.room_name}" created.`, 'ok')
    } catch {
      showStatus('Backend unreachable.', 'error')
    }
  }, [commitWorkspaceState, createDialog])

  const handleSelectRoom = useCallback((roomName: string | null) => {
    updateWorkspaceState(current => ({ ...current, selectedRoomName: roomName }))
  }, [updateWorkspaceState])

  const handleSelectAnchor = useCallback((anchorId: string | null) => {
    updateWorkspaceState(current => ({ ...current, selectedAnchorId: anchorId }))
  }, [updateWorkspaceState])

  const handleViewportChange = useCallback((viewport: AnchorManagerViewport) => {
    updateWorkspaceState(current => ({ ...current, viewport }))
  }, [updateWorkspaceState])

  const handleRoomCanvasClick = useCallback((roomName: string) => {
    updateWorkspaceState(current => ({ ...current, selectedRoomName: roomName, selectedAnchorId: null }))
  }, [updateWorkspaceState])

  const handleSetAllAnchorZ = useCallback((roomName: string, zValue: number) => {
    commitWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(room => {
        if (room.room_name !== roomName) return room
        return {
          ...room,
          anchors: room.anchors.map(anchor => ({ ...anchor, z_ft: zValue })),
        }
      }),
    }))
  }, [commitWorkspaceState])


  const handleAnchorUpdate = useCallback((roomName: string, anchorId: string, patch: Partial<AnchorData>) => {
    commitWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(room => {
        if (room.room_name !== roomName) return room
        return {
          ...room,
          anchors: room.anchors.map(anchor => (anchor.id === anchorId ? { ...anchor, ...patch } : anchor)),
        }
      }),
    }))
  }, [commitWorkspaceState])

  const handleAnchorDelete = useCallback((roomName: string, anchorId: string) => {
    commitWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(room => {
        if (room.room_name !== roomName) return room
        const anchors = room.anchors.filter(anchor => anchor.id !== anchorId)
        const edges = (room.edges ?? []).filter(e => e[0] !== anchorId && e[1] !== anchorId)
        return {
          ...room,
          anchors,
          edges,
          reference_anchor_id: room.reference_anchor_id === anchorId ? anchors[0]?.id ?? null : room.reference_anchor_id,
        }
      }),
      selectedAnchorId: current.selectedAnchorId === anchorId ? null : current.selectedAnchorId,
    }))
  }, [commitWorkspaceState])

  const handleReferenceAnchorChange = useCallback((roomName: string, referenceAnchorId: string | null) => {
    commitWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(room => (
        room.room_name === roomName ? { ...room, reference_anchor_id: referenceAnchorId } : room
      )),
    }))
  }, [commitWorkspaceState])

  const handleRoomSettingsUpdate = useCallback((roomName: string, patch: Partial<RoomData['rtls_settings']>) => {
    commitWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(room => (
        room.room_name !== roomName
          ? room
          : {
              ...room,
              rtls_settings: normalizeRoomSettings({ ...room.rtls_settings, ...patch }),
            }
      )),
    }))
  }, [commitWorkspaceState])

  const handleEdgesUpdate = useCallback((roomName: string, nextEdges: [string, string][]) => {
    commitWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(room => (
        room.room_name === roomName ? { ...room, edges: nextEdges } : room
      )),
    }))
  }, [commitWorkspaceState])

  const handleNudgeAnchor = useCallback((dx: number, dy: number) => {
    const current = workspaceStateRef.current
    if (!current.selectedRoomName || !current.selectedAnchorId) return
    const room = current.rooms.find(item => item.room_name === current.selectedRoomName)
    const anchor = room?.anchors.find(item => item.id === current.selectedAnchorId)
    if (!room || !anchor) return
    const nextWorldX = room.room_bounds_ft.min_x + anchor.x_ft + dx
    const nextWorldY = room.room_bounds_ft.min_y + anchor.y_ft + dy
    if (!roomContainsWorldPoint(room, nextWorldX, nextWorldY, 0.05)) return

    commitWorkspaceState(state => ({
      ...state,
      rooms: state.rooms.map(item => {
        if (item.room_name !== room.room_name) return item
        return {
          ...item,
          anchors: item.anchors.map(existing => (
            existing.id === anchor.id
              ? { ...existing, x_ft: existing.x_ft + dx, y_ft: existing.y_ft + dy }
              : existing
          )),
        }
      }),
    }))
  }, [commitWorkspaceState])

  const handleRoomDoubleClick = useCallback((roomName: string) => {
    updateWorkspaceState(current => ({ ...current, selectedRoomName: roomName, selectedAnchorId: null }))
    setPanelPage('room-detail')
  }, [updateWorkspaceState])

  const handleAnchorPlace = useCallback((roomName: string, localX: number, localY: number) => {
    const rooms = workspaceStateRef.current.rooms
    const roomIndex = rooms.findIndex(r => r.room_name === roomName) + 1
    if (roomIndex <= 0) return
    const room = rooms[roomIndex - 1]
    const nextIdx = anchorCounter.current[roomName] ?? room.anchors.length
    anchorCounter.current[roomName] = nextIdx + 1
    const anchorId = `R${roomIndex}A${nextIdx}`
    const defaultHwId = `A${nextIdx}`
    commitWorkspaceState(state => ({
      ...state,
      rooms: state.rooms.map(r => r.room_name !== roomName ? r : {
        ...r,
        anchors: [...r.anchors, { id: anchorId, hw_id: defaultHwId, x_ft: localX, y_ft: localY, z_ft: 0 }],
        reference_anchor_id: r.reference_anchor_id ?? anchorId,
      }),
      selectedAnchorId: anchorId,
    }))
  }, [commitWorkspaceState])

  const handleDeleteRoom = useCallback((roomName: string) => {
    commitWorkspaceState(current => {
      const remaining = current.rooms.filter(r => r.room_name !== roomName)
      return {
        ...current,
        rooms: remaining,
        selectedRoomName: current.selectedRoomName === roomName ? null : current.selectedRoomName,
        selectedAnchorId: null,
      }
    })
    delete anchorCounter.current[roomName]
    setPanelPage('rooms')
  }, [commitWorkspaceState])

  const handleAnchorMoveStart = useCallback((_roomName: string, _anchorId: string) => {
    dragSnapshotRef.current = cloneState(workspaceStateRef.current)
  }, [])

  const handleAnchorMove = useCallback((roomName: string, anchorId: string, localX: number, localY: number) => {
    updateWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(r => r.room_name !== roomName ? r : {
        ...r,
        anchors: r.anchors.map(a => a.id !== anchorId ? a : { ...a, x_ft: localX, y_ft: localY }),
      }),
      selectedAnchorId: anchorId,
    }))
  }, [updateWorkspaceState])

  const handleAnchorMoveEnd = useCallback(() => {
    const before = dragSnapshotRef.current
    dragSnapshotRef.current = null
    if (!before) return
    if (roomStateSignature(before) === roomStateSignature(workspaceStateRef.current)) return
    setUndoStack(stack => [...stack.slice(-49), before])
    setRedoStack([])
  }, [])

  useEffect(() => {
    const handleViewCommand = (event: Event) => {
      const detail = (event as CustomEvent).detail as { cmd?: string; tool?: ActiveTool; workspaceId?: string }
      if (detail.workspaceId !== workspaceId) return

      switch (detail.cmd) {
        case 'undo':
          handleUndo()
          break
        case 'redo':
          handleRedo()
          break
        case 'zoom_in':
          canvasRef.current?.zoomIn()
          break
        case 'zoom_out':
          canvasRef.current?.zoomOut()
          break
        case 'zoom_reset':
          canvasRef.current?.fitView()
          break
        case 'set_tool':
          if (detail.tool === 'cursor' || detail.tool === 'select' || detail.tool === 'smartSelect') {
            setActiveTool(detail.tool)
            if (detail.tool === 'cursor') canvasRef.current?.focusCanvas()
          }
          break
        default:
          break
      }
    }

    window.addEventListener('anchor-view-command', handleViewCommand)
    return () => window.removeEventListener('anchor-view-command', handleViewCommand)
  }, [handleRedo, handleUndo, workspaceId])

  useEffect(() => {
    const handler = async (e: Event) => {
      const detail = (e as CustomEvent).detail as { workspaceId: string; module?: string }
      if (detail.workspaceId !== workspaceId || (detail.module && detail.module !== 'anchors')) return
      if (!workspaceState.svgContent.trim()) {
        await confirmAsync({
          title: 'No Floor Plan Loaded',
          message: 'Load an SVG floor plan before saving the project. Use "Load SVG" in the Anchor Manager toolbar.',
          confirmLabel: 'OK',
        })
        return
      }
      await handleSaveProject()
    }
    window.addEventListener('workspace-save-command', handler)
    window.addEventListener('workspace-save-as-command', handler)
    return () => {
      window.removeEventListener('workspace-save-command', handler)
      window.removeEventListener('workspace-save-as-command', handler)
    }
  }, [workspaceId, workspaceState.svgContent, handleSaveProject])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.key !== 'c' && event.key !== 'C') || event.ctrlKey || event.metaKey || event.altKey) return
      const root = rootRef.current
      if (!root || root.offsetParent === null) return
      const target = event.target as HTMLElement | null
      if (target) {
        const tag = target.tagName
        if (target.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      }
      setActiveTool('cursor')
      canvasRef.current?.focusCanvas()
      event.preventDefault()
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className="am-root" ref={rootRef}>
      <div className="am-toolbar">
        <span className="am-project-name">{workspaceState.projectName}</span>
        <div className="am-toolbar-actions">
          <button className="am-btn am-btn--ghost" onClick={handleLoadSVG}>Load SVG</button>
          <button className="am-btn am-btn--ghost" onClick={handleLoadManifest}>Load Rooms</button>
          <button className="am-btn am-btn--secondary" onClick={handleSaveManifest}>Save Rooms</button>
          <button className="am-btn am-btn--secondary" onClick={handleSaveProject}>Save Project</button>
        </div>
        {status && <div className={`am-status am-status--${statusKind}`}>{status}</div>}
      </div>

      <div className="am-workspace">
        <div className="am-canvas-wrap">
          {workspaceState.allSegments.length === 0 ? (
            <div className="am-empty-canvas">
              <div className="am-empty-icon">O</div>
              <div className="am-empty-title">No Floor Plan Loaded</div>
              <div className="am-empty-sub">Click <strong>Load SVG</strong> to import a CAD export or floor plan.</div>
            </div>
          ) : (
            <>
              <AnchorManagerCanvas
                ref={canvasRef}
                allSegments={workspaceState.allSegments}
                rooms={workspaceState.rooms}
                selectedRoomName={workspaceState.selectedRoomName}
                selectedAnchorId={workspaceState.selectedAnchorId}
                selectedSegments={workspaceState.selectedSegments}
                viewport={workspaceState.viewport}
                activeTool={activeTool}
                hoverRoomName={hoverRoomName}
                placementRoomName={panelPage === 'room-detail' ? workspaceState.selectedRoomName : null}
                onViewportChange={handleViewportChange}
                onToolChange={setActiveTool}
                onSegmentClick={handleSegmentClick}
                onSmartSelectClick={handleSmartSelectClick}
                onRoomClick={handleRoomCanvasClick}
                onRoomHover={setHoverRoomName}
                onNudgeAnchor={handleNudgeAnchor}
                onCanvasContextMenu={handleCreateRoom}
                onRoomDoubleClick={handleRoomDoubleClick}
                onAnchorPlace={handleAnchorPlace}
                onPlacementPreviewChange={setPlacementPreview}
              />

              <AnchorEditPanel
                rooms={workspaceState.rooms}
                selectedRoomName={workspaceState.selectedRoomName}
                selectedAnchorId={workspaceState.selectedAnchorId}
                hoverRoomName={hoverRoomName}
                panelPage={panelPage}
                serialPorts={serialPortState.ports}
                autoDetectPort={serialPortState.autoDetectPort}
                serialPortsLoading={serialPortState.loading}
                externalPreview={placementPreview}
                onPageChange={setPanelPage}
                onRoomSelect={handleSelectRoom}
                onRoomHover={setHoverRoomName}
                onRoomDoubleClick={handleRoomDoubleClick}
                onAnchorUpdate={handleAnchorUpdate}
                onAnchorDelete={handleAnchorDelete}
                onEdgesUpdate={handleEdgesUpdate}
                onAnchorSelect={handleSelectAnchor}
                onAnchorPlace={handleAnchorPlace}
                onAnchorMoveStart={handleAnchorMoveStart}
                onAnchorMove={handleAnchorMove}
                onAnchorMoveEnd={handleAnchorMoveEnd}
                onReferenceAnchorChange={handleReferenceAnchorChange}
                onRefreshSerialPorts={loadSerialPorts}
                onRoomSettingsUpdate={handleRoomSettingsUpdate}
                onSetAllAnchorZ={handleSetAllAnchorZ}
              />

              {workspaceState.rooms.length > 0 && (
                <div className="am-room-dock">
                  <div className="am-room-dock-label">Rooms</div>
                  <div className="am-room-dock-scroll">
                    {workspaceState.rooms.map(room => {
                      const isActive = room.room_name === workspaceState.selectedRoomName
                      const isHovered = room.room_name === hoverRoomName && !isActive
                      return (
                        <div
                          key={room.room_name}
                          className={`am-room-dock-tab${isActive ? ' active' : ''}${isHovered ? ' hovered' : ''}`}
                          onClick={() => updateWorkspaceState(current => ({
                            ...current,
                            selectedRoomName: current.selectedRoomName === room.room_name ? null : room.room_name,
                            selectedAnchorId: null,
                          }))}
                          onMouseEnter={() => setHoverRoomName(room.room_name)}
                          onMouseLeave={() => setHoverRoomName(null)}
                          onDoubleClick={() => handleRoomDoubleClick(room.room_name)}
                          title={`${room.anchors.length} anchor${room.anchors.length !== 1 ? 's' : ''} · double-click for detail`}
                          role="button"
                        >
                          <span>{room.room_name}</span>
                          <button
                            type="button"
                            className="am-room-dock-tab-close"
                            onClick={e => { e.stopPropagation(); handleDeleteRoom(room.room_name) }}
                            title={`Delete ${room.room_name}`}
                            aria-label={`Delete ${room.room_name}`}
                          >
                            ×
                          </button>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {workspaceState.selectedSegments.length > 0 && (
                <div className={`am-selection-banner${workspaceState.rooms.length > 0 ? ' am-selection-banner--above-dock' : ''}`}>
                  <div className="am-selection-copy">
                    {workspaceState.selectedSegments.length} segment{workspaceState.selectedSegments.length === 1 ? '' : 's'} selected
                  </div>
                  <div className="am-selection-actions">
                    <button className="am-btn am-btn--primary" onClick={handleCreateRoom}>Create Room</button>
                    <button
                      className="am-btn am-btn--ghost"
                      onClick={() => updateWorkspaceState(current => ({ ...current, selectedSegments: [] }))}
                    >
                      Clear
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {createDialog.open && (
        <div className="am-dialog-overlay" onClick={() => setCreateDialog(dialog => ({ ...dialog, open: false }))}>
          <div className="am-dialog" onClick={event => event.stopPropagation()}>
            <div className="am-dialog-title">Create Room</div>
            <div className="am-dialog-sub">{createDialog.segments.length} segments selected</div>
            <label className="am-dialog-label">Room Name</label>
            <input
              className="am-input"
              value={createDialog.name}
              onChange={event => setCreateDialog(dialog => ({ ...dialog, name: event.target.value }))}
              onKeyDown={event => {
                if (event.key === 'Enter') handleConfirmCreateRoom()
              }}
              autoFocus
            />
            <div className="am-dialog-btns">
              <button className="am-btn am-btn--ghost" onClick={() => setCreateDialog(dialog => ({ ...dialog, open: false }))}>
                Cancel
              </button>
              <button className="am-btn am-btn--primary" onClick={handleConfirmCreateRoom}>
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AnchorManager
