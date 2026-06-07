"use strict";

// RNNoise processes exactly 480 samples per frame at 48 kHz (10 ms).
const FRAME_SIZE = 480;
// Ring buffer capacity: 4 frames should be more than enough headroom.
const RING_CAP = FRAME_SIZE * 4;

// Load the Emscripten glue from the same origin (copied by scripts/copy-wasm.js).
// importScripts is synchronous and runs before the class is instantiated.
try {
  importScripts("/rnnoise.js");
} catch (e) {
  // Will surface as 'error' message when port receives 'init'.
}

class RNNoiseProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // Input staging buffer — accumulate until we have a full frame.
    this._inBuf    = new Float32Array(FRAME_SIZE);
    this._inBufLen = 0;

    // Output ring buffer — holds processed samples waiting to be written.
    this._ring      = new Float32Array(RING_CAP);
    this._ringRead  = 0;
    this._ringWrite = 0;
    this._ringCount = 0;

    this._mod   = null; // Emscripten module
    this._state = 0;    // rnnoise state pointer
    this._inPtr = 0;
    this._outPtr = 0;
    this._ready = false;

    this.port.onmessage = async ({ data }) => {
      if (data.type !== "init") return;
      try {
        if (typeof createRNNWasmModule === "undefined") throw new Error("rnnoise.js failed to load");
        // locateFile tells Emscripten where to find rnnoise.wasm in AudioWorklet scope
        // (no document.currentScript available here).
        const mod = await createRNNWasmModule({ locateFile: (f) => `/${f}` });
        this._mod    = mod;
        this._inPtr  = mod._malloc(FRAME_SIZE * 4);
        this._outPtr = mod._malloc(FRAME_SIZE * 4);
        this._state  = mod._rnnoise_create(0);
        this._ready  = true;
        this.port.postMessage({ type: "ready" });
      } catch (err) {
        this.port.postMessage({ type: "error", message: err.message });
      }
    };
  }

  _ringPush(samples) {
    for (let i = 0; i < samples.length; i++) {
      if (this._ringCount < RING_CAP) {
        this._ring[this._ringWrite] = samples[i];
        this._ringWrite = (this._ringWrite + 1) % RING_CAP;
        this._ringCount++;
      }
    }
  }

  _ringDrain(output) {
    const len = Math.min(this._ringCount, output.length);
    for (let i = 0; i < len; i++) {
      output[i] = this._ring[this._ringRead];
      this._ringRead = (this._ringRead + 1) % RING_CAP;
      this._ringCount--;
    }
    // Silence-pad if the ring doesn't have enough yet (startup latency).
    for (let i = len; i < output.length; i++) output[i] = 0;
  }

  _processFrame() {
    const mod     = this._mod;
    const heap    = mod.HEAPF32;
    const inBase  = this._inPtr  >> 2;
    const outBase = this._outPtr >> 2;

    // RNNoise expects the range ±32768, not ±1.
    for (let i = 0; i < FRAME_SIZE; i++) heap[inBase + i] = this._inBuf[i] * 32768;
    mod._rnnoise_process_frame(this._state, this._outPtr, this._inPtr);
    const out = new Float32Array(FRAME_SIZE);
    for (let i = 0; i < FRAME_SIZE; i++) out[i] = heap[outBase + i] / 32768;
    this._ringPush(out);
  }

  process(inputs, outputs) {
    const input  = inputs[0]?.[0];
    const output = outputs[0]?.[0];
    if (!output) return true;

    if (!this._ready || !input?.length) {
      if (input) output.set(input);
      return true;
    }

    // Feed input into the staging buffer, flushing full frames to RNNoise.
    let srcOffset = 0;
    while (srcOffset < input.length) {
      const toCopy = Math.min(FRAME_SIZE - this._inBufLen, input.length - srcOffset);
      this._inBuf.set(input.subarray(srcOffset, srcOffset + toCopy), this._inBufLen);
      this._inBufLen += toCopy;
      srcOffset += toCopy;
      if (this._inBufLen === FRAME_SIZE) {
        this._processFrame();
        this._inBufLen = 0;
      }
    }

    this._ringDrain(output);
    return true;
  }
}

registerProcessor("rnnoise-processor", RNNoiseProcessor);
