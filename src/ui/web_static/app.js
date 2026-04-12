const statusEl = document.getElementById("status");
const recordBtn = document.getElementById("record-btn");
const transcriptList = document.getElementById("transcript-list");
const hotkeyLabel = document.getElementById("hotkey-label");
const hotkeyBtn = document.getElementById("hotkey-btn");

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
    setStatus("Transcribing...", true);
    const resp = await fetch("/transcribe", {
      method: "POST",
      body: form,
    });
    if (!resp.ok) {
      throw new Error("Server rejected audio");
    }
    const payload = await resp.json();
    const latencyPayload = payload.latency_ms ?? payload.latency ?? {};
    updateLatencyValue("stt", latencyPayload.stt);
    updateLatencyValue("llm", latencyPayload.llm);
    if (payload.transcript) {
      addMessage(payload.transcript, "user");
    }
    if (payload.agent_reply) {
      addMessage(payload.agent_reply, "agent");
      playAgentAudio(payload.agent_reply);
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
    setStatus(`Ready. Hold ${currentHotkeyDisplay} or click the button.`);
  } catch (error) {
    console.error(error);
    setStatus("Microphone access denied.");
    recordBtn.disabled = true;
  }
};

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
      if (mediaRecorder?.state !== "recording") {
        keyHeld = true;
        startRecording();
      }
    } else if (action === "up") {
      if (keyHeld) {
        keyHeld = false;
        if (mediaRecorder?.state === "recording") {
          stopRecording();
        }
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

await initHotkey();
bindElectronHotkey();
if (hotkeyBtn) {
  hotkeyBtn.addEventListener("click", startHotkeyCapture);
}

await initRecorder();
