// ── CAD Module ────────────────────────────────────────────────────
import React, { useCallback, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { useCADWebSocket } from './useCADWebSocket'
import CADCanvas from './CADCanvas'
import FeatureManager from './FeatureManager'
import CADRightPanel from './CADRightPanel'
import { CADCommand } from './types'
import './CADModule.css'

// ── Dialog modal (replaces Python simpledialog.askfloat) ──────────
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
    if (!isNaN(n)) onConfirm(n)
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
          <button className="cad-dialog-btn cad-dialog-btn--ok"     onClick={confirm}>OK</button>
        </div>
      </motion.div>
    </div>
  )
}

// ── CAD Module ────────────────────────────────────────────────────
const CADModule: React.FC = () => {
  const { state, status, sendCommand, reconnect } = useCADWebSocket()

  const handleCommand = useCallback((cmd: CADCommand) => {
    sendCommand(cmd)
  }, [sendCommand])

  // ── Resolve pending_dialog ────────────────────────────────────
  const dialog = state?.pending_dialog ?? null

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
      {/* ── Canvas area (spans "canvas" grid cell) ──────────── */}
      <div className="cad-canvas-area">
        {/* Disconnected overlay */}
        {status !== 'connected' && !state && (
          <div className="cad-offline-overlay">
            <div className="cad-offline-icon">⬡</div>
            <div className="cad-offline-title">CAD Engine Offline</div>
            <div className="cad-offline-sub">
              {status === 'connecting'
                ? 'Connecting to Python backend…'
                : 'Could not reach the CAD server on localhost:8765'}
            </div>
            {status !== 'connecting' && (
              <button className="cad-offline-retry" onClick={reconnect}>
                Reconnect
              </button>
            )}
          </div>
        )}

        {/* Canvas */}
        <CADCanvas state={state} onCommand={handleCommand} />

        {/* Floating feature manager */}
        <FeatureManager state={state} />

        {/* Cursor world coord readout */}
        {state && (
          <div className="cad-coord-readout">
            X {state.cursor_world_snapped[0].toFixed(2)}
            &nbsp;&nbsp;
            Y {state.cursor_world_snapped[1].toFixed(2)}
          </div>
        )}
      </div>

      {/* ── Right panel (spans "right" grid cell) ───────────── */}
      <CADRightPanel state={state} onCommand={handleCommand} status={status} />

      {/* ── Float dialog portal ──────────────────────────────── */}
      <AnimatePresence>
        {dialog && dialog.kind === 'prompt_float' && (
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
