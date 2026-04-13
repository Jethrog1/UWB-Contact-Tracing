import { app, BrowserWindow, shell, ipcMain } from 'electron'
import { join } from 'path'
import { spawn, ChildProcess } from 'child_process'
import { is } from '@electron-toolkit/utils'

let cadServer: ChildProcess | null = null

// ── Spawn Python CAD backend ──────────────────────────────────────
function startCadServer(): void {
  // Resolve backend directory relative to the app root.
  // app.getAppPath() returns the electron-vite project root (BRIGID/frontend/)
  // in both dev and packaged builds.
  const backendDir = is.dev
    ? join(app.getAppPath(), '..', 'backend')         // dev: BRIGID/frontend/../backend = BRIGID/backend
    : join(process.resourcesPath, 'backend')          // packaged: resources/backend

  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3'

  console.log(`[main] Starting CAD server in ${backendDir}`)

  cadServer = spawn(
    pythonCmd,
    ['-m', 'uvicorn', 'cad_server:app', '--host', '127.0.0.1', '--port', '8765'],
    {
      cwd:   backendDir,
      stdio: ['ignore', 'pipe', 'pipe'],
      env:   { ...process.env, PYTHONUNBUFFERED: '1' },
    }
  )

  cadServer.stdout?.on('data', (d) => {
    process.stdout.write(`[cad-server] ${d}`)
  })
  cadServer.stderr?.on('data', (d) => {
    process.stderr.write(`[cad-server] ${d}`)
  })
  cadServer.on('exit', (code) => {
    console.log(`[main] CAD server exited with code ${code}`)
    cadServer = null
  })
}

function stopCadServer(): void {
  if (cadServer) {
    cadServer.kill()
    cadServer = null
  }
}

// ── IPC: backend status ───────────────────────────────────────────
ipcMain.handle('cad:status', () => {
  return { running: cadServer !== null && !cadServer.killed }
})

ipcMain.handle('cad:restart', () => {
  stopCadServer()
  startCadServer()
  return { ok: true }
})

// ── Window creation ───────────────────────────────────────────────
function createWindow(): void {
  const mainWindow = new BrowserWindow({
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
      height: 32,                  // must match .hot-bar height in CSS
    },
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow.on('ready-to-show', () => {
    mainWindow.maximize()
    mainWindow.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

// ── App lifecycle ─────────────────────────────────────────────────
app.whenReady().then(() => {
  startCadServer()
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
