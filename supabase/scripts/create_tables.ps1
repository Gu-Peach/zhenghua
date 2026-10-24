<#
Apply canonical migrations to an already-started LOCAL Supabase.
Default: preview only. -Apply: migrate after reviewing the preview and backups.
Historical migration 20261014010000 permanently drops legacy business tables.
Do not bootstrap an existing database with missing migration history.
#>
[CmdletBinding()]
param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot 'supabase\config.toml'))) {
    throw 'Missing supabase/config.toml. Follow README.md to initialize a NEW local instance, or recover the existing instance configuration.'
}
if (-not (Get-Command supabase -ErrorAction SilentlyContinue)) {
    throw 'Supabase CLI is required. See README.md for installation.'
}

Push-Location $repositoryRoot
try {
    Write-Host 'Previewing pending migrations for the LOCAL instance in this repository.'
    & supabase db push --local --dry-run
    if ($LASTEXITCODE -ne 0) {
        throw "Migration preview failed (exit $LASTEXITCODE). No migration was requested."
    }
    if ($Apply) {
        Write-Warning 'Applying pending local migrations. Historical 20261014010000 deletes legacy business tables; existing data requires a reviewed backup/migration plan.'
        & supabase migration up --local
        if ($LASTEXITCODE -ne 0) {
            throw "Migration failed (exit $LASTEXITCODE). Inspect history before retrying; earlier migrations may already be committed."
        }
    } else {
        Write-Host 'Preview complete. Use -Apply only after reviewing pending SQL and the target instance.'
    }
} finally {
    Pop-Location
}
