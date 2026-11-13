# PixelMug Codex Buddy for Windows

PixelMug Codex Buddy connects Codex on Windows to a PixelMug display. The desktop buddy runs in the Windows system tray and forwards Codex status to the PixelMug app.

## Install

Install the Windows package, start **PixelMug Codex Buddy**, and keep it running in the system tray. After installing the Codex hook, open Codex and run:

```text
/hooks
```

Trust the PixelMug Codex Buddy hook when Codex asks.

## First-time pairing

Pair the PixelMug once before connecting it:

1. Make sure PixelMug is not connected to a desktop buddy.
2. On PixelMug, double-click the bottom area to enter pairing mode.
3. PixelMug displays a pairing code.
4. Open the PixelMug Codex Buddy tray menu and select **Pair PixelMug**.
5. Enter the code shown on PixelMug.
6. The buddy saves the pairing and connects to the device.

Once connected, Codex status appears on PixelMug.

## Reconnect a paired PixelMug

If a paired PixelMug becomes disconnected, open the tray menu and select **Connect**. You do not need to pair it again.

## Disconnect or exit

- Select **Disconnect** to end the current connection while keeping the pairing.
- Select **Quit** to close the desktop buddy.
- Start the buddy again and select **Connect** to reconnect a previously paired device.

## Tray menu

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

From this directory, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build_exe.ps1
```

The executables are written to `dist\`. To build the Windows installer, install Inno Setup and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

The installer is written to `installer_out\`.
