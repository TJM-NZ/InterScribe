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
const
  DockerDesktopUrl = 'https://www.docker.com/products/docker-desktop/';

function DockerInstalled(): Boolean;
begin
  Result := FileExists(ExpandConstant('{commonpf64}\Docker\Docker\Docker Desktop.exe'))
         or FileExists(ExpandConstant('{commonpf}\Docker\Docker\Docker Desktop.exe'));
end;

function DockerRunning(): Boolean;
var RC: Integer;
begin
  Result := Exec('docker', 'info', '', SW_HIDE, ewWaitUntilTerminated, RC) and (RC = 0);
end;

function OllamaInstalled(): Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'));
end;

function InitializeSetup(): Boolean;
var RC: Integer;
begin
  Result := True;

  if not DockerInstalled() then
  begin
    if MsgBox(
      'Docker Desktop is required but is not installed.' + #13#10 + #13#10 +
      'InterScribe needs Docker Desktop with WSL 2 to run its services.' + #13#10 + #13#10 +
      'Click Yes to open the Docker Desktop download page.' + #13#10 +
      'After installing, start Docker Desktop, wait for it to finish' + #13#10 +
      'loading, then run this installer again.',
      mbConfirmation, MB_YESNO) = IDYES then
      ShellExec('open', DockerDesktopUrl, '', '', SW_SHOW, ewNoWait, RC);
    Result := False;
    Exit;
  end;

  if not DockerRunning() then
  begin
    MsgBox(
      'Docker Desktop is installed but is not running.' + #13#10 + #13#10 +
      'Start Docker Desktop, wait for it to finish loading, then run this installer again.',
      mbInformation, MB_OK);
    Result := False;
    Exit;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var RC: Integer;
begin
  Result := '';
  NeedsRestart := False;

  if not OllamaInstalled() then
  begin
    WizardForm.StatusLabel.Caption := 'Installing Ollama (AI model runtime)...';
    if not Exec('winget',
                'install Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements',
                '', SW_HIDE, ewWaitUntilTerminated, RC)
       or (RC <> 0) then
      Result := 'Could not install Ollama automatically.' + #13#10 +
                'Download and install it from https://ollama.com then run this installer again.';
  end;
end;
