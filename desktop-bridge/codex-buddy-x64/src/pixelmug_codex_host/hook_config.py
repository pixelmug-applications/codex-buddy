from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from .constants import CODEX_HOOK_TIMEOUT_SEC, HOOK_ID, HOOK_STATUS_MESSAGE, TOOL_MATCHER
from .paths import codex_hooks_path, ensure_dirs

HOOK_EXE_TOKEN = "pixelmug-codex"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"hooks": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        backup = path.with_suffix(".json.bak")
        try:
            backup.write_text(path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
        except OSError:
            pass
        raise RuntimeError(f"Invalid hooks.json. Backed up to {backup}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("hooks.json root must be an object")
    if not isinstance(data.get("hooks"), dict):
        data["hooks"] = {}
    return data


def _save_json(path: Path, data: dict[str, Any]) -> None:
    ensure_dirs()
    if path.exists():
        try:
            shutil.copy2(path, path.with_suffix(".json.bak"))
        except OSError:
            pass
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _quote_cmd_command(path: str) -> str:
    quoted = f'"{path}"' if " " in path else path
    # The hook executable ignores extra argv, but keeping the subcommand makes the
    # hooks.json shape match the macOS CLI command: pixelmug-codex hook.
    return f"{quoted} hook"


def _quote_powershell_command(path: str) -> str:
    escaped = path.replace("'", "''")
    return f'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& \'{escaped}\' hook"'


def _hook_command(hook_exe: str) -> dict[str, Any]:
    command = _quote_cmd_command(hook_exe)
    command_windows = _quote_powershell_command(hook_exe)
    return {
        "type": "command",
        "command": command,
        "commandWindows": command_windows,
        "timeout": CODEX_HOOK_TIMEOUT_SEC,
        "statusMessage": HOOK_STATUS_MESSAGE,
        "pixelmugHookId": HOOK_ID,
    }


def _event_entries(hook_exe: str) -> dict[str, list[dict[str, Any]]]:
    hook = _hook_command(hook_exe)
    return {
        "SessionStart": [{"hooks": [deepcopy(hook)]}],
        "UserPromptSubmit": [{"hooks": [deepcopy(hook)]}],
        "PreToolUse": [{"matcher": TOOL_MATCHER, "hooks": [deepcopy(hook)]}],
        "PermissionRequest": [{"matcher": TOOL_MATCHER, "hooks": [deepcopy(hook)]}],
        "PostToolUse": [{"matcher": TOOL_MATCHER, "hooks": [deepcopy(hook)]}],
        "PreCompact": [{"matcher": "manual|auto", "hooks": [deepcopy(hook)]}],
        "PostCompact": [{"matcher": "manual|auto", "hooks": [deepcopy(hook)]}],
        "SubagentStart": [{"hooks": [deepcopy(hook)]}],
        "SubagentStop": [{"hooks": [deepcopy(hook)]}],
        "Stop": [{"hooks": [deepcopy(hook)]}],
    }


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
        command = f"{hook.get('command') or ''} {hook.get('commandWindows') or ''}".lower()
        if HOOK_EXE_TOKEN in command and "hook" in command:
            return True
    return False


def remove_pixelmug_hooks(data: dict[str, Any]) -> int:
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        data["hooks"] = {}
        return 0
    removed = 0
    for event, entries in list(hooks.items()):
        if not isinstance(entries, list):
            continue
        kept = []
        for item in entries:
            if _is_pixelmug_hook_item(item):
                removed += 1
            else:
                kept.append(item)
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    return removed


def install_hooks(hook_exe: str) -> Path:
    path = codex_hooks_path()
    data = _load_json(path)
    remove_pixelmug_hooks(data)
    hooks = data.setdefault("hooks", {})
    for event, entries in _event_entries(hook_exe).items():
        existing = hooks.setdefault(event, [])
        if isinstance(existing, list):
            existing.extend(entries)
        else:
            hooks[event] = entries
    _save_json(path, data)
    return path


def uninstall_hooks() -> tuple[Path, int]:
    path = codex_hooks_path()
    data = _load_json(path)
    removed = remove_pixelmug_hooks(data)
    _save_json(path, data)
    return path, removed

