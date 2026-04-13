import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { spawn, ChildProcess } from 'child_process'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'

let cadServer: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null

const CAD_SERVER_HEALTH_URL = 'http://127.0.0.1:8765/health'

async function isCadServerReachable(): Promise<boolean> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 1200)

  try {
    const response = await fetch(CAD_SERVER_HEALTH_URL, { signal: controller.signal })
    return response.ok
  } catch {
    return false
  } finally {
    clearTimeout(timeout)
  }
}

async function startCadServer(): Promise<void> {
  if (await isCadServerReachable()) {
    console.log('[main] Reusing existing CAD server on 127.0.0.1:8765')
    cadServer = null
    return
  }

  const backendDir = is.dev
    ? join(app.getAppPath(), '..', 'backend')
    : join(process.resourcesPath, 'backend')

  const pythonCmd = process.platform === 'win32' ? 'py' : 'python3'
  const pythonArgs = process.platform === 'win32' ? ['-3'] : []

  console.log(`[main] Starting CAD server in ${backendDir}`)

  cadServer = spawn(
    pythonCmd,
    [...pythonArgs, '-m', 'uvicorn', 'cad_server:app', '--host', '127.0.0.1', '--port', '8765'],
    {
      cwd: backendDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    },
  )

  cadServer.stdout?.on('data', (data) => {
    process.stdout.write(`[cad-server] ${data}`)
  })

  cadServer.stderr?.on('data', (data) => {
    process.stderr.write(`[cad-server] ${data}`)
  })

  cadServer.on('exit', async (code) => {
    if (code !== 0 && await isCadServerReachable()) {
      console.log('[main] CAD server already active on 127.0.0.1:8765, reusing existing instance')
      cadServer = null
      return
    }

    console.log(`[main] CAD server exited with code ${code}`)
    cadServer = null
  })
}

function stopCadServer(): void {
  if (!cadServer) return
  cadServer.kill()
  cadServer = null
}

// ── Paths ──────────────────────────────────────────────────────────────

const brigidRoot = is.dev
  ? join(app.getAppPath(), '..')          // BRIGID/frontend/.. → BRIGID/
  : join(process.resourcesPath, '..')

ipcMain.handle('app:get-paths', () => ({
  svg: join(brigidRoot, 'svg'),
  pdf: join(brigidRoot, 'pdf'),
}))

// ── File dialogs ───────────────────────────────────────────────────────

ipcMain.handle('dialog:open-file', async (_event, options: Electron.OpenDialogOptions) => {
  if (!mainWindow) return { canceled: true, filePaths: [] }
  return dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    ...options,
  })
})

ipcMain.handle('dialog:save-file', async (_event, options: Electron.SaveDialogOptions) => {
  if (!mainWindow) return { canceled: true, filePath: undefined }
  return dialog.showSaveDialog(mainWindow, options)
})

ipcMain.handle('cad:status', async () => {
  const running = (cadServer !== null && !cadServer.killed) || await isCadServerReachable()
  return { running }
})

ipcMain.handle('cad:restart', async () => {
  stopCadServer()
  await startCadServer()
  const running = (cadServer !== null && !cadServer.killed) || await isCadServerReachable()
  return { ok: running }
})

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1200,
    minHeight: 800,
    show: false,
    backgroundColor: '#060a0f',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#060a0f',
      symbolColor: '#4a5a74',
      height: 32,
    },
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  let windowShown = false
  const revealWindow = (reason: string) => {
    if (!mainWindow || windowShown) return
    windowShown = true
    console.log(`[main] Revealing window (${reason})`)
    mainWindow.maximize()
    mainWindow.show()
    mainWindow.focus()
  }

  mainWindow.on('ready-to-show', () => {
    revealWindow('ready-to-show')
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  mainWindow.webContents.on('did-finish-load', () => {
    console.log('[main] Renderer finished load')
    revealWindow('did-finish-load')
  })

  mainWindow.webContents.on('did-fail-load', (_event, code, description, url, isMainFrame) => {
    console.error(`[main] Renderer failed to load (code=${code}, mainFrame=${isMainFrame}) ${description}: ${url}`)
    revealWindow('did-fail-load')
  })

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error(`[main] Renderer process gone: ${details.reason}`)
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  if (is.dev && process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }

  setTimeout(() => {
    revealWindow('fallback-timeout')
  }, 1800)
}

const gotSingleInstanceLock = app.requestSingleInstanceLock()

if (!gotSingleInstanceLock) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore()
      mainWindow.show()
      mainWindow.focus()
      return
    }

    if (app.isReady()) createWindow()
  })
}

app.whenReady().then(async () => {
  await startCadServer()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  stopCadServer()
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  stopCadServer()
})
