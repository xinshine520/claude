# Rebuild pg-mcp test database fixtures (Windows)
# Usage:
#   .\rebuild.ps1           - rebuild all three databases
#   .\rebuild.ps1 small    - rebuild pg_mcp_small only
#   .\rebuild.ps1 medium   - rebuild pg_mcp_medium only
#   .\rebuild.ps1 large    - rebuild pg_mcp_large only
#   .\rebuild.ps1 clean    - drop all three databases
#
# Environment: $env:PGHOST, $env:PGPORT, $env:PGUSER, $env:PGPASSWORD

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# PGBIN: optional path to PostgreSQL bin
$DefaultPGBins = @(
    $env:PGBIN,
    "D:\Program Files\PostgreSQL\bin"
)
foreach ($bin in $DefaultPGBins) {
    if (-not $bin) { continue }
    if (Test-Path (Join-Path $bin "psql.exe")) {
        $env:PATH = "$bin;$env:PATH"
        break
    }
}
$psqlExe = $null
foreach ($bin in $DefaultPGBins) {
    if (-not $bin) { continue }
    $p = Join-Path $bin "psql.exe"
    if (Test-Path $p) { $psqlExe = $p; break }
}
if (-not $psqlExe) {
    $p = (Get-Command psql -ErrorAction SilentlyContinue).Source
    if ($p) { $psqlExe = $p }
}
if (-not $psqlExe) {
    Write-Error "psql not found. Set `$env:PGBIN='D:\Program Files\PostgreSQL\bin' or add PostgreSQL bin to PATH"
    exit 1
}

$PGHOST = if ($env:PGHOST) { $env:PGHOST } else { "localhost" }
$PGPORT = if ($env:PGPORT) { $env:PGPORT } else { "5432" }
$PGUSER = if ($env:PGUSER) { $env:PGUSER } else { "postgres" }

$DB_SMALL  = "pg_mcp_small"
$DB_MEDIUM = "pg_mcp_medium"
$DB_LARGE  = "pg_mcp_large"

function Invoke-Psql {
    param([string]$Database, [string[]]$PsqlArgs)
    $allArgs = @("-h", $PGHOST, "-p", $PGPORT, "-U", $PGUSER, "-d", $Database, "-w")
    if ($PsqlArgs) { $allArgs += $PsqlArgs }
    & $psqlExe $allArgs
    if ($LASTEXITCODE -ne 0) { throw "psql exited with $LASTEXITCODE" }
}

function Rebuild-Db {
    param([string]$Name, [string]$SqlFile)
    Write-Host "Rebuilding $Name..."
    try {
        Invoke-Psql "postgres" -PsqlArgs @("-v", "ON_ERROR_STOP=1", "-c", "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$Name' AND pid <> pg_backend_pid();") 2>$null
    } catch { }
    Invoke-Psql "postgres" -PsqlArgs @("-v", "ON_ERROR_STOP=1", "-c", "DROP DATABASE IF EXISTS $Name;")
    Invoke-Psql "postgres" -PsqlArgs @("-v", "ON_ERROR_STOP=1", "-c", "CREATE DATABASE $Name;")
    Invoke-Psql $Name -PsqlArgs @("-f", $SqlFile)
    Write-Host "Done: $Name"
}

function Clean-Db {
    param([string]$Name)
    try {
        Invoke-Psql "postgres" -PsqlArgs @("-v", "ON_ERROR_STOP=1", "-c", "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$Name' AND pid <> pg_backend_pid();") 2>$null
    } catch { }
    Invoke-Psql "postgres" -PsqlArgs @("-v", "ON_ERROR_STOP=1", "-c", "DROP DATABASE IF EXISTS $Name;")
    Write-Host "Dropped: $Name"
}

$target = if ($args.Count -gt 0) { $args[0].ToLower() } else { "all" }

switch ($target) {
    "small"  { Rebuild-Db $DB_SMALL  (Join-Path $ScriptDir "small.sql") }
    "medium" { Rebuild-Db $DB_MEDIUM (Join-Path $ScriptDir "medium.sql") }
    "large"  { Rebuild-Db $DB_LARGE  (Join-Path $ScriptDir "large.sql") }
    "clean"  {
        Write-Host "Dropping fixtures..."
        foreach ($db in $DB_SMALL, $DB_MEDIUM, $DB_LARGE) { Clean-Db $db }
        Write-Host "Fixtures dropped."
    }
    "all"    {
        Rebuild-Db $DB_SMALL  (Join-Path $ScriptDir "small.sql")
        Rebuild-Db $DB_MEDIUM (Join-Path $ScriptDir "medium.sql")
        Rebuild-Db $DB_LARGE  (Join-Path $ScriptDir "large.sql")
        Write-Host "All fixtures rebuilt: $DB_SMALL, $DB_MEDIUM, $DB_LARGE"
    }
    default  {
        Write-Host "Usage: .\rebuild.ps1 [all|small|medium|large|clean]"
        Write-Host "Env: PGHOST PGPORT PGUSER PGPASSWORD"
        exit 1
    }
}
