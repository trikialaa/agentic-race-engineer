#!/usr/bin/env python3
"""
Render radio-effect comparison clips so you can pick an intensity by ear.

For each preset (off/light/medium/heavy) this writes a 48 kHz / mono / 16-bit WAV
to an output directory, letting you A/B the dry voice against each radio setting.

Dry voice source (pick one):
    --input clean.wav     apply the effect to an existing clean voice WAV (no API key)
    --text "Box this lap" synthesize a dry clip via Inworld TTS (needs INWORLD_* keys)

Usage:
    python helpers/radio_fx_preview.py --input some_clean_voice.wav
    python helpers/radio_fx_preview.py --text "Box this lap, box box. Mind the front-left."
    python helpers/radio_fx_preview.py --input clip.wav --presets light,medium
    python helpers/radio_fx_preview.py --input clip.wav --out /tmp/samples
"""

from __future__ import annotations

import argparse
import audioop
import sys
import wave
from pathlib import Path

# Make `src` importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.voice_pipeline import radio_fx  # noqa: E402

SAMPLE_RATE = radio_fx.SAMPLE_RATE
CHANNELS = 1
SAMPLE_WIDTH = 2


def _read_wav_as_pcm(path: Path) -> bytes:
    """Load any WAV and return 48 kHz / mono / 16-bit PCM bytes."""
    with wave.open(str(path), "rb") as wf:
        data = wf.readframes(wf.getnframes())
        width, channels, rate = wf.getsampwidth(), wf.getnchannels(), wf.getframerate()
    if width != SAMPLE_WIDTH:
        data = audioop.lin2lin(data, width, SAMPLE_WIDTH)
    if channels == 2:
        data = audioop.tomono(data, SAMPLE_WIDTH, 0.5, 0.5)
    elif channels > 2:
        raise SystemExit(f"Unsupported channel count: {channels}")
    if rate != SAMPLE_RATE:
        data, _ = audioop.ratecv(data, SAMPLE_WIDTH, CHANNELS, rate, SAMPLE_RATE, None)
    return data


def _synthesize_dry_pcm(text: str) -> bytes:
    """Synthesize a dry (FX-off) clip via the TTS client. Needs INWORLD_* keys."""
    from src.voice_pipeline.tts import TTS

    tts = TTS()
    pcm = bytearray()
    for chunk in tts.stream_audio(text, radio_preset="off"):
        pcm.extend(chunk)
    if not pcm:
        raise SystemExit("TTS returned no audio (check INWORLD_* env vars / network).")
    return bytes(pcm)


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render radio-effect comparison clips.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", type=Path, help="Clean voice WAV to color (no API key needed).")
    src.add_argument("--text", type=str, help="Text to synthesize a dry clip via TTS.")
    parser.add_argument(
        "--presets",
        type=str,
        default="off,light,medium,heavy",
        help="Comma-separated presets to render (default: all).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("radio_fx_samples"),
        help="Output directory (default: ./radio_fx_samples).",
    )
    args = parser.parse_args()

    presets = [p.strip().lower() for p in args.presets.split(",") if p.strip()]
    unknown = [p for p in presets if p not in radio_fx.PRESETS]
    if unknown:
        raise SystemExit(
            f"Unknown preset(s): {', '.join(unknown)}. Valid: {', '.join(radio_fx.PRESETS)}"
        )

    if args.input:
        if not args.input.exists():
            raise SystemExit(f"Input file not found: {args.input}")
        stem = args.input.stem
        dry_pcm = _read_wav_as_pcm(args.input)
    else:
        stem = "tts"
        dry_pcm = _synthesize_dry_pcm(args.text)

    args.out.mkdir(parents=True, exist_ok=True)

    print(
        f"Source: {'WAV ' + str(args.input) if args.input else 'TTS text'}  "
        f"({len(dry_pcm) // (SAMPLE_WIDTH * SAMPLE_RATE):.0f}s @ {SAMPLE_RATE} Hz mono)"
    )
    for preset in presets:
        out_path = args.out / f"{stem}__{preset}.wav"
        _write_wav(out_path, radio_fx.process_pcm(dry_pcm, preset))
        params = radio_fx.PRESETS[preset] or {"(dry passthrough)": True}
        print(f"  {preset:7s} -> {out_path}   {params}")


if __name__ == "__main__":
    main()
