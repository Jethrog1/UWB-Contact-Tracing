"use strict";
const electron = require("electron");
const path = require("path");
const utils = require("@electron-toolkit/utils");
function createWindow() {
  const mainWindow = new electron.BrowserWindow({
    width: 1600,
    height: 1e3,
    minWidth: 1200,
    minHeight: 800,
    show: false,
    backgroundColor: "#0a0e17",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#0d1117",
      symbolColor: "#8b949e",
      height: 36
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
  createWindow();
  electron.app.on("activate", function() {
    if (electron.BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});
electron.app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    electron.app.quit();
  }
});
