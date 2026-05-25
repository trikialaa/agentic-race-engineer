from dotenv import load_dotenv
load_dotenv()

import logging
import os
from deepgram import DeepgramClient

logger = logging.getLogger(__name__)

# F1 jargon and all current grid surnames — boosted for Nova-3 recognition
STATIC_KEYTERMS: list[str] = [
    # Race control / strategy
    "DRS", "ERS", "VSC", "safety car", "virtual safety car", "pit", "box",
    "undercut", "overcut", "pit window", "pit stop", "pit lane", "pit wall",
    "fastest lap", "lap time", "sector", "gap", "interval", "delta",
    "option", "prime", "soft", "medium", "hard", "inter", "intermediate", "wet",
    "tyre", "compound", "degradation", "wear", "graining", "blistering",
    "front wing", "rear wing", "floor", "diff", "brake bias",
    "fuel load", "fuel saving", "push", "manage", "backing up",
    # 2024/25/26 grid surnames
    "Verstappen", "Norris", "Leclerc", "Piastri", "Russell", "Hamilton",
    "Alonso", "Sainz", "Perez", "Gasly", "Ocon", "Stroll", "Albon",
    "Bottas", "Zhou", "Magnussen", "Hulkenberg", "Tsunoda", "Lawson",
    "Bearman", "Colapinto", "Doohan", "Antonelli", "Hadjar",
    # 2026 additions
    "Lindblad", "Bortoleto",
]


class STT():

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
