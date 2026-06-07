import asyncio
import logging
import os
import signal
import sys
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path

# Ensure src/ is importable when running tests from repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.voice_pipeline.agent import RaceEngineerAgent

AGENT_TIMEOUT = 15.0

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

agent = RaceEngineerAgent()
agent_loop = asyncio.new_event_loop()
shutdown_requested = threading.Event()


def start_agent_loop() -> None:
    asyncio.set_event_loop(agent_loop)
    agent_loop.run_forever()


agent_thread = threading.Thread(target=start_agent_loop, daemon=True)
agent_thread.start()


def run_agent_coroutine(coro, timeout: float = AGENT_TIMEOUT):
    future: Future = asyncio.run_coroutine_threadsafe(coro, agent_loop)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        future.cancel()
        raise


def ensure_agent_ready(timeout: float = AGENT_TIMEOUT) -> bool:
    try:
        run_agent_coroutine(agent.init_async(), timeout)
        logging.info("Race engineer agent initialized")
        return True
    except Exception as exc:
        logging.error("Failed to initialize agent: %s", exc)
        return False


def query_agent(prompt: str, **kwargs) -> str | None:
    return run_agent_coroutine(agent.reply_async(prompt, **kwargs))


def shutdown_agent(timeout: float = AGENT_TIMEOUT) -> None:
    """Best-effort shutdown of the agent and MCP subprocess."""
    try:
        run_agent_coroutine(agent.shutdown_async(), timeout=timeout)
    except Exception as exc:
        logging.warning("Agent shutdown timed out or failed: %s", exc)


def interactive_loop():
    print("Text-only agent console (type EXIT or press Ctrl+D to quit)")
    while not shutdown_requested.is_set():
        try:
            text = input("> ").strip()
        except KeyboardInterrupt:
            break
        except EOFError:
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit", "bye"}:
            break
        try:
            reply = query_agent(text)
            print("Agent:", reply or "no response")
        except Exception as exc:
            print("Agent error:", exc)


def main():
    if not ensure_agent_ready():
        sys.exit(1)

    def handle_termination(sig, frame):
        shutdown_requested.set()
        print("\nShutting down...")
        # Force input() to unblock immediately on Unix-like systems.
        try:
            os.close(sys.stdin.fileno())
        except Exception:
            pass

    signal.signal(signal.SIGINT, handle_termination)
    signal.signal(signal.SIGTERM, handle_termination)

    try:
        interactive_loop()
    finally:
        shutdown_requested.set()
        shutdown_agent(timeout=AGENT_TIMEOUT)
        if agent_loop.is_running():
            agent_loop.call_soon_threadsafe(agent_loop.stop)
        agent_thread.join(timeout=1.0)
        # Last-resort exit if a child process still prevents normal shutdown.
        if agent_thread.is_alive():
            os._exit(1)


if __name__ == "__main__":
    main()
