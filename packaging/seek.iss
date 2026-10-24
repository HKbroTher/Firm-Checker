; Seek Windows 安装包（Inno Setup 6）
; 先用 PyInstaller 打包出 dist\Seek，再执行：
;   iscc /DAppVersion=0.2.2 packaging\seek.iss
; 生成 dist\Seek-Setup-<版本>-x64.exe

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define ChsIsl CompilerPath + "Languages\ChineseSimplified.isl"

[Setup]
; AppId 用于识别同一个软件，升级安装时覆盖旧版本，不要修改
AppId={{8F3C2A51-6B7E-4D2C-9A1F-5E0B7C3D9A42}
AppName=Seek
AppVersion={#AppVersion}
AppVerName=Seek {#AppVersion}
AppPublisher=HKbroTher
AppPublisherURL=https://github.com/HKbroTher/Seek
AppSupportURL=https://github.com/HKbroTher/Seek/issues
; 默认装到当前用户目录（%LOCALAPPDATA%\Programs\Seek），不需要管理员权限
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\Seek
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Seek-Setup-{#AppVersion}-x64
SetupIconFile=seek.ico
UninstallDisplayIcon={app}\Seek.exe
UninstallDisplayName=Seek
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 升级时自动关闭正在运行的 Seek
CloseApplications=yes

[Languages]
#if FileExists(ChsIsl)
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Seek\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; 升级时清掉旧版本的程序文件，避免残留不兼容的依赖；用户数据在 %APPDATA%\Seek，不受影响
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Seek"; Filename: "{app}\Seek.exe"
Name: "{autodesktop}\Seek"; Filename: "{app}\Seek.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Seek.exe"; Description: "{cm:LaunchProgram,Seek}"; Flags: nowait postinstall skipifsilent
