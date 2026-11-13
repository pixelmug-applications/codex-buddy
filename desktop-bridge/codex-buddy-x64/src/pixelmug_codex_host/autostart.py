from __future__ import annotations

import sys

from .constants import RUN_REG_NAME


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("Windows autostart is only supported on Windows")


def set_autostart(enabled: bool, bridge_exe: str | None = None) -> None:
    _require_windows()
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            if not bridge_exe:
                raise ValueError("bridge_exe is required when enabling autostart")
            cmd = f'"{bridge_exe}"'
            winreg.SetValueEx(key, RUN_REG_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, RUN_REG_NAME)
            except FileNotFoundError:
                pass


def get_autostart() -> str | None:
    _require_windows()
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, RUN_REG_NAME)
            return str(value)
    except FileNotFoundError:
        return None
