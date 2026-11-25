# PixelMug Codex Buddy for macOS

This directory contains the macOS companion for PixelMug Codex Buddy. It installs the Codex hook, runs the menu-bar bridge, and connects Codex status to PixelMug.

## Build the macOS package

Run these commands on macOS:

```bash
cd pixelmug-codex-macos
xcode-select --install   # If Command Line Tools are not installed
./packaging/build_macos.sh
```

The package is written to:

```text
release/PixelMugCodex-<version>.pkg
```

Install it with:

```bash
sudo installer -pkg "release/PixelMugCodex-<version>.pkg" -target /
```

The package installs:

```text
/usr/local/bin/pixelmug-codex
/Applications/PixelMug Codex.app
```

After installation, the post-install step registers the user-level Codex hook and LaunchAgent, then opens the menu-bar app.

## First-time pairing

1. Make sure PixelMug is not connected to another desktop buddy.
2. On PixelMug, double-click the bottom area to enter pairing mode.
3. PixelMug displays a pairing code.
4. Open the PixelMug menu-bar menu and select **Pair PixelMug**.
5. Enter the code shown on PixelMug.
6. The bridge saves the pairing and connects to the device.

## Reconnect a paired PixelMug

If a paired PixelMug becomes disconnected, select **Connect** from the menu-bar menu. Pairing is not required again.

The menu-bar menu includes:

```text
Pair PixelMug
Connect
Disconnect
Send Test Status
Open Logs
Start on Login
Quit
```

## Test without a PixelMug

Use the UDP simulator in one terminal:

```bash
python tools/pixelmug_udp_simulator.py
```

Press Enter to enter simulated pairing mode. In another terminal, start the bridge:

```bash
pixelmug-codex bridge
```

Select **Pair PixelMug** in the menu-bar app and enter the code printed by the simulator.

To simulate a Codex hook event:

```bash
printf '%s' '{"event":"PreToolUse","tool_name":"Bash","tool_input":{"command":"idf.py build"}}' | pixelmug-codex hook
```

## Uninstall

Remove the application, hooks, and LaunchAgent with:

```bash
./packaging/uninstall_macos.sh
```

To also remove the PixelMug configuration and logs:

```bash
./packaging/uninstall_macos.sh --delete-config --delete-logs
```

## Release signing and notarization

For external distribution, configure your Apple Developer ID certificates before building:

```bash
export DEVELOPER_ID_APPLICATION="Developer ID Application: Your Company (TEAMID)"
export DEVELOPER_ID_INSTALLER="Developer ID Installer: Your Company (TEAMID)"
./packaging/build_macos.sh
```

Submit and staple the package with:

```bash
xcrun notarytool submit "release/PixelMugCodex-<version>.pkg" \
  --keychain-profile "<your-notary-profile>" \
  --wait

xcrun stapler staple "release/PixelMugCodex-<version>.pkg"
spctl -a -vv -t install "release/PixelMugCodex-<version>.pkg"
```
