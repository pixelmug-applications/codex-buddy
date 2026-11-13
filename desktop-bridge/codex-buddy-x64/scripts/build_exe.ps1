param(
    [string]$Python = "py -3"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[1/5] Creating virtual environment..."
if (!(Test-Path ".venv")) {
    Invoke-Expression "$Python -m venv .venv"
}

Write-Host "[2/5] Installing dependencies..."
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "[3/5] Creating Windows icon..."
.\.venv\Scripts\python.exe .\scripts\make_windows_icon.py
$IconPath = Join-Path $Root "assets\pixelmug-codex.ico"
if (!(Test-Path -LiteralPath $IconPath)) {
    throw "Windows icon was not produced: $IconPath"
}

Write-Host "[4/5] Cleaning old build output..."
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Remove-Item -Force *.spec -ErrorAction SilentlyContinue

Write-Host "[5/5] Building EXEs with PyInstaller..."
.\.venv\Scripts\python.exe -m PyInstaller --clean --onefile --console --icon $IconPath --name pixelmug-codex-hook --paths src src\pixelmug_codex_host\entry_hook.py
.\.venv\Scripts\python.exe -m PyInstaller --clean --onefile --console --icon $IconPath --name pixelmug-codex-cli --paths src src\pixelmug_codex_host\entry_cli.py
.\.venv\Scripts\python.exe -m PyInstaller --clean --onefile --windowed --icon $IconPath --name pixelmug-codex-buddy --paths src --add-data "assets;assets" src\pixelmug_codex_host\entry_bridge.py

$BuddyExe = Join-Path $Root "dist\pixelmug-codex-buddy.exe"
if (!(Test-Path -LiteralPath $BuddyExe)) {
    throw "Buddy EXE was not produced: $BuddyExe"
}

Write-Host "Done. EXEs are in: $Root\dist"
