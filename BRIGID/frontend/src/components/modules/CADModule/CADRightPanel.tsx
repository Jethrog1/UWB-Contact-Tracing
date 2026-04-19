import React, { useEffect, useState } from 'react'
import { Tooltip } from '@blueprintjs/core'
import { CADCommand, CADState, ToolMode } from './types'
import './CADRightPanel.css'

const API = 'http://localhost:8765'

interface Props {
  state: CADState | null
  onCommand: (cmd: CADCommand) => void
  status: 'connecting' | 'connected' | 'disconnected' | 'error'
  workspaceId?: string
  workspaceName?: string
}

const TOOLS: { mode: ToolMode; icon: string; label: string; shortcut: string }[] = [
  { mode: 'cursor', icon: '↖', label: 'Select / Move', shortcut: 'V' },
  { mode: 'line', icon: '╱', label: 'Draw Line', shortcut: 'L' },
  { mode: 'vertex', icon: '◦', label: 'Vertex Mode', shortcut: 'N' },
  { mode: 'dim', icon: '↔', label: 'Dimension Tool', shortcut: 'D' },
]

const CADRightPanel: React.FC<Props> = ({ state, onCommand, status, workspaceId, workspaceName }) => {
  const [iobusy, setIoBusy] = useState(false)
  const [paths, setPaths] = useState<{ svg: string; pdf: string } | null>(null)
  const [downloadsPath, setDownloadsPath] = useState<string | null>(null)
  const tool = state?.tool_mode ?? 'cursor'

  const getPaths = window.api?.getPaths
  const openFile = window.api?.openFile
  const saveFile = window.api?.saveFile

  useEffect(() => {
    let cancelled = false

    if (workspaceId && workspaceName) {
      // Fetch workspace-specific svg/ and pdf/ paths from the backend
      fetch(`${API}/api/workspace/paths/${encodeURIComponent(workspaceId)}?workspace_name=${encodeURIComponent(workspaceName)}`)
        .then(r => r.json())
        .then(data => {
          if (!cancelled && data.success) setPaths({ svg: data.svg, pdf: data.pdf })
        })
        .catch(() => { if (!cancelled) setPaths(null) })
    } else if (getPaths) {
      getPaths()
        .then(nextPaths => { if (!cancelled) setPaths(nextPaths) })
        .catch(() => { if (!cancelled) setPaths(null) })
    }

    if (getPaths) {
      getPaths()
        .then(nextPaths => { if (!cancelled) setDownloadsPath(nextPaths.downloads) })
        .catch(() => { if (!cancelled) setDownloadsPath(null) })
    }

    return () => { cancelled = true }
  }, [workspaceId, workspaceName, getPaths])

  const handleOpen = async () => {
    if (!openFile || iobusy) return
    setIoBusy(true)
    try {
      const result = await openFile(
        [{ name: 'CAD Designs', extensions: ['svg'] }],
        paths?.svg,
      )
      if (!result.canceled && result.filePaths.length > 0) {
        onCommand({ type: 'open_cad', filepath: result.filePaths[0] })
      }
    } finally {
      setIoBusy(false)
    }
  }

  const handleImport = async () => {
    if (!openFile || iobusy) return
    setIoBusy(true)
    try {
      const result = await openFile(
        [
          { name: 'Floor Plans', extensions: ['pdf', 'svg', 'png', 'jpg', 'jpeg'] },
          { name: 'PDF Files', extensions: ['pdf'] },
          { name: 'SVG Files', extensions: ['svg'] },
          { name: 'Images', extensions: ['png', 'jpg', 'jpeg'] },
        ],
        downloadsPath ?? undefined,
      )
      if (!result.canceled && result.filePaths.length > 0) {
        onCommand({ type: 'import_file', filepath: result.filePaths[0] })
      }
    } finally {
      setIoBusy(false)
    }
  }

  const handleSaveSVG = async () => {
    if (!saveFile || iobusy) return
    setIoBusy(true)
    try {
      const defaultPath = paths?.svg ? `${paths.svg}\\floor-plan.svg` : 'floor-plan.svg'
      const result = await saveFile(
        [{ name: 'SVG Files', extensions: ['svg'] }],
        defaultPath,
      )
      if (!result.canceled && result.filePath) {
        onCommand({ type: 'export_svg', filepath: result.filePath })
      }
    } finally {
      setIoBusy(false)
    }
  }

  const handleSavePDF = async () => {
    if (!saveFile || iobusy) return
    setIoBusy(true)
    try {
      const defaultPath = paths?.pdf ? `${paths.pdf}\\floor-plan.pdf` : 'floor-plan.pdf'
      const result = await saveFile(
        [{ name: 'PDF Files', extensions: ['pdf'] }],
        defaultPath,
      )
      if (!result.canceled && result.filePath) {
        onCommand({ type: 'export_pdf', filepath: result.filePath })
      }
    } finally {
      setIoBusy(false)
    }
  }

  const flags = {
    manipulate_line: state?.manipulate_line ?? false,
    snap_axis: state?.snap_axis ?? false,
    line_match: state?.line_match ?? false,
    disable_vpoint: state?.disable_vpoint ?? false,
  }

  const setTool = (nextTool: ToolMode) => onCommand({ type: 'tool_change', tool: nextTool })
  const toggle = (flag: keyof typeof flags) => onCommand({ type: 'toggle_flag', flag, value: !flags[flag] })

  return (
    <aside className="cad-right-panel">
      <div className={`crp-status crp-status--${status}`}>
        <span className="crp-status-dot" title={status} />
        <span className="crp-status-label">
          {status === 'connected' ? 'Connected' : status === 'connecting' ? 'Connecting...' : status === 'error' ? 'Error' : 'Offline'}
        </span>
      </div>

      <div className="crp-section">
        <div className="crp-section-label">Tools</div>
        <div className="crp-tool-grid">
          {TOOLS.map((entry) => (
            <Tooltip key={entry.mode} content={`${entry.label} · ${entry.shortcut}`} placement="left">
              <button
                className={`crp-tool-btn${tool === entry.mode ? ' crp-tool-btn--active' : ''}`}
                onClick={() => setTool(entry.mode)}
              >
                <span className="crp-tool-label">{entry.label}</span>
              </button>
            </Tooltip>
          ))}
        </div>
      </div>

      <div className="crp-section">
        <div className="crp-section-label">Edit</div>
        <div className="crp-tool-grid">
          <Tooltip content="Copy the selected geometry to the clipboard · Ctrl+C" placement="left">
            <button className="crp-tool-btn" onClick={() => onCommand({ type: 'copy' })}>
              <span className="crp-tool-label">Copy</span>
            </button>
          </Tooltip>
          <Tooltip content="Paste clipboard contents at the cursor · Ctrl+V" placement="left">
            <button className="crp-tool-btn" onClick={() => onCommand({ type: 'paste' })}>
              <span className="crp-tool-label">Paste</span>
            </button>
          </Tooltip>
          <Tooltip content="Delete the selected geometry · Del" placement="left">
            <button className="crp-tool-btn crp-tool-btn--danger" onClick={() => onCommand({ type: 'delete' })}>
              <span className="crp-tool-label">Delete</span>
            </button>
          </Tooltip>
          <Tooltip content="Cancel the current tool action · Esc" placement="left">
            <button className="crp-tool-btn" onClick={() => onCommand({ type: 'escape' })}>
              <span className="crp-tool-label">Escape</span>
            </button>
          </Tooltip>
        </div>
      </div>

      <div className="crp-section">
        <div className="crp-section-label">Advanced</div>
        <div className="crp-tool-grid">
          <Tooltip content="Rotate the selected geometry around a chosen pivot" placement="left">
            <button className="crp-tool-btn" onClick={() => onCommand({ type: 'context_action', action: 'rotate' })}>
              <span className="crp-tool-label">Rotate</span>
            </button>
          </Tooltip>
          <Tooltip content="Trim a line back to the nearest intersection" placement="left">
            <button className="crp-tool-btn crp-tool-btn--trim" onClick={() => onCommand({ type: 'context_action', action: 'trim' })}>
              <span className="crp-tool-label">Trim</span>
            </button>
          </Tooltip>
        </div>
      </div>

      <div className="crp-section">
        <div className="crp-section-label">Behaviour</div>
        <ToggleRow label="Manipulate Line" active={flags.manipulate_line} onToggle={() => toggle('manipulate_line')} />
        <ToggleRow label="Axis Snap" active={flags.snap_axis} onToggle={() => toggle('snap_axis')} />
        <ToggleRow label="Line Match" active={flags.line_match} onToggle={() => toggle('line_match')} />
        <ToggleRow label="Hide V-Points" active={flags.disable_vpoint} onToggle={() => toggle('disable_vpoint')} />
      </div>

      <div className="crp-section">
        <div className="crp-section-label">Angle Snap (deg)</div>
        <div className="crp-angle-grid">
          {(state?.angle_snap_values ?? ['', '']).slice(0, 2).map((value, index) => (
            <input
              key={index}
              className="crp-angle-input"
              value={value}
              onChange={(e) => onCommand({ type: 'angle_snap_set', index, value: e.target.value })}
            />
          ))}
        </div>
      </div>

      <div className="crp-section crp-section--io">
        <div className="crp-section-label">File</div>
        <Tooltip content="Open a previously saved CAD design (SVG)" placement="left">
          <button className="crp-io-btn" onClick={handleOpen} disabled={iobusy || !openFile}>
            Open
          </button>
        </Tooltip>
        <Tooltip content="Import an external floor plan (PDF, SVG, PNG)" placement="left">
          <button className="crp-io-btn" onClick={handleImport} disabled={iobusy || !openFile}>
            Import
          </button>
        </Tooltip>
        <Tooltip content="Save design to BRIGID/svg/" placement="left">
          <button className="crp-io-btn" onClick={handleSaveSVG} disabled={iobusy || !state?.lines.length || !saveFile}>
            Save SVG
          </button>
        </Tooltip>
        <Tooltip content="Export print-ready PDF to BRIGID/pdf/" placement="left">
          <button className="crp-io-btn" onClick={handleSavePDF} disabled={iobusy || !state?.lines.length || !saveFile}>
            Save PDF
          </button>
        </Tooltip>
      </div>
    </aside>
  )
}

const ToggleRow: React.FC<{ label: string; active: boolean; onToggle: () => void }> = ({ label, active, onToggle }) => (
  <div className={`crp-toggle-row${active ? ' crp-toggle-row--active' : ''}`} onClick={onToggle}>
    <span className="crp-toggle-label">{label}</span>
    <div className={`crp-toggle-pill${active ? ' crp-toggle-pill--on' : ''}`}>
      <div className="crp-toggle-thumb" />
    </div>
  </div>
)

export default CADRightPanel
