from cb_config import PAIR_PORT, PAIR_TYPE, PROTOCOL_VERSION, STATUS_PORT, STATUS_TYPE
from cb_storage import save_pairing
from cb_time import now_ms, ticks_add, ticks_diff
from cb_utils import json_bytes, make_pair_code, parse_json, short


class PairProtocol:
    def __init__(self, app):
        self.app = app
        self.enabled = False
        self.deadline = 0
        self.code = ""
        self.last_confirm_request_id = ""
        self.last_confirm_payload = None

    def begin(self):
        self.enabled = True
        self.deadline = ticks_add(now_ms(), self.app.pair_ttl_ms)
        self.code = make_pair_code()
        self.last_confirm_request_id = ""
        self.last_confirm_payload = None
        self.app.show_pair_code(self.code)
        print("[PAIR] enabled code=%s ttl=%ds" % (self.code, self.app.pair_ttl_ms // 1000))

    def cancel(self, timeout=False):
        self.enabled = False
        self.code = ""
        self.last_confirm_request_id = ""
        self.last_confirm_payload = None
        if timeout:
            self.app.show_pair_timeout()

    def expired(self):
        return self.enabled and ticks_diff(now_ms(), self.deadline) >= 0

    def seconds_left(self):
        if not self.enabled:
            return 0
        remaining = ticks_diff(self.deadline, now_ms())
        if remaining <= 0:
            return 0
        return (remaining + 999) // 1000

    def poll(self):
        sock = self.app.pair_sock
        if sock is None:
            return
        while True:
            try:
                data, addr = sock.recvfrom(self.app.udp_packet_max)
            except OSError:
                return
            msg = parse_json(data)
            if not msg or msg.get("type") != PAIR_TYPE or msg.get("v") != PROTOCOL_VERSION:
                continue
            cmd = msg.get("cmd")
            if cmd == "discover":
                self.handle_discover(msg, addr)
            elif cmd == "pair_start":
                self.handle_pair_start(msg, addr)
            elif cmd == "pair_confirm":
                self.handle_pair_confirm(msg, addr)
            elif cmd == "auth_check":
                self.handle_auth_check(msg, addr)

    def send(self, payload, addr):
        try:
            self.app.pair_sock.sendto(json_bytes(payload), addr)
        except Exception as exc:
            print("[PAIR] send failed:", exc)

    def base_response(self, cmd, request_id):
        return {
            "type": PAIR_TYPE,
            "v": PROTOCOL_VERSION,
            "cmd": cmd,
            "request_id": request_id,
            "device_id": self.app.device_id,
        }

    def error(self, request_id, addr, error):
        payload = self.base_response("pair_error", request_id)
        payload["error"] = error
        self.send(payload, addr)
        if error == "invalid_code":
            self.app.show_pair_error()
        print("[PAIR] failed error=%s" % error)

    def handle_discover(self, msg, addr):
        request_id = msg.get("request_id", "")
        payload = self.base_response("device_info", request_id)
        payload["device_name"] = self.app.device_name
        payload["pairing_enabled"] = bool(self.enabled)
        payload["paired"] = bool(self.app.paired)
        payload["status_port"] = STATUS_PORT
        payload["pair_port"] = PAIR_PORT
        self.send(payload, addr)

    def handle_pair_start(self, msg, addr):
        request_id = msg.get("request_id", "")
        if msg.get("device_id") != self.app.device_id:
            self.error(request_id, addr, "invalid_device")
            return
        if not self.enabled:
            self.error(request_id, addr, "not_in_pair_mode")
            return
        if self.expired():
            self.cancel(timeout=True)
            self.error(request_id, addr, "expired")
            return
        payload = self.base_response("pair_code_shown", request_id)
        payload["ttl"] = self.seconds_left()
        self.send(payload, addr)

    def handle_auth_check(self, msg, addr):
        request_id = msg.get("request_id", "")
        payload = self.base_response("auth_ok", request_id)
        payload["ok"] = False
        if msg.get("device_id") != self.app.device_id:
            payload["error"] = "invalid_device"
            self.send(payload, addr)
            return
        if not self.app.paired:
            payload["error"] = "not_paired"
            self.send(payload, addr)
            return

        expected_token = self.app.pairing.get("token")
        expected_bridge_id = self.app.pairing.get("bridge_id")
        bridge_id = str(msg.get("bridge_id", ""))
        token = str(msg.get("token", ""))
        if token != expected_token:
            payload["error"] = "token_mismatch"
        elif expected_bridge_id and bridge_id != expected_bridge_id:
            payload["error"] = "bridge_mismatch"
        else:
            payload["ok"] = True
        self.send(payload, addr)

    def handle_pair_confirm(self, msg, addr):
        request_id = msg.get("request_id", "")
        if request_id and request_id == self.last_confirm_request_id and self.last_confirm_payload:
            self.send(self.last_confirm_payload, addr)
            return
        if msg.get("device_id") != self.app.device_id:
            self.error(request_id, addr, "invalid_device")
            return
        if not self.enabled:
            self.error(request_id, addr, "not_in_pair_mode")
            return
        if self.expired():
            self.cancel(timeout=True)
            self.error(request_id, addr, "expired")
            return

        self.app.show_pair_verifying()
        if not self.code or str(msg.get("code", "")) != self.code:
            self.error(request_id, addr, "invalid_code")
            self.code = make_pair_code()
            self.app.defer_pair_code(self.code)
            return

        token = str(msg.get("token", ""))
        if len(token) < 16:
            self.error(request_id, addr, "invalid_token")
            return

        pairing = {
            "paired": True,
            "bridge_id": str(msg.get("bridge_id", "")),
            "token": token,
            "device_id": self.app.device_id,
            "device_name": self.app.device_name,
            "status_port": STATUS_PORT,
            "pair_port": PAIR_PORT,
        }
        try:
            save_pairing(pairing)
        except Exception as exc:
            print("[PAIR] save failed:", exc)
            self.error(request_id, addr, "internal_error")
            return

        self.app.pairing = pairing
        self.enabled = False
        self.code = ""
        self.app.on_pair_success()

        payload = self.base_response("paired", request_id)
        payload["ok"] = True
        self.last_confirm_request_id = request_id
        self.last_confirm_payload = payload
        self.send(payload, addr)
        print("[PAIR] success")


class StatusProtocol:
    def __init__(self, app):
        self.app = app
        self.last_seq = -1
        self.last_ts = 0

    def reset(self):
        self.last_seq = -1
        self.last_ts = 0

    def poll(self):
        sock = self.app.status_sock
        if sock is None:
            return
        while True:
            try:
                data, _addr = sock.recvfrom(self.app.udp_packet_max)
            except OSError:
                return
            msg = parse_json(data)
            if not msg or msg.get("type") != STATUS_TYPE or msg.get("v") != PROTOCOL_VERSION:
                continue
            self.handle(msg)

    def handle(self, msg):
        if not self.app.paired:
            return
        if msg.get("token") != self.app.pairing.get("token"):
            return
        try:
            seq = int(msg.get("seq"))
        except Exception:
            return
        try:
            ts = int(msg.get("ts") or 0)
        except Exception:
            ts = 0

        seq_reset = seq <= self.last_seq and ts > self.last_ts
        if seq <= self.last_seq and not seq_reset:
            return

        self.last_seq = seq
        self.last_ts = ts

        event = short(msg.get("event") or "", 32)
        state = short(msg.get("state") or "idle", 24)
        event_key = event.lower()
        state_key = state.lower()
        disconnected = msg.get("connected") is False
        disconnected = disconnected or event_key in ("disconnect", "disconnected", "bridgedisconnect", "bridgedisconnected")
        disconnected = disconnected or state_key in ("disconnect", "disconnected", "offline")
        if disconnected:
            self.app.mark_disconnected()
            print("[CODEX] seq=%d disconnected" % seq)
            return

        usage = msg.get("usage")
        if isinstance(usage, dict):
            self.app.usage = usage
        if event not in ("UsageRefresh", "Heartbeat"):
            if event_key == "userpromptsubmit" and self.app.can_set_host_state("working", event):
                self.app.set_host_state("working")
            elif state_key != "session" and state_key != "error" and self.app.can_set_host_state(state, event):
                self.app.set_host_state(state)
        self.app.mark_connected()
        if event not in ("UsageRefresh", "Heartbeat"):
            print("[CODEX] seq=%d state=%s" % (seq, self.app.host_state))
