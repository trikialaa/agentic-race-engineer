#!/usr/bin/env python3
"""
Analyze a session recording directory: audio quality, STT confidence, and transcript comparison.

Usage:
    python helpers/analyze_recording.py <recording_dir>
    python helpers/analyze_recording.py recordings/20260611_183537
    python helpers/analyze_recording.py recordings/20260611_183537 --plots
    python helpers/analyze_recording.py recordings/20260611_183537 --retranscribe
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import av
import librosa
import numpy as np

# ── Audio decoding ─────────────────────────────────────────────────────────────


def decode_webm(path: Path) -> tuple[np.ndarray, int]:
    """Decode a webm/opus file to float32 mono PCM. Returns (samples, sample_rate)."""
    container = av.open(str(path))
    chunks = []
    sr = 48000
    for stream in container.streams.audio:
        sr = stream.sample_rate
        break
    for frame in container.decode(audio=0):
        arr = frame.to_ndarray().astype(np.float32)
        if arr.ndim > 1:
            arr = arr.mean(axis=0)  # mix to mono
        chunks.append(arr)
    container.close()
    if not chunks:
        return np.array([], dtype=np.float32), sr
    return np.concatenate(chunks), sr


# ── Per-file metrics ───────────────────────────────────────────────────────────


def analyze_audio(pcm: np.ndarray, sr: int) -> dict:
    if len(pcm) == 0:
        return {"duration_s": 0.0, "empty": True}

    duration = len(pcm) / sr

    # RMS energy (overall loudness, -inf to 0 dBFS)
    rms = float(np.sqrt(np.mean(pcm ** 2)))
    rms_db = float(20 * np.log10(rms + 1e-9))

    # Peak amplitude
    peak = float(np.abs(pcm).max())
    peak_db = float(20 * np.log10(peak + 1e-9))

    # Frame-level RMS to find silence / low-energy regions
    frame_len = int(sr * 0.025)   # 25ms frames
    hop_len   = int(sr * 0.010)   # 10ms hop
    rms_frames = librosa.feature.rms(y=pcm, frame_length=frame_len, hop_length=hop_len)[0]
    rms_frames_db = 20 * np.log10(rms_frames + 1e-9)

    silence_threshold_db = -40.0
    silence_ratio = float(np.mean(rms_frames_db < silence_threshold_db))

    # Leading silence — how long before first voiced frame
    voiced_frames = np.where(rms_frames_db > silence_threshold_db)[0]
    leading_silence_s = float(voiced_frames[0] * hop_len / sr) if len(voiced_frames) > 0 else duration

    # Trailing silence
    trailing_silence_s = float((len(rms_frames) - voiced_frames[-1] - 1) * hop_len / sr) if len(voiced_frames) > 0 else 0.0

    # Spectral centroid — where most energy sits (Hz); voice is 300–3000 Hz
    centroid = librosa.feature.spectral_centroid(y=pcm, sr=sr)[0]
    mean_centroid_hz = float(np.mean(centroid))

    # Zero-crossing rate — high in noisy/unvoiced segments
    zcr = librosa.feature.zero_crossing_rate(y=pcm, frame_length=frame_len, hop_length=hop_len)[0]
    mean_zcr = float(np.mean(zcr))

    # SNR estimate: voiced-frame RMS vs silence-frame RMS
    voiced_rms = rms_frames[rms_frames_db > silence_threshold_db]
    silent_rms  = rms_frames[rms_frames_db <= silence_threshold_db]
    snr_db: float | None = None
    if len(voiced_rms) > 0 and len(silent_rms) > 0:
        snr_db = float(20 * np.log10((voiced_rms.mean() + 1e-9) / (silent_rms.mean() + 1e-9)))

    # Clipping detection — samples within 1% of full scale
    clip_ratio = float(np.mean(np.abs(pcm) > 0.99))

    return {
        "duration_s": round(duration, 2),
        "rms_db": round(rms_db, 1),
        "peak_db": round(peak_db, 1),
        "silence_ratio": round(silence_ratio, 3),
        "leading_silence_s": round(leading_silence_s, 3),
        "trailing_silence_s": round(trailing_silence_s, 3),
        "mean_centroid_hz": round(mean_centroid_hz, 0),
        "mean_zcr": round(mean_zcr, 4),
        "snr_db": round(snr_db, 1) if snr_db is not None else None,
        "clip_ratio": round(clip_ratio, 5),
        "rms_frames_db": rms_frames_db,  # for plots
        "hop_len": hop_len,
        "sr": sr,
    }


def quality_flags(metrics: dict) -> list[str]:
    flags = []
    if metrics.get("empty"):
        return ["EMPTY — no audio data"]
    if metrics["duration_s"] < 0.5:
        flags.append(f"TOO SHORT ({metrics['duration_s']:.2f}s)")
    if metrics["leading_silence_s"] > 0.15:
        flags.append(f"LEADING SILENCE {metrics['leading_silence_s']*1000:.0f}ms — first word likely clipped")
    if metrics["rms_db"] < -30:
        flags.append(f"LOW VOLUME ({metrics['rms_db']:.0f} dBFS) — may be below Deepgram noise floor")
    if metrics["silence_ratio"] > 0.40:
        flags.append(f"HIGH SILENCE RATIO ({metrics['silence_ratio']*100:.0f}%) — background noise or gaps")
    if metrics["snr_db"] is not None and metrics["snr_db"] < 12:
        flags.append(f"LOW SNR ({metrics['snr_db']:.0f} dB) — background noise masking voice")
    if metrics["mean_centroid_hz"] < 400:
        flags.append(f"LOW SPECTRAL CENTROID ({metrics['mean_centroid_hz']:.0f} Hz) — engine/crowd noise dominating")
    if metrics["clip_ratio"] > 0.001:
        flags.append(f"CLIPPING ({metrics['clip_ratio']*100:.2f}% of samples) — audio too loud/distorted")
    return flags


# ── Retranscription ────────────────────────────────────────────────────────────


def retranscribe(audio_path: Path, keyterms: list[str]) -> tuple[str | None, float | None, list]:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from deepgram import DeepgramClient
        client = DeepgramClient()
        model = os.getenv("DEEPGRAM_MODEL", "nova-3")
        resp = client.listen.v1.media.transcribe_file(
            request=audio_path.read_bytes(),
            model=model,
            language="en",
            smart_format=True,
            keyterm=keyterms,
        )
        alt = resp.results.channels[0].alternatives[0]
        words = getattr(alt, "words", []) or []
        word_confs = [(w.word, round(w.confidence, 3)) for w in words]
        return alt.transcript or None, round(getattr(alt, "confidence", 0) or 0, 3), word_confs
    except Exception as e:
        return f"ERROR: {e}", None, []


# ── Plots ──────────────────────────────────────────────────────────────────────


def save_plot(turn_num: int, pcm: np.ndarray, metrics: dict, out_dir: Path, transcript: str):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        sr = metrics["sr"]
        hop_len = metrics["hop_len"]
        rms_db = metrics["rms_frames_db"]
        t_rms = np.arange(len(rms_db)) * hop_len / sr
        t_pcm = np.linspace(0, len(pcm) / sr, len(pcm))

        fig, axes = plt.subplots(3, 1, figsize=(12, 7), tight_layout=True)
        fig.suptitle(f"Turn {turn_num:02d}: {transcript[:80]}", fontsize=10)

        # Waveform
        axes[0].plot(t_pcm, pcm, linewidth=0.4, color="steelblue")
        axes[0].axhline(0.99, color="red", linewidth=0.8, linestyle="--", label="clip")
        axes[0].axhline(-0.99, color="red", linewidth=0.8, linestyle="--")
        axes[0].set_ylabel("Amplitude")
        axes[0].set_ylim(-1.05, 1.05)
        axes[0].legend(fontsize=7)

        # RMS energy over time
        axes[1].plot(t_rms, rms_db, color="darkorange", linewidth=0.8)
        axes[1].axhline(-40, color="red", linewidth=0.8, linestyle="--", label="-40dB silence threshold")
        axes[1].set_ylabel("RMS (dBFS)")
        axes[1].set_ylim(-80, 5)
        axes[1].legend(fontsize=7)

        # Spectrogram
        D = librosa.amplitude_to_db(np.abs(librosa.stft(pcm, n_fft=1024, hop_length=hop_len)), ref=np.max)
        img = librosa.display.specshow(D, sr=sr, hop_length=hop_len, x_axis="time", y_axis="hz", ax=axes[2])
        axes[2].set_ylim(0, 8000)
        axes[2].set_ylabel("Frequency (Hz)")
        axes[2].axhline(300, color="lime", linewidth=0.6, linestyle="--", alpha=0.7, label="voice band 300Hz")
        axes[2].axhline(3000, color="lime", linewidth=0.6, linestyle="--", alpha=0.7, label="voice band 3kHz")
        axes[2].legend(fontsize=7)
        fig.colorbar(img, ax=axes[2], format="%+2.0f dB")

        out_path = out_dir / f"turn_{turn_num:04d}.png"
        plt.savefig(out_path, dpi=120)
        plt.close(fig)
        return out_path
    except Exception as e:
        return f"plot failed: {e}"


# ── Main ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Analyze a session recording directory.")
    parser.add_argument("recording_dir", type=Path)
    parser.add_argument("--plots", action="store_true", help="Save waveform/spectrogram plots as PNG")
    parser.add_argument("--retranscribe", action="store_true", help="Re-run Deepgram on each audio file")
    parser.add_argument("--only-flagged", action="store_true", help="Only show turns with quality issues")
    args = parser.parse_args()

    rec_dir = args.recording_dir
    interactions_path = rec_dir / "interactions.jsonl"
    if not interactions_path.exists():
        print(f"No interactions.jsonl found in {rec_dir}", file=sys.stderr)
        sys.exit(1)

    turns = [json.loads(line) for line in interactions_path.read_text().splitlines() if line.strip()]
    plots_dir = rec_dir / "plots"
    if args.plots:
        plots_dir.mkdir(exist_ok=True)

    keyterms = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from src.voice_pipeline.stt import STATIC_KEYTERMS
        keyterms = STATIC_KEYTERMS
    except Exception:
        pass

    print(f"\n{'='*80}")
    print(f"Recording: {rec_dir.name}   ({len(turns)} turns)")
    print(f"{'='*80}\n")

    summary_flags: list[tuple[int, list[str]]] = []
    all_metrics: list[dict] = []

    for i, turn in enumerate(turns):
        audio_path = rec_dir / turn["audio_path"]
        turn_num = i + 1
        transcript = turn.get("transcript", "")
        response = turn.get("response", "")
        stt_ms = turn.get("stt_ms")
        llm_ms = turn.get("llm_ms")

        try:
            pcm, sr = decode_webm(audio_path)
            metrics = analyze_audio(pcm, sr)
        except Exception as e:
            metrics = {"duration_s": 0.0, "empty": True, "error": str(e)}
            pcm = np.array([])

        flags = quality_flags(metrics)
        all_metrics.append(metrics)

        retrans = None
        retrans_conf = None
        retrans_words = []
        if args.retranscribe and not metrics.get("empty"):
            retrans, retrans_conf, retrans_words = retranscribe(audio_path, keyterms)

        plot_path = None
        if args.plots and not metrics.get("empty") and len(pcm) > 0:
            plot_path = save_plot(turn_num, pcm, metrics, plots_dir, transcript)

        if args.only_flagged and not flags:
            continue

        dur = metrics.get("duration_s", 0)
        rms = metrics.get("rms_db")
        snr = metrics.get("snr_db")
        lead = metrics.get("leading_silence_s", 0)
        centroid = metrics.get("mean_centroid_hz")

        rms_str = f"{rms:.0f}dBFS" if rms is not None else "?"
        snr_str = f"SNR {snr:.0f}dB" if snr is not None else "SNR ?"
        lead_str = f"lead {lead*1000:.0f}ms"
        cent_str = f"centroid {centroid:.0f}Hz" if centroid is not None else ""

        match_marker = ""
        if retrans is not None:
            match_marker = " ✓" if retrans == transcript else " ✗"

        print(f"Turn {turn_num:02d} | {audio_path.name} | {dur:.2f}s | {rms_str} | {snr_str} | {lead_str} | {cent_str}")
        print(f"  Stored  : {transcript!r}")
        if args.retranscribe:
            print(f"  Retrans : {retrans!r}{match_marker} (conf={retrans_conf})")
            low_words = [(w, c) for w, c in retrans_words if c < 0.80]
            if low_words:
                print(f"  Low conf: {low_words}")
        if response:
            print(f"  Reply   : {response[:100]!r}")
        if stt_ms or llm_ms:
            latency = f"stt={stt_ms:.0f}ms" if stt_ms else ""
            if llm_ms:
                latency += f" llm={llm_ms:.0f}ms"
            print(f"  Latency : {latency}")
        if flags:
            for f in flags:
                print(f"  ⚠ {f}")
            summary_flags.append((turn_num, flags))
        if plot_path:
            print(f"  Plot    : {plot_path}")
        print()

    # Summary
    print(f"{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    valid = [m for m in all_metrics if not m.get("empty")]
    if valid:
        durations = [m["duration_s"] for m in valid]
        rms_vals = [m["rms_db"] for m in valid if m.get("rms_db") is not None]
        snr_vals = [m["snr_db"] for m in valid if m.get("snr_db") is not None]
        leads = [m["leading_silence_s"] for m in valid]
        print(f"Duration   : avg {np.mean(durations):.2f}s  min {min(durations):.2f}s  max {max(durations):.2f}s")
        if rms_vals:
            print(f"RMS volume : avg {np.mean(rms_vals):.1f} dBFS  min {min(rms_vals):.1f}  max {max(rms_vals):.1f}")
        if snr_vals:
            print(f"SNR        : avg {np.mean(snr_vals):.1f} dB  min {min(snr_vals):.1f}  max {max(snr_vals):.1f}")
        if leads:
            print(f"Lead sil.  : avg {np.mean(leads)*1000:.0f}ms  max {max(leads)*1000:.0f}ms")
    print(f"\nTurns with quality flags: {len(summary_flags)}/{len(turns)}")
    for turn_num, flags in summary_flags:
        print(f"  Turn {turn_num:02d}: {' | '.join(flags)}")
    if args.plots:
        print(f"\nPlots saved to: {plots_dir}/")


if __name__ == "__main__":
    main()
