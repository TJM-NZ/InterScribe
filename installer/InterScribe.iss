; InterScribe Windows installer — built with Inno Setup 6

#define AppName    "InterScribe"
#define AppVersion "1.0"
#define AppExe     "InterScribe.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL=https://github.com/TJM-NZ/InterScribe
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=dist
OutputBaseFilename=InterScribe-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
PrivilegesRequired=lowest
DisableProgramGroupPage=yes

[Files]
; Tray app
Source: "tray-app\bin\Release\net48\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion

; Docker Compose files
Source: "..\docker-compose.yml";     DestDir: "{app}"; Flags: ignoreversion
Source: "..\docker-compose.mac.yml"; DestDir: "{app}"; Flags: ignoreversion

; Setup script and env template
Source: "..\setup.bat";    DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; DestName: ".env.example"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}";    Filename: "{app}\{#AppExe}"
Name: "{userstartup}\{#AppName}";    Filename: "{app}\{#AppExe}"

[Run]
; Offer to run setup after install (interactive, shows a console window)
Filename: "{app}\setup.bat"; \
  Description: "Run initial setup (Docker check, model download, first launch)"; \
  Flags: postinstall shellexec skipifsilent; \
  StatusMsg: "Running setup…"

; Start tray app immediately after install
Filename: "{app}\{#AppExe}"; \
  Description: "Start InterScribe"; \
  Flags: postinstall nowait skipifsilent

[UninstallRun]
; Bring services down before uninstalling
Filename: "docker"; \
  Parameters: "compose -f ""{app}\docker-compose.yml"" -f ""{app}\docker-compose.mac.yml"" down"; \
  WorkingDir: "{app}"; \
  Flags: skipifdoesntexist runhidden

[Code]
function DockerRunning(): Boolean;
var
  RC: Integer;
begin
  Result := Exec('docker', 'info', '', SW_HIDE, ewWaitUntilTerminated, RC) and (RC = 0);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if not DockerRunning() then
  begin
    if MsgBox(
      'Docker Desktop does not appear to be running.' + #13#10 + #13#10 +
      'InterScribe requires Docker Desktop with WSL 2 integration enabled.' + #13#10 +
      'Download it from https://www.docker.com/products/docker-desktop/' + #13#10 + #13#10 +
      'Continue installation anyway?',
      mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
  end;
end;
