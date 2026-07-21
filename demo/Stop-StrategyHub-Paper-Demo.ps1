$ErrorActionPreference = "Stop"
$LocalAppData = [Environment]::GetFolderPath('LocalApplicationData')
if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
    throw "Windows Local AppData could not be resolved."
}
$DemoRoot = Join-Path $LocalAppData "StrategyHub-Paper-Demo-20260721\RangeBot"
$PidFile = Join-Path $DemoRoot "runtime\paper-demo-engine.pid"

$pidValue = $null
if (Test-Path -LiteralPath $PidFile -PathType Leaf) {
    $raw = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($raw -match '^\d+$') {
        $pidValue = [int]$raw
    }
}

if ($null -ne $pidValue) {
    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($null -ne $process) {
        Stop-Process -Id $pidValue -Force
        $process.WaitForExit()
    }
}

Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "StrategyHub Paper demo engine stopped."
Write-Host "The clean demo data remains at $DemoRoot."
