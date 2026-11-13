#!/usr/bin/env python3
"""Tiny PixelMug UDP simulator for host-side testing.

Run this on the same LAN as the bridge. Press Enter to enable pair mode.
It implements the first-stage pair/status protocol and prints received status.
"""
from __future__ import annotations

import argparse
import json
import random
import socket
import threading
import time

PAIR_PORT = 39218
STATUS_PORT = 39217
PAIR_TYPE = "pixelmug_pair"
STATUS_TYPE = "pixelmug_codex_status"


def dumps(obj):
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


class PixelMugSim:
    def __init__(self, device_id: str, device_name: str) -> None:
        self.device_id = device_id
        self.device_name = device_name
        self.pairing_enabled = False
        self.pair_deadline = 0.0
        self.current_code = ""
        self.token = ""
        self.bridge_id = ""
        self.last_seq = -1
        self.stop = threading.Event()

    def enable_pairing(self, ttl: int = 60) -> None:
        self.pairing_enabled = True
        self.pair_deadline = time.monotonic() + ttl
        self.current_code = ""
        print(f"[PAIR] enabled ttl={ttl}s")

    def _pair_loop(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(("", PAIR_PORT))
            sock.settimeout(0.25)
            while not self.stop.is_set():
                if self.pairing_enabled and time.monotonic() > self.pair_deadline:
                    self.pairing_enabled = False
                    print("[PAIR] expired")
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                try:
                    msg = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
                if not isinstance(msg, dict) or msg.get("type") != PAIR_TYPE:
                    continue
                cmd = msg.get("cmd")
                req = msg.get("request_id")
                if cmd == "discover":
                    resp = {
                        "type": PAIR_TYPE,
                        "v": 1,
                        "cmd": "device_info",
                        "request_id": req,
                        "device_id": self.device_id,
                        "device_name": self.device_name,
                        "pairing_enabled": self.pairing_enabled,
                        "paired": bool(self.token),
                        "status_port": STATUS_PORT,
                        "pair_port": PAIR_PORT,
                    }
                    sock.sendto(dumps(resp), addr)
                    print(f"[PAIR] device_info sent to {addr[0]}")
                elif cmd == "pair_start":
                    if not self.pairing_enabled:
                        sock.sendto(dumps({"type": PAIR_TYPE, "v": 1, "cmd": "pair_error", "request_id": req, "device_id": self.device_id, "error": "not_in_pair_mode"}), addr)
                        continue
                    if msg.get("device_id") != self.device_id:
                        sock.sendto(dumps({"type": PAIR_TYPE, "v": 1, "cmd": "pair_error", "request_id": req, "device_id": self.device_id, "error": "invalid_device"}), addr)
                        continue
                    self.current_code = f"{random.randint(0, 999999):06d}"
                    print(f"[PAIR] code={self.current_code}")
                    sock.sendto(dumps({"type": PAIR_TYPE, "v": 1, "cmd": "pair_code_shown", "request_id": req, "device_id": self.device_id, "ttl": 60}), addr)
                elif cmd == "pair_confirm":
                    if msg.get("code") != self.current_code:
                        sock.sendto(dumps({"type": PAIR_TYPE, "v": 1, "cmd": "pair_error", "request_id": req, "device_id": self.device_id, "error": "invalid_code"}), addr)
                        continue
                    token = str(msg.get("token") or "")
                    if len(token) < 32:
                        sock.sendto(dumps({"type": PAIR_TYPE, "v": 1, "cmd": "pair_error", "request_id": req, "device_id": self.device_id, "error": "invalid_token"}), addr)
                        continue
                    self.token = token
                    self.bridge_id = str(msg.get("bridge_id") or "")
                    self.pairing_enabled = False
                    print("[PAIR] success")
                    sock.sendto(dumps({"type": PAIR_TYPE, "v": 1, "cmd": "paired", "request_id": req, "device_id": self.device_id, "ok": True}), addr)
                elif cmd == "auth_check":
                    if not self.token:
                        error = "not_paired"
                    elif msg.get("device_id") != self.device_id:
                        error = "invalid_device"
                    elif msg.get("bridge_id") != self.bridge_id:
                        error = "bridge_mismatch"
                    elif msg.get("token") != self.token:
                        error = "token_mismatch"
                    else:
                        error = ""
                    if error:
                        sock.sendto(dumps({"type": PAIR_TYPE, "v": 1, "cmd": "pair_error", "request_id": req, "device_id": self.device_id, "ok": False, "error": error}), addr)
                    else:
                        sock.sendto(dumps({"type": PAIR_TYPE, "v": 1, "cmd": "auth_ok", "request_id": req, "device_id": self.device_id, "ok": True}), addr)

    def _status_loop(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", STATUS_PORT))
            sock.settimeout(0.25)
            while not self.stop.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                try:
                    msg = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
                if msg.get("type") != STATUS_TYPE:
                    continue
                if not self.token or msg.get("token") != self.token:
                    print("[CODEX] drop invalid token")
                    continue
                seq = int(msg.get("seq", -1))
                if seq <= self.last_seq:
                    print(f"[CODEX] drop old seq={seq}")
                    continue
                self.last_seq = seq
                print(f"[CODEX] seq={seq} state={msg.get('state')} tool={msg.get('tool')} repo={msg.get('repo')} text={msg.get('text')}")

    def run(self) -> None:
        threading.Thread(target=self._pair_loop, daemon=True).start()
        threading.Thread(target=self._status_loop, daemon=True).start()
        print("[BOOT] PixelMug UDP simulator started")
        print("Press Enter to enable pair mode; Ctrl-C to quit.")
        try:
            while True:
                input()
                self.enable_pairing()
        except KeyboardInterrupt:
            self.stop.set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-id", default="pixelmug-SIM1")
    parser.add_argument("--device-name", default="PixelMug Simulator")
    args = parser.parse_args()
    PixelMugSim(args.device_id, args.device_name).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
