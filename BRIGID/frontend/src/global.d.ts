declare module '*.png' {
  const src: string
  export default src
}

interface FileDialogFilter {
  name: string
  extensions: string[]
}

interface BrigidDesktopApi {
  getVersion: () => string
  cadStatus: () => Promise<{ running: boolean }>
  cadRestart: () => Promise<{ ok: boolean }>
  getPaths?: () => Promise<{ svg: string; pdf: string; profile: string; downloads: string }>
  openFile?: (
    filters: FileDialogFilter[],
    defaultPath?: string,
  ) => Promise<{ canceled: boolean; filePaths: string[] }>
  saveFile?: (
    filters: FileDialogFilter[],
    defaultPath?: string,
  ) => Promise<{ canceled: boolean; filePath?: string }>
  openFolder?: (
    defaultPath?: string,
  ) => Promise<{ canceled: boolean; folderPath?: string }>
  openPath?: (path: string) => Promise<void>
  readTextFile?: (path: string) => Promise<{ success: boolean; content?: string; path?: string; error?: string }>
}

interface Window {
  api?: BrigidDesktopApi
}
