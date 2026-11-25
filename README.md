# PixelMug Codex Buddy

PixelMug Codex Buddy connects Codex on a computer to a PixelMug display. This repository contains the PixelMug application and the desktop companion tools for macOS and Windows.

## Components

- **`bot/` and `mpy/`** contain the PixelMug Studio application. The Bot opens the device app, and the MicroPython app displays Codex status.
- **`desktop-bridge/codex-buddy-macos/`** — the macOS companion. It provides the Codex hook, menu-bar bridge, pairing flow, and `.pkg` packaging scripts.
- **`desktop-bridge/codex-buddy-x64/`** — the Windows x64 companion. It provides the Codex hook, system-tray bridge, CLI utilities, executable build, and installer scripts.

Both desktop companions use the same local UDP channels: `39216` for hook events, `39217` for runtime status, and `39218` for discovery and pairing. The desktop tools do not use BLE; the PixelMug app receives the paired status over the supported local protocol.

## PixelMug app

Open the repository root in PixelMug Studio to test or run the application. The bot uses the current PixelMug Bot SDK and reads its connection settings from environment variables such as `BOT_TOKEN`, `BOT_API_BASE_URL`, `STUDIO_MPS_ID`, and `STUDIO_MPS_VERSION`.

Install the Bot dependencies from the repository root:

```bash
npm ci
```

The Studio Bot deployment package excludes `desktop-bridge/` and local debug output.

## Desktop development

Each desktop directory has its own detailed platform README and build scripts. Use the macOS bridge on macOS and the x64 bridge on Windows. Generated virtual environments, caches, build output, installers, and logs are ignored by the root `.gitignore`.

This repository is the source tree for all three components. Build artifacts and machine-local configuration should not be committed.
