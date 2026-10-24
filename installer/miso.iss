; Miso installer (Inno Setup 6) — built by build.ps1
; Installs per user (no admin prompt) into %LOCALAPPDATA%\Programs\Miso.

#define AppName "Miso"
#define AppVersion "1.0.0"
#define AppExe "Miso.exe"

[Setup]
AppId={{6B1E8C2A-5D47-4F0E-9A63-2C7F1D4E8B90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Miso
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=Miso-Setup
SetupIconFile=..\assets\icon.ico
LicenseFile=..\LICENSE
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardSmallImageFile=..\assets\setup-small.bmp,..\assets\setup-small-200.bmp
Compression=lzma2/ultra64
SolidCompression=yes
AppMutex=MisoAppMutex
CloseApplications=yes

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Miso\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; Miso writes this itself when "Mit Windows starten" is on — remove it on uninstall
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Miso"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if MsgBox('Sollen auch deine Bibliothek, heruntergeladene Workshop-Items, eigene Bilder und ' +
              'Einstellungen gelöscht werden?' + #13#10#13#10 +
              'Wähle "Nein", wenn du Miso später wieder installieren und alles behalten willst.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\Miso'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\Miso'), True, True, True);
    end;
end;
