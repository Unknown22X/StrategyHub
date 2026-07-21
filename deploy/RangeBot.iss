#define MyAppName "RangeBot"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "RangeBot"
#define MyAppExeName "RangeBot.exe"

[Setup]
AppId={{D3943178-972D-4B4E-A1B0-5C47D354DFF1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\RangeBot
DefaultGroupName=RangeBot
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=RangeBot-Setup
SetupIconFile=RangeBot.ico
UninstallDisplayIcon={app}\launcher\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=RangeBot local multi-strategy trading application

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\bot-engine\*"; DestDir: "{app}\engine"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\RangeBot\*"; DestDir: "{app}\launcher"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\vendor\WinSW-x64.exe"; DestDir: "{app}\service"; DestName: "RangeBot.Engine.exe"; Flags: ignoreversion
Source: "RangeBot.Engine.xml"; DestDir: "{app}\service"; Flags: ignoreversion
Source: "install-service.ps1"; DestDir: "{app}\service"; Flags: ignoreversion
Source: "uninstall-service.ps1"; DestDir: "{app}\service"; Flags: ignoreversion
Source: "stop-engine-for-upgrade.ps1"; Flags: dontcopy
Source: "..\vendor\WinSW-LICENSE.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\USER_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\KNOWN_LIMITATIONS.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\demo\*"; DestDir: "{app}\demo"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RangeBot"; Filename: "{app}\launcher\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\StrategyHub Paper Demo"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\demo\Start-StrategyHub-Paper-Demo.ps1"""; WorkingDir: "{app}\demo"; IconFilename: "{app}\launcher\{#MyAppExeName}"
Name: "{autodesktop}\RangeBot"; Filename: "{app}\launcher\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autodesktop}\StrategyHub Paper Demo"; Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\demo\Start-StrategyHub-Paper-Demo.ps1"""; WorkingDir: "{app}\demo"; IconFilename: "{app}\launcher\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\launcher\{#MyAppExeName}"; Description: "{cm:LaunchProgram,RangeBot}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[Code]
var
  RemovePersonalData: Boolean;
  ExistingDataRoot: String;
  DataDirectoryPage: TInputDirWizardPage;
  UpgradeInstall: Boolean;

procedure InitializeWizard;
var
  PageTitle: String;
  PageDescription: String;
begin
  UpgradeInstall := False;
  if ActiveLanguage = 'arabic' then
  begin
    PageTitle := 'موقع بيانات RangeBot';
    PageDescription := 'اختر مكان قاعدة البيانات والسجلات والنسخ الاحتياطية. يمكنك اختيار D:\RangeBot لتوفير مساحة القرص C.';
  end
  else
  begin
    PageTitle := 'RangeBot data location';
    PageDescription := 'Choose where to keep the database, logs, and backups. You can select D:\RangeBot to save space on C:.';
  end;

  DataDirectoryPage := CreateInputDirPage(
    wpSelectDir,
    PageTitle,
    PageDescription,
    '',
    False,
    ''
  );
  DataDirectoryPage.Add('');
  DataDirectoryPage.Values[0] := ExpandConstant('{localappdata}\RangeBot');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
    UpgradeInstall := FileExists(
      AddBackslash(WizardDirValue) + 'service\RangeBot.Engine.xml'
    );
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := UpgradeInstall and (PageID = DataDirectoryPage.ID);
end;

function DataRemovalQuestion(): String;
begin
  if ActiveLanguage = 'arabic' then
    Result := 'هل تريد حذف جميع إعدادات RangeBot وسجل التداول والنسخ الاحتياطية؟ اختر لا للاحتفاظ ببياناتك.'
  else
    Result := 'Remove all RangeBot settings, trading history, logs, and backups? Choose No to keep your personal data.';
end;

function ServiceActionFailureMessage(ActionName: String; ResultCode: Integer): String;
begin
  if ActiveLanguage = 'arabic' then
    Result := 'فشلت عملية خدمة RangeBot. رمز الخطأ: ' + IntToStr(ResultCode) +
      '. لم تكتمل العملية بأمان.'
  else
    Result := 'Failed to ' + ActionName + ' the RangeBot service. Exit code: ' +
      IntToStr(ResultCode) + '. The operation did not complete safely.';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  PowerShellPath: String;
  Parameters: String;
  ServiceUninstaller: String;
  UpgradeHelper: String;
  DataRootFile: String;
  DataRootLines: TArrayOfString;
begin
  Result := '';
  PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  ServiceUninstaller := ExpandConstant('{app}\service\uninstall-service.ps1');
  if FileExists(ServiceUninstaller) then
  begin
    Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' +
      ServiceUninstaller + '" -InstallRoot "' + ExpandConstant('{app}') + '"';

    if not Exec(
      PowerShellPath,
      Parameters,
      ExpandConstant('{app}\service'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    ) then
    begin
      Result := ServiceActionFailureMessage('prepare the upgrade', ResultCode);
      Exit;
    end;
    if ResultCode <> 0 then
    begin
      Result := ServiceActionFailureMessage('prepare the upgrade', ResultCode);
      Exit;
    end;
  end;

  ExtractTemporaryFile('stop-engine-for-upgrade.ps1');
  UpgradeHelper := ExpandConstant('{tmp}\stop-engine-for-upgrade.ps1');
  DataRootFile := ExpandConstant('{tmp}\rangebot-data-root.txt');
  Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' +
    UpgradeHelper + '" -InstallRoot "' + ExpandConstant('{app}') +
    '" -DataRootOutputFile "' + DataRootFile + '"';

  if not Exec(
    PowerShellPath,
    Parameters,
    ExpandConstant('{tmp}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    Result := ServiceActionFailureMessage('unlock the upgrade', ResultCode);
    Exit;
  end;
  if ResultCode <> 0 then
  begin
    Result := ServiceActionFailureMessage('unlock the upgrade', ResultCode);
    Exit;
  end;

  if FileExists(DataRootFile) and LoadStringsFromFile(DataRootFile, DataRootLines) then
  begin
    if GetArrayLength(DataRootLines) > 0 then
      ExistingDataRoot := Trim(DataRootLines[0]);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  PowerShellPath: String;
  Parameters: String;
  InstallDataRoot: String;
begin
  if CurStep <> ssPostInstall then
    Exit;

  PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  InstallDataRoot := ExistingDataRoot;
  if InstallDataRoot = '' then
    InstallDataRoot := DataDirectoryPage.Values[0];
  Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\service\install-service.ps1') + '" -InstallRoot "' +
    ExpandConstant('{app}') + '" -DataRoot "' +
    InstallDataRoot + '"';

  if not Exec(
    PowerShellPath,
    Parameters,
    ExpandConstant('{app}\service'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
    RaiseException(ServiceActionFailureMessage('start', ResultCode));
  if ResultCode <> 0 then
    RaiseException(ServiceActionFailureMessage('start', ResultCode));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  PowerShellPath: String;
  Parameters: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    if UninstallSilent then
      RemovePersonalData := False
    else
      RemovePersonalData := MsgBox(
        DataRemovalQuestion(),
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON2
      ) = IDYES;

    PowerShellPath := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
    Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{app}\service\uninstall-service.ps1') + '" -InstallRoot "' +
      ExpandConstant('{app}') + '"';
    if RemovePersonalData then
      Parameters := Parameters + ' -RemovePersonalData';
    if not Exec(
      PowerShellPath,
      Parameters,
      ExpandConstant('{app}\service'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    ) then
      RaiseException(ServiceActionFailureMessage('remove', ResultCode));
    if ResultCode <> 0 then
      RaiseException(ServiceActionFailureMessage('remove', ResultCode));
  end;
end;
