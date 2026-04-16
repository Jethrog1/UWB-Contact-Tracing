import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { spawn, ChildProcess, execFile } from 'child_process'
import { join } from 'path'
import { promisify } from 'util'
import { is } from '@electron-toolkit/utils'

let cadServer: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
let shutdownPromise: Promise<void> | null = null
let appQuitInFlight = false

const CAD_SERVER_HEALTH_URL = 'http://127.0.0.1:8765/health'
const CAD_SERVER_PORT = 8765
const execFileAsync = promisify(execFile)

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

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

async function listCadServerPids(): Promise<number[]> {
  try {
    if (process.platform === 'win32') {
      const { stdout } = await execFileAsync('netstat', ['-ano', '-p', 'tcp'])
      const matches = stdout
        .split(/\r?\n/)
        .map(line => line.trim())
        .filter(line => line.startsWith('TCP'))
        .map(line => line.split(/\s+/))
        .filter(parts => parts.length >= 5 && parts[1].endsWith(`:${CAD_SERVER_PORT}`) && parts[3] === 'LISTENING')
        .map(parts => Number.parseInt(parts[4], 10))
        .filter((pid): pid is number => Number.isInteger(pid) && pid > 0)
      return [...new Set(matches)]
    }

    const { stdout } = await execFileAsync('lsof', ['-ti', `tcp:${CAD_SERVER_PORT}`, '-sTCP:LISTEN'])
    return stdout
      .split(/\r?\n/)
      .map(line => Number.parseInt(line.trim(), 10))
      .filter((pid): pid is number => Number.isInteger(pid) && pid > 0)
  } catch {
    return []
  }
}

async function killProcessTree(pid: number): Promise<void> {
  if (!Number.isInteger(pid) || pid <= 0 || pid === process.pid) return

  try {
    if (process.platform === 'win32') {
      await execFileAsync('taskkill', ['/PID', String(pid), '/T', '/F'])
      return
    }

    process.kill(pid, 'SIGTERM')
    await sleep(500)
    try {
      process.kill(pid, 0)
      process.kill(pid, 'SIGKILL')
    } catch {
      // Process exited after SIGTERM.
    }
  } catch {
    // The process may already be gone.
  }
}

async function stopCadServersOnPort(excludePid?: number): Promise<void> {
  const pids = await listCadServerPids()
  for (const pid of pids) {
    if (excludePid && pid === excludePid) continue
    await killProcessTree(pid)
  }

  const deadline = Date.now() + 4000
  while (Date.now() < deadline) {
    const remaining = await listCadServerPids()
    const live = excludePid ? remaining.filter(pid => pid !== excludePid) : remaining
    if (live.length === 0 && !(await isCadServerReachable())) return
    await sleep(120)
  }
}

async function waitForCadServerReady(): Promise<void> {
  const deadline = Date.now() + 10000
  while (Date.now() < deadline) {
    if (await isCadServerReachable()) return
    if (cadServer?.exitCode != null) {
      throw new Error(`CAD server exited early with code ${cadServer.exitCode}`)
    }
    await sleep(150)
  }
  throw new Error('Timed out waiting for CAD server to become ready.')
}

async function startCadServer(): Promise<void> {
  if (cadServer && cadServer.exitCode == null && !cadServer.killed) {
    return
  }

  await stopCadServersOnPort()

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
      windowsHide: true,
    },
  )

  cadServer.stdout?.on('data', (data) => {
    process.stdout.write(`[cad-server] ${data}`)
  })

  cadServer.stderr?.on('data', (data) => {
    process.stderr.write(`[cad-server] ${data}`)
  })

  cadServer.on('exit', async (code) => {
    console.log(`[main] CAD server exited with code ${code}`)
    cadServer = null
  })

  await waitForCadServerReady()
}

async function stopCadServer(): Promise<void> {
  if (shutdownPromise) {
    await shutdownPromise
    return
  }

  shutdownPromise = (async () => {
    const child = cadServer
    cadServer = null

    if (child?.pid) {
      try {
        child.kill('SIGTERM')
      } catch {
        // The process may already be exiting.
      }
      await sleep(300)
      await killProcessTree(child.pid)
    }

    await stopCadServersOnPort()
  })()

  try {
    await shutdownPromise
  } finally {
    shutdownPromise = null
  }
}

// ── Paths ──────────────────────────────────────────────────────────────

const brigidRoot = is.dev
  ? join(app.getAppPath(), '..')          // BRIGID/frontend/.. → BRIGID/
  : join(process.resourcesPath, '..')

ipcMain.handle('app:get-paths', () => ({
  svg: join(brigidRoot, 'svg'),
  pdf: join(brigidRoot, 'pdf'),
  profile: join(brigidRoot, 'Profile'),
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

ipcMain.handle('dialog:open-folder', async (_event, options: { defaultPath?: string }) => {
  if (!mainWindow) return { canceled: true, folderPath: undefined }
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    defaultPath: options?.defaultPath,
  })
  return {
    canceled: result.canceled,
    folderPath: result.canceled ? undefined : result.filePaths[0],
  }
})

ipcMain.handle('shell:open-path', async (_event, path: string) => {
  await shell.openPath(path)
})

ipcMain.handle('cad:status', async () => {
  const running = (cadServer !== null && !cadServer.killed) || await isCadServerReachable()
  return { running }
})

ipcMain.handle('cad:restart', async () => {
  await stopCadServer()
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
    backgroundColor: '#0a0b0d',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#00000000',
      symbolColor: '#8c96a5',
      height: 28,
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
  try {
    await startCadServer()
  } catch (error) {
    console.error('[main] Failed to start CAD server:', error)
  }
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', (event) => {
  if (appQuitInFlight) return
  event.preventDefault()
  appQuitInFlight = true
  void stopCadServer().finally(() => {
    app.exit(0)
  })
})
