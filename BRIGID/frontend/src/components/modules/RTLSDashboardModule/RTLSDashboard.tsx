/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { RoomData, SegmentData } from '../../../types'
import RTLSDashboardCanvas, {
  RTLSDashboardCanvasHandle,
  RTLSTagState,
  tagColor,
} from './RTLSDashboardCanvas'
import RTLSRoomView, { RTLSRoomViewHandle, RTLSVisualSettings, TagAppearance } from './RTLSRoomView'
import './RTLSDashboard.css'

const API = 'http://localhost:8765'
const POLL_MS = 80
const AUTO_LOAD_RETRIES = 6
const AUTO_LOAD_DELAY_MS = 1500

interface RTLSTag {
  tag_id: string
  status: string
  position: { x: number; y: number } | null
  distances: Record<string, number>
}

interface FilterState {
  mode: string
  ema_alpha: number
  roll_n: number
  kal_q: number
  kal_r: number
}

interface ElevationState {
  override: boolean
  value_ft: number
}

interface CSVState {
  enabled: boolean
  path: string
}

interface RoomSettingsState {
  ble_module_port: string
  filter_mode: string
  tag_height_ft: number
}

type RtlsTransportMode = 'serial' | 'ble'

interface FloorplanSegment extends SegmentData {
  role?: string
}

interface RTLSSnapshot {
  mode: RtlsTransportMode | null
  transport_status: string
  transport_detail: string
  selected_port: string
  ports: string[]
  auto_detect_port: string
  ble_available: boolean
  tags: RTLSTag[]
  anchors: Record<string, [number, number]>
  room_name: string
  reference_anchor_id: string
  room_settings: RoomSettingsState
  filter: FilterState
  elevation: ElevationState
  csv: CSVState
  serial_debug: string[]
}

interface RTLSLoadSource {
  manifestPath?: string
  folderPath?: string
  svgFolder?: string
  roomsFolder?: string
  tagsFolder?: string
  projectPath?: string
}

interface RTLSLoadResponse extends RTLSSnapshot {
  success: boolean
  error?: string
  project_name?: string
  room_name: string
  anchor_count: number
  tag_count: number
  available_rooms?: string[]
  rooms?: RoomData[]
  floorplan_segments?: FloorplanSegment[]
}

interface RTLSDashboardProps {
  workspaceId: string
  workspaceName: string
}

interface RoomViewTab {
  id: string
  roomName: string
}

type DashboardPanelTab = 'setup' | 'visuals' | 'analytics'

const DEFAULT_VISUAL: RTLSVisualSettings = {
  heatMap: false,
  heatGradientRate: 0.3,
  heatRange: 5.0,
  heatPeak: 70,
  tagAppearance: 'dots',
}

const emptySnap = (): RTLSSnapshot => ({
  mode: 'serial',
  transport_status: 'idle',
  transport_detail: 'Disconnected.',
  selected_port: '',
  ports: [],
  auto_detect_port: '',
  ble_available: false,
  tags: [],
  anchors: {},
  room_name: '',
  reference_anchor_id: '',
  room_settings: { ble_module_port: '', filter_mode: 'Raw', tag_height_ft: 0 },
  filter: { mode: 'Raw', ema_alpha: 0.2, roll_n: 8, kal_q: 0.1, kal_r: 2.0 },
  elevation: { override: false, value_ft: 3.0 },
  csv: { enabled: false, path: '' },
  serial_debug: [],
})

const normalizeRoomSettings = (settings: RoomData['rtls_settings'] | undefined): RoomData['rtls_settings'] => ({
  tag_height_ft: Number(settings?.tag_height_ft ?? 0),
  filter_mode: (settings?.filter_mode ?? 'Raw') === 'None' ? 'Raw' : (settings?.filter_mode ?? 'Raw'),
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

const transportStatusColor = (status: string): string => {
  const lower = status.toLowerCase()
  if (lower.includes('connected') && !lower.includes('disconnect')) return '#42d17e'
  if (lower.includes('connecting')) return '#ffb11f'
  return '#ff5b4d'
}

const NumInput: React.FC<{
  value: number
  min?: number
  max?: number
  disabled?: boolean
  onChange: (v: number) => void
}> = ({ value, min, max, disabled, onChange }) => {
  const [draft, setDraft] = useState(String(value))
  const focused = useRef(false)

  useEffect(() => {
    if (!focused.current) setDraft(String(value))
  }, [value])

  return (
    <input
      type="text"
      inputMode="decimal"
      className="rtls-num-input"
      value={draft}
      disabled={disabled}
      onChange={e => setDraft(e.target.value)}
      onFocus={() => { focused.current = true }}
      onBlur={() => {
        focused.current = false
        const parsed = parseFloat(draft)
        const clamped = Number.isFinite(parsed)
          ? Math.max(min ?? -Infinity, Math.min(max ?? Infinity, parsed))
          : value
        setDraft(String(clamped))
        onChange(clamped)
      }}
    />
  )
}

const SliderInput: React.FC<{
  label: string
  value: number
  min: number
  max: number
  step: number
  unit: string
  decimals?: number
  onChange: (v: number) => void
}> = ({ label, value, min, max, step, unit, decimals = 1, onChange }) => {
  const formatValue = useCallback((next: number) => next.toFixed(decimals), [decimals])
  const [text, setText] = useState(() => formatValue(value))
  const focused = useRef(false)

  useEffect(() => {
    if (!focused.current) setText(formatValue(value))
  }, [formatValue, value])

  const clamp = useCallback((next: number) => Math.max(min, Math.min(max, next)), [max, min])
  const parsed = parseFloat(text)
  const sliderValue = Number.isFinite(parsed) ? clamp(parsed) : value

  return (
    <div className="rtls-slider-row">
      <div className="rtls-slider-header">
        <span className="rtls-slider-label">{label}</span>
        <div className="rtls-slider-input-group">
          <input
            type="text"
            inputMode="decimal"
            className="rtls-slider-text-input"
            value={text}
            onFocus={() => { focused.current = true }}
            onChange={e => {
              setText(e.target.value)
              const next = parseFloat(e.target.value)
              if (Number.isFinite(next)) onChange(clamp(next))
            }}
            onBlur={() => {
              focused.current = false
              const next = parseFloat(text)
              const clamped = Number.isFinite(next) ? clamp(next) : value
              setText(formatValue(clamped))
              onChange(clamped)
            }}
            onKeyDown={e => {
              if (e.key !== 'Enter') return
              const next = parseFloat(text)
              const clamped = Number.isFinite(next) ? clamp(next) : value
              setText(formatValue(clamped))
              onChange(clamped)
              ;(e.target as HTMLInputElement).blur()
            }}
          />
          <span className="rtls-slider-unit">{unit}</span>
        </div>
      </div>
      <input
        type="range"
        className="rtls-range"
        min={min}
        max={max}
        step={step}
        value={sliderValue}
        onChange={e => {
          const next = parseFloat(e.target.value)
          setText(formatValue(next))
          onChange(next)
        }}
      />
    </div>
  )
}

const RTLSDashboard: React.FC<RTLSDashboardProps> = ({ workspaceId, workspaceName }) => {
  const [snap, setSnap] = useState<RTLSSnapshot>(emptySnap)
  const [rooms, setRooms] = useState<RoomData[]>([])
  const [floorplanSegments, setFloorplanSegments] = useState<FloorplanSegment[]>([])
  const [projectName, setProjectName] = useState('')
  const [roomLoaded, setRoomLoaded] = useState(false)
  const [autoLoading, setAutoLoading] = useState(false)
  const [statusMsg, setStatusMsg] = useState<{ text: string; kind: 'ok' | 'warn' | 'error' } | null>(null)
  const [activeTab, setActiveTab] = useState<string>('floor-plan')
  const [roomTabs, setRoomTabs] = useState<RoomViewTab[]>([])
  const [selectedRoomName, setSelectedRoomName] = useState<string | null>(null)
  const [hoverRoomName, setHoverRoomName] = useState<string | null>(null)
  const [transportMode, setTransportMode] = useState<RtlsTransportMode>('serial')
  const [activePanelTab, setActivePanelTab] = useState<DashboardPanelTab>('setup')
  const [visualSettings, setVisualSettings] = useState<RTLSVisualSettings>(DEFAULT_VISUAL)

  const floorplanCanvasRef = useRef<RTLSDashboardCanvasHandle>(null)
  const roomViewRef = useRef<RTLSRoomViewHandle>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const busyRef = useRef(false)
  const loadSourceRef = useRef<RTLSLoadSource>({})
  const statusTimerRef = useRef<number | null>(null)

  const solveRoom = useMemo(
    () => rooms.find(room => room.room_name === snap.room_name) ?? null,
    [rooms, snap.room_name],
  )

  const selectedRoom = useMemo(
    () => rooms.find(room => room.room_name === selectedRoomName) ?? null,
    [rooms, selectedRoomName],
  )

  const activeRoomTab = useMemo(
    () => roomTabs.find(tab => tab.id === activeTab) ?? null,
    [activeTab, roomTabs],
  )

  const canvasMode = activeTab === 'floor-plan' ? 'floor-plan' : 'room'
  const visibleRoom = useMemo(
    () => canvasMode === 'room'
      ? rooms.find(room => room.room_name === activeRoomTab?.roomName) ?? null
      : selectedRoom,
    [activeRoomTab?.roomName, canvasMode, rooms, selectedRoom],
  )

  const tagStates: RTLSTagState[] = useMemo(
    () => snap.tags.map((tag, index) => ({
      tag_id: tag.tag_id,
      status: tag.status,
      position: tag.position,
      color: tagColor(index),
    })),
    [snap.tags],
  )

  const savedModulePort = visibleRoom?.rtls_settings?.ble_module_port?.trim()
    || selectedRoom?.rtls_settings?.ble_module_port?.trim()
    || solveRoom?.rtls_settings?.ble_module_port?.trim()
    || snap.room_settings?.ble_module_port?.trim()
    || ''

  const activeViewLabel = activeTab === 'floor-plan'
    ? 'Floor Plan'
    : `${activeRoomTab?.roomName ?? 'Room'} Room View`
  const isRoomView = canvasMode === 'room'

  const panelSubtitle = [
    projectName || workspaceName || 'RTLS Dashboard',
    activeViewLabel,
    selectedRoomName ? `Selected room: ${selectedRoomName}` : null,
    snap.room_name ? `Active solve room: ${snap.room_name}` : null,
  ].filter(Boolean).join(' · ')

  useEffect(() => {
    if (snap.mode === 'ble' || snap.mode === 'serial') setTransportMode(snap.mode)
  }, [snap.mode])

  const showMsg = useCallback((text: string, kind: 'ok' | 'warn' | 'error', ms = 4000) => {
    setStatusMsg({ text, kind })
    if (statusTimerRef.current) window.clearTimeout(statusTimerRef.current)
    statusTimerRef.current = window.setTimeout(() => {
      setStatusMsg(null)
      statusTimerRef.current = null
    }, ms)
  }, [])

  useEffect(() => () => {
    if (statusTimerRef.current) window.clearTimeout(statusTimerRef.current)
  }, [])

  const poll = useCallback(async () => {
    if (busyRef.current) return
    busyRef.current = true
    try {
      const res = await fetch(`${API}/api/rtls/snapshot`)
      if (!res.ok) return
      const data = await res.json()
      if (data.success) setSnap(data as RTLSSnapshot)
    } catch {
      /* backend may not be ready */
    } finally {
      busyRef.current = false
    }
  }, [])

  useEffect(() => {
    pollRef.current = setInterval(poll, POLL_MS)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [poll])

  const resetCanvasSoon = useCallback(() => {
    window.setTimeout(() => {
      floorplanCanvasRef.current?.resetView()
      roomViewRef.current?.resetView()
    }, 80)
  }, [])

  const loadWorkspace = useCallback(async (
    source: RTLSLoadSource = loadSourceRef.current,
    opts?: { roomName?: string; silent?: boolean },
  ) => {
    try {
      const res = await fetch(`${API}/api/rtls/workspace/load`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceId,
          workspace_name: workspaceName,
          manifest_path: source.manifestPath ?? null,
          folder_path: source.folderPath ?? null,
          svg_folder: source.svgFolder ?? null,
          rooms_folder: source.roomsFolder ?? null,
          tags_folder: source.tagsFolder ?? null,
          project_path: source.projectPath ?? null,
          room_name: opts?.roomName ?? null,
        }),
      })
      const data = await res.json() as RTLSLoadResponse
      if (!data.success) {
        if (!opts?.silent) showMsg(data.error ?? 'No RTLS project data found.', 'warn')
        return false
      }

      loadSourceRef.current = source
      const nextRooms = Array.isArray(data.rooms) ? data.rooms.map(normalizeRoom) : []
      setSnap(data as RTLSSnapshot)
      setRooms(nextRooms)
      setFloorplanSegments(Array.isArray(data.floorplan_segments) ? data.floorplan_segments : [])
      setProjectName(data.project_name ?? '')
      setRoomLoaded(true)
      setHoverRoomName(null)
      setSelectedRoomName(currentSelected => {
        const requested = opts?.roomName ?? data.room_name ?? currentSelected
        if (requested && nextRooms.some(room => room.room_name === requested)) return requested
        return nextRooms[0]?.room_name ?? null
      })
      showMsg(`Loaded ${data.room_name || 'project'}: ${data.anchor_count} anchors, ${data.tag_count} profiled tags.`, 'ok')
      resetCanvasSoon()
      return true
    } catch {
      if (!opts?.silent) showMsg('Backend unavailable.', 'error')
      return false
    }
  }, [resetCanvasSoon, showMsg, workspaceId, workspaceName])

  useEffect(() => {
    setSnap(emptySnap())
    setRooms([])
    setFloorplanSegments([])
    setProjectName('')
    setRoomLoaded(false)
    setRoomTabs([])
    setSelectedRoomName(null)
    setActiveTab('floor-plan')
    setHoverRoomName(null)
    loadSourceRef.current = {}
    setAutoLoading(true)

    let cancelled = false
    let attempt = 0

    const tryLoad = async () => {
      if (cancelled) return
      attempt += 1
      const isFinal = attempt >= AUTO_LOAD_RETRIES
      const ok = await loadWorkspace({}, { silent: !isFinal })
      if (cancelled) return
      if (ok || isFinal) {
        setAutoLoading(false)
        return
      }
      window.setTimeout(tryLoad, AUTO_LOAD_DELAY_MS)
    }

    void tryLoad()

    return () => {
      cancelled = true
      setAutoLoading(false)
    }
  }, [loadWorkspace, workspaceId])

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { cmd: string; workspaceId: string }
      if (detail.workspaceId !== workspaceId) return

      const requestedRoom = activeTab === 'floor-plan'
        ? (selectedRoomName || snap.room_name || undefined)
        : (activeRoomTab?.roomName || selectedRoomName || undefined)
      if (detail.cmd === 'refresh') {
        void loadWorkspace(loadSourceRef.current, { roomName: requestedRoom })
        return
      }

      const currentView = activeTab === 'floor-plan' ? floorplanCanvasRef.current : roomViewRef.current
      if (!currentView) return
      if (detail.cmd === 'zoom_in') currentView.zoomIn()
      else if (detail.cmd === 'zoom_out') currentView.zoomOut()
      else if (detail.cmd === 'zoom_reset') currentView.resetView()
    }

    window.addEventListener('rtls-view-command', handler)
    return () => window.removeEventListener('rtls-view-command', handler)
  }, [activeRoomTab?.roomName, activeTab, loadWorkspace, selectedRoomName, snap.room_name, workspaceId])

  const currentCompositeSource = useCallback((): RTLSLoadSource => {
    const current = loadSourceRef.current
    if (current.projectPath) {
      return { projectPath: current.projectPath, tagsFolder: current.tagsFolder }
    }
    if (current.folderPath) {
      return { folderPath: current.folderPath, tagsFolder: current.tagsFolder }
    }
    return {
      manifestPath: current.manifestPath,
      roomsFolder: current.roomsFolder,
      svgFolder: current.svgFolder,
      tagsFolder: current.tagsFolder,
    }
  }, [])

  const resetViewState = useCallback(() => {
    setActiveTab('floor-plan')
    setRoomTabs([])
    setSelectedRoomName(null)
    setHoverRoomName(null)
  }, [])

  const loadProject = useCallback(async () => {
    const r = await window.api?.openFile?.([{ name: 'RTLS Project', extensions: ['rtls'] }])
    if (r && !r.canceled && r.filePaths[0]) {
      resetViewState()
      await loadWorkspace({ projectPath: r.filePaths[0] })
    }
  }, [loadWorkspace, resetViewState])

  const loadFolder = useCallback(async () => {
    const r = await window.api?.openFolder?.()
    if (r && !r.canceled && r.folderPath) {
      resetViewState()
      await loadWorkspace({ folderPath: r.folderPath })
    }
  }, [loadWorkspace, resetViewState])

  const loadRoomsFolder = useCallback(async () => {
    const r = await window.api?.openFolder?.()
    if (r && !r.canceled && r.folderPath) {
      resetViewState()
      await loadWorkspace({
        ...currentCompositeSource(),
        manifestPath: undefined,
        projectPath: undefined,
        folderPath: undefined,
        roomsFolder: r.folderPath,
      })
    }
  }, [currentCompositeSource, loadWorkspace, resetViewState])

  const loadTagsFolder = useCallback(async () => {
    const r = await window.api?.openFolder?.()
    if (r && !r.canceled && r.folderPath) {
      await loadWorkspace({
        ...currentCompositeSource(),
        tagsFolder: r.folderPath,
      }, { roomName: selectedRoomName || snap.room_name || undefined })
    }
  }, [currentCompositeSource, loadWorkspace, selectedRoomName, snap.room_name])

  const loadSvgFolder = useCallback(async () => {
    const r = await window.api?.openFolder?.()
    if (r && !r.canceled && r.folderPath) {
      await loadWorkspace({
        ...currentCompositeSource(),
        svgFolder: r.folderPath,
      }, { roomName: selectedRoomName || snap.room_name || undefined })
    }
  }, [currentCompositeSource, loadWorkspace, selectedRoomName, snap.room_name])

  const connect = useCallback(async () => {
    const port = transportMode === 'serial' ? (snap.selected_port || savedModulePort || snap.auto_detect_port) : ''
    if (transportMode === 'serial' && !port) {
      showMsg('Select a module port first.', 'warn')
      return
    }
    try {
      const res = await fetch(`${API}/api/rtls/transport/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: transportMode, port }),
      })
      const data = await res.json()
      if (data.success) {
        setSnap(data as RTLSSnapshot)
        showMsg(transportMode === 'serial' ? `Connected to ${port}.` : 'BLE listeners started.', 'ok')
      } else {
        showMsg(data.error ?? 'Could not connect to RTLS transport.', 'warn')
      }
    } catch {
      showMsg('Could not connect to RTLS transport.', 'error')
    }
  }, [savedModulePort, showMsg, snap.auto_detect_port, snap.selected_port, transportMode])

  const disconnect = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/rtls/transport/disconnect`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setSnap(data as RTLSSnapshot)
        showMsg('RTLS transport disconnected.', 'ok')
      }
    } catch {
      showMsg('Could not disconnect RTLS transport.', 'error')
    }
  }, [showMsg])

  const setFilter = useCallback(async (patch: Partial<FilterState>) => {
    const next = { ...snap.filter, ...patch }
    setSnap(prev => ({ ...prev, filter: next }))
    try {
      await fetch(`${API}/api/rtls/filter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
    } catch {
      /* ignore */
    }
  }, [snap.filter])

  const setElevation = useCallback(async (patch: Partial<ElevationState>) => {
    const next = { ...snap.elevation, ...patch }
    setSnap(prev => ({ ...prev, elevation: next }))
    try {
      await fetch(`${API}/api/rtls/elevation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override: next.override, value_ft: next.value_ft }),
      })
    } catch {
      /* ignore */
    }
  }, [snap.elevation])

  const toggleCsv = useCallback(async () => {
    const stopping = snap.csv.enabled
    const endpoint = stopping ? '/api/rtls/csv/stop' : '/api/rtls/csv/start'
    try {
      const res = await fetch(`${API}${endpoint}`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setSnap(data as RTLSSnapshot)
        showMsg(stopping ? 'CSV logging stopped.' : 'CSV logging started.', 'ok')
      } else {
        showMsg(data.error ?? 'CSV logging error.', 'warn')
      }
    } catch {
      showMsg('Could not change CSV logging state.', 'error')
    }
  }, [showMsg, snap.csv.enabled])

  const selectRoom = useCallback(async (roomName: string) => {
    setSelectedRoomName(roomName)
    if (roomName === snap.room_name && roomLoaded) return
    await loadWorkspace(loadSourceRef.current, { roomName })
  }, [loadWorkspace, roomLoaded, snap.room_name])

  const openRoomTab = useCallback((roomName: string) => {
    const tabId = `room-view-${roomName}`
    setSelectedRoomName(roomName)
    setRoomTabs(current => current.some(tab => tab.id === tabId) ? current : [...current, { id: tabId, roomName }])
    setActiveTab(tabId)
    if (roomName !== snap.room_name || !roomLoaded) {
      void loadWorkspace(loadSourceRef.current, { roomName })
    }
  }, [loadWorkspace, roomLoaded, snap.room_name])

  const closeRoomTab = useCallback((tabId: string) => {
    setRoomTabs(current => {
      const remaining = current.filter(tab => tab.id !== tabId)
      setActiveTab(currentActive => {
        if (currentActive !== tabId) return currentActive
        const closedIndex = current.findIndex(tab => tab.id === tabId)
        return remaining[Math.max(0, closedIndex - 1)]?.id ?? 'floor-plan'
      })
      return remaining
    })
  }, [])

  const handleTabClick = useCallback((tabId: string) => {
    setActiveTab(tabId)
    if (tabId !== 'floor-plan') {
      const tab = roomTabs.find(entry => entry.id === tabId)
      if (tab) {
        setSelectedRoomName(tab.roomName)
        if (tab.roomName !== snap.room_name || !roomLoaded) {
          void loadWorkspace(loadSourceRef.current, { roomName: tab.roomName })
        }
      }
    }
  }, [loadWorkspace, roomLoaded, roomTabs, snap.room_name])

  let refX = 0
  let refY = 0
  if (snap.reference_anchor_id && snap.anchors[snap.reference_anchor_id]) {
    ;[refX, refY] = snap.anchors[snap.reference_anchor_id]
  }

  const renderRoomManagerSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Room Manager</div>
      <div className="rtls-room-chip-list">
        {rooms.length === 0 && (
          <div className="rtls-runtime-note">Load a project to restore the floor plan and room definitions.</div>
        )}
        {rooms.map(room => {
          const isSelected = room.room_name === selectedRoomName
          const isHovered = room.room_name === hoverRoomName
          const isOpen = roomTabs.some(tab => tab.roomName === room.room_name)
          return (
            <button
              key={room.room_name}
              className={`rtls-room-chip${isSelected ? ' active' : ''}${isHovered ? ' hovered' : ''}${isOpen ? ' open' : ''}`}
              onClick={() => void selectRoom(room.room_name)}
              onMouseEnter={() => setHoverRoomName(room.room_name)}
              onMouseLeave={() => setHoverRoomName(null)}
              onDoubleClick={() => void openRoomTab(room.room_name)}
            >
              <span className="rtls-room-chip__name">{room.room_name}</span>
              <span className="rtls-room-chip__meta">
                {room.anchors.length} anchor{room.anchors.length !== 1 ? 's' : ''}
              </span>
            </button>
          )
        })}
      </div>
      <div className="rtls-runtime-note">
        Click a room to target it on the floor plan. Double-click a room or room outline to open a room tab.
      </div>
    </div>
  )

  const renderTransportSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Connectivity</div>
      <div className="rtls-transport-tabs">
        <button
          className={`rtls-btn rtls-transport-tab${transportMode === 'ble' ? ' rtls-transport-tab--active' : ''}`}
          disabled={!snap.ble_available}
          onClick={() => setTransportMode('ble')}
        >
          Bluetooth (BLE)
        </button>
        <button
          className={`rtls-btn rtls-transport-tab${transportMode === 'serial' ? ' rtls-transport-tab--active' : ''}`}
          onClick={() => setTransportMode('serial')}
        >
          Serial Port
        </button>
      </div>
      {transportMode === 'serial' ? (
        <select
          className="rtls-input"
          value={snap.selected_port || savedModulePort || snap.auto_detect_port || ''}
          onChange={e => setSnap(prev => ({ ...prev, selected_port: e.target.value }))}
        >
          <option value="">Select a module port</option>
          {Array.from(new Set([savedModulePort, snap.auto_detect_port, ...snap.ports].filter(Boolean))).map(port => (
            <option key={port} value={port}>{port}</option>
          ))}
        </select>
      ) : (
        <div className="rtls-runtime-note">
          BLE uses the MAC addresses saved in each tag profile for the active RTLS room.
        </div>
      )}
      <div className="rtls-runtime-note">{snap.transport_detail}</div>
      {snap.tags.length > 0 ? (
        <div className="rtls-ble-rows">
          {snap.tags.map((tag, index) => (
            <div key={tag.tag_id} className="rtls-ble-row">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="rtls-tag-dot" style={{ background: tagColor(index) }} />
                {tag.tag_id}
              </span>
              <span style={{ color: transportStatusColor(tag.status), fontWeight: 600 }}>{tag.status}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="rtls-runtime-note">No profiled tags available yet.</div>
      )}
      {snap.serial_debug.length > 0 && (
        <div className="rtls-serial-log">
          {snap.serial_debug.slice(-12).map((line, index) => (
            <div key={`${index}-${line}`} className="rtls-serial-log__line">{line}</div>
          ))}
        </div>
      )}
      <div className="rtls-connect-row">
        <button
          className="rtls-btn rtls-btn--primary"
          style={{ flex: 1 }}
          disabled={snap.transport_status === 'connected'}
          onClick={() => void connect()}
        >
          Connect
        </button>
        <button
          className="rtls-btn"
          style={{ flex: 1 }}
          disabled={snap.transport_status === 'idle'}
          onClick={() => void disconnect()}
        >
          Disconnect
        </button>
      </div>
    </div>
  )

  const renderTagCoordinatesSection = () => (
    snap.tags.length > 0 ? (
      <div className="rtls-section">
        <div className="rtls-section-title">Coordinates (ft)</div>
        <div className="rtls-ble-rows">
          {snap.tags.map((tag, index) => (
            <div key={tag.tag_id} className="rtls-ble-row">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="rtls-tag-dot" style={{ background: tagColor(index) }} />
                {tag.tag_id}
              </span>
              <span>
                {tag.position
                  ? `(${(tag.position.x - refX).toFixed(2)}, ${(tag.position.y - refY).toFixed(2)})`
                  : '(---, ---)'}
              </span>
            </div>
          ))}
        </div>
      </div>
    ) : null
  )

  const renderTagElevationSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Tag Elevation</div>
      <label className="rtls-check">
        <input
          type="checkbox"
          checked={snap.elevation.override}
          onChange={e => void setElevation({ override: e.target.checked })}
        />
        Manual Z-Height Override
      </label>
      {snap.elevation.override && (
        <div className="rtls-elevation-row">
          <div className="rtls-elevation-label">Height (ft):</div>
          <NumInput
            value={snap.elevation.value_ft}
            min={0}
            max={30}
            onChange={value => void setElevation({ value_ft: value })}
          />
        </div>
      )}
    </div>
  )

  const renderSmoothingFilterSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Smoothing Filter</div>
      <div className="rtls-transport-tabs">
        {(['Raw', 'EMA', 'Rolling', 'Kalman'] as const).map(mode => (
          <button
            key={mode}
            className={`rtls-filter-tab${snap.filter.mode === mode ? ' active' : ''}`}
            onClick={() => void setFilter({ mode })}
          >
            {mode}
          </button>
        ))}
      </div>
      <div className="rtls-slider-row">
        <div className="rtls-slider-header">
          <span className="rtls-slider-label">EMA α</span>
          <span className="rtls-slider-value">{snap.filter.ema_alpha.toFixed(2)}</span>
        </div>
        <input
          type="range"
          className="rtls-range"
          min={0.01}
          max={0.99}
          step={0.01}
          value={snap.filter.ema_alpha}
          disabled={snap.filter.mode !== 'EMA'}
          onChange={e => void setFilter({ ema_alpha: parseFloat(e.target.value) })}
        />
      </div>
      <div className="rtls-slider-row">
        <div className="rtls-slider-header">
          <span className="rtls-slider-label">Rolling N</span>
          <span className="rtls-slider-value">{snap.filter.roll_n}</span>
        </div>
        <input
          type="range"
          className="rtls-range"
          min={2}
          max={30}
          step={1}
          value={snap.filter.roll_n}
          disabled={snap.filter.mode !== 'Rolling'}
          onChange={e => void setFilter({ roll_n: parseInt(e.target.value, 10) })}
        />
      </div>
      <div className="rtls-slider-row">
        <div className="rtls-slider-header">
          <span className="rtls-slider-label">Kalman Q</span>
          <span className="rtls-slider-value">{snap.filter.kal_q.toFixed(3)}</span>
        </div>
        <input
          type="range"
          className="rtls-range"
          min={0.001}
          max={1}
          step={0.001}
          value={snap.filter.kal_q}
          disabled={snap.filter.mode !== 'Kalman'}
          onChange={e => void setFilter({ kal_q: parseFloat(e.target.value) })}
        />
      </div>
      <div className="rtls-slider-row">
        <div className="rtls-slider-header">
          <span className="rtls-slider-label">Kalman R</span>
          <span className="rtls-slider-value">{snap.filter.kal_r.toFixed(1)}</span>
        </div>
        <input
          type="range"
          className="rtls-range"
          min={0.1}
          max={20}
          step={0.1}
          value={snap.filter.kal_r}
          disabled={snap.filter.mode !== 'Kalman'}
          onChange={e => void setFilter({ kal_r: parseFloat(e.target.value) })}
        />
      </div>
    </div>
  )

  const renderCsvSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Log CSV</div>
      <button
        className={`rtls-btn rtls-btn--full ${snap.csv.enabled ? 'rtls-btn--danger' : 'rtls-btn--primary'}`}
        onClick={() => void toggleCsv()}
      >
        {snap.csv.enabled ? 'Stop Logging' : 'Start Logging'}
      </button>
      {snap.csv.enabled && snap.csv.path && (
        <div className="rtls-csv-path">{snap.csv.path}</div>
      )}
    </div>
  )

  const renderSetupTab = () => (
    <>
      {renderRoomManagerSection()}
      {isRoomView && (
        <div className="rtls-section">
          <div className="rtls-section-title">Room View</div>
          <div className="rtls-panel-info-grid">
            <div className="rtls-panel-info-card">
              <span className="rtls-panel-info-card__label">Room</span>
              <span className="rtls-panel-info-card__value">{visibleRoom?.room_name ?? '—'}</span>
            </div>
            <div className="rtls-panel-info-card">
              <span className="rtls-panel-info-card__label">Module</span>
              <span className="rtls-panel-info-card__value">{savedModulePort || 'Not assigned'}</span>
            </div>
          </div>
          <div className="rtls-runtime-note">
            Room-specific connectivity and coordinates live here so the floor-plan setup stays cleaner.
          </div>
        </div>
      )}
      {isRoomView && renderTransportSection()}
      {isRoomView && renderTagCoordinatesSection()}
      {renderTagElevationSection()}
      {renderSmoothingFilterSection()}
      {renderCsvSection()}
    </>
  )

  const renderVisualsTab = () => (
    <>
      <div className="rtls-section">
        <div className="rtls-section-title">Heat Map</div>
        <div className="rtls-toggle-row">
          <span className="rtls-toggle-label">Enable Heat Map</span>
          <label className="rtls-toggle">
            <input
              type="checkbox"
              checked={visualSettings.heatMap}
              onChange={e => setVisualSettings(current => ({ ...current, heatMap: e.target.checked }))}
            />
            <span className="rtls-toggle-slider" />
          </label>
        </div>
        <SliderInput
          label="Exposure Rate"
          value={visualSettings.heatGradientRate}
          min={0.05}
          max={5.0}
          step={0.05}
          unit="s/step"
          decimals={2}
          onChange={value => setVisualSettings(current => ({ ...current, heatGradientRate: value }))}
        />
        <SliderInput
          label="Range"
          value={visualSettings.heatRange}
          min={0.5}
          max={30}
          step={0.5}
          unit="ft"
          decimals={1}
          onChange={value => setVisualSettings(current => ({ ...current, heatRange: value }))}
        />
        <div className="rtls-slider-row">
          <div className="rtls-slider-header">
            <span className="rtls-slider-label">Peak Color</span>
            <span className="rtls-slider-value">{visualSettings.heatPeak}</span>
          </div>
          <input
            type="range"
            className="rtls-range"
            min={1}
            max={100}
            step={1}
            value={visualSettings.heatPeak}
            onChange={e => setVisualSettings(current => ({ ...current, heatPeak: parseInt(e.target.value, 10) }))}
          />
        </div>
        <div className="rtls-runtime-note">
          Heat is now driven only by live tag coordinates in room view, using the same grid size and deposit logic as your reference implementation.
        </div>
      </div>

      <div className="rtls-section">
        <div className="rtls-section-title">Tag Appearance</div>
        <div className="rtls-transport-tabs">
          {([
            ['invisible', 'Invisible'],
            ['dots', 'Normal'],
            ['human', 'Human'],
          ] as [TagAppearance, string][]).map(([value, label]) => (
            <button
              key={value}
              className={`rtls-btn rtls-transport-tab${visualSettings.tagAppearance === value ? ' rtls-transport-tab--active' : ''}`}
              onClick={() => setVisualSettings(current => ({ ...current, tagAppearance: value }))}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="rtls-runtime-note">
          Human mode replaces the live tag dots with the walking-frame animation assets. The animation direction is inferred from real tag movement between hardware updates.
        </div>
        {!isRoomView && (
          <div className="rtls-placeholder-item">
            Visuals are shown in room view so the heat map and tag appearance stay clipped to the active room geometry.
          </div>
        )}
      </div>

      <div className="rtls-section">
        <div className="rtls-section-title">Reference Alignment</div>
        <div className="rtls-placeholder-list">
          <div className="rtls-placeholder-item">Heat map resolution stays at 0.02 ft per cell with the same offscreen raster and lookup-table rendering strategy from the docs.</div>
          <div className="rtls-placeholder-item">The simulated bot controls from the reference were intentionally omitted so visuals apply only to real RTLS hardware tags.</div>
        </div>
      </div>
    </>
  )

  const renderAnalyticsTab = () => (
    <>
      <div className="rtls-section">
        <div className="rtls-section-title">Analytics</div>
        <div className="rtls-runtime-note">
          This tab is staged for future exposure and occupancy views that build on the same heatmap-oriented data flow from the docs.
        </div>
      </div>
      <div className="rtls-section">
        <div className="rtls-section-title">Planned Outputs</div>
        <div className="rtls-placeholder-list">
          <div className="rtls-placeholder-item">Room-level exposure summaries and trend views.</div>
          <div className="rtls-placeholder-item">Session insights derived from live tags plus upcoming simulated visual layers.</div>
        </div>
      </div>
    </>
  )

  return (
    <div className="rtls-root">
      <div className="rtls-stage">
        <div className="rtls-main-panel">
          {roomLoaded && (
            <div className="rtls-inner-tabbar">
              <button
                className={`rtls-inner-tab${activeTab === 'floor-plan' ? ' rtls-inner-tab--active' : ''}`}
                onClick={() => void handleTabClick('floor-plan')}
              >
                Floor Plan
              </button>
              {roomTabs.map(tab => (
                <button
                  key={tab.id}
                  className={`rtls-inner-tab${activeTab === tab.id ? ' rtls-inner-tab--active' : ''}`}
                  onClick={() => void handleTabClick(tab.id)}
                >
                  {tab.roomName}
                  <span
                    className="rtls-inner-tab-close"
                    role="button"
                    onClick={e => {
                      e.stopPropagation()
                      closeRoomTab(tab.id)
                    }}
                  >
                    ×
                  </span>
                </button>
              ))}
            </div>
          )}

          {!roomLoaded ? (
            <div className="rtls-no-room">
              <div className="rtls-no-room-icon">{autoLoading ? '◌' : '◎'}</div>
              <div className="rtls-no-room-text">
                {autoLoading
                  ? 'Connecting to backend…'
                  : <>No RTLS project loaded.<br />Load a project or workspace to begin.</>}
              </div>
            </div>
          ) : activeTab === 'floor-plan' ? (
            <RTLSDashboardCanvas
              ref={floorplanCanvasRef}
              mode="floor-plan"
              floorplanSegments={floorplanSegments}
              rooms={rooms}
              activeRoomName={selectedRoomName}
              currentRoom={selectedRoom}
              hoverRoomName={hoverRoomName}
              anchors={snap.anchors}
              tags={tagStates}
              referenceAnchorId={snap.reference_anchor_id}
              onRoomClick={roomName => void selectRoom(roomName)}
              onRoomDoubleClick={roomName => void openRoomTab(roomName)}
              onRoomHover={setHoverRoomName}
            />
          ) : visibleRoom ? (
            <RTLSRoomView
              ref={roomViewRef}
              room={visibleRoom}
              tags={tagStates}
              activeSolveRoomName={snap.room_name || null}
              referenceAnchorId={snap.reference_anchor_id}
              visualSettings={visualSettings}
            />
          ) : (
            <div className="rtls-no-room">
              <div className="rtls-no-room-icon">◎</div>
              <div className="rtls-no-room-text">
                Room data is unavailable for this tab.
              </div>
            </div>
          )}
        </div>

        {statusMsg && (
          <div className={`rtls-status rtls-status--${statusMsg.kind}`}>
            {statusMsg.text}
          </div>
        )}

        <div className="rtls-right-panel">
          <div className="rtls-panel-header">
            <div>
              <div className="rtls-panel-title">RTLS Dashboard</div>
              <div className="rtls-panel-subtitle">{panelSubtitle}</div>
            </div>
          </div>

          <div className="rtls-panel-body">
            <div className="rtls-section">
              <div className="rtls-section-title">Load</div>
              <button className="rtls-btn rtls-btn--primary rtls-btn--full" onClick={() => void loadProject()}>
                Load Project…
              </button>
              <div className="rtls-section-title" style={{ marginTop: 8 }}>Load Individually</div>
              <div className="rtls-load-row">
                <button className="rtls-btn" style={{ flex: 1 }} onClick={() => void loadFolder()}>Workspace…</button>
                <button className="rtls-btn" style={{ flex: 1 }} onClick={() => void loadRoomsFolder()}>Rooms…</button>
                <button className="rtls-btn" style={{ flex: 1 }} onClick={() => void loadTagsFolder()}>Tags…</button>
                <button className="rtls-btn" style={{ flex: 1 }} onClick={() => void loadSvgFolder()}>SVG…</button>
              </div>
              <div className="rtls-runtime-note">
                RTLS reuses the finished Anchor Manager project: full floor plan as the environment, room tabs as focused subsets.
              </div>
            </div>

            <div className="rtls-section">
              <div className="rtls-section-title">Tabs</div>
              <div className="rtls-dashboard-tabs">
                {([
                  ['setup', 'Setup'],
                  ['visuals', 'Visuals'],
                  ['analytics', 'Analytics'],
                ] as [DashboardPanelTab, string][]).map(([tabId, label]) => (
                  <button
                    key={tabId}
                    className={`rtls-btn rtls-dashboard-tab${activePanelTab === tabId ? ' rtls-dashboard-tab--active' : ''}`}
                    onClick={() => setActivePanelTab(tabId)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {activePanelTab === 'setup' && renderSetupTab()}
            {activePanelTab === 'visuals' && renderVisualsTab()}
            {activePanelTab === 'analytics' && renderAnalyticsTab()}
          </div>
        </div>
      </div>
    </div>
  )
}

export default RTLSDashboard
