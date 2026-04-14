import { contextBridge, ipcRenderer } from 'electron'

const api = {
  getVersion: (): string => '1.0.0',

  /** Check if the Python CAD backend process is running */
  cadStatus: (): Promise<{ running: boolean }> =>
    ipcRenderer.invoke('cad:status'),

  /** Ask main process to restart the Python CAD backend */
  cadRestart: (): Promise<{ ok: boolean }> =>
    ipcRenderer.invoke('cad:restart'),

  /** Resolve platform-specific save directories (svg / pdf) */
  getPaths: (): Promise<{ svg: string; pdf: string }> =>
    ipcRenderer.invoke('app:get-paths'),

  /** Open a native file-open dialog */
  openFile: (
    filters: { name: string; extensions: string[] }[],
    defaultPath?: string,
  ): Promise<{ canceled: boolean; filePaths: string[] }> =>
    ipcRenderer.invoke('dialog:open-file', { filters, defaultPath }),

  /** Open a native file-save dialog */
  saveFile: (
    filters: { name: string; extensions: string[] }[],
    defaultPath?: string,
  ): Promise<{ canceled: boolean; filePath?: string }> =>
    ipcRenderer.invoke('dialog:save-file', { filters, defaultPath }),
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
