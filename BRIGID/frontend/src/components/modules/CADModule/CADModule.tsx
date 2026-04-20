import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useCADWebSocket } from './useCADWebSocket'
import CADCanvas from './CADCanvas'
import CADRightPanel from './CADRightPanel'
import FeatureManager from './FeatureManager'
import { CADCommand, CADContextMenuItem } from './types'
import './CADModule.css'

// ── Float dialog ──────────────────────────────────────────────────

interface DialogProps {
  title: string
  label: string
  initial: number
  onConfirm: (v: number) => void
  onCancel: () => void
}

const FloatDialog: React.FC<DialogProps> = ({ title, label, initial, onConfirm, onCancel }) => {
  const [value, setValue] = useState(String(initial))
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  const confirm = () => {
    const n = parseFloat(value)
    if (!Number.isNaN(n)) onConfirm(n)
  }

  return (
    <div className="cad-dialog-overlay" onClick={onCancel}>
      <motion.div
        className="cad-dialog"
        initial={{ opacity: 0, scale: 0.94, y: -8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.94, y: -8 }}
        transition={{ duration: 0.18 }}
        onClick={e => e.stopPropagation()}
      >
        <div className="cad-dialog-title">{title}</div>
        <div className="cad-dialog-label">{label}</div>
        <input
          ref={inputRef}
          className="cad-dialog-input"
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') confirm()
            if (e.key === 'Escape') onCancel()
          }}
        />
        <div className="cad-dialog-btns">
          <button className="cad-dialog-btn cad-dialog-btn--cancel" onClick={onCancel}>Cancel</button>
          <button className="cad-dialog-btn cad-dialog-btn--ok" onClick={confirm}>OK</button>
        </div>
      </motion.div>
    </div>
  )
}

// ── Context menu item ─────────────────────────────────────────────

const ContextMenuItemRow: React.FC<{
  item: CADContextMenuItem
  onClick: () => void
}> = ({ item, onClick }) => (
  <button className="cad-context-item" disabled={item.disabled} onClick={onClick}>
    <span>{item.label}</span>
    {item.kind === 'toggle' && (
      <span className={`cad-context-check${item.checked ? ' cad-context-check--on' : ''}`}>
        {item.checked ? '●' : '○'}
      </span>
    )}
  </button>
)

// ── Floating notification ─────────────────────────────────────────

interface NoticeState {
  id: number
  kind: 'error' | 'info'
  title: string
  message: string
}

let noticeSeq = 0

const FloatingNotice: React.FC<{
  notice: NoticeState
  onDismiss: (id: number) => void
}> = ({ notice, onDismiss }) => {
  useEffect(() => {
    const t = setTimeout(() => onDismiss(notice.id), 7000)
    return () => clearTimeout(t)
  }, [notice.id, onDismiss])

  return (
    <motion.div
      className={`cad-notice cad-notice--${notice.kind}`}
      initial={{ opacity: 0, y: -8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -6, scale: 0.96 }}
      transition={{ duration: 0.18 }}
      layout
    >
      <div className="cad-notice-body">
        <div className="cad-notice-title">{notice.title}</div>
        <div className="cad-notice-message">{notice.message}</div>
      </div>
      <button className="cad-notice-close" onClick={() => onDismiss(notice.id)} title="Dismiss">×</button>
    </motion.div>
  )
}

// ── Floating tool panel (Trim / Rotate) ──────────────────────────

interface CADModuleProps {
  workspaceId: string
  workspaceName?: string
}

const CADModule: React.FC<CADModuleProps> = ({ workspaceId, workspaceName }) => {
  const { state, status, sendCommand, reconnect } = useCADWebSocket(workspaceId)
  const dialog = state?.pending_dialog ?? null
  const contextMenu = state?.context_menu ?? null
  const contextRef = useRef<HTMLDivElement>(null)
  const canvasAreaRef = useRef<HTMLDivElement>(null)

  // Floating notifications
  const [notices, setNotices] = useState<NoticeState[]>([])
  const prevNoticeRef = useRef<string>('')

  const dismissNotice = useCallback((id: number) => {
    setNotices(prev => prev.filter(n => n.id !== id))
  }, [])

  // Detect new last_notice from state
  useEffect(() => {
    if (!state?.last_notice) return
    const key = `${state.last_notice.title}::${state.last_notice.message}`
    if (key === prevNoticeRef.current) return
    prevNoticeRef.current = key
    const newNotice: NoticeState = {
      id: ++noticeSeq,
      kind: state.last_notice.kind,
      title: state.last_notice.title,
      message: state.last_notice.message,
    }
    setNotices(prev => [...prev.slice(-4), newNotice])
  }, [state?.last_notice])

  const handleCommand = useCallback((cmd: CADCommand) => {
    sendCommand(cmd)
  }, [sendCommand])

  // Listen for view commands broadcast from TabStrip / HotBar
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as { cmd: string; workspaceId: string; tool?: string }
      if (detail.workspaceId !== workspaceId) return  // only this workspace
      if (detail.cmd === 'set_tool') {
        const tool = detail.tool
        if (tool === 'cursor' || tool === 'line' || tool === 'vertex' || tool === 'dim') {
          sendCommand({ type: 'tool_change', tool })
        } else if (tool === 'rotate' || tool === 'trim') {
          sendCommand({ type: 'context_action', action: tool })
        }
        return
      }
      const cmdMap: Record<string, CADCommand> = {
        undo:       { type: 'undo' },
        redo:       { type: 'redo' },
        zoom_in:    { type: 'zoom_in' },
        zoom_out:   { type: 'zoom_out' },
        zoom_reset: { type: 'zoom_reset' },
      }
      const cadCmd = cmdMap[detail.cmd]
      if (cadCmd) sendCommand(cadCmd)
    }
    window.addEventListener('cad-view-command', handler)
    return () => window.removeEventListener('cad-view-command', handler)
  }, [workspaceId, sendCommand])

  useEffect(() => {
    const handler = async (e: Event) => {
      const detail = (e as CustomEvent).detail as { workspaceId: string; module?: string }
      if (detail.workspaceId !== workspaceId || (detail.module && detail.module !== 'cad')) return
      if (!window.api?.saveFile) return
      let defaultPath = 'floor-plan.svg'
      try {
        if (workspaceName) {
          const res = await fetch(`http://localhost:8765/api/workspace/paths/${encodeURIComponent(workspaceId)}?workspace_name=${encodeURIComponent(workspaceName)}`)
          const data = await res.json() as { success: boolean; svg?: string }
          if (data.success && data.svg) defaultPath = `${data.svg}\\floor-plan.svg`
        }
      } catch { /* use fallback */ }
      const result = await window.api.saveFile(
        [{ name: 'SVG Files', extensions: ['svg'] }],
        defaultPath,
      )
      if (!result.canceled && result.filePath) {
        sendCommand({ type: 'export_svg', filepath: result.filePath })
      }
    }
    window.addEventListener('workspace-save-command', handler)
    window.addEventListener('workspace-save-as-command', handler)
    return () => {
      window.removeEventListener('workspace-save-command', handler)
      window.removeEventListener('workspace-save-as-command', handler)
    }
  }, [workspaceId, workspaceName, sendCommand])

  // Close context menu on outside click
  useEffect(() => {
    if (!contextMenu) return
    const onPointerDown = (event: MouseEvent) => {
      if (contextRef.current?.contains(event.target as Node)) return
      sendCommand({ type: 'context_close' })
    }
    window.addEventListener('mousedown', onPointerDown)
    return () => window.removeEventListener('mousedown', onPointerDown)
  }, [contextMenu, sendCommand])

  // Context menu: clamp position using actual measured size after render
  const [menuPos, setMenuPos] = useState<{ left: number; top: number }>({ left: 0, top: 0 })

  useLayoutEffect(() => {
    if (!contextMenu) return
    const menu = contextRef.current
    const area = canvasAreaRef.current
    const MARGIN = 4
    const menuRect = menu?.getBoundingClientRect()
    const areaRect = area?.getBoundingClientRect() ?? { width: window.innerWidth, height: window.innerHeight } as DOMRect
    const w = menuRect?.width ?? 0
    const h = menuRect?.height ?? 0
    const maxLeft = Math.max(0, areaRect.width - w - MARGIN)
    const maxTop = Math.max(0, areaRect.height - h - MARGIN)
    const left = Math.max(0, Math.min(contextMenu.x, maxLeft))
    const top = Math.max(0, Math.min(contextMenu.y, maxTop))
    setMenuPos(prev => (prev.left === left && prev.top === top ? prev : { left, top }))
  }, [contextMenu])

  const handleDialogConfirm = useCallback((value: number) => {
    if (!dialog) return
    sendCommand({ type: 'dialog_response', request_id: dialog.request_id, value })
  }, [dialog, sendCommand])

  const handleDialogCancel = useCallback(() => {
    if (!dialog) return
    sendCommand({ type: 'dialog_response', request_id: dialog.request_id, value: null })
  }, [dialog, sendCommand])

  return (
    <>
      <div ref={canvasAreaRef} className="cad-canvas-area">
        {/* Offline overlay */}
        {status !== 'connected' && !state && (
          <div className="cad-offline-overlay">
            <div className="cad-offline-icon">□</div>
            <div className="cad-offline-title">CAD Engine Offline</div>
            <div className="cad-offline-sub">
              {status === 'connecting'
                ? 'Connecting to the Python CAD backend...'
                : 'Could not reach the CAD server on localhost:8765'}
            </div>
            {status !== 'connecting' && (
              <button className="cad-offline-retry" onClick={reconnect}>
                Reconnect
              </button>
            )}
          </div>
        )}

        <CADCanvas state={state} onCommand={handleCommand} />
        <FeatureManager state={state} />

        {/* Floating notification stack */}
        <div className="cad-notice-stack">
          <AnimatePresence mode="popLayout">
            {notices.map(n => (
              <FloatingNotice key={n.id} notice={n} onDismiss={dismissNotice} />
            ))}
          </AnimatePresence>
        </div>

        {/* Contextual floating tool panel — Trim */}
        <AnimatePresence>
          {state?.trim_state.active && (
            <motion.div
              className="cad-tool-panel cad-tool-panel--trim"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.18 }}
            >
              <div className="cad-tool-panel-title">
                <span className="cad-tool-panel-icon">✂</span>
                Trim
              </div>
              <div className="cad-tool-panel-row">
                <input
                  className="cad-tool-input"
                  value={state.trim_state.trim1_text}
                  placeholder="Point 1"
                  onChange={e => handleCommand({ type: 'trim_value_set', point: 1, value: e.target.value })}
                />
                <input
                  className="cad-tool-input"
                  value={state.trim_state.trim2_text}
                  placeholder="Point 2"
                  onChange={e => handleCommand({ type: 'trim_value_set', point: 2, value: e.target.value })}
                />
              </div>
              {state.trim_state.distance_text && (
                <div className="cad-tool-panel-hint">{state.trim_state.distance_text}</div>
              )}
              <button
                className="cad-tool-panel-apply"
                onClick={() => handleCommand({ type: 'trim_apply' })}
              >
                Apply Trim
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Contextual floating tool panel — Rotate */}
        <AnimatePresence>
          {state?.rotate_state.active && (
            <motion.div
              className="cad-tool-panel cad-tool-panel--rotate"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.18 }}
            >
              <div className="cad-tool-panel-title">
                <span className="cad-tool-panel-icon">↻</span>
                Rotate
              </div>
              <div className="cad-tool-panel-hint">
                {state.rotate_state.state === 'select_pivot' && 'Pick the pivot vertex.'}
                {state.rotate_state.state === 'select_axis' && 'Pick a second vertex to define the axis.'}
                {state.rotate_state.state === 'rotating' && `Preview: ${state.rotate_state.current_angle_deg.toFixed(1)}°`}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* World coordinate readout */}
        {state && (
          <div className="cad-coord-readout">
            X {state.cursor_world_snapped[0].toFixed(2)}
            &nbsp;&nbsp;
            Y {state.cursor_world_snapped[1].toFixed(2)}
          </div>
        )}

        {/* Right-click context menu — clamped to viewport */}
        {contextMenu && (
          <div
            ref={contextRef}
            className="cad-context-menu"
            style={{ left: menuPos.left, top: menuPos.top }}
          >
            {contextMenu.sections.map(section => (
              <div key={section.title} className="cad-context-section">
                <div className="cad-context-title">{section.title}</div>
                {section.items.map(item => (
                  <ContextMenuItemRow
                    key={item.id}
                    item={item}
                    onClick={() => sendCommand({ type: 'context_action', action: item.id })}
                  />
                ))}
              </div>
            ))}
          </div>
        )}

        {/* Right panel — absolutely positioned inside canvas area */}
        <CADRightPanel state={state} onCommand={handleCommand} status={status} workspaceId={workspaceId} workspaceName={workspaceName} />
      </div>

      <AnimatePresence>
        {dialog?.kind === 'prompt_float' && (
          <FloatDialog
            key={dialog.request_id}
            title={dialog.title}
            label={dialog.label}
            initial={dialog.initial}
            onConfirm={handleDialogConfirm}
            onCancel={handleDialogCancel}
          />
        )}
      </AnimatePresence>
    </>
  )
}

export default CADModule
