const TEAM_COLORS = {
  "Red Bull":       "#3671C6",
  "Ferrari":        "#E8002D",
  "Mercedes":       "#27F4D2",
  "McLaren":        "#FF8000",
  "Aston Martin":   "#229971",
  "Alpine":         "#FF87BC",
  "Williams":       "#64C4FF",
  "Racing Bulls":   "#6692FF",
  "Haas":           "#B6BABD",
  "Audi":           "#C9D246",
  "Cadillac":       "#CC0000",
};

const teamColor = (teamName) => TEAM_COLORS[teamName] ?? "#E10600";

const statusEl = document.getElementById("status");
const recordBtn = document.getElementById("record-btn");
const transcriptList = document.getElementById("transcript-list");
const hotkeyLabel = document.getElementById("hotkey-label");
const hotkeyBtn = document.getElementById("hotkey-btn");
const settingsBtn = document.getElementById("settings-btn");
const settingsPanel = document.getElementById("settings-panel");
const settingsBack = document.getElementById("settings-back");
const settingsSave = document.getElementById("settings-save-btn");
const settingsHotkeyDisplay = document.getElementById("settings-hotkey-display");
const settingsRebind = document.getElementById("settings-rebind-btn");
const settingsUdpPort = document.getElementById("settings-udp-port");
const settingsServerPort = document.getElementById("settings-server-port");
const settingsSessionTypes = document.getElementById("settings-session-types");
const settingsTtsVoice = document.getElementById("settings-tts-voice");
const settingsDismissSpeed = document.getElementById("settings-dismiss-speed");

const latencyElements = {
  stt: document.getElementById("latency-stt"),
  llm: document.getElementById("latency-llm"),
  tts: document.getElementById("latency-tts"),
};

const formatLatencyValue = (value) =>
  typeof value === "number" ? `${value.toFixed(0)} ms` : "--";

const updateLatencyValue = (metric, value) => {
  const el = latencyElements[metric];
  if (!el) {
    return;
  }
  el.textContent = formatLatencyValue(value);
};

const resetLatencies = () => {
  Object.keys(latencyElements).forEach((metric) =>
    updateLatencyValue(metric, null)
  );
};

resetLatencies();

let mediaRecorder;
let audioStream;
let chunks = [];
let keyHeld = false;
let isCapturingHotkey = false;
const HOTKEY_STORAGE_KEY = "nova-tts-hotkey";
const DEFAULT_FALLBACK_HOTKEY = "R";
const isElectron = Boolean(window.electronAPI?.captureGlobalHotkey);
let configuredHotkey = DEFAULT_FALLBACK_HOTKEY.toLowerCase();
let currentHotkeyDisplay = DEFAULT_FALLBACK_HOTKEY;

const updateHotkeyDisplay = (display) => {
  if (!display) {
    return;
  }
  currentHotkeyDisplay = display;
  if (hotkeyLabel) {
    hotkeyLabel.textContent = display;
  }
  if (recordBtn) {
    recordBtn.textContent = `Hold ${display} or click`;
  }
  if (settingsHotkeyDisplay) {
    settingsHotkeyDisplay.textContent = display;
  }
};

const persistFallbackHotkey = (key) => {
  try {
    localStorage?.setItem(HOTKEY_STORAGE_KEY, key);
  } catch {
    // swallow storage errors (private mode, etc.)
  }
};

const setFallbackHotkey = (key) => {
  const normalized = (key || DEFAULT_FALLBACK_HOTKEY).toLowerCase();
  configuredHotkey = normalized;
  const display = (key || DEFAULT_FALLBACK_HOTKEY).toUpperCase();
  updateHotkeyDisplay(display);
  persistFallbackHotkey(normalized);
};

const isConfiguredHotkey = (key) =>
  !isElectron &&
  typeof key === "string" &&
  key.toLowerCase() === configuredHotkey;

const captureFallbackKey = () =>
  new Promise((resolve) => {
    const cleanup = () => {
      window.removeEventListener("keydown", handleKey, true);
      window.removeEventListener("mousedown", handleMouse, true);
    };

    const handleKey = (event) => {
      event.preventDefault();
      cleanup();
      resolve(event.key || event.code || DEFAULT_FALLBACK_HOTKEY);
    };

    const handleMouse = (event) => {
      event.preventDefault();
      cleanup();
      resolve(`Mouse ${event.button}`);
    };

    window.addEventListener("keydown", handleKey, {
      capture: true,
      once: true,
    });
    window.addEventListener("mousedown", handleMouse, {
      capture: true,
      once: true,
    });
  });

const startHotkeyCapture = async () => {
  if (isCapturingHotkey) {
    return;
  }
  isCapturingHotkey = true;
  setStatus("Press the key or mouse button you want to bind", true);

  try {
    if (isElectron && window.electronAPI?.captureGlobalHotkey) {
      const result = await window.electronAPI.captureGlobalHotkey();
      if (result?.success && result.config) {
        const display = result.config.display || DEFAULT_FALLBACK_HOTKEY;
        updateHotkeyDisplay(display);
        setStatus(`Bound to ${display}`);
      } else {
        setStatus("Unable to bind hotkey.", true);
      }
    } else {
      const key = await captureFallbackKey();
      setFallbackHotkey(key);
      setStatus(`Bound to ${currentHotkeyDisplay}`);
    }
  } catch (error) {
    console.error("Hotkey capture failed", error);
    setStatus("Hotkey capture failed.", true);
  } finally {
    isCapturingHotkey = false;
  }
};

const initHotkey = async () => {
  if (isElectron && window.electronAPI?.getGlobalHotkey) {
    const electronConfig = await window.electronAPI.getGlobalHotkey();
    if (electronConfig?.display) {
      updateHotkeyDisplay(electronConfig.display);
      return;
    }
  }

  const stored = localStorage?.getItem(HOTKEY_STORAGE_KEY);
  setFallbackHotkey(stored || DEFAULT_FALLBACK_HOTKEY);
};

const SAMPLE_RATE = 48000;
let audioContext;
let nextPlaybackTime = 0;

const getAudioContext = () => {
  if (audioContext) {
    return audioContext;
  }
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  audioContext = new AudioContextClass({ sampleRate: SAMPLE_RATE });
  return audioContext;
};

const ensureAudioContextActive = async () => {
  const ctx = getAudioContext();
  if (ctx.state === "suspended") {
    await ctx.resume();
  }
  return ctx;
};

const setStatus = (text, highlight = false) => {
  statusEl.textContent = text;
  statusEl.dataset.state = highlight ? "highlight" : "";
};

const addMessage = (text, role) => {
  const li = document.createElement("li");
  li.className = `message ${role}`;
  li.textContent = text;
  transcriptList.prepend(li);
};

const convertPcmToFloat32 = (chunk) => {
  const length = chunk.byteLength & ~1;
  if (length === 0) {
    return null;
  }
  const samples = new Int16Array(chunk.buffer, chunk.byteOffset, length / 2);
  const float32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    float32[i] = Math.max(-1, Math.min(1, samples[i] / 0x8000));
  }
  return float32;
};

const scheduleChunkPlayback = (float32) => {
  const ctx = getAudioContext();
  const buffer = ctx.createBuffer(1, float32.length, SAMPLE_RATE);
  buffer.copyToChannel(float32, 0, 0);
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(ctx.destination);
  const startTime = Math.max(ctx.currentTime, nextPlaybackTime);
  source.start(startTime);
  nextPlaybackTime = startTime + buffer.duration;
};

const streamAgentAudio = async (text) => {
  await ensureAudioContextActive();
  nextPlaybackTime = Math.max(nextPlaybackTime, audioContext.currentTime);

  const resp = await fetch(`/tts?text=${encodeURIComponent(text)}`);
  if (!resp.ok) {
    throw new Error("Unable to stream TTS");
  }

  const reader = resp.body?.getReader();
  if (!reader) {
    throw new Error("Readable stream not supported");
  }

  let pendingAudio = new Uint8Array(0);
  const MIN_BUFFER_BYTES = 4096;

  const drainPending = (force = false) => {
    while (
      pendingAudio.length >= MIN_BUFFER_BYTES ||
      (force && pendingAudio.length >= 2)
    ) {
      const usableLen = pendingAudio.length & ~1;
      if (usableLen === 0) {
        break;
      }
      const chunk = pendingAudio.slice(0, usableLen);
      pendingAudio = pendingAudio.slice(usableLen);
      const float32 = convertPcmToFloat32(chunk);
      if (float32) {
        scheduleChunkPlayback(float32);
      }
    }
  };

  const appendPending = (chunk) => {
    const combined = new Uint8Array(pendingAudio.length + chunk.length);
    combined.set(pendingAudio);
    combined.set(chunk, pendingAudio.length);
    pendingAudio = combined;
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    if (value) {
      appendPending(value);
      drainPending();
    }
  }

  drainPending(true);
};

const playAgentAudio = async (text) => {
  if (!text) {
    return;
  }
  try {
    const ttsStart = performance.now();
    await streamAgentAudio(text);
    const ttsLatency = performance.now() - ttsStart;
    updateLatencyValue("tts", ttsLatency);
  } catch (error) {
    console.error("TTS error", error);
    updateLatencyValue("tts", null);
  }
};

const sendRecording = async () => {
  if (chunks.length === 0) {
    setStatus("No audio captured.");
    return;
  }
  resetLatencies();
  const blob = new Blob(chunks, { type: "audio/webm" });
  chunks = [];

  const form = new FormData();
  form.append("audio_data", blob, "recording.webm");

  try {
    // Phase 1: STT — show driver text as soon as it arrives
    setStatus("Transcribing...", true);
    const sttResp = await fetch("/transcribe", { method: "POST", body: form });
    if (sttResp.status === 403) { setStatus("No active race session."); return; }
    if (!sttResp.ok) throw new Error("Server rejected audio");
    const sttPayload = await sttResp.json();
    updateLatencyValue("stt", sttPayload.latency_ms?.stt);

    const transcript = sttPayload.transcript;
    if (!transcript) {
      setStatus("No speech detected.");
      return;
    }
    addMessage(transcript, "user");
    const player = sttPayload.player ?? {};
    window.electronAPI?.showOverlayDriver({
      driver: player.name || "DRIVER",
      driverText: transcript,
      teamColor: teamColor(player.team),
    });
    setStatus("Thinking...", true);

    // Phase 2: LLM — update overlay with engineer reply
    const agentResp = await fetch("/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: transcript }),
    });
    if (!agentResp.ok) throw new Error("Agent request failed");
    const agentPayload = await agentResp.json();
    updateLatencyValue("llm", agentPayload.latency_ms?.llm);

    if (agentPayload.agent_reply) {
      addMessage(agentPayload.agent_reply, "agent");
      window.electronAPI?.updateOverlayEngineer({ engineerText: agentPayload.display_reply || agentPayload.agent_reply });
      playAgentAudio(agentPayload.agent_reply);
    }
    setStatus("Transcript received.");
  } catch (error) {
    console.error(error);
    setStatus("Transcription failed.");
  }
};


const startRecording = () => {
  if (!mediaRecorder || mediaRecorder.state === "recording") {
    return;
  }
  chunks = [];
  mediaRecorder.start();
  recordBtn.classList.add("recording");
  recordBtn.textContent = "Recording…";
  setStatus("Recording…", true);
};

const stopRecording = () => {
  if (!mediaRecorder || mediaRecorder.state !== "recording") {
    return;
  }
  mediaRecorder.stop();
  recordBtn.classList.remove("recording");
  recordBtn.textContent = `Hold ${currentHotkeyDisplay} or click`;
};

const initRecorder = async () => {
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(audioStream, {
      mimeType: "audio/webm;codecs=opus",
    });
    mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data && event.data.size > 0) {
        chunks.push(event.data);
      }
    });
    mediaRecorder.addEventListener("stop", sendRecording);
  } catch (error) {
    console.error(error);
    setStatus("Microphone access denied.");
    recordBtn.disabled = true;
  }
};

// ── Session state polling ──────────────────────────────────────
let sessionActive = false;

const applySessionState = (active) => {
  if (active === sessionActive) return;
  sessionActive = active;
  if (active) {
    recordBtn.disabled = false;
    setStatus(`Ready. Hold ${currentHotkeyDisplay} or click the button.`);
  } else {
    recordBtn.disabled = true;
    if (mediaRecorder?.state === "recording") stopRecording();
    setStatus("Waiting for race session...");
  }
};

const pollSession = async () => {
  try {
    const resp = await fetch("/session-state");
    if (resp.ok) {
      const { active } = await resp.json();
      applySessionState(Boolean(active));
    }
  } catch { /* server starting up */ }
};

// Disable button immediately until first poll confirms an active session
recordBtn.disabled = true;
setStatus("Waiting for race session...");
pollSession();
setInterval(pollSession, 3000);

recordBtn.addEventListener("mousedown", () => {
  startRecording();
});

recordBtn.addEventListener("mouseup", () => {
  stopRecording();
});

["mouseleave", "touchend", "touchcancel"].forEach((event) => {
  recordBtn.addEventListener(event, () => {
    stopRecording();
  });
});

const bindElectronHotkey = () => {
  if (!isElectron || !window.electronAPI?.onGlobalHotkey) {
    return;
  }

  window.electronAPI.onHotkeyUpdated((config) => {
    if (config?.display) {
      updateHotkeyDisplay(config.display);
    }
  });

  window.electronAPI.onGlobalHotkey((action) => {
    if (action === "down") {
      keyHeld = true;
      if (mediaRecorder?.state !== "recording") {
        startRecording();
      }
    } else if (action === "up") {
      keyHeld = false;
      if (mediaRecorder?.state === "recording") {
        stopRecording();
      }
    }
  });
};

if (!isElectron) {
  window.addEventListener("keydown", (event) => {
    if (isConfiguredHotkey(event.key) && !keyHeld) {
      keyHeld = true;
      startRecording();
      event.preventDefault();
    }
  });

  window.addEventListener("keyup", (event) => {
    if (isConfiguredHotkey(event.key) && keyHeld) {
      keyHeld = false;
      stopRecording();
    }
  });

  window.addEventListener("blur", () => {
    if (keyHeld) {
      keyHeld = false;
      stopRecording();
    }
  });
}

// ── Settings panel ────────────────────────────────────────────
// Only available in Electron; hide the gear button in plain browser mode.
if (!isElectron && settingsBtn) {
  settingsBtn.style.display = "none";
}

const openSettings = async () => {
  const cfg = await window.electronAPI.getConfig();

  settingsHotkeyDisplay.textContent = currentHotkeyDisplay;
  settingsUdpPort.value = cfg.udpPort ?? 20777;
  settingsServerPort.value = cfg.serverPort ?? 8080;

  const activeTypes = Array.isArray(cfg.sessionTypes) ? cfg.sessionTypes : [];
  settingsSessionTypes.querySelectorAll("input[type=checkbox]").forEach((cb) => {
    cb.checked = activeTypes.includes(cb.value);
  });

  settingsTtsVoice.value = cfg.ttsVoice ?? "Alex";

  const side = cfg.overlayPosition ?? "right";
  settingsPanel.querySelectorAll("input[name='overlay-side']").forEach((r) => {
    r.checked = r.value === side;
  });

  settingsDismissSpeed.value = cfg.overlayDismissSpeed ?? "normal";

  settingsPanel.classList.add("open");
  settingsPanel.removeAttribute("aria-hidden");
};

const closeSettings = () => {
  settingsPanel.classList.remove("open");
  settingsPanel.setAttribute("aria-hidden", "true");
};

const saveSettings = async () => {
  const sessionTypes = Array.from(
    settingsSessionTypes.querySelectorAll("input[type=checkbox]")
  ).filter((cb) => cb.checked).map((cb) => cb.value);

  const overlayPosition =
    settingsPanel.querySelector("input[name='overlay-side']:checked")?.value ?? "right";

  await window.electronAPI.setConfig({
    udpPort: parseInt(settingsUdpPort.value, 10) || 20777,
    serverPort: parseInt(settingsServerPort.value, 10) || 8080,
    sessionTypes,
    ttsVoice: settingsTtsVoice.value.trim() || "Alex",
    overlayPosition,
    overlayDismissSpeed: settingsDismissSpeed.value,
  });

  closeSettings();
};

if (isElectron && settingsBtn) settingsBtn.addEventListener("click", openSettings);
if (settingsBack) settingsBack.addEventListener("click", closeSettings);
if (settingsSave) settingsSave.addEventListener("click", saveSettings);
if (settingsRebind) settingsRebind.addEventListener("click", startHotkeyCapture);

await initHotkey();
bindElectronHotkey();
if (hotkeyBtn) {
  hotkeyBtn.addEventListener("click", startHotkeyCapture);
}

await initRecorder();
