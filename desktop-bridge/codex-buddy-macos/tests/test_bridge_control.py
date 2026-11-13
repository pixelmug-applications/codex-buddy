from src.bridge import BridgeCore
from src.config import BridgeConfig
from src.constants import CONTROL_MSG_TYPE
from src.protocol import make_control_message


class DummyStore:
    def __init__(self) -> None:
        self.config = BridgeConfig()

    def load(self) -> BridgeConfig:
        return self.config

    def save(self, config: BridgeConfig) -> None:
        self.config = config


def test_make_control_message():
    msg = make_control_message("pair")

    assert msg["type"] == CONTROL_MSG_TYPE
    assert msg["cmd"] == "pair"
    assert "ts" in msg


def test_control_pair_can_be_handled_by_ui_callback():
    handled = []
    bridge = BridgeCore(store=DummyStore(), control_callback=lambda msg: handled.append(msg["cmd"]) or True)

    bridge.handle_control_message(make_control_message("pair"))

    assert handled == ["pair"]
    assert bridge.state.last_error == ""


def test_control_connect_uses_running_bridge():
    calls = []
    bridge = BridgeCore(store=DummyStore())
    bridge._threaded = lambda target, *args, **kwargs: calls.append((target, args, kwargs))  # type: ignore[method-assign]

    bridge.handle_control_message(make_control_message("connect"))

    assert calls == [(bridge.connect, (True,), {})]
