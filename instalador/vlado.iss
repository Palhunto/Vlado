; Inno Setup script for Vlado-Setup.exe. Compiled by scripts/gerar_instalador.py (ISCC /DVersao=... ).
; Per-user install, no administrator rights. Program in %LOCALAPPDATA%\Programs\Vlado;
; data in %LOCALAPPDATA%\Vlado (created by Vlado.exe, never touched by install, update or uninstall).

#ifndef Versao
  #define Versao "2.1.0"
#endif
#ifndef Origem
  #define Origem "..\build\instalador"
#endif

[Setup]
AppId={{7B3E2C1A-5D4F-4E8B-9A61-0C2D9F4B7E10}
AppName=Vlado
AppVersion={#Versao}
AppVerName=Vlado {#Versao}
AppPublisher=Vlado
DefaultDirName={localappdata}\Programs\Vlado
DefaultGroupName=Vlado
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Origem}\saida
OutputBaseFilename=Vlado-Setup
SetupIconFile={#Origem}\vlado.ico
UninstallDisplayIcon={app}\Vlado.exe
UninstallDisplayName=Vlado {#Versao}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Vlado.exe holds this mutex while running: setup and uninstall ask to close it first.
AppMutex=VladoMesaDeApuracao
CloseApplications=yes
LicenseFile=TERMO_DE_USO.txt

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Updates replace the program folder contents (never the data folder).
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Origem}\pyinstaller\Vlado\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Origem}\payload\tesseract\*"; DestDir: "{app}\tesseract"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Origem}\payload\ghostscript\*"; DestDir: "{app}\ghostscript"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#Origem}\payload\licencas\*"; DestDir: "{app}\licencas"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Vlado"; Filename: "{app}\Vlado.exe"; WorkingDir: "{app}"
Name: "{autoprograms}\Desinstalar Vlado"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Vlado"; Filename: "{app}\Vlado.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Vlado.exe"; Description: "{cm:LaunchProgram,Vlado}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only program files. %LOCALAPPDATA%\Vlado (cases, conversations, accounts, keys) is preserved.
Type: filesandordirs; Name: "{app}\_internal"
