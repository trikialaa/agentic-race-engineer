const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const { app, BrowserWindow, ipcMain, screen, Menu } = require("electron");
const { uIOhook, UiohookKey, WheelDirection } = require("uiohook-napi");

const DEFAULT_URL = "http://localhost:8080";
const DEFAULT_HOTKEY = { type: "key", keycode: UiohookKey.R, display: "R" };

const HELPER_CANDIDATES = [
  path.join(
    __dirname,
    "..",
    "..",
    "..",
    "helpers",
    "wheel_detector",
    "bin",
    "WheelHelper.exe"
  ),
];

const helperPath = HELPER_CANDIDATES.find((candidate) => fs.existsSync(candidate)) || HELPER_CANDIDATES[0];
let wheelHelperProcess = null;
let wheelStdoutBuffer = "";
let wheelCapturePending = null;

let mainWindow;
let hotkeyConfig = { ...DEFAULT_HOTKEY };
let hotkeyHeld = false;
let captureActive = false;
let pendingWheelRelease = null;

let configPath = null;

const loadConfig = () => {
  if (!configPath) return {};
  try {
    return JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch {
    return {};
  }
};

const saveConfig = (updates) => {
  if (!configPath) return;
  try {
    const existing = loadConfig();
    fs.writeFileSync(configPath, JSON.stringify({ ...existing, ...updates }, null, 2), "utf8");
  } catch (err) {
    console.error("Failed to save config:", err);
  }
};

const keyReverseMap = Object.entries(UiohookKey).reduce((map, [name, code]) => {
  map[code] = name;
  return map;
}, {});

const WheelDirectionNames = {
  [WheelDirection.VERTICAL]: "Vertical",
  [WheelDirection.HORIZONTAL]: "Horizontal",
};

const getKeyDisplay = (code) => String(keyReverseMap[code] ?? code);

const emitHotkeyEvent = (action) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("global-hotkey", action);
  }
};

const broadcastHotkeyUpdated = () => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("hotkey:updated", hotkeyConfig);
  }
};

const resetHotkeyState = () => {
  hotkeyHeld = false;
  releaseWheel();
};

const matchesKey = (event) =>
  hotkeyConfig.type === "key" && event.keycode === hotkeyConfig.keycode;

const matchesMouse = (event) =>
  hotkeyConfig.type === "mouse" && event.button === hotkeyConfig.button;

const matchesWheel = (event) =>
  hotkeyConfig.type === "wheel" &&
  event.direction === hotkeyConfig.direction &&
  Math.sign(event.rotation) === hotkeyConfig.rotationSign;

const matchesWheelButton = (event) =>
  hotkeyConfig.type === "wheel-button" && event.button === hotkeyConfig.button;

const releaseWheel = () => {
  if (pendingWheelRelease) {
    clearTimeout(pendingWheelRelease);
    pendingWheelRelease = null;
  }
};

const handleKeyDown = (event) => {
  if (captureActive || hotkeyHeld || !matchesKey(event)) {
    return;
  }
  hotkeyHeld = true;
  emitHotkeyEvent("down");
};

const handleKeyUp = (event) => {
  if (captureActive || !hotkeyHeld || !matchesKey(event)) {
    return;
  }
  hotkeyHeld = false;
  emitHotkeyEvent("up");
};

const handleMouseDown = (event) => {
  if (captureActive || hotkeyHeld || !matchesMouse(event)) {
    return;
  }
  hotkeyHeld = true;
  emitHotkeyEvent("down");
};

const handleMouseUp = (event) => {
  if (captureActive || !hotkeyHeld || !matchesMouse(event)) {
    return;
  }
  hotkeyHeld = false;
  emitHotkeyEvent("up");
};

const handleWheelEvent = (event) => {
  if (captureActive || hotkeyHeld || !matchesWheel(event)) {
    return;
  }
  hotkeyHeld = true;
  emitHotkeyEvent("down");
  releaseWheel();
  pendingWheelRelease = setTimeout(() => {
    hotkeyHeld = false;
    emitHotkeyEvent("up");
    pendingWheelRelease = null;
  }, 60);
};

const tryResolveWheelCapture = (event) => {
  if (!wheelCapturePending) {
    return;
  }
  const resolve = wheelCapturePending;
  wheelCapturePending = null;
  resolve({
    type: "wheel-button",
    button: event.button,
    display: `Wheel Button ${event.button}`,
  });
};

const handleWheelButtonEvent = (event) => {
  tryResolveWheelCapture(event);
  if (captureActive || !matchesWheelButton(event)) {
    return;
  }
  if (event.pressed) {
    if (!hotkeyHeld) {
      hotkeyHeld = true;
      emitHotkeyEvent("down");
    }
  } else {
    if (hotkeyHeld) {
      hotkeyHeld = false;
      emitHotkeyEvent("up");
    }
  }
};

const sanitizeHotkey = (config) => {
  if (!config || !config.type) {
    return null;
  }
  if (config.type === "key") {
    if (typeof config.keycode !== "number") {
      return null;
    }
    return {
      type: "key",
      keycode: config.keycode,
      display: config.display || getKeyDisplay(config.keycode),
    };
  }
  if (config.type === "mouse") {
    if (config.button == null) {
      return null;
    }
    return {
      type: "mouse",
      button: config.button,
      display: config.display || `Mouse ${config.button}`,
    };
  }
  if (config.type === "wheel") {
    if (
      typeof config.direction !== "number" ||
      typeof config.rotationSign !== "number"
    ) {
      return null;
    }
    return {
      type: "wheel",
      direction: config.direction,
      rotationSign: config.rotationSign,
      display:
        config.display ||
        `Wheel ${
          WheelDirectionNames[config.direction] || config.direction
        } ${config.rotationSign > 0 ? "+" : "-"}`,
    };
  }
  if (config.type === "wheel-button") {
    return sanitizeWheelButton(config);
  }
  return null;
};

const sanitizeWheelButton = (config) => {
  if (typeof config.button !== "number") {
    return null;
  }
  return {
    type: "wheel-button",
    button: config.button,
    display: config.display || `Wheel Button ${config.button}`,
  };
};

const setHotkey = (config) => {
  const sanitized = sanitizeHotkey(config);
  if (!sanitized) {
    return false;
  }
  hotkeyConfig = sanitized;
  resetHotkeyState();
  broadcastHotkeyUpdated();
  saveConfig({ hotkey: hotkeyConfig });
  return true;
};

const captureHotkey = () => {
  if (captureActive) {
    return Promise.reject(new Error("Capture already in progress"));
  }
  captureActive = true;
  return new Promise((resolve) => {
    let settled = false;

    const cleanup = () => {
      captureActive = false;
      uIOhook.off("keydown", handleKey);
      uIOhook.off("mousedown", handleMouse);
      uIOhook.off("wheel", handleWheel);
      wheelCapturePending = null;
    };

    const finish = (config) => {
      if (settled) {
        return;
      }
      settled = true;
      cleanup();
      resolve(config);
    };

    const handleKey = (event) => {
      finish({
        type: "key",
        keycode: event.keycode,
        display: getKeyDisplay(event.keycode),
      });
    };

    const handleMouse = (event) => {
      finish({
        type: "mouse",
        button: event.button,
        display: `Mouse ${event.button}`,
      });
    };

    const handleWheel = (event) => {
      const direction = event.direction;
      const rotationSign = Math.sign(event.rotation) || 1;
      finish({
        type: "wheel",
        direction,
        rotationSign,
        display: `Wheel ${
          WheelDirectionNames[direction] || direction
        } ${rotationSign > 0 ? "+" : "-"}`,
      });
    };

    wheelCapturePending = (event) => {
      finish({
        type: "wheel-button",
        button: event.button,
        display: `Wheel Button ${event.button}`,
      });
    };

    uIOhook.on("keydown", handleKey);
    uIOhook.on("mousedown", handleMouse);
    uIOhook.on("wheel", handleWheel);
  });
};

const parseWheelHelperLine = (line) => {
  if (!line.trim()) {
    return null;
  }
  try {
    const event = JSON.parse(line);
    if (
      event &&
      typeof event.button === "number" &&
      typeof event.pressed === "boolean"
    ) {
      return event;
    }
  } catch (error) {
    console.error("Failed to parse wheel helper message", error, line);
  }
  return null;
};

const handleHelperChunk = (chunk) => {
  wheelStdoutBuffer += chunk.toString("utf8");
  let index;
  while ((index = wheelStdoutBuffer.indexOf("\n")) !== -1) {
    const line = wheelStdoutBuffer.slice(0, index);
    wheelStdoutBuffer = wheelStdoutBuffer.slice(index + 1);
    const event = parseWheelHelperLine(line);
    if (event) {
      handleWheelButtonEvent(event);
    }
  }
};

const startWheelHelper = () => {
  if (wheelHelperProcess || process.platform !== "win32") {
    return;
  }
  if (!helperPath || !fs.existsSync(helperPath)) {
    console.warn(
      `Wheel helper binary not found (${helperPath ?? "unknown path"}). Build it with 'dotnet publish -c Release -o helpers/wheel_detector/bin helpers/wheel_detector/WheelHelper.csproj' or copy from native/wheel-helper/bin.`
    );
    return;
  }
  console.log(`Spawning wheel helper from ${helperPath}`);
  wheelHelperProcess = spawn(helperPath, [], {
    cwd: path.resolve(__dirname, ".."),
    stdio: ["ignore", "pipe", "pipe"],
  });
  wheelHelperProcess.stdout.on("data", handleHelperChunk);
  wheelHelperProcess.stderr.on("data", (chunk) => {
    console.error("wheel helper error:", chunk.toString("utf8"));
  });
  wheelHelperProcess.on("exit", (code, signal) => {
    console.warn(
      "wheel helper exited",
      code !== null ? `code ${code}` : `signal ${signal}`
    );
    wheelHelperProcess = null;
    wheelStdoutBuffer = "";
    // If the button was held when the helper died, synthesize a release so
    // hotkeyHeld doesn't stay stuck true and block all future presses.
    if (hotkeyHeld && hotkeyConfig.type === "wheel-button") {
      hotkeyHeld = false;
      emitHotkeyEvent("up");
    }
    // Restart after a short delay so transient crashes self-heal.
    setTimeout(startWheelHelper, 2000);
  });
};

const stopWheelHelper = () => {
  if (!wheelHelperProcess) {
    return;
  }
  wheelHelperProcess.kill();
  wheelHelperProcess = null;
  wheelStdoutBuffer = "";
};

let overlayWindow = null;

const broadcastOverlayConfig = () => {
  const cfg = loadConfig();
  overlayWindow?.webContents.send("overlay:config", {
    position: cfg.overlayPosition ?? "right",
    dismissSpeed: cfg.overlayDismissSpeed ?? "normal",
  });
};

function createOverlayWindow() {
  const { width, height } = screen.getPrimaryDisplay().size;
  overlayWindow = new BrowserWindow({
    width,
    height,
    x: 0,
    y: 0,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  overlayWindow.setAlwaysOnTop(true, "screen-saver");
  overlayWindow.setIgnoreMouseEvents(true, { forward: true });
  overlayWindow.loadFile(path.join(__dirname, "overlay.html"));
  overlayWindow.webContents.once("did-finish-load", broadcastOverlayConfig);
  overlayWindow.on("closed", () => { overlayWindow = null; });
}

function createWindow() {
  Menu.setApplicationMenu(null);

  mainWindow = new BrowserWindow({
    width: 440,
    height: 640,
    resizable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      devTools: false,
    },
  });

  mainWindow.webContents.on("context-menu", (e) => e.preventDefault());

  const targetUrl = process.env.F1_RADIO_URL || DEFAULT_URL;
  mainWindow.loadURL(targetUrl);
  mainWindow.on("closed", () => {
    mainWindow = undefined;
  });

  mainWindow.webContents.once("did-finish-load", broadcastHotkeyUpdated);
  return mainWindow;
}

ipcMain.on("show-radio-driver", (event, data) => {
  overlayWindow?.webContents.send("radio-driver-data", data);
});

ipcMain.on("update-radio-engineer", (event, data) => {
  overlayWindow?.webContents.send("radio-engineer-data", data);
});

ipcMain.handle("config:get", () => loadConfig());

ipcMain.handle("config:set", (event, updates) => {
  saveConfig(updates);
  broadcastOverlayConfig();
  return { success: true };
});

ipcMain.handle("hotkey:get", () => hotkeyConfig);

ipcMain.handle("hotkey:set", (event, config) => {
  const previous = hotkeyConfig;
  const success = setHotkey(config);
  return { success, config: success ? hotkeyConfig : previous };
});

ipcMain.handle("hotkey:capture", async () => {
  try {
    const config = await captureHotkey();
    const success = setHotkey(config);
    return { success, config: success ? hotkeyConfig : null };
  } catch (error) {
    return { success: false, error: error?.message };
  }
});

app.whenReady().then(() => {
  configPath = path.join(__dirname, "..", "..", "..", "config.json");
  const savedConfig = loadConfig();
  if (savedConfig.hotkey) {
    const sanitized = sanitizeHotkey(savedConfig.hotkey);
    if (sanitized) {
      hotkeyConfig = sanitized;
    }
  }

  uIOhook.on("keydown", handleKeyDown);
  uIOhook.on("keyup", handleKeyUp);
  uIOhook.on("mousedown", handleMouseDown);
  uIOhook.on("mouseup", handleMouseUp);
  uIOhook.on("wheel", handleWheelEvent);
  uIOhook.start();
  startWheelHelper();

  createWindow();
  createOverlayWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("will-quit", () => {
  uIOhook.stop();
  stopWheelHelper();
});
