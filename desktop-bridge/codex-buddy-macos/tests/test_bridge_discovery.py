import socket

from src import bridge as bridge_module
from src.bridge import BridgeCore
from src.config import BridgeConfig, PairedDevice
from src.constants import BROADCAST_ADDR, PIXELMUG_PAIR_PORT


class DummyStore:
    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.saved: list[BridgeConfig] = []

    def load(self) -> BridgeConfig:
        return self.config

    def save(self, config: BridgeConfig) -> None:
        self.saved.append(config)


def make_bridge(device: PairedDevice) -> BridgeCore:
    config = BridgeConfig(paired_devices=[device], active_device_id=device.device_id)
    return BridgeCore(store=DummyStore(config))


def test_connection_check_uses_longer_timeout_and_five_misses():
    device = PairedDevice(device_id="mug-1", last_host="192.168.1.8", pair_port=40123, token="token")
    bridge = make_bridge(device)
    bridge.state.connection = "Connected"
    calls = []

    def fake_discover(**kwargs):
        calls.append(kwargs)
        return []

    bridge.discover = fake_discover  # type: ignore[method-assign]

    for _ in range(4):
        assert bridge._verify_connected_device()
        assert bridge.state.connection != "Disconnected"

    assert not bridge._verify_connected_device()
    assert bridge.state.connection == "Disconnected"
    assert bridge._connection_check_misses == 5
    assert calls[0]["timeout"] == 2.0
    assert calls[0]["preferred_host"] == "192.168.1.8"
    assert calls[0]["preferred_port"] == 40123


def test_connect_prefers_saved_host_during_discover():
    device = PairedDevice(device_id="mug-1", last_host="192.168.1.8", pair_port=40123, token="token")
    bridge = make_bridge(device)
    calls = []

    def fake_discover(**kwargs):
        calls.append(kwargs)
        return [
            {
                "device_id": "mug-1",
                "host": "192.168.1.9",
                "status_port": 39217,
                "pair_port": 40124,
            }
        ]

    bridge.discover = fake_discover  # type: ignore[method-assign]
    bridge.send_test_status = lambda **_kwargs: True  # type: ignore[method-assign]
    bridge._auth_check_device = lambda *_args, **_kwargs: True  # type: ignore[method-assign]

    assert bridge.connect(use_discover=True)
    assert calls[0]["preferred_host"] == "192.168.1.8"
    assert calls[0]["preferred_port"] == 40123
    assert device.last_host == "192.168.1.9"
    assert device.pair_port == 40124


def test_connect_requires_auth_check_after_discover():
    device = PairedDevice(device_id="mug-1", last_host="192.168.1.8", pair_port=40123, token="token")
    bridge = make_bridge(device)
    auth_calls = []

    bridge.discover = lambda **_kwargs: [  # type: ignore[method-assign]
        {
            "device_id": "mug-1",
            "host": "192.168.1.9",
            "status_port": 39217,
            "pair_port": 40124,
        }
    ]
    def fake_auth_check(auth_device, **_kwargs):
        auth_calls.append(auth_device)
        bridge.state.connection = "Disconnected"
        return False

    bridge._auth_check_device = fake_auth_check  # type: ignore[method-assign]

    assert not bridge.connect(use_discover=True)
    assert auth_calls == [device]
    assert bridge.state.connection == "Disconnected"


def test_auth_check_rejects_other_host_pairing():
    device = PairedDevice(device_id="mug-1", last_host="192.168.1.8", pair_port=40123, token="token")
    bridge = make_bridge(device)

    bridge._send_pair_request_wait = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
        "cmd": "pair_error",
        "ok": False,
        "error": "bridge_mismatch",
    }

    assert not bridge._auth_check_device(device)
    assert bridge.state.connection == "Disconnected"
    assert bridge.state.last_error == "PixelMug is paired with another host. Pair again to use this host."


def test_send_status_disconnects_on_send_error(monkeypatch):
    device = PairedDevice(
        device_id="mug-1",
        last_host="192.168.1.8",
        status_port=39217,
        pair_port=40123,
        token="token",
    )
    bridge = make_bridge(device)
    bridge.state.connection = "Connected"

    class FailingSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def sendto(self, _data, _addr):
            raise OSError("temporary send failure")

    monkeypatch.setattr(bridge_module.socket, "socket", lambda *_args: FailingSocket())

    sent = bridge.send_status(
        {
            "state": "idle",
            "event": "SendTestStatus",
            "tool": "",
            "repo": "macOS",
            "text": "paired",
            "ts": 1,
        }
    )

    assert not sent
    assert bridge.state.connection == "Disconnected"
    assert bridge.state.last_error == "temporary send failure"


def test_discover_sends_to_preferred_host_before_broadcast(monkeypatch):
    sends = []

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def setsockopt(self, *_args):
            pass

        def settimeout(self, _timeout):
            pass

        def sendto(self, _data, addr):
            sends.append(addr)

        def recvfrom(self, _size):
            raise socket.timeout()

    times = iter([0.0, 0.1, 1.1])

    monkeypatch.setattr(bridge_module.socket, "socket", lambda *_args: FakeSocket())
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: next(times))

    bridge = make_bridge(PairedDevice(device_id="mug-1", token="token"))
    assert bridge.discover(timeout=1.0, preferred_host="192.168.1.8", preferred_port=40123) == []

    assert sends[0] == ("192.168.1.8", 40123)
    assert sends[1] == (BROADCAST_ADDR, PIXELMUG_PAIR_PORT)
