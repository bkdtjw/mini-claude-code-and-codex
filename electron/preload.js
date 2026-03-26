const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  selectFolder: () => ipcRenderer.invoke("select-folder"),
  getCwd: () => ipcRenderer.invoke("get-cwd"),
  platform: process.platform,
});
