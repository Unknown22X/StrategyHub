param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot,

    [Parameter(Mandatory = $true)]
    [string]$DataRootOutputFile
)

$ErrorActionPreference = "Stop"
$configuration = Join-Path $InstallRoot "service\RangeBot.Engine.xml"
$engineExecutable = Join-Path $InstallRoot "engine\bot-engine.exe"
$expectedEnginePath = [System.IO.Path]::GetFullPath($engineExecutable)

# Preserve a previously selected data root (including one on D:) before the
# installer replaces the materialized service configuration.
if (Test-Path -LiteralPath $configuration) {
    [xml]$serviceXml = Get-Content -LiteralPath $configuration -Raw
    $homeNode = $serviceXml.SelectSingleNode("/service/env[@name='RANGEBOT_HOME']")
    if ($null -ne $homeNode -and $homeNode.value) {
        $dataRoot = [string]$homeNode.value
        if ([System.IO.Path]::IsPathRooted($dataRoot) -and
            -not $dataRoot.Contains("__RANGEBOT_DATA_ROOT__")) {
            $dataRoot = [System.IO.Path]::GetFullPath($dataRoot)
            $utf8WithBom = New-Object System.Text.UTF8Encoding($true)
            [System.IO.File]::WriteAllText($DataRootOutputFile, $dataRoot, $utf8WithBom)
        }
    }
}

function Get-InstalledEngineProcesses {
    return @(
        Get-CimInstance Win32_Process -Filter "Name = 'bot-engine.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $processPath = [string]$_.ExecutablePath
                $processPath -and
                    [System.IO.Path]::GetFullPath($processPath) -ieq $expectedEnginePath
            }
    )
}

# The previous installed uninstaller may return before its child exits. Stop
# only the engine from this installation, never another bot-engine executable.
foreach ($process in @(Get-InstalledEngineProcesses)) {
    try {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    } catch {
        if ($null -ne (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue)) {
            throw
        }
    }
}

Start-Sleep -Milliseconds 500
if (@(Get-InstalledEngineProcesses).Count -gt 0) {
    throw "RangeBot engine process remained locked during upgrade."
}
