param(
    [Parameter(Mandatory = $true)][string]$Database,
    [Parameter(Mandatory = $true)][string]$Username,
    [Parameter(Mandatory = $true)][string]$OutputFile,
    [string]$HostName = "127.0.0.1"
)

$parent = Split-Path -Parent $OutputFile
if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent | Out-Null
}

& pg_dump --format=custom --file $OutputFile --host $HostName --username $Username $Database
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL backup failed." }
