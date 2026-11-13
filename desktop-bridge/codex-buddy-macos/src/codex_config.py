"""Safe merge/removal of PixelMug hook entries in ~/.codex/hooks.json."""
from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path
from typing import Any

from .constants import CODEX_HOOK_TIMEOUT_SEC, HOOK_ID, HOOK_STATUS_MESSAGE, TOOL_MATCHER
from .paths import chmod_user_readable, codex_hooks_file, ensure_user_dirs


def _hook_command(bin_path: str) -> dict[str, Any]:
    return {
        "type": "command",
        "command": f"{shlex.quote(bin_path)} hook",
        "commandWindows": "pixelmug-codex.exe hook",
        "timeout": CODEX_HOOK_TIMEOUT_SEC,
        "statusMessage": HOOK_STATUS_MESSAGE,
        "pixelmugHookId": HOOK_ID,
    }


def _event_entries(bin_path: str) -> dict[str, list[dict[str, Any]]]:
    hook = _hook_command(bin_path)
    return {
        "SessionStart": [{"hooks": [hook.copy()]}],
        "UserPromptSubmit": [{"hooks": [hook.copy()]}],
        "PreToolUse": [{"matcher": TOOL_MATCHER, "hooks": [hook.copy()]}],
        "PermissionRequest": [{"matcher": TOOL_MATCHER, "hooks": [hook.copy()]}],
        "PostToolUse": [{"matcher": TOOL_MATCHER, "hooks": [hook.copy()]}],
        "PreCompact": [{"matcher": "manual|auto", "hooks": [hook.copy()]}],
        "PostCompact": [{"matcher": "manual|auto", "hooks": [hook.copy()]}],
        "SubagentStart": [{"hooks": [hook.copy()]}],
        "SubagentStop": [{"hooks": [hook.copy()]}],
        "Stop": [{"hooks": [hook.copy()]}],
    }


def _load_hooks(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"hooks": {}}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("hooks.json root must be an object")
    if not isinstance(data.get("hooks"), dict):
        data["hooks"] = {}
    return data


def _is_pixelmug_hook_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    hooks = item.get("hooks")
    if not isinstance(hooks, list):
        return False
    for hook in hooks:
        if not isinstance(hook, dict):
            continue
        if hook.get("pixelmugHookId") == HOOK_ID:
            return True
        command = str(hook.get("command") or "")
        if "pixelmug-codex" in command and " hook" in command:
            return True
    return False


def remove_pixelmug_hooks(data: dict[str, Any]) -> dict[str, Any]:
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        data["hooks"] = {}
        return data
    for event, entries in list(hooks.items()):
        if not isinstance(entries, list):
            continue
        hooks[event] = [item for item in entries if not _is_pixelmug_hook_item(item)]
        if not hooks[event]:
            hooks.pop(event, None)
    return data


def install_codex_hooks(bin_path: str, path: Path | None = None) -> Path:
    ensure_user_dirs()
    path = path or codex_hooks_file()
    data = _load_hooks(path)
    data = remove_pixelmug_hooks(data)
    hooks = data.setdefault("hooks", {})
    for event, entries in _event_entries(bin_path).items():
        hooks.setdefault(event, [])
        if isinstance(hooks[event], list):
            hooks[event].extend(entries)
        else:
            hooks[event] = entries

    if path.exists():
        backup = path.with_suffix(".json.bak")
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)
    chmod_user_readable(path)
    return path


def uninstall_codex_hooks(path: Path | None = None) -> Path:
    ensure_user_dirs()
    path = path or codex_hooks_file()
    if not path.exists():
        return path
    data = _load_hooks(path)
    data = remove_pixelmug_hooks(data)
    backup = path.with_suffix(".json.bak")
    try:
        shutil.copy2(path, backup)
    except OSError:
        pass
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)
    chmod_user_readable(path)
    return path
