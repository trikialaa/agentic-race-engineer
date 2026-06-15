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
const statusEl    = document.getElementById("status");
const recordBtn   = document.getElementById("record-btn");
const hotkeyLabel = document.getElementById("hotkey-label");
const hotkeyBtn   = document.getElementById("hotkey-btn");
const sessionDot  = document.getElementById("session-dot");
const saveBtn     = document.getElementById("save-btn");

// ── Status ────────────────────────────────────────────────────
const setStatus = (text, highlight = false) => {
  statusEl.textContent = text;
  statusEl.classList.toggle("highlight", highlight);
};

// ── Hotkey ────────────────────────────────────────────────────
const HOTKEY_STORAGE_KEY  = "f1radio-hotkey";
const DEFAULT_HOTKEY      = "R";
const isElectron          = Boolean(window.electronAPI?.captureGlobalHotkey);

let configuredHotkey     = DEFAULT_HOTKEY.toLowerCase();
let currentHotkeyDisplay = DEFAULT_HOTKEY;
let keyHeld              = false;
let isCapturingHotkey    = false;

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
    const onKey   = (e) => { e.preventDefault(); cleanup(); resolve(e.key || e.code || DEFAULT_HOTKEY); };
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
const MIC_DEVICE_KEY      = "f1radio-mic-device";
const MIC_ENHANCEMENT_KEY = "f1radio-mic-enhancement";
let mediaRecorder;
let audioStream;
let chunks = [];
let _pttStartTimer = null;
let micTestBtn  = document.getElementById("mic-test-btn");
let testRecorder = null;
let testChunks   = [];
let rnnoiseWorkletLoaded = false;
let rnnoiseNode    = null;
let compressorNode = null;
let gainNode       = null;
let limiterNode    = null;
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

    compressorNode = ctx.createDynamicsCompressor();
    compressorNode.threshold.value = -40;
    compressorNode.knee.value      = 8;
    compressorNode.ratio.value     = 6;
    compressorNode.attack.value    = 0.003;
    compressorNode.release.value   = 0.20;

    gainNode = ctx.createGain();
    gainNode.gain.value = 3.0;

    limiterNode = ctx.createDynamicsCompressor();
    limiterNode.threshold.value = -1;
    limiterNode.knee.value      = 0;
    limiterNode.ratio.value     = 20;
    limiterNode.attack.value    = 0.001;
    limiterNode.release.value   = 0.10;

    const dest = ctx.createMediaStreamDestination();
    chainEnd.connect(compressorNode);
    compressorNode.connect(gainNode);
    gainNode.connect(limiterNode);
    limiterNode.connect(dest);
    recordingStream = dest.stream;

    mediaRecorder = new MediaRecorder(recordingStream, {
      mimeType: "audio/webm;codecs=opus",
      audioBitsPerSecond: 64000,
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

// ── Chart.js setup ────────────────────────────────────────────
const CHART_DEFAULTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 300 },
  plugins: {
    legend: {
      display: true,
      labels: { color: "rgba(255,255,255,0.5)", font: { size: 10 }, boxWidth: 12 },
    },
    tooltip: { mode: "index", intersect: false },
  },
  scales: {
    x: {
      ticks: { color: "rgba(255,255,255,0.4)", font: { size: 10 } },
      grid:  { color: "rgba(255,255,255,0.06)" },
    },
    y: {
      ticks: { color: "rgba(255,255,255,0.4)", font: { size: 10 } },
      grid:  { color: "rgba(255,255,255,0.06)" },
    },
  },
};

const mergeDeep = (base, overrides) => {
  const out = { ...base };
  for (const k of Object.keys(overrides)) {
    if (overrides[k] && typeof overrides[k] === "object" && !Array.isArray(overrides[k])) {
      out[k] = mergeDeep(base[k] ?? {}, overrides[k]);
    } else {
      out[k] = overrides[k];
    }
  }
  return out;
};

// ── Lap-times chart ───────────────────────────────────────────
let lapTimesChart = null;
const lapDataMap  = new Map();  // lapNum → seconds

const initLapTimesChart = () => {
  const canvas = document.getElementById("chart-laptimes");
  if (!canvas || !window.Chart || lapTimesChart) return;
  lapTimesChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "Lap Time (s)",
        data: [],
        borderColor: "#E10600",
        backgroundColor: "rgba(225,6,0,0.12)",
        pointRadius: 3,
        tension: 0.3,
        fill: true,
      }],
    },
    options: mergeDeep(CHART_DEFAULTS, {
      scales: {
        x: { title: { display: true, text: "Lap", color: "rgba(255,255,255,0.3)", font: { size: 9 } } },
        y: { title: { display: true, text: "Seconds", color: "rgba(255,255,255,0.3)", font: { size: 9 } } },
      },
    }),
  });
};

// Parse "1:23.456" → seconds
const parseFormattedLap = (s) => {
  if (!s || typeof s !== "string") return null;
  const parts = s.split(":");
  if (parts.length !== 2) return null;
  const secs = parseInt(parts[0], 10) * 60 + parseFloat(parts[1]);
  return isFinite(secs) && secs > 0 ? secs : null;
};

const updateLapTimesChart = (lapNum, lapSecs) => {
  if (!lapTimesChart || !lapNum || !lapSecs) return;
  if (lapDataMap.has(lapNum)) return;  // dedupe
  lapDataMap.set(lapNum, lapSecs);
  const sorted = [...lapDataMap.entries()].sort((a, b) => a[0] - b[0]);
  lapTimesChart.data.labels = sorted.map(([l]) => `L${l}`);
  lapTimesChart.data.datasets[0].data = sorted.map(([, t]) => Math.round(t * 1000) / 1000);
  lapTimesChart.update("none");
};

// ── Gap chart (rolling time-series) ──────────────────────────
let gapChart = null;
const gapAheadData  = [];
const gapBehindData = [];
const gapLabels     = [];
let gapTickCount    = 0;
const MAX_GAP_POINTS = 60;

const initGapChart = () => {
  const canvas = document.getElementById("chart-gap");
  if (!canvas || !window.Chart || gapChart) return;
  gapChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: gapLabels,
      datasets: [
        {
          label: "Gap Ahead (s)",
          data: gapAheadData,
          borderColor: "#27F4D2",
          backgroundColor: "rgba(39,244,210,0.08)",
          pointRadius: 2,
          tension: 0.35,
          fill: false,
        },
        {
          label: "Gap Behind (s)",
          data: gapBehindData,
          borderColor: "#FF8000",
          backgroundColor: "rgba(255,128,0,0.08)",
          pointRadius: 2,
          tension: 0.35,
          fill: false,
        },
      ],
    },
    options: mergeDeep(CHART_DEFAULTS, {
      scales: {
        y: { title: { display: true, text: "Seconds", color: "rgba(255,255,255,0.3)", font: { size: 9 } } },
      },
    }),
  });
};

const updateGapChart = (ahead, behind) => {
  if (!gapChart) return;
  gapTickCount++;
  gapLabels.push(`${gapTickCount}s`);
  gapAheadData.push(typeof ahead === "number" && ahead >= 0 ? Math.round(ahead * 100) / 100 : null);
  gapBehindData.push(typeof behind === "number" && behind >= 0 ? Math.round(behind * 100) / 100 : null);
  if (gapLabels.length > MAX_GAP_POINTS) {
    gapLabels.shift();
    gapAheadData.shift();
    gapBehindData.shift();
  }
  gapChart.update("none");
};

// ── Tyre wear line chart (rolling, resets on compound change) ─
let tyreChart       = null;
const tyreWearData   = [];
const tyreWearLabels = [];
let tyreTickCount    = 0;
let lastTyreCompound = null;
const MAX_TYRE_POINTS = 120;

const initTyreChart = () => {
  const canvas = document.getElementById("chart-tyre");
  if (!canvas || !window.Chart || tyreChart) return;
  tyreChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: tyreWearLabels,
      datasets: [{
        label: "Wear %",
        data: tyreWearData,
        borderColor: "#FF8000",
        backgroundColor: "rgba(255,128,0,0.12)",
        pointRadius: 1,
        tension: 0.3,
        fill: true,
      }],
    },
    options: mergeDeep(CHART_DEFAULTS, {
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: false } },
        y: {
          min: 0,
          max: 100,
          title: { display: true, text: "Wear %", color: "rgba(255,255,255,0.3)", font: { size: 9 } },
        },
      },
    }),
  });
};

const updateTyreChart = (compound, wearPct) => {
  if (!tyreChart) return;
  tyreTickCount++;
  if (compound && compound !== lastTyreCompound) {
    // New stint — clear series
    tyreWearData.length  = 0;
    tyreWearLabels.length = 0;
    lastTyreCompound = compound;
    tyreChart.data.datasets[0].label = `Wear % (${compound})`;
  }
  tyreWearLabels.push(`${tyreTickCount}s`);
  tyreWearData.push(typeof wearPct === "number" ? Math.round(wearPct * 10) / 10 : null);
  if (tyreWearLabels.length > MAX_TYRE_POINTS) {
    tyreWearLabels.shift();
    tyreWearData.shift();
  }
  tyreChart.update("none");
};

// ── Position-by-lap chart ─────────────────────────────────────
let positionChart = null;
const posDataMap  = new Map();  // lapNum → position

const initPositionChart = () => {
  const canvas = document.getElementById("chart-position");
  if (!canvas || !window.Chart || positionChart) return;
  positionChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "Position",
        data: [],
        borderColor: "#fbbf24",
        backgroundColor: "rgba(251,191,36,0.1)",
        stepped: "before",
        pointRadius: 3,
        fill: true,
      }],
    },
    options: mergeDeep(CHART_DEFAULTS, {
      scales: {
        x: { title: { display: true, text: "Lap", color: "rgba(255,255,255,0.3)", font: { size: 9 } } },
        y: {
          reverse: true,
          min: 1,
          title: { display: true, text: "Position", color: "rgba(255,255,255,0.3)", font: { size: 9 } },
          ticks: { stepSize: 1 },
        },
      },
    }),
  });
};

const updatePositionChart = (lapNum, position) => {
  if (!positionChart || !lapNum || !position) return;
  posDataMap.set(lapNum, position);
  const sorted = [...posDataMap.entries()].sort((a, b) => a[0] - b[0]);
  positionChart.data.labels = sorted.map(([l]) => `L${l}`);
  positionChart.data.datasets[0].data = sorted.map(([, p]) => p);
  positionChart.update("none");
};

const ensureChartsInit = () => {
  if (!window.Chart) return;
  initLapTimesChart();
  initGapChart();
  initTyreChart();
  initPositionChart();
};

// Charts resize when window resizes
const resizeObserver = new ResizeObserver(() => {
  [lapTimesChart, gapChart, tyreChart, positionChart].forEach((c) => {
    if (c) c.resize();
  });
});
const chartGrid = document.getElementById("chart-grid");
if (chartGrid) resizeObserver.observe(chartGrid);

// ── Readout strip ─────────────────────────────────────────────
const setReadout = (id, value) => {
  const el = document.getElementById(id);
  if (el) el.textContent = value ?? "—";
};

const fmtSeconds = (s) => {
  if (s == null || s <= 0) return "—";
  const m = Math.floor(s / 60);
  const rem = (s - m * 60).toFixed(3).padStart(6, "0");
  return m > 0 ? `${m}:${rem}` : `${s.toFixed(3)}`;
};

const fmtGap = (gap) => {
  if (gap == null) return "—";
  if (typeof gap === "string") return gap;
  return `+${gap.toFixed(2)}s`;
};

// context_frame structure:
// { context: { session: { lap: {current, total}, lapsRemaining, phase },
//              player: { id, position: {current}, gap: {frontS, backS},
//                        pace: {lastLapS}, car: {tyre: {compound, ageLaps},
//                        fuel: {deltaLaps}, ersPct} },
//              raceControl: {safetyCar, flag} } }
const updateReadout = (snap) => {
  const cf      = snap.get_context_frame ?? {};
  const strat   = snap.get_strategy ?? {};
  const ctx     = cf.context ?? {};
  const session = ctx.session ?? {};
  const player  = ctx.player ?? {};
  const car     = player.car ?? {};
  const gap     = player.gap ?? {};
  const pace    = player.pace ?? {};
  const pos     = player.position ?? {};
  const rc      = ctx.raceControl ?? {};
  const lapInfo = session.lap ?? {};

  setReadout("ro-position", pos.current != null ? `P${pos.current}` : "—");

  const lap = lapInfo.current;
  const tot = lapInfo.total;
  setReadout("ro-lap", lap != null && tot != null ? `${lap}/${tot}` : lap ?? "—");

  setReadout("ro-last-lap", fmtSeconds(pace.lastLapS));
  setReadout("ro-gap-ahead",  fmtGap(gap.frontS));
  setReadout("ro-gap-behind", fmtGap(gap.backS));

  const compound = car.tyre?.compound ?? strat.currentTyre?.compound ?? "—";
  const age      = car.tyre?.ageLaps  ?? strat.currentTyre?.ageLaps;
  setReadout("ro-tyre", age != null ? `${compound} L${age}` : compound);

  const deltaLaps = car.fuel?.deltaLaps;
  setReadout("ro-fuel", deltaLaps != null
    ? (deltaLaps >= 0 ? `+${deltaLaps.toFixed(1)}` : `${deltaLaps.toFixed(1)}`)
    : "—");

  setReadout("ro-ers", car.ersPct != null ? `${Math.round(car.ersPct)}%` : "—");

  const flag = rc.flag;
  const sc   = rc.safetyCar;
  const flagDisplay = (sc && sc !== "none") ? sc.toUpperCase()
    : (flag && flag !== "none") ? flag.toUpperCase()
    : "—";
  setReadout("ro-flag", flagDisplay);
};

// ── Telemetry poller ──────────────────────────────────────────
let telemInterval = null;
let lastLapForChart = null;

const fetchTelemetry = async () => {
  if (!sessionActive || activeTab !== "telemetry") return;
  try {
    const resp = await fetch("/telemetry");
    if (!resp.ok) return;
    const snap = await resp.json();
    if (!snap.active || snap.stale) return;

    // Update readout strip
    updateReadout(snap);

    // Unpack tool results (keys from fetch_telemetry_snapshot)
    const cf    = snap.get_context_frame ?? {};
    const strat = snap.get_strategy ?? {};
    const lt    = snap.get_lap_times ?? {};

    const ctx     = cf.context ?? {};
    const session = ctx.session ?? {};
    const player  = ctx.player ?? {};
    const car     = player.car ?? {};
    const gap     = player.gap ?? {};
    const pos     = player.position ?? {};
    const lapInfo = session.lap ?? {};

    const lapNum  = lapInfo.current;
    const position = pos.current;

    // Lap time chart — find player's row by carId, read mostRecent.lap string
    const playerId = player.id;
    if (playerId != null && lapNum != null && lapNum !== lastLapForChart) {
      const lapRows = lt.lapTimes ?? [];
      const myRow   = lapRows.find((r) => r.carId === playerId);
      const lapStr  = myRow?.mostRecent?.lap;   // "1:23.456"
      const lapSecs = parseFormattedLap(lapStr);
      if (lapSecs) {
        updateLapTimesChart(lapNum - 1, lapSecs);  // record completed lap N-1
        lastLapForChart = lapNum;
      }
    }

    // Position chart (lap-indexed)
    if (lapNum && position) updatePositionChart(lapNum, position);

    // Gap chart (rolling)
    updateGapChart(gap.frontS ?? null, gap.backS ?? null);

    // Tyre wear chart (rolling, resets on stint change)
    const compound = car.tyre?.compound ?? strat.currentTyre?.compound;
    const wear     = strat.currentTyre?.wear ?? null;  // single int 0–100
    updateTyreChart(compound, wear);
  } catch (err) {
    console.debug("Telemetry poll error:", err);
  }
};

const startTelemPoller = () => {
  if (telemInterval) return;
  telemInterval = setInterval(fetchTelemetry, 1000);
  fetchTelemetry();  // immediate first poll
};

const stopTelemPoller = () => {
  if (telemInterval) { clearInterval(telemInterval); telemInterval = null; }
};

// ── Tab controller ────────────────────────────────────────────
let activeTab      = "config";
let userOverrideTab = false;

const switchTab = (name, isUserAction = false) => {
  if (name === activeTab && !isUserAction) return;
  if (isUserAction) userOverrideTab = true;
  activeTab = name;

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === name);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tab === name);
  });

  if (name === "telemetry") {
    ensureChartsInit();
    startTelemPoller();
  } else {
    stopTelemPoller();
  }
};

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab, true));
});

// ── Session polling + auto-tab ────────────────────────────────
let sessionActive  = false;
let sessionEnded   = false;
let reportFetched  = false;

const applySessionState = (active, phase, ended) => {
  const wasActive = sessionActive;
  const wasEnded  = sessionEnded;  // capture before update
  sessionActive = active;
  sessionEnded  = Boolean(ended);

  sessionDot?.classList.toggle("active", active);
  if (sessionDot) sessionDot.title = active ? "Race session active" : "Race session inactive";

  if (active) {
    recordBtn.disabled = false;
    setStatus("Ready");
  } else {
    recordBtn.disabled = true;
    if (mediaRecorder?.state === "recording") stopRecording();
    if (!sessionEnded) setStatus("Waiting for race session…");
  }

  // Auto-tab switching — only when user hasn't manually overridden
  if (!userOverrideTab) {
    if (active && !wasActive) {
      // New session started → go to telemetry, reset per-session flags
      userOverrideTab = false;
      reportFetched   = false;
      switchTab("telemetry");
    } else if (sessionEnded && !wasEnded) {
      // Race just ended → go to report
      switchTab("report");
    }
  }

  // Fetch report whenever race ends (regardless of which tab is showing)
  // Don't reset reportFetched here — fetchAndRenderReport handles retries internally
  if (sessionEnded && !wasEnded && !reportFetched) {
    reportFetched = true;
    fetchAndRenderReport();
  }

  // Reset override flag only (not reportFetched) when session goes inactive —
  // the report may have just been triggered this same tick and shouldn't be cancelled
  if (!active && wasActive) {
    userOverrideTab = false;
  }

  // "No session" overlay on telemetry tab
  const telemPanel = document.getElementById("tab-telemetry");
  telemPanel?.classList.toggle("no-session", !active);
};

const pollSession = async () => {
  try {
    const resp = await fetch("/session-state");
    if (resp.ok) {
      const data = await resp.json();
      applySessionState(Boolean(data.active), data.phase ?? "", Boolean(data.ended));
    }
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
    udpPort:             parseInt(document.getElementById("cfg-udp-port")?.value, 10)    || 20777,
    serverPort:          parseInt(document.getElementById("cfg-server-port")?.value, 10) || 8080,
    sessionTypes,
    overlayPosition,
    overlayDismissSpeed: document.getElementById("cfg-dismiss-speed")?.value ?? "normal",
    engineerCallouts:    document.getElementById("cfg-callouts")?.value ?? "critical",
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

// ── Post-Race Report renderer ─────────────────────────────────
const TYRE_CLASS   = { Soft: "S", Medium: "M", Hard: "H", Inter: "I", Wet: "W" };
const EVENT_LABELS = { FTLP: "Fastest Lap", PENA: "Penalty", RTMT: "Retirement", RCWN: "Race Winner" };

const renderReport = (data) => {
  const noData     = document.getElementById("report-no-data");
  const table      = document.getElementById("report-table");
  const tbody      = document.getElementById("report-table-body");
  const evWrap     = document.getElementById("report-events-wrap");
  const evList     = document.getElementById("report-events-list");
  const playerCard = document.getElementById("report-player-card");
  const subLabel   = document.getElementById("report-session-label");

  if (!data?.available || !Array.isArray(data.results) || data.results.length === 0) {
    if (noData) noData.style.display = "";
    return;
  }

  if (noData) noData.style.display = "none";

  // Player highlight card
  const player = data.results.find((r) => r.isPlayer);
  if (player && playerCard) {
    const delta = player.positionChange;
    const deltaStr   = delta == null ? "" : delta > 0 ? `▲${delta}` : delta < 0 ? `▼${Math.abs(delta)}` : "=";
    const deltaClass = delta == null ? "same" : delta > 0 ? "gained" : delta < 0 ? "lost" : "same";
    playerCard.innerHTML = `
      <div class="rpc-pos">P${player.position}</div>
      <div class="rpc-meta">
        <div class="rpc-name">${player.name}</div>
        <div class="rpc-detail">${player.team} · Best ${player.bestLapTime ?? "—"} · ${player.numPitStops ?? 0} stop${(player.numPitStops ?? 0) !== 1 ? "s" : ""}</div>
      </div>
      ${deltaStr ? `<div class="rpc-change ${deltaClass}">${deltaStr}</div>` : ""}
    `;
    playerCard.style.display = "flex";
  }

  if (subLabel) subLabel.textContent = `${data.results.length} classified`;

  // Results table
  if (table && tbody) {
    tbody.innerHTML = "";
    data.results.forEach((r) => {
      const delta      = r.positionChange;
      const deltaStr   = delta == null ? "" : delta > 0 ? `+${delta}` : `${delta}`;
      const deltaClass = delta == null ? "" : delta > 0 ? "pos-gained" : delta < 0 ? "pos-lost" : "";
      const tyreStr = (r.tyreStints ?? []).map((s) => {
        const code = TYRE_CLASS[s.compound] ?? s.compound?.[0] ?? "?";
        return `<span class="tyre-pill tyre-${code}">${code}</span>`;
      }).join("");
      const tr = document.createElement("tr");
      if (r.isPlayer) tr.classList.add("is-player");
      tr.innerHTML = `
        <td>${r.position}</td>
        <td>${r.name}</td>
        <td style="font-size:0.7rem;color:rgba(255,255,255,0.55)">${r.team}</td>
        <td class="${deltaClass}">${deltaStr}</td>
        <td>${r.bestLapTime ?? "—"}</td>
        <td>${r.numPitStops ?? 0}</td>
        <td>${tyreStr || "—"}</td>
      `;
      tbody.appendChild(tr);
    });
    table.style.display = "";
  }

  // Notable events
  if (evWrap && evList && Array.isArray(data.notableEvents) && data.notableEvents.length) {
    evList.innerHTML = "";
    data.notableEvents.forEach((ev) => {
      const li = document.createElement("li");
      if (ev.involvesPlayer) li.classList.add("player-event");
      li.textContent = EVENT_LABELS[ev.code] ?? ev.eventName ?? ev.code;
      evList.appendChild(li);
    });
    evWrap.style.display = "";
  }
};

const fetchAndRenderReport = async (attempt = 0) => {
  try {
    const resp = await fetch("/race-report");
    if (!resp.ok) return;
    const data = await resp.json();
    if (data?.available) {
      renderReport(data);
    } else if (attempt < 5) {
      // Final classification packet may not have arrived yet — retry with backoff
      setTimeout(() => fetchAndRenderReport(attempt + 1), 3000 * (attempt + 1));
    }
  } catch {}
};

// ── Init ──────────────────────────────────────────────────────
await initHotkey();
bindElectronHotkey();
await loadConfigIntoUI();
await initRecorder(
  localStorage.getItem(MIC_DEVICE_KEY) || "",
  localStorage.getItem(MIC_ENHANCEMENT_KEY) || "off"
);
