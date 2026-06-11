const TEAM_COLORS = {
  "Red Bull":     "#3671C6",
  "Ferrari":      "#E8002D",
  "Mercedes":     "#27F4D2",
  "McLaren":      "#FF8000",
  "Aston Martin": "#229971",
  "Alpine":       "#FF87BC",
  "Williams":     "#64C4FF",
  "Racing Bulls": "#6692FF",
  "Haas":         "#B6BABD",
  "Audi":         "#C9D246",
  "Cadillac":     "#CC0000",
};

const teamColor = (teamName) => TEAM_COLORS[teamName] ?? "#E10600";

// ── Element refs ──────────────────────────────────────────────
const statusEl   = document.getElementById("status");
const recordBtn  = document.getElementById("record-btn");
const hotkeyLabel = document.getElementById("hotkey-label");
const hotkeyBtn  = document.getElementById("hotkey-btn");
const sessionDot = document.getElementById("session-dot");
const saveBtn    = document.getElementById("save-btn");

// ── Status ────────────────────────────────────────────────────
const setStatus = (text, highlight = false) => {
  statusEl.textContent = text;
  statusEl.classList.toggle("highlight", highlight);
};

// ── Hotkey ────────────────────────────────────────────────────
const HOTKEY_STORAGE_KEY  = "f1radio-hotkey";
const DEFAULT_HOTKEY      = "R";
const isElectron          = Boolean(window.electronAPI?.captureGlobalHotkey);

let configuredHotkey   = DEFAULT_HOTKEY.toLowerCase();
let currentHotkeyDisplay = DEFAULT_HOTKEY;
let keyHeld            = false;
let isCapturingHotkey  = false;

const updateHotkeyDisplay = (display) => {
  if (!display) return;
  currentHotkeyDisplay = display;
  if (hotkeyLabel) hotkeyLabel.textContent = display;
};

const persistFallbackHotkey = (key) => {
  try { localStorage?.setItem(HOTKEY_STORAGE_KEY, key); } catch {}
};

const setFallbackHotkey = (key) => {
  configuredHotkey = (key || DEFAULT_HOTKEY).toLowerCase();
  updateHotkeyDisplay((key || DEFAULT_HOTKEY).toUpperCase());
  persistFallbackHotkey(configuredHotkey);
};

const isConfiguredHotkey = (key) =>
  !isElectron && typeof key === "string" && key.toLowerCase() === configuredHotkey;

const captureFallbackKey = () =>
  new Promise((resolve) => {
    const cleanup = () => {
      window.removeEventListener("keydown", onKey,   true);
      window.removeEventListener("mousedown", onMouse, true);
    };
    const onKey = (e) => { e.preventDefault(); cleanup(); resolve(e.key || e.code || DEFAULT_HOTKEY); };
    const onMouse = (e) => { e.preventDefault(); cleanup(); resolve(`Mouse ${e.button}`); };
    window.addEventListener("keydown",   onKey,   { capture: true, once: true });
    window.addEventListener("mousedown", onMouse, { capture: true, once: true });
  });

const startHotkeyCapture = async () => {
  if (isCapturingHotkey) return;
  isCapturingHotkey = true;
  setStatus("Press any key or button to bind…", true);
  try {
    if (isElectron && window.electronAPI?.captureGlobalHotkey) {
      const result = await window.electronAPI.captureGlobalHotkey();
      if (result?.success && result.config) {
        updateHotkeyDisplay(result.config.display || DEFAULT_HOTKEY);
        setStatus(sessionActive ? "Ready" : "Waiting for race session…");
      } else {
        setStatus("Could not bind hotkey.");
      }
    } else {
      const key = await captureFallbackKey();
      setFallbackHotkey(key);
      setStatus(sessionActive ? "Ready" : "Waiting for race session…");
    }
  } catch (err) {
    console.error("Hotkey capture failed", err);
    setStatus("Hotkey capture failed.");
  } finally {
    isCapturingHotkey = false;
  }
};

const initHotkey = async () => {
  if (isElectron && window.electronAPI?.getGlobalHotkey) {
    const cfg = await window.electronAPI.getGlobalHotkey();
    if (cfg?.display) { updateHotkeyDisplay(cfg.display); return; }
  }
  const stored = localStorage?.getItem(HOTKEY_STORAGE_KEY);
  setFallbackHotkey(stored || DEFAULT_HOTKEY);
};

// ── Audio context ─────────────────────────────────────────────
const SAMPLE_RATE = 48000;
let audioContext;
let nextPlaybackTime = 0;
let _audioAbort = null;
const _activeSources = new Set();

const getAudioContext = () => {
  if (audioContext) return audioContext;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  audioContext = new Ctx({ sampleRate: SAMPLE_RATE });
  return audioContext;
};

const ensureAudioContextActive = async () => {
  const ctx = getAudioContext();
  if (ctx.state === "suspended") await ctx.resume();
  return ctx;
};

const stopAudio = () => {
  if (_audioAbort) { _audioAbort.abort(); _audioAbort = null; }
  for (const src of _activeSources) {
    try { src.stop(); } catch {}
  }
  _activeSources.clear();
  nextPlaybackTime = 0;
};

const convertPcmToFloat32 = (chunk) => {
  const length = chunk.byteLength & ~1;
  if (length === 0) return null;
  const samples = new Int16Array(chunk.buffer, chunk.byteOffset, length / 2);
  const float32 = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    float32[i] = Math.max(-1, Math.min(1, samples[i] / 0x8000));
  }
  return float32;
};

const scheduleChunkPlayback = (float32) => {
  const ctx = getAudioContext();
  const buf = ctx.createBuffer(1, float32.length, SAMPLE_RATE);
  buf.copyToChannel(float32, 0, 0);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(ctx.destination);
  const startTime = Math.max(ctx.currentTime, nextPlaybackTime);
  src.start(startTime);
  nextPlaybackTime = startTime + buf.duration;
  _activeSources.add(src);
  src.onended = () => _activeSources.delete(src);
};

const streamAgentAudio = async (text) => {
  stopAudio();
  await ensureAudioContextActive();
  nextPlaybackTime = Math.max(nextPlaybackTime, audioContext.currentTime);

  const controller = new AbortController();
  _audioAbort = controller;

  let resp;
  try {
    resp = await fetch(`/tts?text=${encodeURIComponent(text)}`, { signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") return;
    throw err;
  }
  if (!resp.ok) throw new Error("TTS stream failed");
  const reader = resp.body?.getReader();
  if (!reader) throw new Error("Readable stream not supported");

  let pending = new Uint8Array(0);
  const MIN_BYTES = 4096;

  const drain = (force = false) => {
    while (pending.length >= MIN_BYTES || (force && pending.length >= 2)) {
      const usable = pending.length & ~1;
      if (usable === 0) break;
      const chunk = pending.slice(0, usable);
      pending = pending.slice(usable);
      const f32 = convertPcmToFloat32(chunk);
      if (f32) scheduleChunkPlayback(f32);
    }
  };

  const append = (chunk) => {
    const merged = new Uint8Array(pending.length + chunk.length);
    merged.set(pending);
    merged.set(chunk, pending.length);
    pending = merged;
  };

  try {
    while (true) {
      if (controller.signal.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      if (value) { append(value); drain(); }
    }
    if (!controller.signal.aborted) drain(true);
  } finally {
    if (_audioAbort === controller) _audioAbort = null;
    try { reader.cancel(); } catch {}
  }
};

const playAgentAudio = async (text) => {
  if (!text) return;
  try { await streamAgentAudio(text); } catch (err) { console.error("TTS error", err); }
};

// ── Recording ─────────────────────────────────────────────────
const MIC_DEVICE_KEY       = "f1radio-mic-device";
const MIC_ENHANCEMENT_KEY  = "f1radio-mic-enhancement";
let mediaRecorder;
let audioStream;
let chunks = [];
let _pttStartTimer = null;
let micTestBtn = document.getElementById("mic-test-btn");
let testRecorder = null;
let testChunks = [];
let rnnoiseWorkletLoaded = false;
let rnnoiseNode = null;
let compressorNode = null;
let gainNode = null;
let limiterNode = null;
let recordingStream = null;

const sendRecording = async () => {
  if (chunks.length === 0) { setStatus("No audio captured."); return; }

  const blob = new Blob(chunks, { type: "audio/webm" });
  chunks = [];
  const form = new FormData();
  form.append("audio_data", blob, "recording.webm");

  try {
    setStatus("Transcribing…", true);
    const sttResp = await fetch("/transcribe", { method: "POST", body: form });
    if (sttResp.status === 403) { setStatus("No active race session."); return; }
    if (!sttResp.ok) throw new Error("Server rejected audio");
    const sttPayload = await sttResp.json();

    const transcript = sttPayload.transcript;
    if (!transcript) { setStatus("No speech detected."); return; }

    const player = sttPayload.player ?? {};
    window.electronAPI?.showOverlayDriver({
      driver: player.name || "DRIVER",
      driverText: transcript,
      teamColor: teamColor(player.team),
    });
    setStatus("Thinking…", true);

    const agentBody = { text: transcript };
    if (sttPayload.turn_id) agentBody.turn_id = sttPayload.turn_id;
    const agentResp = await fetch("/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(agentBody),
    });
    if (!agentResp.ok) throw new Error("Agent request failed");
    const agentPayload = await agentResp.json();

    if (agentPayload.agent_reply) {
      window.electronAPI?.updateOverlayEngineer({
        engineerText: agentPayload.display_reply || agentPayload.agent_reply,
      });
      playAgentAudio(agentPayload.agent_reply);
    }
    setStatus("Ready");
  } catch (err) {
    console.error(err);
    setStatus("Error — try again.");
  }
};

const startRecording = () => {
  if (!mediaRecorder || mediaRecorder.state === "recording" || _pttStartTimer) return;
  chunks = [];
  recordBtn.classList.add("recording");
  setStatus("Recording…", true);
  // 120ms delay: lets PTT click/mechanical noise clear before capture starts
  _pttStartTimer = setTimeout(() => {
    _pttStartTimer = null;
    if (mediaRecorder && mediaRecorder.state !== "recording") mediaRecorder.start();
  }, 120);
};

const stopRecording = () => {
  if (_pttStartTimer !== null) {
    // Released within the delay window — cancel before recording even started
    clearTimeout(_pttStartTimer);
    _pttStartTimer = null;
    recordBtn.classList.remove("recording");
    setStatus("");
    return;
  }
  if (!mediaRecorder || mediaRecorder.state !== "recording") return;
  mediaRecorder.stop();
  recordBtn.classList.remove("recording");
};

const populateMicDevices = async () => {
  const sel = document.getElementById("cfg-mic-device");
  if (!sel) return;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const inputs = devices.filter((d) => d.kind === "audioinput");
    const savedId = localStorage.getItem(MIC_DEVICE_KEY) || "";
    sel.innerHTML = "";
    const defaultOpt = document.createElement("option");
    defaultOpt.value = "";
    defaultOpt.textContent = "Default";
    sel.appendChild(defaultOpt);
    inputs.forEach((d, i) => {
      const opt = document.createElement("option");
      opt.value = d.deviceId;
      opt.textContent = d.label || `Microphone ${i + 1}`;
      if (d.deviceId === savedId) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch {}
};

const setupRNNoise = async (ctx, source) => {
  if (!rnnoiseWorkletLoaded) {
    await ctx.audioWorklet.addModule("/rnnoise-processor.js");
    rnnoiseWorkletLoaded = true;
  }
  const node = new AudioWorkletNode(ctx, "rnnoise-processor");
  await new Promise((resolve, reject) => {
    node.port.onmessage = ({ data }) => {
      if (data.type === "ready") resolve();
      if (data.type === "error") reject(new Error(data.message));
    };
    node.port.postMessage({ type: "init" });
  });
  source.connect(node);
  return node;
};

const initRecorder = async (deviceId = "", enhancement = "off") => {
  // Tear down previous Web Audio nodes and stream
  if (rnnoiseNode)    { rnnoiseNode.disconnect();    rnnoiseNode    = null; }
  if (compressorNode) { compressorNode.disconnect(); compressorNode = null; }
  if (gainNode)       { gainNode.disconnect();       gainNode       = null; }
  if (limiterNode)    { limiterNode.disconnect();    limiterNode    = null; }
  if (audioStream) audioStream.getTracks().forEach((t) => t.stop());

  const isStandard = enhancement === "standard";
  const isAI       = enhancement === "ai";

  const audioConstraints = {
    ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
    echoCancellation: isStandard || isAI,
    noiseSuppression: isStandard || isAI,
    autoGainControl:  isStandard || isAI,
  };

  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });

    // Always route through Web Audio: source → [rnnoise] → compressor → gain → dest
    const ctx = getAudioContext();
    if (ctx.state === "suspended") await ctx.resume();
    const source = ctx.createMediaStreamSource(audioStream);
    let chainEnd = source;

    if (isAI) {
      try {
        rnnoiseNode = await setupRNNoise(ctx, source);
        chainEnd = rnnoiseNode;
      } catch (err) {
        console.warn("RNNoise failed, falling back to raw audio:", err);
        rnnoiseNode = null;
      }
    }

    // Compressor: brings up quiet/distant-mic voice, levels out dynamics
    compressorNode = ctx.createDynamicsCompressor();
    compressorNode.threshold.value = -40;  // compress anything above -40 dBFS
    compressorNode.knee.value      = 8;    // soft knee for natural sound
    compressorNode.ratio.value     = 6;    // 6:1 — strong enough for quiet mics
    compressorNode.attack.value    = 0.003; // 3ms — catches consonants without pumping
    compressorNode.release.value   = 0.20;  // 200ms

    // Makeup gain: pushes compressed voice up to ~-18 dBFS target
    gainNode = ctx.createGain();
    gainNode.gain.value = 3.0;  // +10 dB — conservative to avoid clipping

    // Brick-wall limiter: prevents clipping if gain pushes any peak over 0 dBFS
    limiterNode = ctx.createDynamicsCompressor();
    limiterNode.threshold.value = -1;   // engage just below 0 dBFS
    limiterNode.knee.value      = 0;    // hard knee
    limiterNode.ratio.value     = 20;   // near-infinite ratio = true limiter
    limiterNode.attack.value    = 0.001; // 1ms — instantaneous
    limiterNode.release.value   = 0.10;

    const dest = ctx.createMediaStreamDestination();
    chainEnd.connect(compressorNode);
    compressorNode.connect(gainNode);
    gainNode.connect(limiterNode);
    limiterNode.connect(dest);
    recordingStream = dest.stream;

    mediaRecorder = new MediaRecorder(recordingStream, {
      mimeType: "audio/webm;codecs=opus",
      audioBitsPerSecond: 64000,  // bumped from 32kbps — more headroom for quiet voice
    });
    mediaRecorder.addEventListener("dataavailable", (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    });
    mediaRecorder.addEventListener("stop", sendRecording);
    if (micTestBtn) micTestBtn.disabled = false;
    await populateMicDevices();
  } catch (err) {
    console.error(err);
    setStatus("Microphone access denied.");
    recordBtn.disabled = true;
  }
};

// ── Mic test ──────────────────────────────────────────────────
const startMicTest = () => {
  if (!recordingStream || mediaRecorder?.state === "recording") return;
  testChunks = [];
  testRecorder = new MediaRecorder(recordingStream, { mimeType: "audio/webm;codecs=opus" });
  testRecorder.addEventListener("dataavailable", (e) => {
    if (e.data && e.data.size > 0) testChunks.push(e.data);
  });
  testRecorder.addEventListener("stop", () => {
    const blob = new Blob(testChunks, { type: "audio/webm" });
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => URL.revokeObjectURL(url);
    audio.play();
    micTestBtn.textContent = "Hold to Test";
    micTestBtn.classList.remove("recording");
  });
  testRecorder.start();
  micTestBtn.textContent = "Recording…";
  micTestBtn.classList.add("recording");
};

const stopMicTest = () => {
  if (testRecorder?.state === "recording") testRecorder.stop();
};

// ── Session polling ───────────────────────────────────────────
let sessionActive = false;

const applySessionState = (active) => {
  if (active === sessionActive) return;
  sessionActive = active;
  sessionDot?.classList.toggle("active", active);
  if (sessionDot) sessionDot.title = active ? "Race session active" : "Race session inactive";
  if (active) {
    recordBtn.disabled = false;
    setStatus("Ready");
  } else {
    recordBtn.disabled = true;
    if (mediaRecorder?.state === "recording") stopRecording();
    setStatus("Waiting for race session…");
  }
};

const pollSession = async () => {
  try {
    const resp = await fetch("/session-state");
    if (resp.ok) applySessionState(Boolean((await resp.json()).active));
  } catch {}
};

recordBtn.disabled = true;
setStatus("Waiting for race session…");
pollSession();
setInterval(pollSession, 3000);

// ── PTT events ────────────────────────────────────────────────
recordBtn.addEventListener("mousedown", startRecording);
recordBtn.addEventListener("mouseup", stopRecording);
["mouseleave", "touchend", "touchcancel"].forEach((ev) =>
  recordBtn.addEventListener(ev, stopRecording)
);

// ── Electron global hotkey ────────────────────────────────────
const bindElectronHotkey = () => {
  if (!isElectron || !window.electronAPI?.onGlobalHotkey) return;

  window.electronAPI.onHotkeyUpdated((cfg) => {
    if (cfg?.display) updateHotkeyDisplay(cfg.display);
  });

  window.electronAPI.onGlobalHotkey((action) => {
    if (action === "down") {
      keyHeld = true;
      if (mediaRecorder?.state !== "recording") startRecording();
    } else if (action === "up") {
      keyHeld = false;
      if (mediaRecorder?.state === "recording") stopRecording();
    }
  });
};

if (!isElectron) {
  window.addEventListener("keydown", (e) => {
    if (isConfiguredHotkey(e.key) && !keyHeld) { keyHeld = true; startRecording(); e.preventDefault(); }
  });
  window.addEventListener("keyup", (e) => {
    if (isConfiguredHotkey(e.key) && keyHeld) { keyHeld = false; stopRecording(); }
  });
  window.addEventListener("blur", () => {
    if (keyHeld) { keyHeld = false; stopRecording(); }
  });
}

// ── Config / settings ─────────────────────────────────────────
const loadConfigIntoUI = async () => {
  if (!isElectron) return;
  const cfg = await window.electronAPI.getConfig();

  const udpIn    = document.getElementById("cfg-udp-port");
  const serverIn = document.getElementById("cfg-server-port");
  if (udpIn    && typeof cfg.udpPort    === "number") udpIn.value    = cfg.udpPort;
  if (serverIn && typeof cfg.serverPort === "number") serverIn.value = cfg.serverPort;

  const active = Array.isArray(cfg.sessionTypes) ? cfg.sessionTypes : [];
  document.querySelectorAll("#cfg-session-types input[type=checkbox]").forEach((cb) => {
    cb.checked = active.includes(cb.value);
  });

  const side = cfg.overlayPosition ?? "right";
  document.querySelectorAll("input[name='overlay-side']").forEach((r) => {
    r.checked = r.value === side;
  });

  const speedSel = document.getElementById("cfg-dismiss-speed");
  if (speedSel && cfg.overlayDismissSpeed) speedSel.value = cfg.overlayDismissSpeed;

  const calloutSel = document.getElementById("cfg-callouts");
  if (calloutSel && (cfg.engineerCallouts ?? cfg.proactiveEvents))
    calloutSel.value = cfg.engineerCallouts ?? cfg.proactiveEvents;
};

saveBtn?.addEventListener("click", async () => {
  if (!isElectron) return;

  const sessionTypes = Array.from(
    document.querySelectorAll("#cfg-session-types input[type=checkbox]")
  ).filter((cb) => cb.checked).map((cb) => cb.value);

  const overlayPosition =
    document.querySelector("input[name='overlay-side']:checked")?.value ?? "right";

  await window.electronAPI.setConfig({
    udpPort:           parseInt(document.getElementById("cfg-udp-port")?.value, 10)    || 20777,
    serverPort:        parseInt(document.getElementById("cfg-server-port")?.value, 10) || 8080,
    sessionTypes,
    overlayPosition,
    overlayDismissSpeed:  document.getElementById("cfg-dismiss-speed")?.value ?? "normal",
    engineerCallouts:     document.getElementById("cfg-callouts")?.value ?? "critical",
  });

  const original = saveBtn.textContent;
  saveBtn.textContent = "Saved ✓";
  saveBtn.disabled = true;
  setTimeout(() => { saveBtn.textContent = original; saveBtn.disabled = false; }, 1500);
});

hotkeyBtn?.addEventListener("click", startHotkeyCapture);

const savedEnhancement = localStorage.getItem(MIC_ENHANCEMENT_KEY) || "off";
const enhancementSel = document.getElementById("cfg-mic-enhancement");
if (enhancementSel) enhancementSel.value = savedEnhancement;

document.getElementById("cfg-mic-enhancement")?.addEventListener("change", async (e) => {
  const enhancement = e.target.value;
  localStorage.setItem(MIC_ENHANCEMENT_KEY, enhancement);
  await initRecorder(localStorage.getItem(MIC_DEVICE_KEY) || "", enhancement);
});

document.getElementById("cfg-mic-device")?.addEventListener("change", async (e) => {
  const deviceId = e.target.value;
  localStorage.setItem(MIC_DEVICE_KEY, deviceId);
  await initRecorder(deviceId, localStorage.getItem(MIC_ENHANCEMENT_KEY) || "off");
});

micTestBtn?.addEventListener("mousedown", startMicTest);
micTestBtn?.addEventListener("mouseup", stopMicTest);
["mouseleave", "touchend", "touchcancel"].forEach((ev) =>
  micTestBtn?.addEventListener(ev, stopMicTest)
);

// ── Callout SSE ───────────────────────────────────────────────
const connectCalloutStream = () => {
  const es = new EventSource("/callout-stream");
  es.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type !== "callout") return;
      window.electronAPI?.showOverlayDriver({
        driver: "",
        driverText: "",
        teamColor: teamColor(msg.playerTeam),
      });
      if (msg.display_reply) {
        window.electronAPI?.updateOverlayEngineer({ engineerText: msg.display_reply });
      }
      playAgentAudio(msg.engineer_reply);
    } catch {}
  };
  es.onerror = () => {
    es.close();
    setTimeout(connectCalloutStream, 5000);
  };
};
connectCalloutStream();

// ── Init ──────────────────────────────────────────────────────
await initHotkey();
bindElectronHotkey();
await loadConfigIntoUI();
await initRecorder(
  localStorage.getItem(MIC_DEVICE_KEY) || "",
  localStorage.getItem(MIC_ENHANCEMENT_KEY) || "off"
);
