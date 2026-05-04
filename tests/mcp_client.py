import argparse
import asyncio
from typing import Any

from fastmcp import Client
from fastmcp.client import transports as mcp_transports

try:
    from pydantic import BaseModel  # type: ignore
except Exception:
    BaseModel = None  # pragma: no cover


def _build_http_transport(url: str):
    candidates = ("StreamableHttpTransport", "HTTPTransport", "HttpTransport")
    for class_name in candidates:
        transport_cls = getattr(mcp_transports, class_name, None)
        if transport_cls is None:
            continue
        for kwargs in ({"url": url}, {"endpoint": url}, {"base_url": url}):
            try:
                return transport_cls(**kwargs)
            except TypeError:
                continue
        try:
            return transport_cls(url)
        except TypeError:
            continue
    raise RuntimeError(
        "No supported HTTP transport found in fastmcp.client.transports. "
        f"Tried: {', '.join(candidates)}"
    )


class F1TelemetryClient:
    def __init__(self, url: str = "http://127.0.0.1:20915/mcp"):
        self.client = Client(transport=_build_http_transport(url))

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.__aexit__(exc_type, exc, tb)

    async def call(self, tool: str, **params):
        return await self.client.call_tool(tool, params)


def _to_plain(obj: Any):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_plain(v) for v in obj]
    if BaseModel and isinstance(obj, BaseModel):
        return _to_plain(obj.model_dump())
    if hasattr(obj, "model_dump"):
        try:
            return _to_plain(obj.model_dump())
        except Exception:
            pass
    if hasattr(obj, "dict"):
        try:
            return _to_plain(obj.dict())
        except Exception:
            pass
    if hasattr(obj, "__root__"):
        try:
            return _to_plain(obj.__root__)
        except Exception:
            pass
    if hasattr(obj, "root"):
        try:
            return _to_plain(obj.root)
        except Exception:
            pass
    if hasattr(obj, "__dict__"):
        try:
            return _to_plain(vars(obj))
        except Exception:
            pass
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8", "ignore")
        except Exception:
            return obj.hex()
    return obj


def _print(tool: str, result):
    try:
        import json

        payload = result.data if hasattr(result, "data") else result
        payload = _to_plain(payload)
        print(f"\n--- {tool} ---")
        print(json.dumps(payload, indent=2))
    except Exception as exc:
        print(f"\n--- {tool} (could not format: {exc}) ---")
        print(result)


async def _list_tool_names(client: F1TelemetryClient) -> list[str]:
    try:
        tools = await client.client.list_tools()
    except Exception:
        return []

    names: list[str] = []
    if isinstance(tools, list):
        for item in tools:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(item["name"])
            elif hasattr(item, "name") and isinstance(getattr(item, "name"), str):
                names.append(getattr(item, "name"))
    elif hasattr(tools, "tools"):
        for item in getattr(tools, "tools", []):
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(item["name"])
            elif hasattr(item, "name") and isinstance(getattr(item, "name"), str):
                names.append(getattr(item, "name"))
    return names


async def main_with_url(url: str, full: bool = False):
    async with F1TelemetryClient(url=url) as client:
        tool_names = await _list_tool_names(client)
        if tool_names:
            print("\n--- available_tools ---")
            for name in sorted(tool_names):
                print(name)

        call_plan = [("get_context_frame", "get_context_frame", {})]
        if full and tool_names:
            call_plan = [
                (name, name, {})
                for name in sorted(tool_names)
            ]
        elif full:
            call_plan.extend(
                [
                    ("get_leaderboard", "get_leaderboard", {}),
                ]
            )
        for label, tool, params in call_plan:
            _print(label, await client.call(tool, **params))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP HTTP smoke client")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:20915/mcp",
        help="HTTP MCP endpoint URL (example: http://127.0.0.1:20915/mcp)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Call additional non-context tools (debug/detail output).",
    )
    args = parser.parse_args()
    asyncio.run(main_with_url(args.url, full=args.full))
