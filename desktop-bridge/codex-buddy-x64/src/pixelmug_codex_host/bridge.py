from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from .autostart import get_autostart, set_autostart
from .config import AppConfig, PairedDevice, load_config, save_config
from .constants import (
    CONTROL_MESSAGE_TYPE,
    DISCOVER_TIMEOUT_SEC,
    LOCAL_HOST,
    LOCAL_HOOK_PORT,
    LOCAL_MESSAGE_TYPE,
    PAIR_MESSAGE_TYPE,
    PAIR_PORT,
    PAIR_TIMEOUT_SEC,
    PROTOCOL_VERSION,
    STATUS_PORT,
    UDP_PACKET_MAX,
)
from .logging_utils import configure_file_logger
from .network import broadcast_targets
from .paths import bridge_log_path, logs_dir
from .protocol import (
    json_dumps_bytes,
    json_loads_bytes,
    make_auth_check_message,
    make_control_message,
    make_discover_message,
    make_pair_confirm_message,
    make_pair_start_message,
    make_status_packet,
    now_ts,
    send_udp,
    truncate_text,
)
from .usage import CodexUsageMonitor

StatusCallback = Callable[[str], None]


@dataclass
class RuntimeState:
    connection: str = "Disconnected"
    last_state: str = "idle"
    last_error: str = ""
    last_device: str = ""
    seq: int = 0


class PairingError(RuntimeError):
    pass


class BridgeService:
    def __init__(self) -> None:
        self.logger = configure_file_logger("pixelmug_codex_bridge", bridge_log_path())
        self.cfg: AppConfig = load_config()
        self.state = RuntimeState()
        self.on_status_change: StatusCallback | None = None
        self.running = threading.Event()
        self.running.set()
        self.connected = False
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
        self._local_sock: socket.socket | None = None
        self._local_thread: threading.Thread | None = None
        self._sender_thread: threading.Thread | None = None
        self._usage_thread: threading.Thread | None = None

    @property
    def status_text(self) -> str:
        device = self.cfg.active_device()
        device_text = f" device={device.device_id}" if device else ""
        err = f" error={self.state.last_error}" if self.state.last_error else ""
        return f"{self.state.connection} state={self.state.last_state} seq={self.state.seq}{device_text}{err}"

    def start(self, auto_connect: bool = True) -> None:
        self.logger.info("bridge started bridge_id=%s", self.cfg.bridge_id)
        self.running.set()
        self._local_thread = threading.Thread(target=self._local_udp_loop, name="PixelMugLocalUdp", daemon=True)
        self._local_thread.start()
        self._sender_thread = threading.Thread(target=self._status_sender_loop, name="PixelMugStatusSender", daemon=True)
        self._sender_thread.start()
        self._usage_monitor.start()
        self._usage_thread = threading.Thread(target=self._usage_push_loop, name="PixelMugUsagePush", daemon=True)
        self._usage_thread.start()
        if auto_connect:
            self.threaded(self.connect_saved_device, True)

    def stop(self) -> None:
        self.running.clear()
        self.connected = False
        self._usage_monitor.stop()
        with self._send_condition:
            self._send_condition.notify_all()
        try:
            if self._local_sock:
                self._local_sock.close()
        except Exception:
            pass
        self._set_connection("Disconnected")
        self.logger.info("bridge stopped")

    def threaded(self, target: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True).start()

    def _notify(self) -> None:
        if self.on_status_change:
            try:
                self.on_status_change(self.status_text)
            except Exception:
                self.logger.exception("status callback failed")

    def _set_connection(self, text: str) -> None:
        self.state.connection = text
        self.connected = text.startswith("Connected") or text == "Connected"
        self.logger.info("status=%s", self.status_text)
        self._notify()

    def _local_udp_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._local_sock = sock
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((LOCAL_HOST, LOCAL_HOOK_PORT))
        sock.settimeout(0.25)
        self.logger.info("local UDP listening on %s:%d", LOCAL_HOST, LOCAL_HOOK_PORT)
        while self.running.is_set():
            try:
                data, addr = sock.recvfrom(UDP_PACKET_MAX)
            except socket.timeout:
                continue
            except OSError as exc:
                self.logger.info("local udp stopped: %s", exc)
                break
            msg = json_loads_bytes(data)
            if not msg:
                continue
            msg_type = msg.get("type")
            if msg_type == LOCAL_MESSAGE_TYPE:
                self.logger.info("hook message received state=%s event=%s tool=%s", msg.get("state"), msg.get("event"), msg.get("tool"))
                self.handle_local_codex_message(msg)
            elif msg_type == CONTROL_MESSAGE_TYPE:
                self.handle_control_message(msg)
            else:
                self.logger.warning("invalid local packet from %s", addr)

    def handle_control_message(self, msg: dict[str, Any]) -> None:
        cmd = msg.get("cmd")
        self.logger.info("control command=%s", cmd)
        if cmd == "pair":
            self.threaded(self.pair_device)
        elif cmd == "connect":
            self.threaded(self.connect_saved_device, True)
        elif cmd == "disconnect":
            self.disconnect()
        elif cmd == "send_test":
            self.send_test_status()
        elif cmd == "quit":
            self.stop()
        elif cmd == "open_logs":
            self.open_logs()

    def handle_local_codex_message(self, msg: dict[str, Any]) -> None:
        with self._lock:
            self.state.last_state = str(msg.get("state") or "idle")
        self._notify()
        if not self.connected:
            self.threaded(self.connect_saved_device, True)
        if self.connected:
            self._enqueue_status(msg)
        else:
            self.logger.info("skip status because bridge is disconnected")

    def _enqueue_status(self, msg: dict[str, Any]) -> None:
        with self._send_condition:
            dropped = len(self._send_queue) == self._send_queue.maxlen
            self._send_queue.append(msg)
            if dropped:
                self.logger.info("status queue full; dropped oldest local hook message")
            self._send_condition.notify()

    def _clear_status_queue(self) -> None:
        with self._send_condition:
            self._send_queue.clear()

    def _next_status_message(self) -> dict[str, Any] | None:
        with self._send_condition:
            while self.running.is_set() and not self._send_queue:
                self._send_condition.wait(timeout=0.25)
            if not self.running.is_set():
                return None
            return self._send_queue.popleft()

    def _status_sender_loop(self) -> None:
        while self.running.is_set():
            msg = self._next_status_message()
            if msg is None:
                continue
            try:
                self.send_status(msg)
            except Exception as exc:
                self.logger.warning("status sender error: %s", exc)

    def _usage_push_loop(self) -> None:
        while self.running.is_set():
            time.sleep(self._heartbeat_interval_sec)
            if not self.running.is_set() or not self.connected:
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
                    "repo": "Windows",
                    "text": text,
                    "ts": now_ts(),
                }
            )

    def _verify_connected_device(self) -> bool:
        device = self.cfg.active_device()
        if not device or not device.token:
            self.state.last_error = "no paired PixelMug"
            self._clear_status_queue()
            self._set_connection("Disconnected")
            return False

        self._last_connection_check_at = time.monotonic()
        for item in self.discover_devices(
            timeout_s=self._connection_check_timeout_sec,
            target_device_id=device.device_id,
            target_host=device.last_host,
        ):
            if item.get("device_id") == device.device_id:
                device.last_host = str(item.get("host") or device.last_host)
                device.status_port = int(item.get("status_port") or device.status_port)
                device.pair_port = int(item.get("pair_port") or device.pair_port)
                self.cfg.upsert_device(device)
                save_config(self.cfg)
                if not self._auth_check_device(device, timeout_s=self._connection_check_timeout_sec):
                    return False
                self._connection_check_misses = 0
                return True
        self._connection_check_misses += 1
        self.logger.info(
            "connection check missed device_id=%s misses=%d",
            device.device_id,
            self._connection_check_misses,
        )
        if self._connection_check_misses >= self._connection_check_max_misses:
            self.state.last_error = "PixelMug went offline"
            self._clear_status_queue()
            self._set_connection("Disconnected")
            return False
        return True

    def discover_devices(
        self,
        timeout_s: float = DISCOVER_TIMEOUT_SEC,
        target_device_id: str = "",
        target_host: str = "",
    ) -> list[dict[str, Any]]:
        request = make_discover_message(self.cfg.bridge_id)
        found: dict[str, dict[str, Any]] = {}
        deadline = time.monotonic() + timeout_s
        targets = broadcast_targets()
        if target_host:
            targets = [target_host] + [target for target in targets if target != target_host]
        self.logger.info("discover targets=%s", ",".join(targets))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(0.35)
            while time.monotonic() < deadline:
                for target in targets:
                    try:
                        sock.sendto(json_dumps_bytes(request), (target, PAIR_PORT))
                    except OSError as exc:
                        self.logger.warning("discover broadcast failed target=%s error=%s", target, exc)
                try:
                    data, addr = sock.recvfrom(UDP_PACKET_MAX)
                except socket.timeout:
                    continue
                msg = json_loads_bytes(data)
                if not msg or msg.get("type") != PAIR_MESSAGE_TYPE or msg.get("cmd") != "device_info":
                    continue
                if msg.get("request_id") != request.get("request_id"):
                    continue
                device_id = truncate_text(msg.get("device_id"), 64)
                if not device_id:
                    continue
                msg["host"] = addr[0]
                found[device_id] = msg
                self.logger.info("pixelmug discovered device_id=%s host=%s pairing_enabled=%s", device_id, addr[0], msg.get("pairing_enabled"))
                if target_device_id and device_id == target_device_id:
                    return [msg]
        return list(found.values())

    def pair_device(self) -> None:
        try:
            self._pair_device()
        except Exception as exc:
            self.state.last_error = str(exc)
            self._set_connection("Disconnected")
            show_error("Pair PixelMug", str(exc))

    def _pair_device(self) -> PairedDevice:
        progress = show_pair_progress("Pair PixelMug", "Discovering PixelMug...")
        try:
            self._set_connection("Pairing")
            candidates = self.discover_devices(timeout_s=DISCOVER_TIMEOUT_SEC)
            pairable = [item for item in candidates if bool(item.get("pairing_enabled"))]
            if not pairable:
                raise PairingError("No PixelMug in pairing mode. Double-click PixelMug to enter pairing mode, then try again.")

            target = pairable[0]
            host = str(target.get("host") or "")
            device_id = str(target.get("device_id") or "")
            pair_port = int(target.get("pair_port") or PAIR_PORT)
            pair_start = make_pair_start_message(self.cfg.bridge_id, device_id)
            response = self._send_pair_request_wait(host, pair_port, pair_start, expected_cmd="pair_code_shown", timeout_s=PAIR_TIMEOUT_SEC)
            if not response:
                raise PairingError("PixelMug did not confirm that a pair code is shown.")
            if response.get("cmd") == "pair_error":
                raise PairingError(f"Pair start failed: {response.get('error')}")

            progress.close()
            progress = None
            code = ask_pair_code(str(target.get("device_name") or "PixelMug"), device_id, int(response.get("ttl") or 60))
            if not code:
                raise PairingError("Pairing canceled.")
            token = secrets.token_hex(32)
            confirm = make_pair_confirm_message(self.cfg.bridge_id, device_id, code.strip(), token)
            result = self._send_pair_request_wait(host, pair_port, confirm, expected_cmd="paired", timeout_s=PAIR_TIMEOUT_SEC)
            if not result or not result.get("ok", True):
                raise PairingError(f"Pair failed: {result.get('error') if result else 'timeout'}")
        finally:
            if progress is not None:
                progress.close()
        device = PairedDevice(
            device_id=device_id,
            device_name=str(target.get("device_name") or "PixelMug"),
            last_host=host,
            status_port=int(target.get("status_port") or STATUS_PORT),
            pair_port=pair_port,
            token=token,
        )
        self.cfg.upsert_device(device)
        save_config(self.cfg)
        self.state.last_device = device.device_id
        self._connection_check_misses = 0
        self._last_connection_check_at = time.monotonic()
        self._set_connection("Connected")
        self.logger.info("pair success device_id=%s host=%s", device_id, host)
        show_info("Pair PixelMug", f"Paired with {device.device_name} ({device.device_id}).")
        self.send_test_status(state="idle", text="paired")
        return device

    def _send_pair_request_wait(self, host: str, port: int, payload: dict[str, Any], *, expected_cmd: str, timeout_s: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout_s
        request_id = payload.get("request_id")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.35)
            while time.monotonic() < deadline:
                try:
                    sock.sendto(json_dumps_bytes(payload), (host, port))
                except OSError as exc:
                    self.logger.warning("pair request send failed: %s", exc)
                try:
                    data, _addr = sock.recvfrom(UDP_PACKET_MAX)
                except socket.timeout:
                    continue
                msg = json_loads_bytes(data)
                if not msg or msg.get("type") != PAIR_MESSAGE_TYPE:
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
        self._set_connection("Disconnected")

    def _auth_check_device(self, device: PairedDevice, timeout_s: float = PAIR_TIMEOUT_SEC) -> bool:
        if not device.last_host or not device.token:
            self._set_auth_failed("missing saved PixelMug auth")
            return False
        request = make_auth_check_message(self.cfg.bridge_id, device.device_id, device.token)
        result = self._send_pair_request_wait(
            device.last_host,
            device.pair_port or PAIR_PORT,
            request,
            expected_cmd="auth_ok",
            timeout_s=timeout_s,
        )
        if not result:
            self._set_auth_failed("PixelMug auth check timed out")
            self.logger.info("auth check timed out device_id=%s host=%s", device.device_id, device.last_host)
            return False
        if not bool(result.get("ok")):
            error = str(result.get("error") or "auth_failed")
            self._set_auth_failed(error)
            self.logger.info("auth check rejected device_id=%s error=%s", device.device_id, error)
            return False
        self.state.last_error = ""
        self.logger.info("auth check ok device_id=%s", device.device_id)
        return True

    def connect_saved_device(self, use_discover: bool = True) -> bool:
        device = self.cfg.active_device()
        if not device or not device.token:
            self._set_connection("Disconnected")
            return False
        discovered = not use_discover
        if use_discover:
            self._set_connection("Connecting")
            for item in self.discover_devices(
                timeout_s=DISCOVER_TIMEOUT_SEC,
                target_device_id=device.device_id,
                target_host=device.last_host,
            ):
                if item.get("device_id") == device.device_id:
                    device.last_host = str(item.get("host") or device.last_host)
                    device.status_port = int(item.get("status_port") or device.status_port)
                    device.pair_port = int(item.get("pair_port") or device.pair_port)
                    self.cfg.upsert_device(device)
                    save_config(self.cfg)
                    discovered = True
                    break
            if not discovered:
                self.state.last_error = "saved PixelMug not found"
                self._set_connection("Disconnected")
                self.logger.info("connect skipped; saved device was not discovered device_id=%s", device.device_id)
                return False
        if not device.last_host:
            self.state.last_error = "no saved PixelMug host"
            self._set_connection("Disconnected")
            return False
        if not self._auth_check_device(device):
            return False
        self.state.last_device = device.device_id
        self._connection_check_misses = 0
        self._last_connection_check_at = time.monotonic()
        self._set_connection("Connected")
        self.send_test_status(state="idle", text="bridge connected")
        self.logger.info("connected device_id=%s host=%s", device.device_id, device.last_host)
        return True

    def disconnect(self) -> None:
        if self.cfg.active_device():
            self.send_status(
                {
                    "state": "disconnected",
                    "event": "BridgeDisconnected",
                    "tool": "",
                    "repo": "Windows",
                    "text": "bridge disconnected",
                    "connected": False,
                    "ts": now_ts(),
                }
            )
        self._clear_status_queue()
        self._connection_check_misses = 0
        self._last_connection_check_at = 0.0
        self._set_connection("Disconnected")
        self.logger.info("disconnected")

    def send_status(self, local_msg: dict[str, Any]) -> bool:
        device = self.cfg.active_device()
        if not device or not device.token or not device.last_host:
            self._set_connection("Disconnected")
            return False

        now = time.monotonic()
        if now - self._last_send_at < self._min_send_interval_sec:
            time.sleep(self._min_send_interval_sec - (now - self._last_send_at))
        self._last_send_at = time.monotonic()

        with self._lock:
            self.state.seq += 1
            seq = self.state.seq
        usage = self._usage_monitor.snapshot().as_packet_fields()
        payload = make_status_packet(local_msg, token=device.token, seq=seq, usage=usage)
        data = json_dumps_bytes(payload)
        if len(data) > UDP_PACKET_MAX:
            payload["text"] = truncate_text(payload.get("text", ""), 24)
            data = json_dumps_bytes(payload)
        if len(data) > UDP_PACKET_MAX:
            payload.pop("usage", None)

        try:
            send_udp(payload, device.last_host, device.status_port, timeout=0.2)
            self.state.last_state = str(payload.get("state") or "idle")
            self.logger.info("status sent seq=%s state=%s device_id=%s", seq, payload.get("state"), device.device_id)
            self._notify()
            return True
        except OSError as exc:
            self.state.last_error = str(exc)
            self._set_connection("Disconnected")
            self.logger.warning("udp send error device_id=%s error=%s", device.device_id, exc)
            return False

    def send_test_status(self, state: str = "prompt", text: str = "test from Windows") -> bool:
        return self.send_status(
            {
                "state": state,
                "event": "SendTestStatus",
                "tool": "",
                "repo": "Windows",
                "text": text,
                "ts": now_ts(),
            }
        )

    def open_logs(self) -> None:
        logs_dir().mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(logs_dir()))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open", str(logs_dir())])

    def set_start_on_login(self, enabled: bool) -> None:
        bridge_exe = sys.executable
        set_autostart(enabled, bridge_exe=bridge_exe if enabled else None)
        self.cfg.start_on_login = enabled
        save_config(self.cfg)
        self.logger.info("start_on_login=%s", enabled)
        self._notify()

    def start_on_login_enabled(self) -> bool:
        return get_autostart() is not None


class PairProgressDialog:
    def __init__(self, title: str, message: str) -> None:
        self.proc: subprocess.Popen[str] | None = None
        self.title = title
        self.message = message
        if sys.platform == "win32":
            self._open_windows_dialog()
        else:
            try:
                print(f"{title}: {message}", file=sys.stderr)
            except Exception:
                pass

    def _open_windows_dialog(self) -> None:
        ps_title = self.title.replace("'", "''")
        ps_message = self.message.replace("'", "''")
        script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object System.Windows.Forms.Form
$form.Text = '{ps_title}'
$form.Size = New-Object System.Drawing.Size(340, 140)
$form.StartPosition = 'CenterScreen'
$form.TopMost = $true
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$label = New-Object System.Windows.Forms.Label
$label.Text = '{ps_message}'
$label.AutoSize = $true
$label.Location = New-Object System.Drawing.Point(24, 24)
$form.Controls.Add($label)
$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Style = 'Marquee'
$progress.MarqueeAnimationSpeed = 30
$progress.Size = New-Object System.Drawing.Size(280, 18)
$progress.Location = New-Object System.Drawing.Point(24, 58)
$form.Controls.Add($progress)
[void]$form.ShowDialog()
"""
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=flags,
            )
        except Exception:
            self.proc = None

    def close(self) -> None:
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=1.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def show_pair_progress(title: str, message: str) -> PairProgressDialog:
    return PairProgressDialog(title, message)

def show_info(title: str, message: str) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, str(message), str(title), 0x00000040)
            return
        except Exception:
            pass
    try:
        print(f"{title}: {message}", file=sys.stderr)
    except Exception:
        pass



def show_error(title: str, message: str) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, str(message), str(title), 0x00000010)
            return
        except Exception:
            pass
    try:
        print(f"{title}: {message}", file=sys.stderr)
    except Exception:
        pass


def ask_pair_code(device_name: str, device_id: str, ttl: int = 60) -> str | None:
    prompt = f"PixelMug has shown a 6-digit code. Enter it within {ttl}s.`n`n{device_name} ({device_id})"
    if sys.platform == "win32":
        ps_prompt = prompt.replace("'", "''")
        script = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"[Microsoft.VisualBasic.Interaction]::InputBox('{ps_prompt}', 'PixelMug Pairing', '')"
        )
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                check=False,
                capture_output=True,
                text=True,
                creationflags=flags,
                timeout=ttl + 10,
            )
            code = result.stdout.strip()
            return code or None
        except Exception:
            return None
    try:
        return input(f"PixelMug pairing code for {device_name} ({device_id}): ").strip() or None
    except Exception:
        return None


def run_headless_forever(service: BridgeService) -> int:
    service.start()
    try:
        while service.running.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        service.stop()
    return 0


def main() -> int:
    service = BridgeService()
    try:
        from .tray import run_tray

        return run_tray(service)
    except Exception:
        service.logger.exception("tray failed; running headless")
        return run_headless_forever(service)


if __name__ == "__main__":
    raise SystemExit(main())



