from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .autostart import set_autostart
from .constants import APP_VERSION, LOCAL_HOST, LOCAL_HOOK_PORT
from .hook_config import install_hooks, uninstall_hooks
from .paths import bridge_log_path, config_path, ensure_dirs, hook_log_path
from .protocol import make_control_message, send_udp


def send_control(cmd: str) -> None:
    send_udp(make_control_message(cmd), LOCAL_HOST, LOCAL_HOOK_PORT, timeout=0.1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pixelmug-codex-cli", description="PixelMug Codex Buddy CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install-hooks", help="Install Codex hooks.json entries")
    p_install.add_argument("--hook-exe", required=True, help="Absolute path to pixelmug-codex-hook.exe")

    sub.add_parser("uninstall-hooks", help="Remove PixelMug entries from Codex hooks.json")

    p_autostart = sub.add_parser("autostart", help="Manage Windows start-on-login")
    p_autostart.add_argument("mode", choices=["on", "off"])
    p_autostart.add_argument("--bridge-exe", help="Absolute path to pixelmug-codex-buddy.exe")

    sub.add_parser("pair", help="Ask running bridge to pair PixelMug")
    sub.add_parser("connect", help="Ask running bridge to connect")
    sub.add_parser("disconnect", help="Ask running bridge to disconnect")
    sub.add_parser("send-test", help="Ask running bridge to send a test status")
    sub.add_parser("open-logs", help="Ask running bridge to open logs")
    sub.add_parser("bridge-quit", help="Ask running bridge to quit")
    sub.add_parser("paths", help="Print config and log paths")

    args = parser.parse_args(argv)
    ensure_dirs()

    if args.cmd == "install-hooks":
        path = install_hooks(args.hook_exe)
        print(f"Installed Codex hooks: {path}")
        print("Open Codex and run /hooks to trust PixelMug hooks.")
        return 0

    if args.cmd == "uninstall-hooks":
        path, removed = uninstall_hooks()
        print(f"Updated Codex hooks: {path}; removed entries: {removed}")
        return 0

    if args.cmd == "autostart":
        if args.mode == "on":
            if not args.bridge_exe:
                parser.error("--bridge-exe is required for autostart on")
            set_autostart(True, args.bridge_exe)
            print("Start on login enabled")
        else:
            set_autostart(False)
            print("Start on login disabled")
        return 0

    control_map = {
        "pair": "pair",
        "connect": "connect",
        "disconnect": "disconnect",
        "send-test": "send_test",
        "open-logs": "open_logs",
        "bridge-quit": "quit",
    }
    if args.cmd in control_map:
        send_control(control_map[args.cmd])
        print(f"Sent bridge command: {control_map[args.cmd]}")
        return 0

    if args.cmd == "paths":
        print(f"Config: {config_path()}")
        print(f"Bridge log: {bridge_log_path()}")
        print(f"Hook log: {hook_log_path()}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

