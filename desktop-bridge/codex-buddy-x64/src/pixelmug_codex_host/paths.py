from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .constants import APP_ID, CONFIG_FILE_NAME, HOOK_LOG_FILE_NAME, LOG_FILE_NAME


def _ensure_or_temp(path: Path, suffix: str = "") -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return path
    except OSError:
        fallback = Path(tempfile.gettempdir()) / APP_ID
        if suffix:
            fallback = fallback / suffix
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def appdata_dir() -> Path:
    base = os.environ.get("APPDATA")
    preferred = Path(base) / APP_ID if base else Path.home() / ".config" / APP_ID
    return _ensure_or_temp(preferred, "config")


def localappdata_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    preferred = Path(base) / APP_ID if base else Path.home() / ".local" / "share" / APP_ID
    return _ensure_or_temp(preferred, "local")


def config_path() -> Path:
    return appdata_dir() / CONFIG_FILE_NAME


def logs_dir() -> Path:
    return localappdata_dir() / "logs"


def bridge_log_path() -> Path:
    return logs_dir() / LOG_FILE_NAME


def hook_log_path() -> Path:
    return logs_dir() / HOOK_LOG_FILE_NAME


def codex_dir() -> Path:
    value = os.environ.get("CODEX_HOME", "").strip()
    preferred = Path(value).expanduser() if value else Path.home() / ".codex"
    return _ensure_or_temp(preferred, "codex")


def codex_hooks_path() -> Path:
    return codex_dir() / "hooks.json"


def ensure_dirs() -> None:
    appdata_dir().mkdir(parents=True, exist_ok=True)
    localappdata_dir().mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)
    codex_dir().mkdir(parents=True, exist_ok=True)
