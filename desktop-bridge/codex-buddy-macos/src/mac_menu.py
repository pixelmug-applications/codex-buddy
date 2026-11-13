"""macOS menu bar UI for the bridge."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from importlib import resources
from queue import Empty, Queue
from pathlib import Path

from .bridge import BridgeCore, PairingError
from .config import ConfigStore
from .installer import install_user_files
from .launch_agent import create_launch_agent, load_launch_agent, remove_launch_agent
from .logger import get_logger
from .paths import log_dir, log_file


def status_icon_path() -> Path | None:
    candidates: list[Path] = []

    def add_assets_dir(path: Path) -> None:
        candidates.append(path / "status-icon@2x.png")
        candidates.append(path / "status-icon.png")

    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        add_assets_dir(bundle_root / "assets")
        executable_dir = Path(sys.executable).resolve().parent
        add_assets_dir(executable_dir / "assets")
        add_assets_dir(executable_dir.parent / "Resources" / "assets")
        add_assets_dir(executable_dir.parent / "Frameworks" / "assets")
        add_assets_dir(executable_dir.parent.parent / "Resources" / "assets")
        for assets_dir in executable_dir.parent.glob("*/assets"):
            add_assets_dir(assets_dir)
    try:
        resource_root = resources.files("src")
        for name in ("status-icon@2x.png", "status-icon.png"):
            resource_path = resource_root.joinpath("assets", name)
            if resource_path.is_file():
                with resources.as_file(resource_path) as path:
                    return path
    except Exception:
        pass

    add_assets_dir(Path(sys.prefix) / "share" / "pixelmug-codex" / "assets")
    source_assets = Path(__file__).resolve().parents[1] / "assets"
    add_assets_dir(source_assets)

    for path in dict.fromkeys(candidates):
        if path.is_file():
            return path
    return None


def default_cli_bin_path() -> str:
    candidates = [
        shutil.which("pixelmug-codex"),
        "/usr/local/bin/pixelmug-codex",
        "/opt/homebrew/bin/pixelmug-codex",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(sys.argv[0]).resolve())


def run_menu_bar_app() -> int:
    try:
        import rumps  # type: ignore
    except Exception as exc:
        print("rumps is required for the macOS menu bar UI.", file=sys.stderr)
        print("Install with: python3 -m pip install rumps pyobjc-framework-Cocoa", file=sys.stderr)
        print(f"Import error: {exc}", file=sys.stderr)
        bridge = BridgeCore()
        bridge.run_forever()
        return 0

    class PixelMugCodexApp(rumps.App):  # type: ignore[misc]
        def __init__(self) -> None:
            icon = status_icon_path()
            self.log = get_logger("mac_menu")
            self.status_icon = str(icon) if icon else ""
            self.status_icon_applied = False
            if icon:
                try:
                    super().__init__("PixelMug Codex", title=None, icon=str(icon), template=False, quit_button=None)
                except TypeError:
                    super().__init__("PixelMug Codex", title=None, icon=str(icon), quit_button=None)
            else:
                super().__init__("PM", quit_button=None)
            self.store = ConfigStore()
            self.bridge = BridgeCore(
                self.store,
                status_callback=self._bridge_status_changed,
                control_callback=self._handle_control_message,
            )
            self.latest_status = "disconnected"
            self.busy = False
            self.ui_queue = Queue()
            self.pairing_status = ""
            self.rebuild_menu()
            self.bridge.start(auto_connect=True)
            self.refresh_timer = rumps.Timer(self._timer_refresh, 0.25)
            self.refresh_timer.start()

        def _bridge_status_changed(self, text: str) -> None:
            self.latest_status = self._connection_status_label()

        def _handle_control_message(self, msg: dict) -> bool:
            cmd = str(msg.get("cmd") or "")
            if cmd == "pair":
                self.on_pair()
                return True
            if cmd == "open_logs":
                self.on_open_logs()
                return True
            return False

        def _timer_refresh(self, _sender=None) -> None:
            if not self.status_icon_applied:
                self._apply_status_icon()
            self._process_ui_queue()
            self.rebuild_menu()

        def _apply_status_icon(self) -> None:
            if not self.status_icon:
                self.status_icon_applied = True
                self.log.info("status icon unavailable; using text fallback")
                return
            try:
                from AppKit import NSImage, NSMakeSize

                image = NSImage.alloc().initByReferencingFile_(self.status_icon)
                if not image:
                    self.log.warning("status icon failed to load path=%s", self.status_icon)
                    self.status_icon_applied = True
                    return
                image.setScalesWhenResized_(True)
                image.setSize_(NSMakeSize(20, 20))
                image.setTemplate_(False)

                item = getattr(getattr(self, "_nsapp", None), "nsstatusitem", None)
                if item is None:
                    return
                item.setTitle_("")
                item.setImage_(image)
                self.status_icon_applied = True
                self.log.info("status icon applied path=%s", self.status_icon)
            except Exception as exc:
                self.status_icon_applied = True
                self.log.warning("status icon apply failed path=%s error=%s", self.status_icon, exc)

        def _process_ui_queue(self) -> None:
            while True:
                try:
                    item = self.ui_queue.get_nowait()
                except Empty:
                    return
                try:
                    kind = item[0]
                    if kind == "alert":
                        _kind, message = item
                        rumps.alert(title="PixelMug Codex", message=message)
                    elif kind == "notification":
                        _kind, title, subtitle, message = item
                        rumps.notification(title, subtitle, message)
                    elif kind == "pair_code":
                        _kind, info, done, result = item
                        self._handle_pair_code_request(info, done, result)
                except Exception as exc:
                    self.log.warning("ui queue item failed kind=%s error=%s", item[0] if item else "unknown", exc)

        def _handle_pair_code_request(self, info, done, result) -> None:
            try:
                self.pairing_status = "enter_code"
                self.rebuild_menu()
                ttl = info.get("ttl", 60)
                result["code"] = self._prompt_pair_code(ttl)
            except Exception as exc:
                result["error"] = exc
            finally:
                done.set()

        def _prompt_pair_code(self, ttl: int) -> str:
            from AppKit import (
                NSAlert,
                NSApplication,
                NSApplicationActivateIgnoringOtherApps,
                NSApplicationActivationPolicyAccessory,
                NSApplicationActivationPolicyRegular,
                NSMakeRect,
                NSRunningApplication,
                NSTextField,
            )

            app = NSApplication.sharedApplication()
            previous_policy = app.activationPolicy()
            app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
            app.activateIgnoringOtherApps_(True)
            NSRunningApplication.currentApplication().activateWithOptions_(NSApplicationActivateIgnoringOtherApps)

            text_field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 240, 24))
            text_field.setStringValue_("")
            text_field.setEditable_(True)
            text_field.setSelectable_(True)

            alert = NSAlert.alloc().init()
            alert.setMessageText_("PixelMug Pairing")
            alert.setInformativeText_(f"PixelMug has shown a 6-digit code. Enter it within {ttl}s.")
            alert.addButtonWithTitle_("Pair")
            alert.addButtonWithTitle_("Cancel")
            alert.setAccessoryView_(text_field)
            alert.layout()

            alert_window = alert.window()
            alert_window.setInitialFirstResponder_(text_field)
            alert_window.makeFirstResponder_(text_field)
            alert_window.makeKeyAndOrderFront_(None)
            text_field.selectText_(None)

            try:
                clicked = alert.runModal()
            finally:
                if previous_policy is not None:
                    app.setActivationPolicy_(previous_policy)
                else:
                    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

            if clicked != 1000:
                raise PairingError("Pairing canceled by user.")
            return str(text_field.stringValue())

        def _connection_status_label(self) -> str:
            if self.bridge.state.connection == "Connected":
                return "connected"
            return "disconnected"

        def _status_menu_item(self):
            label = self.pairing_status or self._connection_status_label()
            item = rumps.MenuItem(f"Status: {label}", callback=None)
            try:
                from AppKit import NSColor, NSForegroundColorAttributeName
                from Foundation import NSAttributedString

                color = NSColor.systemGreenColor() if label == "connected" else NSColor.systemGrayColor()
                attributed = NSAttributedString.alloc().initWithString_attributes_(
                    f"Status: {label}",
                    {NSForegroundColorAttributeName: color},
                )
                item._menuitem.setAttributedTitle_(attributed)
            except Exception:
                pass
            return item

        def _pair_menu_item(self):
            if self.pairing_status == "discovering":
                return rumps.MenuItem("Discovering PixelMug...", callback=None)
            if self.pairing_status == "enter_code":
                return rumps.MenuItem("Enter Pairing Code...", callback=None)
            if self.pairing_status == "confirming":
                return rumps.MenuItem("Confirming Pairing...", callback=None)
            return rumps.MenuItem("Pair PixelMug", callback=self.on_pair)

        def rebuild_menu(self) -> None:
            cfg = self.bridge.config
            start = "On" if cfg.start_on_login else "Off"
            self.menu.clear()
            self.menu.add(rumps.MenuItem("PixelMug Codex", callback=None))
            self.menu.add(self._status_menu_item())
            self.menu.add(None)
            self.menu.add(self._pair_menu_item())
            self.menu.add(rumps.MenuItem("Connect", callback=self.on_connect))
            self.menu.add(rumps.MenuItem("Disconnect", callback=self.on_disconnect))
            self.menu.add(rumps.MenuItem("Send Test Status", callback=self.on_send_test))
            self.menu.add(None)
            self.menu.add(rumps.MenuItem("Open Logs", callback=self.on_open_logs))
            self.menu.add(rumps.MenuItem(f"Start on Login: {start}", callback=self.on_toggle_start_login))
            self.menu.add(None)
            self.menu.add(rumps.MenuItem("Quit", callback=self.on_quit))

        def _run_background(self, func, success_title: str = "PixelMug Codex") -> None:
            if self.busy:
                rumps.notification("PixelMug Codex", "Busy", "An operation is already running.")
                return
            self.busy = True

            def worker() -> None:
                try:
                    result = func()
                    if result:
                        self.ui_queue.put(("notification", success_title, "Done", str(result)))
                except Exception as exc:
                    self.log.exception("background operation failed")
                    self.bridge.state.last_error = str(exc)
                    self.latest_status = self._connection_status_label()
                    self.ui_queue.put(("alert", str(exc)))
                finally:
                    self.busy = False

            threading.Thread(target=worker, daemon=True).start()

        def on_pair(self, _sender=None) -> None:
            def code_provider(info):
                done = threading.Event()
                result = {}
                self.ui_queue.put(("pair_code", info, done, result))
                done.wait()
                if "error" in result:
                    raise result["error"]
                self.pairing_status = "confirming"
                return str(result.get("code", ""))

            def pair_operation() -> str:
                self.pairing_status = "discovering"
                try:
                    return f"Paired {self.bridge.pair(code_provider).device_id}"
                finally:
                    self.pairing_status = ""

            self._run_background(pair_operation)

        def on_connect(self, _sender=None) -> None:
            self._run_background(lambda: "Connected" if self.bridge.connect(use_discover=True) else "No paired PixelMug")

        def on_disconnect(self, _sender=None) -> None:
            self.bridge.disconnect()
            self.latest_status = self._connection_status_label()
            self.rebuild_menu()

        def on_send_test(self, _sender=None) -> None:
            self._run_background(lambda: "Sent" if self.bridge.send_test_status() else "Not connected")

        def on_open_logs(self, _sender=None) -> None:
            log_dir().mkdir(parents=True, exist_ok=True)
            log_file().touch(exist_ok=True)
            subprocess.run(["open", str(log_dir())], check=False)

        def on_toggle_start_login(self, _sender=None) -> None:
            cfg = self.bridge.config
            cfg.start_on_login = not cfg.start_on_login
            self.store.save(cfg)
            bin_path = default_cli_bin_path()
            if cfg.start_on_login:
                create_launch_agent(bin_path, enabled=True)
                load_launch_agent()
            else:
                remove_launch_agent()
            self.latest_status = self._connection_status_label()
            self.rebuild_menu()

        def on_quit(self, _sender=None) -> None:
            self.bridge.stop()
            rumps.quit_application()

    PixelMugCodexApp().run()
    return 0


def ensure_user_install_and_run() -> int:
    # Useful when the .app is launched directly before postinstall has run.
    install_user_files(default_cli_bin_path(), start_on_login=True, start_now=False)
    return run_menu_bar_app()
