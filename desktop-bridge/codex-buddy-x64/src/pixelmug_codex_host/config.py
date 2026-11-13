from __future__ import annotations

import json
import os
import socket
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .constants import PAIR_PORT, STATUS_PORT
from .paths import config_path, ensure_dirs


@dataclass
class PairedDevice:
    device_id: str
    device_name: str = "PixelMug"
    last_host: str = ""
    status_port: int = STATUS_PORT
    pair_port: int = PAIR_PORT
    token: str = ""


@dataclass
class AppConfig:
    bridge_id: str = ""
    paired_devices: list[PairedDevice] = field(default_factory=list)
    active_device_id: str = ""
    start_on_login: bool = True

    def active_device(self) -> PairedDevice | None:
        if not self.active_device_id and self.paired_devices:
            self.active_device_id = self.paired_devices[0].device_id
        for device in self.paired_devices:
            if device.device_id == self.active_device_id:
                return device
        return None

    def upsert_device(self, device: PairedDevice) -> None:
        for idx, existing in enumerate(self.paired_devices):
            if existing.device_id == device.device_id:
                self.paired_devices[idx] = device
                self.active_device_id = device.device_id
                return
        self.paired_devices.append(device)
        self.active_device_id = device.device_id


def default_bridge_id() -> str:
    host = socket.gethostname().replace(" ", "-")[:24]
    return f"{host}-{uuid.uuid4().hex[:6]}"


def load_config() -> AppConfig:
    ensure_dirs()
    path = config_path()
    if not path.exists():
        cfg = AppConfig(bridge_id=default_bridge_id())
        save_config(cfg)
        return cfg

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        cfg = AppConfig(bridge_id=default_bridge_id())
        save_config(cfg)
        return cfg

    devices = [PairedDevice(**d) for d in raw.get("paired_devices", []) if isinstance(d, dict)]
    cfg = AppConfig(
        bridge_id=raw.get("bridge_id") or default_bridge_id(),
        paired_devices=devices,
        active_device_id=raw.get("active_device_id", ""),
        start_on_login=bool(raw.get("start_on_login", True)),
    )
    return cfg


def save_config(cfg: AppConfig) -> None:
    ensure_dirs()
    data: dict[str, Any] = asdict(cfg)
    tmp = config_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, config_path())
