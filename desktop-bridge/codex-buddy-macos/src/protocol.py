"""Message normalization and UDP protocol helpers."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from .constants import (
    CONTROL_MSG_TYPE,
    LOCAL_MSG_TYPE,
    MAX_TEXT_CHARS,
    PAIR_MSG_TYPE,
    PROTOCOL_VERSION,
    STATUS_MSG_TYPE,
)

_SECRETISH_RE = re.compile(
    r"(?i)(token|secret|password|passwd|pwd|cookie|authorization|api[_-]?key|access[_-]?key|private[_-]?key)\s*[:=]\s*\S+"
)
_WS_RE = re.compile(r"\s+")


def now_ts() -> int:
    return int(time.time())


def make_request_id(prefix: str = "req") -> str:
    return f"{prefix}-{os.urandom(6).hex()}"


def truncate_text(value: Any, max_chars: int = MAX_TEXT_CHARS) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            value = str(value)
    value = value.replace("\x00", " ")
    value = _SECRETISH_RE.sub(lambda m: m.group(1) + "=<redacted>", value)
    value = _WS_RE.sub(" ", value).strip()
    if len(value) > max_chars:
        return value[: max_chars - 3] + "..."
    return value


def _first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _nested_first_string(data: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> str:
    for path in paths:
        cur: Any = data
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        if isinstance(cur, str) and cur:
            return cur
    return ""


def get_repo_name(data: dict[str, Any]) -> str:
    direct = _first_string(data, ("repo", "repository", "project", "workspace"))
    if direct:
        return truncate_text(Path(direct).name, 40)
    cwd = _first_string(data, ("cwd", "working_dir", "workingDirectory"))
    if not cwd:
        cwd = os.getcwd()
    return truncate_text(Path(cwd).name, 40)


def get_tool_name(data: dict[str, Any]) -> str:
    return truncate_text(
        _first_string(data, ("tool", "tool_name", "toolName", "name"))
        or _nested_first_string(data, (("tool", "name"), ("tool_call", "name"), ("message", "tool_name"))),
        40,
    )


def get_event_name(data: dict[str, Any]) -> str:
    return truncate_text(
        _first_string(data, ("event", "hook_event_name", "hookEventName", "eventName", "type"))
        or _nested_first_string(data, (("hook", "event"), ("message", "event"))),
        40,
    )


def _text_from_tool(data: dict[str, Any]) -> str:
    tool = get_tool_name(data)
    candidates: list[Any] = []
    for key in (
        "command",
        "cmd",
        "input",
        "text",
        "summary",
        "status",
        "description",
        "prompt",
    ):
        if key in data:
            candidates.append(data[key])

    for path in (
        ("tool_input", "command"),
        ("toolInput", "command"),
        ("tool_input", "cmd"),
        ("toolInput", "cmd"),
        ("tool_input", "patch"),
        ("toolInput", "patch"),
        ("tool", "input"),
        ("tool_call", "input"),
        ("message", "content"),
    ):
        cur: Any = data
        for key in path:
            if not isinstance(cur, dict):
                cur = None
                break
            cur = cur.get(key)
        if cur:
            candidates.append(cur)

    for candidate in candidates:
        text = truncate_text(candidate)
        if text:
            # Do not leak full prompts. For prompt events, a generic label is enough.
            event = get_event_name(data)
            if event == "UserPromptSubmit" and "prompt" in data:
                return "prompt submitted"
            return text

    if tool:
        return tool
    return ""


def map_state(event: str, tool: str, raw: dict[str, Any]) -> str:
    event = event or get_event_name(raw)
    tool = tool or get_tool_name(raw)
    if event == "SessionStart":
        return "session"
    if event == "UserPromptSubmit":
        return "prompt"
    if event == "PermissionRequest":
        return "permission"
    if event == "Stop":
        return "done"
    if event == "PreToolUse":
        if tool == "Bash":
            return "bash"
        if tool == "apply_patch":
            return "edit"
        return "subagent"
    if event == "PostToolUse":
        ok = raw.get("ok")
        success = raw.get("success")
        error = raw.get("error") or raw.get("is_error") or raw.get("failed")
        if error or ok is False or success is False:
            return "error"
        return "tool_done"
    if event in ("PreCompact", "Compact", "ContextCompact"):
        return "compact"
    if event == "PostCompact":
        return "compact_done"
    if event == "SubagentStart":
        return "subagent"
    if event == "SubagentStop":
        error = raw.get("error") or raw.get("is_error") or raw.get("failed")
        if error:
            return "error"
        return "tool_done"
    return "idle"


def normalize_hook_payload(raw: dict[str, Any]) -> dict[str, Any]:
    event = get_event_name(raw)
    tool = get_tool_name(raw)
    state = map_state(event, tool, raw)
    msg = {
        "type": LOCAL_MSG_TYPE,
        "v": PROTOCOL_VERSION,
        "event": event,
        "state": state,
        "tool": tool,
        "repo": get_repo_name(raw),
        "text": _text_from_tool(raw),
        "ts": now_ts(),
    }
    for out_key, in_keys in {
        "session_id": ("session_id", "sessionId", "conversation_id", "conversationId"),
        "turn_id": ("turn_id", "turnId", "request_id", "requestId"),
    }.items():
        value = _first_string(raw, in_keys)
        if value:
            msg[out_key] = truncate_text(value, 40)
    return msg


def make_status_packet(
    local_msg: dict[str, Any],
    token: str,
    seq: int,
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packet: dict[str, Any] = {
        "type": STATUS_MSG_TYPE,
        "v": PROTOCOL_VERSION,
        "token": token,
        "seq": seq,
        "state": truncate_text(local_msg.get("state") or "idle", 32),
        "event": truncate_text(local_msg.get("event") or "", 40),
        "tool": truncate_text(local_msg.get("tool") or "", 40),
        "repo": truncate_text(local_msg.get("repo") or "", 40),
        "text": truncate_text(local_msg.get("text") or "", MAX_TEXT_CHARS),
        "ts": int(local_msg.get("ts") or now_ts()),
    }
    for key in ("session_id", "turn_id"):
        if local_msg.get(key):
            packet[key] = truncate_text(local_msg.get(key), 40)
    if "connected" in local_msg:
        packet["connected"] = bool(local_msg.get("connected"))
    if usage:
        packet["usage"] = usage
    return packet


def json_dumps_bytes(packet: dict[str, Any]) -> bytes:
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def make_control_message(cmd: str, **kwargs: Any) -> dict[str, Any]:
    msg = {
        "type": CONTROL_MSG_TYPE,
        "v": PROTOCOL_VERSION,
        "cmd": cmd,
        "ts": now_ts(),
    }
    msg.update(kwargs)
    return msg


def make_auth_check_message(bridge_id: str, device_id: str, token: str, request_id: str | None = None) -> dict[str, Any]:
    return {
        "type": PAIR_MSG_TYPE,
        "v": PROTOCOL_VERSION,
        "cmd": "auth_check",
        "request_id": request_id or make_request_id(),
        "bridge_id": bridge_id,
        "device_id": device_id,
        "token": token,
    }
