"""pixelmug-codex command line entry."""
from __future__ import annotations

import argparse
import socket

from .constants import LOCAL_HOOK_PORT, LOCAL_HOST
from .protocol import json_dumps_bytes, make_control_message


def _send_control(cmd: str, **kwargs) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(0.1)
        sock.sendto(json_dumps_bytes(make_control_message(cmd, **kwargs)), (LOCAL_HOST, LOCAL_HOOK_PORT))


def _cmd_bridge(args: argparse.Namespace) -> int:
    from .bridge import BridgeCore
    from .mac_menu import run_menu_bar_app

    if args.headless:
        bridge = BridgeCore()
        bridge.run_forever()
        return 0
    return run_menu_bar_app()


def _cmd_install(args: argparse.Namespace) -> int:
    from .installer import install_user_files
    from .mac_menu import default_cli_bin_path

    bin_path = args.bin or default_cli_bin_path()
    result = install_user_files(bin_path, start_on_login=not args.no_start_on_login, start_now=not args.no_start_now)
    print("PixelMug Codex user install completed.")
    print(f"hooks: {result['hooks']}")
    print(f"launch_agent: {result['launch_agent']}")
    print("Open Codex and trust the PixelMug Codex hook when prompted.")
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:
    from .installer import uninstall_user_files

    result = uninstall_user_files(delete_config=args.delete_config, delete_logs=args.delete_logs, delete_cache=True)
    print("PixelMug Codex user uninstall completed.")
    print(f"hooks cleaned: {result['hooks']}")
    print(f"launch_agent removed: {result['launch_agent']}")
    if not args.delete_config:
        print(f"pairing config kept: {result['config_dir']}")
    if not args.delete_logs:
        print(f"logs kept: {result['log_dir']}")
    return 0


def _cmd_pair(args: argparse.Namespace) -> int:
    _send_control("pair")
    print("Sent bridge command: pair")
    return 0


def _cmd_connect(args: argparse.Namespace) -> int:
    _send_control("connect")
    print("Sent bridge command: connect")
    return 0


def _cmd_send_test(args: argparse.Namespace) -> int:
    _send_control("send_test", state=args.state, text=args.text)
    print("Sent bridge command: send_test")
    return 0


def _cmd_disconnect(args: argparse.Namespace) -> int:
    _send_control("disconnect")
    print("Sent bridge command: disconnect")
    return 0


def _cmd_bridge_quit(args: argparse.Namespace) -> int:
    _send_control("quit")
    print("Sent bridge command: quit")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from .bridge import BridgeCore
    from .paths import config_file, log_file

    print(f"config: {config_file()}")
    print(f"log: {log_file()}")
    bridge = BridgeCore()
    print(bridge.status_text())
    return 0


def _cmd_hook(args: argparse.Namespace) -> int:
    from .hook import main as hook_main

    return hook_main([])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pixelmug-codex", description="PixelMug Codex hook and macOS bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("hook", help="Codex hook entry: read JSON from stdin and forward to bridge").set_defaults(func=_cmd_hook)

    p_bridge = sub.add_parser("bridge", help="Run the macOS menu bar bridge")
    p_bridge.add_argument("--headless", action="store_true", help="Run without the macOS menu bar UI")
    p_bridge.set_defaults(func=_cmd_bridge)

    p_install = sub.add_parser("install", help="Install per-user Codex hooks and LaunchAgent")
    p_install.add_argument("--bin", help="Absolute pixelmug-codex CLI path used in hooks and LaunchAgent")
    p_install.add_argument("--no-start-on-login", action="store_true", help="Do not register bridge for login startup")
    p_install.add_argument("--no-start-now", action="store_true", help="Do not start bridge after install")
    p_install.set_defaults(func=_cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="Remove per-user hooks and LaunchAgent")
    p_uninstall.add_argument("--delete-config", action="store_true", help="Delete pairing config; default keeps it")
    p_uninstall.add_argument("--delete-logs", action="store_true", help="Delete logs; default keeps them")
    p_uninstall.set_defaults(func=_cmd_uninstall)

    sub.add_parser("pair", help="Ask the running bridge to pair PixelMug").set_defaults(func=_cmd_pair)
    sub.add_parser("connect", help="Ask the running bridge to connect").set_defaults(func=_cmd_connect)
    sub.add_parser("disconnect", help="Ask the running bridge to disconnect").set_defaults(func=_cmd_disconnect)
    sub.add_parser("bridge-quit", help="Ask the running bridge to quit").set_defaults(func=_cmd_bridge_quit)

    p_test = sub.add_parser("send-test", help="Send one test status packet")
    p_test.add_argument("--state", default="prompt")
    p_test.add_argument("--text", default="test from macOS")
    p_test.add_argument("--no-discover", action="store_true")
    p_test.set_defaults(func=_cmd_send_test)

    sub.add_parser("status", help="Print config/log paths and current persisted state").set_defaults(func=_cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
