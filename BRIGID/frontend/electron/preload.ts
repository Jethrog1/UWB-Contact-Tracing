import { contextBridge, ipcRenderer } from 'electron'

const api = {
  getVersion: (): string => '1.0.0',

  cadStatus: (): Promise<{ running: boolean }> =>
    ipcRenderer.invoke('cad:status'),

  cadRestart: (): Promise<{ ok: boolean }> =>
    ipcRenderer.invoke('cad:restart'),

  getPaths: (): Promise<{ svg: string; pdf: string; profile: string; downloads: string }> =>
    ipcRenderer.invoke('app:get-paths'),

  readTextFile: (path: string): Promise<{ success: boolean; content?: string; path?: string; error?: string }> =>
    ipcRenderer.invoke('fs:read-text-file', path),

  openFile: (
    filters: { name: string; extensions: string[] }[],
    defaultPath?: string,
  ): Promise<{ canceled: boolean; filePaths: string[] }> =>
    ipcRenderer.invoke('dialog:open-file', { filters, defaultPath }),

  saveFile: (
    filters: { name: string; extensions: string[] }[],
    defaultPath?: string,
  ): Promise<{ canceled: boolean; filePath?: string }> =>
    ipcRenderer.invoke('dialog:save-file', { filters, defaultPath }),

  openFolder: (
    defaultPath?: string,
  ): Promise<{ canceled: boolean; folderPath?: string }> =>
    ipcRenderer.invoke('dialog:open-folder', { defaultPath }),

  openPath: (path: string): Promise<void> =>
    ipcRenderer.invoke('shell:open-path', path),
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
