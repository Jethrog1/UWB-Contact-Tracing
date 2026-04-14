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

interface CalibrationToolProps {
  workspaceId: string
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

const CalibrationTool: React.FC<CalibrationToolProps> = ({ workspaceId: _workspaceId }) => {
  const mapCanvasRef = useRef<CalibrationMapCanvasHandle>(null)
  const mapSyncBlockedRef = useRef(false)
  const statusTimerRef = useRef<number | null>(null)

  const [runtime, setRuntime] = useState<CalibrationRuntimeSnapshot>(emptySnapshot)
  const [transportMode, setTransportMode] = useState<CalibrationTransportMode>('ble')
  const [serialPort, setSerialPort] = useState('')
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null)
  const [activeAnchorId, setActiveAnchorId] = useState<AnchorId>('A0')
  const [mapState, setMapState] = useState<CalibrationMapRuntime>(toMapState(emptySnapshot().map))
  const [placingReference, setPlacingReference] = useState(false)
  const [referenceDot, setReferenceDot] = useState<{ x: number; y: number } | null>(null)
  const [linePicker, setLinePicker] = useState<AnchorId[]>([])
  const [graphCollapsed, setGraphCollapsed] = useState(false)
  const [sampleCount, setSampleCount] = useState('20')
  const [referenceDistances, setReferenceDistances] = useState<Record<AnchorId, string>>({ A0: '', A1: '', A2: '', A3: '' })
  const [referenceHeight, setReferenceHeight] = useState('0')
  const [equationDrafts, setEquationDrafts] = useState<Record<AnchorId, string>>({ A0: '', A1: '', A2: '', A3: '' })
  const [status, setStatus] = useState<{ text: string; kind: 'ok' | 'error' } | null>(null)
  const [busy, setBusy] = useState<{ transport: boolean; save: boolean; capture: boolean }>({
    transport: false,
    save: false,
    capture: false,
  })

  const selectedTag = useMemo(
    () => runtime.tags.find(tag => tag.tag_id === selectedTagId) ?? null,
    [runtime.tags, selectedTagId],
  )
  const mapSignature = JSON.stringify(runtime.map)
  const referenceSignature = JSON.stringify(selectedTag ? {
    distances: selectedTag.reference_floor,
    height: selectedTag.reference_height,
  } : null)
  const equationSignature = JSON.stringify(selectedTag?.equations ?? null)
  const activeFit = selectedTag?.fit_options[activeAnchorId] ?? null
  const transportSummary = runtime.mode === 'serial'
    ? (runtime.selected_port || serialPort || 'Serial Port')
    : runtime.mode === 'ble'
      ? 'Bluetooth (BLE)'
      : 'Disconnected'
  const captureSummary = runtime.capture.active
    ? `${runtime.capture.phase}${runtime.capture.tag_id ? ` · ${runtime.capture.tag_id}` : ''}`
    : 'Idle'

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
      const response = await fetch(`${API}/api/calibration/runtime`)
      const data = await response.json() as CalibrationRuntimeSnapshot
      if (data.success) applySnapshot(data)
    } catch {
      // Silent while backend boots.
    }
  }

  useEffect(() => {
    void loadRuntime()
    const intervalId = window.setInterval(loadRuntime, 450)
    return () => {
      window.clearInterval(intervalId)
      if (statusTimerRef.current) window.clearTimeout(statusTimerRef.current)
    }
  }, [])

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
      if (!data.success) {
        showStatus(data.error ?? 'Could not update calibration map.', 'error')
        return
      }
      applySnapshot(data)
    } catch {
      showStatus('Could not reach backend.', 'error')
    } finally {
      mapSyncBlockedRef.current = false
    }
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
        tag_id: selectedTagId,
        distances,
        height: Number.parseFloat(referenceHeight || '0') || 0,
      })
      if (!data.success) {
        showStatus(data.error ?? 'Could not update reference distances.', 'error')
        return
      }
      applySnapshot(data)
    } catch {
      showStatus('Could not reach backend.', 'error')
    }
  }

  const saveEquation = async (anchorId: AnchorId) => {
    if (!selectedTagId) return
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/equation', {
        tag_id: selectedTagId,
        anchor_id: anchorId,
        equation: equationDrafts[anchorId],
      })
      if (!data.success) {
        showStatus(data.error ?? 'Equation is invalid.', 'error')
        return
      }
      applySnapshot(data)
    } catch {
      showStatus('Could not reach backend.', 'error')
    }
  }

  const updateFitOption = async (anchorId: AnchorId, patch: Record<string, unknown>) => {
    if (!selectedTagId) return
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/fit', {
        tag_id: selectedTagId,
        anchor_id: anchorId,
        ...patch,
      })
      if (!data.success) {
        showStatus(data.error ?? 'Could not update fit settings.', 'error')
        return
      }
      applySnapshot(data)
    } catch {
      showStatus('Could not reach backend.', 'error')
    }
  }

  const handleTransportConnect = async () => {
    setBusy(current => ({ ...current, transport: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string; detail?: string }>('/api/calibration/transport/connect', {
        mode: transportMode,
        port: transportMode === 'serial' ? serialPort : '',
      })
      if (!data.success) {
        showStatus(data.error ?? 'Could not connect transport.', 'error')
        return
      }
      applySnapshot(data)
    } catch {
      showStatus('Could not reach backend.', 'error')
    } finally {
      setBusy(current => ({ ...current, transport: false }))
    }
  }

  const handleTransportDisconnect = async () => {
    setBusy(current => ({ ...current, transport: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>('/api/calibration/transport/disconnect')
      applySnapshot(data)
    } catch {
      showStatus('Could not reach backend.', 'error')
    } finally {
      setBusy(current => ({ ...current, transport: false }))
    }
  }

  const handleReferencePlacement = async (x: number, y: number) => {
    if (!selectedTagId) return
    setReferenceDot({ x, y })
    setPlacingReference(false)
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/reference/place', {
        tag_id: selectedTagId,
        x,
        y,
      })
      if (!data.success) {
        showStatus(data.error ?? 'Could not place reference point.', 'error')
        return
      }
      applySnapshot(data)
    } catch {
      showStatus('Could not reach backend.', 'error')
    }
  }

  const handleCaptureStart = async () => {
    if (!selectedTagId) return
    setBusy(current => ({ ...current, capture: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/capture/start', {
        tag_id: selectedTagId,
        sample_count: Number.parseInt(sampleCount, 10) || 20,
      })
      if (!data.success) {
        showStatus(data.error ?? 'Could not start capture.', 'error')
        return
      }
      applySnapshot(data)
    } catch {
      showStatus('Could not reach backend.', 'error')
    } finally {
      setBusy(current => ({ ...current, capture: false }))
    }
  }

  const handleSaveTag = async () => {
    if (!selectedTagId) return
    setBusy(current => ({ ...current, save: true }))
    try {
      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>(`/api/calibration/tag/save/${encodeURIComponent(selectedTagId)}`)
      if (!data.success) {
        showStatus(data.error ?? 'Could not save tag equations.', 'error')
        return
      }
      applySnapshot(data)
      showStatus(`Saved calibration for ${selectedTagId}.`, 'ok')
    } catch {
      showStatus('Could not reach backend.', 'error')
    } finally {
      setBusy(current => ({ ...current, save: false }))
    }
  }

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
            placingReference={placingReference}
            onReferencePlaced={handleReferencePlacement}
            onCancelReferencePlacement={() => setPlacingReference(false)}
            onMapChange={setMapState}
            onMapCommit={persistMap}
          />
          <div className="ct-overview-card">
            <div className="ct-overview-kicker">Calibration Workspace</div>
            <div className="ct-overview-title">RTLS Calibration Software</div>
            <div className="ct-overview-subtitle">
              {selectedTagId ? `Editing ${selectedTagId}` : 'No profiled tags available yet'}
            </div>
            <div className="ct-overview-grid">
              <div>
                <label>Transport</label>
                <span>{transportSummary}</span>
              </div>
              <div>
                <label>Status</label>
                <span>{runtime.transport_status}</span>
              </div>
              <div>
                <label>Tags</label>
                <span>{runtime.tags.length}</span>
              </div>
              <div>
                <label>Capture</label>
                <span>{captureSummary}</span>
              </div>
            </div>
          </div>
          {status && <div className={`ct-status ct-status--${status.kind}`}>{status.text}</div>}
          <button className="ct-reset-btn" onClick={() => mapCanvasRef.current?.resetView()}>Reset View</button>
          <div className="ct-canvas-hint">Drag to pan, scroll to zoom, and drag anchors to tune the map.</div>
        </div>

        <div className="ct-right-panel">
          <div className="ct-panel-header">
            <div>
              <div className="ct-panel-title">Calibration Controls</div>
              <div className="ct-panel-subtitle">
                {selectedTagId ? `Editing ${selectedTagId}` : `${runtime.tags.length} profiled tags available`}
              </div>
            </div>
            <button className="ct-btn ct-btn--secondary" onClick={handleSaveTag} disabled={!selectedTagId || busy.save}>
              {busy.save ? 'Saving...' : 'Save Tag'}
            </button>
          </div>
          <div className="ct-panel-scroll">
            <section className="ct-section">
              <div className="ct-section-title">Connectivity</div>
              <div className="ct-transport-toggle">
                <button className={`ct-toggle${transportMode === 'ble' ? ' active' : ''}`} onClick={() => setTransportMode('ble')}>Bluetooth (BLE)</button>
                <button className={`ct-toggle${transportMode === 'serial' ? ' active' : ''}`} onClick={() => setTransportMode('serial')}>Serial Port</button>
              </div>
              {transportMode === 'serial' && (
                <select className="ct-input" value={serialPort} onChange={event => setSerialPort(event.target.value)}>
                  <option value="">Select a COM port</option>
                  {runtime.ports.map(port => <option key={port} value={port}>{port}</option>)}
                </select>
              )}
              <div className="ct-runtime-note">{runtime.transport_detail}</div>
              {runtime.tags.length > 0 ? (
                <div className="ct-rows">
                  {runtime.tags.map(tag => (
                    <div key={tag.tag_id} className="ct-ble-row">
                      <span>{tag.tag_id}</span>
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

            <section className="ct-section">
              <div className="ct-section-title">Map Geometry</div>
              {ANCHOR_IDS.map(anchorId => (
                <div key={anchorId} className="ct-field">
                  <label>{anchorId}</label>
                  <input
                    className="ct-input ct-input--mono"
                    value={`${mapState.anchors[anchorId][0]}, ${mapState.anchors[anchorId][1]}`}
                    onChange={event => {
                      const [xRaw, yRaw] = event.target.value.split(',').map(part => part.trim())
                      const x = Number.parseFloat(xRaw)
                      const y = Number.parseFloat(yRaw)
                      if (!Number.isFinite(x) || !Number.isFinite(y)) return
                      setMapState(current => ({ ...current, anchors: { ...current.anchors, [anchorId]: [x, y] } }))
                    }}
                    onBlur={() => void persistMap(mapState)}
                  />
                </div>
              ))}
              <div className="ct-lines-list">
                {mapState.lines.map(line => (
                    <button key={line.join('-')} className="ct-line-row" onClick={() => void persistMap({ ...mapState, lines: mapState.lines.filter(item => item.join('-') !== line.join('-')) })}>
                      <span>{line[0]} {'->'} {line[1]}</span>
                    <span>x</span>
                  </button>
                ))}
              </div>
              <div className="ct-anchor-picker">
                {ANCHOR_IDS.map(anchorId => (
                  <button
                    key={anchorId}
                    className={`ct-pill${linePicker.includes(anchorId) ? ' active' : ''}`}
                    onClick={() => {
                      const next = linePicker.includes(anchorId) ? linePicker.filter(item => item !== anchorId) : [...linePicker, anchorId]
                      if (next.length === 2) {
                        const newLine = [next[0], next[1]]
                        const exists = mapState.lines.some(line => (line[0] === newLine[0] && line[1] === newLine[1]) || (line[0] === newLine[1] && line[1] === newLine[0]))
                        if (!exists) void persistMap({ ...mapState, lines: [...mapState.lines, newLine] })
                        setLinePicker([])
                      } else {
                        setLinePicker(next)
                      }
                    }}
                  >
                    {anchorId}
                  </button>
                ))}
              </div>
              <div className="ct-field">
                <label>Anchor to Tag height (ft)</label>
                <input
                  className="ct-input"
                  type="number"
                  step="0.01"
                  value={mapState.height_offset}
                  onChange={event => setMapState(current => ({ ...current, height_offset: Number.parseFloat(event.target.value) || 0 }))}
                  onBlur={() => void persistMap(mapState)}
                />
              </div>
            </section>

            <section className="ct-section">
              <div className="ct-section-title">Selected Tag</div>
              <div className="ct-tag-tabs">
                {runtime.tags.map(tag => (
                  <button key={tag.tag_id} className={`ct-pill${selectedTagId === tag.tag_id ? ' active' : ''}`} onClick={() => setSelectedTagId(tag.tag_id)}>
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
                <section className="ct-section">
                  <div className="ct-section-title">Reference Distances</div>
                  {ANCHOR_IDS.map(anchorId => (
                    <div key={anchorId} className="ct-field">
                      <label>{anchorId} Distance (X)</label>
                      <input className="ct-input" value={referenceDistances[anchorId]} onChange={event => setReferenceDistances(current => ({ ...current, [anchorId]: event.target.value }))} onBlur={() => void saveReferenceDrafts()} />
                    </div>
                  ))}
                  <div className="ct-field">
                    <label>Height (Y) ft</label>
                    <input className="ct-input" value={referenceHeight} onChange={event => setReferenceHeight(event.target.value)} onBlur={() => void saveReferenceDrafts()} />
                  </div>
                  <div className="ct-actions">
                    <button className={`ct-btn ${placingReference ? 'ct-btn--primary' : 'ct-btn--secondary'}`} onClick={() => setPlacingReference(current => !current)}>Place on Map</button>
                    <button className="ct-btn ct-btn--ghost" onClick={async () => {
                      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/reference/calculate', { tag_id: selectedTag.tag_id })
                      if (!data.success) showStatus(data.error ?? 'Could not calculate reference.', 'error')
                      else applySnapshot(data)
                    }}>Calculate Reference</button>
                  </div>
                </section>

                <section className="ct-section">
                  <div className="ct-section-title">Calibration Fit</div>
                  <div className="ct-lock-grid">
                    {ANCHOR_IDS.map(anchorId => <div key={anchorId}>{anchorId}<span>{selectedTag.locked_reference[anchorId] != null ? selectedTag.locked_reference[anchorId]?.toFixed(3) : '---'}</span></div>)}
                  </div>
                  <div className="ct-actions">
                    <input className="ct-input ct-input--small" value={sampleCount} onChange={event => setSampleCount(event.target.value)} />
                    <button className="ct-btn ct-btn--primary" onClick={handleCaptureStart} disabled={busy.capture || runtime.capture.active}>
                      {runtime.capture.active ? runtime.capture.phase : 'Capture'}
                    </button>
                  </div>
                  {ANCHOR_IDS.map(anchorId => (
                    <div key={anchorId} className="ct-progress-row">
                      <span>{anchorId}</span>
                      <div className="ct-progress"><div style={{ width: `${Math.min(100, ((runtime.capture.counts[anchorId] ?? 0) / Math.max(runtime.capture.target, 1)) * 100)}%` }} /></div>
                      <span>{runtime.capture.counts[anchorId] ?? 0}/{runtime.capture.target || 0}</span>
                    </div>
                  ))}
                  <div className="ct-tag-tabs">
                    {ANCHOR_IDS.map(anchorId => <button key={anchorId} className={`ct-pill${activeAnchorId === anchorId ? ' active' : ''}`} onClick={() => setActiveAnchorId(anchorId)}>{anchorId}</button>)}
                  </div>
                  {activeFit && (
                    <>
                      <label className="ct-check"><input type="checkbox" checked={activeFit.auto} onChange={event => void updateFitOption(activeAnchorId, { auto: event.target.checked })} /> Auto Calibrate</label>
                      <select className="ct-input" value={activeFit.fit_mode} onChange={event => void updateFitOption(activeAnchorId, { fit_mode: event.target.value })}>
                        {FIT_MODES.map(mode => <option key={mode} value={mode}>{mode}</option>)}
                      </select>
                      {activeFit.fit_mode === 'Polynomial' && <input className="ct-input" type="number" min={1} max={10} value={activeFit.poly_deg} onChange={event => void updateFitOption(activeAnchorId, { poly_deg: Number.parseInt(event.target.value, 10) || 4 })} />}
                      {activeFit.fit_mode === 'Moving Average' && (
                        <div className="ct-inline-fields">
                          <input className="ct-input" type="number" min={2} max={10} value={activeFit.ma_period} onChange={event => void updateFitOption(activeAnchorId, { ma_period: Number.parseInt(event.target.value, 10) || 4 })} />
                          <select className="ct-input" value={activeFit.ma_type} onChange={event => void updateFitOption(activeAnchorId, { ma_type: event.target.value })}>
                            <option value="Trailing">Trailing</option>
                            <option value="Centered">Centered</option>
                          </select>
                        </div>
                      )}
                    </>
                  )}
                  {ANCHOR_IDS.map(anchorId => (
                    <div key={anchorId} className="ct-field">
                      <label>{anchorId} Equation</label>
                      <input className="ct-input ct-input--mono" value={equationDrafts[anchorId]} onChange={event => setEquationDrafts(current => ({ ...current, [anchorId]: event.target.value }))} onBlur={() => void saveEquation(anchorId)} />
                      <div className="ct-runtime-note">Saved: {selectedTag.saved_profile_equations[anchorId] || 'Raw distance'}</div>
                    </div>
                  ))}
                </section>

                <section className="ct-section">
                  <div className="ct-section-title">Captured Points</div>
                  <div className="ct-points-log">{selectedTag.captured_points_log.length > 0 ? selectedTag.captured_points_log.join('\n') : 'No data captured yet.'}</div>
                  <button className="ct-btn ct-btn--ghost" onClick={async () => {
                    const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>(`/api/calibration/points/clear/${encodeURIComponent(selectedTag.tag_id)}`)
                    applySnapshot(data)
                  }}>Clear Captured Data</button>
                </section>

                <section className="ct-section">
                  <div className="ct-section-title">Smoothing Filter</div>
                  <div className="ct-tag-tabs">
                    {['EMA', 'Rolling', 'Kalman'].map(mode => <button key={mode} className={`ct-pill${runtime.filter.mode === mode ? ' active' : ''}`} onClick={async () => {
                      const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean; error?: string }>('/api/calibration/filter', { mode })
                      if (!data.success) showStatus(data.error ?? 'Could not update filter.', 'error')
                      else applySnapshot(data)
                    }}>{mode}</button>)}
                  </div>
                  <div className="ct-slider-row"><label>EMA a</label><input className="ct-input" type="number" step="0.01" value={runtime.filter.ema_alpha} onChange={async event => {
                    const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>('/api/calibration/filter', { mode: runtime.filter.mode, ema_alpha: Number.parseFloat(event.target.value) || 0.2 })
                    applySnapshot(data)
                  }} /></div>
                  <div className="ct-slider-row"><label>Rolling</label><input className="ct-input" type="number" step="1" value={runtime.filter.roll_n} onChange={async event => {
                    const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>('/api/calibration/filter', { mode: runtime.filter.mode, roll_n: Number.parseInt(event.target.value, 10) || 8 })
                    applySnapshot(data)
                  }} /></div>
                  <div className="ct-slider-row"><label>Kalman Q</label><input className="ct-input" type="number" step="0.01" value={runtime.filter.kal_q} onChange={async event => {
                    const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>('/api/calibration/filter', { mode: runtime.filter.mode, kal_q: Number.parseFloat(event.target.value) || 0.1 })
                    applySnapshot(data)
                  }} /></div>
                  <div className="ct-slider-row"><label>Kalman R</label><input className="ct-input" type="number" step="0.1" value={runtime.filter.kal_r} onChange={async event => {
                    const data = await postJson<CalibrationRuntimeSnapshot & { success: boolean }>('/api/calibration/filter', { mode: runtime.filter.mode, kal_r: Number.parseFloat(event.target.value) || 2 })
                    applySnapshot(data)
                  }} /></div>
                </section>
              </>
            )}
          </div>
        </div>

        <CalibrationGraphPanel tag={selectedTag} collapsed={graphCollapsed} onToggle={() => setGraphCollapsed(current => !current)} />
      </div>
    </div>
  )
}

export default CalibrationTool
