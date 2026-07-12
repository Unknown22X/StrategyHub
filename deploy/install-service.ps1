param(
    [Parameter(Mandatory = $true)]
    [string]$InstallRoot
)

$resolvedRoot = (Resolve-Path -LiteralPath $InstallRoot).Path
$serviceDirectory = Join-Path $resolvedRoot "service"
$winsw = Join-Path $serviceDirectory "RangeBot.Engine.exe"
$configuration = Join-Path $serviceDirectory "RangeBot.Engine.xml"

if (-not (Test-Path -LiteralPath $winsw) -or -not (Test-Path -LiteralPath $configuration)) {
    throw "WinSW executable and RangeBot.Engine.xml must exist in $serviceDirectory"
}

& $winsw install
if ($LASTEXITCODE -ne 0) { throw "RangeBot service installation failed." }
& $winsw start
if ($LASTEXITCODE -ne 0) { throw "RangeBot service start failed." }
