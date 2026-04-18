import React, { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import './ConfirmDialog.css'

interface ConfirmOptions {
  title?: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}

interface PendingPrompt {
  id: number
  options: ConfirmOptions
  resolve: (ok: boolean) => void
}

type Listener = (prompt: PendingPrompt) => void

let sequence = 0
const listeners = new Set<Listener>()

export function confirmAsync(options: ConfirmOptions): Promise<boolean> {
  return new Promise(resolve => {
    const prompt: PendingPrompt = { id: ++sequence, options, resolve }
    if (listeners.size === 0) {
      resolve(window.confirm(options.message))
      return
    }
    for (const listener of listeners) listener(prompt)
  })
}

export const ConfirmHost: React.FC = () => {
  const [current, setCurrent] = useState<PendingPrompt | null>(null)
  const confirmRef = useRef<HTMLButtonElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const listener: Listener = prompt => setCurrent(prompt)
    listeners.add(listener)
    return () => { listeners.delete(listener) }
  }, [])

  useEffect(() => {
    if (!current) return
    previousFocusRef.current = (document.activeElement as HTMLElement) ?? null
    const timer = window.setTimeout(() => confirmRef.current?.focus(), 10)
    return () => window.clearTimeout(timer)
  }, [current])

  const close = (ok: boolean) => {
    if (!current) return
    const resolve = current.resolve
    setCurrent(null)
    resolve(ok)
    window.setTimeout(() => {
      const previous = previousFocusRef.current
      if (previous && document.body.contains(previous)) {
        previous.focus()
      } else {
        ;(document.activeElement as HTMLElement | null)?.blur?.()
        document.body.focus()
      }
      previousFocusRef.current = null
    }, 0)
  }

  useEffect(() => {
    if (!current) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); close(false) }
      else if (e.key === 'Enter') { e.preventDefault(); close(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [current])

  return (
    <AnimatePresence>
      {current && (
        <motion.div
          key={current.id}
          className="confirm-dialog-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onMouseDown={() => close(false)}
        >
          <motion.div
            className="confirm-dialog"
            initial={{ opacity: 0, scale: 0.94, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.94, y: -8 }}
            transition={{ duration: 0.18 }}
            onMouseDown={e => e.stopPropagation()}
          >
            {current.options.title && (
              <div className="confirm-dialog-title">{current.options.title}</div>
            )}
            <div className="confirm-dialog-message">{current.options.message}</div>
            <div className="confirm-dialog-btns">
              <button
                className="confirm-dialog-btn confirm-dialog-btn--cancel"
                onClick={() => close(false)}
              >
                {current.options.cancelLabel ?? 'Cancel'}
              </button>
              <button
                ref={confirmRef}
                className={`confirm-dialog-btn ${current.options.danger ? 'confirm-dialog-btn--danger' : 'confirm-dialog-btn--ok'}`}
                onClick={() => close(true)}
              >
                {current.options.confirmLabel ?? 'OK'}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export default ConfirmHost
