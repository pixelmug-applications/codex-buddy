#define MyAppName "PixelMug Codex Buddy"
#define MyAppVersion ReadIni(AddBackslash(SourcePath) + "..\pyproject.toml", "project", "version", "")
#if MyAppVersion == ""
#error Missing [project].version in pyproject.toml
#endif
#define MyAppPublisher "PixelMug"
#define MyAppExeName "pixelmug-codex-buddy.exe"
#define MyAppIcon "..\assets\pixelmug-codex.ico"

[Setup]
AppId={{2D4EBF5E-9B6F-45D7-A736-94CF9C7E71D0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\PixelMugCodexBuddy
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\installer_out
OutputBaseFilename=PixelMugCodexBuddySetup-{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=no
UsePreviousAppDir=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startonlogin"; Description: "Start PixelMug Codex Buddy when I sign in"; GroupDescription: "Startup:"; Flags: checkedonce

[Files]
Source: "..\dist\pixelmug-codex-hook.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\pixelmug-codex-buddy.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\pixelmug-codex-cli.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}\PixelMug Codex Buddy"; Filename: "{app}\pixelmug-codex-buddy.exe"; IconFilename: "{app}\pixelmug-codex-buddy.exe"
Name: "{autoprograms}\{#MyAppName}\Uninstall PixelMug Codex Buddy"; Filename: "{uninstallexe}"; IconFilename: "{uninstallexe}"

[Run]
Filename: "{app}\pixelmug-codex-cli.exe"; Parameters: "install-hooks --hook-exe ""{app}\pixelmug-codex-hook.exe"""; Flags: runhidden waituntilterminated
Filename: "{app}\pixelmug-codex-cli.exe"; Parameters: "autostart on --bridge-exe ""{app}\pixelmug-codex-buddy.exe"""; Tasks: startonlogin; Flags: runhidden waituntilterminated
Filename: "{app}\pixelmug-codex-buddy.exe"; Description: "Launch PixelMug Codex Buddy"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\pixelmug-codex-cli.exe"; Parameters: "bridge-quit"; Flags: runhidden waituntilterminated; RunOnceId: "QuitBridge"
Filename: "{app}\pixelmug-codex-cli.exe"; Parameters: "autostart off"; Flags: runhidden waituntilterminated; RunOnceId: "DisableAutostart"
Filename: "{app}\pixelmug-codex-cli.exe"; Parameters: "uninstall-hooks"; Flags: runhidden waituntilterminated; RunOnceId: "UninstallHooks"
