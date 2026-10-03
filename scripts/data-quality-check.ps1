[CmdletBinding()]
param(
    [string]$InputPath = "data/sample/order_events.ndjson",
    [string]$ConfigPath = "config/data-quality-rules.json",
    [string]$OutputDirectory = "build/data-quality"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH

Push-Location $repoRoot
try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    python -m data_quality.cli `
        --input $InputPath `
        --config $ConfigPath `
        --json-output (Join-Path $OutputDirectory "report.json") `
        --markdown-output (Join-Path $OutputDirectory "report.md") `
        --history-db (Join-Path $OutputDirectory "history.db")
    if ($LASTEXITCODE -ne 0) {
        throw "Data-quality gate failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
