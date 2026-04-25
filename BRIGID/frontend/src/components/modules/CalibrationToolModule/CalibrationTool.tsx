import React, { useEffect, useMemo, useRef, useState } from 'react'
import CalibrationMapCanvas, { CalibrationMapCanvasHandle } from './CalibrationMapCanvas'
import CalibrationGraphPanel from './CalibrationGraphPanel'
import { confirmAsync } from '../../common/ConfirmDialog'
import {
  ANCHOR_IDS,
  AnchorId,
  CalibrationMapRuntime,
  CalibrationRuntimeSnapshot,
  CalibrationTagRuntime,
  CalibrationTransportMode,
} from './types'
import './CalibrationTool.css'

const API = 'http://localhost:8765'
const FIT_MODES = ['Linear', 'Polynomial', 'Logarithmic', 'Power Series', 'Exponential', 'Moving Average']

const RIGHT_INSET = 352
const GRAPH_INSET_VISIBLE = 290
const GRAPH_INSET_COLLAPSED = 50

const TAG_PALETTE = ['#3498db', '#e67e22', '#9b59b6', '#27ae60', '#e74c3c', '#f1c40f', '#1abc9c', '#d16cff']

const ANCHOR_COLORS: Record<string, string> = {
  A0: '#ff5b4d',
  A1: '#42d17e',
  A2: '#ae62ff',
  A3: '#ffb11f',
}

const statusColor = (status: string): string => {
  const s = status.toLowerCase()
  if (s.includes('connected') && !s.includes('disconnect')) return '#42d17e'
  if (s.includes('connecting')) return '#ffb11f'
  return '#ff5b4d'
}

// ── Point log parser ────────────────────────────────────────────────
interface ParsedPoint { anchor: string; index: number; raw: number; trueDist: number }
function parsePointLog(lines: string[]): ParsedPoint[] {
  return lines.flatMap(line => {
    const m = line.match(/^(A\d)\s+\[(\d+)\]\s+Raw:([\d.]+)\s+[→>]\s+True:([\d.]+)/)
    if (!m) return []
    return [{ anchor: m[1], index: parseInt(m[2], 10), raw: parseFloat(m[3]), trueDist: parseFloat(m[4]) }]
  })
}

interface CalibrationToolProps {
  workspaceId: string
  workspaceName: string
}

const emptySnapshot = (): CalibrationRuntimeSnapshot => ({
  success: true,
  mode: null,
  transport_status: 'idle',
  transport_detail: 'Disconnected.',
  selected_port: '',
  ble_available: false,
  serial_available: false,
  ports: [],
  auto_detect_port: '',
  capture: { active: false, phase: 'idle', tag_id: null, target: 0, counts: {} },
  map: {
    anchors: { A0: [0, 0], A1: [0, 10], A2: [10, 10], A3: [10, 0] },
    lines: [['A0', 'A1'], ['A1', 'A2'], ['A2', 'A3'], ['A3', 'A0']],
    height_offset: 0,
  },
  filter: { mode: 'EMA', ema_alpha: 0.2, roll_n: 8, kal_q: 0.1, kal_r: 2 },
  tags: [],
})

const toMapState = (map: CalibrationMapRuntime): CalibrationMapRuntime => ({
  anchors: {
    A0: map.anchors.A0 ?? [0, 0],
    A1: map.anchors.A1 ?? [0, 10],
    A2: map.anchors.A2 ?? [10, 10],
    A3: map.anchors.A3 ?? [10, 0],
  },
  lines: map.lines.map(line => [line[0], line[1]]),
  height_offset: map.height_offset,
})

// ── Controlled number input (avoids reset while typing) ─────────────
interface NumInputProps {
  value: number
  className?: string
  step?: string
  onChange: (value: number) => void
}
const NumInput: React.FC<NumInputProps> = ({ value, className, step, onChange }) => {
  const [draft, setDraft] = useState(String(value))
  const focusedRef = useRef(false)
  useEffect(() => {
    if (!focusedRef.current) setDraft(String(value))
  }, [value])
  return (
    <input
      className={className}
      type="text"
      inputMode="decimal"
      value={draft}
      step={step}
      onChange={e => setDraft(e.target.value)}
      onFocus={() => { focusedRef.current = true }}
      onBlur={() => {
        focusedRef.current = false
        const parsed = Number.parseFloat(draft)
        const val = Number.isFinite(parsed) ? parsed : value
        setDraft(String(val))
        onChange(val)
      }}
      onKeyDown={e => {
        if (e.key === 'Enter') {
          (e.target as HTMLInputElement).blur()
          e.preventDefault()
        }
      }}
    />
  )
}

// ── Inline canvas editor overlay ────────────────────────────────────
type InlineEdit =
  | { kind: 'anchor'; anchorId: AnchorId; screenX: number; screenY: number; value: string }
  | { kind: 'refdot'; screenX: number; screenY: number; value: string }

const CalibrationTool: React.FC<CalibrationToolProps> = ({ workspaceId, workspaceName }) => {
  const mapCanvasRef = useRef<CalibrationMapCanvasHandle>(null)
  const mapSyncBlockedRef = useRef(false)
  const statusTimerRef = useRef<number | null>(null)
  const graphCollapsedRef = useRef(false)

  const [runtime, setRuntime] = useState<CalibrationRuntimeSnapshot>(emptySnapshot)
  const [transportMode, setTransportMode] = useState<CalibrationTransportMode>('ble')
  const [serialPort, setSerialPort] = useState('')
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null)
  const [activeAnchorId, setActiveAnchorId] = useState<AnchorId>('A0')
  const [mapState, setMapState] = useState<CalibrationMapRuntime>(toMapState(emptySnapshot().map))
  const [placingReference, setPlacingReference] = useState(false)
  const [referenceDot, setReferenceDot] = useState<{ x: number; y: number } | null>(null)
  const [referenceDotSelected, setReferenceDotSelected] = useState(false)
  const [linePickerMode, setLinePickerMode] = useState(false)
  const [linePicker, setLinePicker] = useState<AnchorId[]>([])
  const [graphCollapsed, setGraphCollapsed] = useState(false)
  const [sampleCount, setSampleCount] = useState('20')
  const [referenceDistances, setReferenceDistances] = useState<Record<AnchorId, string>>({ A0: '', A1: '', A2: '', A3: '' })
  const [referenceHeight, setReferenceHeight] = useState('0')
  const [equationDrafts, setEquationDrafts] = useState<Record<AnchorId, string>>({ A0: '', A1: '', A2: '', A3: '' })
  const [status, setStatus] = useState<{ text: string; kind: 'ok' | 'error' } | null>(null)
  const [busy, setBusy] = useState<{ transport: boolean; save: boolean; capture: boolean }>({
    transport: false, save: false, capture: false,
  })
  const [inlineEdit, setInlineEdit] = useState<InlineEdit | null>(null)
  const [sendDialogOpen, setSendDialogOpen] = useState(false)
  const [selectedLineKey, setSelectedLineKey] = useState<string | null>(null)
  const persistTimerRef = useRef<number | null>(null)
  const mapStateRef = useRef(mapState)
  mapStateRef.current = mapState
  const anyAnchorFocusedRef = useRef(false)

  graphCollapsedRef.current = graphCollapsed

  // Track which fields are being actively edited so background polls don't overwrite drafts.
  const refDistFocusRef = useRef<Record<AnchorId, boolean>>({ A0: false, A1: false, A2: false, A3: false })
  const refHeightFocusRef = useRef(false)
  const equationFocusRef = useRef<Record<AnchorId, boolean>>({ A0: false, A1: false, A2: false, A3: false })

  // ── Tag color palette ─────────────────────────────────────────────
  const tagIds = runtime.tags.map(t => t.tag_id).join('|')
  const tagColors = useMemo(() => {
    const map: Record<string, string> = {}
    runtime.tags.forEach((tag, i) => { map[tag.tag_id] = TAG_PALETTE[i % TAG_PALETTE.length] })
    return map
  }, [tagIds]) // eslint-disable-line react-hooks/exhaustive-deps

  const selectedTag = useMemo(
    () => runtime.tags.find(tag => tag.tag_id === selectedTagId) ?? null,
    [runtime.tags, selectedTagId],
  )
  const mapSignature = JSON.stringify(runtime.map)
  const referenceSignature = JSON.stringify(selectedTag ? {
    distances: selectedTag.reference_floor, height: selectedTag.reference_height,
  } : null)
  const equationSignature = JSON.stringify(selectedTag?.equations ?? null)
  const activeFit = selectedTag?.fit_options[activeAnchorId] ?? null

  const showStatus = (text: string, kind: 'ok' | 'error') => {
    setStatus({ text, kind })
    if (statusTimerRef.current) window.clearTimeout(statusTimerRef.current)
    statusTimerRef.current = window.setTimeout(() => setStatus(null), 3600)
  }

  const applySnapshot = (snapshot: CalibrationRuntimeSnapshot) => {
    setRuntime(snapshot)
    if (snapshot.mode === 'ble' || snapshot.mode === 'serial') setTransportMode(snapshot.mode)
    if (snapshot.selected_port) setSerialPort(snapshot.selected_port)
    else if (!serialPort && snapshot.auto_detect_port) setSerialPort(snapshot.auto_detect_port)
    setSelectedTagId(current => {
      // Keep the current tag selected if it still exists — prevents panel glitch
      if (current && snapshot.tags.some(tag => tag.tag_id === current)) return current
      // If current tag is gone, pick the first one or keep the current (sticky)
      if (snapshot.tags.length > 0) return current ?? snapshot.tags[0].tag_id
      return current
    })
    if (!mapSyncBlockedRef.current) setMapState(toMapState(snapshot.map))
  }

  const loadRuntime = async () => {
    try {
      const response = await fetch(
        `${API}/api/calibration/runtime?workspace_id=${encodeURIComponent(workspaceId)}&workspace_name=${encodeURIComponent(workspaceName)}`,
      )
      const data = await response.json() as CalibrationRuntimeSnapshot
      if (data.success) applySnapshot(data)
    } catch { /* silent while backend boots */ }
  }

  useEffect(() => {
    void loadRuntime()
    const intervalId = window.setInterval(loadRuntime, 80)
    return () => {
      window.clearInterval(intervalId)
      if (statusTimerRef.current) window.clearTimeout(statusTimerRef.current)
    }
  }, [workspaceId, workspaceName]) // eslint-disable-line react-hooks/exhaustive-deps

  // View commands from top TabStrip
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { cmd: string; workspaceId: string }
      if (detail.workspaceId !== workspaceId) return
      if (detail.cmd === 'refresh') { void loadRuntime(); return }
      const canvas = mapCanvasRef.current
      if (!canvas) return
      if (detail.cmd === 'zoom_reset') {
        canvas.resetView({
          rightInset: RIGHT_INSET,
          bottomInset: graphCollapsedRef.current ? GRAPH_INSET_COLLAPSED : GRAPH_INSET_VISIBLE,
        })
      } else if (detail.cmd === 'zoom_in') {
        canvas.zoomIn()
      } else if (detail.cmd === 'zoom_out') {
        canvas.zoomOut()
      }
    }
    window.addEventListener('calibration-view-command', handler)
    return () => window.removeEventListener('calibration-view-command', handler)
  }, [workspaceId])

  useEffect(() => {
    // Skip poll-driven overwrites while the user is typing into any anchor
    // coordinate input, otherwise mid-typing poll snapshots clobber their draft.
    if (mapSyncBlockedRef.current || anyAnchorFocusedRef.current) return
    setMapState(toMapState(runtime.map))
  }, [mapSignature, runtime.map])

  // Sync reference-distance drafts ONLY on tag change (avoids wiping user input on every poll).
  useEffect(() => {
    if (!selectedTag) return
    setReferenceDistances({
      A0: selectedTag.reference_floor.A0 != null ? String(selectedTag.reference_floor.A0) : '',
      A1: selectedTag.reference_floor.A1 != null ? String(selectedTag.reference_floor.A1) : '',
      A2: selectedTag.reference_floor.A2 != null ? String(selectedTag.reference_floor.A2) : '',
      A3: selectedTag.reference_floor.A3 != null ? String(selectedTag.reference_floor.A3) : '',
    })
    setReferenceHeight(String(selectedTag.reference_height ?? 0))
  }, [selectedTagId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Apply backend-driven distance changes (e.g. Place-on-Map) only to inputs not currently focused.
  useEffect(() => {
    if (!selectedTag) return
    setReferenceDistances(prev => {
      const next = { ...prev }
      for (const aid of ANCHOR_IDS) {
        if (refDistFocusRef.current[aid]) continue
        const value = selectedTag.reference_floor[aid]
        next[aid] = value != null ? String(value) : ''
      }
      return next
    })
    if (!refHeightFocusRef.current) {
      setReferenceHeight(String(selectedTag.reference_height ?? 0))
    }
  }, [referenceSignature]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!selectedTag) return
    setEquationDrafts({
      A0: selectedTag.equations.A0 ?? '',
      A1: selectedTag.equations.A1 ?? '',
      A2: selectedTag.equations.A2 ?? '',
      A3: selectedTag.equations.A3 ?? '',
    })
  }, [selectedTagId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Backend-driven equation refreshes (e.g. after fit recalculation) skip focused inputs.
  useEffect(() => {
    if (!selectedTag) return
    setEquationDrafts(prev => {
      const next = { ...prev }
      for (const aid of ANCHOR_IDS) {
        if (equationFocusRef.current[aid]) continue
        next[aid] = selectedTag.equations[aid] ?? ''
      }
      return next
    })
  }, [equationSignature]) // eslint-disable-line react-hooks/exhaustive-deps

  const postJson = async <T,>(path: string, body?: unknown): Promise<T> => {
    // Append workspace_id query param so each tab targets its own backend runtime.
    const separator = path.includes('?') ? '&' : '?'
    const url = `${API}${path}${separator}workspace_id=${encodeURIComponent(workspaceId)}`
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body == null ? undefined : JSON.stringify(body),
    })
    return response.json() as Promise<T>
  }

  const persistMap = async (nextMap: CalibrationMapRuntime) => {
    mapSyncBlockedRef.current = true
    setMapState(nextMap)
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { detail?: string; error?: string }>('/api/calibration/map', {
        anchors: nextMap.anchors,
        lines: nextMap.lines,
        height_offset: nextMap.height_offset,
      })
      if (!data.success) { showStatus(data.error ?? 'Could not update map.', 'error'); return }
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
    finally { mapSyncBlockedRef.current = false }
  }

  const saveReferenceDrafts = async () => {
    if (!selectedTagId) return
    const distances = Object.fromEntries(ANCHOR_IDS.map(anchorId => {
      const raw = referenceDistances[anchorId].trim()
      if (raw === '') return [anchorId, null]
      const parsed = Number.parseFloat(raw)
      return [anchorId, Number.isFinite(parsed) ? parsed : null]
    }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/reference', {
        tag_id: selectedTagId, distances, height: Number.parseFloat(referenceHeight || '0') || 0,
      })
      if (!data.success) { showStatus(data.error ?? 'Could not update reference.', 'error'); return }
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
  }

  const saveEquation = async (anchorId: AnchorId) => {
    if (!selectedTagId) return
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/equation', {
        tag_id: selectedTagId, anchor_id: anchorId, equation: equationDrafts[anchorId],
      })
      if (!data.success) { showStatus(data.error ?? 'Equation is invalid.', 'error'); return }
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
  }

  const updateFitOption = async (anchorId: AnchorId, patch: Record<string, unknown>) => {
    if (!selectedTagId) return
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/fit', {
        tag_id: selectedTagId, anchor_id: anchorId, ...patch,
      })
      if (!data.success) { showStatus(data.error ?? 'Could not update fit.', 'error'); return }
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
  }

  const handleTransportConnect = async () => {
    setBusy(c => ({ ...c, transport: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>(
        `/api/calibration/transport/connect?workspace_name=${encodeURIComponent(workspaceName)}`,
        { mode: transportMode, port: transportMode === 'serial' ? serialPort : '' },
      )
      if (!data.success) { showStatus(data.error ?? 'Could not connect.', 'error'); return }
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
    finally { setBusy(c => ({ ...c, transport: false })) }
  }

  const handleTransportDisconnect = async () => {
    setBusy(c => ({ ...c, transport: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>(
        `/api/calibration/transport/disconnect?workspace_name=${encodeURIComponent(workspaceName)}`,
      )
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
    finally { setBusy(c => ({ ...c, transport: false })) }
  }

  const handleReferencePlacement = async (x: number, y: number) => {
    if (!selectedTagId) return
    setReferenceDot({ x, y })
    setPlacingReference(false)
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string; distances?: Record<string, number> }>('/api/calibration/reference/place', {
        tag_id: selectedTagId, x, y,
      })
      if (!data.success) { showStatus(data.error ?? 'Could not place reference.', 'error'); return }
      if (data.distances) {
        setReferenceDistances(prev => ({
          A0: data.distances?.A0 != null ? String(data.distances.A0) : prev.A0,
          A1: data.distances?.A1 != null ? String(data.distances.A1) : prev.A1,
          A2: data.distances?.A2 != null ? String(data.distances.A2) : prev.A2,
          A3: data.distances?.A3 != null ? String(data.distances.A3) : prev.A3,
        }))
      }
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
  }

  const handleCaptureStart = async () => {
    if (!selectedTagId) return
    setBusy(c => ({ ...c, capture: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/capture/start', {
        tag_id: selectedTagId, sample_count: Number.parseInt(sampleCount, 10) || 20,
      })
      if (!data.success) { showStatus(data.error ?? 'Could not start capture.', 'error'); return }
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
    finally { setBusy(c => ({ ...c, capture: false })) }
  }

  const saveTagById = async (tagId: string) => {
    const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string; calibration_date?: string }>(
      `/api/calibration/tag/save/${encodeURIComponent(tagId)}?workspace_id=${encodeURIComponent(workspaceId)}`,
    )
    return data
  }

  const handleSaveTag = async () => {
    if (!selectedTagId) return
    setBusy(c => ({ ...c, save: true }))
    try {
      const data = await saveTagById(selectedTagId)
      if (!data.success) { showStatus(data.error ?? 'Could not save tag.', 'error'); return }
      applySnapshot(data)
      const dateStr = data.calibration_date ?? new Date().toISOString().split('T')[0]
      showStatus(`Equations sent to profile "${selectedTagId}" — ${dateStr}`, 'ok')
    } catch { showStatus('Could not reach backend.', 'error') }
    finally { setBusy(c => ({ ...c, save: false })) }
  }

  const handleSendAllTags = async () => {
    if (runtime.tags.length === 0) return
    setBusy(c => ({ ...c, save: true }))
    let lastSnapshot: CalibrationRuntimeSnapshot | null = null
    let okCount = 0
    const failures: string[] = []
    try {
      for (const tag of runtime.tags) {
        try {
          const data = await saveTagById(tag.tag_id)
          if (data.success) { okCount += 1; lastSnapshot = data }
          else failures.push(`${tag.tag_id}: ${data.error ?? 'failed'}`)
        } catch {
          failures.push(`${tag.tag_id}: backend unreachable`)
        }
      }
      if (lastSnapshot) applySnapshot(lastSnapshot)
      if (failures.length === 0) showStatus(`Equations sent to ${okCount} tag profile${okCount === 1 ? '' : 's'}.`, 'ok')
      else showStatus(`Sent ${okCount}; failed: ${failures.join(', ')}`, 'error')
    } finally { setBusy(c => ({ ...c, save: false })) }
  }

  useEffect(() => {
    const handler = async (e: Event) => {
      const detail = (e as CustomEvent).detail as { workspaceId: string; module?: string }
      if (detail.workspaceId !== workspaceId || (detail.module && detail.module !== 'calibration')) return
      if (!selectedTagId) {
        const confirmed = await confirmAsync({
          title: 'No Tag Selected',
          message: 'Select a tag with calibration equations before saving. Open the Tag Profile for that tag first.',
          confirmLabel: 'OK',
        })
        void confirmed
        return
      }
      await handleSaveTag()
    }
    window.addEventListener('workspace-save-command', handler)
    window.addEventListener('workspace-save-as-command', handler)
    return () => {
      window.removeEventListener('workspace-save-command', handler)
      window.removeEventListener('workspace-save-as-command', handler)
    }
  }, [workspaceId, selectedTagId]) // eslint-disable-line react-hooks/exhaustive-deps

  const updateFilter = async (patch: Record<string, unknown>) => {
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/filter', {
        mode: runtime.filter.mode, ...patch,
      })
      if (!data.success) showStatus(data.error ?? 'Could not update filter.', 'error')
      else applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
  }

  // ── Line helpers (shared by canvas + right-panel) ───────────────
  const keyForLine = (a: string, b: string) => `${a}-${b}`
  const matchLineKey = (key: string, line: string[]) => (
    keyForLine(line[0], line[1]) === key || keyForLine(line[1], line[0]) === key
  )

  const deleteLineByKey = (key: string) => {
    const base = mapStateRef.current
    const nextLines = base.lines.filter(line => !matchLineKey(key, line))
    if (nextLines.length === base.lines.length) return
    setSelectedLineKey(null)
    void persistMap({ ...base, lines: nextLines })
  }

  const createLine = (a: AnchorId, b: AnchorId) => {
    if (a === b) return
    const base = mapStateRef.current
    const exists = base.lines.some(line => matchLineKey(keyForLine(a, b), line))
    if (exists) return
    void persistMap({ ...base, lines: [...base.lines, [a, b]] })
  }

  // Delete-key fallback when the right-panel line row is selected but the
  // canvas isn't focused. Ignored when the user is typing into any input.
  useEffect(() => {
    if (!selectedLineKey) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Delete' && event.key !== 'Backspace') return
      const target = event.target as HTMLElement | null
      if (target) {
        const tag = target.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || target.isContentEditable) return
      }
      deleteLineByKey(selectedLineKey)
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selectedLineKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Inline editor commit ─────────────────────────────────────────
  const commitInlineEdit = (edit: InlineEdit) => {
    const parts = edit.value.split(',').map(s => s.trim())
    const x = Number.parseFloat(parts[0])
    const y = Number.parseFloat(parts[1])
    if (!Number.isFinite(x) || !Number.isFinite(y)) { setInlineEdit(null); return }
    if (edit.kind === 'anchor') {
      const next = { ...mapState, anchors: { ...mapState.anchors, [edit.anchorId]: [x, y] as [number, number] } }
      void persistMap(next)
    } else {
      void handleReferencePlacement(x, y)
    }
    setInlineEdit(null)
  }

  // ── Anchor coordinate drafts (prevent reset while typing) ─────────
  const anchorDraftRef = useRef<Record<AnchorId, string>>({ A0: '', A1: '', A2: '', A3: '' })
  const anchorFocusedRef = useRef<Record<AnchorId, boolean>>({ A0: false, A1: false, A2: false, A3: false })
  const [, setForceRender] = useState(0)

  // Sync anchor drafts from mapState when not focused
  const getAnchorDraft = (anchorId: AnchorId) => {
    if (!anchorFocusedRef.current[anchorId]) {
      anchorDraftRef.current[anchorId] = `${mapState.anchors[anchorId][0]}, ${mapState.anchors[anchorId][1]}`
    }
    return anchorDraftRef.current[anchorId]
  }

  // Debounced persist for anchor coordinate editing
  const debouncedPersistMap = (nextMap: CalibrationMapRuntime) => {
    if (persistTimerRef.current) window.clearTimeout(persistTimerRef.current)
    persistTimerRef.current = window.setTimeout(() => { void persistMap(nextMap) }, 600)
  }

  // ── Parsed captured points ────────────────────────────────────────
  const parsedPoints = useMemo(
    () => selectedTag ? parsePointLog(selectedTag.captured_points_log) : [],
    [selectedTag?.captured_points_log],
  )

  return (
    <div className="ct-root">
      <div className="ct-stage">
        <div className="ct-module-title">Calibration Tool</div>
        <div className="ct-main-panel">
          <CalibrationMapCanvas
            ref={mapCanvasRef}
            map={mapState}
            tags={runtime.tags}
            selectedTagId={selectedTagId}
            referenceDot={referenceDot}
            referenceDotSelected={referenceDotSelected}
            placingReference={placingReference}
            onReferencePlaced={handleReferencePlacement}
            onCancelReferencePlacement={() => setPlacingReference(false)}
            onMapChange={setMapState}
            onMapCommit={persistMap}
            onAnchorDragStart={() => { mapSyncBlockedRef.current = true }}
            onReferenceDotSelect={setReferenceDotSelected}
            onReferenceDotDelete={() => { setReferenceDot(null); setReferenceDotSelected(false) }}
            onAnchorDoubleClick={(anchorId, screenX, screenY) => {
              const [x, y] = mapState.anchors[anchorId]
              setInlineEdit({ kind: 'anchor', anchorId, screenX, screenY, value: `${x}, ${y}` })
            }}
            onReferenceDotDoubleClick={(screenX, screenY) => {
              if (!referenceDot) return
              setInlineEdit({ kind: 'refdot', screenX, screenY, value: `${referenceDot.x}, ${referenceDot.y}` })
            }}
            selectedLineKey={selectedLineKey}
            onLineSelect={setSelectedLineKey}
            onLineDelete={deleteLineByKey}
            onLineCreate={createLine}
          />

          {/* Inline canvas coordinate editor */}
          {inlineEdit && (
            <div
              className="ct-inline-editor"
              style={{ left: inlineEdit.screenX - 64, top: inlineEdit.screenY - 36 }}
            >
              <div className="ct-inline-editor-label">
                {inlineEdit.kind === 'anchor' ? inlineEdit.anchorId : 'Ref'}
              </div>
              <input
                autoFocus
                className="ct-inline-editor-input"
                value={inlineEdit.value}
                onChange={e => setInlineEdit(prev => prev ? { ...prev, value: e.target.value } : null)}
                onKeyDown={e => {
                  if (e.key === 'Enter') { commitInlineEdit(inlineEdit); e.preventDefault() }
                  if (e.key === 'Escape') { setInlineEdit(null); e.preventDefault() }
                }}
                onBlur={() => commitInlineEdit(inlineEdit)}
              />
            </div>
          )}

          {status && <div className={`ct-status ct-status--${status.kind}`}>{status.text}</div>}
          <div className="ct-canvas-hint">Drag to pan · Scroll to zoom · Drag anchors · Double-click to edit</div>
        </div>

        {/* ── Right panel ────────────────────────────────────────────── */}
        <div className="ct-right-panel">
          <div className="ct-panel-header">
            <div className="ct-panel-header-left">
              <div className="ct-panel-title-row">
                <div className="ct-panel-title">Calibration Controls</div>
                {selectedTagId && tagColors[selectedTagId] && (
                  <span className="ct-tag-chip" style={{ background: tagColors[selectedTagId] }}>
                    {selectedTagId}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="ct-panel-scroll">

            {/* CONNECTIVITY */}
            <section className="ct-section">
              <div className="ct-section-title">Connectivity</div>
              {(() => {
                const isActive =
                  runtime.transport_status === 'connected' ||
                  runtime.transport_status === 'connecting'
                const activeMode = isActive ? runtime.mode : null
                const bleLocked = activeMode === 'serial'
                const serialLocked = activeMode === 'ble'
                return (
                  <div className="ct-transport-toggle">
                    <button
                      className={`ct-toggle${transportMode === 'ble' ? ' active' : ''}`}
                      onClick={() => setTransportMode('ble')}
                      disabled={bleLocked}
                      title={bleLocked ? 'Disconnect serial to use BLE.' : ''}
                    >
                      Bluetooth (BLE)
                    </button>
                    <button
                      className={`ct-toggle${transportMode === 'serial' ? ' active' : ''}`}
                      onClick={() => setTransportMode('serial')}
                      disabled={serialLocked}
                      title={serialLocked ? 'Disconnect BLE to use Serial.' : ''}
                    >
                      Serial Port
                    </button>
                  </div>
                )
              })()}
              {transportMode === 'serial' && (
                <select className="ct-input" value={serialPort} onChange={e => setSerialPort(e.target.value)}>
                  <option value="">Select a COM port</option>
                  {runtime.ports.map(port => <option key={port} value={port}>{port}</option>)}
                </select>
              )}
              <div className="ct-runtime-note">{runtime.transport_detail}</div>
              {runtime.tags.length > 0 ? (
                <div className="ct-rows">
                  {runtime.tags.map(tag => (
                    <div key={tag.tag_id} className="ct-ble-row">
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span className="ct-tag-dot" style={{ background: tagColors[tag.tag_id] ?? '#666' }} />
                        {tag.tag_id}
                      </span>
                      <span style={{ color: statusColor(tag.status), fontWeight: 600 }}>{tag.status}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="ct-runtime-note">No profiled tags available yet.</div>
              )}
              <div className="ct-actions">
                <button className="ct-btn ct-btn--primary" onClick={handleTransportConnect} disabled={busy.transport}>Connect</button>
                <button className="ct-btn ct-btn--ghost" onClick={handleTransportDisconnect} disabled={busy.transport}>Disconnect</button>
              </div>
            </section>

            {/* MAP GEOMETRY */}
            <section className="ct-section">
              <div className="ct-section-title">Map Geometry</div>
              {ANCHOR_IDS.map(anchorId => (
                <div key={anchorId} className="ct-field-inline">
                  <label className="ct-field-inline-label" style={{ color: ANCHOR_COLORS[anchorId], fontWeight: 600 }}>{anchorId}</label>
                  <input
                    className="ct-input ct-input--mono"
                    value={getAnchorDraft(anchorId)}
                    onChange={event => {
                      anchorDraftRef.current[anchorId] = event.target.value
                      setForceRender(c => c + 1)
                      const [xRaw, yRaw] = event.target.value.split(',').map(s => s.trim())
                      const x = Number.parseFloat(xRaw)
                      const y = Number.parseFloat(yRaw)
                      if (Number.isFinite(x) && Number.isFinite(y)) {
                        // Update local preview only; defer backend sync until blur/Enter.
                        setMapState(c => ({ ...c, anchors: { ...c.anchors, [anchorId]: [x, y] as [number, number] } }))
                      }
                    }}
                    onFocus={() => {
                      anchorFocusedRef.current[anchorId] = true
                      anyAnchorFocusedRef.current = true
                    }}
                    onBlur={() => {
                      anchorFocusedRef.current[anchorId] = false
                      anyAnchorFocusedRef.current = Object.values(anchorFocusedRef.current).some(Boolean)
                      if (persistTimerRef.current) window.clearTimeout(persistTimerRef.current)
                      // Always parse the user's current draft for this anchor and merge on
                      // top of the latest map state. Poll-driven state resets can otherwise
                      // leave mapState stale between keystrokes and Enter.
                      const draft = anchorDraftRef.current[anchorId] ?? ''
                      const [xRaw, yRaw] = draft.split(',').map(s => s.trim())
                      const x = Number.parseFloat(xRaw)
                      const y = Number.parseFloat(yRaw)
                      const base = mapStateRef.current
                      const nextAnchorCoord: [number, number] =
                        Number.isFinite(x) && Number.isFinite(y)
                          ? [x, y]
                          : base.anchors[anchorId]
                      const nextMap: CalibrationMapRuntime = {
                        ...base,
                        anchors: { ...base.anchors, [anchorId]: nextAnchorCoord },
                      }
                      void persistMap(nextMap)
                    }}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        (e.target as HTMLInputElement).blur()
                        e.preventDefault()
                      }
                    }}
                  />
                </div>
              ))}

              {/* Line list */}
              <div className="ct-lines-list">
                {mapState.lines.map(line => {
                  const key = line.join('-')
                  const isSelected = selectedLineKey != null && matchLineKey(selectedLineKey, line)
                  return (
                    <div
                      key={key}
                      className={`ct-line-row${isSelected ? ' ct-line-row--selected' : ''}`}
                      onClick={() => setSelectedLineKey(isSelected ? null : key)}
                    >
                      <span>
                        <span style={{ color: ANCHOR_COLORS[line[0]] || '#8c96a5', fontWeight: 600 }}>{line[0]}</span>
                        {' → '}
                        <span style={{ color: ANCHOR_COLORS[line[1]] || '#8c96a5', fontWeight: 600 }}>{line[1]}</span>
                      </span>
                      <button
                        className="ct-line-row-delete"
                        onClick={event => {
                          event.stopPropagation()
                          deleteLineByKey(key)
                        }}
                        title="Delete line"
                      >✕</button>
                    </div>
                  )
                })}
              </div>

              {/* Create new line */}
              {!linePickerMode ? (
                <button className="ct-btn ct-btn--ghost ct-btn--full" onClick={() => setLinePickerMode(true)}>
                  + Create Line
                </button>
              ) : (
                <div className="ct-line-creator">
                  <div className="ct-line-creator-hint">
                    {linePicker.length === 0 ? 'Select first anchor' : `${linePicker[0]} → select second`}
                  </div>
                  <div className="ct-anchor-picker">
                    {ANCHOR_IDS.map(anchorId => (
                      <button
                        key={anchorId}
                        className={`ct-pill${linePicker.includes(anchorId) ? ' active' : ''}`}
                        onClick={() => {
                          const next = linePicker.includes(anchorId)
                            ? linePicker.filter(item => item !== anchorId)
                            : [...linePicker, anchorId]
                          if (next.length === 2) {
                            const newLine = [next[0], next[1]]
                            const exists = mapState.lines.some(l =>
                              (l[0] === newLine[0] && l[1] === newLine[1]) ||
                              (l[0] === newLine[1] && l[1] === newLine[0])
                            )
                            if (!exists) void persistMap({ ...mapState, lines: [...mapState.lines, newLine] })
                            setLinePicker([])
                            setLinePickerMode(false)
                          } else {
                            setLinePicker(next)
                          }
                        }}
                      >
                        {anchorId}
                      </button>
                    ))}
                  </div>
                  <button className="ct-btn ct-btn--ghost" onClick={() => { setLinePickerMode(false); setLinePicker([]) }}>
                    Cancel
                  </button>
                </div>
              )}

              {/* Height offset */}
              <div className="ct-field-inline" style={{ marginTop: 10 }}>
                <label className="ct-field-inline-label" style={{ fontSize: 9.5, whiteSpace: 'nowrap', minWidth: 60 }}>Height (ft)</label>
                <NumInput
                  className="ct-input"
                  value={mapState.height_offset}
                  step="0.01"
                  onChange={val => void persistMap({ ...mapState, height_offset: val })}
                />
              </div>
            </section>

            {/* SELECTED TAG */}
            <section className="ct-section">
              <div className="ct-section-title">Selected Tag</div>
              <div className="ct-tag-tabs">
                {runtime.tags.map(tag => (
                  <button
                    key={tag.tag_id}
                    className={`ct-pill${selectedTagId === tag.tag_id ? ' active' : ''}`}
                    style={selectedTagId === tag.tag_id ? { borderColor: tagColors[tag.tag_id], background: tagColors[tag.tag_id] + '22' } : {}}
                    onClick={() => setSelectedTagId(tag.tag_id)}
                  >
                    {tag.tag_id}
                  </button>
                ))}
              </div>
              {selectedTag ? (
                <>
                  <div className="ct-meta-grid">
                    <div>MAC<span>{selectedTag.mac_address || 'Not set'}</span></div>
                    <div>Device<span>{selectedTag.device_type || 'Unknown'}</span></div>
                  </div>
                    <table className="ct-table">
                    <thead><tr><th>Anchor</th><th>Raw</th><th>Cal</th></tr></thead>
                    <tbody>
                      {ANCHOR_IDS.map(anchorId => (
                        <tr key={anchorId}>
                          <td style={{ color: ANCHOR_COLORS[anchorId], fontWeight: 600 }}>{anchorId}</td>
                          <td>{selectedTag.raw_distances[anchorId] > 0 ? selectedTag.raw_distances[anchorId].toFixed(2) : '---'}</td>
                          <td>{selectedTag.calibrated_distances[anchorId] > 0 ? selectedTag.calibrated_distances[anchorId].toFixed(2) : '---'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="ct-runtime-note">RAW X,Y: {selectedTag.raw_xy ? `${selectedTag.raw_xy[0].toFixed(2)}, ${selectedTag.raw_xy[1].toFixed(2)}` : '---, ---'}</div>
                  <div className="ct-runtime-note">CAL X,Y: {selectedTag.calibrated_xy ? `${selectedTag.calibrated_xy[0].toFixed(2)}, ${selectedTag.calibrated_xy[1].toFixed(2)}` : '---, ---'}</div>
                </>
              ) : (
                <div className="ct-runtime-note">Create or load a tag profile to start calibrating.</div>
              )}
            </section>

            {selectedTag && (
              <>
                {/* REFERENCE DISTANCES */}
                <section className="ct-section">
                  <div className="ct-section-title">Reference Distances</div>
                  {ANCHOR_IDS.map(anchorId => (
                    <div key={anchorId} className="ct-field-inline">
                      <label className="ct-field-inline-label" style={{ color: ANCHOR_COLORS[anchorId], fontWeight: 600, minWidth: 30 }}>{anchorId}</label>
                      <input
                        className="ct-input"
                        value={referenceDistances[anchorId]}
                        placeholder="ft"
                        onFocus={() => { refDistFocusRef.current[anchorId] = true }}
                        onChange={e => setReferenceDistances(c => ({ ...c, [anchorId]: e.target.value }))}
                        onBlur={() => { refDistFocusRef.current[anchorId] = false; void saveReferenceDrafts() }}
                        onKeyDown={e => { if (e.key === 'Enter') { (e.target as HTMLInputElement).blur(); e.preventDefault() } }}
                      />
                    </div>
                  ))}
                  <div className="ct-field-inline">
                    <label className="ct-field-inline-label" style={{ fontSize: 9.5, whiteSpace: 'nowrap', minWidth: 60 }}>z Height (FT)</label>
                    <input
                      className="ct-input"
                      value={referenceHeight}
                      placeholder="ft"
                      onFocus={() => { refHeightFocusRef.current = true }}
                      onChange={e => setReferenceHeight(e.target.value)}
                      onBlur={() => { refHeightFocusRef.current = false; void saveReferenceDrafts() }}
                      onKeyDown={e => { if (e.key === 'Enter') { (e.target as HTMLInputElement).blur(); e.preventDefault() } }}
                    />
                  </div>
                  <div className="ct-actions">
                    <button
                      className={`ct-btn ${placingReference ? 'ct-btn--primary' : 'ct-btn--secondary'}`}
                      onClick={() => setPlacingReference(c => !c)}
                    >
                      {placingReference ? 'Click map to place' : 'Place on Map'}
                    </button>
                    <button className="ct-btn ct-btn--ghost" onClick={async () => {
                      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/reference/calculate', { tag_id: selectedTag.tag_id })
                      if (!data.success) showStatus(data.error ?? 'Could not calculate.', 'error')
                      else applySnapshot(data)
                    }}>Calculate</button>
                  </div>
                </section>

                {/* CALIBRATION FIT (collection controls only) */}
                <section className="ct-section">
                  <div className="ct-section-title">Calibration Fit</div>
                  <div className="ct-lock-grid">
                    {ANCHOR_IDS.map(anchorId => (
                      <div key={anchorId}>
                        <span style={{ color: ANCHOR_COLORS[anchorId], fontWeight: 600 }}>{anchorId}</span>
                        <span>{selectedTag.locked_reference[anchorId] != null ? selectedTag.locked_reference[anchorId]?.toFixed(3) : '---'}</span>
                      </div>
                    ))}
                  </div>
                  <div className="ct-actions">
                    <input className="ct-input ct-input--small" value={sampleCount} onChange={e => setSampleCount(e.target.value)} placeholder="N" />
                    <button
                      className="ct-btn ct-btn--primary"
                      onClick={handleCaptureStart}
                      disabled={busy.capture || runtime.capture.active}
                    >
                      {runtime.capture.active ? runtime.capture.phase : 'Collect'}
                    </button>
                  </div>
                  {ANCHOR_IDS.map(anchorId => {
                    const stallRemaining = runtime.capture.stall_remaining?.[anchorId]
                    const showCountdown =
                      runtime.capture.active &&
                      runtime.capture.phase === 'collect' &&
                      stallRemaining != null
                    return (
                      <div key={anchorId} className="ct-progress-row">
                        <span style={{ color: ANCHOR_COLORS[anchorId], fontWeight: 600 }}>{anchorId}</span>
                        <div className="ct-progress">
                          <div style={{ width: `${Math.min(100, ((runtime.capture.counts[anchorId] ?? 0) / Math.max(runtime.capture.target, 1)) * 100)}%` }} />
                        </div>
                        <span className="ct-progress-count">
                          {runtime.capture.counts[anchorId] ?? 0}/{runtime.capture.target || 0}
                          {showCountdown && (
                            <span className="ct-progress-stall"> {stallRemaining.toFixed(1)}s</span>
                          )}
                        </span>
                      </div>
                    )
                  })}
                </section>

                {/* CAPTURED POINTS */}
                <section className="ct-section">
                  <div className="ct-section-title">Captured Points</div>
                  {parsedPoints.length > 0 ? (
                    <div className="ct-capture-table-wrap">
                      <table className="ct-capture-table">
                        <thead>
                          <tr><th>#</th><th>Anchor</th><th>Raw (ft)</th><th>True (ft)</th></tr>
                        </thead>
                        <tbody>
                          {parsedPoints.map((pt, i) => (
                            <tr key={i}>
                              <td>{pt.index}</td>
                              <td>{pt.anchor}</td>
                              <td>{pt.raw.toFixed(3)}</td>
                              <td>{pt.trueDist.toFixed(3)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="ct-runtime-note">No data captured yet.</div>
                  )}
                  <button className="ct-btn ct-btn--ghost" style={{ marginTop: 8 }} onClick={async () => {
                    const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>(`/api/calibration/points/clear/${encodeURIComponent(selectedTag.tag_id)}`)
                    applySnapshot(data)
                  }}>Clear Data</button>
                </section>

                {/* EQUATIONS */}
                <section className="ct-section">
                  <div className="ct-section-title">Equations</div>

                  {/* Anchor selector */}
                  <div className="ct-tag-tabs">
                    {ANCHOR_IDS.map(anchorId => (
                      <button
                        key={anchorId}
                        className={`ct-pill${activeAnchorId === anchorId ? ' active' : ''}`}
                        onClick={() => setActiveAnchorId(anchorId)}
                      >
                        {anchorId}
                      </button>
                    ))}
                  </div>

                  {/* Active anchor controls */}
                  {activeFit && (
                    <div className="ct-eq-detail">
                      <div className="ct-field-inline" style={{ marginBottom: 8 }}>
                        <label className="ct-field-inline-label">Type</label>
                        <select
                          className="ct-input"
                          value={activeFit.fit_mode}
                          onChange={e => void updateFitOption(activeAnchorId, { fit_mode: e.target.value })}
                        >
                          {FIT_MODES.map(mode => <option key={mode} value={mode}>{mode}</option>)}
                        </select>
                      </div>
                      <label className="ct-check">
                        <input
                          type="checkbox"
                          checked={activeFit.auto}
                          onChange={e => void updateFitOption(activeAnchorId, { auto: e.target.checked })}
                        />
                        Auto Calibrate
                      </label>
                      {activeFit.fit_mode === 'Polynomial' && (
                        <div className="ct-field-inline" style={{ marginTop: 6 }}>
                          <label className="ct-field-inline-label">Degree</label>
                          <input
                            className="ct-input"
                            type="number"
                            min={1} max={10}
                            value={activeFit.poly_deg}
                            onChange={e => void updateFitOption(activeAnchorId, { poly_deg: Number.parseInt(e.target.value, 10) || 4 })}
                          />
                        </div>
                      )}
                      {activeFit.fit_mode === 'Moving Average' && (
                        <div className="ct-inline-fields" style={{ marginTop: 6 }}>
                          <div className="ct-field-inline" style={{ flex: 1 }}>
                            <label className="ct-field-inline-label">Period</label>
                            <input
                              className="ct-input"
                              type="number" min={2} max={10}
                              value={activeFit.ma_period}
                              onChange={e => void updateFitOption(activeAnchorId, { ma_period: Number.parseInt(e.target.value, 10) || 4 })}
                            />
                          </div>
                          <div className="ct-field-inline" style={{ flex: 1 }}>
                            <label className="ct-field-inline-label">Type</label>
                            <select
                              className="ct-input"
                              value={activeFit.ma_type}
                              onChange={e => void updateFitOption(activeAnchorId, { ma_type: e.target.value })}
                            >
                              <option value="Trailing">Trailing</option>
                              <option value="Centered">Centered</option>
                            </select>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Equations summary table */}
                  <div className="ct-eq-table">
                    {ANCHOR_IDS.map(anchorId => (
                      <div
                        key={anchorId}
                        className={`ct-eq-row${activeAnchorId === anchorId ? ' active' : ''}`}
                        onClick={() => setActiveAnchorId(anchorId)}
                      >
                        <span className="ct-eq-anchor" style={{ color: ANCHOR_COLORS[anchorId], fontWeight: 600 }}>{anchorId}</span>
                        <input
                          className="ct-eq-input"
                          value={equationDrafts[anchorId]}
                          placeholder="Raw distance"
                          onFocus={() => { equationFocusRef.current[anchorId] = true }}
                          onChange={e => setEquationDrafts(c => ({ ...c, [anchorId]: e.target.value }))}
                          onBlur={() => { equationFocusRef.current[anchorId] = false; void saveEquation(anchorId) }}
                          onClick={e => e.stopPropagation()}
                        />
                      </div>
                    ))}
                  </div>
                  <div className="ct-runtime-note" style={{ marginTop: 4 }}>
                    In profile: {selectedTag.saved_profile_equations[activeAnchorId] || 'Raw distance'}
                  </div>

                  <button
                    className="ct-btn ct-btn--primary ct-btn--full"
                    style={{ marginTop: 8 }}
                    onClick={() => setSendDialogOpen(true)}
                    disabled={!selectedTagId || busy.save}
                    title={`Export equations to a tag profile`}
                  >
                    {busy.save ? 'Sending…' : 'Send to Profile'}
                  </button>
                </section>

                {/* SMOOTHING FILTER */}
                <section className="ct-section">
                  <div className="ct-section-title">Smoothing Filter</div>
                  <div className="ct-tag-tabs">
                    {(['EMA', 'Rolling', 'Kalman'] as const).map(mode => (
                      <button
                        key={mode}
                        className={`ct-pill${runtime.filter.mode === mode ? ' active' : ''}`}
                        onClick={async () => {
                          const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/filter', { mode })
                          if (!data.success) showStatus(data.error ?? 'Could not update filter.', 'error')
                          else applySnapshot(data)
                        }}
                      >
                        {mode}
                      </button>
                    ))}
                  </div>

                  <div className="ct-slider-row">
                    <div className="ct-slider-header">
                      <label>EMA α</label>
                      <span className="ct-slider-val">{runtime.filter.ema_alpha.toFixed(2)}</span>
                    </div>
                    <input className="ct-range" type="range" min="0.01" max="0.99" step="0.01" value={runtime.filter.ema_alpha}
                      onChange={async e => { await updateFilter({ ema_alpha: Number.parseFloat(e.target.value) }) }} />
                  </div>

                  <div className="ct-slider-row">
                    <div className="ct-slider-header">
                      <label>Rolling N</label>
                      <span className="ct-slider-val">{runtime.filter.roll_n}</span>
                    </div>
                    <input className="ct-range" type="range" min="2" max="30" step="1" value={runtime.filter.roll_n}
                      onChange={async e => { await updateFilter({ roll_n: Number.parseInt(e.target.value, 10) }) }} />
                  </div>

                  <div className="ct-slider-row">
                    <div className="ct-slider-header">
                      <label>Kalman Q</label>
                      <span className="ct-slider-val">{runtime.filter.kal_q.toFixed(3)}</span>
                    </div>
                    <input className="ct-range" type="range" min="0.001" max="1" step="0.001" value={runtime.filter.kal_q}
                      onChange={async e => { await updateFilter({ kal_q: Number.parseFloat(e.target.value) }) }} />
                  </div>

                  <div className="ct-slider-row">
                    <div className="ct-slider-header">
                      <label>Kalman R</label>
                      <span className="ct-slider-val">{runtime.filter.kal_r.toFixed(1)}</span>
                    </div>
                    <input className="ct-range" type="range" min="0.1" max="20" step="0.1" value={runtime.filter.kal_r}
                      onChange={async e => { await updateFilter({ kal_r: Number.parseFloat(e.target.value) }) }} />
                  </div>
                </section>
              </>
            )}
          </div>
        </div>

        <CalibrationGraphPanel
          tag={selectedTag}
          collapsed={graphCollapsed}
          onToggle={() => setGraphCollapsed(c => !c)}
        />
      </div>

      {sendDialogOpen && selectedTagId && (
        <div
          className="confirm-dialog-overlay"
          onMouseDown={() => setSendDialogOpen(false)}
        >
          <div className="confirm-dialog" onMouseDown={e => e.stopPropagation()}>
            <div className="confirm-dialog-title">Send Equations to Profile</div>
            <div className="confirm-dialog-message">
              Send the current calibration equations to all tag profiles, or only to {selectedTagId}?
            </div>
            <div className="confirm-dialog-btns">
              <button
                className="confirm-dialog-btn confirm-dialog-btn--cancel"
                onClick={() => setSendDialogOpen(false)}
              >
                Cancel
              </button>
              <button
                className="confirm-dialog-btn confirm-dialog-btn--ok"
                onClick={async () => { setSendDialogOpen(false); await handleSaveTag() }}
                disabled={busy.save}
              >
                Only {selectedTagId}
              </button>
              <button
                className="confirm-dialog-btn confirm-dialog-btn--ok"
                onClick={async () => { setSendDialogOpen(false); await handleSendAllTags() }}
                disabled={busy.save || runtime.tags.length === 0}
              >
                All tags ({runtime.tags.length})
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CalibrationTool
