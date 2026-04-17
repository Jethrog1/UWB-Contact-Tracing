/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import RTLSDashboardCanvas, {
  BotAppearance,
  RTLSDashboardCanvasHandle,
  RTLSTagState,
  VisualSettings,
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
  room_polygon_ft: { x: number; y: number }[]
  room_name: string
  reference_anchor_id: string
  filter: FilterState
  elevation: ElevationState
  csv: CSVState
}

const MAX_BOTS = 24

const DEFAULT_VISUAL: VisualSettings = {
  heatMap: false,
  heatGradientRate: 0.3,
  heatRange: 5.0,
  heatPeak: 70,
  botAppearance: 'dots',
  bots: false,
  botSpeed: 2.0,
  botAccel: 1.5,
  botPause: 1.0,
}

interface RTLSDashboardProps {
  workspaceId: string
  workspaceName: string
}

// ── Slider + typeable input (slider moves as you type; Enter/blur confirms) ───
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
  const fmt = (n: number) => n.toFixed(decimals)
  const [text, setText] = useState(() => fmt(value))
  const focused = useRef(false)

  useEffect(() => { if (!focused.current) setText(fmt(value)) }, [value]) // eslint-disable-line react-hooks/exhaustive-deps

  const clamp = (n: number) => Math.max(min, Math.min(max, n))
  const parsed = parseFloat(text)
  const sliderVal = isFinite(parsed) ? clamp(parsed) : value

  return (
    <div className="rtls-slider-row">
      <div className="rtls-slider-header">
        <span className="rtls-slider-label">{label}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <input
            type="text"
            className="rtls-slider-text-input"
            value={text}
            onFocus={() => { focused.current = true }}
            onChange={e => {
              setText(e.target.value)
              const v = parseFloat(e.target.value)
              if (isFinite(v)) onChange(clamp(v))   // slider tracks immediately
            }}
            onBlur={() => {
              focused.current = false
              const v = parseFloat(text)
              const c = isFinite(v) ? clamp(v) : value
              setText(fmt(c)); onChange(c)
            }}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                const v = parseFloat(text)
                const c = isFinite(v) ? clamp(v) : value
                setText(fmt(c)); onChange(c)
                  ; (e.target as HTMLInputElement).blur()
              }
            }}
          />
          <span className="rtls-slider-unit">{unit}</span>
        </div>
      </div>
      <input
        type="range" className="rtls-range"
        min={min} max={max} step={step}
        value={sliderVal}
        onChange={e => {
          const v = parseFloat(e.target.value)
          setText(fmt(v)); onChange(v)
        }}
      />
    </div>
  )
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
  room_polygon_ft: [],
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
  const [visualSettings, setVisualSettings] = useState<VisualSettings>(DEFAULT_VISUAL)
  const [botCount, setBotCount] = useState(0)
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

  // ── View commands (refresh / zoom from TabStrip) ───────────────────────────
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { cmd: string; workspaceId: string }
      if (detail.workspaceId !== workspaceId) return
      if (detail.cmd === 'refresh') loadWorkspace()

      const canvas = canvasRef.current
      if (!canvas) return
      if (detail.cmd === 'zoom_in') canvas.zoomIn()
      else if (detail.cmd === 'zoom_out') canvas.zoomOut()
      else if (detail.cmd === 'zoom_reset') canvas.resetView()
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
  const transportKind: 'ok' | 'error' =
    (tStatus === 'connected' && !snap.transport_detail.toLowerCase().includes('disconnect')) ? 'ok'
      : 'error'

  const { filter, elevation } = snap

  // Reference anchor offset
  let refX = 0
  let refY = 0
  if (snap.reference_anchor_id && snap.anchors[snap.reference_anchor_id]) {
    [refX, refY] = snap.anchors[snap.reference_anchor_id]
  }

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
              roomPolygon={snap.room_polygon_ft}
              svgContent={svgContent}
              referenceAnchorId={snap.reference_anchor_id}
              visualSettings={visualSettings}
            />
          )}
        </div>

        {/* ── Status toast ── */}
        {statusMsg && (
          <div className={`rtls-status rtls-status--${statusMsg.kind}`}>
            {statusMsg.text}
          </div>
        )}

        {/* ── Right panel ── */}
        <div className="rtls-right-panel">
          <div className="rtls-panel-header">
            <div>
              <div className="rtls-panel-title">RTLS Dashboard</div>
              <div className="rtls-panel-subtitle">{snap.room_name || 'No room loaded'}</div>
            </div>
          </div>

          <div className="rtls-panel-body">

            {/* Load */}
            <div className="rtls-section">
              <div className="rtls-section-title">Load</div>
              <button className="rtls-btn rtls-btn--primary rtls-btn--full" onClick={loadFolder}>
                Load Workspace
              </button>
              <div className="rtls-section-title" style={{ marginTop: 8 }}>Load Individually</div>
              <div className="rtls-load-row">
                <button className="rtls-btn" style={{ flex: 1 }} onClick={loadRoomsFolder}>Rooms…</button>
                <button className="rtls-btn" style={{ flex: 1 }} onClick={loadTagsFolder}>Tags…</button>
                <button className="rtls-btn" style={{ flex: 1 }} onClick={loadSvgFolder}>SVG…</button>
              </div>
            </div>

            {/* Connectivity */}
            <div className="rtls-section">
              <div className="rtls-section-title">Connectivity</div>
              <div className="rtls-transport-tabs">
                <button className={`rtls-transport-tab${transportMode === 'Bluetooth (BLE)' ? ' active' : ''}`} onClick={() => setTransportMode('Bluetooth (BLE)')}>Bluetooth (BLE)</button>
                <button className={`rtls-transport-tab${transportMode === 'Serial Port' ? ' active' : ''}`} onClick={() => setTransportMode('Serial Port')}>Serial Port</button>
              </div>
              {transportMode === 'Serial Port' && (
                <select className="rtls-input" value={snap.selected_port || snap.auto_detect_port || ''} onChange={e => setSnap(p => ({ ...p, selected_port: e.target.value }))}>
                  <option value="">Select a COM port</option>
                  {snap.ports.map(port => <option key={port} value={port}>{port}</option>)}
                </select>
              )}
              <div className="rtls-runtime-note">{snap.transport_detail}</div>
              {snap.tags.length > 0 ? (
                <div className="rtls-ble-rows">
                  {snap.tags.map((tag, i) => {
                    const s = tag.status.toLowerCase()
                    const statusColor = s.includes('connected') && !s.includes('disconnect') ? '#42d17e'
                      : s.includes('connecting') ? '#ffb11f' : '#ff5b4d'
                    return (
                      <div key={tag.tag_id} className="rtls-ble-row">
                        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span className="rtls-tag-dot" style={{ background: tagColor(i) }} />
                          {tag.tag_id}
                        </span>
                        <span style={{ color: statusColor, fontWeight: 600 }}>{tag.status}</span>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="rtls-runtime-note">No profiled tags available yet.</div>
              )}
              <div className="rtls-connect-row">
                <button className="rtls-btn rtls-btn--primary" style={{ flex: 1 }} disabled={tStatus === 'connected'} onClick={connect}>Connect</button>
                <button className="rtls-btn" style={{ flex: 1 }} disabled={tStatus === 'idle'} onClick={disconnect}>Disconnect</button>
              </div>
            </div>

            {/* Coordinates */}
            {snap.tags.length > 0 && (
              <div className="rtls-section">
                <div className="rtls-section-title">Coordinates (ft)</div>
                <div className="rtls-ble-rows">
                  {snap.tags.map((t, i) => (
                    <div key={t.tag_id} className="rtls-ble-row">
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span className="rtls-tag-dot" style={{ background: tagColor(i) }} />
                        {t.tag_id}
                      </span>
                      <span>
                        {t.position
                          ? `(${(t.position.x - refX).toFixed(2)}, ${(t.position.y - refY).toFixed(2)})`
                          : '(---, ---)'
                        }
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tag Elevation */}
            <div className="rtls-section">
              <div className="rtls-section-title">Tag Elevation</div>
              <label className="rtls-check">
                <input
                  type="checkbox"
                  checked={elevation.override}
                  onChange={e => setElevation({ override: e.target.checked })}
                />
                Manual Z-Height Override
              </label>
              {elevation.override && (
                <div className="rtls-elevation-row">
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

            {/* Smoothing Filter */}
            <div className="rtls-section">
              <div className="rtls-section-title">Smoothing Filter</div>
              <div className="rtls-transport-tabs">
                {(['EMA', 'Rolling', 'Kalman'] as const).map(m => (
                  <button
                    key={m}
                    className={`rtls-filter-tab${filter.mode === m ? ' active' : ''}`}
                    onClick={() => setFilter({ mode: m })}
                  >
                    {m}
                  </button>
                ))}
              </div>

              <div className="rtls-slider-row">
                <div className="rtls-slider-header">
                  <span className="rtls-slider-label">EMA α</span>
                  <span className="rtls-slider-value">{filter.ema_alpha.toFixed(2)}</span>
                </div>
                <input
                  type="range" className="rtls-range"
                  min={0.01} max={0.99} step={0.01}
                  value={filter.ema_alpha}
                  onChange={e => setFilter({ ema_alpha: parseFloat(e.target.value) })}
                />
              </div>

              <div className="rtls-slider-row">
                <div className="rtls-slider-header">
                  <span className="rtls-slider-label">Rolling N</span>
                  <span className="rtls-slider-value">{filter.roll_n}</span>
                </div>
                <input
                  type="range" className="rtls-range"
                  min={2} max={30} step={1}
                  value={filter.roll_n}
                  onChange={e => setFilter({ roll_n: parseInt(e.target.value) })}
                />
              </div>

              <div className="rtls-slider-row">
                <div className="rtls-slider-header">
                  <span className="rtls-slider-label">Kalman Q</span>
                  <span className="rtls-slider-value">{filter.kal_q.toFixed(3)}</span>
                </div>
                <input
                  type="range" className="rtls-range"
                  min={0.001} max={1} step={0.001}
                  value={filter.kal_q}
                  onChange={e => setFilter({ kal_q: parseFloat(e.target.value) })}
                />
              </div>

              <div className="rtls-slider-row">
                <div className="rtls-slider-header">
                  <span className="rtls-slider-label">Kalman R</span>
                  <span className="rtls-slider-value">{filter.kal_r.toFixed(1)}</span>
                </div>
                <input
                  type="range" className="rtls-range"
                  min={0.1} max={20} step={0.1}
                  value={filter.kal_r}
                  onChange={e => setFilter({ kal_r: parseFloat(e.target.value) })}
                />
              </div>
            </div>

            {/* CSV Logging */}
            <div className="rtls-section">
              <div className="rtls-section-title">CSV Logging</div>
              <button
                className={`rtls-btn rtls-btn--full ${snap.csv.enabled ? 'rtls-btn--danger' : 'rtls-btn--primary'}`}
                onClick={toggleCsv}
              >
                {snap.csv.enabled ? 'Stop Logging' : 'Start Logging'}
              </button>
              {snap.csv.enabled && snap.csv.path && (
                <div className="rtls-csv-path">{snap.csv.path}</div>
              )}
            </div>

            {/* Visual Settings */}
            <div className="rtls-section">
              <div className="rtls-section-title">Visual Settings</div>

              {/* ── Heat Map ── */}
              <div className="rtls-toggle-row">
                <span className="rtls-toggle-label">Heat Map</span>
                <label className="rtls-toggle">
                  <input type="checkbox" checked={visualSettings.heatMap}
                    onChange={e => setVisualSettings(p => ({ ...p, heatMap: e.target.checked }))} />
                  <span className="rtls-toggle-slider" />
                </label>
              </div>

              <SliderInput
                label="Exposure Rate"
                value={visualSettings.heatGradientRate}
                min={0.05} max={5.0} step={0.05} decimals={2} unit="s/step"
                onChange={v => setVisualSettings(p => ({ ...p, heatGradientRate: v }))}
              />
              <SliderInput
                label="Range"
                value={visualSettings.heatRange}
                min={0.5} max={30} step={0.5} decimals={1} unit="ft"
                onChange={v => setVisualSettings(p => ({ ...p, heatRange: v }))}
              />

              <div className="rtls-slider-row">
                <div className="rtls-slider-header">
                  <span className="rtls-slider-label">Peak Color</span>
                  <span className="rtls-slider-value">{visualSettings.heatPeak}</span>
                </div>
                <input type="range" className="rtls-range" min={1} max={100} step={1}
                  value={visualSettings.heatPeak}
                  onChange={e => setVisualSettings(p => ({ ...p, heatPeak: parseInt(e.target.value) }))} />
              </div>

              {/* ── Bot Appearance (3-option segmented control) ── */}
              <div className="rtls-section-title" style={{ marginTop: 10 }}>Bot Appearance</div>
              <div className="rtls-transport-tabs">
                {(['invisible', 'dots', 'human'] as BotAppearance[]).map(opt => (
                  <button
                    key={opt}
                    className={`rtls-transport-tab${visualSettings.botAppearance === opt ? ' active' : ''}`}
                    onClick={() => setVisualSettings(p => ({ ...p, botAppearance: opt }))}
                  >
                    {opt === 'invisible' ? 'Invisible' : opt === 'dots' ? 'Normal' : 'Human'}
                  </button>
                ))}
              </div>

              {/* ── Bots ── */}
              <div className="rtls-toggle-row" style={{ marginTop: 6 }}>
                <span className="rtls-toggle-label">Bots</span>
                <label className="rtls-toggle">
                  <input type="checkbox" checked={visualSettings.bots}
                    onChange={e => {
                      const enabled = e.target.checked
                      setVisualSettings(p => ({ ...p, bots: enabled }))
                      if (enabled && canvasRef.current && canvasRef.current.getBotCount() === 0) {
                        canvasRef.current.seedBots(6); setBotCount(6)
                      }
                    }} />
                  <span className="rtls-toggle-slider" />
                </label>
              </div>

              <button
                className="rtls-btn rtls-btn--full"
                style={{ marginTop: 4 }}
                disabled={!visualSettings.bots || botCount >= MAX_BOTS}
                onClick={() => { if (!canvasRef.current) return; setBotCount(canvasRef.current.addBot()) }}
              >
                Add Random{botCount > 0 ? ` (${botCount}/${MAX_BOTS})` : ''}
              </button>

              <SliderInput label="Speed" value={visualSettings.botSpeed}
                min={0.5} max={8} step={0.1} decimals={1} unit="ft/s"
                onChange={v => setVisualSettings(p => ({ ...p, botSpeed: v }))} />
              <SliderInput label="Acceleration" value={visualSettings.botAccel}
                min={0.1} max={5} step={0.1} decimals={1} unit="ft/s²"
                onChange={v => setVisualSettings(p => ({ ...p, botAccel: v }))} />
              <SliderInput label="Pause" value={visualSettings.botPause}
                min={0.2} max={3.0} step={0.1} decimals={1} unit="s"
                onChange={v => setVisualSettings(p => ({ ...p, botPause: v }))} />
            </div>

          </div>
        </div>
      </div>
    </div>
  )
}

export default RTLSDashboard
