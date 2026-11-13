"""PyInstaller entrypoint for the macOS app bundle."""
from __future__ import annotations

from src.mac_app_entry import ensure_user_install_and_run


if __name__ == "__main__":
    raise SystemExit(ensure_user_install_and_run())
