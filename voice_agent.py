import asyncio
import websockets
import json
import pyaudio
import base64
import logging
import os
import ssl
import threading
import time
import numpy as np
from scipy import signal
AUDIO_EFFECTS_AVAILABLE = True
from pydub import AudioSegment
PYDUB_AVAILABLE = True
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load F1 radio beeps from audio file
def load_f1_radio_beeps():
    """Load F1 radio beeps from audio file and convert to PCM16 format."""
    
    # Try different file formats in order of preference
    file_attempts = [
        ("f1radio.wav", "wav"),
        ("f1radio.mp3", "mp3"),
        ("f1radio.raw", "raw")
    ]
    
    for filename, format_type in file_attempts:
        try:
            if not PYDUB_AVAILABLE and format_type != "raw":
                continue
                
            if format_type == "raw":
                # Load raw PCM data directly (no pydub needed)
                try:
                    with open(filename, "rb") as f:
                        raw_data = f.read()
                    logger.info(f"Loaded F1 radio beeps from raw PCM: {len(raw_data)} bytes")
                    return raw_data
                except FileNotFoundError:
                    continue
                    
            elif format_type == "wav":
                # WAV files don't need ffmpeg
                audio = AudioSegment.from_wav(filename)
                
            elif format_type == "mp3":
                # MP3 files need ffmpeg
                audio = AudioSegment.from_mp3(filename)
            
            # Convert to target format
            audio = audio.set_channels(1)  # Mono
            audio = audio.set_frame_rate(24000)  # 24kHz sample rate
            audio = audio.set_sample_width(2)  # 16-bit
            
            # Get raw audio data
            raw_data = audio.raw_data
            logger.info(f"Loaded F1 radio beeps from {filename}: {len(raw_data)} bytes, {len(audio)}ms duration")
            return raw_data
            
        except FileNotFoundError:
            logger.debug(f"{filename} not found, trying next format...")
            continue
        except Exception as e:
            logger.warning(f"Error loading {filename}: {e}")
            continue
    
    # If all attempts failed
    logger.error("Could not load F1 radio beeps from any supported format")
    logger.error("Supported formats: f1radio.wav (recommended), f1radio.mp3 (needs ffmpeg), f1radio.raw")
    logger.error("Convert your f1radio.mp3 to f1radio.wav to avoid ffmpeg dependency")
    return b''

# Load the F1 radio beeps as a constant
F1_RADIO_BEEPS = load_f1_radio_beeps()
logger.info(f"F1_RADIO_BEEPS loaded: {len(F1_RADIO_BEEPS) if F1_RADIO_BEEPS else 0} bytes")


INSTRUCTIONS = f"""
SYSTEM:

You are a Formula One Race Engineer, supporting a player during an F1 game session.  
Your role is to **interpret telemetry data** and **answer the player's questions** clearly, concisely, and in racing context.  

OBJECTIVE:
- Help the player understand telemetry metrics (tyre wear, temperatures, fuel load, ERS deployment, brake balance, wing settings, etc.).
- Give clear explanations of what numbers mean and how they affect lap time, handling, or strategy.
- Suggest adjustments the player can make (driving style, strategy, setup tweaks) to improve performance or preserve tyres/fuel.
- Provide tactical advice (when to pit, how to save ERS, tyre compound choices).

STYLE & TONE:
- Speak like a calm, professional race engineer: short, precise, supportive.
- Avoid overwhelming the player with raw data — summarize and highlight only the most relevant points.
- Always connect telemetry to **driver feel and performance outcome** (e.g. “front-left overheating is why you feel understeer in fast corners”).

CONVERSATION FLOW:
- When the player asks a question, explain *what the telemetry shows*, *why it matters*, and *what action is recommended*.
- If the player asks something vague, politely clarify what metric they want to understand.
- Use real-world racing context in explanations, but adapt to the **F1 game environment** (e.g. ERS modes, fuel mix, tyre life as simulated).
- Always provide **clear, actionable advice** in one or two sentences.

SAFETY:
- If telemetry is missing, corrupted, or contradictory, explain the issue and suggest the most likely interpretation instead of guessing recklessly.
- Never invent car capabilities that aren’t in the F1 game (e.g. illegal setup changes).

SAMPLE RESPONSES:
- “Your rear tyres are at 85% — still usable, but you’ll start losing traction on exits soon. Consider a pit stop within 5 laps.”  
- “Fuel load is +0.8 laps — safe to push for an overtake now.”  
- “ERS is nearly depleted. Switch to Medium mode for 2 laps to recover.”  
- “Front-left tyre is 15°C hotter than ideal, likely from aggressive turn-in. Try easing off steering input in fast corners.”  

---

NOW:
- *Always* start the conversation with these exact words "Radio check, do you copy?".
- Do not ask further questions after the user provides a response to that first question.
- The player will ask you about telemetry or driving strategy during gameplay. Respond as a Race Engineer according to these rules.
"""

KEYBOARD_COMMANDS = """
q: Quit
t: Send text message
a: Send audio message
"""

class AudioHandler:
    """
    Handles audio input and output using PyAudio.
    """
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.audio_buffer = b''
        self.chunk_size = 1024  # Number of audio frames per buffer
        self.format = pyaudio.paInt16  # Audio format (16-bit PCM)
        self.channels = 1  # Mono audio
        self.rate = 24000  # Sampling rate in Hz
        self.is_recording = False

    def start_audio_stream(self, input_device_index=None):
        """
        Start the audio input stream.
        """
        try:
            self.stream = self.p.open(
                format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=input_device_index
            )
            logger.debug("Audio input stream started")
        except Exception as e:
            logger.error(f"Failed to open audio input stream: {e}")
            self.stream = None

    def stop_audio_stream(self):
        """
        Stop the audio input stream.
        """
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            logger.debug("Audio input stream stopped")
            self.stream = None

    def cleanup(self):
        """
        Clean up resources by stopping the stream and terminating PyAudio.
        """
        if self.stream:
            self.stop_audio_stream()
        self.p.terminate()
        logger.debug("PyAudio terminated")

    def start_recording(self):
        """Start continuous recording"""
        self.is_recording = True
        self.audio_buffer = b''
        self.start_audio_stream()

    def stop_recording(self):
        """Stop recording and return the recorded audio"""
        self.is_recording = False
        self.stop_audio_stream()
        return self.audio_buffer

    def record_chunk(self):
        """Record a single chunk of audio"""
        if self.stream and self.is_recording:
            try:
                data = self.stream.read(
                    self.chunk_size,
                    exception_on_overflow=False  # Okay to exceed buffer
                )
                self.audio_buffer += data
                return data
            except Exception as e:
                logger.error(f"Error reading audio chunk: {e}")
                return None
        else:
            logger.debug("Stream is not active or recording has stopped")
        return None



    def apply_radio_effects(self, audio_data):
        """
        Apply realistic F1 radio effects to audio data.
        
        :param audio_data: Raw audio data
        :return: Processed audio data with radio effects
        """
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            
            # Normalize to [-1, 1]
            audio_array = audio_array / 32768.0
            
            # Apply F1 radio effects
            
            # 1. Band-pass filter (300Hz - 3000Hz) - F1 radio frequency range
            nyquist = self.rate / 2
            low_freq = 300 / nyquist
            high_freq = 3000 / nyquist
            b, a = signal.butter(6, [low_freq, high_freq], btype='band')
            audio_array = signal.filtfilt(b, a, audio_array)
            
            # 2. Apply compression (F1 radios are heavily compressed)
            threshold = 0.6
            ratio = 6.0
            audio_array = np.where(
                np.abs(audio_array) > threshold,
                np.sign(audio_array) * (threshold + (np.abs(audio_array) - threshold) / ratio),
                audio_array
            )
            
            # 3. Add slight saturation for radio character (no noise)
            drive = 1.4
            audio_array = np.tanh(audio_array * drive) / drive
            
            # 4. Apply a subtle high-frequency roll-off for authenticity
            high_cut = 2800 / nyquist
            b_hf, a_hf = signal.butter(2, high_cut, btype='low')
            audio_array = signal.filtfilt(b_hf, a_hf, audio_array)
            
            # 5. Final limiting to prevent clipping
            audio_array = np.clip(audio_array, -0.9, 0.9)
            
            # Convert back to int16
            audio_array = (audio_array * 32767).astype(np.int16)
            
            return audio_array.tobytes()
            
        except ImportError:
            logger.warning("scipy/numpy not available, playing audio without radio effects")
            return audio_data
        except Exception as e:
            logger.error(f"Error applying radio effects: {e}")
            return audio_data

    def play_audio(self, audio_data):
        """
        Play audio data with authentic F1 radio effects and beeps from f1radio.mp3.
        
        :param audio_data: Received audio data (AI response)
        """
        def play():
            try:
                # Apply radio effects to the main audio
                processed_audio = self.apply_radio_effects(audio_data)
                
                # Brief silence before and after beeps
                short_silence = b'\x00' * int(self.rate * 0.1 * 2)  # 100ms silence
                
                stream = self.p.open(
                    format=self.format,
                    channels=self.channels,
                    rate=self.rate,
                    output=True
                )
                
                # Play the complete F1 radio transmission sequence
                stream.write(short_silence)      # Brief silence
                
                # Play authentic F1 radio beeps if available
                if F1_RADIO_BEEPS:
                    logger.debug(f"Playing F1 radio beeps: {len(F1_RADIO_BEEPS)} bytes")
                    stream.write(F1_RADIO_BEEPS)  # Authentic F1 radio beeps
                    stream.write(short_silence)   # Brief pause after beeps
                else:
                    logger.warning("F1_RADIO_BEEPS is empty, skipping beeps")
                
                stream.write(processed_audio)    # Main message with radio effects
                
                stream.stop_stream()
                stream.close()
                
            except Exception as e:
                logger.error(f"Error playing audio: {e}")
                # Fallback to original audio without effects
                try:
                    silence = b'\x00' * 2048
                    stream = self.p.open(
                        format=self.format,
                        channels=self.channels,
                        rate=self.rate,
                        output=True
                    )
                    stream.write(silence)
                    stream.write(audio_data)
                    stream.stop_stream()
                    stream.close()
                except Exception as fallback_e:
                    logger.error(f"Fallback audio playback failed: {fallback_e}")

        logger.debug("Playing audio with authentic F1 radio beeps and effects")
        # Use a separate thread for playback to avoid blocking
        playback_thread = threading.Thread(target=play)
        playback_thread.start()

class RealtimeClient:
    """
    Client for interacting with the OpenAI Realtime API via WebSocket.

    Possible events: https://platform.openai.com/docs/api-reference/realtime-client-events
    """
    def __init__(self, instructions, voice="alloy"):
        # WebSocket Configuration
        self.url = "wss://api.openai.com/v1/realtime"  # WebSocket URL
        self.model = "gpt-4o-mini-realtime-preview"
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.ws = None
        self.audio_handler = AudioHandler()
        
        # SSL Configuration (skipping certificate verification)
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        self.audio_buffer = b''  # Buffer for streaming audio responses
        self.instructions = instructions
        self.voice = voice

        # VAD mode (set to None to disable server-side VAD)
        self.session_config = {
            "modalities": ["audio", "text"],
            "instructions": self.instructions,
            "voice": self.voice,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "turn_detection": None,
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "temperature": 0.6
        }

    async def connect(self):
        """
        Connect to the WebSocket server.
        """
        # logger.info(f"Connecting to WebSocket: {self.url}")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }
        
        # NEEDS websockets version < 14.0
        self.ws = await websockets.connect(
            f"{self.url}?model={self.model}",
            extra_headers=headers,
            ssl=self.ssl_context
        )
        logger.info("Successfully connected to OpenAI Realtime API")

        # Configure session
        await self.send_event(
            {
                "type": "session.update",
                "session": self.session_config
            }
        )
        logger.info("Session set up")

        # Send a response.create event to initiate the conversation
        await self.send_event({"type": "response.create"})
        logger.debug("Sent response.create to initiate conversation")

    async def send_event(self, event):
        """
        Send an event to the WebSocket server.
        
        :param event: Event data to send (from the user)
        """
        await self.ws.send(json.dumps(event))
        # logger.debug(f"Event sent - type: {event['type']}")

    async def receive_events(self):
        """
        Continuously receive events from the WebSocket server.
        """
        try:
            async for message in self.ws:
                event = json.loads(message)
                await self.handle_event(event)
        except websockets.ConnectionClosed as e:
            logger.error(f"WebSocket connection closed: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")

    async def handle_event(self, event):
        """
        Handle incoming events from the WebSocket server.
        Possible events: https://platform.openai.com/docs/api-reference/realtime-server-events
        
        :param event: Event data received (from the server).
        """
        event_type = event.get("type")
        # logger.debug(f"Received event type: {event_type}")

        if event_type == "error":
            pass
            # logger.error(f"Error event received: {event['error']['message']}")
        elif event_type == "response.text.delta":
            pass
            # Print text response incrementally
            # print(event["delta"], end="", flush=True)
        elif event_type == "response.audio.delta":
            # Append audio data to buffer
            audio_data = base64.b64decode(event["delta"])
            self.audio_buffer += audio_data
            # logger.debug("Audio data appended to buffer")
        elif event_type == "response.audio.done":
            # Play the complete audio response
            if self.audio_buffer:
                self.audio_handler.play_audio(self.audio_buffer)
                # logger.info("Done playing audio response")
                self.audio_buffer = b''
            else:
                logger.warning("No audio data to play")
        elif event_type == "response.done":
            logger.debug("Response generation completed")
        elif event_type == "conversation.item.created":
            pass
            # logger.debug(f"Conversation item created: {event.get('item')}")
        elif event_type == "input_audio_buffer.speech_started":
            logger.debug("Speech started detected by server VAD")
        elif event_type == "input_audio_buffer.speech_stopped":
            logger.debug("Speech stopped detected by server VAD")
        else:
            pass
            # logger.debug(f"Unhandled event type: {event_type}")

    async def send_text(self, text):
        """
        Send a text message to the WebSocket server.
        
        :param text: Text message to send.
        """
        logger.info(f"Sending text message: {text}")
        event = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": text
                }]
            }
        }
        await self.send_event(event)
        await self.send_event({"type": "response.create"})
        logger.debug(f"Sent text: {text}")

    async def send_audio(self):
        """
        Record and send audio using manual turn detection.
        """
        logger.info("Starting audio recording. Press Enter to stop recording.")
        self.audio_handler.start_recording()
        
        stop_recording = False

        async def wait_for_enter():
            nonlocal stop_recording
            await asyncio.get_event_loop().run_in_executor(None, input)
            stop_recording = True

        try:
            # Start the input listener
            enter_task = asyncio.create_task(wait_for_enter())
            while not stop_recording:
                chunk = self.audio_handler.record_chunk()
                if chunk:
                    # Encode and send audio chunk
                    base64_chunk = base64.b64encode(chunk).decode('utf-8')
                    await self.send_event({
                        "type": "input_audio_buffer.append",
                        "audio": base64_chunk
                    })
                    await asyncio.sleep(0.01)
                else:
                    break

            # Wait for enter_task to complete
            await enter_task

        except Exception as e:
            logger.error(f"Error during audio recording: {e}")
            self.audio_handler.stop_recording()
            logger.debug("Audio recording stopped")

        finally:
            # Stop recording even if an exception occurs
            self.audio_handler.stop_recording()
            logger.debug("Audio recording stopped")
        
        # Commit the audio buffer and send response.create
        # Must commit the buffer manually when not using server-side VAD
        await self.send_event({"type": "input_audio_buffer.commit"})
        logger.debug("Audio buffer committed")
        await self.send_event({"type": "response.create"})
        logger.debug("Sent response.create after committing audio buffer")

    async def run(self):
        """
        Main loop to handle user input and interact with the WebSocket server.
        """
        await self.connect()
        
        # Continuously listen to events in the background
        receive_task = asyncio.create_task(self.receive_events())

        try:
            while True:
                # Get user command input
                command = await asyncio.get_event_loop().run_in_executor(
                    None, input, KEYBOARD_COMMANDS
                )
                if command == 'q':
                    logger.info("Quit command received")
                    break
                elif command == 't':
                    # Get text input from user
                    text = await asyncio.get_event_loop().run_in_executor(
                        None, input, "Enter TEXT message: "
                    )
                    await self.send_text(text)
                elif command == 'a':
                    # Record and send audio
                    await self.send_audio()
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        finally:
            receive_task.cancel()
            await self.cleanup()

    async def cleanup(self):
        """
        Clean up resources by closing the WebSocket and audio handler.
        """
        self.audio_handler.cleanup()
        if self.ws:
            await self.ws.close()

async def main():

    client = RealtimeClient(
        instructions=INSTRUCTIONS,
        voice="ash"
    )
    try:
        await client.run()
    except Exception as e:
        logger.error(f"An error occurred in main: {e}")
    finally:
        logger.info("Main done")

if __name__ == "__main__":
    asyncio.run(main())