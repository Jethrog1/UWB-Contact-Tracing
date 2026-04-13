"use strict";
const electron = require("electron");
const child_process = require("child_process");
const path = require("path");
const utils = require("@electron-toolkit/utils");
let cadServer = null;
let mainWindow = null;
const CAD_SERVER_HEALTH_URL = "http://127.0.0.1:8765/health";
async function isCadServerReachable() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1200);
  try {
    const response = await fetch(CAD_SERVER_HEALTH_URL, { signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}
async function startCadServer() {
  if (await isCadServerReachable()) {
    console.log("[main] Reusing existing CAD server on 127.0.0.1:8765");
    cadServer = null;
    return;
  }
  const backendDir = utils.is.dev ? path.join(electron.app.getAppPath(), "..", "backend") : path.join(process.resourcesPath, "backend");
  const pythonCmd = process.platform === "win32" ? "py" : "python3";
  const pythonArgs = process.platform === "win32" ? ["-3"] : [];
  console.log(`[main] Starting CAD server in ${backendDir}`);
  cadServer = child_process.spawn(
    pythonCmd,
    [...pythonArgs, "-m", "uvicorn", "cad_server:app", "--host", "127.0.0.1", "--port", "8765"],
    {
      cwd: backendDir,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" }
    }
  );
  cadServer.stdout?.on("data", (data) => {
    process.stdout.write(`[cad-server] ${data}`);
  });
  cadServer.stderr?.on("data", (data) => {
    process.stderr.write(`[cad-server] ${data}`);
  });
  cadServer.on("exit", async (code) => {
    if (code !== 0 && await isCadServerReachable()) {
      console.log("[main] CAD server already active on 127.0.0.1:8765, reusing existing instance");
      cadServer = null;
      return;
    }
    console.log(`[main] CAD server exited with code ${code}`);
    cadServer = null;
  });
}
function stopCadServer() {
  if (!cadServer) return;
  cadServer.kill();
  cadServer = null;
}
const brigidRoot = utils.is.dev ? path.join(electron.app.getAppPath(), "..") : path.join(process.resourcesPath, "..");
electron.ipcMain.handle("app:get-paths", () => ({
  svg: path.join(brigidRoot, "svg"),
  pdf: path.join(brigidRoot, "pdf")
}));
electron.ipcMain.handle("dialog:open-file", async (_event, options) => {
  if (!mainWindow) return { canceled: true, filePaths: [] };
  return electron.dialog.showOpenDialog(mainWindow, {
    properties: ["openFile"],
    ...options
  });
});
electron.ipcMain.handle("dialog:save-file", async (_event, options) => {
  if (!mainWindow) return { canceled: true, filePath: void 0 };
  return electron.dialog.showSaveDialog(mainWindow, options);
});
electron.ipcMain.handle("cad:status", async () => {
  const running = cadServer !== null && !cadServer.killed || await isCadServerReachable();
  return { running };
});
electron.ipcMain.handle("cad:restart", async () => {
  stopCadServer();
  await startCadServer();
  const running = cadServer !== null && !cadServer.killed || await isCadServerReachable();
  return { ok: running };
});
function createWindow() {
  mainWindow = new electron.BrowserWindow({
    width: 1600,
    height: 1e3,
    minWidth: 1200,
    minHeight: 800,
    show: false,
    backgroundColor: "#060a0f",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#060a0f",
      symbolColor: "#4a5a74",
      height: 32
    },
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  let windowShown = false;
  const revealWindow = (reason) => {
    if (!mainWindow || windowShown) return;
    windowShown = true;
    console.log(`[main] Revealing window (${reason})`);
    mainWindow.maximize();
    mainWindow.show();
    mainWindow.focus();
  };
  mainWindow.on("ready-to-show", () => {
    revealWindow("ready-to-show");
  });
  mainWindow.webContents.setWindowOpenHandler((details) => {
    electron.shell.openExternal(details.url);
    return { action: "deny" };
  });
  mainWindow.webContents.on("did-finish-load", () => {
    console.log("[main] Renderer finished load");
    revealWindow("did-finish-load");
  });
  mainWindow.webContents.on("did-fail-load", (_event, code, description, url, isMainFrame) => {
    console.error(`[main] Renderer failed to load (code=${code}, mainFrame=${isMainFrame}) ${description}: ${url}`);
    revealWindow("did-fail-load");
  });
  mainWindow.webContents.on("render-process-gone", (_event, details) => {
    console.error(`[main] Renderer process gone: ${details.reason}`);
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
  if (utils.is.dev && process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
  setTimeout(() => {
    revealWindow("fallback-timeout");
  }, 1800);
}
const gotSingleInstanceLock = electron.app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  electron.app.quit();
} else {
  electron.app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
      return;
    }
    if (electron.app.isReady()) createWindow();
  });
}
electron.app.whenReady().then(async () => {
  await startCadServer();
  createWindow();
  electron.app.on("activate", () => {
    if (electron.BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
electron.app.on("window-all-closed", () => {
  stopCadServer();
  if (process.platform !== "darwin") {
    electron.app.quit();
  }
});
electron.app.on("before-quit", () => {
  stopCadServer();
});
