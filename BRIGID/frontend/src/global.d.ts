interface FileDialogFilter {
  name: string
  extensions: string[]
}

interface BrigidDesktopApi {
  getVersion: () => string
  cadStatus: () => Promise<{ running: boolean }>
  cadRestart: () => Promise<{ ok: boolean }>
  getPaths?: () => Promise<{ svg: string; pdf: string }>
  openFile?: (
    filters: FileDialogFilter[],
    defaultPath?: string,
  ) => Promise<{ canceled: boolean; filePaths: string[] }>
  saveFile?: (
    filters: FileDialogFilter[],
    defaultPath?: string,
  ) => Promise<{ canceled: boolean; filePath?: string }>
}

interface Window {
  api?: BrigidDesktopApi
}
