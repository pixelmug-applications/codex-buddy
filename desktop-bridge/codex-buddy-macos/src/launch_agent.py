"""macOS LaunchAgent helper."""
from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from .constants import LAUNCH_AGENT_ID
from .paths import launch_agent_file, launch_agents_dir


def _uid() -> int:
    return os.getuid()


def create_launch_agent(bin_path: str, *, enabled: bool = True) -> Path:
    launch_agents_dir().mkdir(parents=True, exist_ok=True)
    plist_path = launch_agent_file()
    data = {
        "Label": LAUNCH_AGENT_ID,
        "ProgramArguments": [bin_path, "bridge"],
        "RunAtLoad": bool(enabled),
        "KeepAlive": False,
        "StandardOutPath": str(Path.home() / "Library" / "Logs" / "PixelMugCodex" / "launchd.out.log"),
        "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "PixelMugCodex" / "launchd.err.log"),
        "WorkingDirectory": str(Path.home()),
    }
    with plist_path.open("wb") as f:
        plistlib.dump(data, f, sort_keys=False)
    os.chmod(plist_path, 0o644)
    return plist_path


def remove_launch_agent() -> Path:
    unload_launch_agent()
    plist_path = launch_agent_file()
    try:
        plist_path.unlink()
    except FileNotFoundError:
        pass
    return plist_path


def load_launch_agent() -> None:
    plist_path = launch_agent_file()
    if not plist_path.exists():
        return
    domain = f"gui/{_uid()}"
    # Modern launchctl path. Ignore failures and try legacy fallback.
    subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "enable", f"{domain}/{LAUNCH_AGENT_ID}"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{LAUNCH_AGENT_ID}"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def unload_launch_agent() -> None:
    plist_path = launch_agent_file()
    domain = f"gui/{_uid()}"
    subprocess.run(["launchctl", "bootout", domain, str(plist_path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "remove", LAUNCH_AGENT_ID], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
