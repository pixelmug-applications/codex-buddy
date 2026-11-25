# PixelMug Codex Buddy for macOS

PixelMug Codex Buddy connects Codex on macOS to a PixelMug display. The buddy runs in the macOS menu bar and forwards Codex status to the PixelMug app.

## Install

Install the macOS package, open **PixelMug Codex**, and keep it running in the menu bar. After installing the Codex hook, open Codex and run:

```text
/hooks
```

Trust the PixelMug Codex Buddy hook when Codex asks.

## First-time pairing

Pair the PixelMug once before connecting it:

1. Make sure PixelMug is not connected to another desktop buddy.
2. On PixelMug, double-click the bottom area to enter pairing mode.
3. PixelMug displays a pairing code.
4. Open the PixelMug Codex menu-bar menu and select **Pair PixelMug**.
5. Enter the code shown on PixelMug.
6. The buddy saves the pairing and connects to the device.

Once connected, Codex status appears on PixelMug.

## Reconnect a paired PixelMug

If a paired PixelMug becomes disconnected, open the menu-bar menu and select **Connect**. You do not need to pair it again.

## Disconnect or exit

- Select **Disconnect** to end the current connection while keeping the pairing.
- Select **Quit** to close the desktop buddy.
- Start the buddy again and select **Connect** to reconnect a previously paired device.

## Menu-bar menu

```text
Status: Connected / Disconnected / Pairing
Pair PixelMug
Connect
Disconnect
Send Test Status
Open Logs
Start on Login
Quit
```

## Build from source

Build the macOS package on macOS:

```bash
xcode-select --install   # If Command Line Tools are not installed
./packaging/build_macos.sh
```

The package is written to `release/PixelMugCodex-<version>.pkg`, using `[project].version` from `pyproject.toml`.

To install it locally:

```bash
sudo installer -pkg "release/PixelMugCodex-<version>.pkg" -target /
```

To uninstall the buddy:

```bash
./packaging/uninstall_macos.sh
```

To also remove its configuration and logs:

```bash
./packaging/uninstall_macos.sh --delete-config --delete-logs
```
