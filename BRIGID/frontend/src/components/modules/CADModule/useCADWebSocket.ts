// ── CAD WebSocket Hook ────────────────────────────────────────────
import { useEffect, useRef, useState, useCallback } from 'react'
import { CADState, CADCommand } from './types'

const WS_BASE = 'ws://localhost:8765/cad/ws'
const RECONNECT_DELAY_MS = 2000
const MAX_RECONNECT_ATTEMPTS = 10

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface UseCADWebSocketReturn {
  state: CADState | null
  status: ConnectionStatus
  sendCommand: (cmd: CADCommand) => void
  reconnect: () => void
}

export function useCADWebSocket(workspaceId: string): UseCADWebSocketReturn {
  const [state, setState]   = useState<CADState | null>(null)
  const [status, setStatus] = useState<ConnectionStatus>('disconnected')

  const wsRef              = useRef<WebSocket | null>(null)
  const reconnectCount     = useRef(0)
  const reconnectTimer     = useRef<ReturnType<typeof setTimeout> | null>(null)
  const unmountedRef       = useRef(false)

  const clearReconnectTimer = () => {
    if (reconnectTimer.current !== null) {
      clearTimeout(reconnectTimer.current)
      reconnectTimer.current = null
    }
  }

  const connect = useCallback(() => {
    if (unmountedRef.current) return
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return

    setStatus('connecting')

    const url = workspaceId ? `${WS_BASE}/${workspaceId}` : WS_BASE
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (unmountedRef.current) { ws.close(); return }
      setStatus('connected')
      reconnectCount.current = 0
    }

    ws.onmessage = (ev: MessageEvent) => {
      if (unmountedRef.current) return
      try {
        const data = JSON.parse(ev.data as string) as CADState
        setState(data)
      } catch {
        console.error('[CAD WS] Failed to parse message:', ev.data)
      }
    }

    ws.onerror = () => {
      if (unmountedRef.current) return
      setStatus('error')
    }

    ws.onclose = () => {
      if (unmountedRef.current) return
      setStatus('disconnected')
      wsRef.current = null

      if (reconnectCount.current < MAX_RECONNECT_ATTEMPTS) {
        reconnectCount.current += 1
        clearReconnectTimer()
        reconnectTimer.current = setTimeout(() => {
          if (!unmountedRef.current) connect()
        }, RECONNECT_DELAY_MS)
      }
    }
  }, [workspaceId])

  // Manual reconnect — resets attempt counter
  const reconnect = useCallback(() => {
    clearReconnectTimer()
    reconnectCount.current = 0
    if (wsRef.current) {
      wsRef.current.onclose = null   // suppress auto-reconnect from old socket
      wsRef.current.close()
      wsRef.current = null
    }
    connect()
  }, [connect])

  const sendCommand = useCallback((cmd: CADCommand) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.warn('[CAD WS] sendCommand called while not connected:', cmd.type)
      return
    }
    try {
      wsRef.current.send(JSON.stringify(cmd))
    } catch (err) {
      console.error('[CAD WS] send error:', err)
    }
  }, [])

  useEffect(() => {
    unmountedRef.current = false
    connect()

    return () => {
      unmountedRef.current = true
      clearReconnectTimer()
      if (wsRef.current) {
        wsRef.current.onclose = null  // don't trigger reconnect on teardown
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  return { state, status, sendCommand, reconnect }
}
