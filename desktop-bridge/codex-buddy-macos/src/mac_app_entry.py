"""PyInstaller .app entrypoint."""
from __future__ import annotations

from .mac_menu import ensure_user_install_and_run

if __name__ == "__main__":
    raise SystemExit(ensure_user_install_and_run())
