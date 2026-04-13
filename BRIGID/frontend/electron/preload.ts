import { contextBridge } from 'electron'

/** Placeholder API surface for future IPC communication with main process */
const api = {
  /** Returns the app version — placeholder */
  getVersion: (): string => '1.0.0',
  /** Placeholder for future backend communication */
  sendToBackend: (_channel: string, _data?: unknown): void => {
    console.log('[preload] sendToBackend called — not connected yet')
  }
}

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore
  window.api = api
}
