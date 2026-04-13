import { contextBridge, ipcRenderer } from 'electron'

const api = {
  getVersion: (): string => '1.0.0',

  /** Check if the Python CAD backend process is running */
  cadStatus: (): Promise<{ running: boolean }> =>
    ipcRenderer.invoke('cad:status'),

  /** Ask main process to restart the Python CAD backend */
  cadRestart: (): Promise<{ ok: boolean }> =>
    ipcRenderer.invoke('cad:restart'),
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
