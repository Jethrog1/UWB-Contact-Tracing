/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { RoomData, SegmentData } from '../../../types'
import RTLSDashboardCanvas, {
  RTLSDashboardCanvasHandle,
  RTLSTagState,
  tagColor,
} from './RTLSDashboardCanvas'
import RTLSRoomView, { RTLSRoomViewHandle, RTLSVisualSettings, TagAppearance } from './RTLSRoomView'
import { confirmAsync } from '../../common/ConfirmDialog'
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

interface NoiseCancelState {
  enabled: boolean
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
  noise_cancel: NoiseCancelState
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

interface RTLSAnalyticsSummary {
  rows_analyzed: number
  unique_tags: number
  unique_pairs: number
  time_windows: number
  peak_probability_pct: number
  avg_probability_pct: number
  latest_window: string | null
  highest_tag: string | null
}

interface RTLSAnalyticsWindow {
  rank: number
  pair: string
  tag_a: string
  tag_b: string
  chunk_start: string | null
  first_seen: string | null
  last_seen: string | null
  risk_band: string
  probability_pct: number
  predicted_positive: boolean
  close_contact_minutes: number
  cumulative_contact_hours: number
  exposure_minutes: number
  infection_pressure: number
  mean_distance_ft: number
  min_distance_ft: number
}

interface RTLSAnalyticsPairSummary {
  pair: string
  tag_a: string
  tag_b: string
  max_probability_pct: number
  avg_probability_pct: number
  latest_probability_pct: number
  windows_analyzed: number
  windows_above_50: number
  total_close_contact_hours: number
  total_exposure_hours: number
  peak_window: string | null
  peak_risk_band: string
}

interface RTLSAnalyticsTagSummary {
  tag_id: string
  max_probability_pct: number
  avg_probability_pct: number
  linked_pairs: number
  total_close_contact_hours: number
  peak_pair: string
  peak_window: string | null
  peak_risk_band: string
}

interface RTLSAnalyticsTrendPoint {
  chunk_start: string | null
  peak_probability_pct: number
  mean_probability_pct: number
  window_count: number
}

interface RTLSAnalyticsResponse {
  success: boolean
  error?: string
  csv_path: string
  generated_at: string
  chunk_minutes: number
  model_name: string
  summary: RTLSAnalyticsSummary
  hottest_window: RTLSAnalyticsWindow | null
  top_windows: RTLSAnalyticsWindow[]
  pair_leaderboard: RTLSAnalyticsPairSummary[]
  tag_leaderboard: RTLSAnalyticsTagSummary[]
  trend: RTLSAnalyticsTrendPoint[]
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

export interface FloorplanSettings {
  heatMap: boolean
  heatGradientRate: number
  heatRange: number
  heatPeak: number
  showAnchors: boolean
  showAnchorLabels: boolean
}

const DEFAULT_VISUAL: RTLSVisualSettings = {
  heatMap: false,
  heatGradientRate: 0.3,
  heatRange: 5.0,
  heatPeak: 70,
  tagAppearance: 'dots',
  showInterTagLines: true,
  showAnchors: true,
  showAnchorLabels: true,
}

const DEFAULT_FLOORPLAN: FloorplanSettings = {
  heatMap: false,
  heatGradientRate: 0.3,
  heatRange: 5.0,
  heatPeak: 70,
  showAnchors: false,
  showAnchorLabels: false,
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
  noise_cancel: { enabled: false },
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

const formatPercent = (value: number | null | undefined): string => (
  typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)}%` : '—'
)

const formatHours = (value: number | null | undefined): string => (
  typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)} h` : '—'
)

const formatMinutes = (value: number | null | undefined): string => (
  typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(1)} min` : '—'
)

const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
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
  const [loadCollapsed, setLoadCollapsed] = useState(false)
  const [roomVisualSettings, setRoomVisualSettings] = useState<Record<string, RTLSVisualSettings>>({})
  const [floorplanSettings, setFloorplanSettings] = useState<FloorplanSettings>(DEFAULT_FLOORPLAN)
  const [analyticsData, setAnalyticsData] = useState<RTLSAnalyticsResponse | null>(null)
  const [analyticsBusy, setAnalyticsBusy] = useState(false)
  const [workspacePaths, setWorkspacePaths] = useState<{
    svg?: string; rooms?: string; tags?: string; projects?: string; rtls?: string
  }>({})
  const [profileRootPath, setProfileRootPath] = useState<string | undefined>(undefined)
  const [quickSetup, setQuickSetup] = useState<{ active: boolean; step: string }>({
    active: false,
    step: '',
  })
  const quickSetupCancelRef = useRef<boolean>(false)
  const quickSetupRunningRef = useRef<boolean>(false)

  useEffect(() => {
    let cancelled = false
    fetch(`${API}/api/workspace/paths/${encodeURIComponent(workspaceId)}?workspace_name=${encodeURIComponent(workspaceName)}`)
      .then(r => r.json())
      .then(data => {
        if (cancelled || !data.success) return
        setWorkspacePaths({
          svg: data.svg,
          rooms: data.rooms,
          tags: data.tags,
          projects: data.projects,
          rtls: data.rtls,
        })
      })
      .catch(() => { /* optional */ })
    void window.api?.getPaths?.()
      .then(paths => { if (!cancelled) setProfileRootPath(paths.profile) })
      .catch(() => { /* optional */ })
    return () => { cancelled = true }
  }, [workspaceId, workspaceName])

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

  const currentRoomVisual: RTLSVisualSettings = useMemo(() => {
    if (canvasMode !== 'room' || !visibleRoom) return DEFAULT_VISUAL
    return roomVisualSettings[visibleRoom.room_name] ?? DEFAULT_VISUAL
  }, [canvasMode, roomVisualSettings, visibleRoom])

  const updateCurrentRoomVisual = useCallback(
    (updater: (prev: RTLSVisualSettings) => RTLSVisualSettings) => {
      const roomName = visibleRoom?.room_name
      if (!roomName) return
      setRoomVisualSettings(current => ({
        ...current,
        [roomName]: updater(current[roomName] ?? DEFAULT_VISUAL),
      }))
    },
    [visibleRoom],
  )

  const updateFloorplan = useCallback(
    (updater: (prev: FloorplanSettings) => FloorplanSettings) => {
      setFloorplanSettings(prev => updater(prev))
    },
    [],
  )

  const bleConnected = snap.transport_status === 'connected'

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
  const isFloorPlanView = canvasMode === 'floor-plan'

  const panelSubtitle = [
    projectName || workspaceName || 'RTLS Dashboard',
    activeViewLabel,
    selectedRoomName ? `Selected room: ${selectedRoomName}` : null,
    snap.room_name ? `Active solve room: ${snap.room_name}` : null,
  ].filter(Boolean).join(' · ')

  useEffect(() => {
    if (snap.mode === 'ble' || snap.mode === 'serial') setTransportMode(snap.mode)
  }, [snap.mode])

  useEffect(() => {
    if (activeTab === 'floor-plan' && activePanelTab !== 'setup') {
      setActivePanelTab('setup')
    }
  }, [activeTab, activePanelTab])

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
    setAnalyticsData(null)
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

  useEffect(() => {
    const handler = async (e: Event) => {
      const detail = (e as CustomEvent).detail as { workspaceId: string; module?: string }
      if (detail.workspaceId !== workspaceId || (detail.module && detail.module !== 'rtls')) return

      const projectPath = loadSourceRef.current.projectPath
      if (!projectPath || rooms.length === 0) {
        await confirmAsync({
          title: 'Nothing to Save',
          message: 'Open or create a .rtls project in the Anchor Manager first, then return here to run it.',
          confirmLabel: 'OK',
        })
        return
      }

      try {
        const res = await fetch(`${API}/api/rooms/project/save`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_path: projectPath,
            project_name: projectName || workspaceName || 'RTLS Project',
            rooms: rooms.map(room => ({ ...room })),
            workspace_id: workspaceId,
            workspace_name: workspaceName,
          }),
        })
        const data = await res.json()
        if (data.success) showMsg('RTLS project saved.', 'ok')
        else showMsg(data.error ?? 'Could not save project.', 'error')
      } catch {
        showMsg('Could not reach backend.', 'error')
      }
    }
    window.addEventListener('workspace-save-command', handler)
    window.addEventListener('workspace-save-as-command', handler)
    return () => {
      window.removeEventListener('workspace-save-command', handler)
      window.removeEventListener('workspace-save-as-command', handler)
    }
  }, [projectName, rooms, showMsg, workspaceId, workspaceName])

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
    const r = await window.api?.openFile?.(
      [{ name: 'RTLS Project', extensions: ['rtls'] }],
      workspacePaths.projects,
    )
    if (r && !r.canceled && r.filePaths[0]) {
      resetViewState()
      await loadWorkspace({ projectPath: r.filePaths[0] })
    }
  }, [loadWorkspace, resetViewState, workspacePaths.projects])

  const loadFolder = useCallback(async () => {
    const r = await window.api?.openFolder?.(profileRootPath)
    if (r && !r.canceled && r.folderPath) {
      resetViewState()
      await loadWorkspace({ folderPath: r.folderPath })
    }
  }, [loadWorkspace, profileRootPath, resetViewState])

  const loadRoomsFolder = useCallback(async () => {
    const r = await window.api?.openFolder?.(workspacePaths.rooms)
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
  }, [currentCompositeSource, loadWorkspace, resetViewState, workspacePaths.rooms])

  const loadTagsFolder = useCallback(async () => {
    const r = await window.api?.openFolder?.(workspacePaths.tags)
    if (r && !r.canceled && r.folderPath) {
      await loadWorkspace({
        ...currentCompositeSource(),
        tagsFolder: r.folderPath,
      }, { roomName: selectedRoomName || snap.room_name || undefined })
    }
  }, [currentCompositeSource, loadWorkspace, selectedRoomName, snap.room_name, workspacePaths.tags])

  const loadSvgFolder = useCallback(async () => {
    const r = await window.api?.openFolder?.(workspacePaths.svg)
    if (r && !r.canceled && r.folderPath) {
      await loadWorkspace({
        ...currentCompositeSource(),
        svgFolder: r.folderPath,
      }, { roomName: selectedRoomName || snap.room_name || undefined })
    }
  }, [currentCompositeSource, loadWorkspace, selectedRoomName, snap.room_name, workspacePaths.svg])

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

  const setNoiseCancel = useCallback(async (enabled: boolean) => {
    setSnap(prev => ({ ...prev, noise_cancel: { enabled } }))
    try {
      await fetch(`${API}/api/rtls/noise_cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
    } catch {
      /* ignore */
    }
  }, [])

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

  const runAnalytics = useCallback(async (csvPath?: string) => {
    const selectedPath = (csvPath ?? snap.csv.path ?? analyticsData?.csv_path ?? '').trim()
    if (!selectedPath) {
      showMsg('Start Log CSV or choose a saved RTLS CSV first.', 'warn')
      return
    }
    setAnalyticsBusy(true)
    try {
      const res = await fetch(`${API}/api/rtls/analytics/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_path: selectedPath }),
      })
      const data = await res.json() as RTLSAnalyticsResponse
      if (data.success) {
        setAnalyticsData(data)
        showMsg(`Analytics ready for ${data.summary.unique_pairs} tag pairs.`, 'ok')
      } else {
        showMsg(data.error ?? 'Analytics could not be generated.', 'warn')
      }
    } catch {
      showMsg('Could not run RTLS analytics.', 'error')
    } finally {
      setAnalyticsBusy(false)
    }
  }, [analyticsData?.csv_path, showMsg, snap.csv.path])

  const chooseAnalyticsCsv = useCallback(async () => {
    const picker = await window.api?.openFile?.(
      [{ name: 'RTLS CSV', extensions: ['csv'] }],
      workspacePaths.rtls || undefined,
    )
    if (!picker || picker.canceled || !picker.filePaths[0]) return
    await runAnalytics(picker.filePaths[0])
  }, [runAnalytics, workspacePaths.rtls])

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

  const runQuickSetup = useCallback(async () => {
    if (quickSetupRunningRef.current) return
    if (!roomLoaded || rooms.length === 0) {
      showMsg('Load a project first, then run Quick Setup.', 'warn')
      return
    }

    quickSetupRunningRef.current = true
    quickSetupCancelRef.current = false
    setQuickSetup({ active: true, step: 'Preparing Quick Setup…' })

    const sleep = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms))
    const isCancelled = () => quickSetupCancelRef.current

    try {
      setQuickSetup({ active: true, step: `Creating tabs for ${rooms.length} room${rooms.length === 1 ? '' : 's'}…` })
      setRoomTabs(rooms.map(room => ({ id: `room-view-${room.room_name}`, roomName: room.room_name })))
      await sleep(150)
      if (isCancelled()) throw new Error('cancelled')

      setQuickSetup({ active: true, step: 'Switching transport to Bluetooth…' })
      setTransportMode('ble')
      await sleep(100)
      if (isCancelled()) throw new Error('cancelled')

      setQuickSetup({ active: true, step: 'Starting BLE listeners…' })
      const connectRes = await fetch(`${API}/api/rtls/transport/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'ble', port: '' }),
      })
      const connectData = await connectRes.json().catch(() => ({}))
      if (!connectData.success) {
        throw new Error(connectData.error || 'Could not start BLE listeners.')
      }
      if (isCancelled()) throw new Error('cancelled')

      setQuickSetup({ active: true, step: 'Waiting for a tag to connect…' })
      while (true) {
        if (isCancelled()) throw new Error('cancelled')
        try {
          const snapRes = await fetch(`${API}/api/rtls/snapshot`)
          if (snapRes.ok) {
            const snapData = await snapRes.json()
            const tags: { status?: string }[] = Array.isArray(snapData.tags) ? snapData.tags : []
            const anyConnected = tags.some(t => {
              const s = (t.status || '').toLowerCase()
              return s.includes('connected') && !s.includes('disconnect')
            })
            if (anyConnected) break
          }
        } catch {
          /* backend blip — keep polling */
        }
        await sleep(500)
      }
      if (isCancelled()) throw new Error('cancelled')

      setQuickSetup({ active: true, step: 'Applying floor plan settings…' })
      setActiveTab('floor-plan')
      setActivePanelTab('setup')
      setFloorplanSettings(current => ({
        ...current,
        heatMap: true,
        heatGradientRate: 0.05,
        heatRange: 6.0,
        heatPeak: 100,
      }))
      await sleep(80)
      if (isCancelled()) throw new Error('cancelled')

      setQuickSetup({ active: true, step: 'Enabling EMA smoothing filter (α = 0.15)…' })
      const filterPayload = {
        mode: 'EMA',
        ema_alpha: 0.15,
        roll_n: snap.filter.roll_n,
        kal_q: snap.filter.kal_q,
        kal_r: snap.filter.kal_r,
      }
      await fetch(`${API}/api/rtls/filter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(filterPayload),
      })
      if (isCancelled()) throw new Error('cancelled')

      setQuickSetup({ active: true, step: 'Starting CSV logging for all tags…' })
      const csvSnapRes = await fetch(`${API}/api/rtls/snapshot`)
      const csvSnapData = await csvSnapRes.json().catch(() => ({}))
      if (!csvSnapData?.csv?.enabled) {
        await fetch(`${API}/api/rtls/csv/start`, { method: 'POST' })
      }

      setActiveTab('floor-plan')
      setQuickSetup({ active: false, step: '' })
      showMsg('Quick Setup complete.', 'ok')
    } catch (err) {
      setQuickSetup({ active: false, step: '' })
      if (quickSetupCancelRef.current) {
        showMsg('Quick Setup cancelled.', 'warn')
      } else {
        showMsg(`Quick Setup failed: ${err instanceof Error ? err.message : String(err)}`, 'error')
      }
    } finally {
      quickSetupRunningRef.current = false
      quickSetupCancelRef.current = false
    }
  }, [rooms, roomLoaded, showMsg, snap.filter.kal_q, snap.filter.kal_r, snap.filter.roll_n])

  const cancelQuickSetup = useCallback(() => {
    quickSetupCancelRef.current = true
  }, [])

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent).detail as { workspaceId: string }
      if (detail?.workspaceId !== workspaceId) return
      void runQuickSetup()
    }
    window.addEventListener('rtls-quick-setup', handler)
    return () => window.removeEventListener('rtls-quick-setup', handler)
  }, [runQuickSetup, workspaceId])

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

  const renderInterTagDistancesSection = () => {
    const positioned = snap.tags.filter(t => t.position)
    if (positioned.length < 2) return null
    const pairs: { key: string; t1: RTLSTag; t2: RTLSTag; dist: number }[] = []
    for (let i = 0; i < positioned.length; i++) {
      for (let j = i + 1; j < positioned.length; j++) {
        const t1 = positioned[i]
        const t2 = positioned[j]
        const dist = Math.hypot(t2.position!.x - t1.position!.x, t2.position!.y - t1.position!.y)
        pairs.push({ key: `${t1.tag_id}-${t2.tag_id}`, t1, t2, dist })
      }
    }
    return (
      <div className="rtls-section">
        <div className="rtls-section-title">Inter-Tag Distances</div>
        <div className="rtls-ble-rows">
          {pairs.map(({ key, t1, t2, dist }) => (
            <div key={key} className="rtls-ble-row">
              <span>{t1.tag_id} → {t2.tag_id}</span>
              <span style={{ color: 'rgba(255, 185, 0, 0.95)', fontWeight: 600 }}>{dist.toFixed(2)} ft</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const renderNoiseCancelSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Noise Cancelation</div>
      <div className="rtls-toggle-row">
        <span className="rtls-toggle-label">Enable Noise Cancelation</span>
        <label className="rtls-toggle">
          <input
            type="checkbox"
            checked={snap.noise_cancel.enabled}
            onChange={e => void setNoiseCancel(e.target.checked)}
          />
          <span className="rtls-toggle-slider" />
        </label>
      </div>
      <div className="rtls-runtime-note">
        Suppresses ≥2 ft anchor-distance jumps within 0.25 s of the last reading. Disqualified samples print last ± 0.1 ft; if the next sample confirms the jump it is accepted and a 3 s cooldown begins.
      </div>
    </div>
  )

  const renderUniversalNoiseCancelSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Universal Noise Cancelation</div>
      <div className="rtls-runtime-note">
        Overrides noise cancelation for all rooms.
      </div>
      <div className="rtls-toggle-row">
        <span className="rtls-toggle-label">Enable Noise Cancelation</span>
        <label className="rtls-toggle">
          <input
            type="checkbox"
            checked={snap.noise_cancel.enabled}
            onChange={e => void setNoiseCancel(e.target.checked)}
          />
          <span className="rtls-toggle-slider" />
        </label>
      </div>
      <div className="rtls-runtime-note">
        Suppresses ≥2 ft anchor-distance jumps within 0.25 s of the last reading. Disqualified samples print last ± 0.1 ft; if the next sample confirms the jump it is accepted and a 3 s cooldown begins.
      </div>
    </div>
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

  const renderRoomSetupTab = () => (
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
      {isRoomView && renderInterTagDistancesSection()}
      {renderTagElevationSection()}
      {renderNoiseCancelSection()}
      {renderSmoothingFilterSection()}
      {renderCsvSection()}
    </>
  )

  const renderFloorplanHeatMapSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Heat Map</div>
      <div className="rtls-toggle-row">
        <span className="rtls-toggle-label">Enable Heat Map</span>
        <label className="rtls-toggle">
          <input
            type="checkbox"
            checked={floorplanSettings.heatMap}
            onChange={e => updateFloorplan(current => ({ ...current, heatMap: e.target.checked }))}
          />
          <span className="rtls-toggle-slider" />
        </label>
      </div>
      <SliderInput
        label="Exposure Rate"
        value={floorplanSettings.heatGradientRate}
        min={0.05}
        max={5.0}
        step={0.05}
        unit="s/step"
        decimals={2}
        onChange={value => updateFloorplan(current => ({ ...current, heatGradientRate: value }))}
      />
      <SliderInput
        label="Range"
        value={floorplanSettings.heatRange}
        min={0.5}
        max={30}
        step={0.5}
        unit="ft"
        decimals={1}
        onChange={value => updateFloorplan(current => ({ ...current, heatRange: value }))}
      />
      <div className="rtls-slider-row">
        <div className="rtls-slider-header">
          <span className="rtls-slider-label">Peak Color</span>
          <span className="rtls-slider-value">{floorplanSettings.heatPeak}</span>
        </div>
        <input
          type="range"
          className="rtls-range"
          min={1}
          max={100}
          step={1}
          value={floorplanSettings.heatPeak}
          onChange={e => updateFloorplan(current => ({ ...current, heatPeak: parseInt(e.target.value, 10) }))}
        />
      </div>
      <div className="rtls-runtime-note">
        Floor-plan heat map uses live tag positions across all rooms. Tag markers are hidden — only the heat layer is shown.
      </div>
    </div>
  )

  const renderFloorplanAnchorSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Anchor Appearance</div>
      <div className="rtls-toggle-row">
        <span className="rtls-toggle-label">Show Anchors</span>
        <label className="rtls-toggle">
          <input
            type="checkbox"
            checked={floorplanSettings.showAnchors}
            onChange={e => updateFloorplan(current => ({ ...current, showAnchors: e.target.checked }))}
          />
          <span className="rtls-toggle-slider" />
        </label>
      </div>
      <div className="rtls-toggle-row">
        <span className="rtls-toggle-label">Show Anchor Coordinates</span>
        <label className="rtls-toggle">
          <input
            type="checkbox"
            checked={floorplanSettings.showAnchorLabels}
            disabled={!floorplanSettings.showAnchors}
            onChange={e => updateFloorplan(current => ({ ...current, showAnchorLabels: e.target.checked }))}
          />
          <span className="rtls-toggle-slider" />
        </label>
      </div>
      <div className="rtls-runtime-note">
        Shows the anchors of every room on the floor plan. Does not affect individual room views.
      </div>
    </div>
  )

  const renderUniversalSmoothingSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Universal Smoothing Filter</div>
      <div className="rtls-runtime-note">
        Overrides the smoothing filter for all rooms.
      </div>
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

  const renderLogAllTagsSection = () => (
    <div className="rtls-section">
      <div className="rtls-section-title">Log All Tags</div>
      <button
        className={`rtls-btn rtls-btn--full ${snap.csv.enabled ? 'rtls-btn--danger' : 'rtls-btn--primary'}`}
        onClick={() => void toggleCsv()}
      >
        {snap.csv.enabled ? 'Stop Logging' : 'Start Logging'}
      </button>
      {snap.csv.enabled && snap.csv.path && (
        <div className="rtls-csv-path">{snap.csv.path}</div>
      )}
      <div className="rtls-runtime-note">
        Overrides per-room logging. Logs every active tag across all rooms. Stopping here stops logging everywhere.
      </div>
    </div>
  )

  const renderFloorplanSetupTab = () => (
    <div className={`rtls-locked-wrapper${bleConnected ? '' : ' rtls-locked-wrapper--locked'}`}>
      {renderRoomManagerSection()}
      {renderFloorplanHeatMapSection()}
      {renderFloorplanAnchorSection()}
      {renderUniversalNoiseCancelSection()}
      {renderUniversalSmoothingSection()}
      {renderLogAllTagsSection()}
    </div>
  )

  const renderSetupTab = () => (
    isFloorPlanView ? renderFloorplanSetupTab() : renderRoomSetupTab()
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
              checked={currentRoomVisual.heatMap}
              onChange={e => updateCurrentRoomVisual(current => ({ ...current, heatMap: e.target.checked }))}
            />
            <span className="rtls-toggle-slider" />
          </label>
        </div>
        <SliderInput
          label="Exposure Rate"
          value={currentRoomVisual.heatGradientRate}
          min={0.05}
          max={5.0}
          step={0.05}
          unit="s/step"
          decimals={2}
          onChange={value => updateCurrentRoomVisual(current => ({ ...current, heatGradientRate: value }))}
        />
        <SliderInput
          label="Range"
          value={currentRoomVisual.heatRange}
          min={0.5}
          max={30}
          step={0.5}
          unit="ft"
          decimals={1}
          onChange={value => updateCurrentRoomVisual(current => ({ ...current, heatRange: value }))}
        />
        <div className="rtls-slider-row">
          <div className="rtls-slider-header">
            <span className="rtls-slider-label">Peak Color</span>
            <span className="rtls-slider-value">{currentRoomVisual.heatPeak}</span>
          </div>
          <input
            type="range"
            className="rtls-range"
            min={1}
            max={100}
            step={1}
            value={currentRoomVisual.heatPeak}
            onChange={e => updateCurrentRoomVisual(current => ({ ...current, heatPeak: parseInt(e.target.value, 10) }))}
          />
        </div>
        <div className="rtls-runtime-note">
          Heat map settings are saved per room — changes here do not affect other rooms or the floor plan.
        </div>
      </div>

      <div className="rtls-section">
        <div className="rtls-section-title">Inter-Tag Lines</div>
        <div className="rtls-toggle-row">
          <span className="rtls-toggle-label">Show Distance Lines</span>
          <label className="rtls-toggle">
            <input
              type="checkbox"
              checked={currentRoomVisual.showInterTagLines}
              onChange={e => updateCurrentRoomVisual(current => ({ ...current, showInterTagLines: e.target.checked }))}
            />
            <span className="rtls-toggle-slider" />
          </label>
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
              className={`rtls-btn rtls-transport-tab${currentRoomVisual.tagAppearance === value ? ' rtls-transport-tab--active' : ''}`}
              onClick={() => updateCurrentRoomVisual(current => ({ ...current, tagAppearance: value }))}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="rtls-section">
        <div className="rtls-section-title">Anchor Appearance</div>
        <div className="rtls-toggle-row">
          <span className="rtls-toggle-label">Show Anchors</span>
          <label className="rtls-toggle">
            <input
              type="checkbox"
              checked={currentRoomVisual.showAnchors}
              onChange={e => updateCurrentRoomVisual(current => ({ ...current, showAnchors: e.target.checked }))}
            />
            <span className="rtls-toggle-slider" />
          </label>
        </div>
        <div className="rtls-toggle-row">
          <span className="rtls-toggle-label">Show Anchor Coordinates</span>
          <label className="rtls-toggle">
            <input
              type="checkbox"
              checked={currentRoomVisual.showAnchorLabels}
              disabled={!currentRoomVisual.showAnchors}
              onChange={e => updateCurrentRoomVisual(current => ({ ...current, showAnchorLabels: e.target.checked }))}
            />
            <span className="rtls-toggle-slider" />
          </label>
        </div>
      </div>
    </>
  )

  const analyticsChart = useMemo(() => {
    const points = analyticsData?.trend ?? []
    if (points.length === 0) return null
    const width = 248
    const height = 90
    const padX = 8
    const padY = 10
    const usableWidth = width - (padX * 2)
    const usableHeight = height - (padY * 2)
    const peakMax = Math.max(1, ...points.map(point => point.peak_probability_pct))
    const pointFor = (value: number, index: number, total: number) => {
      const x = total <= 1 ? width / 2 : padX + ((usableWidth * index) / (total - 1))
      const y = padY + usableHeight - ((Math.max(0, value) / peakMax) * usableHeight)
      return `${x},${y}`
    }
    return {
      width,
      height,
      peakMax,
      peakLine: points.map((point, index) => pointFor(point.peak_probability_pct, index, points.length)).join(' '),
      meanLine: points.map((point, index) => pointFor(point.mean_probability_pct, index, points.length)).join(' '),
      firstLabel: formatDateTime(points[0]?.chunk_start),
      lastLabel: formatDateTime(points[points.length - 1]?.chunk_start),
    }
  }, [analyticsData])

  const renderAnalyticsTab = () => (
    <>
      <div className="rtls-section">
        <div className="rtls-section-title">Transmission Model</div>
        <div className="rtls-analytics-toolbar">
          <button
            className="rtls-btn rtls-btn--primary"
            disabled={analyticsBusy || (!snap.csv.path && !analyticsData?.csv_path)}
            onClick={() => void runAnalytics()}
          >
            {analyticsBusy ? 'Analyzing…' : (snap.csv.enabled ? 'Analyze Live Log' : 'Analyze Last Log')}
          </button>
          <button className="rtls-btn" disabled={analyticsBusy} onClick={() => void chooseAnalyticsCsv()}>
            Choose CSV…
          </button>
        </div>
        <div className="rtls-runtime-note">
          Runs the bundled model against real RTLS CSV distance logs and ranks the highest transmission-pressure windows by tag pair.
        </div>
        {snap.csv.path && (
          <div className="rtls-csv-path">Current log: {snap.csv.path}</div>
        )}
        {analyticsData?.csv_path && (
          <div className="rtls-analytics-meta">
            Loaded file: {analyticsData.csv_path}
            <br />
            Model: {analyticsData.model_name} · {analyticsData.chunk_minutes}-minute windows · Last run {formatDateTime(analyticsData.generated_at)}
          </div>
        )}
      </div>

      {!analyticsData ? (
        <div className="rtls-section">
          <div className="rtls-section-title">Ready To Analyze</div>
          <div className="rtls-placeholder-list">
            <div className="rtls-placeholder-item">Start `Log CSV` in Setup, collect real tag traffic, then run `Analyze Live Log`.</div>
            <div className="rtls-placeholder-item">You can also choose any saved RTLS CSV to rank the highest-risk windows, hottest tags, and strongest pair interactions.</div>
          </div>
        </div>
      ) : (
        <>
          <div className="rtls-section">
            <div className="rtls-section-title">Session Snapshot</div>
            <div className="rtls-panel-info-grid">
              <div className="rtls-panel-info-card">
                <span className="rtls-panel-info-card__label">Peak Window</span>
                <span className="rtls-panel-info-card__value">{formatPercent(analyticsData.summary.peak_probability_pct)}</span>
              </div>
              <div className="rtls-panel-info-card">
                <span className="rtls-panel-info-card__label">Average Window</span>
                <span className="rtls-panel-info-card__value">{formatPercent(analyticsData.summary.avg_probability_pct)}</span>
              </div>
              <div className="rtls-panel-info-card">
                <span className="rtls-panel-info-card__label">Pairs</span>
                <span className="rtls-panel-info-card__value">{analyticsData.summary.unique_pairs}</span>
              </div>
              <div className="rtls-panel-info-card">
                <span className="rtls-panel-info-card__label">Highest Tag</span>
                <span className="rtls-panel-info-card__value">{analyticsData.summary.highest_tag ?? '—'}</span>
              </div>
            </div>
            <div className="rtls-session-grid">
              <div className="rtls-session-cell">
                <span className="rtls-session-label">Tags Logged</span>
                <span className="rtls-session-value">{analyticsData.summary.unique_tags}</span>
              </div>
              <div className="rtls-session-cell">
                <span className="rtls-session-label">Windows</span>
                <span className="rtls-session-value">{analyticsData.summary.time_windows}</span>
              </div>
              <div className="rtls-session-cell">
                <span className="rtls-session-label">Rows Analyzed</span>
                <span className="rtls-session-value">{analyticsData.summary.rows_analyzed}</span>
              </div>
              <div className="rtls-session-cell">
                <span className="rtls-session-label">Latest Window</span>
                <span className="rtls-session-value">{formatDateTime(analyticsData.summary.latest_window)}</span>
              </div>
            </div>
          </div>

          {analyticsData.hottest_window && (
            <div className="rtls-section">
              <div className="rtls-section-title">Hottest Window</div>
              <div className="rtls-analytics-hero">
                <div className="rtls-analytics-hero__header">
                  <div>
                    <div className="rtls-analytics-hero__pair">{analyticsData.hottest_window.pair}</div>
                    <div className="rtls-analytics-hero__time">{formatDateTime(analyticsData.hottest_window.chunk_start)}</div>
                  </div>
                  <div className={`rtls-risk-pill rtls-risk-pill--${analyticsData.hottest_window.risk_band.toLowerCase()}`}>
                    {analyticsData.hottest_window.risk_band}
                  </div>
                </div>
                <div className="rtls-analytics-hero__score">
                  {formatPercent(analyticsData.hottest_window.probability_pct)}
                </div>
                <div className="rtls-analytics-hero__meta">
                  <span>Close: {formatMinutes(analyticsData.hottest_window.close_contact_minutes)}</span>
                  <span>Cumulative: {formatHours(analyticsData.hottest_window.cumulative_contact_hours)}</span>
                  <span>Min distance: {analyticsData.hottest_window.min_distance_ft.toFixed(1)} ft</span>
                </div>
              </div>
            </div>
          )}

          {analyticsChart && (
            <div className="rtls-section">
              <div className="rtls-section-title">Room Risk Curve</div>
              <div className="rtls-analytics-chart">
                <svg viewBox={`0 0 ${analyticsChart.width} ${analyticsChart.height}`} className="rtls-analytics-chart__svg">
                  <polyline className="rtls-analytics-chart__line rtls-analytics-chart__line--mean" fill="none" points={analyticsChart.meanLine} />
                  <polyline className="rtls-analytics-chart__line rtls-analytics-chart__line--peak" fill="none" points={analyticsChart.peakLine} />
                </svg>
                <div className="rtls-analytics-chart__labels">
                  <span>{analyticsChart.firstLabel}</span>
                  <span>Peak {formatPercent(analyticsChart.peakMax)}</span>
                  <span>{analyticsChart.lastLabel}</span>
                </div>
              </div>
            </div>
          )}

          <div className="rtls-section">
            <div className="rtls-section-title">Top Transmission Windows</div>
            <div className="rtls-analytics-list">
              {analyticsData.top_windows.slice(0, 6).map(windowRow => (
                <div key={`${windowRow.pair}-${windowRow.chunk_start}-${windowRow.rank}`} className="rtls-analytics-row">
                  <div className="rtls-analytics-row__title">
                    <span>{windowRow.rank}. {windowRow.pair}</span>
                    <span>{formatPercent(windowRow.probability_pct)}</span>
                  </div>
                  <div className="rtls-analytics-row__meta">
                    <span>{formatDateTime(windowRow.chunk_start)}</span>
                    <span>{windowRow.risk_band}</span>
                    <span>{formatMinutes(windowRow.close_contact_minutes)} close</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rtls-section">
            <div className="rtls-section-title">Tag Pressure Leaderboard</div>
            <div className="rtls-analytics-list">
              {analyticsData.tag_leaderboard.slice(0, 5).map(tag => (
                <div key={`${tag.tag_id}-${tag.peak_window}`} className="rtls-analytics-row">
                  <div className="rtls-analytics-row__title">
                    <span>{tag.tag_id}</span>
                    <span>{formatPercent(tag.max_probability_pct)}</span>
                  </div>
                  <div className="rtls-analytics-row__meta">
                    <span>{tag.peak_pair}</span>
                    <span>{tag.peak_risk_band}</span>
                    <span>{tag.linked_pairs} pairs</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rtls-section">
            <div className="rtls-section-title">Pair Leaderboard</div>
            <div className="rtls-analytics-list">
              {analyticsData.pair_leaderboard.slice(0, 5).map(pair => (
                <div key={`${pair.pair}-${pair.peak_window}`} className="rtls-analytics-row">
                  <div className="rtls-analytics-row__title">
                    <span>{pair.pair}</span>
                    <span>{formatPercent(pair.max_probability_pct)}</span>
                  </div>
                  <div className="rtls-analytics-row__meta">
                    <span>{pair.windows_above_50} hot windows</span>
                    <span>{formatHours(pair.total_close_contact_hours)} close</span>
                    <span>{pair.peak_risk_band}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )

  const roomBannerInfo = isRoomView && visibleRoom ? {
    name: visibleRoom.room_name,
    width: visibleRoom.room_bounds_ft.width,
    height: visibleRoom.room_bounds_ft.height,
    anchorCount: visibleRoom.anchors.length,
    refLabel: (() => {
      const refAnchor = visibleRoom.anchors.find(anchor => (
        anchor.id === (visibleRoom.reference_anchor_id ?? null)
        || (!!snap.reference_anchor_id && (anchor.hw_id === snap.reference_anchor_id || anchor.id === snap.reference_anchor_id))
      ))
      return refAnchor?.hw_id || refAnchor?.id || '—'
    })(),
  } : null

  return (
    <div className="rtls-root">
      <div className="rtls-stage">
        <div className="rtls-main-panel">
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
              floorplanSettings={floorplanSettings}
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
              visualSettings={currentRoomVisual}
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

        {roomLoaded && roomBannerInfo && (
          <div className="rtls-floating-banner">
            <div className="rtls-floating-banner__meta">
              {roomBannerInfo.width.toFixed(1)} × {roomBannerInfo.height.toFixed(1)} ft
              {' · '}
              {roomBannerInfo.anchorCount} anchor{roomBannerInfo.anchorCount !== 1 ? 's' : ''}
              {' · '}
              Ref: {roomBannerInfo.refLabel}
            </div>
          </div>
        )}

        {statusMsg && (
          <div className={`rtls-status rtls-status--${statusMsg.kind}`}>
            {statusMsg.text}
          </div>
        )}

        {roomLoaded && (
          <div className="rtls-floating-tabbar">
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

        <div className="rtls-right-panel">
          <div className="rtls-panel-header">
            <div>
              <div className="rtls-panel-title">RTLS Dashboard</div>
              <div className="rtls-panel-subtitle">{panelSubtitle}</div>
            </div>
          </div>

          <div className="rtls-panel-sticky">
            <div className={`rtls-section rtls-load-section${loadCollapsed ? ' rtls-load-section--collapsed' : ''}`}>
              <div className="rtls-load-header">
                <div className="rtls-section-title rtls-load-title">Load</div>
                <button
                  type="button"
                  className="rtls-load-toggle"
                  onClick={() => setLoadCollapsed(value => !value)}
                  aria-expanded={!loadCollapsed}
                  title={loadCollapsed ? 'Maximize Load' : 'Minimize Load'}
                >
                  {loadCollapsed ? '+' : '−'}
                </button>
              </div>
              <div className={`rtls-load-body${loadCollapsed ? ' rtls-load-body--collapsed' : ''}`}>
                <div className="rtls-load-body-inner">
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
              </div>
            </div>

            <div
              className={`rtls-dashboard-tabs rtls-dashboard-tabs--attached${
                isFloorPlanView ? ' rtls-dashboard-tabs--with-banner' : ''
              }`}
            >
              {(
                (isFloorPlanView
                  ? [['setup', 'Setup']]
                  : [
                      ['setup', 'Setup'],
                      ['visuals', 'Visuals'],
                      ['analytics', 'Analytics'],
                    ]) as [DashboardPanelTab, string][]
              ).map(([tabId, label]) => (
                <button
                  key={tabId}
                  className={`rtls-btn rtls-dashboard-tab${activePanelTab === tabId ? ' rtls-dashboard-tab--active' : ''}`}
                  onClick={() => setActivePanelTab(tabId)}
                >
                  {label}
                </button>
              ))}
              {isFloorPlanView && (
                <div
                  className={`rtls-connectivity-banner ${
                    bleConnected
                      ? 'rtls-connectivity-banner--connected'
                      : 'rtls-connectivity-banner--disconnected'
                  }`}
                >
                  {bleConnected ? 'Connected' : 'Double click on a room to begin BLE Connectivity'}
                </div>
              )}
            </div>
          </div>

          <div className="rtls-panel-body">
            {activePanelTab === 'setup' && renderSetupTab()}
            {activePanelTab === 'visuals' && renderVisualsTab()}
            {activePanelTab === 'analytics' && renderAnalyticsTab()}
          </div>
        </div>
      </div>

      {quickSetup.active && (
        <div className="rtls-quick-setup-overlay" role="dialog" aria-modal="true">
          <div className="rtls-quick-setup-modal">
            <div className="rtls-quick-setup-spinner" />
            <div className="rtls-quick-setup-title">Quick Setup</div>
            <div className="rtls-quick-setup-step">{quickSetup.step}</div>
            <button
              type="button"
              className="rtls-btn rtls-btn--danger rtls-quick-setup-cancel"
              onClick={cancelQuickSetup}
            >
              Force Quit
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default RTLSDashboard
