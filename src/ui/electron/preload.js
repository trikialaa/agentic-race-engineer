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
  showOverlayDriver: (data) => ipcRenderer.send("show-radio-driver", data),
  updateOverlayEngineer: (data) => ipcRenderer.send("update-radio-engineer", data),
  onRadioDriver: (callback) => ipcRenderer.on("radio-driver-data", (event, data) => callback(data)),
  onRadioEngineer: (callback) => ipcRenderer.on("radio-engineer-data", (event, data) => callback(data)),
  onOverlayConfig: (callback) => ipcRenderer.on("overlay:config", (event, cfg) => callback(cfg)),
  setGlobalHotkey: async (config) => ipcRenderer.invoke("hotkey:set", config),
  getGlobalHotkey: () => ipcRenderer.invoke("hotkey:get"),
  captureGlobalHotkey: () => ipcRenderer.invoke("hotkey:capture"),
  getConfig: () => ipcRenderer.invoke("config:get"),
  setConfig: (updates) => ipcRenderer.invoke("config:set", updates),
});
