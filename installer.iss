; ---------------------------------------------------------------------------
; HOPE Plugin Tester - Inno Setup Script
; ---------------------------------------------------------------------------
; Build requirements:
;   Inno Setup 6  (https://jrsoftware.org/isdl.php)
;
; To compile manually:
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
; Or use build_installer.ps1 which handles Inno Setup download automatically.
; ---------------------------------------------------------------------------

#define AppName      "HOPE Plugin Tester"
#define AppVersion   "1.0.0"
#define AppPublisher "Sovalius Corporation"
#define AppURL       "https://github.com/Sovalius-Corporation/HOPE_PluginTester"
#define AppExeName   "HOPEPluginTester.exe"
#define DistDir      "dist\HOPEPluginTester"

[Setup]
; Unique GUID — do NOT change after first release (used for upgrades/uninstall)
AppId={{B7C4F21A-9E3D-4B8F-AE12-6D053C7A1F40}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Install to Program Files\HOPE Plugin Tester
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; Allow user to choose whether to add desktop icon
; (shown on last page of installer)
AllowNoIcons=yes

; Output
OutputDir=dist\installer
OutputBaseFilename=HOPEPluginTester_Setup_{#AppVersion}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Require 64-bit Windows
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Visual
WizardStyle=modern
WizardSizePercent=120

; Minimum Windows version: Windows 10
MinVersion=10.0

; Request admin rights so we can install to Program Files
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline

; Restart hint (not required, but good practice)
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Main executable
Source: "{#DistDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; All support files in _internal\
Source: "{#DistDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

; Desktop shortcut (only if user ticked the task)
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Offer to launch the app after install
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up logs/cache written by the app inside its own install folder
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\cache"
