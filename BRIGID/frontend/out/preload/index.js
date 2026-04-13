"use strict";
const electron = require("electron");
const api = {
  getVersion: () => "1.0.0",
  /** Check if the Python CAD backend process is running */
  cadStatus: () => electron.ipcRenderer.invoke("cad:status"),
  /** Ask main process to restart the Python CAD backend */
  cadRestart: () => electron.ipcRenderer.invoke("cad:restart")
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
