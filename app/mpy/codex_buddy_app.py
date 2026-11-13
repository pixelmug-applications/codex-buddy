import micropyxel as pyxel
import mpy_button as touch_events

from cb_assets import load_assets
from cb_config import (
    DEVICE_NAME,
    FPS,
    PAIR_PORT,
    PERMISSION_MIN_DISPLAY_MS,
    PAIR_TTL_MS,
    STATUS_PORT,
    STATUS_TIMEOUT_MS,
    UDP_PACKET_MAX,
)
from cb_net import make_udp_socket, wifi_status_text
from cb_protocol import PairProtocol, StatusProtocol
from cb_storage import load_pairing
from cb_time import now_ms, ticks_add, ticks_diff
from cb_utils import make_device_id
from state_connection import ConnectionScreen
from state_function import FunctionScreen
from state_pairing import PairingScreen


APP_CONNECTION = 0
APP_PAIRING = 1
APP_FUNCTION = 2


class CodexBuddyApp:
    def __init__(self):
        self.device_name = DEVICE_NAME
        self.device_id = make_device_id()
        self.pairing = load_pairing()
        self.pairing["device_id"] = self.device_id

        self.pair_ttl_ms = PAIR_TTL_MS
        self.status_timeout_ms = STATUS_TIMEOUT_MS
        self.permission_min_display_ms = PERMISSION_MIN_DISPLAY_MS
        self.udp_packet_max = UDP_PACKET_MAX

        self.frame = 0
        self.mode = APP_CONNECTION
        self.host_state = "idle"
        self.permission_until_ms = 0
        self.usage = {}
        self.last_status_ms = 0

        self.pair_code = ""
        self.pair_view = "code"
        self.pair_message_until = 0
        self.pending_pair_code = ""

        self.connection_screen = ConnectionScreen()
        self.pairing_screen = PairingScreen()
        self.function_screen = FunctionScreen()

        self.pair_sock = None
        self.status_sock = None
        self.pending_pairing = False
        self.pair_proto = PairProtocol(self)
        self.status_proto = StatusProtocol(self)

        print("[BOOT] codex buddy started")
        print("[BOOT]", wifi_status_text())
        print("[BOOT] device_id=%s paired=%s" % (self.device_id, self.paired))

        pyxel.init()
        load_assets()
        self.init_sockets()
        self.init_touch()

    @property
    def paired(self):
        return bool(self.pairing.get("paired") and self.pairing.get("token"))

    @property
    def connected(self):
        return bool(self.last_status_ms and ticks_diff(now_ms(), self.last_status_ms) <= self.status_timeout_ms)

    def init_sockets(self):
        try:
            self.pair_sock = make_udp_socket(PAIR_PORT)
            print("[BOOT] pair udp listening on %d" % PAIR_PORT)
        except Exception as exc:
            print("[BOOT] pair udp failed:", exc)
        try:
            self.status_sock = make_udp_socket(STATUS_PORT)
            print("[BOOT] status udp listening on %d" % STATUS_PORT)
        except Exception as exc:
            print("[BOOT] status udp failed:", exc)

    def init_touch(self):
        try:
            touch_events.clear()
            print("[BOOT] mpy_button ready")
        except Exception as exc:
            print("[BOOT] mpy_button unavailable:", exc)

    def enter_connection(self):
        self.mode = APP_CONNECTION

    def enter_pairing(self):
        self.mode = APP_PAIRING
        self.status_proto.reset()
        self.pair_proto.begin()

    def enter_function(self):
        self.mode = APP_FUNCTION

    def on_click(self):
        if self.mode == APP_FUNCTION:
            if self.host_state == "done":
                self.set_host_state("idle")
                return
            self.function_screen.next_page()


    def update_touch(self):
        while True:
            event = touch_events.get()
            if event is None:
                break
            if event == "click":
                self.on_click()
            elif event == "double":
                self.pending_pairing = True

    def enter_pending_pairing(self):
        if not self.pending_pairing:
            return
        self.pending_pairing = False
        self.enter_pairing()

    def show_pair_code(self, code):
        self.pair_code = code
        self.pair_view = "code"
        self.pair_message_until = 0
        self.pending_pair_code = ""

    def defer_pair_code(self, code):
        self.pending_pair_code = code
        self.pair_message_until = ticks_add(now_ms(), 900)

    def show_pair_verifying(self):
        self.pair_view = "verifying"
        self.pair_message_until = 0

    def show_pair_error(self):
        self.pair_view = "error"
        self.pair_message_until = ticks_add(now_ms(), 900)

    def show_pair_timeout(self):
        self.pair_view = "timeout"
        self.pair_message_until = ticks_add(now_ms(), 1200)

    def on_pair_success(self):
        self.pair_view = "ok"
        self.pair_message_until = ticks_add(now_ms(), 700)
        self.set_host_state("idle")
        self.status_proto.reset()
        self.last_status_ms = 0

    def can_set_host_state(self, state, event=""):
        state_key = str(state or "").lower()
        event_key = str(event or "").lower()
        if self.host_state == "done":
            return state_key == "done" or event_key == "userpromptsubmit"
        if self.host_state != "permission" or state_key == "permission":
            return True
        if ticks_diff(now_ms(), self.permission_until_ms) < 0:
            return False
        return event_key in ("pretooluse", "posttooluse", "stop", "userpromptsubmit", "sessionstart")

    def set_host_state(self, state):
        self.host_state = state
        if state == "permission":
            self.permission_until_ms = ticks_add(now_ms(), self.permission_min_display_ms)
        else:
            self.permission_until_ms = 0

    def mark_connected(self):
        self.last_status_ms = now_ms()
        if self.mode != APP_PAIRING:
            self.enter_function()


    def mark_disconnected(self):
        self.last_status_ms = 0
        self.set_host_state("idle")
        self.usage = {}
        self.status_proto.reset()
        if self.mode != APP_PAIRING:
            self.enter_connection()

    def finish_pair_message_if_ready(self):
        if not self.pair_message_until or ticks_diff(now_ms(), self.pair_message_until) < 0:
            return
        self.pair_message_until = 0
        if self.pair_view == "error" and self.pending_pair_code:
            self.show_pair_code(self.pending_pair_code)
        elif self.pair_view == "ok":
            if self.connected:
                self.enter_function()
            else:
                self.enter_connection()
        elif self.pair_view == "timeout":
            self.enter_connection()

    def check_liveness(self):
        if self.pair_proto.expired():
            self.pair_proto.cancel(timeout=True)
        if self.mode == APP_PAIRING:
            return
        if not self.paired:
            self.enter_connection()
        elif self.connected:
            self.enter_function()
        else:
            self.enter_connection()

    def update(self, rt):
        self.frame += 1
        self.update_touch()
        self.pair_proto.poll()
        self.status_proto.poll()
        self.enter_pending_pairing()
        self.finish_pair_message_if_ready()
        self.check_liveness()

    def draw(self, rt):
        if self.mode == APP_PAIRING:
            self.pairing_screen.draw(self)
        elif self.mode == APP_FUNCTION:
            self.function_screen.draw(self)
        else:
            self.connection_screen.draw(self)

    def on_exit(self, rt, reason, exc):
        try:
            if self.pair_sock is not None:
                self.pair_sock.close()
            if self.status_sock is not None:
                self.status_sock.close()
        except Exception:
            pass
        try:
            pyxel.destroy()
        except Exception:
            pass

    def run(self):
        pyxel.run(self.update, self.draw, fps=FPS, on_exit=self.on_exit)


def appMain():
    CodexBuddyApp().run()
