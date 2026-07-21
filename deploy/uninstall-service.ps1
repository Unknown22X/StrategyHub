param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,

    [switch]$RemovePersonalData
)

$ErrorActionPreference = "Stop"
$serviceDirectory = Join-Path $InstallRoot "service"
$winsw = Join-Path $serviceDirectory "RangeBot.Engine.exe"
$configuration = Join-Path $serviceDirectory "RangeBot.Engine.xml"
$serviceName = "RangeBotEngine"
$engineExecutable = Join-Path $InstallRoot "engine\bot-engine.exe"
$dataRoot = $null

function Get-InstalledEngineProcesses {
    $expectedPath = [System.IO.Path]::GetFullPath($engineExecutable)
    return @(
        Get-CimInstance Win32_Process -Filter "Name = 'bot-engine.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $processPath = [string]$_.ExecutablePath
                $processPath -and
                    [System.IO.Path]::GetFullPath($processPath) -ieq $expectedPath
            }
    )
}

if ($RemovePersonalData) {
    if (-not (Test-Path -LiteralPath $configuration)) {
        throw "Cannot safely locate RangeBot personal data because the service configuration is missing."
    }
    [xml]$serviceXml = Get-Content -LiteralPath $configuration -Raw
    $homeNode = $serviceXml.SelectSingleNode("/service/env[@name='RANGEBOT_HOME']")
    if ($null -eq $homeNode -or -not $homeNode.value) {
        throw "Cannot safely locate RangeBot personal data from the service configuration."
    }
    $rawDataRoot = [string]$homeNode.value
    if (-not [System.IO.Path]::IsPathRooted($rawDataRoot)) {
        throw "Refusing to delete a non-absolute RangeBot personal-data path."
    }
    $dataRoot = [System.IO.Path]::GetFullPath($rawDataRoot)
    $resolvedInstallRoot = [System.IO.Path]::GetFullPath($InstallRoot)
    $dataRootWithSeparator = $dataRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    $installRootWithSeparator = $resolvedInstallRoot.TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
    if ([System.IO.Path]::GetFileName($dataRoot) -ne "RangeBot" -or
        [System.IO.Path]::GetPathRoot($dataRoot) -eq $dataRoot -or
        $resolvedInstallRoot -ieq $dataRoot -or
        $resolvedInstallRoot.StartsWith(
            $dataRootWithSeparator,
            [System.StringComparison]::OrdinalIgnoreCase
        ) -or
        $dataRoot.StartsWith(
            $installRootWithSeparator,
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
        throw "Refusing to delete an invalid RangeBot personal-data path."
    }
}

if (-not (Test-Path -LiteralPath $winsw)) {
    $existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        throw "RangeBot service is still registered, but the WinSW executable is missing."
    }
} else {
    $existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($null -ne $existingService) {
        if ($existingService.Status -ne "Stopped") {
            & $winsw stop
            if ($LASTEXITCODE -ne 0) { throw "RangeBot service stop failed." }
        }

        & $winsw uninstall
        if ($LASTEXITCODE -ne 0) { throw "RangeBot service removal failed." }

        $deadline = [DateTime]::UtcNow.AddSeconds(45)
        do {
            Start-Sleep -Milliseconds 250
            $remaining = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        } while ($null -ne $remaining -and [DateTime]::UtcNow -lt $deadline)

        if ($null -ne $remaining) {
            throw "RangeBot service remained registered after removal."
        }
    }
}

# WinSW can finish unregistering before its child engine has completely exited.
# Wait for that exact installed executable, then terminate only that scoped
# leftover process so Inno Setup can safely replace the engine files.
$processDeadline = [DateTime]::UtcNow.AddSeconds(15)
do {
    $engineProcesses = @(Get-InstalledEngineProcesses)
    if ($engineProcesses.Count -eq 0) { break }
    Start-Sleep -Milliseconds 250
} while ([DateTime]::UtcNow -lt $processDeadline)

foreach ($process in $engineProcesses) {
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    } catch {
        if ($null -ne (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue)) {
            throw
        }
    }
}

if ($engineProcesses.Count -gt 0) {
    Start-Sleep -Milliseconds 500
}
if (@(Get-InstalledEngineProcesses).Count -gt 0) {
    throw "RangeBot engine process remained after service removal."
}

if ($RemovePersonalData -and (Test-Path -LiteralPath $dataRoot)) {
    $ownershipMarker = Join-Path $dataRoot ".rangebot-data-root"
    if (-not (Test-Path -LiteralPath $ownershipMarker -PathType Leaf)) {
        throw "Refusing to delete RangeBot personal data without its ownership marker."
    }
    Remove-Item -LiteralPath $dataRoot -Recurse -Force
}
