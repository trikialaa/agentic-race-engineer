#!/usr/bin/env python3
"""Lightweight helper to exercise the wheel helper binary and log every button event."""

from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Iterable, Iterator


HELPER_REL_PATH = Path("helpers") / "wheel_detector" / "bin" / "WheelHelper.exe"


RIDI_DEVICENAME = 0x20000007
RIDI_DEVICEINFO = 0x2000000b


class RAWINPUTDEVICELIST(ctypes.Structure):
    _fields_ = [
        ("hDevice", wintypes.HANDLE),
        ("dwType", wintypes.DWORD),
    ]


class RID_DEVICE_INFO_HID(ctypes.Structure):
    _fields_ = [
        ("dwVendorId", wintypes.DWORD),
        ("dwProductId", wintypes.DWORD),
        ("dwVersionNumber", wintypes.DWORD),
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
    ]


class RID_DEVICE_INFO_UNION(ctypes.Union):
    _fields_ = [
        ("hid", RID_DEVICE_INFO_HID),
    ]


class RID_DEVICE_INFO(ctypes.Structure):
    _anonymous_ = ("info",)
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwType", wintypes.DWORD),
        ("info", RID_DEVICE_INFO_UNION),
    ]


def _find_helper() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "helpers").is_dir() and (parent / "src").is_dir():
            resolved = (parent / HELPER_REL_PATH).resolve()
            return resolved
    raise FileNotFoundError(
        "WheelHelper.exe not found. Build it with:\n"
        "  dotnet publish -c Release -o helpers/wheel_detector/bin helpers/wheel_detector/WheelHelper.csproj"
    )
    if resolved.exists():
        return resolved
    raise FileNotFoundError(
        "WheelHelper.exe not found. Build it with:\n"
        "  dotnet publish -c Release -o helpers/wheel_detector/bin helpers/wheel_detector/WheelHelper.csproj"
    )


def _spawn_helper(path: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [str(path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )


def _tail_stream(stream: Iterable[bytes]) -> Iterator[str]:
    for chunk in stream:
        if not chunk:
            continue
        try:
            yield chunk.decode("utf-8", "replace")
        except Exception:
            yield "<non utf-8 data>\n"


def _list_raw_input_devices() -> None:
    if sys.platform != "win32":
        print("Raw input device listing is only available on Windows.")
        return
    user32 = ctypes.windll.user32
    count = wintypes.UINT(0)
    cb = ctypes.sizeof(RAWINPUTDEVICELIST)
    if user32.GetRawInputDeviceList(None, ctypes.byref(count), cb) == -1:
        print("GetRawInputDeviceList failed (initial call).", file=sys.stderr)
        return
    if count.value == 0:
        print("No raw input devices found.")
        return

    devices = (RAWINPUTDEVICELIST * count.value)()
    if user32.GetRawInputDeviceList(devices, ctypes.byref(count), cb) == -1:
        print("GetRawInputDeviceList failed (retrieval).", file=sys.stderr)
        return

    print(f"Found {count.value} raw input device(s):")
    for dev in devices:
        name_size = wintypes.UINT(0)
        user32.GetRawInputDeviceInfoW(
            dev.hDevice, RIDI_DEVICENAME, None, ctypes.byref(name_size)
        )
        name = ""
        if name_size.value:
            buffer = ctypes.create_unicode_buffer(name_size.value)
            user32.GetRawInputDeviceInfoW(
                dev.hDevice, RIDI_DEVICENAME, buffer, ctypes.byref(name_size)
            )
            name = buffer.value

        info = RID_DEVICE_INFO()
        info.cbSize = ctypes.sizeof(RID_DEVICE_INFO)
        info_size = wintypes.UINT(ctypes.sizeof(RID_DEVICE_INFO))
        hid_info = ""
        if (
            user32.GetRawInputDeviceInfoW(
                dev.hDevice, RIDI_DEVICEINFO, ctypes.byref(info), ctypes.byref(info_size)
            )
            != -1
        ):
            hid_info = (
                f"usage_page=0x{info.hid.usUsagePage:04X} usage=0x{info.hid.usUsage:04X} "
                f"vendor=0x{info.hid.dwVendorId:04X} product=0x{info.hid.dwProductId:04X}"
            )
        else:
            hid_info = "deviceinfo unavailable"

        type_name = {0: "MOUSE", 1: "KEYBOARD", 2: "HID"}.get(dev.dwType, f"TYPE_{dev.dwType}")
        print(f"  {type_name}: {name or '<unnamed>'} ({hid_info})")


def main() -> int:
    _list_raw_input_devices()
    helper_path = _find_helper()
    print(f"Launching wheel helper: {helper_path}")
    proc = _spawn_helper(helper_path)
    stop_reading = threading.Event()

    def _log_stderr() -> None:
        for line in _tail_stream(proc.stderr):
            print(f"[helper stderr] {line.strip()}", file=sys.stderr)
        stop_reading.set()

    stderr_thread = threading.Thread(target=_log_stderr, daemon=True)
    stderr_thread.start()

    try:
        for raw in _tail_stream(proc.stdout):
            raw = raw.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[helper] {raw}", file=sys.stderr)
                continue
            button = payload.get("button")
            pressed = payload.get("pressed")
            if button is None or pressed is None:
                print(f"[helper] malformed payload: {payload}", file=sys.stderr)
                continue
            state = "pressed" if pressed else "released"
            print(f"[{button:02d}] {state}")
    except KeyboardInterrupt:
        print("Interrupted, terminating helper.")
    except Exception as exc:  # pragma: no cover
        print(f"Unhandled error while reading helper stdout: {exc}", file=sys.stderr)
    finally:
        proc.terminate()
        proc.wait(timeout=1.0)
        stop_reading.set()
        stderr_thread.join(timeout=0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
