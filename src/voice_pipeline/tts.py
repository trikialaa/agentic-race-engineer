from dotenv import load_dotenv
load_dotenv()

from io import BytesIO
from src import config as _app_config
import audioop
import base64
import json
import logging
import wave
import requests
import os
from pathlib import Path

logger = logging.getLogger(__name__)

INWORLD_API_KEY = os.getenv("INWORLD_API_KEY")
INWORLD_BASE_URL = os.getenv("INWORLD_BASE_URL")

headers = {
    "Authorization": f"Basic {INWORLD_API_KEY}",
    "Content-Type": "application/json",
}


class TTS():

    SAMPLE_RATE = 48000
    CHANNELS = 1
    SAMPLE_WIDTH = 2
    CHUNK_SIZE = 4096
    INTRO_PATH = Path(__file__).resolve().parents[2] / "assets" / "f1radio.wav"

    def __init__(self):
        if not INWORLD_API_KEY:
            raise RuntimeError("INWORLD_API_KEY is not set")
        if not INWORLD_BASE_URL:
            raise RuntimeError("INWORLD_BASE_URL is not set")
        self.voice_id: str = _app_config.get("ttsVoice", "Alex")

    def read_text(self, text):
        pcm_bytes = bytearray()
        for chunk in self.stream_audio(text):
            pcm_bytes.extend(chunk)
        return self._build_wav(pcm_bytes)

    def stream_audio(self, text):
        payload = self._build_payload(text)

        def generator():
            yield from self._intro_stream()
            try:
                with requests.post(INWORLD_BASE_URL, json=payload, headers=headers, stream=True, timeout=(5, 30)) as response:
                    response.raise_for_status()
                    for line in response.iter_lines(decode_unicode=True):
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        result = chunk.get("result")
                        if not result or "audioContent" not in result:
                            continue
                        audio_chunk = base64.b64decode(result["audioContent"])
                        trimmed_chunk = self._trim_wave_header(audio_chunk)
                        if trimmed_chunk:
                            yield trimmed_chunk
            except Exception:
                logger.exception("TTS stream failed")

        return generator()

    def _intro_stream(self):
        if not self.INTRO_PATH.exists():
            return
        try:
            with wave.open(str(self.INTRO_PATH), "rb") as wf:
                data = wf.readframes(wf.getnframes())
                if wf.getsampwidth() != self.SAMPLE_WIDTH:
                    data = audioop.lin2lin(
                        data, wf.getsampwidth(), self.SAMPLE_WIDTH
                    )
                if wf.getnchannels() != self.CHANNELS:
                    if wf.getnchannels() == 2 and self.CHANNELS == 1:
                        data = audioop.tomono(
                            data, self.SAMPLE_WIDTH, 0.5, 0.5
                        )
                    elif wf.getsampwidth() and wf.getnchannels() > 1:
                        sample_stride = wf.getsampwidth() * wf.getnchannels()
                        mono = bytearray()
                        for pos in range(0, len(data), sample_stride):
                            mono.extend(
                                data[pos : pos + wf.getsampwidth()]
                            )
                        data = bytes(mono)
                if wf.getframerate() != self.SAMPLE_RATE:
                    data, _ = audioop.ratecv(
                        data,
                        self.SAMPLE_WIDTH,
                        self.CHANNELS,
                        wf.getframerate(),
                        self.SAMPLE_RATE,
                        None,
                    )
                for idx in range(0, len(data), self.CHUNK_SIZE):
                    yield data[idx : idx + self.CHUNK_SIZE]
        except Exception:
            return

    def _build_payload(self, text):
        return {
            "text": text,
            "voice_id": self.voice_id,
            "audio_config": {
                "audio_encoding": "LINEAR16",
                "sample_rate_hertz": self.SAMPLE_RATE,
            },
            "temperature": 0.55,
            "model_id": str(os.getenv("INWORLD_MODEL"))
        }

    def _trim_wave_header(self, audio_chunk: bytes) -> bytes:
        if len(audio_chunk) < 12 or audio_chunk[:4] != b"RIFF":
            return audio_chunk
        # Walk sub-chunks to find the actual 'data' offset instead of assuming 44 bytes.
        offset = 12  # skip RIFF(4) + file-size(4) + WAVE(4)
        while offset + 8 <= len(audio_chunk):
            chunk_id = audio_chunk[offset:offset + 4]
            chunk_size = int.from_bytes(audio_chunk[offset + 4:offset + 8], "little")
            if chunk_id == b"data":
                return audio_chunk[offset + 8:]
            offset += 8 + chunk_size
        return audio_chunk[44:]  # fallback: standard 44-byte header

    def _build_wav(self, pcm_bytes: bytes) -> BytesIO:
        wav_io = BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(self.CHANNELS)
            wav_file.setsampwidth(self.SAMPLE_WIDTH)
            wav_file.setframerate(self.SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)
        wav_io.seek(0)
        return wav_io
