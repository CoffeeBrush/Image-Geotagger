[Setup]
AppName=Image Geotagger
AppVersion=1.0
AppPublisher=Chris Stevenson
AppPublisherURL=https://github.com/coffeebrush/Image-Geotagger
AppSupportURL=https://github.com/coffeebrush/Image-Geotagger/issues
AppUpdatesURL=https://github.com/coffeebrush/Image-Geotagger/releases

DefaultDirName={pf}\Chris Stevenson\Image Geotagger
DefaultGroupName=Image Geotagger

OutputDir=installer
OutputBaseFilename="Image Geotagger Setup"
Compression=lzma
SolidCompression=yes

ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

SetupIconFile=bin\icon.ico
UninstallDisplayIcon={app}\Image Geotagger.exe

DisableProgramGroupPage=yes
PrivilegesRequired=admin

[Files]
Source: "dist\Image Geotagger\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Image Geotagger"; Filename: "{app}\Image Geotagger.exe"
Name: "{commondesktop}\Image Geotagger"; Filename: "{app}\Image Geotagger.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\Image Geotagger.exe"; Description: "Launch Image Geotagger"; Flags: nowait postinstall skipifsilent
