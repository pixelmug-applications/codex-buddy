from __future__ import annotations

import sys
import threading
from importlib import resources
from pathlib import Path
from typing import Any

from .bridge import BridgeService
from .constants import APP_NAME


def status_icon_path() -> Path | None:
    candidates: list[Path] = []

    def add_assets_dir(path: Path) -> None:
        candidates.append(path / "status-icon@2x.png")
        candidates.append(path / "status-icon.png")

    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        add_assets_dir(bundle_root / "assets")
        add_assets_dir(Path(sys.executable).resolve().parent / "assets")
    source_assets = Path(__file__).resolve().parents[2] / "assets"
    add_assets_dir(source_assets)
    for path in dict.fromkeys(candidates):
        if path.is_file():
            return path
    return None


def _make_icon_image():
    from PIL import Image, ImageDraw

    icon_path = status_icon_path()
    if icon_path:
        try:
            return Image.open(icon_path).convert("RGBA")
        except Exception:
            pass
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((6, 10, 58, 54), radius=10, fill=(30, 40, 80, 255), outline=(100, 180, 255, 255), width=3)
    for x in range(18, 48, 10):
        draw.rectangle((x, 24, x + 5, 29), fill=(120, 220, 255, 255))
    draw.rectangle((22, 40, 42, 44), fill=(120, 255, 160, 255))
    return img


class BridgeTray:
    def __init__(self, service: BridgeService) -> None:
        import pystray

        self.service = service
        self.pystray = pystray
        self.icon = pystray.Icon(APP_NAME, _make_icon_image(), APP_NAME)
        self.service.on_status_change = self._on_status_change
        self.icon.menu = self._build_menu()

    def _on_status_change(self, _status: str) -> None:
        self.icon.title = f"{APP_NAME}: {self._connection_status_label()}"
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _connection_status_label(self) -> str:
        return "● connected" if self.service.connected else "○ disconnected"

    def _run_threaded(self, func, *args: Any) -> None:
        threading.Thread(target=func, args=args, daemon=True).start()

    def _start_on_login_label(self) -> str:
        return "On" if self.service.start_on_login_enabled() else "Off"

    def _build_menu(self):
        pystray = self.pystray
        return pystray.Menu(
            pystray.MenuItem("PixelMug Codex", None, enabled=False),
            pystray.MenuItem(lambda item: f"Status: {self._connection_status_label()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Pair PixelMug", lambda icon, item: self._run_threaded(self.service.pair_device)),
            pystray.MenuItem("Connect", lambda icon, item: self._run_threaded(self.service.connect_saved_device, True)),
            pystray.MenuItem("Disconnect", lambda icon, item: self.service.disconnect()),
            pystray.MenuItem("Send Test Status", lambda icon, item: self._run_threaded(self.service.send_test_status)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Logs", lambda icon, item: self.service.open_logs()),
            pystray.MenuItem(
                lambda item: f"Start on Login: {self._start_on_login_label()}",
                lambda icon, item: self.service.set_start_on_login(not self.service.start_on_login_enabled()),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit),
        )

    def run(self) -> int:
        self.service.start(auto_connect=True)
        self.icon.run()
        return 0

    def quit(self, icon=None, item=None) -> None:
        self.service.stop()
        self.icon.stop()


def run_tray(service: BridgeService) -> int:
    return BridgeTray(service).run()
