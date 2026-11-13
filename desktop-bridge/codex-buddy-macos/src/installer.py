"""User-level install/uninstall actions.

The .pkg installs program files. These functions modify per-user files:
Codex hooks, LaunchAgent, app config and logs directories.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .codex_config import install_codex_hooks, uninstall_codex_hooks
from .config import ConfigStore
from .launch_agent import create_launch_agent, load_launch_agent, remove_launch_agent
from .logger import get_logger
from .paths import cache_dir, config_dir, ensure_user_dirs, log_dir


def install_user_files(bin_path: str, *, start_on_login: bool = True, start_now: bool = True) -> dict[str, str]:
    ensure_user_dirs()
    log = get_logger("install")
    hooks_path = install_codex_hooks(bin_path)
    plist_path = create_launch_agent(bin_path, enabled=start_on_login)
    cfg_store = ConfigStore()
    cfg = cfg_store.load()
    cfg.start_on_login = start_on_login
    cfg_store.save(cfg)
    if start_now:
        load_launch_agent()
    log.info("config saved")
    return {
        "hooks": str(hooks_path),
        "launch_agent": str(plist_path),
        "config_dir": str(config_dir()),
        "log_dir": str(log_dir()),
    }


def uninstall_user_files(*, delete_config: bool = False, delete_logs: bool = False, delete_cache: bool = True) -> dict[str, str]:
    log = get_logger("install")
    hooks_path = uninstall_codex_hooks()
    plist_path = remove_launch_agent()
    if delete_config:
        shutil.rmtree(config_dir(), ignore_errors=True)
    if delete_logs:
        shutil.rmtree(log_dir(), ignore_errors=True)
    if delete_cache:
        shutil.rmtree(cache_dir(), ignore_errors=True)
    log.info("uninstall user files done")
    return {
        "hooks": str(hooks_path),
        "launch_agent": str(plist_path),
        "config_dir": str(config_dir()),
        "log_dir": str(log_dir()),
    }
