param(
    [Parameter(Mandatory = $true)][string]$Database,
    [Parameter(Mandatory = $true)][string]$Username,
    [Parameter(Mandatory = $true)][string]$BackupFile,
    [string]$HostName = "127.0.0.1",
    [Parameter(Mandatory = $true)][ValidateSet("RESTORE RANGEBOT")][string]$Confirmation
)

if (-not (Test-Path -LiteralPath $BackupFile)) {
    throw "Backup file not found: $BackupFile"
}

& pg_restore --clean --if-exists --host $HostName --username $Username --dbname $Database $BackupFile
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL restore failed." }

Write-Output "Start bot-engine.exe with --restored-state. Entries remain blocked until reconciliation succeeds."
