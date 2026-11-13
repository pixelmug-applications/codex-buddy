"""Codex hook entry point.

This module intentionally exits with status 0 even when parsing or UDP send fails,
so Codex workflows are not blocked by PixelMug integration errors.
"""
from __future__ import annotations

import json
import socket
import sys
from typing import Any

from .constants import LOCAL_HOOK_PORT, LOCAL_HOST
from .protocol import json_dumps_bytes, normalize_hook_payload


def read_stdin_json() -> dict[str, Any]:
    try:
        raw = sys.stdin.read(256 * 1024)
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"payload": data}
    except Exception:
        return {}


def send_to_bridge(payload: dict[str, Any], timeout: float = 0.5) -> None:
    data = json_dumps_bytes(payload)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(data, (LOCAL_HOST, LOCAL_HOOK_PORT))


def main(argv: list[str] | None = None) -> int:
    try:
        raw = read_stdin_json()
        payload = normalize_hook_payload(raw)
        send_to_bridge(payload)
    except Exception:
        # Never break Codex just because the optional display hook failed.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
