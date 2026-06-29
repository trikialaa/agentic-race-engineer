"""Radio / walkie-talkie coloring for TTS PCM audio.

Applies a band-limit + mic-saturation + static-hiss bed to 48 kHz / mono / 16-bit
signed PCM so the race engineer's voice sounds like it's coming over team radio.

The same processing powers two callers:
  * live streaming TTS (src/voice_pipeline/tts.py) — uses ``make_processor`` so the
    bandpass filter state is carried across the streamed chunks, keeping the filter
    continuous instead of resetting every 4096 bytes.
  * offline sample export (helpers/radio_fx_preview.py) — uses ``process_pcm`` on a
    whole clip at once.

DSP is numpy-only (no scipy). The bandpass is a biquad whose coefficients come from
the RBJ "audio EQ cookbook", computed with plain math.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

# Must match the format constants in src/voice_pipeline/tts.py
SAMPLE_RATE = 48000
_INT16_MAX = 32767.0

# Intensity presets. ``off`` is an identity passthrough (also used as the dry
# reference in the sample export). Values are a first-pass starting point — the
# export helper exists so they can be tuned by ear.
PRESETS: dict[str, dict] = {
    "off": {},
    "light": {
        "bp_low": 320.0,
        "bp_high": 3200.0,
        "bp_order": 1,
        "saturation_drive": 1.5,
        "hiss_db": -42.0,
        "output_gain": 1.0,
    },
    # Tight ~350-2800 Hz PA band; bp_high is set above 2800 because cascaded sections pull the -3 dB point down.
    "medium": {
        "bp_low": 300.0,
        "bp_high": 3400.0,
        "bp_order": 2,
        "saturation_drive": 2.2,
        "hiss_db": -36.0,
        "output_gain": 1.0,
    },
    "heavy": {
        "bp_low": 350.0,
        "bp_high": 2800.0,
        "bp_order": 3,
        "saturation_drive": 3.0,
        "hiss_db": -30.0,
        "output_gain": 1.0,
    },
}

DEFAULT_PRESET = "medium"


# Butterworth Q for a flat passband (single 2nd-order section).
_BUTTERWORTH_Q = 0.70710678


def _highpass_coeffs(fc: float, q: float = _BUTTERWORTH_Q, sr: int = SAMPLE_RATE):
    """RBJ cookbook high-pass biquad coefficients (normalized, a0 divided out)."""
    w0 = 2.0 * math.pi * fc / sr
    cos_w0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    b0 = (1.0 + cos_w0) / 2.0
    b1 = -(1.0 + cos_w0)
    b2 = (1.0 + cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def _lowpass_coeffs(fc: float, q: float = _BUTTERWORTH_Q, sr: int = SAMPLE_RATE):
    """RBJ cookbook low-pass biquad coefficients (normalized, a0 divided out)."""
    w0 = 2.0 * math.pi * fc / sr
    cos_w0 = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    b0 = (1.0 - cos_w0) / 2.0
    b1 = 1.0 - cos_w0
    b2 = (1.0 - cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def _bandpass_chain(low_hz: float, high_hz: float, order: int) -> list[_Biquad]:
    """Steep bandpass = `order` cascaded HPF + LPF biquad sections.

    A single 2nd-order section rolls off at only 6 dB/oct, which sounds too gentle.
    Cascading `order` sections each side gives 6*order dB/oct skirts.
    """
    chain: list[_Biquad] = []
    for _ in range(max(1, order)):
        chain.append(_Biquad(_highpass_coeffs(low_hz)))
        chain.append(_Biquad(_lowpass_coeffs(high_hz)))
    return chain


class _Biquad:
    """Direct-form-I biquad that remembers state across calls (for streaming)."""

    def __init__(self, coeffs):
        self.b0, self.b1, self.b2, self.a1, self.a2 = coeffs
        self.x1 = 0.0
        self.x2 = 0.0
        self.y1 = 0.0
        self.y2 = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        # Sample-by-sample is unavoidable for a stateful IIR, but each chunk is
        # ~2048 samples (<1 ms of work) so this stays well inside the TTS budget.
        b0, b1, b2, a1, a2 = self.b0, self.b1, self.b2, self.a1, self.a2
        x1, x2, y1, y2 = self.x1, self.x2, self.y1, self.y2
        out = np.empty_like(x)
        for i in range(x.shape[0]):
            xn = x[i]
            yn = b0 * xn + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            out[i] = yn
            x2 = x1
            x1 = xn
            y2 = y1
            y1 = yn
        self.x1, self.x2, self.y1, self.y2 = x1, x2, y1, y2
        return out


class _PinkNoise:
    """Paul Kellet 'economy' pink-noise generator (stateful across chunks).

    Pink (1/f) noise rolls the harsh high end off white noise, so the static bed
    sounds like a warm open radio channel instead of a bright digital hiss. State
    is carried between calls so the noise is continuous over streamed chunks.
    Output is normalized to ~unit RMS; the caller scales it to the target level.
    """

    # Output std for unit-variance white input (measured), used to normalize.
    _GAIN = 3.08

    def __init__(self) -> None:
        self.b0 = 0.0
        self.b1 = 0.0
        self.b2 = 0.0

    def generate(self, n: int) -> np.ndarray:
        white = np.random.normal(0.0, 1.0, n).astype(np.float32)
        out = np.empty(n, dtype=np.float32)
        b0, b1, b2 = self.b0, self.b1, self.b2
        for i in range(n):
            wi = white[i]
            b0 = 0.99765 * b0 + wi * 0.0990460
            b1 = 0.96300 * b1 + wi * 0.2965164
            b2 = 0.57000 * b2 + wi * 1.0526913
            out[i] = b0 + b1 + b2 + wi * 0.1848
        self.b0, self.b1, self.b2 = b0, b1, b2
        return out / self._GAIN


def _pcm_to_float(pcm: bytes) -> np.ndarray:
    """16-bit signed PCM bytes -> float32 array in [-1, 1]."""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    return samples / _INT16_MAX


def _float_to_pcm(samples: np.ndarray) -> bytes:
    """float array -> clipped 16-bit signed PCM bytes."""
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * _INT16_MAX).astype("<i2").tobytes()


class _RadioProcessor:
    """Stateful per-stream processor: bandpass -> saturation -> hiss bed."""

    def __init__(self, params: dict):
        self._drive = float(params["saturation_drive"])
        self._tanh_norm = math.tanh(self._drive) or 1.0
        # Hiss amplitude relative to full scale, from a dBFS level.
        self._hiss_amp = 10.0 ** (float(params["hiss_db"]) / 20.0)
        self._gain = float(params.get("output_gain", 1.0))
        self._filters = _bandpass_chain(
            params["bp_low"], params["bp_high"], int(params.get("bp_order", 2))
        )
        self._pink = _PinkNoise()

    def __call__(self, pcm: bytes) -> bytes:
        if not pcm:
            return pcm
        x = _pcm_to_float(pcm)
        # 1) band-limit the voice into the walkie-talkie PA band (steep skirts)
        for biquad in self._filters:
            x = biquad.process(x)
        # 2) mic saturation (tanh soft-clip, normalized so quiet stays quiet)
        x = np.tanh(self._drive * x) / self._tanh_norm
        # 3) warm pink-noise static bed (open-channel hiss), normalized to hiss_amp RMS
        if self._hiss_amp > 0.0:
            x = x + self._pink.generate(x.shape[0]) * self._hiss_amp
        if self._gain != 1.0:
            x = x * self._gain
        return _float_to_pcm(x)


def _resolve(preset_name: str | None) -> dict | None:
    """Return params for a preset, or None for off/unknown (passthrough)."""
    params = PRESETS.get((preset_name or "").lower())
    if not params:  # 'off' maps to {} -> falsy -> passthrough
        return None
    return params


def make_processor(preset_name: str | None) -> Callable[[bytes], bytes]:
    """Build a stateful processor closure for streaming.

    Returns an identity passthrough for 'off' or any unknown preset, so callers
    never have to special-case the disabled state.
    """
    params = _resolve(preset_name)
    if params is None:
        return lambda pcm: pcm
    return _RadioProcessor(params)


def process_pcm(pcm: bytes, preset_name: str | None) -> bytes:
    """One-shot processing of a whole clip (used by the offline export helper)."""
    return make_processor(preset_name)(pcm)
