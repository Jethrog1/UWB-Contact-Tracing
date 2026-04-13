import React from 'react'
import { Icon, Tooltip } from '@blueprintjs/core'
import { CADCommand, CADState, ToolMode } from './types'
import './CADRightPanel.css'

interface Props {
  state: CADState | null
  onCommand: (cmd: CADCommand) => void
  status: 'connecting' | 'connected' | 'disconnected' | 'error'
}

const TOOLS: { mode: ToolMode; icon: string; label: string; shortcut: string }[] = [
  { mode: 'cursor', icon: 'cursor', label: 'Select / Move', shortcut: 'V' },
  { mode: 'line', icon: 'slash', label: 'Draw Line', shortcut: 'L' },
  { mode: 'vertex', icon: 'dot', label: 'Vertex Mode', shortcut: 'N' },
  { mode: 'dim', icon: 'arrows-horizontal', label: 'Dimension Tool', shortcut: 'D' },
]

const CADRightPanel: React.FC<Props> = ({ state, onCommand, status }) => {
  const tool = state?.tool_mode ?? 'cursor'
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
        <span className="crp-status-dot" />
        <span className="crp-status-label">
          {status === 'connected'
            ? 'Backend connected'
            : status === 'connecting'
              ? 'Connecting...'
              : status === 'error'
                ? 'Connection error'
                : 'Disconnected'}
        </span>
      </div>

      <Section title="Tools">
        <div className="crp-tool-grid">
          {TOOLS.map(entry => (
            <Tooltip key={entry.mode} content={`${entry.label} (${entry.shortcut})`} placement="left">
              <button
                className={`crp-tool-btn${tool === entry.mode ? ' crp-tool-btn--active' : ''}`}
                onClick={() => setTool(entry.mode)}
              >
                <Icon icon={entry.icon as any} size={14} />
                <span>{entry.label}</span>
              </button>
            </Tooltip>
          ))}
        </div>
      </Section>

      <Section title="Edit">
        <div className="crp-btn-row">
          <ActionBtn icon="undo" label="Undo" shortcut="Ctrl+Z" onClick={() => onCommand({ type: 'undo' })} />
          <ActionBtn icon="redo" label="Redo" shortcut="Ctrl+Y / Ctrl+Shift+Z" onClick={() => onCommand({ type: 'redo' })} />
        </div>
        <div className="crp-btn-row">
          <ActionBtn icon="duplicate" label="Copy" shortcut="Ctrl+C" onClick={() => onCommand({ type: 'copy' })} />
          <ActionBtn icon="clipboard" label="Paste" shortcut="Ctrl+V" onClick={() => onCommand({ type: 'paste' })} />
        </div>
        <div className="crp-btn-row">
          <ActionBtn icon="trash" label="Delete" shortcut="Del" onClick={() => onCommand({ type: 'delete' })} danger />
          <ActionBtn icon="cross" label="Escape" shortcut="Esc" onClick={() => onCommand({ type: 'escape' })} />
        </div>
      </Section>

      <Section title="View">
        <div className="crp-btn-row">
          <ActionBtn icon="zoom-in" label="Zoom In" shortcut="+" onClick={() => onCommand({ type: 'zoom_in' })} />
          <ActionBtn icon="zoom-out" label="Zoom Out" shortcut="-" onClick={() => onCommand({ type: 'zoom_out' })} />
        </div>
        <ActionBtn icon="zoom-to-fit" label="Reset View" shortcut="0" onClick={() => onCommand({ type: 'zoom_reset' })} wide />
      </Section>

      <Section title="Advanced Tools">
        <div className="crp-btn-row">
          <ActionBtn icon="repeat" label="Rotate" shortcut="Panel / menu" onClick={() => onCommand({ type: 'context_action', action: 'rotate' })} />
          <ActionBtn icon="cut" label="Trim" shortcut="Panel / menu" onClick={() => onCommand({ type: 'context_action', action: 'trim' })} />
        </div>
      </Section>

      <Section title="Snap & Behaviour">
        <ToggleRow label="Manipulate Line" active={flags.manipulate_line} onToggle={() => toggle('manipulate_line')} />
        <ToggleRow label="Axis Snap" active={flags.snap_axis} onToggle={() => toggle('snap_axis')} />
        <ToggleRow label="Line Match" active={flags.line_match} onToggle={() => toggle('line_match')} />
        <ToggleRow label="Disable Vanishing Point" active={flags.disable_vpoint} onToggle={() => toggle('disable_vpoint')} />
      </Section>

      <Section title="Angle Snap Values">
        <div className="crp-angle-grid">
          {(state?.angle_snap_values ?? ['', '', '', '']).map((value, index) => (
            <input
              key={index}
              className="crp-angle-input"
              value={value}
              onChange={e => onCommand({ type: 'angle_snap_set', index, value: e.target.value })}
              placeholder={`Angle ${index + 1}`}
            />
          ))}
        </div>
      </Section>

      <Section title="Geometry">
        <div className="crp-stats">
          <StatRow label="Lines" value={state?.lines.length ?? 0} />
          <StatRow label="Fixed Dims" value={state ? Object.keys(state.fixed_lengths).length : 0} />
          <StatRow label="Distances" value={state?.distance_constraints.length ?? 0} />
          <StatRow label="Angles" value={state?.angle_constraints.length ?? 0} />
          <StatRow label="Clipboard" value={state?.clipboard.line_count ?? 0} />
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
            <span className="crp-value">{state?.multi_selected_ids.length} lines</span>
          </div>
        )}
      </Section>

      {state?.rotate_state.active && (
        <Section title="Rotate">
          <div className="crp-helper-text">
            {state.rotate_state.state === 'select_pivot' && 'Pick the pivot vertex on the selected geometry.'}
            {state.rotate_state.state === 'select_axis' && 'Pick a second vertex to define the rotation axis.'}
            {state.rotate_state.state === 'rotating' && `Rotation preview: ${state.rotate_state.current_angle_deg.toFixed(1)}°`}
          </div>
        </Section>
      )}

      {state?.trim_state.active && (
        <Section title="Trim">
          <div className="crp-angle-grid">
            <input
              className="crp-angle-input"
              value={state.trim_state.trim1_text}
              placeholder="Trim Point 1"
              onChange={e => onCommand({ type: 'trim_value_set', point: 1, value: e.target.value })}
            />
            <input
              className="crp-angle-input"
              value={state.trim_state.trim2_text}
              placeholder="Trim Point 2"
              onChange={e => onCommand({ type: 'trim_value_set', point: 2, value: e.target.value })}
            />
          </div>
          <div className="crp-helper-text">{state.trim_state.distance_text || 'Pick two trim points or type distances.'}</div>
          <ActionBtn icon="endorsed" label="Apply Trim" shortcut="Enter" onClick={() => onCommand({ type: 'trim_apply' })} wide />
        </Section>
      )}

      {state?.last_error && (
        <div className="crp-error">
          <Icon icon="warning-sign" size={12} />
          <span>{state.last_error}</span>
        </div>
      )}
    </aside>
  )
}

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div className="crp-section">
    <div className="crp-section-title">{title}</div>
    <div className="crp-section-body">{children}</div>
  </div>
)

const ActionBtn: React.FC<{
  icon: string
  label: string
  shortcut: string
  onClick: () => void
  danger?: boolean
  wide?: boolean
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

