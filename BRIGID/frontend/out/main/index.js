"use strict";
const electron = require("electron");
const path = require("path");
const child_process = require("child_process");
const utils = require("@electron-toolkit/utils");
let cadServer = null;
function startCadServer() {
  const backendDir = utils.is.dev ? path.join(electron.app.getAppPath(), "..", "backend") : path.join(process.resourcesPath, "backend");
  const pythonCmd = process.platform === "win32" ? "python" : "python3";
  console.log(`[main] Starting CAD server in ${backendDir}`);
  cadServer = child_process.spawn(
    pythonCmd,
    ["-m", "uvicorn", "cad_server:app", "--host", "127.0.0.1", "--port", "8765"],
    {
      cwd: backendDir,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" }
    }
  );
  cadServer.stdout?.on("data", (d) => {
    process.stdout.write(`[cad-server] ${d}`);
  });
  cadServer.stderr?.on("data", (d) => {
    process.stderr.write(`[cad-server] ${d}`);
  });
  cadServer.on("exit", (code) => {
    console.log(`[main] CAD server exited with code ${code}`);
    cadServer = null;
  });
}
function stopCadServer() {
  if (cadServer) {
    cadServer.kill();
    cadServer = null;
  }
}
electron.ipcMain.handle("cad:status", () => {
  return { running: cadServer !== null && !cadServer.killed };
});
electron.ipcMain.handle("cad:restart", () => {
  stopCadServer();
  startCadServer();
  return { ok: true };
});
function createWindow() {
  const mainWindow = new electron.BrowserWindow({
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
      // must match .hot-bar height in CSS
    },
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  mainWindow.on("ready-to-show", () => {
    mainWindow.maximize();
    mainWindow.show();
  });
  mainWindow.webContents.setWindowOpenHandler((details) => {
    electron.shell.openExternal(details.url);
    return { action: "deny" };
  });
  if (utils.is.dev && process.env["ELECTRON_RENDERER_URL"]) {
    mainWindow.loadURL(process.env["ELECTRON_RENDERER_URL"]);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
}
electron.app.whenReady().then(() => {
  startCadServer();
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
