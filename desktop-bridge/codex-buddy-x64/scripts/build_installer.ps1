param(
    [string]$Path = "iscc"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ScriptPath = "installer\pixelmug-codex-buddy.iss"
$OutputDir = Join-Path $Root "installer_out"

if (!(Test-Path "dist\pixelmug-codex-hook.exe") -or !(Test-Path "dist\pixelmug-codex-buddy.exe") -or !(Test-Path "dist\pixelmug-codex-cli.exe")) {
    throw "EXEs not found. Run scripts\build_exe.ps1 first."
}

if (!(Test-Path -LiteralPath $ScriptPath)) {
    throw "Installer script not found: $ScriptPath"
}

New-Item -ItemType Directory -Force $OutputDir | Out-Null

function Resolve-InnoPath([string]$InputPath) {
    if ($InputPath -eq "iscc") {
        $cmd = Get-Command iscc -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        foreach ($candidate in @(
            "C:\Program Files\Inno Setup 7\ISCC.exe",
            "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
            "C:\Program Files\Inno Setup 6\ISCC.exe",
            "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            "C:\Program Files\Inno Setup 7\ISIDE.exe",
            "C:\Program Files (x86)\Inno Setup 7\ISIDE.exe",
            "C:\Program Files\Inno Setup 6\ISIDE.exe",
            "C:\Program Files (x86)\Inno Setup 6\ISIDE.exe"
        )) {
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
        return ""
    }
    return $InputPath
}

$InnoPath = Resolve-InnoPath $Path
if (!$InnoPath -or !(Test-Path -LiteralPath $InnoPath)) {
    throw "Inno Setup executable was not found. Pass -Path with ISCC.exe for automatic build or ISIDE.exe for manual IDE build."
}

$leaf = Split-Path -Leaf $InnoPath
if ($leaf -ieq "ISCC.exe") {
    & $InnoPath $ScriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC failed with exit code $LASTEXITCODE."
    }
    Write-Host "Done. Installer is in: $OutputDir"
    exit 0
}

if ($leaf -ieq "ISIDE.exe") {
    Write-Host "Opening Inno Setup IDE: $InnoPath"
    Write-Host "Script: $Root\$ScriptPath"
    Write-Host "In the IDE, click Build/Compile. Output will be written to: $OutputDir"
    Start-Process -FilePath $InnoPath -ArgumentList @($ScriptPath) -WorkingDirectory $Root
    exit 0
}

throw "Unsupported Inno Setup executable: $InnoPath. Use ISCC.exe or ISIDE.exe."


