"use strict";
const electron = require("electron");
const api = {
  /** Returns the app version — placeholder */
  getVersion: () => "1.0.0",
  /** Placeholder for future backend communication */
  sendToBackend: (_channel, _data) => {
    console.log("[preload] sendToBackend called — not connected yet");
  }
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
