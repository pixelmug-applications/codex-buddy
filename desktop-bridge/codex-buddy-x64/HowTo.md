# PixelMug Codex Buddy Windows x64 How-To

This directory contains the Windows x64 companion for PixelMug Codex Buddy. It is designed to provide the same workflow as the macOS companion:

```text
Codex hook -> local Buddy bridge -> UDP -> PixelMug
```

## Components

The build produces three executables:

```text
dist\pixelmug-codex-hook.exe
dist\pixelmug-codex-cli.exe
dist\pixelmug-codex-buddy.exe
```

- `pixelmug-codex-hook.exe` is called by Codex lifecycle hooks. It reads JSON from stdin and quickly forwards the event to `127.0.0.1:39216` over UDP.
- `pixelmug-codex-buddy.exe` is the persistent Windows tray application. It handles pairing, connection, status forwarding, and tray actions.
- `pixelmug-codex-cli.exe` provides installer commands and manual diagnostic commands.

## Build the executables

Install Python 3.10 or later, then run the following commands in PowerShell:

```powershell
cd mps\codex-buddy\codex-buddy-x64
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build_exe.ps1
```

The executables are written to:

```text
dist\pixelmug-codex-hook.exe
dist\pixelmug-codex-cli.exe
dist\pixelmug-codex-buddy.exe
```

## Build the installer

The build script accepts `-Path` with either `ISCC.exe` for an automated build or `ISIDE.exe` for an IDE build.

### Automated build with ISCC.exe

If `ISCC.exe` is on `PATH`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

Otherwise, pass its full path:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Path "C:\Program Files\Inno Setup 7\ISCC.exe"
```

The installer is written to:

```text
installer_out\PixelMugCodexBuddySetup-<version>.exe
```

### Manual build with ISIDE.exe

The installer version comes from `[project].version` in `pyproject.toml`.

If only the Inno Setup IDE is available, pass `ISIDE.exe`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -Path "C:\Program Files\Inno Setup 7\ISIDE.exe"
```

The script opens the installer project in Inno Setup. Click **Build > Compile** in the IDE. The installer is still written to:

```text
installer_out\PixelMugCodexBuddySetup-<version>.exe
```

## Installer behavior

The installer:

1. Installs the three executables to `%LOCALAPPDATA%\Programs\PixelMugCodexBuddy`.
2. Adds or merges the Codex hooks in `%USERPROFILE%\.codex\hooks.json`.
3. Registers startup in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
4. Starts `pixelmug-codex-buddy.exe` with its tray icon.

After installation, run this command in Codex:

```text
/hooks
```

Then trust the PixelMug Codex Buddy hooks.

## Install hooks manually

To install hooks without the installer:

```powershell
.\dist\pixelmug-codex-cli.exe install-hooks --hook-exe "$PWD\dist\pixelmug-codex-hook.exe"
```

Enable startup manually:

```powershell
.\dist\pixelmug-codex-cli.exe autostart on --bridge-exe "$PWD\dist\pixelmug-codex-buddy.exe"
```

Start Buddy:

```powershell
.\dist\pixelmug-codex-buddy.exe
```

## Tray menu

The tray menu includes:

```text
PixelMug Codex
Status: connected / disconnected
Pair PixelMug
Connect
Disconnect
Send Test Status
Open Logs
Start on Login: On / Off
Quit
```

## Logs and configuration

Print the paths with:

```powershell
.\dist\pixelmug-codex-cli.exe paths
```

Typical locations are:

```text
%APPDATA%\PixelMugCodex\config.json
%LOCALAPPDATA%\PixelMugCodex\logs\bridge.log
%LOCALAPPDATA%\PixelMugCodex\logs\hook.log
```

If a restricted Windows environment prevents writing to these locations, the application falls back to:

```text
%TEMP%\PixelMugCodex\...
```

## Test the hook locally

Use PowerShell to simulate a Codex hook event:

```powershell
'{"event":"PreToolUse","tool_name":"Bash","tool_input":{"command":"idf.py build"}}' | .\dist\pixelmug-codex-hook.exe hook
```

The hook should exit with code 0 and produce no stdout. When Buddy is running, the received status appears in its log.
