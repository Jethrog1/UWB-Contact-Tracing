import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useCADWebSocket } from './useCADWebSocket'
import CADCanvas from './CADCanvas'
import CADRightPanel from './CADRightPanel'
import FeatureManager from './FeatureManager'
import { CADCommand, CADContextMenuItem } from './types'
import './CADModule.css'

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
    if (!Number.isNaN(n)) {
      onConfirm(n)
    }
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

const ContextMenuItemRow: React.FC<{
  item: CADContextMenuItem
  onClick: () => void
}> = ({ item, onClick }) => (
  <button className="cad-context-item" disabled={item.disabled} onClick={onClick}>
    <span>{item.label}</span>
    {item.kind === 'toggle' && <span className="cad-context-check">{item.checked ? 'On' : 'Off'}</span>}
  </button>
)

const CADModule: React.FC = () => {
  const { state, status, sendCommand, reconnect } = useCADWebSocket()
  const dialog = state?.pending_dialog ?? null
  const contextMenu = state?.context_menu ?? null
  const contextRef = useRef<HTMLDivElement>(null)

  const handleCommand = useCallback((cmd: CADCommand) => {
    sendCommand(cmd)
  }, [sendCommand])

  useEffect(() => {
    if (!contextMenu) return

    const onPointerDown = (event: MouseEvent) => {
      if (contextRef.current?.contains(event.target as Node)) return
      sendCommand({ type: 'context_close' })
    }

    window.addEventListener('mousedown', onPointerDown)
    return () => window.removeEventListener('mousedown', onPointerDown)
  }, [contextMenu, sendCommand])

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
      <div className="cad-canvas-area">
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

        {state?.last_notice && (
          <div className={`cad-notice cad-notice--${state.last_notice.kind}`}>
            <div className="cad-notice-title">{state.last_notice.title}</div>
            <div className="cad-notice-message">{state.last_notice.message}</div>
          </div>
        )}

        {state && (
          <div className="cad-coord-readout">
            X {state.cursor_world_snapped[0].toFixed(2)}
            &nbsp;&nbsp;
            Y {state.cursor_world_snapped[1].toFixed(2)}
          </div>
        )}

        {contextMenu && (
          <div
            ref={contextRef}
            className="cad-context-menu"
            style={{ left: contextMenu.x, top: contextMenu.y }}
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
      </div>

      <CADRightPanel state={state} onCommand={handleCommand} status={status} />

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

