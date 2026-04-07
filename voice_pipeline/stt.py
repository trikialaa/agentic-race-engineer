from dotenv import load_dotenv
load_dotenv()

from deepgram import DeepgramClient

class STT():

    def __init__(self):
        self.client = DeepgramClient()

    def transcribe_audio(self, audio_bytes):
        response = self.client.listen.v1.media.transcribe_file(
            request=audio_bytes,
            model="nova-3",
            smart_format=True,
        )
        return response.results.channels[0].alternatives[0].transcript