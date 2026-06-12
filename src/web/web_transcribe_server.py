import asyncio
import json
import logging
import os
import queue
import threading
import time
import uuid
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from src.observability.session_recorder import build_recorder, is_active
from src.voice_pipeline.agent import RaceEngineerAgent
from src.voice_pipeline.stt import STT
from src.voice_pipeline.tts import TTS
from src.voice_pipeline.tts_utils import sanitize_for_tts

STATIC_FOLDER = Path(__file__).resolve().parent.parent / "ui" / "web_static"
static_folder = str(STATIC_FOLDER)
app = Flask(__name__, static_folder=static_folder, static_url_path="")

logging.basicConfig(level=logging.WARN)

stt = STT()
tts_client = TTS()

_record_dir = os.environ.get("F1_RECORD_DIR")
_mcp_env: dict[str, str] | None = None
if _record_dir:
    _tool_log = os.environ.get("F1_MCP_TOOL_LOG", str(Path(_record_dir) / "toolcalls.jsonl"))
    _mcp_env = {"F1_RECORD_DIR": _record_dir, "F1_MCP_TOOL_LOG": _tool_log}

_recorder = build_recorder()
race_engineer_agent = RaceEngineerAgent(mcp_env=_mcp_env)

# Thread-safe queue: CalloutMonitor pushes callout messages, SSE endpoint drains them.
callout_queue: queue.Queue = queue.Queue(maxsize=8)
race_engineer_agent.set_callout_queue(callout_queue)

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
        return run_agent_coroutine(race_engineer_agent.reply_async(transcript), timeout)
    except FuturesTimeoutError:
        logging.warning("Race engineer reply timed out")
        return "Race engineer timed out"
    except Exception:
        logging.exception("Agent reply failed")
        return "Race engineer unavailable"


@app.route("/")
def index():
    return send_from_directory(static_folder, "index.html")


@app.route("/session-state", methods=["GET"])
def session_state():
    return jsonify(race_engineer_agent.get_session_info())


@app.route("/transcribe", methods=["POST"])
def transcribe():
    if not race_engineer_agent.is_session_active():
        return jsonify({"error": "No active race session."}), 403
    if "audio_data" not in request.files:
        return jsonify({"error": "Missing file field 'audio_data'."}), 400
    audio_file = request.files["audio_data"]
    audio_payload = audio_file.read()
    stt_start = time.perf_counter()
    transcript = stt.transcribe_audio(
        audio_payload, extra_keyterms=race_engineer_agent.get_stt_keyterms()
    )
    stt_latency_ms = round((time.perf_counter() - stt_start) * 1000, 1)

    turn_id: str | None = None
    if is_active(_recorder) and transcript:
        turn_id = str(uuid.uuid4())
        audio_rel, audio_abs = _recorder.next_turn_audio_path()
        _recorder.record_turn_audio(audio_abs, audio_payload)
        context_snapshot: dict = {}
        frame: int | None = None
        try:
            raw_snapshot = run_agent_coroutine(
                race_engineer_agent._fetch_context_frame(), timeout=2.0
            )
            import json as _json

            context_snapshot = _json.loads(raw_snapshot) if isinstance(raw_snapshot, str) else {}
            frame = (context_snapshot.get("meta") or {}).get("frame")
        except Exception:
            pass
        _recorder.open_turn(
            turn_id=turn_id,
            ts=time.time(),
            frame=frame,
            transcript=transcript,
            stt_ms=stt_latency_ms,
            audio_path=audio_rel,
            context_frame=context_snapshot,
        )

    payload = {
        "transcript": transcript,
        "latency_ms": {"stt": stt_latency_ms},
        "player": race_engineer_agent.get_player_info(),
    }
    if turn_id is not None:
        payload["turn_id"] = turn_id
    return jsonify(payload)


@app.route("/agent", methods=["POST"])
def agent():
    if not race_engineer_agent.is_session_active():
        return jsonify({"error": "No active race session."}), 403
    data = request.get_json(silent=True) or {}
    transcript = (data.get("text") or "").strip()
    if not transcript:
        return jsonify({"error": "Missing 'text' field."}), 400
    turn_id: str | None = data.get("turn_id") or None
    llm_start = time.perf_counter()
    agent_reply_raw = None
    try:
        agent_reply_raw = get_agent_reply(transcript)
    finally:
        llm_latency_ms = round((time.perf_counter() - llm_start) * 1000, 1)
    if is_active(_recorder) and turn_id and agent_reply_raw:
        _recorder.close_turn(turn_id, agent_reply_raw, llm_latency_ms)
    payload: dict = {"latency_ms": {"llm": llm_latency_ms}}
    if agent_reply_raw:
        payload["display_reply"] = agent_reply_raw
        payload["agent_reply"] = sanitize_for_tts(agent_reply_raw)
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


@app.route("/callout-stream", methods=["GET"])
def callout_stream():
    def generate():
        while True:
            try:
                msg = callout_queue.get(timeout=25)
                yield f"data: {json.dumps(msg)}\n\n"
            except queue.Empty:
                yield ": heartbeat\n\n"
            except GeneratorExit:
                break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/<path:path>")
def static_proxy(path):
    return send_from_directory(static_folder, path)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    ensure_agent_ready()
    app.run(host="0.0.0.0", port=port, threaded=True)
