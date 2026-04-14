"use strict";
const electron = require("electron");
const child_process = require("child_process");
const path = require("path");
const util = require("util");
const utils = require("@electron-toolkit/utils");
let cadServer = null;
let mainWindow = null;
let shutdownPromise = null;
let appQuitInFlight = false;
const CAD_SERVER_HEALTH_URL = "http://127.0.0.1:8765/health";
const CAD_SERVER_PORT = 8765;
const execFileAsync = util.promisify(child_process.execFile);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
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
async function listCadServerPids() {
  try {
    if (process.platform === "win32") {
      const { stdout: stdout2 } = await execFileAsync("netstat", ["-ano", "-p", "tcp"]);
      const matches = stdout2.split(/\r?\n/).map((line) => line.trim()).filter((line) => line.startsWith("TCP")).map((line) => line.split(/\s+/)).filter((parts) => parts.length >= 5 && parts[1].endsWith(`:${CAD_SERVER_PORT}`) && parts[3] === "LISTENING").map((parts) => Number.parseInt(parts[4], 10)).filter((pid) => Number.isInteger(pid) && pid > 0);
      return [...new Set(matches)];
    }
    const { stdout } = await execFileAsync("lsof", ["-ti", `tcp:${CAD_SERVER_PORT}`, "-sTCP:LISTEN"]);
    return stdout.split(/\r?\n/).map((line) => Number.parseInt(line.trim(), 10)).filter((pid) => Number.isInteger(pid) && pid > 0);
  } catch {
    return [];
  }
}
async function killProcessTree(pid) {
  if (!Number.isInteger(pid) || pid <= 0 || pid === process.pid) return;
  try {
    if (process.platform === "win32") {
      await execFileAsync("taskkill", ["/PID", String(pid), "/T", "/F"]);
      return;
    }
    process.kill(pid, "SIGTERM");
    await sleep(500);
    try {
      process.kill(pid, 0);
      process.kill(pid, "SIGKILL");
    } catch {
    }
  } catch {
  }
}
async function stopCadServersOnPort(excludePid) {
  const pids = await listCadServerPids();
  for (const pid of pids) {
    await killProcessTree(pid);
  }
  const deadline = Date.now() + 4e3;
  while (Date.now() < deadline) {
    const remaining = await listCadServerPids();
    const live = remaining;
    if (live.length === 0 && !await isCadServerReachable()) return;
    await sleep(120);
  }
}
async function waitForCadServerReady() {
  const deadline = Date.now() + 1e4;
  while (Date.now() < deadline) {
    if (await isCadServerReachable()) return;
    if (cadServer?.exitCode != null) {
      throw new Error(`CAD server exited early with code ${cadServer.exitCode}`);
    }
    await sleep(150);
  }
  throw new Error("Timed out waiting for CAD server to become ready.");
}
async function startCadServer() {
  if (cadServer && cadServer.exitCode == null && !cadServer.killed) {
    return;
  }
  await stopCadServersOnPort();
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
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      windowsHide: true
    }
  );
  cadServer.stdout?.on("data", (data) => {
    process.stdout.write(`[cad-server] ${data}`);
  });
  cadServer.stderr?.on("data", (data) => {
    process.stderr.write(`[cad-server] ${data}`);
  });
  cadServer.on("exit", async (code) => {
    console.log(`[main] CAD server exited with code ${code}`);
    cadServer = null;
  });
  await waitForCadServerReady();
}
async function stopCadServer() {
  if (shutdownPromise) {
    await shutdownPromise;
    return;
  }
  shutdownPromise = (async () => {
    const child = cadServer;
    cadServer = null;
    if (child?.pid) {
      try {
        child.kill("SIGTERM");
      } catch {
      }
      await sleep(300);
      await killProcessTree(child.pid);
    }
    await stopCadServersOnPort();
  })();
  try {
    await shutdownPromise;
  } finally {
    shutdownPromise = null;
  }
}
const brigidRoot = utils.is.dev ? path.join(electron.app.getAppPath(), "..") : path.join(process.resourcesPath, "..");
electron.ipcMain.handle("app:get-paths", () => ({
  svg: path.join(brigidRoot, "svg"),
  pdf: path.join(brigidRoot, "pdf"),
  profile: path.join(brigidRoot, "Profile")
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
electron.ipcMain.handle("dialog:open-folder", async (_event, options) => {
  if (!mainWindow) return { canceled: true, folderPath: void 0 };
  const result = await electron.dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"],
    defaultPath: options?.defaultPath
  });
  return {
    canceled: result.canceled,
    folderPath: result.canceled ? void 0 : result.filePaths[0]
  };
});
electron.ipcMain.handle("shell:open-path", async (_event, path2) => {
  await electron.shell.openPath(path2);
});
electron.ipcMain.handle("cad:status", async () => {
  const running = cadServer !== null && !cadServer.killed || await isCadServerReachable();
  return { running };
});
electron.ipcMain.handle("cad:restart", async () => {
  await stopCadServer();
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
  try {
    await startCadServer();
  } catch (error) {
    console.error("[main] Failed to start CAD server:", error);
  }
  createWindow();
  electron.app.on("activate", () => {
    if (electron.BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
electron.app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    electron.app.quit();
  }
});
electron.app.on("before-quit", (event) => {
  if (appQuitInFlight) return;
  event.preventDefault();
  appQuitInFlight = true;
  void stopCadServer().finally(() => {
    electron.app.exit(0);
  });
});
