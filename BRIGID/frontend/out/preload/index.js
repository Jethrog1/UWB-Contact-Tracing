"use strict";
const electron = require("electron");
const api = {
  getVersion: () => "1.0.0",
  /** Check if the Python CAD backend process is running */
  cadStatus: () => electron.ipcRenderer.invoke("cad:status"),
  /** Ask main process to restart the Python CAD backend */
  cadRestart: () => electron.ipcRenderer.invoke("cad:restart"),
  /** Resolve platform-specific save directories (svg / pdf) */
  getPaths: () => electron.ipcRenderer.invoke("app:get-paths"),
  /** Open a native file-open dialog */
  openFile: (filters, defaultPath) => electron.ipcRenderer.invoke("dialog:open-file", { filters, defaultPath }),
  /** Open a native file-save dialog */
  saveFile: (filters, defaultPath) => electron.ipcRenderer.invoke("dialog:save-file", { filters, defaultPath })
};
if (process.contextIsolated) {
  try {
    electron.contextBridge.exposeInMainWorld("api", api);
  } catch (error) {
    console.error(error);
  }
} else {
  window.api = api;
}
