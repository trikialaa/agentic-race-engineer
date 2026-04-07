const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  onGlobalHotkey: (callback) => {
    const listener = (event, ...args) => callback(...args);
    ipcRenderer.on("global-hotkey", listener);
    return () => ipcRenderer.removeListener("global-hotkey", listener);
  },
  onHotkeyUpdated: (callback) => {
    const listener = (event, config) => callback(config);
    ipcRenderer.on("hotkey:updated", listener);
    return () => ipcRenderer.removeListener("hotkey:updated", listener);
  },
  setGlobalHotkey: async (config) => ipcRenderer.invoke("hotkey:set", config),
  getGlobalHotkey: () => ipcRenderer.invoke("hotkey:get"),
  captureGlobalHotkey: () => ipcRenderer.invoke("hotkey:capture"),
});
