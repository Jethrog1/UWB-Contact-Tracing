/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import RTLSDashboardCanvas, {
  RTLSDashboardCanvasHandle,
  RTLSTagState,
  tagColor,
} from './RTLSDashboardCanvas'
import './RTLSDashboard.css'

const API = 'http://localhost:8765'
const POLL_MS = 80
const AUTO_LOAD_RETRIES = 6
const AUTO_LOAD_DELAY_MS = 1500

// ── Types ──────────────────────────────────────────────────────────────────────

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

interface RTLSSnapshot {
  transport_status: string
  transport_detail: string
  selected_port: string
  ports: string[]
  auto_detect_port: string
  tags: RTLSTag[]
  anchors: Record<string, [number, number]>
  segments: { x1: number; y1: number; x2: number; y2: number }[]
  room_bounds: { min_x?: number; min_y?: number; max_x?: number; max_y?: number }
  room_name: string
  reference_anchor_id: string
  filter: FilterState
  elevation: ElevationState
  csv: CSVState
}

interface RTLSDashboardProps {
  workspaceId: string
  workspaceName: string
}

// ── Controlled numeric input ───────────────────────────────────────────────────
const NumInput: React.FC<{
  value: number
  min?: number
  max?: number
  disabled?: boolean
  onChange: (v: number) => void
}> = ({ value, min, max, disabled, onChange }) => {
  const [draft, setDraft] = useState(String(value))
  const focused = useRef(false)
  useEffect(() => { if (!focused.current) setDraft(String(value)) }, [value])
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
        const clamped = isFinite(parsed)
          ? Math.max(min ?? -Infinity, Math.min(max ?? Infinity, parsed))
          : value
        setDraft(String(clamped))
        onChange(clamped)
      }}
    />
  )
}

// ── Empty state ────────────────────────────────────────────────────────────────
const emptySnap = (): RTLSSnapshot => ({
  transport_status: 'idle',
  transport_detail: 'Disconnected.',
  selected_port: '',
  ports: [],
  auto_detect_port: '',
  tags: [],
  anchors: {},
  segments: [],
  room_bounds: {},
  room_name: '',
  reference_anchor_id: '',
  filter: { mode: 'EMA', ema_alpha: 0.2, roll_n: 8, kal_q: 0.1, kal_r: 2.0 },
  elevation: { override: false, value_ft: 3.0 },
  csv: { enabled: false, path: '' },
})

// ── Main component ─────────────────────────────────────────────────────────────
const RTLSDashboard: React.FC<RTLSDashboardProps> = ({ workspaceId, workspaceName }) => {
  const [snap, setSnap] = useState<RTLSSnapshot>(emptySnap)
  const [statusMsg, setStatusMsg] = useState<{ text: string; kind: 'ok' | 'warn' | 'error' } | null>(null)
  const [transportMode, setTransportMode] = useState<'Serial Port' | 'Bluetooth (BLE)'>('Serial Port')
  const [roomLoaded, setRoomLoaded] = useState(false)
  const [svgContent, setSvgContent] = useState<string | null>(null)
  const [autoLoading, setAutoLoading] = useState(false)
  const canvasRef = useRef<RTLSDashboardCanvasHandle>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const busy = useRef(false)

  const showMsg = (text: string, kind: 'ok' | 'warn' | 'error', ms = 4000) => {
    setStatusMsg({ text, kind })
    setTimeout(() => setStatusMsg(null), ms)
  }

  // ── Polling ────────────────────────────────────────────────────────────────
  const poll = useCallback(async () => {
    if (busy.current) return
    busy.current = true
    try {
      const res = await fetch(`${API}/api/rtls/snapshot`)
      if (!res.ok) return
      const data = await res.json()
      if (data.success) setSnap(data as RTLSSnapshot)
    } catch { /* server may not be ready */ }
    finally { busy.current = false }
  }, [])

  useEffect(() => {
    pollRef.current = setInterval(poll, POLL_MS)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [poll])

  // ── Load workspace ─────────────────────────────────────────────────────────
  const loadWorkspace = useCallback(async (opts?: {
    manifestPath?: string
    folderPath?: string
    svgFolder?: string
    roomsFolder?: string
    tagsFolder?: string
    silent?: boolean
  }) => {
    try {
      const res = await fetch(`${API}/api/rtls/workspace/load`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_id: workspaceId,
          workspace_name: workspaceName,
          manifest_path: opts?.manifestPath ?? null,
          folder_path: opts?.folderPath ?? null,
          svg_folder: opts?.svgFolder ?? null,
          rooms_folder: opts?.roomsFolder ?? null,
          tags_folder: opts?.tagsFolder ?? null,
        }),
      })
      const data = await res.json() as any
      if (data.success) {
        setSnap(data as RTLSSnapshot)
        setRoomLoaded(true)
        if (data.svg_content) setSvgContent(data.svg_content)
        showMsg(`Loaded: ${data.room_name} (${data.anchor_count} anchors, ${data.tag_count} tags)`, 'ok')
        setTimeout(() => canvasRef.current?.resetView(), 120)
        return true
      } else {
        if (!opts?.silent) showMsg(data.error ?? 'No room data found in workspace.', 'warn')
        return false
      }
    } catch {
      if (!opts?.silent) showMsg('Backend unavailable.', 'error')
      return false
    }
  }, [workspaceId, workspaceName])

  // ── Auto-load on mount / workspace switch with retries ────────────────────
  useEffect(() => {
    setRoomLoaded(false)
    setSvgContent(null)
    setAutoLoading(true)
    let cancelled = false
    let attempt = 0

    const tryLoad = async () => {
      if (cancelled) return
      attempt++
      const isFinal = attempt >= AUTO_LOAD_RETRIES
      const ok = await loadWorkspace({ silent: !isFinal })
      if (ok || isFinal || cancelled) {
        if (!cancelled) setAutoLoading(false)
        return
      }
      setTimeout(tryLoad, AUTO_LOAD_DELAY_MS)
    }
    tryLoad()

    return () => { cancelled = true; setAutoLoading(false) }
  }, [workspaceId]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── View commands (refresh from TabStrip) ──────────────────────────────────
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { cmd: string; workspaceId: string }
      if (detail.workspaceId !== workspaceId) return
      if (detail.cmd === 'refresh') loadWorkspace()
    }
    window.addEventListener('rtls-view-command', handler)
    return () => window.removeEventListener('rtls-view-command', handler)
  }, [workspaceId, loadWorkspace])

  const loadFile = async () => {
    const r = await window.api?.openFile?.([
      { name: 'Room Manifest', extensions: ['json'] },
    ])
    if (r && !r.canceled && r.filePaths[0]) loadWorkspace({ manifestPath: r.filePaths[0] })
  }

  const loadFolder = async () => {
    const r = await window.api?.openFolder?.()
    if (r && !r.canceled && r.folderPath) loadWorkspace({ folderPath: r.folderPath })
  }

  const loadSvgFolder = async () => {
    const r = await window.api?.openFolder?.()
    if (r && !r.canceled && r.folderPath) loadWorkspace({ svgFolder: r.folderPath })
  }

  const loadRoomsFolder = async () => {
    const r = await window.api?.openFolder?.()
    if (r && !r.canceled && r.folderPath) loadWorkspace({ roomsFolder: r.folderPath })
  }

  const loadTagsFolder = async () => {
    const r = await window.api?.openFolder?.()
    if (r && !r.canceled && r.folderPath) loadWorkspace({ tagsFolder: r.folderPath })
  }

  // ── Transport ──────────────────────────────────────────────────────────────
  const connect = async () => {
    const port = snap.selected_port || snap.auto_detect_port
    if (!port) { showMsg('Select a COM port first.', 'warn'); return }
    try {
      const res = await fetch(`${API}/api/rtls/serial/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port }),
      })
      const data = await res.json() as any
      if (data.success) setSnap(data as RTLSSnapshot)
    } catch { /* ignore */ }
  }

  const disconnect = async () => {
    try {
      const res = await fetch(`${API}/api/rtls/serial/disconnect`, { method: 'POST' })
      const data = await res.json() as any
      if (data.success) setSnap(data as RTLSSnapshot)
    } catch { /* ignore */ }
  }

  // ── Filter ─────────────────────────────────────────────────────────────────
  const setFilter = async (patch: Partial<FilterState>) => {
    const next = { ...snap.filter, ...patch }
    setSnap(prev => ({ ...prev, filter: next }))
    try {
      await fetch(`${API}/api/rtls/filter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
    } catch { /* ignore */ }
  }

  // ── Elevation ──────────────────────────────────────────────────────────────
  const setElevation = async (patch: Partial<ElevationState>) => {
    const next = { ...snap.elevation, ...patch }
    setSnap(prev => ({ ...prev, elevation: next }))
    try {
      await fetch(`${API}/api/rtls/elevation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override: next.override, value_ft: next.value_ft }),
      })
    } catch { /* ignore */ }
  }

  // ── CSV logging ───────────────────────────────────────────────────────────
  const toggleCsv = async () => {
    const endpoint = snap.csv.enabled ? '/api/rtls/csv/stop' : '/api/rtls/csv/start'
    try {
      const res = await fetch(`${API}${endpoint}`, { method: 'POST' })
      const data = await res.json() as any
      if (data.success) {
        setSnap(data as RTLSSnapshot)
        if (!snap.csv.enabled) showMsg(`CSV logging started`, 'ok')
        else showMsg('CSV logging stopped', 'ok')
      } else {
        showMsg(data.error ?? 'CSV error', 'warn')
      }
    } catch { /* ignore */ }
  }

  // ── Canvas tag state ───────────────────────────────────────────────────────
  const tagStates: RTLSTagState[] = snap.tags.map((t, i) => ({
    tag_id: t.tag_id,
    status: t.status,
    position: t.position,
    color: tagColor(i),
  }))

  const tStatus = snap.transport_status
  const transportKind: 'ok' | 'warn' | 'error' | undefined =
    tStatus === 'connected' ? 'ok'
    : tStatus === 'connecting' ? 'warn'
    : tStatus === 'error' ? 'error'
    : undefined

  const { filter, elevation } = snap

  return (
    <div className="rtls-root">
      <div className="rtls-stage">

        {/* ── Main canvas panel ── */}
        <div className="rtls-main-panel">
          {!roomLoaded ? (
            <div className="rtls-no-room">
              <div className="rtls-no-room-icon">{autoLoading ? '◌' : '◎'}</div>
              <div className="rtls-no-room-text">
                {autoLoading
                  ? 'Connecting to backend…'
                  : <>No floor plan loaded.<br />Use &quot;Load Workspace&quot; in the right panel to begin.</>
                }
              </div>
            </div>
          ) : (
            <RTLSDashboardCanvas
              ref={canvasRef}
              segments={snap.segments}
              anchors={snap.anchors}
              tags={tagStates}
              roomBounds={snap.room_bounds}
              svgContent={svgContent}
              referenceAnchorId={snap.reference_anchor_id}
            />
          )}
        </div>

        {/* ── Status toast ── */}
        {statusMsg && (
          <div className={`rtls-status rtls-status--${statusMsg.kind}`}>
            {statusMsg.text}
          </div>
        )}
        {!statusMsg && transportKind && (
          <div className={`rtls-status rtls-status--${transportKind}`}>
            {snap.transport_detail}
          </div>
        )}

        <div className="rtls-canvas-hint">Scroll to zoom · Drag to pan</div>

        {/* ── Right panel ── */}
        <div className="rtls-right-panel">
          <div className="rtls-panel-header">
            <div className="rtls-panel-title">RTLS Dashboard</div>
            <div className="rtls-panel-subtitle">{snap.room_name || 'No room loaded'}</div>
          </div>

          <div className="rtls-panel-body">

            {/* Load */}
            <div className="rtls-section">
              <div className="rtls-section-label">Load</div>
              <div className="rtls-section-body">
                <div className="rtls-load-row">
                  <button className="rtls-btn rtls-btn--primary" onClick={() => loadWorkspace()}>
                    Load Workspace
                  </button>
                  <button className="rtls-btn" onClick={loadFile}>Load File</button>
                </div>
                <div className="rtls-load-row">
                  <button className="rtls-btn" onClick={loadFolder}>Browse Folder</button>
                </div>
                <div className="rtls-section-label" style={{ paddingTop: 8, paddingBottom: 2 }}>Load Individually</div>
                <div className="rtls-load-row">
                  <button className="rtls-btn" style={{ flex: 1 }} onClick={loadRoomsFolder}>Rooms…</button>
                  <button className="rtls-btn" style={{ flex: 1 }} onClick={loadTagsFolder}>Tags…</button>
                  <button className="rtls-btn" style={{ flex: 1 }} onClick={loadSvgFolder}>SVG…</button>
                </div>
                <button
                  className="rtls-btn"
                  style={{ width: '100%', marginTop: 4 }}
                  onClick={() => canvasRef.current?.resetView()}
                >
                  Reset View
                </button>
              </div>
            </div>

            {/* Connectivity */}
            <div className="rtls-section">
              <div className="rtls-section-label">Connectivity</div>
              <div className="rtls-section-body">
                <div className="rtls-transport-tabs">
                  {(['Serial Port', 'Bluetooth (BLE)'] as const).map(m => (
                    <button
                      key={m}
                      className={`rtls-transport-tab${transportMode === m ? ' rtls-transport-tab--active' : ''}`}
                      onClick={() => setTransportMode(m)}
                    >
                      {m}
                    </button>
                  ))}
                </div>

                {transportMode === 'Serial Port' ? (
                  <>
                    <div className="rtls-port-row">
                      <select
                        className="rtls-port-select"
                        value={snap.selected_port || snap.auto_detect_port || ''}
                        onChange={e => setSnap(p => ({ ...p, selected_port: e.target.value }))}
                      >
                        {snap.ports.length === 0
                          ? <option value="">No ports found</option>
                          : snap.ports.map(p => <option key={p} value={p}>{p}</option>)
                        }
                      </select>
                    </div>
                    <div className="rtls-connect-row">
                      <button
                        className="rtls-btn rtls-btn--primary"
                        disabled={tStatus === 'connected'}
                        onClick={connect}
                      >
                        Connect
                      </button>
                      <button
                        className="rtls-btn rtls-btn--danger"
                        disabled={tStatus === 'idle'}
                        onClick={disconnect}
                      >
                        Disconnect
                      </button>
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 10, color: '#4d6a88', lineHeight: 1.5 }}>
                    BLE scanning is handled automatically by the ESP32-C6 dongle
                    connected via Serial Port.
                  </div>
                )}

                {/* Tag status table */}
                <div className="rtls-tag-table" style={{ marginTop: 8 }}>
                  {snap.tags.length === 0
                    ? <div style={{ fontSize: 10, color: '#3d5470' }}>No tags loaded. Load workspace first.</div>
                    : snap.tags.map((t, i) => {
                      const statusClass = t.status === 'Connected' ? 'connected'
                        : t.status.startsWith('Connect') ? 'connecting'
                        : 'disconnected'
                      return (
                        <div key={t.tag_id} className="rtls-tag-row">
                          <div className="rtls-tag-dot" style={{ background: tagColor(i) }} />
                          <div className="rtls-tag-id">{t.tag_id}</div>
                          <div className="rtls-tag-coords">
                            {t.position
                              ? `(${t.position.x.toFixed(2)}, ${t.position.y.toFixed(2)})`
                              : '(---, ---)'
                            }
                          </div>
                          <div className={`rtls-tag-status rtls-tag-status--${statusClass}`}>
                            {t.status}
                          </div>
                        </div>
                      )
                    })
                  }
                </div>
              </div>
            </div>

            {/* Coordinates */}
            {snap.tags.length > 0 && (
              <div className="rtls-section">
                <div className="rtls-section-label">Coordinates (ft)</div>
                <div className="rtls-section-body">
                  <div className="rtls-tag-table">
                    {snap.tags.map((t, i) => (
                      <div key={t.tag_id} className="rtls-tag-row">
                        <div className="rtls-tag-dot" style={{ background: tagColor(i) }} />
                        <div className="rtls-tag-id">{t.tag_id}</div>
                        <div className="rtls-tag-coords" style={{ gridColumn: '3 / 5' }}>
                          {t.position
                            ? `X: ${t.position.x.toFixed(3)}   Y: ${t.position.y.toFixed(3)}`
                            : '---'
                          }
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Tag Elevation */}
            <div className="rtls-section">
              <div className="rtls-section-label">Tag Elevation</div>
              <div className="rtls-section-body">
                <div className="rtls-elevation-row">
                  <div className="rtls-elevation-label">
                    {elevation.override ? 'Manual override (ft):' : 'Auto — |anchor_z − tag_z|'}
                  </div>
                  <label className="rtls-elevation-toggle">
                    <input
                      type="checkbox"
                      checked={elevation.override}
                      onChange={e => setElevation({ override: e.target.checked })}
                    />
                    <span>Override</span>
                  </label>
                </div>
                {elevation.override && (
                  <div className="rtls-elevation-row" style={{ marginTop: 6 }}>
                    <div className="rtls-elevation-label">Height (ft):</div>
                    <NumInput
                      value={elevation.value_ft}
                      min={0}
                      max={30}
                      onChange={v => setElevation({ value_ft: v })}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Smoothing Filter */}
            <div className="rtls-section">
              <div className="rtls-section-label">Smoothing Filter</div>
              <div className="rtls-section-body">
                <div className="rtls-filter-tabs">
                  {(['EMA', 'Rolling', 'Kalman'] as const).map(m => (
                    <button
                      key={m}
                      className={`rtls-filter-tab${filter.mode === m ? ' rtls-filter-tab--active' : ''}`}
                      onClick={() => setFilter({ mode: m })}
                    >
                      {m}
                    </button>
                  ))}
                </div>

                {filter.mode === 'EMA' && (
                  <div className="rtls-slider-row">
                    <div className="rtls-slider-header">
                      <span className="rtls-slider-label">α (0=smooth, 1=raw)</span>
                      <span className="rtls-slider-value">{filter.ema_alpha.toFixed(2)}</span>
                    </div>
                    <input
                      type="range" className="rtls-slider"
                      min={0.01} max={1.0} step={0.01}
                      value={filter.ema_alpha}
                      onChange={e => setFilter({ ema_alpha: parseFloat(e.target.value) })}
                    />
                  </div>
                )}

                {filter.mode === 'Rolling' && (
                  <div className="rtls-slider-row">
                    <div className="rtls-slider-header">
                      <span className="rtls-slider-label">Window (frames)</span>
                      <span className="rtls-slider-value">{filter.roll_n}</span>
                    </div>
                    <input
                      type="range" className="rtls-slider"
                      min={2} max={30} step={1}
                      value={filter.roll_n}
                      onChange={e => setFilter({ roll_n: parseInt(e.target.value) })}
                    />
                  </div>
                )}

                {filter.mode === 'Kalman' && (
                  <>
                    <div className="rtls-slider-row">
                      <div className="rtls-slider-header">
                        <span className="rtls-slider-label">Q (process noise)</span>
                        <span className="rtls-slider-value">{filter.kal_q.toFixed(2)}</span>
                      </div>
                      <input
                        type="range" className="rtls-slider"
                        min={0.01} max={2.0} step={0.01}
                        value={filter.kal_q}
                        onChange={e => setFilter({ kal_q: parseFloat(e.target.value) })}
                      />
                    </div>
                    <div className="rtls-slider-row">
                      <div className="rtls-slider-header">
                        <span className="rtls-slider-label">R (meas. noise)</span>
                        <span className="rtls-slider-value">{filter.kal_r.toFixed(1)}</span>
                      </div>
                      <input
                        type="range" className="rtls-slider"
                        min={0.1} max={10.0} step={0.1}
                        value={filter.kal_r}
                        onChange={e => setFilter({ kal_r: parseFloat(e.target.value) })}
                      />
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* CSV Logging */}
            <div className="rtls-section">
              <div className="rtls-section-label">CSV Logging</div>
              <div className="rtls-section-body">
                <button
                  className={`rtls-btn ${snap.csv.enabled ? 'rtls-btn--danger' : 'rtls-btn--primary'}`}
                  style={{ width: '100%' }}
                  onClick={toggleCsv}
                >
                  {snap.csv.enabled ? 'Stop Logging' : 'Start Logging'}
                </button>
                {snap.csv.enabled && snap.csv.path && (
                  <div className="rtls-csv-path">{snap.csv.path}</div>
                )}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  )
}

export default RTLSDashboard
