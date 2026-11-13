; League Start Tracker installer (Inno Setup 6). Built by installer/build.ps1, which
; first puts everything to install in ..\build:
;   build\League Start Tracker.exe   the launcher
;   build\python\                    a private copy of Python (with tkinter)
;   build\app\                       the tracker's code (updated in place by the app)
; Installs per user (no admin prompt) so the app can update its own files.
; Your times stay in %LOCALAPPDATA%\LeagueStartTracker and are never touched.

#define AppName "League Start Tracker"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppExe "League Start Tracker.exe"

[Setup]
AppId={{E44C8568-CC9C-4493-922C-E0730E4651A8}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=klovnary
AppPublisherURL=https://github.com/klovnary/poe1-leaguestart
AppUpdatesURL=https://github.com/klovnary/poe1-leaguestart/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=League-Start-Tracker-Setup
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
InfoBeforeFile=..\DISCLAIMER.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\build\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName} (with log window)"; Filename: "{app}\{#AppExe}"; Parameters: "--console"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; files the app changes itself (updates, Python's caches); your times are elsewhere
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"
