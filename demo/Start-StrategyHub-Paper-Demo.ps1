param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Port = 8876
$LocalAppData = [Environment]::GetFolderPath('LocalApplicationData')
if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
    throw "Windows Local AppData could not be resolved."
}
$DemoRoot = Join-Path $LocalAppData "StrategyHub-Paper-Demo-20260721\RangeBot"
$ApplicationRoot = Split-Path $PSScriptRoot -Parent
$RebuiltEngine = Join-Path $ApplicationRoot "dist\bot-engine\bot-engine.exe"
$ApplicationEngine = Join-Path $ApplicationRoot "engine\bot-engine.exe"
$DefaultInstalledEngine = "C:\Program Files\RangeBot\engine\bot-engine.exe"
$Engine = if (Test-Path -LiteralPath $RebuiltEngine -PathType Leaf) {
    $RebuiltEngine
} elseif (Test-Path -LiteralPath $ApplicationEngine -PathType Leaf) {
    $ApplicationEngine
} else {
    $DefaultInstalledEngine
}
$RuntimeDirectory = Join-Path $DemoRoot "runtime"
$LogsDirectory = Join-Path $DemoRoot "logs"
$PidFile = Join-Path $RuntimeDirectory "paper-demo-engine.pid"
$Url = "http://127.0.0.1:$Port"

if (-not (Test-Path -LiteralPath $Engine -PathType Leaf)) {
    throw "Installed StrategyHub engine not found at $Engine. Install RangeBot-Setup.exe first."
}

foreach ($directory in @(
    $DemoRoot,
    (Join-Path $DemoRoot "data"),
    (Join-Path $DemoRoot "config"),
    (Join-Path $DemoRoot "config\credentials"),
    $LogsDirectory,
    (Join-Path $DemoRoot "backup"),
    $RuntimeDirectory
)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

function Get-Health {
    try {
        return Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 2
    } catch {
        return $null
    }
}

function Assert-PaperRuntime {
    $runtime = Invoke-RestMethod -Uri "$Url/v1/runtime/environment" -TimeoutSec 5
    $valid =
        $runtime.configured_environment -eq "paper" -and
        $runtime.requested_environment -eq "paper" -and
        $runtime.active_engine_environment -eq "paper" -and
        $null -eq $runtime.exchange_adapter_environment -and
        $runtime.transition_state -eq "ready" -and
        $runtime.activated -eq $true -and
        $null -eq $runtime.credential_profile
    if (-not $valid) {
        throw "Paper demo runtime safety validation failed. Close the demo engine and inspect PAPER_DEMO_STATUS.md."
    }
    return $runtime
}

$health = Get-Health
if ($null -eq $health) {
    $env:RANGEBOT_HOME = $DemoRoot
    $arguments = @(
        "--mode", "paper",
        "--enable-public-websocket",
        "--host", "127.0.0.1",
        "--port", "$Port"
    )
    $process = Start-Process -FilePath $Engine -ArgumentList $arguments -WorkingDirectory (Split-Path $Engine -Parent) -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ASCII

    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        Start-Sleep -Milliseconds 400
        $health = Get-Health
        if ($process.HasExited) {
            throw "Paper demo engine exited during startup. Check $LogsDirectory."
        }
    } while ($null -eq $health -and [DateTime]::UtcNow -lt $deadline)

    if ($null -eq $health) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "Paper demo engine did not become healthy within 60 seconds."
    }
}

$runtime = Assert-PaperRuntime
Write-Host "StrategyHub Paper demo is ready."
Write-Host "Data root: $DemoRoot"
Write-Host "URL: $Url/app/"
Write-Host "Environment: $($runtime.active_engine_environment) / $($runtime.transition_state)"

if (-not $NoBrowser) {
    Start-Process "$Url/app/"
}
