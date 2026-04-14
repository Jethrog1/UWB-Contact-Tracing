import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AnchorData, FloorplanManifest, RoomData, SegmentData } from '../../../types'
import AnchorEditPanel from './AnchorEditPanel'
import AnchorManagerCanvas, { AnchorManagerCanvasHandle, AnchorManagerViewport } from './AnchorManagerCanvas'
import { roomContainsWorldPoint } from './anchorGeometry'
import './AnchorManager.css'

const API = 'http://localhost:8765'

type LoadedSegment = SegmentData & { color?: string }

interface CreateRoomDialog {
  open: boolean
  name: string
  segments: SegmentData[]
}

interface AnchorManagerProps {
  workspaceId: string
}

interface AnchorWorkspaceState {
  allSegments: LoadedSegment[]
  rooms: RoomData[]
  selectedRoomName: string | null
  selectedAnchorId: string | null
  selectedSegments: SegmentData[]
  svgPath: string
  projectName: string
  viewport: AnchorManagerViewport
}

const DEFAULT_VIEWPORT: AnchorManagerViewport = { offsetX: 0, offsetY: 0, scale: 20 }

const createDefaultState = (): AnchorWorkspaceState => ({
  allSegments: [],
  rooms: [],
  selectedRoomName: null,
  selectedAnchorId: null,
  selectedSegments: [],
  svgPath: '',
  projectName: 'Untitled',
  viewport: DEFAULT_VIEWPORT,
})

const cloneState = (state: AnchorWorkspaceState): AnchorWorkspaceState => JSON.parse(JSON.stringify(state))

const normalizeRoom = (room: RoomData): RoomData => ({
  ...room,
  reference_anchor_id: room.reference_anchor_id ?? room.anchors[0]?.id ?? null,
  edges: room.edges ?? [],
})

const normalizeState = (state: Partial<AnchorWorkspaceState> | null | undefined): AnchorWorkspaceState => {
  const fallback = createDefaultState()
  if (!state) return fallback
  return {
    ...fallback,
    ...state,
    rooms: Array.isArray(state.rooms) ? state.rooms.map(normalizeRoom) : fallback.rooms,
    allSegments: Array.isArray(state.allSegments) ? state.allSegments : fallback.allSegments,
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

const AnchorManager: React.FC<AnchorManagerProps> = ({ workspaceId }) => {
  const canvasRef = useRef<AnchorManagerCanvasHandle>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const manifestInputRef = useRef<HTMLInputElement>(null)
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

  const handleLoadSVGFile = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    showStatus('Loading SVG...', 'ok')
    const reader = new FileReader()
    reader.onload = loadEvent => {
      try {
        const text = loadEvent.target?.result as string
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
          rooms: [],
          selectedRoomName: null,
          selectedAnchorId: null,
          selectedSegments: [],
          svgPath: file.name,
          projectName: file.name.replace(/\.svg$/i, ''),
          viewport: DEFAULT_VIEWPORT,
        })
        showStatus(`Loaded ${segments.length} segment${segments.length === 1 ? '' : 's'} from ${file.name}`, 'ok')
      } catch (error) {
        showStatus(`Failed to parse SVG: ${String(error)}`, 'error')
      }
    }
    reader.onerror = () => showStatus('Could not read file.', 'error')
    reader.readAsText(file)
    event.target.value = ''
  }, [replaceWorkspaceState])

  const handleLoadManifestFile = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = loadEvent => {
      try {
        const manifest = JSON.parse(loadEvent.target?.result as string) as FloorplanManifest
        const rooms = (manifest.rooms ?? []).map(normalizeRoom)
        fitAfterLoadRef.current = true
        replaceWorkspaceState({
          ...workspaceStateRef.current,
          rooms,
          allSegments: workspaceStateRef.current.allSegments.length > 0
            ? workspaceStateRef.current.allSegments
            : deriveSegmentsFromRooms(rooms),
          projectName: manifest.project_name ?? 'Project',
          selectedRoomName: rooms[0]?.room_name ?? null,
          selectedAnchorId: null,
          selectedSegments: [],
          viewport: DEFAULT_VIEWPORT,
        })
        showStatus(`Loaded ${rooms.length} room${rooms.length === 1 ? '' : 's'} from ${file.name}`, 'ok')
      } catch {
        showStatus('Invalid manifest JSON.', 'error')
      }
    }
    reader.readAsText(file)
    event.target.value = ''
  }, [replaceWorkspaceState])

  const handleSaveManifest = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/rooms/manifest/save?workspace_id=${encodeURIComponent(workspaceId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_name: workspaceState.projectName,
          svg_path: workspaceState.svgPath,
          rooms: workspaceState.rooms,
        }),
      })
      const data = await res.json()
      if (data.success) showStatus(`Saved to ${data.path}`, 'ok')
      else showStatus(data.error, 'error')
    } catch {
      showStatus('Backend unreachable.', 'error')
    }
  }, [workspaceState.projectName, workspaceState.rooms, workspaceState.svgPath])

  const handleSegmentClick = useCallback((segment: SegmentData, shiftHeld: boolean) => {
    updateWorkspaceState(current => {
      const key = `${segment.x1},${segment.y1},${segment.x2},${segment.y2}`
      const exists = current.selectedSegments.some(item => `${item.x1},${item.y1},${item.x2},${item.y2}` === key)
      const nextSegments = shiftHeld
        ? (exists
          ? current.selectedSegments.filter(item => `${item.x1},${item.y1},${item.x2},${item.y2}` !== key)
          : [...current.selectedSegments, segment])
        : (exists && current.selectedSegments.length === 1 ? [] : [segment])
      return { ...current, selectedSegments: nextSegments }
    })
  }, [updateWorkspaceState])

  const handleCreateRoom = useCallback(() => {
    if (workspaceState.selectedSegments.length === 0) {
      showStatus('Select segments on the canvas first.', 'error')
      return
    }
    setCreateDialog({
      open: true,
      name: `Room_${roomCounter.current}`,
      segments: workspaceState.selectedSegments,
    })
  }, [workspaceState.selectedSegments])

  const handleConfirmCreateRoom = useCallback(async () => {
    if (!createDialog.name.trim()) return
    try {
      const res = await fetch(`${API}/api/rooms/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: createDialog.name.trim(),
          segments: createDialog.segments.map(seg => [seg.x1, seg.y1, seg.x2, seg.y2]),
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
      showStatus(`Room "${nextRoom.room_name}" created.`, 'ok')
    } catch {
      showStatus('Backend unreachable.', 'error')
    }
  }, [commitWorkspaceState, createDialog])

  const handleCanvasCtrlClick = useCallback((worldX: number, worldY: number) => {
    const current = workspaceStateRef.current
    if (!current.selectedRoomName) {
      showStatus('Select a room first.', 'error')
      return
    }
    const room = current.rooms.find(item => item.room_name === current.selectedRoomName)
    if (!room) return
    if (!roomContainsWorldPoint(room, worldX, worldY, 0.05)) {
      showStatus('Anchor must be placed inside room bounds.', 'error')
      return
    }

    const roomIndex = current.rooms.findIndex(item => item.room_name === room.room_name) + 1
    const nextAnchorIndex = anchorCounter.current[room.room_name] ?? room.anchors.length
    anchorCounter.current[room.room_name] = nextAnchorIndex + 1
    const anchorId = `R${roomIndex}A${nextAnchorIndex}`
    const localX = worldX - room.room_bounds_ft.min_x
    const localY = worldY - room.room_bounds_ft.min_y

    commitWorkspaceState(state => ({
      ...state,
      rooms: state.rooms.map(item => {
        if (item.room_name !== room.room_name) return item
        const newAnchor: AnchorData = {
          id: anchorId,
          hw_id: '',
          x_ft: localX,
          y_ft: localY,
          z_ft: 0,
        }
        return {
          ...item,
          anchors: [...item.anchors, newAnchor],
          reference_anchor_id: item.reference_anchor_id ?? anchorId,
        }
      }),
      selectedRoomName: room.room_name,
      selectedAnchorId: anchorId,
    }))
  }, [commitWorkspaceState])

  const handleAnchorClick = useCallback((anchorId: string, roomName: string) => {
    updateWorkspaceState(current => ({
      ...current,
      selectedRoomName: roomName,
      selectedAnchorId: current.selectedAnchorId === anchorId ? null : anchorId,
    }))
  }, [updateWorkspaceState])

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

  const handleEdgesUpdate = useCallback((roomName: string, nextEdges: [string, string][]) => {
    commitWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(room => (
        room.room_name === roomName ? { ...room, edges: nextEdges } : room
      )),
    }))
  }, [commitWorkspaceState])

  const handleAnchorMoveStart = useCallback((_roomName: string, _anchorId: string) => {
    dragSnapshotRef.current = cloneState(workspaceStateRef.current)
  }, [])

  const handleAnchorMove = useCallback((roomName: string, anchorId: string, worldX: number, worldY: number) => {
    updateWorkspaceState(current => ({
      ...current,
      rooms: current.rooms.map(room => {
        if (room.room_name !== roomName) return room
        return {
          ...room,
          anchors: room.anchors.map(anchor => (
            anchor.id !== anchorId
              ? anchor
              : {
                  ...anchor,
                  x_ft: worldX - room.room_bounds_ft.min_x,
                  y_ft: worldY - room.room_bounds_ft.min_y,
                }
          )),
        }
      }),
      selectedRoomName: roomName,
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

  const handleEscapeCanvas = useCallback(() => {
    canvasRef.current?.cancelInteraction()
    canvasRef.current?.focusCanvas()
  }, [])

  useEffect(() => {
    const handleViewCommand = (event: Event) => {
      const detail = (event as CustomEvent).detail as { cmd?: string; workspaceId?: string }
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
        default:
          break
      }
    }

    window.addEventListener('anchor-view-command', handleViewCommand)
    return () => window.removeEventListener('anchor-view-command', handleViewCommand)
  }, [handleRedo, handleUndo, workspaceId])

  return (
    <div className="am-root">
      <div className="am-toolbar">
        <span className="am-project-name">{workspaceState.projectName}</span>
        <div className="am-toolbar-actions">
          <button className="am-btn am-btn--ghost" onClick={() => fileInputRef.current?.click()}>Load SVG</button>
          <button className="am-btn am-btn--ghost" onClick={() => manifestInputRef.current?.click()}>Load Rooms</button>
          <button className="am-btn am-btn--secondary" onClick={handleSaveManifest}>Save Rooms</button>
          {workspaceState.allSegments.length > 0 && (
            <>
              <div className="am-toolbar-sep" />
              <button className="am-btn am-btn--ghost" onClick={handleEscapeCanvas}>Esc</button>
            </>
          )}
          <input ref={fileInputRef} type="file" accept=".svg" style={{ display: 'none' }} onChange={handleLoadSVGFile} />
          <input ref={manifestInputRef} type="file" accept=".json,.rooms.json" style={{ display: 'none' }} onChange={handleLoadManifestFile} />
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
                onViewportChange={viewport => updateWorkspaceState(current => ({ ...current, viewport }))}
                onSegmentClick={handleSegmentClick}
                onCanvasCtrlClick={handleCanvasCtrlClick}
                onAnchorClick={handleAnchorClick}
                onAnchorMoveStart={handleAnchorMoveStart}
                onAnchorMove={handleAnchorMove}
                onAnchorMoveEnd={handleAnchorMoveEnd}
                onNudgeAnchor={handleNudgeAnchor}
              />

              <AnchorEditPanel
                rooms={workspaceState.rooms}
                selectedRoomName={workspaceState.selectedRoomName}
                selectedAnchorId={workspaceState.selectedAnchorId}
                canUndo={undoStack.length > 0}
                canRedo={redoStack.length > 0}
                onRoomSelect={roomName => updateWorkspaceState(current => ({ ...current, selectedRoomName: roomName }))}
                onAnchorUpdate={handleAnchorUpdate}
                onAnchorDelete={handleAnchorDelete}
                onEdgesUpdate={handleEdgesUpdate}
                onAnchorSelect={anchorId => updateWorkspaceState(current => ({ ...current, selectedAnchorId: anchorId }))}
                onReferenceAnchorChange={handleReferenceAnchorChange}
                onUndo={handleUndo}
                onRedo={handleRedo}
                onEscapeCanvas={handleEscapeCanvas}
              />

              {workspaceState.selectedSegments.length > 0 && (
                <div className="am-selection-banner">
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
