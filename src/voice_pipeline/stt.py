from dotenv import load_dotenv

load_dotenv()

import logging
import os

from deepgram import DeepgramClient

logger = logging.getLogger(__name__)

# F1 jargon and all current grid surnames — boosted for Nova-3 recognition
STATIC_KEYTERMS: list[str] = [
    # Race control / strategy
    "box",
    "box box",
    "DRS",
    "ERS",
    "VSC",
    "safety car",
    "undercut",
    "overcut",
    "pit window",
    "soft",
    "medium",
    "hard",
    "inter",
    "intermediate",
    "tyre",
    "degradation",
    "graining",
    "gap",
    "interval",
    "delta",
    "sector",
    "fuel load",
    "fuel saving",
    "brake bias",
    "radio check",
    "lap"
    # Surnames (unique / phonetically tricky)
    "Verstappen",
    "Norris",
    "Leclerc",
    "Piastri",
    "Russell",
    "Hamilton",
    "Alonso",
    "Sainz",
    "Perez",
    "Gasly",
    "Ocon",
    "Stroll",
    "Albon",
    "Bottas",
    "Magnussen",
    "Hulkenberg",
    "Tsunoda",
    "Lawson",
    "Bearman",
    "Colapinto",
    "Doohan",
    "Antonelli",
    "Hadjar",
    "Lindblad",
    "Bortoleto",
    # First names that are ambiguous or uncommon
    "Oscar",
    "Lando",
    "Guanyu",
    "Isack",
    "Kimi",
    "Yuki",
]


class STT:
    def __init__(self):
        self.client = DeepgramClient()
        self.model = os.getenv("DEEPGRAM_MODEL", "nova-3")

    def transcribe_audio(self, audio_bytes, extra_keyterms: list[str] | None = None):
        keyterms = list(STATIC_KEYTERMS)
        if extra_keyterms:
            # Deduplicate while preserving order
            seen = set(keyterms)
            for term in extra_keyterms:
                if term and term not in seen:
                    keyterms.append(term)
                    seen.add(term)
        for attempt in range(2):
            try:
                response = self.client.listen.v1.media.transcribe_file(
                    request=audio_bytes,
                    model=self.model,
                    language="en",
                    smart_format=True,
                    keyterm=keyterms,
                )
                return response.results.channels[0].alternatives[0].transcript or None
            except Exception:
                if attempt == 0:
                    logger.warning("STT transcription failed on first attempt, retrying")
                else:
                    logger.exception("STT transcription failed after retry")
        return None
