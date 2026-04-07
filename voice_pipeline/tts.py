from dotenv import load_dotenv
load_dotenv()

from io import BytesIO
import base64
import json
import wave
import requests
import os

INWORLD_API_KEY = os.getenv("INWORLD_API_KEY")
INWORLD_BASE_URL = os.getenv("INWORLD_BASE_URL")

if not INWORLD_API_KEY:
    raise RuntimeError("INWORLD_API_KEY is not set")
if not INWORLD_BASE_URL:
    raise RuntimeError("INWORLD_BASE_URL is not set")

headers = {
    "Authorization": f"Basic {INWORLD_API_KEY}",
    "Content-Type": "application/json",
}


class TTS():

    SAMPLE_RATE = 48000
    CHANNELS = 1
    SAMPLE_WIDTH = 2

    def __init__(self):
        pass

    def read_text(self, text):
        pcm_bytes = bytearray()
        for chunk in self.stream_audio(text):
            pcm_bytes.extend(chunk)
        return self._build_wav(pcm_bytes)

    def stream_audio(self, text):
        payload = self._build_payload(text)

        def generator():
            with requests.post(INWORLD_BASE_URL, json=payload, headers=headers, stream=True) as response:
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

        return generator()

    def _build_payload(self, text):
        return {
            "text": text,
            "voice_id": "Alex",
            "audio_config": {
                "audio_encoding": "LINEAR16",
                "sample_rate_hertz": self.SAMPLE_RATE,
            },
            "temperature": 0.74,
            "model_id": str(os.getenv("INWORLD_MODEL"))
        }

    def _trim_wave_header(self, audio_chunk: bytes) -> bytes:
        if len(audio_chunk) >= 12 and audio_chunk[:4] == b"RIFF":
            return audio_chunk[44:]
        return audio_chunk

    def _build_wav(self, pcm_bytes: bytes) -> BytesIO:
        wav_io = BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(self.CHANNELS)
            wav_file.setsampwidth(self.SAMPLE_WIDTH)
            wav_file.setframerate(self.SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)
        wav_io.seek(0)
        return wav_io
