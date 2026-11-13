"""Configuration persistence for the macOS bridge."""
from __future__ import annotations

import json
import secrets
import socket
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

from .constants import PIXELMUG_PAIR_PORT, PIXELMUG_STATUS_PORT
from .paths import chmod_user_readable, config_file, ensure_user_dirs


def _default_bridge_id() -> str:
    hostname = socket.gethostname().split(".", 1)[0] or "mac"
    return f"host-{hostname}-{secrets.token_hex(3)}"


@dataclass
class PairedDevice:
    device_id: str
    device_name: str = "PixelMug"
    last_host: str = ""
    status_port: int = PIXELMUG_STATUS_PORT
    pair_port: int = PIXELMUG_PAIR_PORT
    token: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PairedDevice":
        return cls(
            device_id=str(data.get("device_id", "")),
            device_name=str(data.get("device_name", "PixelMug")),
            last_host=str(data.get("last_host", data.get("host", ""))),
            status_port=int(data.get("status_port", PIXELMUG_STATUS_PORT)),
            pair_port=int(data.get("pair_port", PIXELMUG_PAIR_PORT)),
            token=str(data.get("token", "")),
        )


@dataclass
class BridgeConfig:
    bridge_id: str = field(default_factory=_default_bridge_id)
    paired_devices: list[PairedDevice] = field(default_factory=list)
    active_device_id: str | None = None
    start_on_login: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BridgeConfig":
        devices = [PairedDevice.from_dict(d) for d in data.get("paired_devices", []) if isinstance(d, dict)]
        devices = [d for d in devices if d.device_id]
        return cls(
            bridge_id=str(data.get("bridge_id") or _default_bridge_id()),
            paired_devices=devices,
            active_device_id=data.get("active_device_id"),
            start_on_login=bool(data.get("start_on_login", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def active_device(self) -> PairedDevice | None:
        if not self.active_device_id:
            return self.paired_devices[0] if self.paired_devices else None
        for device in self.paired_devices:
            if device.device_id == self.active_device_id:
                return device
        return None

    def upsert_device(self, device: PairedDevice) -> None:
        for idx, existing in enumerate(self.paired_devices):
            if existing.device_id == device.device_id:
                self.paired_devices[idx] = device
                break
        else:
            self.paired_devices.append(device)
        self.active_device_id = device.device_id


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_file()

    def load(self) -> BridgeConfig:
        ensure_user_dirs()
        if not self.path.exists():
            cfg = BridgeConfig()
            self.save(cfg)
            return cfg
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("config root is not object")
            return BridgeConfig.from_dict(data)
        except Exception:
            # Preserve the bad file for manual inspection and start with a safe config.
            backup = self.path.with_suffix(".json.bad")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            cfg = BridgeConfig()
            self.save(cfg)
            return cfg

    def save(self, config: BridgeConfig) -> None:
        ensure_user_dirs()
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp.replace(self.path)
        chmod_user_readable(self.path)
