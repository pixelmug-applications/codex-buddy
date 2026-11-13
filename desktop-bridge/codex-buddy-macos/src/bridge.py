"""Host bridge core.

The bridge receives local Codex hook messages on 127.0.0.1:39216 and forwards
short status packets to a paired PixelMug over UDP.
"""
from __future__ import annotations

import json
import secrets
import socket
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from .config import BridgeConfig, ConfigStore, PairedDevice
from .constants import (
    BROADCAST_ADDR,
    CONTROL_MSG_TYPE,
    DISCOVER_TIMEOUT_SEC,
    LOCAL_HOOK_PORT,
    LOCAL_HOST,
    LOCAL_MSG_TYPE,
    MAX_UDP_PACKET_BYTES,
    PAIR_MSG_TYPE,
    PAIR_TIMEOUT_SEC,
    PIXELMUG_PAIR_PORT,
    PROTOCOL_VERSION,
)
from .logger import get_logger
from .protocol import json_dumps_bytes, make_auth_check_message, make_status_packet, now_ts
from .usage import CodexUsageMonitor

StatusCallback = Callable[[str], None]
ControlCallback = Callable[[dict[str, Any]], bool]


@dataclass
class RuntimeState:
    connection: str = "Disconnected"
    last_state: str = "idle"
    last_error: str = ""
    last_device: str = ""
    seq: int = 0


class PairingError(RuntimeError):
    pass


class BridgeCore:
    def __init__(
        self,
        store: ConfigStore | None = None,
        status_callback: StatusCallback | None = None,
        control_callback: ControlCallback | None = None,
    ) -> None:
        self.log = get_logger("bridge")
        self.store = store or ConfigStore()
        self.config: BridgeConfig = self.store.load()
        self.status_callback = status_callback
        self.control_callback = control_callback
        self.state = RuntimeState()
        self._stop_event = threading.Event()
        self._local_thread: threading.Thread | None = None
        self._sender_thread: threading.Thread | None = None
        self._usage_push_thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._send_condition = threading.Condition()
        self._send_queue: deque[dict[str, Any]] = deque(maxlen=32)
        self._last_send_at = 0.0
        self._min_send_interval_sec = 0.02
        self._usage_monitor = CodexUsageMonitor()
        self._heartbeat_interval_sec = 3.0
        self._usage_push_interval_sec = 60.0
        self._last_usage_push_at = 0.0
        self._connection_check_interval_sec = 6.0
        self._connection_check_timeout_sec = 2.0
        self._connection_check_max_misses = 5
        self._connection_check_misses = 0
        self._last_connection_check_at = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self, auto_connect: bool = True) -> None:
        self.log.info("bridge started")
        self._stop_event.clear()
        self._local_thread = threading.Thread(target=self._local_udp_loop, name="PixelMugLocalUdp", daemon=True)
        self._local_thread.start()
        self._sender_thread = threading.Thread(target=self._status_sender_loop, name="PixelMugStatusSender", daemon=True)
        self._sender_thread.start()
        self._usage_monitor.start()
        self._usage_push_thread = threading.Thread(target=self._usage_push_loop, name="PixelMugUsagePush", daemon=True)
        self._usage_push_thread.start()
        if auto_connect:
            self._threaded(self.connect, True)

    def stop(self) -> None:
        self._stop_event.set()
        with self._send_condition:
            self._send_condition.notify_all()
        self._usage_monitor.stop()
        self.state.connection = "Disconnected"
        self._notify()
        self.log.info("bridge stopped")

    def _threaded(self, target: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True).start()

    def run_forever(self) -> None:
        self.start(auto_connect=True)
        try:
            while not self._stop_event.is_set():
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # ------------------------------------------------------------------
    # Local hook receive
    # ------------------------------------------------------------------
    def _local_udp_loop(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((LOCAL_HOST, LOCAL_HOOK_PORT))
            sock.settimeout(0.25)
            while not self._stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                except OSError as exc:
                    self.log.info("local udp stopped: %s", exc)
                    break
                try:
                    msg = json.loads(data.decode("utf-8"))
                    if not isinstance(msg, dict):
                        continue
                    msg_type = msg.get("type")
                    if msg_type == LOCAL_MSG_TYPE:
                        self.log.info("hook message received state=%s event=%s tool=%s", msg.get("state"), msg.get("event"), msg.get("tool"))
                        self.handle_local_message(msg)
                    elif msg_type == CONTROL_MSG_TYPE:
                        self.handle_control_message(msg)
                except Exception as exc:
                    self.log.warning("invalid local hook packet from %s: %s", addr, exc)

    def handle_control_message(self, msg: dict[str, Any]) -> None:
        cmd = str(msg.get("cmd") or "")
        self.log.info("control command=%s", cmd)
        if self.control_callback and self.control_callback(msg):
            return
        if cmd == "connect":
            self._threaded(self.connect, True)
        elif cmd == "disconnect":
            self.disconnect()
        elif cmd == "send_test":
            self._threaded(
                self.send_test_status,
                str(msg.get("state") or "prompt"),
                str(msg.get("text") or "test from macOS"),
            )
        elif cmd == "quit":
            self.stop()
        elif cmd == "pair":
            self.state.last_error = "pair requires the macOS menu bar app"
            self._notify()

    def handle_local_message(self, msg: dict[str, Any]) -> None:
        with self._lock:
            self.state.last_state = str(msg.get("state") or "idle")
        self._notify()
        if self.state.connection != "Connected":
            self._threaded(self.connect, True)
        if self.state.connection == "Connected":
            self._enqueue_status(msg)

    def _enqueue_status(self, msg: dict[str, Any]) -> None:
        with self._send_condition:
            dropped = len(self._send_queue) == self._send_queue.maxlen
            self._send_queue.append(msg)
            if dropped:
                self.log.info("status queue full; dropped oldest local hook message")
            self._send_condition.notify()

    def _next_status_message(self) -> dict[str, Any] | None:
        with self._send_condition:
            while not self._stop_event.is_set() and not self._send_queue:
                self._send_condition.wait(timeout=0.25)
            if self._stop_event.is_set():
                return None
            return self._send_queue.popleft()

    def _status_sender_loop(self) -> None:
        while not self._stop_event.is_set():
            msg = self._next_status_message()
            if msg is None:
                continue
            try:
                self.send_status(msg)
            except Exception as exc:
                self.log.warning("status sender error: %s", exc)

    def _clear_status_queue(self) -> None:
        with self._send_condition:
            self._send_queue.clear()

    def _usage_push_loop(self) -> None:
        while not self._stop_event.wait(self._heartbeat_interval_sec):
            if self.state.connection != "Connected":
                continue
            now = time.monotonic()
            if now - self._last_connection_check_at >= self._connection_check_interval_sec:
                if not self._verify_connected_device():
                    continue
                now = time.monotonic()
            push_usage = now - self._last_usage_push_at >= self._usage_push_interval_sec
            if push_usage:
                self._last_usage_push_at = now
            event = "UsageRefresh" if push_usage else "Heartbeat"
            text = "usage refreshed" if push_usage else "heartbeat"
            self._enqueue_status(
                {
                    "state": "idle",
                    "event": event,
                    "tool": "",
                    "repo": "macOS",
                    "text": text,
                    "ts": now_ts(),
                }
            )

    def _verify_connected_device(self) -> bool:
        device = self.config.active_device()
        if not device or not device.token:
            self.state.last_error = "no paired PixelMug"
            self._clear_status_queue()
            self.state.connection = "Disconnected"
            self._notify()
            return False

        self._last_connection_check_at = time.monotonic()
        for item in self.discover(
            timeout=self._connection_check_timeout_sec,
            target_device_id=device.device_id,
            preferred_host=device.last_host,
            preferred_port=device.pair_port,
        ):
            if item.get("device_id") == device.device_id:
                device.last_host = str(item.get("host") or device.last_host)
                device.status_port = int(item.get("status_port") or device.status_port)
                device.pair_port = int(item.get("pair_port") or device.pair_port)
                self.config.upsert_device(device)
                self.store.save(self.config)
                if not self._auth_check_device(device, timeout=self._connection_check_timeout_sec):
                    return False
                self._connection_check_misses = 0
                return True

        self._connection_check_misses += 1
        self.log.info(
            "connection check missed device_id=%s misses=%d",
            device.device_id,
            self._connection_check_misses,
        )
        if self._connection_check_misses >= self._connection_check_max_misses:
            self.state.last_error = "PixelMug went offline"
            self._clear_status_queue()
            self.state.connection = "Disconnected"
            self._notify()
            return False
        return True

    # ------------------------------------------------------------------
    # Pairing and connection
    # ------------------------------------------------------------------
    def discover(
        self,
        timeout: float = DISCOVER_TIMEOUT_SEC,
        target_device_id: str = "",
        preferred_host: str = "",
        preferred_port: int = PIXELMUG_PAIR_PORT,
    ) -> list[dict[str, Any]]:
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        packet = {
            "type": PAIR_MSG_TYPE,
            "v": PROTOCOL_VERSION,
            "cmd": "discover",
            "request_id": request_id,
            "bridge_id": self.config.bridge_id,
        }
        packet_data = json_dumps_bytes(packet)
        found: dict[str, dict[str, Any]] = {}
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.35)

            def send_broadcast() -> None:
                sock.sendto(packet_data, (BROADCAST_ADDR, PIXELMUG_PAIR_PORT))

            if preferred_host:
                try:
                    sock.sendto(packet_data, (preferred_host, preferred_port or PIXELMUG_PAIR_PORT))
                except OSError as exc:
                    self.log.info("preferred discover send failed host=%s error=%s", preferred_host, exc)
                    send_broadcast()
            else:
                send_broadcast()

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    # Prefer a saved host first; broadcast after the first miss and keep
                    # rebroadcasting to survive Wi-Fi lossiness.
                    try:
                        send_broadcast()
                    except OSError:
                        pass
                    continue
                try:
                    msg = json.loads(data.decode("utf-8"))
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") != PAIR_MSG_TYPE or msg.get("cmd") != "device_info":
                        continue
                    if msg.get("request_id") != request_id:
                        continue
                    device_id = str(msg.get("device_id") or "")
                    if not device_id:
                        continue
                    msg["host"] = addr[0]
                    found[device_id] = msg
                    self.log.info("pixelmug discovered device_id=%s host=%s pairing_enabled=%s", device_id, addr[0], msg.get("pairing_enabled"))
                    if target_device_id and device_id == target_device_id:
                        return [msg]
                except Exception as exc:
                    self.log.warning("invalid discover response: %s", exc)
        return list(found.values())

    def pair(self, code_provider: Callable[[dict[str, Any]], str], timeout: float = PAIR_TIMEOUT_SEC) -> PairedDevice:
        self.state.connection = "Pairing"
        self._notify()
        devices = self.discover()
        pairable = [d for d in devices if bool(d.get("pairing_enabled"))]
        if not pairable:
            self.state.connection = "Disconnected"
            self._notify()
            raise PairingError("No PixelMug in pairing mode. Double-click PixelMug to enter pairing mode, then try again.")

        target = pairable[0]
        host = str(target.get("host"))
        device_id = str(target.get("device_id"))
        pair_port = int(target.get("pair_port") or PIXELMUG_PAIR_PORT)

        request_id = f"req-{uuid.uuid4().hex[:12]}"
        pair_start = {
            "type": PAIR_MSG_TYPE,
            "v": PROTOCOL_VERSION,
            "cmd": "pair_start",
            "request_id": request_id,
            "bridge_id": self.config.bridge_id,
            "device_id": device_id,
        }
        code_shown = self._send_pair_request_wait(host, pair_port, pair_start, expected_cmd="pair_code_shown", timeout=timeout)
        if not code_shown:
            raise PairingError("PixelMug did not confirm that a pair code is shown.")
        if code_shown.get("cmd") == "pair_error":
            raise PairingError(f"Pair start failed: {code_shown.get('error')}")

        self.log.info("pair started device_id=%s", device_id)
        code = code_provider(code_shown).strip()
        if not code:
            raise PairingError("Pairing canceled.")
        token = secrets.token_hex(32)
        confirm_req = f"req-{uuid.uuid4().hex[:12]}"
        pair_confirm = {
            "type": PAIR_MSG_TYPE,
            "v": PROTOCOL_VERSION,
            "cmd": "pair_confirm",
            "request_id": confirm_req,
            "bridge_id": self.config.bridge_id,
            "device_id": device_id,
            "code": code,
            "token": token,
        }
        msg = self._send_pair_request_wait(host, pair_port, pair_confirm, expected_cmd="paired", timeout=timeout)
        if not msg:
            raise PairingError("Timed out waiting for PixelMug pairing confirmation.")
        if msg.get("cmd") == "pair_error":
            self.log.info("pair failed device_id=%s error=%s", device_id, msg.get("error"))
            raise PairingError(f"Pair failed: {msg.get('error')}")
        if msg.get("cmd") == "paired" and bool(msg.get("ok", True)):
            device = PairedDevice(
                device_id=device_id,
                device_name=str(target.get("device_name") or "PixelMug"),
                last_host=host,
                status_port=int(target.get("status_port") or 39217),
                pair_port=pair_port,
                token=token,
            )
            self.config.upsert_device(device)
            self.store.save(self.config)
            self.log.info("pair success device_id=%s host=%s", device_id, host)
            self.state.connection = "Connected"
            self.state.last_device = device_id
            self._connection_check_misses = 0
            self._last_connection_check_at = time.monotonic()
            self._notify()
            self.send_test_status(state="idle", text="paired")
            return device
        raise PairingError(f"Pair failed: {msg.get('error') or 'not_ok'}")

    def _send_pair_request_wait(
        self,
        host: str,
        port: int,
        payload: dict[str, Any],
        *,
        expected_cmd: str,
        timeout: float,
    ) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        request_id = payload.get("request_id")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.35)
            while time.monotonic() < deadline:
                try:
                    sock.sendto(json_dumps_bytes(payload), (host, port))
                except OSError as exc:
                    self.log.warning("pair request send failed: %s", exc)
                try:
                    data, _addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                try:
                    msg = json.loads(data.decode("utf-8"))
                except Exception:
                    continue
                if not isinstance(msg, dict) or msg.get("type") != PAIR_MSG_TYPE:
                    continue
                if request_id and msg.get("request_id") != request_id:
                    continue
                if msg.get("cmd") in (expected_cmd, "pair_error"):
                    return msg
        return None

    def _set_auth_failed(self, error: str = "") -> None:
        if error in ("token_mismatch", "bridge_mismatch", "not_paired"):
            self.state.last_error = "PixelMug is paired with another host. Pair again to use this host."
        else:
            self.state.last_error = error or "PixelMug auth check failed"
        self._clear_status_queue()
        self.state.connection = "Disconnected"
        self._notify()

    def _auth_check_device(self, device: PairedDevice, timeout: float = PAIR_TIMEOUT_SEC) -> bool:
        if not device.last_host or not device.token:
            self._set_auth_failed("missing saved PixelMug auth")
            return False
        request = make_auth_check_message(self.config.bridge_id, device.device_id, device.token)
        result = self._send_pair_request_wait(
            device.last_host,
            device.pair_port or PIXELMUG_PAIR_PORT,
            request,
            expected_cmd="auth_ok",
            timeout=timeout,
        )
        if not result:
            self._set_auth_failed("PixelMug auth check timed out")
            self.log.info("auth check timed out device_id=%s host=%s", device.device_id, device.last_host)
            return False
        if not bool(result.get("ok")):
            error = str(result.get("error") or "auth_failed")
            self._set_auth_failed(error)
            self.log.info("auth check rejected device_id=%s error=%s", device.device_id, error)
            return False
        self.state.last_error = ""
        self.log.info("auth check ok device_id=%s", device.device_id)
        return True

    def connect(self, use_discover: bool = True) -> bool:
        device = self.config.active_device()
        if not device or not device.token:
            self.state.connection = "Disconnected"
            self._notify()
            return False

        if use_discover:
            self.state.connection = "Connecting"
            self._notify()
            discovered = False
            devices = self.discover(
                timeout=DISCOVER_TIMEOUT_SEC,
                target_device_id=device.device_id,
                preferred_host=device.last_host,
                preferred_port=device.pair_port,
            )
            for item in devices:
                if item.get("device_id") == device.device_id:
                    device.last_host = str(item.get("host") or device.last_host)
                    device.status_port = int(item.get("status_port") or device.status_port)
                    device.pair_port = int(item.get("pair_port") or device.pair_port)
                    self.config.upsert_device(device)
                    self.store.save(self.config)
                    discovered = True
                    break
            if not discovered:
                self.state.connection = "Disconnected"
                self.state.last_error = "saved PixelMug not found"
                self._notify()
                self.log.info("connect skipped; saved device was not discovered device_id=%s", device.device_id)
                return False

        if not device.last_host:
            self.state.connection = "Disconnected"
            self.state.last_error = "no saved PixelMug host"
            self._notify()
            return False

        if not self._auth_check_device(device):
            return False

        self.state.connection = "Connected"
        self.state.last_device = device.device_id
        self._connection_check_misses = 0
        self._last_connection_check_at = time.monotonic()
        self._notify()
        self.send_test_status(state="idle", text="bridge connected")
        self.log.info("connected device_id=%s host=%s", device.device_id, device.last_host)
        return True

    def disconnect(self) -> None:
        if self.config.active_device():
            self.send_status(
                {
                    "state": "disconnected",
                    "event": "BridgeDisconnected",
                    "tool": "",
                    "repo": "macOS",
                    "text": "bridge disconnected",
                    "connected": False,
                    "ts": now_ts(),
                }
            )
        self._clear_status_queue()
        self._connection_check_misses = 0
        self._last_connection_check_at = 0.0
        self.state.connection = "Disconnected"
        self._notify()
        self.log.info("disconnected")

    # ------------------------------------------------------------------
    # Status sending
    # ------------------------------------------------------------------
    def send_status(self, local_msg: dict[str, Any]) -> bool:
        device = self.config.active_device()
        if not device or not device.token or not device.last_host:
            self.state.connection = "Disconnected"
            self._notify()
            return False

        now = time.monotonic()
        if now - self._last_send_at < self._min_send_interval_sec:
            time.sleep(self._min_send_interval_sec - (now - self._last_send_at))
        self._last_send_at = time.monotonic()

        with self._lock:
            self.state.seq += 1
            seq = self.state.seq
        usage = self._usage_monitor.snapshot().as_packet_fields()
        packet = make_status_packet(local_msg, token=device.token, seq=seq, usage=usage)
        data = json_dumps_bytes(packet)
        if len(data) > MAX_UDP_PACKET_BYTES:
            # Re-trim optional fields if a unicode-heavy packet exceeds the target size.
            packet["text"] = str(packet.get("text", ""))[:24]
            data = json_dumps_bytes(packet)
        if len(data) > MAX_UDP_PACKET_BYTES:
            packet.pop("usage", None)
            data = json_dumps_bytes(packet)

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(data, (device.last_host, device.status_port))
            self.state.last_state = str(packet.get("state") or "idle")
            self.log.info("status sent seq=%s state=%s device_id=%s", seq, packet.get("state"), device.device_id)
            self._notify()
            return True
        except OSError as exc:
            self.state.connection = "Disconnected"
            self.state.last_error = str(exc)
            self.log.warning("udp send error device_id=%s error=%s", device.device_id, exc)
            self._notify()
            return False

    def send_test_status(
        self,
        state: str = "prompt",
        text: str = "test from macOS",
    ) -> bool:
        msg: dict[str, Any] = {
            "state": state,
            "event": "SendTestStatus",
            "tool": "",
            "repo": "macOS",
            "text": text,
            "ts": now_ts(),
        }
        return self.send_status(msg)

    def status_text(self) -> str:
        device = self.config.active_device()
        device_text = f" device={device.device_id}" if device else ""
        err = f" error={self.state.last_error}" if self.state.last_error else ""
        return f"{self.state.connection} state={self.state.last_state} seq={self.state.seq}{device_text}{err}"

    def _notify(self) -> None:
        if self.status_callback:
            try:
                self.status_callback(self.status_text())
            except Exception:
                pass
