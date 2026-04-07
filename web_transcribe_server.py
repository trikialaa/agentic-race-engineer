import asyncio
import logging
import os
import threading
import time
from concurrent.futures import Future, TimeoutError as FuturesTimeoutError

from flask import Flask, Response, jsonify, request, send_from_directory

from voice_pipeline.agent import RaceEngineerAgent
from voice_pipeline.stt import STT
from voice_pipeline.tts import TTS

static_folder = os.path.join(os.path.dirname(__file__), "web_static")
app = Flask(__name__, static_folder=static_folder, static_url_path="")

logging.basicConfig(level=logging.WARN)

stt = STT()
tts_client = TTS()
race_engineer_agent = RaceEngineerAgent()

agent_loop = asyncio.new_event_loop()


def start_agent_loop():
    asyncio.set_event_loop(agent_loop)
    agent_loop.run_forever()


agent_thread = threading.Thread(target=start_agent_loop, daemon=True)
agent_thread.start()


def run_agent_coroutine(coro, timeout: float):
    future: Future = asyncio.run_coroutine_threadsafe(coro, agent_loop)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        future.cancel()
        raise


agent_ready = False


def ensure_agent_ready(timeout: float = 20.0) -> bool:
    global agent_ready
    if agent_ready:
        return True
    try:
        logging.info("Initializing race engineer agent")
        run_agent_coroutine(race_engineer_agent.init_async(), timeout)
        agent_ready = True
        logging.info("Race engineer agent ready")
    except FuturesTimeoutError:
        logging.warning("Agent initialization timed out")
    except Exception as exc:
        logging.warning("Agent initialization failed: %s", exc)
    return agent_ready


def get_agent_reply(transcript: str, timeout: float = 8.0) -> str | None:
    if not ensure_agent_ready():
        return "Race engineer unavailable"
    try:
        return run_agent_coroutine(
            race_engineer_agent.reply_async(transcript), timeout
        )
    except FuturesTimeoutError:
        logging.warning("Race engineer reply timed out")
        return "Race engineer timed out"
    except Exception:
        logging.exception("Agent reply failed")
        return "Race engineer unavailable"


@app.route("/")
def index():
    return send_from_directory(static_folder, "index.html")


@app.route("/transcribe", methods=["POST"])
def transcribe():
    if "audio_data" not in request.files:
        return jsonify({"error": "Missing file field 'audio_data'."}), 400
    audio_file = request.files["audio_data"]
    audio_payload = audio_file.read()
    stt_start = time.perf_counter()
    transcript = stt.transcribe_audio(audio_payload)
    stt_latency_ms = round((time.perf_counter() - stt_start) * 1000, 1)
    agent_reply = None
    llm_latency_ms = None
    if transcript:
        llm_start = time.perf_counter()
        try:
            agent_reply = get_agent_reply(transcript)
        finally:
            llm_latency_ms = round((time.perf_counter() - llm_start) * 1000, 1)
    payload = {
        "transcript": transcript,
        "latency_ms": {
            "stt": stt_latency_ms,
            "llm": llm_latency_ms,
        },
    }
    if agent_reply:
        payload["agent_reply"] = agent_reply
    return jsonify(payload)


@app.route("/tts", methods=["GET"])
def tts():
    text = request.args.get("text", "")
    if not text.strip():
        return jsonify({"error": "Missing 'text' query parameter."}), 400
    audio_stream = tts_client.stream_audio(text)
    return Response(
        audio_stream,
        mimetype="audio/L16; rate=48000; channels=1",
        direct_passthrough=True,
    )


@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(static_folder, path)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    ensure_agent_ready()
    app.run(host="0.0.0.0", port=port)
