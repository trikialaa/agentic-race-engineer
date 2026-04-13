import asyncio
import logging
import os
import signal
import sys
import threading
from concurrent.futures import Future, TimeoutError as FuturesTimeoutError
from pathlib import Path

# Ensure src/ is importable when running tests from repo root
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.mcp.server import telemetry_capture, mcp
from src.voice_pipeline.agent import RaceEngineerAgent

AGENT_TIMEOUT = 15.0

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

agent = RaceEngineerAgent()
agent_loop = asyncio.new_event_loop()


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


async def init_agent():
    await agent.init_async()


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


def start_mcp_server():
    telemetry_capture.start_capture()
    mcp_thread = threading.Thread(target=mcp.run, daemon=True)
    mcp_thread.start()
    return mcp_thread


def stop_mcp_server():
    telemetry_capture.stop_capture()
    mcp.stop()


def interactive_loop():
    print("Text-only agent console (type EXIT or press Ctrl+D to quit)")
    while True:
        try:
            text = input("> ").strip()
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

    mcp_thread = start_mcp_server()

    def handle_sigint(sig, frame):
        print("\nShutting down…")
        stop_mcp_server()
        agent_loop.call_soon_threadsafe(agent_loop.stop)

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        interactive_loop()
    finally:
        stop_mcp_server()
        agent_loop.call_soon_threadsafe(agent_loop.stop)
        mcp_thread.join(timeout=1.0)


if __name__ == "__main__":
    main()
