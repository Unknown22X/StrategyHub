param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,

    [Parameter(Mandatory = $true)]
    [string]$DataRoot
)

$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path -LiteralPath $InstallRoot).Path
if (-not [System.IO.Path]::IsPathRooted($DataRoot)) {
    throw "RangeBot DataRoot must be an absolute path."
}
$resolvedDataRoot = [System.IO.Path]::GetFullPath($DataRoot)
$dataRootName = [System.IO.Path]::GetFileName($resolvedDataRoot.TrimEnd('\', '/'))
$dataRootWithSeparator = $resolvedDataRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
$installRootWithSeparator = $resolvedRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
if ($dataRootName -ne "RangeBot" -or
    [System.IO.Path]::GetPathRoot($resolvedDataRoot) -eq $resolvedDataRoot -or
    $resolvedRoot -ieq $resolvedDataRoot -or
    $resolvedRoot.StartsWith(
        $dataRootWithSeparator,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -or
    $resolvedDataRoot.StartsWith(
        $installRootWithSeparator,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
    throw "RangeBot DataRoot must be a non-root RangeBot directory outside the installation directory."
}
$useInteractiveProfileDefault = $resolvedDataRoot -match "[\\/]AppData[\\/]Local[\\/]RangeBot$"
$interactiveUserSid = $null

# In an elevated installation, Inno's user constants can resolve to a separate
# administrator account. Resolve the Explorer owner in this installer's session
# so a standard user's data still lands in that user's Local AppData profile.
try {
    $sessionId = (Get-Process -Id $PID).SessionId
    $explorer = Get-CimInstance Win32_Process -Filter "Name = 'explorer.exe'" |
        Where-Object { [int]$_.SessionId -eq $sessionId } |
        Select-Object -First 1
    if ($null -ne $explorer) {
        $owner = Invoke-CimMethod -InputObject $explorer -MethodName GetOwner
        if ($owner.ReturnValue -eq 0 -and $owner.User) {
            $account = New-Object System.Security.Principal.NTAccount -ArgumentList $owner.Domain, $owner.User
            $interactiveUserSid = $account.Translate(
                [System.Security.Principal.SecurityIdentifier]
            ).Value
            if ($useInteractiveProfileDefault) {
                $profileKey = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$interactiveUserSid"
                $profilePath = (Get-ItemProperty -LiteralPath $profileKey -Name ProfileImagePath).ProfileImagePath
                $profilePath = [Environment]::ExpandEnvironmentVariables($profilePath)
                $resolvedDataRoot = Join-Path (Join-Path $profilePath "AppData\Local") "RangeBot"
            }
        }
    }
} catch {
    Write-Warning "Could not resolve the interactive Windows profile; using the installer-provided LocalAppData path."
}

$serviceDirectory = Join-Path $resolvedRoot "service"
$winsw = Join-Path $serviceDirectory "RangeBot.Engine.exe"
$configuration = Join-Path $serviceDirectory "RangeBot.Engine.xml"
$serviceName = "RangeBotEngine"
$localService = "NT AUTHORITY\LOCAL SERVICE"

if (-not (Test-Path -LiteralPath $winsw) -or -not (Test-Path -LiteralPath $configuration)) {
    throw "WinSW executable and RangeBot.Engine.xml must exist in $serviceDirectory"
}

$ownershipMarker = Join-Path $resolvedDataRoot ".rangebot-data-root"
if (Test-Path -LiteralPath $resolvedDataRoot) {
    $existingItems = @(Get-ChildItem -LiteralPath $resolvedDataRoot -Force)
    if ($existingItems.Count -gt 0 -and
        -not (Test-Path -LiteralPath $ownershipMarker -PathType Leaf)) {
        $allowedLegacyNames = @("data", "config", "logs", "backup", "runtime")
        $unexpectedItems = @(
            $existingItems | Where-Object { $_.Name -notin $allowedLegacyNames }
        )
        $hasLegacyRangeBotDirectory = @(
            $existingItems | Where-Object {
                $_.PSIsContainer -and $_.Name -in $allowedLegacyNames
            }
        ).Count -gt 0
        if ($unexpectedItems.Count -gt 0 -or -not $hasLegacyRangeBotDirectory) {
            throw "Refusing to use a non-empty directory that is not an existing RangeBot data root."
        }
    }
}

New-Item -ItemType Directory -Force -Path $resolvedDataRoot | Out-Null
foreach ($directory in @("data", "config", "config\credentials", "logs", "backup", "runtime")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $resolvedDataRoot $directory) | Out-Null
}
$markerEncoding = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $ownershipMarker,
    "RangeBot managed data root.",
    $markerEncoding
)

# Keep the required user-local data root while allowing the passwordless LocalService
# engine to read and write it after logout or RDP disconnection.
& icacls.exe $resolvedDataRoot /inheritance:r | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to disable inherited RangeBot data ACLs." }
$aclGrants = @(
    "${localService}:(OI)(CI)(F)",
    "SYSTEM:(OI)(CI)(F)",
    "BUILTIN\Administrators:(OI)(CI)(F)"
)
if ($interactiveUserSid) {
    $aclGrants += "*${interactiveUserSid}:(OI)(CI)(F)"
}
& icacls.exe $resolvedDataRoot /grant:r $aclGrants | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to apply RangeBot data ACLs." }

# WinSW runs as LocalService, so %LOCALAPPDATA% would otherwise resolve to the
# service profile. Materialize the session user's absolute path before installing
# or reinstalling the service.
[xml]$serviceXml = Get-Content -LiteralPath $configuration -Raw
$homeNode = $serviceXml.SelectSingleNode("/service/env[@name='RANGEBOT_HOME']")
$logNode = $serviceXml.SelectSingleNode("/service/logpath")
if ($null -eq $homeNode -or $null -eq $logNode) {
    throw "RangeBot.Engine.xml is missing its data-root placeholders."
}
$homeNode.SetAttribute("value", $resolvedDataRoot)
$logNode.InnerText = Join-Path $resolvedDataRoot "logs"
$serviceXml.Save($configuration)

$existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($null -ne $existingService) {
    $existingServiceRecord = Get-CimInstance Win32_Service -Filter "Name = '$serviceName'"
    $expectedWrapperPath = '"' + $winsw + '"'
    $usesCurrentWrapper = $null -ne $existingServiceRecord -and
        $existingServiceRecord.PathName -ieq $expectedWrapperPath

    if ($existingService.Status -ne "Stopped") {
        if ($usesCurrentWrapper) {
            & $winsw stop
        } else {
            & sc.exe stop $serviceName | Out-Null
        }
        if ($LASTEXITCODE -ne 0) { throw "RangeBot service stop failed during upgrade." }
    }

    if ($usesCurrentWrapper) {
        & $winsw uninstall
        if ($LASTEXITCODE -ne 0) { throw "RangeBot service removal failed during upgrade." }
    } else {
        # A previous installer may have registered the same service name from a
        # different installation directory. Remove only that named service
        # before installing the current wrapper. User data remains under the
        # separate data root.
        & sc.exe delete $serviceName | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "RangeBot service removal failed during upgrade." }
    }

    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    do {
        Start-Sleep -Milliseconds 250
        $remainingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    } while ($null -ne $remainingService -and [DateTime]::UtcNow -lt $deadline)

    if ($null -ne $remainingService) {
        throw "RangeBot service remained registered after upgrade removal."
    }

    & $winsw install
    if ($LASTEXITCODE -ne 0) { throw "RangeBot service installation failed." }
} else {
    & $winsw install
    if ($LASTEXITCODE -ne 0) { throw "RangeBot service installation failed." }
}

$scConfiguration = Start-Process -FilePath sc.exe -ArgumentList (
    'config {0} obj= "NT AUTHORITY\LocalService" password= "" start= auto' -f $serviceName
) -Wait -PassThru -WindowStyle Hidden
if ($scConfiguration.ExitCode -ne 0) { throw "RangeBot LocalService configuration failed." }
& $winsw start
if ($LASTEXITCODE -ne 0) { throw "RangeBot service start failed." }
