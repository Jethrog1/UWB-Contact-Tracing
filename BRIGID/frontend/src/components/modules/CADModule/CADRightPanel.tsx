// ── CAD Right Panel ───────────────────────────────────────────────
import React from 'react'
import { Icon, Tooltip } from '@blueprintjs/core'
import { CADState, CADCommand, ToolMode } from './types'
import './CADRightPanel.css'

interface Props {
  state: CADState | null
  onCommand: (cmd: CADCommand) => void
  status: 'connecting' | 'connected' | 'disconnected' | 'error'
}

// ── Tool definitions ──────────────────────────────────────────────
const TOOLS: { mode: ToolMode; icon: string; label: string; shortcut: string }[] = [
  { mode: 'cursor', icon: 'cursor',     label: 'Select / Move',  shortcut: 'V' },
  { mode: 'line',   icon: 'slash',      label: 'Draw Line',      shortcut: 'L' },
  { mode: 'vertex', icon: 'dot',        label: 'Vertex Mode',    shortcut: 'N' },
  { mode: 'dim',    icon: 'arrows-horizontal', label: 'Dimension Tool', shortcut: 'D' },
]

const CADRightPanel: React.FC<Props> = ({ state, onCommand, status }) => {
  const tool    = state?.tool_mode ?? 'cursor'
  const flags   = {
    manipulate_line: state?.manipulate_line ?? false,
    snap_axis:       state?.snap_axis       ?? false,
    line_match:      state?.line_match      ?? false,
    disable_vpoint:  state?.disable_vpoint  ?? false,
  }

  const setTool = (t: ToolMode) => onCommand({ type: 'tool_change', tool: t })
  const toggle  = (f: keyof typeof flags) =>
    onCommand({ type: 'toggle_flag', flag: f, value: !flags[f] })

  return (
    <aside className="cad-right-panel">
      {/* ── Connection badge ─────────────────────────────────── */}
      <div className={`crp-status crp-status--${status}`}>
        <span className="crp-status-dot" />
        <span className="crp-status-label">
          {status === 'connected'    ? 'Backend connected'
         : status === 'connecting'  ? 'Connecting…'
         : status === 'error'       ? 'Connection error'
                                    : 'Disconnected'}
        </span>
      </div>

      {/* ── Tools ────────────────────────────────────────────── */}
      <Section title="Tools">
        <div className="crp-tool-grid">
          {TOOLS.map(t => (
            <Tooltip key={t.mode} content={`${t.label} (${t.shortcut})`} placement="left">
              <button
                className={`crp-tool-btn${tool === t.mode ? ' crp-tool-btn--active' : ''}`}
                onClick={() => setTool(t.mode)}
              >
                <Icon icon={t.icon as any} size={14} />
                <span>{t.label}</span>
              </button>
            </Tooltip>
          ))}
        </div>
      </Section>

      {/* ── Edit actions ─────────────────────────────────────── */}
      <Section title="Edit">
        <div className="crp-btn-row">
          <ActionBtn icon="undo" label="Undo" shortcut="Ctrl+Z" onClick={() => onCommand({ type: 'undo' })} />
          <ActionBtn icon="redo" label="Redo" shortcut="Ctrl+Y" onClick={() => onCommand({ type: 'redo' })} />
        </div>
        <div className="crp-btn-row">
          <ActionBtn icon="duplicate" label="Copy"   shortcut="Ctrl+C" onClick={() => onCommand({ type: 'copy' })} />
          <ActionBtn icon="clipboard" label="Paste"  shortcut="Ctrl+V" onClick={() => onCommand({ type: 'paste' })} />
        </div>
        <div className="crp-btn-row">
          <ActionBtn icon="trash" label="Delete" shortcut="Del" onClick={() => onCommand({ type: 'delete' })} danger />
          <ActionBtn icon="cross" label="Escape" shortcut="Esc" onClick={() => onCommand({ type: 'escape' })} />
        </div>
      </Section>

      {/* ── View / Zoom ──────────────────────────────────────── */}
      <Section title="View">
        <div className="crp-btn-row">
          <ActionBtn icon="zoom-in"  label="Zoom In"    shortcut="+" onClick={() => onCommand({ type: 'zoom_in' })} />
          <ActionBtn icon="zoom-out" label="Zoom Out"   shortcut="-" onClick={() => onCommand({ type: 'zoom_out' })} />
        </div>
        <ActionBtn icon="zoom-to-fit" label="Reset View" shortcut="0" onClick={() => onCommand({ type: 'zoom_reset' })} wide />
      </Section>

      {/* ── Feature flags ────────────────────────────────────── */}
      <Section title="Snap &amp; Behaviour">
        <ToggleRow
          label="Manipulate Line"
          active={flags.manipulate_line}
          onToggle={() => toggle('manipulate_line')}
        />
        <ToggleRow
          label="Axis Snap"
          active={flags.snap_axis}
          onToggle={() => toggle('snap_axis')}
        />
        <ToggleRow
          label="Line Match"
          active={flags.line_match}
          onToggle={() => toggle('line_match')}
        />
        <ToggleRow
          label="Disable Vanishing Point"
          active={flags.disable_vpoint}
          onToggle={() => toggle('disable_vpoint')}
        />
      </Section>

      {/* ── Angle snaps ──────────────────────────────────────── */}
      <Section title="Angle Snap Values">
        <div className="crp-angle-grid">
          {(state?.angle_snap_values ?? ['0', '45', '90', '135']).map((val, i) => (
            <input
              key={i}
              className="crp-angle-input"
              value={val}
              onChange={e => onCommand({ type: 'angle_snap_set', index: i, value: e.target.value })}
              placeholder={`Angle ${i + 1}`}
            />
          ))}
        </div>
      </Section>

      {/* ── Geometry stats ───────────────────────────────────── */}
      <Section title="Geometry">
        <div className="crp-stats">
          <StatRow label="Lines"      value={state?.lines.length ?? 0} />
          <StatRow label="Fixed Dims" value={state ? Object.keys(state.fixed_lengths).length : 0} />
          <StatRow label="Distances"  value={state?.distance_constraints.length ?? 0} />
          <StatRow label="Angles"     value={state?.angle_constraints.length ?? 0} />
        </div>
        {state?.selected_id && (
          <div className="crp-selection-info">
            <span className="crp-label">Selected</span>
            <span className="crp-value">{state.selected_id.slice(0, 8)}</span>
          </div>
        )}
        {(state?.multi_selected_ids.length ?? 0) > 1 && (
          <div className="crp-selection-info">
            <span className="crp-label">Multi</span>
            <span className="crp-value">{state!.multi_selected_ids.length} lines</span>
          </div>
        )}
      </Section>

      {/* ── Error banner ─────────────────────────────────────── */}
      {state?.last_error && (
        <div className="crp-error">
          <Icon icon="warning-sign" size={12} />
          <span>{state.last_error}</span>
        </div>
      )}
    </aside>
  )
}

// ── Sub-components ────────────────────────────────────────────────
const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="crp-section">
    <div className="crp-section-title">{title}</div>
    <div className="crp-section-body">{children}</div>
  </div>
)

const ActionBtn: React.FC<{
  icon: string; label: string; shortcut: string
  onClick: () => void; danger?: boolean; wide?: boolean
}> = ({ icon, label, shortcut, onClick, danger, wide }) => (
  <Tooltip content={`${label} (${shortcut})`} placement="left">
    <button
      className={`crp-action-btn${danger ? ' crp-action-btn--danger' : ''}${wide ? ' crp-action-btn--wide' : ''}`}
      onClick={onClick}
    >
      <Icon icon={icon as any} size={12} />
      <span>{label}</span>
    </button>
  </Tooltip>
)

const ToggleRow: React.FC<{ label: string; active: boolean; onToggle: () => void }> = ({ label, active, onToggle }) => (
  <div className={`crp-toggle-row${active ? ' crp-toggle-row--active' : ''}`} onClick={onToggle}>
    <span className="crp-toggle-label">{label}</span>
    <div className={`crp-toggle-pill${active ? ' crp-toggle-pill--on' : ''}`}>
      <div className="crp-toggle-thumb" />
    </div>
  </div>
)

const StatRow: React.FC<{ label: string; value: number }> = ({ label, value }) => (
  <div className="crp-stat-row">
    <span className="crp-label">{label}</span>
    <span className="crp-value">{value}</span>
  </div>
)

export default CADRightPanel
