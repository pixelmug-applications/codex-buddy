"""macOS user paths used by the PixelMug Codex host bridge."""
from __future__ import annotations

import os
from pathlib import Path

from .constants import APP_NAME


def home_dir() -> Path:
    return Path.home()


def config_dir() -> Path:
    return home_dir() / "Library" / "Application Support" / APP_NAME


def log_dir() -> Path:
    return home_dir() / "Library" / "Logs" / APP_NAME


def cache_dir() -> Path:
    return home_dir() / "Library" / "Caches" / APP_NAME


def config_file() -> Path:
    return config_dir() / "config.json"


def log_file() -> Path:
    return log_dir() / "bridge.log"


def codex_hooks_file() -> Path:
    return home_dir() / ".codex" / "hooks.json"


def launch_agents_dir() -> Path:
    return home_dir() / "Library" / "LaunchAgents"


def launch_agent_file() -> Path:
    from .constants import LAUNCH_AGENT_ID

    return launch_agents_dir() / f"{LAUNCH_AGENT_ID}.plist"


def ensure_user_dirs() -> None:
    for path in (config_dir(), log_dir(), cache_dir(), codex_hooks_file().parent, launch_agents_dir()):
        path.mkdir(parents=True, exist_ok=True)


def chmod_user_readable(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
