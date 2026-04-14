import React, { useEffect, useMemo, useRef, useState } from 'react'
import CalibrationMapCanvas, { CalibrationMapCanvasHandle } from './CalibrationMapCanvas'
import CalibrationGraphPanel from './CalibrationGraphPanel'
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

const RIGHT_INSET = 368 + 32
const GRAPH_INSET_VISIBLE = 290
const GRAPH_INSET_COLLAPSED = 50

const TAG_PALETTE = ['#3498db', '#e67e22', '#9b59b6', '#27ae60', '#e74c3c', '#f1c40f', '#1abc9c', '#d16cff']

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

  graphCollapsedRef.current = graphCollapsed

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
    setSelectedTagId(current => (current && snapshot.tags.some(tag => tag.tag_id === current) ? current : snapshot.tags[0]?.tag_id ?? null))
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
    const intervalId = window.setInterval(loadRuntime, 450)
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
    if (!mapSyncBlockedRef.current) setMapState(toMapState(runtime.map))
  }, [mapSignature, runtime.map])

  useEffect(() => {
    if (!selectedTag) return
    setReferenceDistances({
      A0: selectedTag.reference_floor.A0 != null ? String(selectedTag.reference_floor.A0) : '',
      A1: selectedTag.reference_floor.A1 != null ? String(selectedTag.reference_floor.A1) : '',
      A2: selectedTag.reference_floor.A2 != null ? String(selectedTag.reference_floor.A2) : '',
      A3: selectedTag.reference_floor.A3 != null ? String(selectedTag.reference_floor.A3) : '',
    })
    setReferenceHeight(String(selectedTag.reference_height ?? 0))
  }, [selectedTagId, referenceSignature])

  useEffect(() => {
    if (!selectedTag) return
    setEquationDrafts({
      A0: selectedTag.equations.A0 ?? '',
      A1: selectedTag.equations.A1 ?? '',
      A2: selectedTag.equations.A2 ?? '',
      A3: selectedTag.equations.A3 ?? '',
    })
  }, [selectedTagId, equationSignature])

  const postJson = async <T,>(path: string, body?: unknown): Promise<T> => {
    const response = await fetch(`${API}${path}`, {
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
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/transport/connect', {
        mode: transportMode, port: transportMode === 'serial' ? serialPort : '',
      })
      if (!data.success) { showStatus(data.error ?? 'Could not connect.', 'error'); return }
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
    finally { setBusy(c => ({ ...c, transport: false })) }
  }

  const handleTransportDisconnect = async () => {
    setBusy(c => ({ ...c, transport: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>('/api/calibration/transport/disconnect')
      applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
    finally { setBusy(c => ({ ...c, transport: false })) }
  }

  const handleReferencePlacement = async (x: number, y: number) => {
    if (!selectedTagId) return
    setReferenceDot({ x, y })
    setPlacingReference(false)
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/reference/place', {
        tag_id: selectedTagId, x, y,
      })
      if (!data.success) { showStatus(data.error ?? 'Could not place reference.', 'error'); return }
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

  const handleSaveTag = async () => {
    if (!selectedTagId) return
    setBusy(c => ({ ...c, save: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>(`/api/calibration/tag/save/${encodeURIComponent(selectedTagId)}?workspace_id=${encodeURIComponent(workspaceId)}`)
      if (!data.success) { showStatus(data.error ?? 'Could not save tag.', 'error'); return }
      applySnapshot(data)
      showStatus(`Saved calibration for ${selectedTagId}.`, 'ok')
    } catch { showStatus('Could not reach backend.', 'error') }
    finally { setBusy(c => ({ ...c, save: false })) }
  }

  const updateFilter = async (patch: Record<string, unknown>) => {
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/filter', {
        mode: runtime.filter.mode, ...patch,
      })
      if (!data.success) showStatus(data.error ?? 'Could not update filter.', 'error')
      else applySnapshot(data)
    } catch { showStatus('Could not reach backend.', 'error') }
  }

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

  // Sync anchor drafts from mapState when not focused
  const getAnchorDraft = (anchorId: AnchorId) => {
    if (!anchorFocusedRef.current[anchorId]) {
      anchorDraftRef.current[anchorId] = `${mapState.anchors[anchorId][0]}, ${mapState.anchors[anchorId][1]}`
    }
    return anchorDraftRef.current[anchorId]
  }

  // ── Parsed captured points ────────────────────────────────────────
  const parsedPoints = useMemo(
    () => selectedTag ? parsePointLog(selectedTag.captured_points_log) : [],
    [selectedTag?.captured_points_log],
  )

  return (
    <div className="ct-root">
      <div className="ct-stage">
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
              <div className="ct-panel-subtitle">
                {selectedTagId ? `Editing ${selectedTagId}` : `${runtime.tags.length} profiled tags`}
              </div>
            </div>
            <button className="ct-btn ct-btn--secondary" onClick={handleSaveTag} disabled={!selectedTagId || busy.save}>
              {busy.save ? 'Saving…' : 'Save Tag'}
            </button>
          </div>

          <div className="ct-panel-scroll">

            {/* CONNECTIVITY */}
            <section className="ct-section">
              <div className="ct-section-title">Connectivity</div>
              <div className="ct-transport-toggle">
                <button className={`ct-toggle${transportMode === 'ble' ? ' active' : ''}`} onClick={() => setTransportMode('ble')}>Bluetooth (BLE)</button>
                <button className={`ct-toggle${transportMode === 'serial' ? ' active' : ''}`} onClick={() => setTransportMode('serial')}>Serial Port</button>
              </div>
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
                      <span>{tag.status}</span>
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
                  <label className="ct-field-inline-label">{anchorId}</label>
                  <input
                    className="ct-input ct-input--mono"
                    value={getAnchorDraft(anchorId)}
                    onChange={event => {
                      anchorDraftRef.current[anchorId] = event.target.value
                      // Force re-render for the input
                      const [xRaw, yRaw] = event.target.value.split(',').map(s => s.trim())
                      const x = Number.parseFloat(xRaw)
                      const y = Number.parseFloat(yRaw)
                      if (Number.isFinite(x) && Number.isFinite(y)) {
                        setMapState(current => ({ ...current, anchors: { ...current.anchors, [anchorId]: [x, y] } }))
                      }
                    }}
                    onFocus={() => { anchorFocusedRef.current[anchorId] = true }}
                    onBlur={() => {
                      anchorFocusedRef.current[anchorId] = false
                      void persistMap(mapState)
                    }}
                  />
                </div>
              ))}

              {/* Line list */}
              <div className="ct-lines-list">
                {mapState.lines.map(line => {
                  const key = line.join('-')
                  return (
                    <div key={key} className="ct-line-row">
                      <span>{line[0]} → {line[1]}</span>
                      <button
                        className="ct-line-row-delete"
                        onClick={() => void persistMap({ ...mapState, lines: mapState.lines.filter(item => item.join('-') !== key) })}
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
                <label className="ct-field-inline-label" style={{ fontSize: 9.5, whiteSpace: 'nowrap' }}>Height (ft)</label>
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
                          <td>{anchorId}</td>
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
                      <label className="ct-field-inline-label">{anchorId}</label>
                      <input
                        className="ct-input"
                        value={referenceDistances[anchorId]}
                        placeholder="ft"
                        onChange={e => setReferenceDistances(c => ({ ...c, [anchorId]: e.target.value }))}
                        onBlur={() => void saveReferenceDrafts()}
                      />
                    </div>
                  ))}
                  <div className="ct-field-inline">
                    <label className="ct-field-inline-label">Height</label>
                    <input
                      className="ct-input"
                      value={referenceHeight}
                      placeholder="ft"
                      onChange={e => setReferenceHeight(e.target.value)}
                      onBlur={() => void saveReferenceDrafts()}
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
                        {anchorId}
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
                  {ANCHOR_IDS.map(anchorId => (
                    <div key={anchorId} className="ct-progress-row">
                      <span>{anchorId}</span>
                      <div className="ct-progress">
                        <div style={{ width: `${Math.min(100, ((runtime.capture.counts[anchorId] ?? 0) / Math.max(runtime.capture.target, 1)) * 100)}%` }} />
                      </div>
                      <span>{runtime.capture.counts[anchorId] ?? 0}/{runtime.capture.target || 0}</span>
                    </div>
                  ))}
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
                        <span className="ct-eq-anchor">{anchorId}</span>
                        <input
                          className="ct-eq-input"
                          value={equationDrafts[anchorId]}
                          placeholder="Raw distance"
                          onChange={e => setEquationDrafts(c => ({ ...c, [anchorId]: e.target.value }))}
                          onBlur={() => void saveEquation(anchorId)}
                          onClick={e => e.stopPropagation()}
                        />
                      </div>
                    ))}
                  </div>
                  <div className="ct-runtime-note" style={{ marginTop: 4 }}>
                    Saved: {selectedTag.saved_profile_equations[activeAnchorId] || 'Raw distance'}
                  </div>
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
    </div>
  )
}

export default CalibrationTool
